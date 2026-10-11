import json

import pytest

from app.schemas.api import ScriptGenerate
from app.services.ai_router import AIProviderError, AIResult, AIRouter
from app.services.script_service import _decode, _validate, generate_scripts
from app.services.skill_loader import load_skill


def payload(count: int = 5) -> ScriptGenerate:
    return ScriptGenerate(
        product_info="Túi vải đeo chéo, đựng được sách và laptop",
        skill_id="tiktok-ban-hang",
        provider="auto",
        count=count,
        duration_min=18,
        duration_max=20,
    )


def test_count_accepts_large_batches():
    assert payload(50).count == 50


def test_router_reports_missing_configuration(monkeypatch):
    router = AIRouter()
    monkeypatch.setattr(router, "_key", lambda _name: "")
    monkeypatch.setattr(router, "_model", lambda _name: "")
    with pytest.raises(AIProviderError, match="chưa cấu hình"):
        router.generate("hello")


def test_auto_falls_back_after_rate_limit(monkeypatch):
    router = AIRouter()
    monkeypatch.setattr(router, "_key", lambda _name: "test-key")
    monkeypatch.setattr(router, "_model", lambda name: "openrouter-model:free" if name == "openrouter" else f"{name}-model")

    def fake_request(name: str, _prompt: str) -> str:
        if name == "gemini":
            raise AIProviderError("HTTP 429", retryable=True)
        return '{"scripts": []}'

    monkeypatch.setattr(router, "_request", fake_request)
    result = router.generate("hello", "auto")
    assert result.provider == "groq"


def test_invalid_ai_json_is_rejected():
    with pytest.raises(ValueError, match="JSON"):
        _decode("đây không phải JSON")


def test_invalid_skill_is_rejected():
    with pytest.raises(ValueError, match="Skill"):
        load_skill("../secret")


def test_crossbody_bag_skill_is_available():
    skill = load_skill("tui-deo-cheo-vui")
    assert skill.constraints["unique_hooks"] is True
    assert skill.constraints["hook_max_words"] == 12


def test_long_hook_is_a_warning_instead_of_rejecting_batch():
    request = payload(1)
    request.skill_id = "tui-deo-cheo-vui"
    hook = "Bạn có từng mang theo cả thế giới chỉ trong một chiếc túi nhỏ xinh chưa?"
    text = hook + " " + " ".join(["túi"] * (75 - len(hook.split())))
    rows = _validate({"scripts": [{"index": 1, "text": text}]}, request, load_skill(request.skill_id).constraints)
    assert "Hook dài" in rows[0].warnings[0]


def test_crossbody_bag_skill_warns_when_script_is_short():
    request = payload(1)
    request.skill_id = "tui-deo-cheo-vui"
    rows = _validate(
        {"scripts": [{"index": 1, "text": "Túi gì mà vui thế? Túi vải rộng rãi, tiện lợi để mang theo mỗi ngày."}]},
        request,
        load_skill(request.skill_id).constraints,
    )
    assert "mục tiêu tham khảo" in rows[0].warnings[-1]


def test_generate_five_scripts(monkeypatch):
    rows = [
        {
            "index": index,
            "text": f"Bạn đang cần một chiếc túi tiện dụng cho ngày bận rộn? Mẫu túi vải đeo chéo này đựng được sách và laptop, giúp mang đồ gọn gàng hơn mỗi ngày. Đây là lựa chọn đáng cân nhắc cho việc học và đi làm, hãy xem thêm thông tin để chọn chiếc túi phù hợp số {index}.",
        }
        for index in range(1, 6)
    ]
    response = json.dumps({"scripts": rows}, ensure_ascii=False)
    monkeypatch.setattr(
        "app.services.script_service.ai_router.generate",
        lambda _prompt, _provider: AIResult("gemini", "configured-model", response),
    )
    result = generate_scripts(payload())
    assert result.provider_used == "gemini"
    assert result.model_used == "configured-model"
    assert len(result.scripts) == 5
    assert all(item.text for item in result.scripts)
