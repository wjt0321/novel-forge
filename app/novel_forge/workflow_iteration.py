"""Iteration policies for bounded writer context and risk-aware workflow routing."""

from __future__ import annotations

import json
import re
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path, PurePath
from typing import Any, Iterable

from . import book_project

WRITER_CONTEXT_MODES = frozenset({"minimal", "full"})
WRITER_CONTEXT_BUDGETS = {"P0": 1500, "P1": 850, "P2": 450}
HOST_CAPABILITY_TIERS = frozenset(
    {"native-isolated", "managed-relay", "exploration"}
)
CHAPTER_RISK_LEVELS = frozenset(
    {
        "standard",
        "volume_start",
        "volume_end",
        "major_turn",
        "character_death",
        "core_reveal",
    }
)
HIGH_RISK_LEVELS = CHAPTER_RISK_LEVELS - {"standard"}

_CJK_RE = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]")


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _validate_slug(slug: str) -> str:
    value = str(slug or "").strip()
    pure = PurePath(value)
    if not value or pure.is_absolute() or len(pure.parts) != 1 or value in {".", ".."}:
        raise ValueError("slug 必须是单一安全路径段。")
    return value


def _count_cjk(text: str) -> int:
    return len(_CJK_RE.findall(text))


def _bounded(text: str, limit: int, *, tail: bool = False) -> str:
    """Return text with at most ``limit`` CJK characters."""
    if limit <= 0 or _count_cjk(text) <= limit:
        return text.strip()
    indices = [match.start() for match in _CJK_RE.finditer(text)]
    if tail:
        start = indices[-limit]
        return text[start:].strip()
    end = indices[limit - 1] + 1
    return text[:end].strip()


def ensure_volume_voice_bible(
    root: Path,
    slug: str,
    *,
    volume: int,
) -> Path:
    """Create the current volume's author-editable voice override if absent."""
    if volume < 1:
        raise ValueError("volume 必须大于等于 1。")
    slug = _validate_slug(slug)
    book_dir = Path(root).resolve() / "books" / slug
    if not book_dir.is_dir():
        raise ValueError(f"书籍不存在：{slug}")
    path = book_dir / "memory" / f"voice-bible-v{volume:02d}.md"
    if not path.exists():
        path.write_text(
            f"# Voice Bible Volume {volume:02d}\n\n"
            "> 卷级覆盖仅由作者或明确授权的控制面修改；未填写项继承书级 voice-bible。\n\n"
            "## 叙事距离\n- 继承书级；本卷覆盖：无。\n\n"
            "## 信息释放顺序\n- 先动作与可见后果，后解释；本卷覆盖：无。\n\n"
            "## 对白与沉默\n- 沉默必须改变权力、关系或下一步行动；本卷覆盖：无。\n\n"
            "## 场景选择与私人代价\n- 每个关键场景让人物作出选择并承担即时私人代价。\n\n"
            "## 作者认可范例\n- 尚未登记；最多保留 1--2 条摘要及其叙事功能，不复制句法骨架。\n\n"
            "## Writer 模型基线与切换记录\n- 基线：未登记。\n",
            encoding="utf-8",
        )
    return path


def _read_if_file(path: Path) -> str:
    return path.read_text(encoding="utf-8-sig") if path.is_file() else ""


def _heading_key(value: str) -> str:
    return re.sub(r"[\s#：:（）()]+", "", value).lower()


def _extract_markdown_sections(text: str, selectors: tuple[str, ...]) -> str:
    """Return selected level-two sections in source order."""
    wanted = tuple(_heading_key(item) for item in selectors)
    chunks: list[str] = []
    current: list[str] = []
    selected = False
    for line in text.splitlines():
        if line.startswith("## "):
            if selected and current:
                chunks.append("\n".join(current).strip())
            heading = line[3:].strip()
            key = _heading_key(heading)
            selected = any(
                key == item or key.startswith(item)
                for item in wanted
            )
            current = [line] if selected else []
        elif selected:
            current.append(line)
    if selected and current:
        chunks.append("\n".join(current).strip())
    return "\n\n".join(chunk for chunk in chunks if chunk)


def compile_writer_package(
    root: Path,
    slug: str,
    *,
    chapter: int,
    volume: int,
    handoff_path: Path,
    mode: str = "minimal",
) -> dict[str, Any]:
    """Compile a bounded P0/P1/P2 writer package or the legacy full handoff."""
    if chapter < 1:
        raise ValueError("chapter 必须大于等于 1。")
    if mode not in WRITER_CONTEXT_MODES:
        raise ValueError("writer context mode 必须是 minimal 或 full。")
    slug = _validate_slug(slug)
    root = Path(root).resolve()
    book_dir = root / "books" / slug
    handoff_path = Path(handoff_path).resolve()
    if not handoff_path.is_file():
        raise ValueError("writer handoff 不存在。")
    if mode == "full":
        text = "# Writer Context — Full Comparison\n\n" + _read_if_file(handoff_path)
        return {
            "schema": "novel-forge-writer-package/v1",
            "mode": "full",
            "chapter": chapter,
            "volume": volume,
            "tiers": {},
            "text": text.rstrip() + "\n",
        }

    scene = _read_if_file(book_dir / "planning" / f"scene-package-ch{chapter:02d}.md")
    previous = ""
    if chapter > 1:
        try:
            previous = _read_if_file(
                book_project.find_chapter_file(book_dir, chapter - 1)
            )
        except Exception:
            previous = ""
    previous_ending = _bounded(previous, 500, tail=True)
    story_obligations = _extract_markdown_sections(
        scene,
        (
            "0. 边界",
            "0a. 用户硬锚合同",
            "0b. 章际交接",
            "1. 场景压力",
            "3. Beat 因果链",
            "4. 信息账本",
            "场景契约",
            "硬锚点",
            "章末目标",
        ),
    )
    if not story_obligations:
        story_obligations = scene
    p0 = _bounded(
        "## 当前故事义务\n"
        + _bounded(story_obligations, 1000)
        + "\n\n## 上一章必要结尾\n"
        + (previous_ending or "不适用或尚无可靠上一章正文。"),
        WRITER_CONTEXT_BUDGETS["P0"],
    )

    human_pressure = _extract_markdown_sections(
        scene,
        (
            "1c. 决策问题",
            "2. 在场者状态",
            "6. 人物性呼吸段",
            "7. 场景余波",
        ),
    )
    memory_parts = []
    for name in ("characters.md", "canon.md", "worldbuilding.md"):
        value = _read_if_file(book_dir / "memory" / name)
        if value:
            memory_parts.append(value)
    direct_memory = _bounded("\n\n".join(memory_parts), 220)
    story = _read_if_file(book_dir / "planning" / "story-engine.md")
    promise_lines = [
        line for line in story.splitlines()
        if any(key in line for key in ("承诺", "promise", "伏笔"))
    ][:2]
    p1 = _bounded(
        "## 当前人物私欲、关系摩擦与感知偏差\n"
        + (_bounded(human_pressure, 560) or "- 未登记，按现场行动保守推断。")
        + "\n\n## 直接 Canon\n"
        + (direct_memory or "- 未登记。")
        + "\n\n## 最多两个未解承诺\n"
        + ("\n".join(promise_lines) or "- 未登记。"),
        WRITER_CONTEXT_BUDGETS["P1"],
    )

    volume_voice = ensure_volume_voice_bible(root, slug, volume=volume)
    voice_source = (
        _read_if_file(book_dir / "memory" / "voice-bible.md")
        + "\n\n"
        + _read_if_file(volume_voice)
    )
    voice_fingerprint = _extract_markdown_sections(
        voice_source,
        (
            "叙事距离",
            "信息释放顺序",
            "对白与沉默",
            "场景选择与私人代价",
            "作者认可范例",
        ),
    )
    p2 = _bounded(
        "## 声音指纹\n"
        + (voice_fingerprint or "- 贴近当前视角；让动作先于解释。"),
        WRITER_CONTEXT_BUDGETS["P2"],
    )

    text = (
        "# Writer Context — Minimal P0/P1/P2\n\n"
        "Writer 只执行作品任务；不得猜测控制面、模型、会话、哈希或发布资格。\n\n"
        "# P0 必须\n\n" + p0 + "\n\n"
        "# P1 重要\n\n" + p1 + "\n\n"
        "# P2 可裁剪参考\n\n" + p2 + "\n"
    )
    return {
        "schema": "novel-forge-writer-package/v1",
        "mode": "minimal",
        "chapter": chapter,
        "volume": volume,
        "tiers": {
            "P0": {"cjk": _count_cjk(p0), "budget_cjk": WRITER_CONTEXT_BUDGETS["P0"]},
            "P1": {"cjk": _count_cjk(p1), "budget_cjk": WRITER_CONTEXT_BUDGETS["P1"]},
            "P2": {"cjk": _count_cjk(p2), "budget_cjk": WRITER_CONTEXT_BUDGETS["P2"]},
        },
        "text": text,
    }


def _model_policy_path(root: Path, slug: str) -> Path:
    slug = _validate_slug(slug)
    path = Path(root).resolve() / ".local-guardian" / slug / "writer-model-policy.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _load_model_policy(root: Path, slug: str) -> dict[str, Any]:
    path = _model_policy_path(root, slug)
    if not path.is_file():
        return {"schema": "novel-forge-writer-model-policy/v1", "volumes": {}}
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else {"schema": "novel-forge-writer-model-policy/v1", "volumes": {}}


def _save_model_policy(root: Path, slug: str, payload: dict[str, Any]) -> None:
    path = _model_policy_path(root, slug)
    temp = path.with_suffix(".tmp")
    temp.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temp.replace(path)


def evaluate_writer_model(
    root: Path,
    slug: str,
    *,
    volume: int,
    model: str,
) -> dict[str, Any]:
    """Enforce a stable primary Writer model within one volume."""
    name = str(model or "").strip()
    if not name or name == "unknown":
        return {"status": "unknown", "model": None, "volume": volume}
    policy = _load_model_policy(root, slug)
    volumes = policy.setdefault("volumes", {})
    key = str(volume)
    record = volumes.get(key)
    if not isinstance(record, dict) or not record.get("primary_model"):
        volumes[key] = {
            "primary_model": name,
            "approved_models": [name],
            "updated_at": _now(),
        }
        _save_model_policy(root, slug, policy)
        return {"status": "baseline_recorded", "model": name, "volume": volume}
    approved = {str(item) for item in record.get("approved_models", [])}
    if name == record.get("primary_model") or name in approved:
        return {"status": "matched", "model": name, "volume": volume}
    return {
        "status": "calibration_required",
        "model": name,
        "primary_model": record.get("primary_model"),
        "volume": volume,
    }


def approve_writer_model_switch(
    root: Path,
    slug: str,
    *,
    volume: int,
    model: str,
    decision_reference: str,
) -> dict[str, Any]:
    """Record an author's informal sample calibration and switch approval."""
    name = str(model or "").strip()
    reference = str(decision_reference or "").strip()
    if not name or name == "unknown" or not reference:
        raise ValueError("模型与作者校准依据均不能为空。")
    policy = _load_model_policy(root, slug)
    volumes = policy.setdefault("volumes", {})
    record = volumes.setdefault(str(volume), {"approved_models": []})
    approved = [str(item) for item in record.get("approved_models", [])]
    if name not in approved:
        approved.append(name)
    record.update(
        {
            "primary_model": name,
            "approved_models": approved,
            "decision_reference": reference,
            "updated_at": _now(),
        }
    )
    _save_model_policy(root, slug, policy)
    voice_path = ensure_volume_voice_bible(root, slug, volume=volume)
    with voice_path.open("a", encoding="utf-8") as handle:
        handle.write(
            f"- {_now()}：切换为 `{name}`；作者校准依据：{reference}。\n"
        )
    return {"status": "approved", "model": name, "volume": volume}


def _open_local_must(findings: Iterable[Any]) -> list[Any]:
    return [
        item for item in findings
        if item.severity.upper() == "MUST" and item.status.lower() == "open"
    ]


def plan_local_patch(
    body: str,
    findings: Iterable[Any],
) -> list[dict[str, str]] | None:
    """Return bounded paragraph targets only when every open MUST is local."""
    must = _open_local_must(findings)
    if not must or any(item.scope != "local" for item in must):
        return None
    paragraphs = [part.strip() for part in re.split(r"\n\s*\n", body) if part.strip()]
    plan: list[dict[str, str]] = []
    used: set[str] = set()
    for finding in must:
        evidence = finding.evidence.strip()
        if not evidence or body.count(evidence) != 1:
            return None
        matches = [index for index, paragraph in enumerate(paragraphs) if evidence in paragraph]
        if len(matches) != 1:
            return None
        index = matches[0]
        target = paragraphs[index]
        if body.count(target) != 1:
            return None
        if target in used:
            continue
        used.add(target)
        plan.append(
            {
                "target": target,
                "before": paragraphs[index - 1] if index else "",
                "after": paragraphs[index + 1] if index + 1 < len(paragraphs) else "",
                "location": finding.location,
                "evidence": evidence,
                "revision_intent": finding.revision_intent,
                "reader_effect": finding.reader_effect,
            }
        )
    return plan


def apply_local_replacements(
    body: str,
    replacements: Iterable[dict[str, str]],
) -> str:
    """Apply replacement fragments only when every target is exact and unique."""
    updated = body
    seen: set[str] = set()
    for item in replacements:
        target = str(item.get("target") or "")
        replacement = str(item.get("replacement") or "").strip()
        if not target or not replacement or target in seen or updated.count(target) != 1:
            raise ValueError("局部 Patch 无法精确定位唯一原文片段。")
        seen.add(target)
        updated = updated.replace(target, replacement, 1)
    return updated


def require_high_risk_confirmation(chapter_risk: str) -> bool:
    if chapter_risk not in CHAPTER_RISK_LEVELS:
        raise ValueError("未知章节风险等级。")
    return chapter_risk in HIGH_RISK_LEVELS


def evaluate_budget_breaker(
    known_total_tokens: int | None,
    *,
    soft_limit: int | None,
    hard_limit: int | None,
) -> str:
    if known_total_tokens is None:
        return "unknown"
    if hard_limit is not None and known_total_tokens >= hard_limit:
        return "hard"
    if soft_limit is not None and known_total_tokens >= soft_limit:
        return "soft"
    return "within"


def display_workflow_state(phase: str, *, patch_round: int = 0) -> str:
    if phase == "complete":
        return "已归档"
    if phase == "decision_required":
        return "待作者决定"
    if phase == "awaiting_writer" and patch_round:
        return "待局部修订"
    if phase in {"awaiting_writer", "writing", "patching"}:
        return "写作中"
    if phase in {
        "awaiting_blind_reader",
        "awaiting_chapter_editor",
        "awaiting_double_review",
    }:
        return "双审中"
    if phase in {"hard_check", "promoting"}:
        return "硬检查"
    return "待写"
