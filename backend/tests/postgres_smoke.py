"""Run an end-to-end smoke test against an already running local server."""

from __future__ import annotations

import subprocess
import tempfile
import time
from pathlib import Path

import httpx


BASE_URL = "http://127.0.0.1:8878/api"


def make_video(path: Path, color: str, frequency: int) -> None:
    subprocess.run(
        [
            "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
            "-f", "lavfi", "-i", f"color=c={color}:s=320x240:r=24:d=0.5",
            "-f", "lavfi", "-i", f"sine=frequency={frequency}:sample_rate=48000:duration=0.5",
            "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", str(path),
        ],
        check=True,
    )


def main() -> None:
    project_id = None
    with httpx.Client(timeout=60) as client:
        status = client.get(f"{BASE_URL}/system/status").raise_for_status().json()
        assert status["database"]["ok"] is True
        project = client.post(f"{BASE_URL}/projects", json={"name": "PostgreSQL smoke test"})
        project.raise_for_status()
        project_id = project.json()["id"]
        try:
            with tempfile.TemporaryDirectory() as temp:
                root = Path(temp)
                first, second = root / "first.mp4", root / "second.mp4"
                make_video(first, "green", 440)
                make_video(second, "purple", 660)
                with first.open("rb") as one, second.open("rb") as two:
                    upload = client.post(
                        f"{BASE_URL}/projects/{project_id}/assets/import",
                        files=[
                            ("files", (first.name, one, "video/mp4")),
                            ("files", (second.name, two, "video/mp4")),
                        ],
                    )
                upload.raise_for_status()
                assets = upload.json()
                generated = client.post(
                    f"{BASE_URL}/projects/{project_id}/sequences/generate",
                    json={
                        "video_asset_ids": [asset["id"] for asset in assets],
                        "mode": "product_with_repetition",
                        "length": 2,
                        "limit": 100,
                    },
                )
                generated.raise_for_status()
                sequences = generated.json()
                assert len(sequences) == 4
                render = client.post(
                    f"{BASE_URL}/projects/{project_id}/render/jobs",
                    json={
                        "sequence_ids": [sequences[1]["id"]],
                        "audio_asset_id": None,
                        "duration_policy": "match_video",
                        "source_audio_policy": "keep_original",
                        "resolution": "320x240",
                        "fps": 24,
                        "video_encoder": "libx264",
                        "fit_mode": "fit",
                    },
                )
                render.raise_for_status()
                job_id = render.json()[0]["id"]
                job = {}
                for _ in range(200):
                    job = client.get(f"{BASE_URL}/jobs/{job_id}").raise_for_status().json()
                    if job["status"] in {"completed", "failed", "cancelled"}:
                        break
                    time.sleep(0.1)
                assert job["status"] == "completed", job
                output = client.get(f"{BASE_URL}/assets/{job['output_asset_id']}/stream")
                output.raise_for_status()
                assert len(output.content) > 1000
                print(
                    f"POSTGRES_SMOKE_OK project={project_id} sequences={len(sequences)} "
                    f"output_bytes={len(output.content)}"
                )
        finally:
            if project_id:
                client.delete(f"{BASE_URL}/projects/{project_id}").raise_for_status()


if __name__ == "__main__":
    main()
