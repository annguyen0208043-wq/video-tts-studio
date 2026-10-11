from __future__ import annotations

import json
import re
from dataclasses import dataclass

from app.core.config import settings


SKILL_ID = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")


@dataclass(frozen=True)
class ScriptSkill:
    id: str
    name: str
    instructions: str
    constraints: dict


def load_skill(skill_id: str) -> ScriptSkill:
    if not SKILL_ID.fullmatch(skill_id):
        raise ValueError("Skill không hợp lệ")
    root = settings.skills_dir.resolve()
    folder = (root / skill_id).resolve()
    if folder.parent != root:
        raise ValueError("Skill không hợp lệ")
    instruction_file = folder / "skill.md"
    constraint_file = folder / "constraints.json"
    if not instruction_file.is_file() or not constraint_file.is_file():
        raise ValueError("Không tìm thấy Skill")
    try:
        constraints = json.loads(constraint_file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"constraints.json của Skill {skill_id} không hợp lệ") from exc
    instructions = instruction_file.read_text(encoding="utf-8").strip()
    if not instructions:
        raise ValueError(f"skill.md của Skill {skill_id} đang trống")
    title = next((line.lstrip("# ").strip() for line in instructions.splitlines() if line.startswith("#")), skill_id)
    return ScriptSkill(skill_id, title, instructions, constraints)


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
            result.append({"id": skill.id, "name": skill.name, "constraints": skill.constraints})
    return result
