import asyncio
import io
import json
import threading
import time

import httpx
from fastapi.testclient import TestClient
from openpyxl import Workbook

from app.api import jobs as jobs_api
from app.db.session import SessionLocal
from app.main import app
from app.models import Job
from app.services.job_service import JobManager


def test_slow_excel_does_not_block_other_requests(monkeypatch):
    monkeypatch.setattr(jobs_api.job_manager, "submit", lambda *args, **kwargs: None)
    book = Workbook()
    book.active.append(["STT", "text"])
    book.active.append([1, "Test narration"])
    content = io.BytesIO()
    book.save(content)
    entered = threading.Event()
    release = threading.Event()
    original = jobs_api.load_workbook

    def slow_workbook(*args, **kwargs):
        entered.set()
        release.wait(3)
        return original(*args, **kwargs)

    monkeypatch.setattr(jobs_api, "load_workbook", slow_workbook)
    with TestClient(app) as client:
        project_id = client.post("/api/projects", json={"name": "Responsive Excel"}).json()["id"]

        async def scenario():
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as async_client:
                started = time.monotonic()
                task = asyncio.create_task(async_client.post(
                    f"/api/projects/{project_id}/tts/excel-jobs",
                    data={"settings": json.dumps({"text": "placeholder", "voice": "test", "group_name": "test-group"})},
                    files={"upload": ("scripts.xlsx", content.getvalue())},
                ))
                try:
                    while not entered.is_set() and time.monotonic() - started < 2:
                        await asyncio.sleep(.005)
                    health = await async_client.get("/api/health")
                    assert health.status_code == 200
                    assert time.monotonic() - started < 1, "Excel blocked the API event loop"
                    assert not task.done(), "Excel must still be processing while health responds"
                finally:
                    release.set()
                    response = await task
                assert response.status_code == 202, response.text

        asyncio.run(scenario())


def test_active_jobs_remain_visible_and_cancel_before_dispatch(monkeypatch):
    monkeypatch.setattr(jobs_api.job_manager, "submit", lambda *args, **kwargs: None)
    with TestClient(app) as client:
        project_id = client.post("/api/projects", json={"name": "Large queue"}).json()["id"]
        with SessionLocal() as db:
            queued = Job(project_id=project_id, kind="tts", status="queued", input_json={})
            db.add(queued)
            db.commit()
            job_id = queued.id
            db.add_all([Job(project_id=project_id, kind="render", status="completed", input_json={}) for _ in range(105)])
            db.commit()
        rows = client.get(f"/api/jobs?project_id={project_id}&limit=10").json()
        assert len(rows) == 11
        assert any(row["id"] == job_id for row in rows)
        cancelled = client.post(f"/api/jobs/{job_id}/cancel")
        assert cancelled.json()["status"] == "cancelled"
        manager = JobManager()
        called = []
        monkeypatch.setattr(manager, "_run_tts", lambda *args: called.append(True))
        manager._execute(job_id, threading.Event())
        assert called == []
        assert client.get(f"/api/jobs/{job_id}").json()["status"] == "cancelled"
        async def terminal_event():
            response = await jobs_api.events(project_id)
            stream = response.body_iterator
            try:
                message = await anext(stream)
                payload = json.loads(message.split("data: ", 1)[1].strip())
                assert next(row for row in payload if row["id"] == job_id)["status"] == "cancelled"
            finally:
                await stream.aclose()
        asyncio.run(terminal_event())
        manager.executor.shutdown()
        manager.tts_executor.shutdown()
