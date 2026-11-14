import subprocess

from fastapi.testclient import TestClient

from app.db.session import SessionLocal
from app.main import app
from app.models import Asset
from app.services.media_probe import create_thumbnail, probe
from app.services.storage_service import resolve_asset_path


def test_short_portrait_video_gets_cover_and_missing_cover_is_repaired(tmp_path):
    video = tmp_path / "portrait.mp4"
    subprocess.run([
        "ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i",
        "color=c=orange:s=90x160:r=25:d=0.04", "-c:v", "libx264", "-pix_fmt", "yuv420p", str(video),
    ], check=True)
    image = tmp_path / "short.jpg"
    create_thumbnail(video, image)
    assert image.read_bytes().startswith(b"\xff\xd8")
    info = probe(image)
    assert info["width"] / info["height"] == 9 / 16

    with TestClient(app) as client:
        project_id = client.post("/api/projects", json={"name": "Portrait covers"}).json()["id"]
        with video.open("rb") as upload:
            response = client.post(f"/api/projects/{project_id}/assets/import", files={"files": ("portrait.mp4", upload, "video/mp4")})
        assert response.status_code == 201, response.text
        asset = response.json()[0]
        assert asset["thumbnail_path"]
        resolve_asset_path(project_id, asset["thumbnail_path"]).unlink()
        with SessionLocal() as db:
            row = db.get(Asset, asset["id"])
            row.thumbnail_path = None
            db.commit()
        url = f"/api/assets/{asset['id']}/thumbnail"
        repaired = client.get(url)
        assert repaired.status_code == 200
        assert repaired.headers["content-type"] == "image/jpeg"
        assert repaired.content.startswith(b"\xff\xd8")
        with SessionLocal() as db:
            saved = db.get(Asset, asset["id"])
            saved_path = resolve_asset_path(project_id, saved.thumbnail_path)
            modified = saved_path.stat().st_mtime_ns
        assert client.get(url).content == repaired.content
        assert saved_path.stat().st_mtime_ns == modified

        # A versioned cover lets the UI replace legacy black thumbnails once.
        versioned_url = f"{url}?v=2"
        versioned = client.get(versioned_url)
        assert versioned.status_code == 200
        assert versioned.content.startswith(b"\xff\xd8")
        with SessionLocal() as db:
            row = db.get(Asset, asset["id"])
            versioned_path = resolve_asset_path(project_id, row.thumbnail_path)
        assert versioned_path.name == f"{asset['id']}.v2.jpg"
        versioned_modified = versioned_path.stat().st_mtime_ns
        assert client.get(versioned_url).content == versioned.content
        assert versioned_path.stat().st_mtime_ns == versioned_modified
