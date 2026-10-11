"""Smoke-test the production TTS job, MP3 output, progress, and audio editor."""

from __future__ import annotations

import time

import httpx


BASE_URL = "http://127.0.0.1:8878/api"


def wait(client: httpx.Client, job_id: str, timeout: float = 180) -> tuple[dict, list[float]]:
    deadline = time.time() + timeout
    progress: list[float] = []
    while time.time() < deadline:
        job = client.get(f"{BASE_URL}/jobs/{job_id}").raise_for_status().json()
        progress.append(job["progress"])
        if job["status"] in {"completed", "failed", "cancelled"}:
            return job, progress
        time.sleep(0.5)
    raise TimeoutError(job_id)


def main() -> None:
    with httpx.Client(timeout=180) as client:
        project = client.post(f"{BASE_URL}/projects", json={"name": "TTS v2 smoke"})
        project.raise_for_status()
        project_id = project.json()["id"]
        try:
            voices = client.get(f"{BASE_URL}/system/tts/voices?device=cuda").raise_for_status().json()
            assert voices
            response = client.post(
                f"{BASE_URL}/projects/{project_id}/tts/jobs",
                json={
                    "text": "Xin chào, đây là kiểm tra tiến độ và tham số nâng cao.",
                    "voice": voices[0]["id"],
                    "device": "cuda",
                    "name": "tts-advanced",
                    "output_format": "mp3",
                    "use_batch": True,
                    "batch_size": 8,
                    "temperature": 0.8,
                    "max_chars": 256,
                    "top_k": 25,
                    "top_p": 0.95,
                    "repetition_penalty": 1.2,
                    "silence_p": 0.15,
                },
            )
            response.raise_for_status()
            job, progress = wait(client, response.json()["id"])
            assert job["status"] == "completed", job
            assert any(5 < value < 100 for value in progress), progress
            assets = client.get(f"{BASE_URL}/projects/{project_id}/assets").raise_for_status().json()
            audio = next(item for item in assets if item["id"] == job["output_asset_id"])
            assert audio["codec"] == "mp3"
            edit = client.post(
                f"{BASE_URL}/assets/{audio['id']}/audio/jobs",
                json={
                    "name": "tts-faster",
                    "speed": 1.1,
                    "trim_start": 0,
                    "trim_end": max(0.2, audio["duration_ms"] / 1000 - 0.1),
                    "output_format": "mp3",
                },
            )
            edit.raise_for_status()
            edited, _ = wait(client, edit.json()["id"], timeout=60)
            assert edited["status"] == "completed", edited
            print(
                f"TTS_SMOKE_OK voices={len(voices)} progress_samples={len(progress)} "
                f"duration_ms={audio['duration_ms']}"
            )
        finally:
            client.delete(f"{BASE_URL}/projects/{project_id}").raise_for_status()


if __name__ == "__main__":
    main()
