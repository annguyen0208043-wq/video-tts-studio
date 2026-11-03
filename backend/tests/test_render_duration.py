from pathlib import Path
from types import SimpleNamespace

from app.services.render_service import RenderOptions, _expanded_assets, build_ffmpeg_command


def asset(name: str, duration_ms: int, *, has_audio: bool = False):
    return SimpleNamespace(
        relative_path=f"source/videos/{name}.mp4",
        duration_ms=duration_ms,
        has_audio=has_audio,
    )


def test_extend_video_to_audio_repeats_pair_and_uses_audio_duration():
    first = asset("a", 8_000)
    second = asset("b", 10_000)
    voice = SimpleNamespace(relative_path="generated/tts/voice.mp3", duration_ms=24_000)
    sequence = SimpleNamespace(items=[SimpleNamespace(asset=first), SimpleNamespace(asset=second)])

    expanded = _expanded_assets(sequence, voice, "extend_video_to_audio")
    assert expanded == [first, second, first, second]

    command, expected_seconds = build_ffmpeg_command(
        "project-id",
        sequence,
        voice,
        Path("output.partial.mp4"),
        RenderOptions(duration_policy="extend_video_to_audio", video_encoder="libx264"),
    )
    assert expected_seconds == 24
    assert command[command.index("-t") + 1] == "24.000000"


def test_extend_video_to_audio_keeps_full_video_when_audio_is_shorter():
    first = asset("a", 8_000)
    second = asset("b", 10_000)
    voice = SimpleNamespace(relative_path="generated/tts/voice.mp3", duration_ms=12_000)
    sequence = SimpleNamespace(items=[SimpleNamespace(asset=first), SimpleNamespace(asset=second)])

    expanded = _expanded_assets(sequence, voice, "extend_video_to_audio")
    assert expanded == [first, second]

    command, expected_seconds = build_ffmpeg_command(
        "project-id",
        sequence,
        voice,
        Path("output.partial.mp4"),
        RenderOptions(duration_policy="extend_video_to_audio", video_encoder="libx264"),
    )
    assert expected_seconds == 18
    assert command[command.index("-t") + 1] == "18.000000"
