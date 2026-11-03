"""Exit 0 for a free port, 10 for the running app, 20 for another listener."""
import json
import socket
from urllib.request import ProxyHandler, build_opener

with socket.socket() as listener:
    try:
        listener.bind(("127.0.0.1", 8765))
    except OSError:
        pass
    else:
        raise SystemExit(0)

try:
    opener = build_opener(ProxyHandler({}))
    with opener.open("http://127.0.0.1:8765/api/health", timeout=3) as response:
        health = json.load(response)
    if health.get("status") == "ok" and health.get("name") == "Video TTS Studio":
        print("Video TTS Studio is already running: http://127.0.0.1:8765")
        print("Open that address in your browser. No second server was started.")
        raise SystemExit(10)
except (OSError, ValueError, AttributeError):
    pass

print("[ERROR] Port 8765 is occupied, but Video TTS Studio is not responding.")
print("Stop the process using this port, or wait for the existing server to start.")
raise SystemExit(20)
