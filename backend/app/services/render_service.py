from __future__ import annotations

import math
import subprocess
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from app.models import Asset, BgmTrack, Sequence
from app.services.media_probe import probe
from app.services.storage_service import bgm_library_dir, resolve_asset_path


@dataclass
class RenderOptions:
    duration_policy: str = "match_audio_loop_video"
    source_audio_policy: str = "mute"
    resolution: str = "1920x1080"
    fps: int = 30
    video_encoder: str = "h264_nvenc"
    fit_mode: str = "fit"
    voice_volume: float = 1.0
    source_volume: float = 0.25
    bgm_volume: float = 1.0
    bgm_loop: bool = True


def _parse_resolution(value: str) -> tuple[int, int]:
    try:
        width, height = (int(part) for part in value.lower().split("x", 1))
    except (ValueError, AttributeError) as exc:
        raise ValueError("Resolution phải có dạng 1920x1080") from exc
    if width < 16 or height < 16 or width > 7680 or height > 4320:
        raise ValueError("Resolution nằm ngoài phạm vi hỗ trợ")
    return width, height


def _expanded_assets(sequence: Sequence, audio: Asset | None, policy: str) -> list[Asset]:
    assets = [item.asset for item in sequence.items]
    if not assets:
        raise ValueError("Sequence không có video")
    if policy != "match_audio_loop_video" or audio is None or not audio.duration_ms:
        return assets
    sequence_ms = sum(item.duration_ms or 0 for item in assets)
    if sequence_ms <= 0:
        raise ValueError("Không xác định được thời lượng video")
    repeats = max(1, math.ceil(audio.duration_ms / sequence_ms))
    return assets * repeats


def _resolve_bgm_path(project_id: str, bgm: Asset | BgmTrack) -> Path:
    """Resolve the file path for a BGM, whether it's a project Asset or global BgmTrack."""
    if isinstance(bgm, BgmTrack):
        return bgm_library_dir() / bgm.relative_path
    return resolve_asset_path(project_id, bgm.relative_path)


def build_ffmpeg_command(
    project_id: str,
    sequence: Sequence,
    audio: Asset | None,
    output_partial: Path,
    options: RenderOptions,
    bgm: Asset | BgmTrack | None = None,
) -> tuple[list[str], float]:
    if options.duration_policy not in {"match_audio_loop_video", "match_video", "shortest"}:
        raise ValueError("Duration policy không hợp lệ")
    if options.source_audio_policy not in {"replace", "mix", "keep_original", "mute"}:
        raise ValueError("Source audio policy không hợp lệ")
    if options.video_encoder not in {"libx264", "h264_nvenc"}:
        raise ValueError("Video encoder không hợp lệ")
    width, height = _parse_resolution(options.resolution)
    assets = _expanded_assets(sequence, audio, options.duration_policy)
    total_video_ms = sum(item.duration_ms or 0 for item in assets)
    if total_video_ms <= 0:
        raise ValueError("Không xác định được thời lượng sequence")
    expected_ms = total_video_ms
    if audio and audio.duration_ms:
        if options.duration_policy == "match_audio_loop_video":
            expected_ms = audio.duration_ms
        elif options.duration_policy == "shortest":
            expected_ms = min(total_video_ms, audio.duration_ms)

    command = ["ffmpeg", "-y", "-hide_banner"]
    for asset in assets:
        command.extend(["-i", str(resolve_asset_path(project_id, asset.relative_path))])
    audio_index = None
    if audio:
        audio_index = len(assets)
        command.extend(["-i", str(resolve_asset_path(project_id, audio.relative_path))])

    bgm_index = None
    if bgm:
        bgm_index = len(assets) + (1 if audio else 0)
        if options.bgm_loop:
            command.extend(["-stream_loop", "-1"])
        command.extend(["-i", str(_resolve_bgm_path(project_id, bgm))])

    filters: list[str] = []
    concat_inputs: list[str] = []
    for index, asset in enumerate(assets):
        if options.fit_mode == "fill":
            video_filter = (
                f"scale={width}:{height}:force_original_aspect_ratio=increase,"
                f"crop={width}:{height}"
            )
        else:
            video_filter = (
                f"scale={width}:{height}:force_original_aspect_ratio=decrease,"
                f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:color=black"
            )
        filters.append(
            f"[{index}:v:0]{video_filter},fps={options.fps},setsar=1,setpts=PTS-STARTPTS[v{index}]"
        )
        duration = (asset.duration_ms or 1) / 1000
        if asset.has_audio:
            filters.append(
                f"[{index}:a:0]aresample=48000,aformat=sample_fmts=fltp:channel_layouts=stereo,"
                f"asetpts=PTS-STARTPTS[a{index}]"
            )
        else:
            filters.append(
                f"anullsrc=r=48000:cl=stereo,atrim=duration={duration:.6f},asetpts=PTS-STARTPTS[a{index}]"
            )
        concat_inputs.append(f"[v{index}][a{index}]")
    filters.append("".join(concat_inputs) + f"concat=n={len(assets)}:v=1:a=1[basev][basea]")

    mix_streams: list[str] = []

    # 1. Original video audio
    if options.source_audio_policy not in {"replace", "mute"}:
        filters.append(f"[basea]volume={options.source_volume}[orig]")
        mix_streams.append("[orig]")
    else:
        filters.append("[basea]anullsink")

    # 2. Voice TTS audio
    if audio_index is not None:
        filters.append(
            f"[{audio_index}:a:0]aresample=48000,aformat=sample_fmts=fltp:channel_layouts=stereo,"
            f"volume={options.voice_volume}[voice]"
        )
        mix_streams.append("[voice]")

    # 3. Background Music (BGM)
    if bgm_index is not None:
        filters.append(
            f"[{bgm_index}:a:0]aresample=48000,aformat=sample_fmts=fltp:channel_layouts=stereo,"
            f"volume={options.bgm_volume}[bgm]"
        )
        mix_streams.append("[bgm]")

    # Mix audio streams
    if len(mix_streams) > 1:
        inputs_str = "".join(mix_streams)
        filters.append(
            f"{inputs_str}amix=inputs={len(mix_streams)}:duration=longest:dropout_transition=0:normalize=0[mixeda]"
        )
        audio_map = "[mixeda]"
    elif len(mix_streams) == 1:
        audio_map = mix_streams[0]
    else:
        duration_sec = (expected_ms or 1000) / 1000
        filters.append(f"anullsrc=r=48000:cl=stereo,atrim=duration={duration_sec:.6f}[silencea]")
        audio_map = "[silencea]"

    if audio_index is not None and options.duration_policy == "match_video":
        filters.append(f"{audio_map}apad,atrim=duration={total_video_ms / 1000:.6f}[finala]")
        audio_map = "[finala]"

    command.extend(["-filter_complex", ";".join(filters), "-map", "[basev]", "-map", audio_map])
    command.extend(["-c:v", options.video_encoder])
    if options.video_encoder == "h264_nvenc":
        command.extend(["-preset", "p4", "-cq", "22"])
    else:
        command.extend(["-preset", "medium", "-crf", "20"])
    command.extend(["-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k", "-ar", "48000"])
    if options.duration_policy == "shortest":
        command.append("-shortest")
    elif expected_ms:
        command.extend(["-t", f"{expected_ms / 1000:.6f}"])
    command.extend(["-movflags", "+faststart", "-progress", "pipe:1", "-nostats", str(output_partial)])
    return command, expected_ms / 1000


def run_ffmpeg(
    command: list[str],
    expected_seconds: float,
    log_path: Path,
    cancel_event: threading.Event,
    on_progress: Callable[[float], None],
    on_process: Callable[[subprocess.Popen | None], None],
) -> None:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("w", encoding="utf-8") as log:
        log.write("COMMAND: " + subprocess.list2cmdline(command) + "\n\n")
        process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=log,
            text=True,
            encoding="utf-8",
            errors="replace",
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        on_process(process)
        try:
            assert process.stdout is not None
            last_progress = -1.0
            last_progress_at = 0.0
            for line in process.stdout:
                if cancel_event.is_set():
                    process.terminate()
                    raise InterruptedError("Job đã bị hủy")
                key, _, value = line.strip().partition("=")
                if key in {"out_time_ms", "out_time_us"} and expected_seconds > 0:
                    # FFmpeg may emit out_time_ms=N/A before the first frame.
                    # It is not an error and must not orphan the encoder process.
                    try:
                        seconds = int(value) / 1_000_000
                    except ValueError:
                        continue
                    progress = min(99.0, seconds / expected_seconds * 100)
                    now = time.monotonic()
                    # Limit database writes when several FFmpeg jobs report
                    # progress at once, while keeping the UI responsive.
                    if progress - last_progress >= 0.5 or now - last_progress_at >= 1.0:
                        on_progress(progress)
                        last_progress = progress
                        last_progress_at = now
            return_code = process.wait()
            if return_code != 0:
                raise RuntimeError(f"FFmpeg kết thúc với mã lỗi {return_code}; xem log {log_path}")
        finally:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()
            on_process(None)


def verify_output(path: Path) -> dict:
    result = probe(path)
    if not result.get("duration_ms") or not result.get("width"):
        raise RuntimeError("File output không có video hợp lệ")
    return result
