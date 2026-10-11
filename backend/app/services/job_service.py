from __future__ import annotations

import logging
import shutil
import subprocess
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.core.config import settings
from app.db.session import SessionLocal
from app.models import Asset, BgmTrack, Job, Project, Sequence, SequenceItem
from app.services.media_probe import probe
from app.services.render_service import RenderOptions, build_ffmpeg_command, run_ffmpeg, verify_output
from app.services.storage_service import (
    create_project_dirs,
    relative_to_project,
    resolve_asset_path,
    safe_filename,
    unique_destination,
)
from app.services.tts_service import tts_service


logger = logging.getLogger(__name__)
_output_path_lock = threading.Lock()


class JobManager:
    def __init__(self) -> None:
        self.executor = ThreadPoolExecutor(
            max_workers=settings.max_concurrent_jobs, thread_name_prefix="media-job"
        )
        # TTS uses a shared model and must be processed in submission order.
        # A dedicated single worker keeps later items genuinely queued instead
        # of marking several jobs as running while they wait on a lock.
        self.tts_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="tts-queue")
        self.cancel_events: dict[str, threading.Event] = {}
        self.processes: dict[str, subprocess.Popen] = {}
        self.lock = threading.Lock()

    def submit(self, job_id: str, kind: str | None = None) -> None:
        event = threading.Event()
        with self.lock:
            self.cancel_events[job_id] = event
        if kind is None:
            with SessionLocal() as db:
                job = db.get(Job, job_id)
                kind = job.kind if job else None
        executor = self.tts_executor if kind == "tts" else self.executor
        executor.submit(self._execute, job_id, event)

    def cancel(self, job_id: str) -> bool:
        with self.lock:
            event = self.cancel_events.get(job_id)
            process = self.processes.get(job_id)
        if not event:
            return False
        event.set()
        if process and process.poll() is None:
            process.terminate()
        return True

    def _set_process(self, job_id: str, process: subprocess.Popen | None) -> None:
        with self.lock:
            if process is None:
                self.processes.pop(job_id, None)
            else:
                self.processes[job_id] = process

    @staticmethod
    def _update(job_id: str, **values) -> None:
        with SessionLocal() as db:
            job = db.get(Job, job_id)
            if job:
                for key, value in values.items():
                    setattr(job, key, value)
                db.commit()

    def _execute(self, job_id: str, cancel_event: threading.Event) -> None:
        if cancel_event.is_set():
            return
        self._update(job_id, status="running", progress=1)
        try:
            with SessionLocal() as db:
                job = db.get(Job, job_id)
                if not job:
                    return
                kind = job.kind
            if kind == "tts":
                self._run_tts(job_id, cancel_event)
            elif kind == "audio_process":
                self._run_audio_process(job_id, cancel_event)
            elif kind == "render":
                self._run_render(job_id, cancel_event)
            else:
                raise ValueError(f"Unsupported job type: {kind}")
        except InterruptedError as exc:
            self._update(job_id, status="cancelled", error_message=str(exc))
        except Exception as exc:
            logger.exception("Job %s failed", job_id)
            self._update(job_id, status="failed", error_message=str(exc))
        finally:
            with self.lock:
                self.cancel_events.pop(job_id, None)
                self.processes.pop(job_id, None)

    def _run_tts(self, job_id: str, cancel_event: threading.Event) -> None:
        with SessionLocal() as db:
            job = db.get(Job, job_id)
            assert job is not None
            payload = job.input_json
            root = create_project_dirs(job.project_id)
            output_format = payload.get("output_format", "mp3").lower()
            if output_format not in {"wav", "mp3"}:
                raise ValueError("TTS format must be wav or mp3")
            name = safe_filename(payload.get("name", "voice"), "voice") + f".{output_format}"
            destination = unique_destination(root / "generated" / "tts", name)
            log_path = root / "logs" / f"tts-{job.id}.log"
            job.log_path = relative_to_project(job.project_id, log_path)
            db.commit()
            log_path.write_text(
                f"{datetime.now().isoformat()} START TTS\nvoice={payload['voice']} device={payload['device']}\n",
                encoding="utf-8",
            )
            self._update(job_id, progress=5)
            if cancel_event.is_set():
                raise InterruptedError("Job was cancelled")

            progress_stop = threading.Event()

            def estimate_progress() -> None:
                # The SDK does not expose a total frame count. This is an explicit estimate
                # based on text length and keeps the UI responsive until inference finishes.
                estimated_seconds = max(8.0, len(payload["text"]) / 18.0)
                started = time.monotonic()
                while not progress_stop.wait(1.0):
                    elapsed = time.monotonic() - started
                    value = 8 + min(84, elapsed / estimated_seconds * 84)
                    self._update(job_id, progress=round(value, 1))

            progress_thread = threading.Thread(target=estimate_progress, daemon=True)
            progress_thread.start()
            generation_options = {
                "temperature": payload.get("temperature", 0.8),
                "top_k": payload.get("top_k", 25),
                "top_p": payload.get("top_p", 0.95),
                "repetition_penalty": payload.get("repetition_penalty", 1.2),
                "silence_p": payload.get("silence_p", 0.15),
                "max_chars": payload.get("max_chars", 256),
                "batch_size": payload.get("batch_size", 16) if payload.get("use_batch", True) else 1,
            }
            try:
                tts_service.generate(
                    payload["text"],
                    payload["voice"],
                    destination,
                    payload["device"],
                    **generation_options,
                )
                speed = float(payload.get("speed", 1.0))
                if speed != 1.0:
                    sped_up = destination.with_name(f"{destination.stem}.speed{destination.suffix}")
                    command = [
                        "ffmpeg", "-y", "-hide_banner", "-i", str(destination), "-vn",
                        "-filter:a", f"atempo={speed}", "-ar", "48000",
                    ]
                    if output_format == "mp3":
                        command.extend(["-c:a", "libmp3lame", "-b:a", "192k"])
                    else:
                        command.extend(["-c:a", "pcm_s16le"])
                    command.append(str(sped_up))
                    result = subprocess.run(command, capture_output=True, text=True)
                    if result.returncode != 0:
                        sped_up.unlink(missing_ok=True)
                        raise RuntimeError(f"Không thể áp dụng tốc độ đọc: {result.stderr[-1000:]}")
                    sped_up.replace(destination)
            finally:
                progress_stop.set()
                progress_thread.join(timeout=1)
            if cancel_event.is_set():
                destination.unlink(missing_ok=True)
                raise InterruptedError("Job was cancelled")
            metadata = probe(destination)
            asset = Asset(
                project_id=job.project_id,
                type="tts_audio",
                display_name=destination.stem,
                relative_path=relative_to_project(job.project_id, destination),
                duration_ms=metadata["duration_ms"],
                codec=metadata["codec"],
                has_audio=True,
                metadata_json={
                    "text": payload["text"],
                    "voice": payload["voice"],
                    "device": payload["device"],
                    "generation_options": generation_options,
                    "output_format": output_format,
                    "speed": float(payload.get("speed", 1.0)),
                    "group_name": payload.get("group_name") or None,
                },
            )
            db.add(asset)
            db.flush()
            job.output_asset_id = asset.id
            job.status = "completed"
            job.progress = 100
            job.error_message = None
            db.commit()
            with log_path.open("a", encoding="utf-8") as log:
                log.write(f"{datetime.now().isoformat()} COMPLETED asset={asset.id}\n")

    def _run_audio_process(self, job_id: str, cancel_event: threading.Event) -> None:
        with SessionLocal() as db:
            job = db.get(Job, job_id)
            assert job is not None
            payload = job.input_json
            source = db.get(Asset, payload["asset_id"])
            if not source or source.project_id != job.project_id:
                raise ValueError("Audio source was not found")
            root = create_project_dirs(job.project_id)
            output_format = payload.get("output_format", "mp3").lower()
            if output_format not in {"wav", "mp3"}:
                raise ValueError("Audio format must be wav or mp3")
            base_name = payload.get("name") or f"{source.display_name}-edited"
            destination = unique_destination(
                root / "generated" / "tts", safe_filename(base_name, "audio") + f".{output_format}"
            )
            partial = destination.with_name(f"{destination.stem}.partial{destination.suffix}")
            log_path = root / "logs" / f"audio-{job.id}.log"
            speed = float(payload.get("speed", 1.0))
            trim_start = float(payload.get("trim_start", 0))
            trim_end = payload.get("trim_end")
            source_duration = (source.duration_ms or 0) / 1000
            selected_duration = max(0.01, (float(trim_end) if trim_end else source_duration) - trim_start)
            expected_seconds = selected_duration / speed
            command = ["ffmpeg", "-y", "-hide_banner", "-ss", str(trim_start)]
            if trim_end:
                command.extend(["-to", str(trim_end)])
            command.extend(
                [
                    "-i",
                    str(resolve_asset_path(job.project_id, source.relative_path)),
                    "-vn",
                    "-filter:a",
                    f"atempo={speed}",
                    "-ar",
                    "48000",
                ]
            )
            if output_format == "mp3":
                command.extend(["-c:a", "libmp3lame", "-b:a", "192k"])
            else:
                command.extend(["-c:a", "pcm_s16le"])
            command.extend(["-progress", "pipe:1", "-nostats", str(partial)])
            job.log_path = relative_to_project(job.project_id, log_path)
            job.status = "processing"
            db.commit()
            try:
                run_ffmpeg(
                    command,
                    expected_seconds,
                    log_path,
                    cancel_event,
                    lambda value: self._update(job_id, progress=round(value, 2)),
                    lambda proc: self._set_process(job_id, proc),
                )
            except Exception:
                partial.unlink(missing_ok=True)
                raise
            partial.replace(destination)
            info = probe(destination)
            asset = Asset(
                project_id=job.project_id,
                type="tts_audio",
                display_name=destination.stem,
                relative_path=relative_to_project(job.project_id, destination),
                duration_ms=info["duration_ms"],
                codec=info["codec"],
                has_audio=True,
                metadata_json={
                    "source_asset_id": source.id,
                    "speed": speed,
                    "trim_start": trim_start,
                    "trim_end": trim_end,
                    "output_format": output_format,
                    "group_name": payload.get("group_name") or source.metadata_json.get("group_name"),
                },
            )
            db.add(asset)
            db.flush()
            job.output_asset_id = asset.id
            job.status = "completed"
            job.progress = 100
            job.error_message = None
            db.commit()

    def _run_render(self, job_id: str, cancel_event: threading.Event) -> None:
        with SessionLocal() as db:
            job = db.get(Job, job_id)
            assert job is not None
            payload = job.input_json
            sequence = db.scalar(
                select(Sequence)
                .where(Sequence.id == payload["sequence_id"])
                .options(selectinload(Sequence.items).selectinload(SequenceItem.asset))
            )
            if not sequence:
                raise ValueError("Sequence was not found")
            audio = db.get(Asset, payload.get("audio_asset_id")) if payload.get("audio_asset_id") else None
            bgm_id = payload.get("bgm_asset_id")
            bgm = None
            if bgm_id:
                bgm = db.get(Asset, bgm_id)
                if not bgm:
                    bgm = db.get(BgmTrack, bgm_id)  # fallback to global library
            root = create_project_dirs(job.project_id)
            timestamp = datetime.now().strftime("%d-%m-%Y_%H-%M-%S")
            project = db.get(Project, job.project_id)
            custom_name = payload.get("custom_name") or (audio.display_name if audio else "original")
            filename = payload.get("output_filename") or (
                f"{safe_filename(project.name if project else 'project', 'project')}_"
                f"{safe_filename(custom_name, 'output')}_{safe_filename(sequence.name, 'sequence')}_"
                f"{timestamp}.mp4"
            )
            run_folder = safe_filename(payload.get("run_folder", timestamp), timestamp)
            output_directory = root / "outputs" / run_folder
            output_directory.mkdir(parents=True, exist_ok=True)
            if shutil.disk_usage(root).free < 500 * 1024 * 1024:
                raise RuntimeError("Less than 500 MB free disk space")
            # Reserve the output name atomically. Multiple batches can be
            # submitted in the same second and must never share a partial or
            # final path while FFmpeg jobs are running concurrently.
            with _output_path_lock:
                final_path = unique_destination(output_directory, filename)
                final_path.touch(exist_ok=False)
            partial_path = final_path.with_name(f"{final_path.stem}.{job_id}.partial.mp4")
            log_path = root / "logs" / f"render-{job.id}.log"
            job.log_path = relative_to_project(job.project_id, log_path)
            db.commit()
            try:
                options = RenderOptions(**payload["options"])
                command, expected_seconds = build_ffmpeg_command(
                    job.project_id, sequence, audio, partial_path, options, bgm=bgm
                )
            except Exception:
                final_path.unlink(missing_ok=True)
                raise
            project_id = job.project_id
            sequence_id = sequence.id
            sequence_batch_name = sequence.batch_name
            audio_id = audio.id if audio else None
            # FFmpeg can run for minutes. Do not reserve a PostgreSQL pool
            # connection while the external process is doing CPU/GPU work.
            db.close()
            self._update(job_id, status="rendering", progress=3)

            try:
                run_ffmpeg(
                    command,
                    expected_seconds,
                    log_path,
                    cancel_event,
                    lambda value: self._update(job_id, progress=round(value, 2)),
                    lambda proc: self._set_process(job_id, proc),
                )
            except Exception:
                partial_path.unlink(missing_ok=True)
                final_path.unlink(missing_ok=True)
                raise
            if cancel_event.is_set():
                partial_path.unlink(missing_ok=True)
                final_path.unlink(missing_ok=True)
                raise InterruptedError("Job was cancelled")
            partial_path.replace(final_path)
            try:
                metadata = verify_output(final_path)
            except Exception:
                final_path.unlink(missing_ok=True)
                raise
            job = db.get(Job, job_id)
            if not job:
                final_path.unlink(missing_ok=True)
                raise ValueError("Job was removed while rendering")
            asset = Asset(
                project_id=project_id,
                type="output",
                display_name=final_path.name,
                relative_path=relative_to_project(project_id, final_path),
                duration_ms=metadata["duration_ms"],
                width=metadata["width"],
                height=metadata["height"],
                fps=metadata["fps"],
                codec=metadata["codec"],
                has_audio=metadata["has_audio"],
                metadata_json={
                    "sequence_id": sequence_id,
                    "audio_asset_id": audio_id,
                    "batch_name": sequence_batch_name,
                    "group_name": payload.get("group_name") or sequence_batch_name,
                    "run_folder": run_folder,
                    "custom_name": custom_name,
                    "output_index": payload.get("output_index"),
                    "run_timestamp": payload.get("run_timestamp"),
                },
            )
            db.add(asset)
            db.flush()
            job.output_asset_id = asset.id
            job.status = "completed"
            job.progress = 100
            job.error_message = None
            db.commit()


job_manager = JobManager()
