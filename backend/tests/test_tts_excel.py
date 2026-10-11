import io
import json

from fastapi.testclient import TestClient
from openpyxl import Workbook

from app.api.jobs import job_manager
from app.main import app


def test_excel_import_queues_rows_with_incrementing_names(monkeypatch):
    monkeypatch.setattr(job_manager, "submit", lambda _job_id: None)
    workbook = Workbook()
    sheet = workbook.active
    sheet.append(["STT", "text"])
    sheet.append([1, "Đoạn thứ nhất"])
    sheet.append([2, "Đoạn thứ hai"])
    content = io.BytesIO()
    workbook.save(content)

    with TestClient(app) as client:
        project = client.post("/api/projects", json={"name": "Excel import"}).json()
        response = client.post(
            f"/api/projects/{project['id']}/tts/excel-jobs",
            data={
                "settings": json.dumps(
                    {"text": "placeholder", "voice": "Adam bua", "name": "kich-ban", "speed": 1.3, "group_name": "9-27-1"}
                )
            },
            files={
                "upload": (
                    "script.xlsx",
                    content.getvalue(),
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                )
            },
        )

    assert response.status_code == 202, response.text
    jobs = response.json()
    assert [job["input_json"]["name"] for job in jobs] == ["kich-ban_1", "kich-ban_2"]
    assert [job["input_json"]["text"] for job in jobs] == ["Đoạn thứ nhất", "Đoạn thứ hai"]
    assert all(job["input_json"]["speed"] == 1.3 for job in jobs)
    assert all(job["input_json"]["group_name"] == "9-27-1" for job in jobs)
