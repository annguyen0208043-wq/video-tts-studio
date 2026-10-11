from __future__ import annotations

import json
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass

from app.core.config import settings


class AIProviderError(RuntimeError):
    def __init__(self, message: str, retryable: bool = False):
        super().__init__(message)
        self.retryable = retryable


@dataclass(frozen=True)
class AIResult:
    provider: str
    model: str
    text: str


class AIRouter:
    order = ("gemini", "groq", "openrouter")

    def __init__(self) -> None:
        self._cooldowns: dict[str, float] = {}
        self._lock = threading.Lock()

    def providers(self) -> list[dict]:
        return [
            {
                "id": name,
                "name": {"gemini": "Gemini", "groq": "Groq", "openrouter": "OpenRouter"}[name],
                "configured": self._configured(name),
                "model": self._model(name) or None,
            }
            for name in self.order
        ]

    def generate(self, prompt: str, provider: str = "auto") -> AIResult:
        selected = (provider or settings.ai_default_provider).lower()
        if selected != "auto" and selected not in self.order:
            raise ValueError("Nhà cung cấp AI không hợp lệ")
        candidates = list(self.order) if selected == "auto" else [selected]
        errors: list[str] = []
        for name in candidates:
            if not self._configured(name):
                if name == "openrouter" and self._key(name) and self._model(name):
                    errors.append("openrouter: chỉ cho phép model có hậu tố :free")
                    continue
                errors.append(f"{name}: chưa cấu hình API key/model")
                continue
            with self._lock:
                cooldown_until = self._cooldowns.get(name, 0)
            if selected == "auto" and cooldown_until > time.monotonic():
                errors.append(f"{name}: đang tạm nghỉ sau lỗi giới hạn")
                continue
            attempts = max(1, settings.ai_max_retries + 1)
            for attempt in range(attempts):
                try:
                    return AIResult(name, self._model(name), self._request(name, prompt))
                except AIProviderError as exc:
                    errors.append(f"{name}: {exc}")
                    if exc.retryable:
                        with self._lock:
                            self._cooldowns[name] = time.monotonic() + settings.ai_cooldown_seconds
                    if not exc.retryable or attempt + 1 >= attempts:
                        break
                    time.sleep(min(1.0, 0.25 * (attempt + 1)))
            if selected != "auto":
                break
        detail = "; ".join(errors) or "không có provider khả dụng"
        raise AIProviderError(f"Không thể tạo kịch bản. {detail}")

    def _key(self, name: str) -> str:
        return str(getattr(settings, f"{name}_api_key"))

    def _model(self, name: str) -> str:
        return str(getattr(settings, f"{name}_model"))

    def _configured(self, name: str) -> bool:
        key, model = self._key(name), self._model(name)
        return bool(key and model and (name != "openrouter" or model.endswith(":free")))

    def _request(self, name: str, prompt: str) -> str:
        if name == "gemini":
            model = urllib.parse.quote(self._model(name), safe="")
            key = urllib.parse.quote(self._key(name), safe="")
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={key}"
            body = {"contents": [{"parts": [{"text": prompt}]}], "generationConfig": {"responseMimeType": "application/json", "temperature": 0.9}}
        else:
            url = "https://api.groq.com/openai/v1/chat/completions" if name == "groq" else "https://openrouter.ai/api/v1/chat/completions"
            body = {"model": self._model(name), "messages": [{"role": "user", "content": prompt}], "temperature": 0.9, "response_format": {"type": "json_object"}}
        headers = {"Content-Type": "application/json", "User-Agent": "Video-TTS-Studio/0.1"}
        if name != "gemini":
            headers["Authorization"] = f"Bearer {self._key(name)}"
        request = urllib.request.Request(url, data=json.dumps(body).encode("utf-8"), headers=headers, method="POST")
        try:
            with urllib.request.urlopen(request, timeout=settings.ai_timeout_seconds) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            retryable = exc.code == 429 or 500 <= exc.code < 600
            raise AIProviderError(f"HTTP {exc.code}", retryable=retryable) from exc
        except (urllib.error.URLError, TimeoutError) as exc:
            raise AIProviderError("timeout hoặc lỗi kết nối", retryable=True) from exc
        except (json.JSONDecodeError, KeyError, IndexError, TypeError) as exc:
            raise AIProviderError("response không hợp lệ") from exc
        try:
            if name == "gemini":
                return payload["candidates"][0]["content"]["parts"][0]["text"]
            return payload["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise AIProviderError("response thiếu nội dung") from exc


ai_router = AIRouter()
