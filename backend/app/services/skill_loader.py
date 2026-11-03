from __future__ import annotations

import json
import re
import shutil
import uuid
from dataclasses import dataclass

from app.core.config import settings


SKILL_ID = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")
MAX_SKILL_CONTENT_BYTES = 256_000
USER_PREFIX = "user-"


@dataclass(frozen=True)
class ScriptSkill:
    id: str
    name: str
    description: str
    instructions: str
    constraints: dict
    read_only: bool


def _folder(skill_id: str):
    if not SKILL_ID.fullmatch(skill_id):
        raise ValueError("Skill không hợp lệ")
    root = settings.skills_dir.resolve()
    folder = (root / skill_id).resolve()
    if folder.parent != root:
        raise ValueError("Skill không hợp lệ")
    return folder


def load_skill(skill_id: str) -> ScriptSkill:
    if not SKILL_ID.fullmatch(skill_id):
        raise ValueError("Skill không hợp lệ")
    folder = _folder(skill_id)
    instruction_file = folder / "skill.md"
    if not instruction_file.is_file():
        raise ValueError("Không tìm thấy Skill")
    try:
        instructions = instruction_file.read_text(encoding="utf-8").strip()
    except UnicodeDecodeError as exc:
        raise ValueError("Skill phải dùng mã hóa UTF-8") from exc
    if not instructions:
        raise ValueError(f"skill.md của Skill {skill_id} đang trống")
    title = next((line.lstrip("# ").strip() for line in instructions.splitlines() if line.startswith("#")), skill_id)
    description = next((line.strip() for line in instructions.splitlines() if line.strip() and not line.startswith("#")), "")
    constraints = {}
    constraint_file = folder / "constraints.json"
    if constraint_file.is_file():
        try:
            parsed = json.loads(constraint_file.read_text(encoding="utf-8"))
            if isinstance(parsed, dict):
                constraints = parsed
        except (UnicodeDecodeError, json.JSONDecodeError):
            pass
    return ScriptSkill(skill_id, title[:120], description[:240], instructions, constraints, not skill_id.startswith(USER_PREFIX))


def skill_dict(skill: ScriptSkill, include_content: bool = False) -> dict:
    result = {"id": skill.id, "name": skill.name, "description": skill.description,
              "read_only": skill.read_only, "constraints": skill.constraints}
    if include_content:
        result["content"] = skill.instructions
    return result


def list_skills() -> list[dict]:
    if not settings.skills_dir.exists():
        return []
    result = []
    for folder in sorted(settings.skills_dir.iterdir()):
        if folder.is_dir() and SKILL_ID.fullmatch(folder.name):
            try:
                skill = load_skill(folder.name)
            except ValueError:
                continue
            result.append(skill_dict(skill))
    return result


def _validate_markdown(content: bytes) -> str:
    if not content or len(content) > MAX_SKILL_CONTENT_BYTES:
        raise ValueError("File Skill phải có nội dung và không lớn hơn 256 KB")
    try:
        instructions = content.decode("utf-8").strip()
    except UnicodeDecodeError as exc:
        raise ValueError("File Skill phải dùng mã hóa UTF-8") from exc
    if not instructions:
        raise ValueError("Nội dung Skill không được để trống")
    return instructions


def install_skill(content: bytes, _filename: str = "") -> dict:
    instructions = _validate_markdown(content)
    skill_id = USER_PREFIX + uuid.uuid4().hex[:12]
    root = settings.skills_dir.resolve()
    root.mkdir(parents=True, exist_ok=True)
    folder = root / skill_id
    if folder.exists():
        raise FileExistsError(f"Skill '{skill_id}' đã tồn tại")
    folder.mkdir()
    try:
        (folder / "skill.md").write_text(instructions + "\n", encoding="utf-8")
        skill = load_skill(skill_id)
    except Exception:
        shutil.rmtree(folder, ignore_errors=True)
        raise
    return skill_dict(skill, include_content=True)


def update_skill(skill_id: str, content: str, name: str | None = None) -> dict:
    skill = load_skill(skill_id)
    if skill.read_only:
        raise PermissionError("Skill hệ thống chỉ được phép xem")
    text = _validate_markdown(content.encode("utf-8"))
    if name and name.strip():
        lines = text.splitlines()
        title = f"# {name.strip()[:120]}"
        if lines and lines[0].lstrip().startswith("#"):
            lines[0] = title
        else:
            lines.insert(0, title)
        text = "\n".join(lines)
    (_folder(skill_id) / "skill.md").write_text(text + "\n", encoding="utf-8")
    return skill_dict(load_skill(skill_id), include_content=True)


def delete_skill(skill_id: str) -> None:
    skill = load_skill(skill_id)
    if skill.read_only:
        raise PermissionError("Skill hệ thống không thể xóa")
    shutil.rmtree(_folder(skill_id))


def skill_template_markdown() -> bytes:
    template = settings.skills_dir.parent / "docs" / "SKILL_MAU_KICH_BAN_LINH_HOAT.md"
    if template.is_file():
        return template.read_bytes()
    return """# Skill mẫu bán hàng

Mô tả rõ giọng văn và cách triển khai kịch bản tại đây.

- Mở đầu bằng một câu thu hút.
- Chỉ sử dụng thông tin sản phẩm được cung cấp.
- Kết thúc bằng lời kêu gọi hành động ngắn gọn.
- Không ấn định số lượng hoặc thời lượng nếu người dùng không yêu cầu.
""".encode("utf-8")
