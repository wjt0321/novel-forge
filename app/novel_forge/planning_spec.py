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
    "1d. 认知与可证伪假设",
    "1e. 规划反证与常识检查",
    "2. 在场者状态",
    "3. Beat 因果链",
    "3c. 因果归属账本",
    "4. 信息账本",
    "5. 信息预算",
    "5b. 专业判断审计",
    "7. 场景余波",
)
BEAT_CHAIN_SECTION = "3. Beat 因果链"
DECISION_QUESTION_SECTION = "1c. 决策问题"
COGNITION_LEDGER_SECTION = "1d. 认知与可证伪假设"
PLANNING_FALSIFICATION_SECTION = "1e. 规划反证与常识检查"
CAUSAL_RESPONSIBILITY_SECTION = "3c. 因果归属账本"
EXPERTISE_AUDIT_SECTION = "5b. 专业判断审计"
DIALOGUE_INTENT_FIELDS: tuple[tuple[str, ...], ...] = (
    ("关键对白意图", "关键对白"),
)
CHAPTER_HANDOFF_SECTION = "0b. 章际交接"
CHAPTER_HANDOFF_FIELDS: tuple[tuple[str, ...], ...] = (
    ("上一章正文路径",),
    ("上一章正文 SHA-256", "上一章正文SHA-256"),
    ("上一章结尾原文",),
    ("本章开头原文",),
    ("上一章结束时间",),
    ("本章开始时间",),
    ("上一章结束地点",),
    ("本章开始地点",),
    ("上一章结束动作",),
    ("本章开始动作",),
    ("转场类型",),
    ("上一章末明确决定",),
    ("本章是否推翻该决定", "是否推翻上一章决定"),
    ("若推翻，触发事件原文", "推翻触发原文"),
)
CHAPTER_HANDOFF_TRANSITIONS: tuple[str, ...] = (
    "same_day_continuous",
    "cross_day",
    "flashback",
    "parallel",
)
CHAPTER_DECISION_REVERSAL_VALUES = frozenset({"是", "否", "不适用"})
DECISION_QUESTION_FIELDS: tuple[tuple[str, ...], ...] = (
    ("不能同时得到的两样东西",),
    ("角色拒绝承认什么", "拒绝承认"),
    ("角色误读了谁或什么", "误读"),
    ("哪句话不能说出口", "不能说出口的话"),
    ("最终接受的具体代价", "接受的代价"),
)
MIN_ACTIVE_DECISION_QUESTIONS = 2
PLANNING_FALSIFICATION_FIELDS: tuple[tuple[str, ...], ...] = (
    ("时间/日历算术", "时间与日历", "时间算术"),
    ("物理动作机制", "动作机制"),
    ("人物知识来源", "知识来源"),
    ("不可逆性反证", "不可逆选择反证"),
    ("场景停止点", "停止点"),
)
MIN_BEATS = 2
MIN_CAUSAL_RESPONSIBILITY_ROWS = 1
MIN_CHAPTER_PARAGRAPHS = 3
MIN_FORMAL_CJK = 5000
DRAFT_MODES: tuple[str, ...] = (
    "formal",
    "exploration",
    "degraded_exploration",
)
ARC_AUDIT_INTERVAL = 5
MAX_AUTOMATIC_GENERATIONS = 2

# Runtime budgets are operational guardrails, not literary verdicts. Generation
# evidence still reports chapter-local metrics, while v3.9 session audits read
# the harness export directly and issue a hard continue/stop decision.
MAX_CACHED_INPUT_TOKENS_PER_CHAPTER = 2_000_000
MAX_REQUESTS_PER_CHAPTER = 30
MAX_DRAFT_MUTATIONS_PER_CHAPTER = 3
MAX_REVIEW_CALLS_PER_CHAPTER = 3
MAX_REQUEST_CONTEXT_TOKENS = 120_000

# v4.0 chapter-session orchestration. A sequence is an orchestration convenience,
# never a shared writer context: every chapter still receives a fresh native
# session and a bounded handoff packet.
DEFAULT_CHAPTERS_PER_SEQUENCE = 1
MAX_CHAPTERS_PER_SEQUENCE = 4
MAX_HANDOFF_MEMORY_CHARS = 12_000
MAX_HANDOFF_SCENE_PACKAGE_CHARS = 8_000
MAX_HANDOFF_PREVIOUS_TAIL_CHARS = 1_600
MAX_HANDOFF_VOICE_EXEMPLAR_CHARS = 1_200
MAX_HANDOFF_TOTAL_CHARS = 28_000

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
    "drafted",
    "surface_checked",
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

DEFAULT_REVIEW_ROLES: tuple[str, ...] = (
    "blind-reader",
    "chapter-editor",
)

# Specialist roles remain valid for old projects and difficult chapters, but
# they are not part of the default ready path. The chapter editor owns their
# former checklist in one consolidated review and may request one specialist
# when a concrete risk justifies the extra context.
SPECIALIST_REVIEW_ROLES: tuple[str, ...] = (
    "causal-editor",
    "line-editor",
    "texture-editor",
    "consistency-guard",
)
REVIEW_ROLES: tuple[str, ...] = (
    *DEFAULT_REVIEW_ROLES,
    *SPECIALIST_REVIEW_ROLES,
)

# Which state each review role completes on success.
REVIEW_STATE_FOR_ROLE: dict[str, str] = {
    "blind-reader": "blind_read",
    "chapter-editor": "editorial_reviewed",
    "causal-editor": "specialist_reviewed",
    "line-editor": "specialist_reviewed",
    "texture-editor": "specialist_reviewed",
    "consistency-guard": "specialist_reviewed",
}

# Roles whose passing verdict is required before a chapter may enter `ready`.
READY_REQUIRED_REVIEWS: tuple[tuple[str, str], ...] = (
    ("blind-reader", "pass"),
    ("chapter-editor", "ready_for_editor_decision"),
)

# chapter-editor issues an editorial verdict; the other roles pass/fail.
EDITORIAL_VERDICTS: tuple[str, ...] = ("ready_for_editor_decision", "needs_revision")
REVIEW_VERDICTS: tuple[str, ...] = ("pass", "needs_revision")
PASSING_VERDICTS = frozenset({"pass", "ready_for_editor_decision"})

# Shared lint/template language. These remain advisory at the lint layer;
# contextual severity belongs to the line/texture review gates.
EXPLANATION_TIC_PATTERNS: tuple[str, ...] = (
    r"这意味着",
    r"真正重要的是",
    r"最重要的是",
    r"[他她](?:突然)?意识到",
    r"[他她]终于明白",
    r"[他她]终于懂得",
    r"这一切说明",
    r"这一切表明",
    r"归根结底",
    r"说到底",
    r"不是告别，是",
    r"不是结束，是",
)

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
    "world-not-protagonist-proof": (
        "世界不得只为证明主角正确而排列线索；重要推断必须保留替代解释和可推翻条件。"
    ),
    "expertise-must-be-executable": (
        "专业判断必须写清证据、未证前提、执行条件、成本与风险，不能只靠术语证明人物聪明。"
    ),
}

GENERATION_METRICS_SOURCES: tuple[str, ...] = (
    "harness_reported",
    "user_observed",
    "unknown",
)
GENERATION_STAGES: tuple[str, ...] = ("raw", "revised", "final")
PROVENANCE_CONFIDENCE_LEVELS: tuple[str, ...] = (
    "harness_exposed",
    "mixed_attestation",
    "user_attested",
    "unknown",
)
GENERATION_REASONING_EFFORTS: tuple[str, ...] = (
    "unknown",
    "standard",
    "high",
    "max",
)
GENERATION_SANDBOX_PROFILES: tuple[str, ...] = (
    "unknown",
    "full",
    "restricted",
    "no_shell",
)
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
