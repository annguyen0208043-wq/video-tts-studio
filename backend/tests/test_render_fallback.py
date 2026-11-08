import threading
from unittest.mock import Mock

import pytest

from app.services import render_service


@pytest.mark.parametrize("cancelled,diagnostic,retries", [
    (False, "Driver does not support the required nvenc API version", True),
    (False, "No NVENC capable devices found", True),
    (False, "Invalid input data", False),
    (True, "Driver does not support the required nvenc API version", False),
])
def test_nvenc_fallback(tmp_path, monkeypatch, cancelled, diagnostic, retries):
    log_path = tmp_path / "render.log"
    event = threading.Event()
    command = ["ffmpeg", "-c:v", "h264_nvenc", "-preset", "p4", "-cq", "22", "out.mp4"]

    def attempt(*args, **kwargs):
        if not kwargs.get("append_log"):
            log_path.write_text(diagnostic, encoding="utf-8")
            if cancelled:
                event.set()
            raise RuntimeError("encoder failed")

    runner = Mock(side_effect=attempt)
    monkeypatch.setattr(render_service, "_run_ffmpeg_once", runner)
    if retries:
        render_service.run_ffmpeg(command, 1, log_path, event, Mock(), Mock())
        fallback = runner.call_args.args[0]
        assert fallback == ["ffmpeg", "-c:v", "libx264", "-preset", "medium", "-crf", "20", "out.mp4"]
        assert "h264_nvenc" in command
        assert diagnostic in log_path.read_text(encoding="utf-8")
        assert runner.call_count == 2
    else:
        with pytest.raises(InterruptedError if cancelled else RuntimeError):
            render_service.run_ffmpeg(command, 1, log_path, event, Mock(), Mock())
        assert runner.call_count == 1
