from __future__ import annotations

import json
import math
import re

from app.schemas.api import GeneratedScript, ScriptGenerate, ScriptGenerateOut
from app.services.ai_router import AIResult, ai_router
from app.services.skill_loader import load_skill


FENCED_JSON = re.compile(r"```(?:json)?\s*(.*?)\s*```", re.DOTALL | re.IGNORECASE)
EMOJI = re.compile("[\U0001F300-\U0001FAFF\u2600-\u27BF]")


def _prompt(payload: ScriptGenerate, instructions: str, constraints: dict, repair: str | None = None) -> str:
    extra = f"\nKết quả trước không hợp lệ: {repair}. Hãy sửa và trả lại toàn bộ JSON.\n" if repair else ""
    words_per_second = float(constraints.get("words_per_second", 4.0))
    min_words = math.ceil(payload.duration_min * words_per_second)
    max_words = math.ceil(payload.duration_max * words_per_second)
    return f"""Bạn là người viết kịch bản video ngắn bằng tiếng Việt.
Chỉ dùng thông tin sản phẩm đã cung cấp; không bịa giá, ưu đãi, chất liệu hoặc tính năng.

THÔNG TIN SẢN PHẨM:
{payload.product_info}

SKILL:
{instructions}

CONSTRAINTS: {json.dumps(constraints, ensure_ascii=False)}
Yêu cầu tạo đúng {payload.count} kịch bản, mục tiêu {payload.duration_min}-{payload.duration_max} giây.
Mỗi kịch bản phải có từ {min_words} đến {max_words} từ tiếng Việt (đếm theo các cụm cách nhau bằng dấu cách). Đây là yêu cầu bắt buộc để đủ thời lượng đọc.
Mỗi kịch bản chỉ chứa lời đọc TTS, một đoạn văn, không tiêu đề hay metadata.
Trả về duy nhất JSON dạng: {{"scripts":[{{"index":1,"text":"..."}}]}}.
{extra}"""


def _decode(raw: str) -> dict:
    match = FENCED_JSON.search(raw)
    candidate = match.group(1) if match else raw.strip()
    try:
        value = json.loads(candidate)
    except json.JSONDecodeError as exc:
        raise ValueError("AI không trả về JSON hợp lệ") from exc
    if not isinstance(value, dict):
        raise ValueError("JSON AI phải là object")
    return value


def _validate(value: dict, payload: ScriptGenerate, constraints: dict) -> list[GeneratedScript]:
    rows = value.get("scripts")
    if not isinstance(rows, list) or len(rows) != payload.count:
        raise ValueError(f"AI phải trả đúng {payload.count} kịch bản")
    result: list[GeneratedScript] = []
    seen: set[str] = set()
    seen_hooks: set[str] = set()
    for index, row in enumerate(rows, 1):
        if not isinstance(row, dict) or not isinstance(row.get("text"), str):
            raise ValueError(f"Kịch bản {index} thiếu text")
        text = " ".join(row["text"].strip().split())
        if not text:
            raise ValueError(f"Kịch bản {index} đang trống")
        warnings = []
        if text.casefold() in seen:
            warnings.append("Nội dung trùng hoàn toàn với một kịch bản khác")
        seen.add(text.casefold())
        if constraints.get("one_paragraph") and ("\n" in row["text"] or "\r" in row["text"]):
            warnings.append("Nội dung nên được viết thành một đoạn")
        if not constraints.get("allow_hashtags", True) and re.search(r"(?<!\w)#\w+", text):
            warnings.append("Nội dung có hashtag không phù hợp với lời đọc TTS")
        if not constraints.get("allow_emoji", True) and EMOJI.search(text):
            warnings.append("Nội dung có emoji không phù hợp với lời đọc TTS")
        hook = re.split(r"[.!?…]", text, maxsplit=1)[0].strip()
        hook_words = hook.split()
        hook_limit = int(constraints.get("hook_max_words", 0) or 0)
        if hook_limit and len(hook_words) > hook_limit:
            warnings.append(f"Hook dài {len(hook_words)} từ; mục tiêu tối đa {hook_limit} từ cho khoảng 3 giây đầu")
        if constraints.get("unique_hooks"):
            # So sánh câu hook đã chuẩn hóa và phần mở đầu để bắt cả trường hợp
            # model chỉ thay một vài từ ở cuối cùng một công thức mở bài.
            hook_key = re.sub(r"[^a-z0-9à-ỹ]+", " ", hook.casefold()).strip()
            opening_key = " ".join(hook_key.split()[:6])
            if not hook_key or hook_key in seen_hooks or opening_key in seen_hooks:
                warnings.append("Hook có cách mở đầu giống một kịch bản khác")
            seen_hooks.update({hook_key, opening_key})
        word_count = len(text.split())
        words_per_second = float(constraints.get("words_per_second", 4.0))
        min_words = math.ceil(payload.duration_min * words_per_second)
        max_words = math.ceil(payload.duration_max * words_per_second)
        estimate = round(word_count / words_per_second, 1)
        if estimate < payload.duration_min or estimate > payload.duration_max:
            warnings.append(f"Có {word_count} từ, ước tính {estimate} giây; mục tiêu tham khảo là {payload.duration_min}-{payload.duration_max} giây ({min_words}-{max_words} từ)")
        result.append(GeneratedScript(index=index, text=text, estimated_duration_seconds=estimate, warnings=warnings))
    return result


def generate_scripts(payload: ScriptGenerate) -> ScriptGenerateOut:
    if payload.duration_min > payload.duration_max:
        raise ValueError("Thời lượng tối thiểu không được lớn hơn tối đa")
    skill = load_skill(payload.skill_id)
    first: AIResult = ai_router.generate(_prompt(payload, skill.instructions, skill.constraints), payload.provider)
    try:
        scripts = _validate(_decode(first.text), payload, skill.constraints)
        used = first
    except ValueError as exc:
        used = ai_router.generate(_prompt(payload, skill.instructions, skill.constraints, str(exc)), first.provider)
        scripts = _validate(_decode(used.text), payload, skill.constraints)
    return ScriptGenerateOut(provider_used=used.provider, model_used=used.model, scripts=scripts)
