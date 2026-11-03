from types import SimpleNamespace
import json

import numpy as np
import pytest
import soundfile as sf
from fastapi.testclient import TestClient

from app.main import app
from app.services import voice_library
from app.services.tts_service import TTSService, tts_service


@pytest.fixture
def library(tmp_path, monkeypatch):
    monkeypatch.setattr(voice_library, "settings", SimpleNamespace(data_dir=tmp_path))
    return tmp_path / "voices"


def test_clone_survives_service_restart_and_does_not_modify_presets(library, tmp_path, monkeypatch):
    source = tmp_path / "sample.wav"
    sf.write(source, np.zeros(48000 * 4), 48000)
    calls = []

    class Engine:
        def add_voice(self, name, reference, **kwargs):
            calls.append((name, kwargs["save"]))

        def get_preset_voice(self, name):
            return {"speaker_emb": np.array([0.1, 0.2]), "codes": np.array([[1, 2]])}

        def remove_voice(self, name, **kwargs):
            calls.append((name, "removed"))

    monkeypatch.setattr(tts_service, "_load", lambda device: Engine())
    item = voice_library.clone_voice("Giọng của tôi", source, "cpu")
    assert item["custom"] is True
    assert calls == [(item["id"], False), (item["id"], "removed")]
    assert (library / f"{item['id']}.wav").exists()
    assert voice_library.custom_voices() == [item]
    preset = voice_library.resolve_voice(item["id"])
    assert np.allclose(preset["speaker_emb"], [0.1, 0.2])
    assert preset["codes"].tolist() == [[1, 2]]
    new_service = TTSService()
    assert item in new_service.voices("cpu")


def test_preview_caches_two_sentences_and_serves_audio(library, monkeypatch):
    calls = []
    monkeypatch.setattr(tts_service, "voices", lambda device: [{"id": "sample", "label": "Sample"}])

    def generate(text, voice, destination, device, **kwargs):
        calls.append(text)
        sf.write(destination, np.zeros(4800), 48000)

    monkeypatch.setattr(tts_service, "generate", generate)
    first = voice_library.preview_voice("sample", "cpu")
    assert first == voice_library.preview_voice("sample", "cpu")
    assert calls == [voice_library.PREVIEW_TEXT]
    assert voice_library.PREVIEW_TEXT.count(".") == 2
    client = TestClient(app)
    response = client.get(first["audio_url"])
    assert response.status_code == 200
    assert response.headers["content-type"] == "audio/wav"
    assert client.get('/api/system/tts/previews/not-a-hash.wav').status_code == 404


def test_bad_voice_cannot_escape_library(library):
    with pytest.raises(ValueError):
        voice_library.resolve_voice("clone_../../.env")
    with pytest.raises(ValueError):
        voice_library.resolve_voice("clone_" + "0" * 32)


def test_clone_upload_rejects_empty_invalid_and_oversize_audio(library):
    client = TestClient(app)
    url = "/api/system/tts/voices/clone"
    assert client.post(url, data={"name": "Voice"}, files={"upload": ("sample.wav", b"")}).status_code == 400
    assert client.post(url, data={"name": "Voice"}, files={"upload": ("sample.exe", b"audio")}).status_code == 415
    assert client.post(url, data={"name": "Voice"}, files={"upload": ("sample.wav", b"x" * (20 * 1024 * 1024 + 1))}).status_code == 413
    assert client.post(url, data={"name": "Voice", "device": "other"}, files={"upload": ("sample.wav", b"audio")}).status_code == 422


def test_clone_rejects_short_audio_before_loading_model(library, tmp_path, monkeypatch):
    source = tmp_path / "short.wav"
    sf.write(source, np.zeros(4800), 48000)
    monkeypatch.setattr(tts_service, "_load", lambda _: pytest.fail("Model must not load for invalid audio"))
    with pytest.raises(ValueError, match="3 đến 30"):
        voice_library.clone_voice("Voice", source, "cpu")
    assert not list(library.glob("clone_*.json"))


def test_startup_prepares_all_samples_and_reuses_them_across_devices(library, monkeypatch):
    monkeypatch.setattr(tts_service, "voices", lambda device: [{"id": "one"}, {"id": "two"}])
    calls = []

    def generate(text, voice, destination, device, **kwargs):
        calls.append(voice)
        sf.write(destination, np.zeros(4800), 48000)

    monkeypatch.setattr(tts_service, "generate", generate)
    voice_library.prepare_previews("cuda")
    assert calls == ["one", "two"]
    voice_library.prepare_previews("cpu")
    assert calls == ["one", "two"]
    assert voice_library.preview_url("one")
    assert voice_library.preview_voice("one", "cpu")["audio_url"] == voice_library.preview_url("one")


def test_model_preload_also_prepares_listening_samples(monkeypatch):
    service = TTSService()
    calls = []
    monkeypatch.setattr(service, "_load", lambda device: calls.append(("model", device)))
    monkeypatch.setattr(voice_library, "prepare_previews", lambda device: calls.append(("previews", device)))
    service.preload("cuda")
    assert calls == [("model", "cuda"), ("previews", "cuda")]


def test_rename_keeps_voice_data_id_and_preview(library):
    voice_id = 'clone_' + 'a' * 32
    library.mkdir(parents=True)
    manifest = library / f'{voice_id}.json'
    payload = {"name": "Tên cũ", "voice": {"speaker_emb": [0.1, 0.2], "codes": [[1, 2]]}, "duration": 4}
    manifest.write_text(json.dumps(payload), encoding='utf-8')
    sample = voice_library.preview_path(voice_id)
    sample.parent.mkdir()
    sample.write_bytes(b'cached preview')
    client = TestClient(app)
    response = client.patch(f'/api/system/tts/voices/{voice_id}', json={"name": "  Giọng mình · Review  "})
    assert response.status_code == 200
    assert response.json()['id'] == voice_id
    assert response.json()['label'] == 'Giọng clone · Giọng mình · Review'
    stored = json.loads(manifest.read_text(encoding='utf-8'))
    assert stored['name'] == 'Giọng mình · Review'
    assert stored['voice'] == payload['voice']
    assert stored['duration'] == payload['duration']
    assert response.json()['preview_url'] == voice_library.preview_url(voice_id)
    assert voice_library.custom_voices()[0]['label'] == response.json()['label']
    assert client.patch(f'/api/system/tts/voices/{voice_id}', json={'name': '   '}).status_code == 400
    assert client.patch('/api/system/tts/voices/builtin', json={'name': 'New'}).status_code == 400
    assert client.patch('/api/system/tts/voices/clone_' + 'b' * 32, json={'name': 'New'}).status_code == 404
