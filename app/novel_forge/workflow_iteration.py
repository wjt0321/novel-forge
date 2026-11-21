"""Iteration policies for bounded writer context and risk-aware workflow routing."""

from __future__ import annotations

import difflib
import json
import re
from dataclasses import asdict, replace
from datetime import UTC, datetime
from pathlib import Path, PurePath
from typing import Any, Iterable

from . import book_project
from .book_memory import canon_context_digest
from .planning_spec import CJK_CHAR_RE
from .style_corpus import render_writer_style_brief

WRITER_CONTEXT_MODES = frozenset({"minimal", "full"})
# Bounded self-service revision budget for ordinary literary MUSTs: Python
# re-issues the consolidated revision this many times before it interrupts the
# author. Gate and high-risk failures never take this path. Single tunable for
# the "no interruption" guarantee; raise it only together with a budget breaker.
MAX_AUTO_LITERARY_REVISION_ROUNDS = 1
# docs/51 S2: only deterministic hard-issue categories may drive an
# automatic revision. Reviewers tag every continuity MUST with one
# category; wording and preference findings are SUGGEST, never MUST.
DETERMINISTIC_MUST_CATEGORIES = frozenset(
    {"timeline", "object", "knowledge", "hard_anchor", "hook"}
)
NON_DETERMINISTIC_CATEGORY = "other"
MUST_CATEGORY_ALIASES = {
    "timeline": "timeline", "时间线": "timeline", "时间": "timeline",
    "object": "object", "物件": "object", "物件归属": "object",
    "位置": "object",
    "knowledge": "knowledge", "知情": "knowledge",
    "人物知情": "knowledge",
    "hard_anchor": "hard_anchor", "硬锚": "hard_anchor",
    "硬锚漂移": "hard_anchor",
    "hook": "hook", "钩子": "hook", "章末钩子": "hook",
    "other": "other", "措辞": "other", "口径": "other",
    "风格": "other", "指代": "other", "不整齐": "other",
    "留白": "other", "建议": "other",
}
# docs/51 S5: the same anchor recurring twice stops automatic revision
# and hands the draft to the author; author authorizations are capped.
MAX_MUST_RECURRENCE_BEFORE_BREAKER = 2
MAX_AUTHOR_REVISION_AUTHORIZATIONS = 1
# P2 carries voice fingerprints plus the style reference set; it was 450 while
# the positive-target slot was an empty placeholder.
WRITER_CONTEXT_BUDGETS = {"P0": 1500, "P1": 850, "P2": 700}
# Writer-facing card. Tables stay in the control plane; this is the only
# craft instruction the draft is allowed to see up front.
_PROSE_CARD = (
    "## 只写这一章\n"
    "规划表已经由程序写好。不要打开、补写或修改任何表。"
    "下面是本章要发生的事，不是要在正文里逐条证明的清单。\n"
    "主题留在最后一个动作或物件上。留一件不是主角推出来的事。"
    "情绪写他做了什么，或直接说出感受；身体感觉最多一处。"
    "结尾停在没办完的后果上，不要写成想通了、和解了。\n"
)
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

_CJK_RE = CJK_CHAR_RE  # shared single-source CJK metric (planning_spec)


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
            "## 作者认可范例\n- 尚未登记；最多保留 1 至 2 条摘要及其叙事功能，不复制句法骨架。\n\n"
            "## Writer 模型基线与切换记录\n- 基线：未登记。\n",
            encoding="utf-8",
        )
    return path


def _read_if_file(path: Path) -> str:
    return path.read_text(encoding="utf-8-sig") if path.is_file() else ""


def _heading_key(value: str) -> str:
    return re.sub(r"[\s#：:（）()]+", "", value).lower()


def extract_markdown_sections(text: str, selectors: tuple[str, ...]) -> str:
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


_PREVIOUS_CHAPTER_LEDGER_PREFIXES = (
    "- 上一章正文路径",
    "- 上一章正文 SHA-256",
    "- 上一章正文SHA-256",
    "- 本章开头原文",
    "- 上一章结束时间",
    "- 本章开始时间",
    "- 上一章结束地点",
    "- 本章开始地点",
    "- 上一章结束动作",
    "- 本章开始动作",
    "- 转场类型",
    "- 上一章末明确决定",
    "- 本章是否推翻",
    "- 若推翻",
)


def _strip_previous_chapter_ledger(text: str) -> str:
    """Drop previous-chapter path/SHA ledger lines; writers need only the quote."""
    return "\n".join(
        line
        for line in text.splitlines()
        if not line.strip().startswith(_PREVIOUS_CHAPTER_LEDGER_PREFIXES)
    )


_ADOPTED_GENE_HEADING = "## 本书采纳的风格基因"
_EXEMPLAR_HEADING = "## 作者认可范例"
_EXEMPLAR_PLACEHOLDER_TOKENS = ("尚未登记", "TODO", "__________")


def _section_body(source: str, heading: str) -> str:
    """Return one level-2 markdown section body without its heading."""
    lines = str(source or "").splitlines()
    collected: list[str] = []
    inside = False
    for line in lines:
        if line.strip().startswith(heading):
            inside = True
            continue
        if inside and line.startswith("## "):
            break
        if inside:
            collected.append(line)
    return "\n".join(collected)


def _adopted_style_genes(voice_source: str) -> list[str]:
    """Technique labels the author checked in the voice bible."""
    body = _section_body(voice_source, _ADOPTED_GENE_HEADING)
    adopted: list[str] = []
    for line in body.splitlines():
        match = re.match(r"^\s*-\s*\[[xX]\]\s*([^：:]+)", line)
        if match:
            adopted.append(match.group(1).strip())
    return adopted


def _has_registered_exemplar(voice_source: str) -> bool:
    body = _section_body(voice_source, _EXEMPLAR_HEADING)
    content = " ".join(
        line.strip()
        for line in body.splitlines()
        if line.strip() and not line.strip().startswith(">")
    )
    if len(content) < 12:
        return False
    return not any(token in content for token in _EXEMPLAR_PLACEHOLDER_TOKENS)


def _without_markdown_tables(text: str) -> str:
    """Drop Markdown tables so a writer never treats a ledger as an outline."""
    kept: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("|"):
            continue
        if (
            stripped
            and set(stripped) <= set("-:| ")
            and "-" in stripped
            and "|" in stripped
        ):
            continue
        kept.append(line)
    return "\n".join(kept).strip()


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
    story_obligations = extract_markdown_sections(
        scene,
        (
            "0. 边界",
            "0a. 用户硬锚合同",
            "0b. 章际交接",
            "1. 场景压力",
            "场景契约",
            "硬锚点",
            "章末目标",
        ),
    )
    if not story_obligations:
        story_obligations = scene
    story_obligations = _without_markdown_tables(
        _strip_previous_chapter_ledger(story_obligations)
    )
    p0 = _bounded(
        _PROSE_CARD
        + "\n## 当前故事义务\n"
        + _bounded(story_obligations, 1000)
        + "\n\n## 上一章必要结尾\n"
        + (previous_ending or "不适用或尚无可靠上一章正文。"),
        WRITER_CONTEXT_BUDGETS["P0"],
    )

    human_pressure = extract_markdown_sections(
        scene,
        (
            "6. 人物性呼吸段",
            "7. 场景余波",
        ),
    )
    memory_parts = [
        canon_context_digest(
            root,
            slug,
            chapter,
            max_chars=4_000,
            sections=("P0 硬事实", "P1 活跃叙事"),
        ),
        _read_if_file(book_dir / "memory" / "worldbuilding.md"),
    ]
    direct_memory = _bounded(
        "\n\n".join(part for part in memory_parts if part), 220
    )
    story = _read_if_file(book_dir / "planning" / "story-engine.md")
    promise_lines = [
        line for line in story.splitlines()
        if any(key in line for key in ("承诺", "promise", "伏笔"))
    ][:2]
    p1 = _bounded(
        "## 当前人物私欲、关系摩擦与感知偏差\n"
        + (
            _bounded(_without_markdown_tables(human_pressure), 560)
            or "- 未登记，按现场行动保守推断。"
        )
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
    voice_fingerprint = extract_markdown_sections(
        voice_source,
        (
            "叙事距离",
            "信息释放顺序",
            "对白与沉默",
            "场景选择与私人代价",
            "作者认可范例",
        ),
    )
    adopted_genes = _adopted_style_genes(voice_source)
    fingerprint = voice_fingerprint or "- 贴近当前视角；让动作先于解释。"
    style_block = ""
    if adopted_genes:
        style_block = (
            "\n\n## 本书采纳手法与反面清单（style-corpus）\n"
            + render_writer_style_brief(
                adopted_genes, max_chars=240, chapter=chapter
            )
        )
    elif not _has_registered_exemplar(voice_source):
        # Nothing adopted and no registered exemplar: offer the name menu.
        # The writer picks one or two. The full library stays on disk.
        style_block = (
            "\n\n## 风格正反例（style-corpus 默认参照）\n"
            + render_writer_style_brief(chapter=chapter)
        )
    p2_room = WRITER_CONTEXT_BUDGETS["P2"] - _count_cjk(style_block)
    p2 = _bounded(
        "## 声音指纹\n" + _bounded(fingerprint, p2_room) + style_block,
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


def split_paragraphs(body: str) -> list[str]:
    """The one paragraph split shared by patch plans and review diffs."""
    return [part.strip() for part in re.split(r"\n\s*\n", body) if part.strip()]


def paragraph_index(body: str, *, first_sentence_chars: int = 12) -> str:
    """Compact paragraph number + first-sentence head (docs/51 S1/S4).

    Reviewers and patch writers locate unchanged paragraphs on demand
    instead of re-reading the full chapter. The head fragment is bounded
    so a whole-chapter index stays inside the incremental input budget.
    """
    lines: list[str] = []
    for number, paragraph in enumerate(split_paragraphs(body), 1):
        first = re.split(r"(?<=[。！？])", paragraph)[0].strip()
        lines.append(f"{number}:{first[:first_sentence_chars]}")
    return "\n".join(lines)


def build_regression_diff(
    base: str,
    current: str,
    *,
    context: int = 2,
    max_changed_ratio: float = 0.6,
    max_chars: int = 12000,
) -> str | None:
    """Paragraph-level diff fragments with context (docs/51 S1).

    Returns None when the change is too large for a regression review;
    the caller must then fall back to the full prose admission read.
    """
    old = split_paragraphs(base)
    new = split_paragraphs(current)
    if not old or not new:
        return None
    matcher = difflib.SequenceMatcher(a=old, b=new, autojunk=False)
    blocks: list[str] = []
    changed = 0
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            continue
        changed += max(i2 - i1, j2 - j1)
        start = max(0, j1 - context)
        end = min(len(new), j2 + context)
        lines = [f"## 变更块 ¶{j1 + 1}-¶{j2}（{tag}）"]
        for index in range(start, end):
            marker = "改" if j1 <= index < j2 else "上下文"
            lines.append(f"¶{index + 1} [{marker}] {new[index]}")
        if tag in {"replace", "delete"}:
            for index in range(i1, i2):
                lines.append(f"原¶{index + 1} [旧] {old[index]}")
        blocks.append("\n".join(lines))
    if not blocks:
        return None
    if changed / max(len(old), len(new)) > max_changed_ratio:
        return None
    text = "\n\n".join(blocks)
    if len(text) > max_chars:
        return None
    return text


def render_previous_review(
    outcomes: Iterable[tuple[str, Any]],
    current_prose: str,
) -> str:
    """Previous-round conclusions with deterministic resolution status.

    A finding whose verbatim evidence no longer exists in the current
    body is marked resolved; the regression reviewer confirms the fix
    instead of re-discovering the whole list (docs/51 S1/R5).
    """
    lines = ["# 上一轮双审结论（回归审基线）"]
    for role, outcome in outcomes:
        lines.append(f"## {role} verdict={outcome.verdict}")
        likeness = str(getattr(outcome, "human_likeness", "") or "")
        if likeness and likeness != "not_applicable":
            lines.append(
                f"human_likeness={likeness} "
                f"reader_desire={getattr(outcome, 'reader_desire', '')}"
            )
        findings = getattr(outcome, "findings", ()) or ()
        if not findings:
            lines.append("- 无条目")
        for item in findings:
            evidence = str(item.evidence or "").strip()
            if evidence:
                status = (
                    "未修复（原文仍在）"
                    if evidence in current_prose
                    else "已修复（原文已不在）"
                )
            else:
                status = "无引文"
            lines.append(
                f"- [{item.severity}/{item.scope}] {item.location}："
                f"{item.revision_intent}（{status}）"
            )
    return "\n".join(lines)[:4000]


def plan_local_patch(
    body: str,
    findings: Iterable[Any],
) -> list[dict[str, Any]] | None:
    """Return bounded paragraph targets only when every open MUST is local.

    docs/51 S4: each target carries up to two full context paragraphs on
    each side plus its paragraph number, so the patch role never needs
    the full draft.
    """
    must = _open_local_must(findings)
    if not must or any(item.scope != "local" for item in must):
        return None
    paragraphs = split_paragraphs(body)
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
                "paragraph_number": index + 1,
                "context_before": paragraphs[max(0, index - 2):index],
                "context_after": paragraphs[index + 1:index + 3],
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


def normalize_must_category(value: Any) -> str:
    """Map a reviewer category label onto the gate enum.

    Empty means the finding predates the category contract (or the
    reviewer omitted it): the gate then keeps the conservative legacy
    routing. Unknown labels also stay conservative; only an explicit
    non-deterministic label downgrades a MUST to SUGGEST.
    """
    text = str(value or "").strip().lower()
    if not text:
        return ""
    return MUST_CATEGORY_ALIASES.get(text, "")


def gate_must_findings(
    findings: Iterable[Any],
    *,
    force_revision: bool = False,
) -> tuple[list[Any], list[Any]]:
    """Split open MUSTs into revision triggers and SUGGEST downgrades.

    A MUST drives revision only when it carries a deterministic
    category (docs/51 S2), when the role verdict forces it (Blind
    Reader synthetic), when it is blocking, or when no category was
    declared at all (conservative legacy routing). An explicitly
    non-deterministic MUST becomes SUGGEST: recorded for the author,
    never auto-revised.
    """
    triggering: list[Any] = []
    downgraded: list[Any] = []
    for item in findings:
        if item.severity.upper() != "MUST" or item.status.lower() != "open":
            continue
        category = str(getattr(item, "category", "") or "")
        if (
            force_revision
            or category in DETERMINISTIC_MUST_CATEGORIES
            or category == ""
            or item.scope == "blocking"
        ):
            triggering.append(item)
        else:
            downgraded.append(replace(item, severity="SUGGEST"))
    return triggering, downgraded


def _normalize_reference(text: str) -> str:
    return re.sub(r"[\s\u3000\W_]+", "", str(text or "")).lower()


def author_revision_budget_error(
    previous_references: Iterable[str], new_reference: str
) -> str | None:
    """docs/51 S5: one author authorization per chapter by default.

    A second authorization is accepted only when it carries a genuinely
    new direction (a reference different from the first); a repeated
    "再修一轮" is refused. Gate and checkpoint decisions never take this
    path.
    """
    previous = [str(ref) for ref in previous_references]
    if len(previous) < MAX_AUTHOR_REVISION_AUTHORIZATIONS:
        return None
    if len(previous) == MAX_AUTHOR_REVISION_AUTHORIZATIONS:
        normalized_new = _normalize_reference(new_reference)
        if normalized_new and all(
            normalized_new != _normalize_reference(ref) for ref in previous
        ):
            return None
        return (
            "本章作者续修授权已用满 1 次；再次授权必须携带与上次不同的新修改方向，"
            "不接受重复的“再修一轮”。可改用 accept-draft 接受当前稿或停止任务。"
        )
    return (
        "本章作者续修授权已达上限，不再接受新的授权；"
        "请选择 accept-draft 接受当前稿或停止任务。"
    )


def summarize_suggestions(
    findings: Iterable[Any], *, max_chars: int = 400
) -> str:
    """One bounded author-facing summary of SUGGEST-level findings."""
    lines: list[str] = []
    for item in findings:
        if str(item.severity).upper() != "SUGGEST":
            continue
        note = str(
            item.revision_intent or item.reader_effect or item.location or ""
        ).strip()
        if note:
            lines.append(f"- {note}")
    if not lines:
        return ""
    text = "措辞级建议（不触发自动修订，供作者一次性裁量）：" + "\n".join(lines)
    return text[:max_chars]

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
    if phase == "awaiting_targeted_recheck":
        return "定向复核"
    if phase in {
        "awaiting_blind_reader",
        "awaiting_chapter_editor",
        "awaiting_double_review",
    }:
        return "双审中"
    if phase in {"hard_check", "promoting"}:
        return "硬检查"
    return "待写"
