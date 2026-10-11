import io
import json

from fastapi.testclient import TestClient
from openpyxl import Workbook

from app.main import app
from app.api.jobs import job_manager
from app.db.session import SessionLocal
from app.models import Asset, Sequence


def test_excel_groups_and_manual_text(monkeypatch):
    monkeypatch.setattr(job_manager, 'submit', lambda _: None)
    book = Workbook()
    book.active.append(['STT', 'text'])
    book.active.append([1, 'Xin chào'])
    content = io.BytesIO()
    book.save(content)
    with TestClient(app) as client:
        project = client.post('/api/projects', json={'name': 'Group rules'}).json()['id']
        payload = {'text': 'Xin chào', 'voice': 'test', 'group_name': '9-27-1'}
        def upload(settings):
            return client.post(f'/api/projects/{project}/tts/excel-jobs', data={'settings': json.dumps(settings)}, files={'upload': ('scripts.xlsx', content.getvalue())})
        assert upload({**payload, 'group_name': None}).status_code == 422
        first = upload(payload)
        assert first.status_code == 202
        assert first.json()[0]['input_json']['group_name'] == '9-27-1'
        assert upload(payload).status_code == 409
        single = client.post(f'/api/projects/{project}/tts/jobs', json=payload)
        assert single.status_code == 202
        assert single.json()['input_json']['group_name'] is None


def test_render_requires_explicit_audio_exceptions(monkeypatch):
    monkeypatch.setattr(job_manager, 'submit', lambda _: None)
    with TestClient(app) as client:
        project = client.post('/api/projects', json={'name': 'Render rules'}).json()['id']
        with SessionLocal() as db:
            seqs = [Sequence(project_id=project, name=f'Video {i}', batch_name='Batch') for i in range(2)]
            audio = Asset(project_id=project, type='tts_audio', display_name='voice', relative_path='voice.wav', metadata_json={})
            db.add_all([*seqs, audio])
            db.commit()
            ids = [seq.id for seq in seqs]
            aid = audio.id
        endpoint = f'/api/projects/{project}/render/jobs'
        missing = {'sequence_ids': ids}
        assert client.post(endpoint, json=missing).status_code == 400
        assert client.post(endpoint, json={**missing, 'allow_missing_audio': True}).status_code == 202
        duplicate = {'items': [{'sequence_id': sid, 'audio_asset_id': aid} for sid in ids]}
        assert client.post(endpoint, json=duplicate).status_code == 400
        allowed = client.post(endpoint, json={**duplicate, 'allow_duplicate_audio': True})
        assert allowed.status_code == 202
        options = allowed.json()[0]['input_json']['options']
        assert options['video_encoder'] == 'h264_nvenc'
        assert options['source_audio_policy'] == 'mute'
        assert options['bgm_volume'] == options['voice_volume'] == 1.0
