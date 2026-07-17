"""Canonical constants for the `books/<slug>/` planning workflow.

Single source of truth shared by the project template renderer
(`project_templates.py`), the narrative gate (`book_gates.py`), and the
skill adapter's book-project operations (`book_project.py`). Changing a
section heading, a state name, or a role here changes it everywhere; the
per-book `tools/` shells and templates are generated from these values.
"""

from __future__ import annotations

# --- Scene package structure ------------------------------------------------

SCENE_PACKAGE_REQUIRED_SECTIONS: tuple[str, ...] = (
    "1. 场景压力",
    "1c. 决策问题",
    "2. 在场者状态",
    "3. Beat 因果链",
    "4. 信息账本",
    "5. 信息预算",
    "7. 场景余波",
)
BEAT_CHAIN_SECTION = "3. Beat 因果链"
MIN_BEATS = 2
MIN_CHAPTER_PARAGRAPHS = 3
MIN_FORMAL_CJK = 5000
DRAFT_MODES: tuple[str, ...] = ("formal", "exploration")
ARC_AUDIT_INTERVAL = 5

# Cells that identify a Markdown table header row (excluded from row counts).
TABLE_HEADER_CELLS = frozenset({"#", "信息", "人物", "触发"})

# Placeholder values that count as "not filled" in gate checks.
PLACEHOLDER_TOKENS = frozenset({"待填", "TODO", "TBD", "无"})

# Explicit waiver: a material file containing this mark counts as filled even
# when everything else is still the template skeleton.
MATERIAL_WAIVER_MARK = "无需"

# --- Chapter state machine (v3, extended) ------------------------------------

CHAPTER_STATES: tuple[str, ...] = (
    "planned",
    "context_collected",
    "scene_packaged",
    "action_drafted",
    "dialogue_planned",
    "drafted",
    "surface_checked",
    "causal_reviewed",
    "line_reviewed",
    "texture_reviewed",
    "consistency_checked",
    "blind_read",
    "editorial_reviewed",
    "ready",
)
STATE_BLOCKED = "blocked"

# A forward transition must follow this graph exactly. Explicit rollback to an
# earlier state remains legal because review failures must return to the
# material layer that owns the problem.
FORWARD_STATE_TRANSITIONS: dict[str, str] = {
    current: following
    for current, following in zip(CHAPTER_STATES, CHAPTER_STATES[1:])
}

# --- Review roles and verdicts ------------------------------------------------

REVIEW_ROLES: tuple[str, ...] = (
    "causal-editor",
    "line-editor",
    "texture-editor",
    "consistency-guard",
    "blind-reader",
    "chapter-editor",
)

# Which state each review role completes on success.
REVIEW_STATE_FOR_ROLE: dict[str, str] = {
    "causal-editor": "causal_reviewed",
    "line-editor": "line_reviewed",
    "texture-editor": "texture_reviewed",
    "consistency-guard": "consistency_checked",
    "blind-reader": "blind_read",
    "chapter-editor": "editorial_reviewed",
}

# Roles whose passing verdict is required before a chapter may enter `ready`.
READY_REQUIRED_REVIEWS: tuple[tuple[str, str], ...] = (
    ("causal-editor", "pass"),
    ("line-editor", "pass"),
    ("texture-editor", "pass"),
    ("consistency-guard", "pass"),
    ("blind-reader", "pass"),
    ("chapter-editor", "ready_for_editor_decision"),
)

# chapter-editor issues an editorial verdict; the other roles pass/fail.
EDITORIAL_VERDICTS: tuple[str, ...] = ("ready_for_editor_decision", "needs_revision")
REVIEW_VERDICTS: tuple[str, ...] = ("pass", "needs_revision")
PASSING_VERDICTS = frozenset({"pass", "ready_for_editor_decision"})

# --- Creative evidence --------------------------------------------------------

EVIDENCE_KINDS: tuple[str, ...] = (
    "preference",
    "branch",
    "evaluation",
    "generation",
    "arc_audit",
    "rule_decision",
)

EVIDENCE_DIRECTORIES: dict[str, str] = {
    "preference": "preferences",
    "branch": "branches",
    "evaluation": "evaluations",
    "generation": "generations",
    "arc_audit": "arc-audits",
    "rule_decision": "rule-decisions",
}

# Stable policy identifiers let generated projects, role prompts, evidence
# records, and the canonical Skill refer to the same non-negotiable boundary.
HUMAN_NARRATIVE_POLICIES: dict[str, str] = {
    "no-deliberate-defects": (
        "不得用故意错别字、事实错误、随机病句或机械噪声伪造人类感。"
    ),
    "single-winner-branch": (
        "分支实验必须选择一个胜者并记录其代价，不得静默拼接全部候选。"
    ),
    "model-score-not-approval": (
        "模型评分、门禁通过和 ready 状态都不是作者批准或发布许可。"
    ),
    "aesthetic-does-not-override-facts": (
        "审美偏好不能覆盖 Canon、事实证据、因果责任或人物已知边界。"
    ),
    "exploration-not-ready": (
        "探索稿可跳过正式材料门，但不得进入 ready 或冒充正式章节。"
    ),
    "role-name-not-independence": (
        "角色名不同不构成独立审稿；必须记录 reviewer/provider/model/context。"
    ),
}
HUMAN_NARRATIVE_POLICY_IDS: tuple[str, ...] = tuple(
    HUMAN_NARRATIVE_POLICIES
)

# --- Genre presets -------------------------------------------------------------

GENRE_PRESETS: tuple[str, ...] = ("urban", "fantasy", "wasteland", "generic")

_GENRE_KEYWORDS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("fantasy", ("仙", "修真", "修仙", "玄幻", "奇幻", "魔幻", "仙侠", "武侠", "神话", "剑")),
    ("wasteland", ("末世", "末日", "废土", "科幻", "星际", "灾变", "废土")),
    ("urban", ("都市", "现实", "神豪", "系统", "职场", "娱乐", "校园", "商战", "重生", "历史", "军事")),
)


def genre_preset(genre: str) -> str:
    """Classify a free-form genre string into a voice-bible preset.

    First matching preset wins (fantasy > wasteland > urban); anything
    unmatched falls back to "generic". The preset only selects writing-guidance
    defaults (sensory palette, rhythm, mechanism-exposition clause) — it never
    blocks anything.
    """
    for preset, keywords in _GENRE_KEYWORDS:
        if any(k in genre for k in keywords):
            return preset
    return "generic"


# Clause injected into CLAUDE.md 严格边界 per preset: never explain the
# mechanism, only render sensation and consequence.
MECHANISM_CLAUSES: dict[str, str] = {
    "urban": "禁止在正文里解释金手指/系统的来历与机制；只呈现规则现象、感官与后果。",
    "fantasy": "禁止在正文里解释穿越/奇幻机制；只呈现感官与后果。",
    "wasteland": "禁止在正文里解释灾难成因与科幻设定机制；只呈现感官与后果。",
    "generic": "禁止在正文里解释世界观机制来历；只呈现感官与后果。",
}
