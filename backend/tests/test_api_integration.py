from __future__ import annotations

import subprocess
import time
from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app


def make_video(path: Path, color: str) -> None:
    subprocess.run(
        [
            "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
            "-f", "lavfi", "-i", f"color=c={color}:s=320x240:r=24:d=0.6",
            "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=48000:duration=0.6",
            "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", str(path),
        ],
        check=True,
    )


def make_audio(path: Path, duration: float = 2.0) -> None:
    subprocess.run(
        [
            "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
            "-f", "lavfi", "-i", f"sine=frequency=700:sample_rate=48000:duration={duration}",
            "-c:a", "pcm_s16le", str(path),
        ],
        check=True,
    )


def wait_for_job(client: TestClient, job_id: str) -> dict:
    job = {}
    for _ in range(150):
        job = client.get(f"/api/jobs/{job_id}").json()
        if job["status"] in {"completed", "failed", "cancelled"}:
            return job
        time.sleep(0.1)
    raise AssertionError(f"Job {job_id} không hoàn thành đúng hạn: {job}")


def test_project_media_sequence_and_real_render(tmp_path: Path):
    video_a = tmp_path / "a.mp4"
    video_b = tmp_path / "b.mp4"
    narration = tmp_path / "narration.wav"
    make_video(video_a, "red")
    make_video(video_b, "blue")
    make_audio(narration)

    with TestClient(app) as client:
        project_response = client.post("/api/projects", json={"name": "Integration test"})
        assert project_response.status_code == 201
        project_id = project_response.json()["id"]

        with video_a.open("rb") as a, video_b.open("rb") as b:
            upload = client.post(
                f"/api/projects/{project_id}/assets/import",
                files=[("files", ("a.mp4", a, "video/mp4")), ("files", ("b.mp4", b, "video/mp4"))],
            )
        assert upload.status_code == 201, upload.text
        assets = upload.json()
        assert len(assets) == 2
        assert all(item["duration_ms"] for item in assets)
        assert all(item["thumbnail_path"] for item in assets)

        generated = client.post(
            f"/api/projects/{project_id}/sequences/generate",
            json={
                "video_asset_ids": [item["id"] for item in assets],
                "mode": "product_with_repetition",
                "length": 2,
                "limit": 100,
                "batch_name": "Tui xach loai 1",
            },
        )
        assert generated.status_code == 201, generated.text
        sequences = generated.json()
        assert {item["name"] for item in sequences} == {"A-A", "A-B", "B-A", "B-B"}
        assert {item["batch_name"] for item in sequences} == {"Tui xach loai 1"}

        render = client.post(
            f"/api/projects/{project_id}/render/jobs",
            json={
                "sequence_ids": [sequences[0]["id"]],
                "audio_asset_id": None,
                "allow_missing_audio": True,
                "duration_policy": "match_video",
                "source_audio_policy": "keep_original",
                "resolution": "320x240",
                "fps": 24,
                "video_encoder": "libx264",
                "fit_mode": "fit",
            },
        )
        assert render.status_code == 202, render.text
        job_id = render.json()[0]["id"]
        job = wait_for_job(client, job_id)
        assert job["status"] == "completed", job.get("error_message")
        output = client.get(f"/api/assets/{job['output_asset_id']}/stream")
        assert output.status_code == 200
        assert len(output.content) > 1000

        with narration.open("rb") as audio_file:
            audio_upload = client.post(
                f"/api/projects/{project_id}/assets/import",
                files=[("files", ("narration.wav", audio_file, "audio/wav"))],
            )
        assert audio_upload.status_code == 201, audio_upload.text
        audio_id = audio_upload.json()[0]["id"]

        processed_response = client.post(
            f"/api/assets/{audio_id}/audio/jobs",
            json={
                "name": "narration-fast",
                "speed": 1.2,
                "trim_start": 0.1,
                "trim_end": 1.7,
                "output_format": "mp3",
            },
        )
        assert processed_response.status_code == 202, processed_response.text
        processed_job = wait_for_job(client, processed_response.json()["id"])
        assert processed_job["status"] == "completed", processed_job.get("error_message")
        processed_assets = client.get(f"/api/projects/{project_id}/assets").json()
        processed_audio = next(item for item in processed_assets if item["id"] == processed_job["output_asset_id"])
        assert processed_audio["codec"] == "mp3"
        assert 1250 <= processed_audio["duration_ms"] <= 1450

        for source_policy in ("replace", "mix"):
            with_audio = client.post(
                f"/api/projects/{project_id}/render/jobs",
                json={
                    "sequence_ids": [sequences[1]["id"]],
                    "audio_asset_id": audio_id,
                    "duration_policy": "match_audio_loop_video",
                    "source_audio_policy": source_policy,
                    "resolution": "320x240",
                    "fps": 24,
                    "video_encoder": "libx264",
                    "fit_mode": "fit",
                    "voice_volume": 1,
                    "source_volume": 0.2,
                },
            )
            assert with_audio.status_code == 202, with_audio.text
            audio_job = wait_for_job(client, with_audio.json()[0]["id"])
            assert audio_job["status"] == "completed", audio_job.get("error_message")
            project_assets = client.get(f"/api/projects/{project_id}/assets").json()
            rendered = next(item for item in project_assets if item["id"] == audio_job["output_asset_id"])
            assert 1900 <= rendered["duration_ms"] <= 2100

        mapped_render = client.post(
            f"/api/projects/{project_id}/render/jobs",
            json={
                "items": [
                    {
                        "sequence_id": sequences[2]["id"],
                        "audio_asset_id": processed_audio["id"],
                        "source_audio_policy": "replace",
                        "custom_name": "tui-do",
                    }
                ],
                "run_name": "chien-dich-thang-9",
                "duration_policy": "match_audio_loop_video",
                "resolution": "320x240",
                "fps": 24,
                "video_encoder": "libx264",
                "fit_mode": "fit",
            },
        )
        assert mapped_render.status_code == 202, mapped_render.text
        mapped_job = wait_for_job(client, mapped_render.json()[0]["id"])
        assert mapped_job["status"] == "completed", mapped_job.get("error_message")
        final_assets = client.get(f"/api/projects/{project_id}/assets").json()
        mapped_output = next(item for item in final_assets if item["id"] == mapped_job["output_asset_id"])
        assert mapped_output["metadata_json"]["custom_name"] == "chien-dich-thang-9"
        assert mapped_output["metadata_json"]["batch_name"] == "Tui xach loai 1"
