"""Tests for Markdown-authoritative creative workflow evidence."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from app.novel_forge.book_evidence import (
    BookEvidenceError,
    evidence_status,
    parse_evidence_markdown,
    record_evidence,
    render_evidence_markdown,
)
from app.novel_forge.project_templates import init_book_project
from app.novel_forge.skill_adapter import main as adapter_main


def _make_book(tmp_path: Path, slug: str = "demo") -> Path:
    result = init_book_project(tmp_path, slug, "演示书", "现实悬疑")
    book_dir = Path(result["book_dir"])
    chapter = book_dir / "chapters/e01/ch-01/正文.md"
    chapter.parent.mkdir(parents=True, exist_ok=True)
    chapter.write_text("# 第一章\n\n陈拾没有开门。\n", encoding="utf-8")
    candidate_dir = book_dir / "evaluation/experiments/opening/candidates"
    candidate_dir.mkdir(parents=True, exist_ok=True)
    (candidate_dir / "A.md").write_text("陈拾没有开门。\n", encoding="utf-8")
    (candidate_dir / "B.md").write_text("门响了三次，陈拾没有动。\n", encoding="utf-8")
    return book_dir


def _base(kind: str, record_id: str, **overrides) -> dict:
    data = {
        "schema_version": 1,
        "id": record_id,
        "kind": kind,
        "created_at": "2026-07-17T12:00:00Z",
        "authority": "agent",
        "source_paths": ["chapters/e01/ch-01/正文.md"],
        "summary": "只用于索引的短摘要。",
    }
    kind_fields = {
        "generation": {
            "chapter": 1,
            "draft_mode": "formal",
            "writer_type": "agent",
            "provider": "local",
            "model": "model-a",
            "content_path": "chapters/e01/ch-01/正文.md",
            "content_sha256": "",
        },
        "branch": {
            "chapter": 1,
            "experiment_id": "opening",
            "candidates": ["A", "B"],
            "winner": "B",
            "selection_mode": "single_winner",
            "evaluation_ids": ["evaluation.opening.reader-1"],
            "discarded_tradeoffs": {"A": "切入更直接，但悬念过早说破。"},
        },
        "evaluation": {
            "chapter": 1,
            "experiment_id": "opening",
            "candidate_labels": ["A", "B"],
            "blinded": True,
            "preferred_label": "B",
            "reviewer_type": "model",
            "reviewer_id": "reader-1",
            "provider": "other-provider",
            "model": "model-b",
            "context_scope": "candidate_prose_only",
            "questions": {
                "desire": "他想拖延开门。",
                "concealment": "他不愿承认自己在等门外的人离开。",
                "relationship_change": "门外的人获得了主动权。",
                "memorable_images": ["三次敲门", "没有动的手"],
                "next_question": "第四次敲门会不会响？",
            },
        },
        "preference": {
            "chapter": 1,
            "branch_id": "branch.opening",
            "evaluation_ids": ["evaluation.opening.reader-1"],
            "selected_id": "B",
            "rejected_ids": ["A"],
            "accepted_qualities": ["悬念来自人物动作范围内"],
            "rejected_qualities": ["过早解释人物意图"],
            "decision_authority": "author",
        },
        "arc_audit": {
            "scope": "checkpoint",
            "start_chapter": 1,
            "end_chapter": 5,
            "volume_id": None,
            "verdict": "continue",
            "open_must": 0,
            "source_sha256": {
                "chapters/e01/ch-01/正文.md": "0" * 64,
            },
        },
        "rule_decision": {
            "rule_id": "decision-questions",
            "hypothesis": "决策问题能减少被动转折。",
            "lifecycle": "experimental",
            "tested_works": ["demo"],
            "tested_genres": ["现实悬疑"],
            "tested_models": ["model-a"],
            "intervention_type": "planning_prompt",
            "retirement_reason": None,
        },
    }
    data.update(kind_fields[kind])
    data.update(overrides)
    return data


def _write_input(path: Path, data: dict, *, validate: bool = True) -> None:
    if validate:
        text = render_evidence_markdown(data)
    else:
        import json

        text = (
            "# Raw pressure input\n\n"
            "<!-- novel-forge-evidence:v1 -->\n"
            "```json\n"
            f"{json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True)}\n"
            "```\n"
        )
    path.write_text(text, encoding="utf-8")


def _arc_with_current_hash(book_dir: Path, record_id: str) -> dict:
    source_paths: list[str] = []
    source_sha256: dict[str, str] = {}
    for number in range(1, 6):
        chapter_path = f"chapters/e01/ch-{number:02d}/正文.md"
        chapter = book_dir / chapter_path
        chapter.parent.mkdir(parents=True, exist_ok=True)
        if not chapter.exists():
            chapter.write_text(
                f"# 第{number}章\n\n检查点正文。\n",
                encoding="utf-8",
            )
        source_paths.append(chapter_path)
        source_sha256[chapter_path] = hashlib.sha256(
            chapter.read_bytes()
        ).hexdigest()
    return _base(
        "arc_audit",
        record_id,
        source_paths=source_paths,
        source_sha256=source_sha256,
    )


def _json_output(capsys) -> dict:
    return json.loads(capsys.readouterr().out.strip())


def test_evidence_markdown_round_trip_and_rejects_approval_claims():
    data = _base("preference", "preference.opening")
    data["authority"] = "author"

    record = parse_evidence_markdown(render_evidence_markdown(data))

    assert record.id == "preference.opening"
    assert record.kind == "preference"
    assert record.data["selected_id"] == "B"

    with pytest.raises(BookEvidenceError, match="author_approved"):
        render_evidence_markdown({**data, "author_approved": True})
    with pytest.raises(BookEvidenceError, match="publication_eligibility"):
        render_evidence_markdown({**data, "publication_eligibility": True})


def test_record_generation_verifies_content_hash_and_does_not_return_body(
    tmp_path: Path,
):
    book_dir = _make_book(tmp_path)
    chapter = book_dir / "chapters/e01/ch-01/正文.md"
    digest = hashlib.sha256(chapter.read_bytes()).hexdigest()
    source = tmp_path / "generation.md"
    _write_input(
        source,
        _base(
            "generation",
            "generation.ch01.first",
            content_sha256=digest,
        ),
    )

    result = record_evidence(tmp_path, "demo", source)

    assert result == {
        "record_id": "generation.ch01.first",
        "kind": "generation",
        "evidence_path": "evidence/generations/generation.ch01.first.md",
        "chapter": 1,
    }
    assert (book_dir / result["evidence_path"]).exists()
    assert "只用于索引" not in str(result)

    stale = tmp_path / "stale-generation.md"
    _write_input(
        stale,
        _base(
            "generation",
            "generation.ch01.stale",
            content_sha256="0" * 64,
        ),
    )
    with pytest.raises(BookEvidenceError, match="content_sha256"):
        record_evidence(tmp_path, "demo", stale)


def test_generation_accepts_auditable_runtime_lineage_and_rejects_bad_metrics():
    data = _base(
        "generation",
        "generation.ch01.metrics",
        authority="human_delegate",
        elapsed_seconds=3000,
        input_tokens=12000,
        output_tokens=8000,
        total_tokens=20000,
        cached_input_tokens=9000,
        request_count=12,
        draft_write_count=1,
        draft_edit_count=1,
        review_call_count=2,
        metrics_source="user_observed",
        pause_count=1,
        interaction_count=2,
        review_round=2,
        parent_generation_id="generation.ch01.r2",
        generation_stage="final",
        provenance_confidence="user_attested",
        content_sha256="0" * 64,
    )

    record = parse_evidence_markdown(render_evidence_markdown(data))

    assert record.data["elapsed_seconds"] == 3000
    assert record.data["review_round"] == 2
    assert record.data["generation_stage"] == "final"
    assert record.data["cached_input_tokens"] == 9000
    assert record.data["draft_edit_count"] == 1

    with pytest.raises(BookEvidenceError, match="elapsed_seconds"):
        render_evidence_markdown({**data, "elapsed_seconds": -1})
    with pytest.raises(BookEvidenceError, match="metrics_source"):
        render_evidence_markdown({**data, "metrics_source": "guessed"})
    with pytest.raises(BookEvidenceError, match="request_count"):
        render_evidence_markdown({**data, "request_count": -1})


def test_evidence_status_reports_runtime_budget_pressure(tmp_path: Path):
    book_dir = _make_book(tmp_path)
    chapter = book_dir / "chapters/e01/ch-01/正文.md"
    source = tmp_path / "generation-budget.md"
    _write_input(
        source,
        _base(
            "generation",
            "generation.ch01.expensive",
            content_sha256=hashlib.sha256(chapter.read_bytes()).hexdigest(),
            metrics_source="harness_reported",
            provenance_confidence="harness_exposed",
            run_id="session-expensive",
            agent_harness="claude-code",
            reasoning_effort="high",
            sandbox_profile="full",
            tool_capabilities=["read", "write", "shell"],
            tool_failures=[],
            cached_input_tokens=8_400_000,
            input_tokens=61_000,
            output_tokens=40_000,
            total_tokens=8_501_000,
            request_count=40,
            draft_write_count=2,
            draft_edit_count=15,
            review_call_count=6,
        ),
    )
    record_evidence(tmp_path, "demo", source)

    status = evidence_status(tmp_path, "demo", chapter=1)

    assert status["runtime_budget"]["status"] == "exceeded"
    codes = {
        finding["code"]
        for finding in status["runtime_budget"]["findings"]
    }
    assert "cached-context-budget" in codes
    assert "draft-mutation-budget" in codes
    assert "review-call-budget" in codes


def test_runtime_budget_aggregates_generations_by_chapter(tmp_path: Path):
    book_dir = _make_book(tmp_path)
    chapter = book_dir / "chapters/e01/ch-01/正文.md"
    first = tmp_path / "generation-first.md"
    _write_input(
        first,
        _base(
            "generation",
            "generation.ch01.first",
            content_sha256=hashlib.sha256(chapter.read_bytes()).hexdigest(),
            cached_input_tokens=1_200_000,
            request_count=20,
            draft_write_count=1,
            draft_edit_count=0,
            review_call_count=1,
        ),
    )
    record_evidence(tmp_path, "demo", first)
    chapter.write_text(
        "# 第一章\n\n陈拾没有开门。门外的人又敲了一次。\n",
        encoding="utf-8",
    )
    second = tmp_path / "generation-second.md"
    _write_input(
        second,
        _base(
            "generation",
            "generation.ch01.second",
            content_sha256=hashlib.sha256(chapter.read_bytes()).hexdigest(),
            cached_input_tokens=1_200_000,
            request_count=20,
            draft_write_count=0,
            draft_edit_count=1,
            review_call_count=1,
            parent_generation_id="generation.ch01.first",
            generation_stage="revised",
        ),
    )
    record_evidence(tmp_path, "demo", second)

    budget = evidence_status(tmp_path, "demo", chapter=1)["runtime_budget"]

    assert budget["status"] == "exceeded"
    totals = budget["chapters"][0]["totals"]
    assert totals["cached_input_tokens"] == 2_400_000
    assert totals["request_count"] == 40


def test_runtime_budget_is_unassessed_when_metrics_are_unknown(tmp_path: Path):
    book_dir = _make_book(tmp_path)
    chapter = book_dir / "chapters/e01/ch-01/正文.md"
    source = tmp_path / "generation-unknown-budget.md"
    _write_input(
        source,
        _base(
            "generation",
            "generation.ch01.unknown-budget",
            content_sha256=hashlib.sha256(chapter.read_bytes()).hexdigest(),
        ),
    )
    record_evidence(tmp_path, "demo", source)

    budget = evidence_status(tmp_path, "demo", chapter=1)["runtime_budget"]

    assert budget["status"] == "unassessed"
    assert budget["chapters"][0]["status"] == "unassessed"


def test_generation_requires_consistent_authority_and_runtime_identity():
    user_attested_agent = _base(
        "generation",
        "generation.ch01.user-attested-agent",
        authority="agent",
        content_sha256="0" * 64,
        provenance_confidence="user_attested",
    )
    with pytest.raises(BookEvidenceError, match="user_attested.*authority"):
        render_evidence_markdown(user_attested_agent)

    harness_exposed = _base(
        "generation",
        "generation.ch01.harness",
        content_sha256="0" * 64,
        metrics_source="harness_reported",
        provenance_confidence="harness_exposed",
        run_id="run-agent-a-001",
        agent_harness="deepseek-writer-a",
        reasoning_effort="standard",
        sandbox_profile="no_shell",
        tool_capabilities=["read_file", "write_file"],
        tool_failures=["shell: sandbox denied"],
    )
    record = parse_evidence_markdown(render_evidence_markdown(harness_exposed))

    assert record.data["run_id"] == "run-agent-a-001"
    assert record.data["sandbox_profile"] == "no_shell"
    assert record.data["tool_failures"] == ["shell: sandbox denied"]

    with pytest.raises(BookEvidenceError, match="run_id"):
        render_evidence_markdown({**harness_exposed, "run_id": None})
    with pytest.raises(BookEvidenceError, match="reasoning_effort"):
        render_evidence_markdown(
            {**harness_exposed, "reasoning_effort": "ultra"}
        )
    with pytest.raises(BookEvidenceError, match="sandbox_profile"):
        render_evidence_markdown(
            {**harness_exposed, "sandbox_profile": "mystery"}
        )


def test_record_generation_rejects_duplicate_content_version(tmp_path: Path):
    book_dir = _make_book(tmp_path)
    chapter = book_dir / "chapters/e01/ch-01/正文.md"
    digest = hashlib.sha256(chapter.read_bytes()).hexdigest()

    first = tmp_path / "generation-first.md"
    _write_input(
        first,
        _base(
            "generation",
            "generation.ch01.raw",
            content_sha256=digest,
            generation_stage="raw",
        ),
    )
    record_evidence(tmp_path, "demo", first)

    duplicate = tmp_path / "generation-duplicate.md"
    _write_input(
        duplicate,
        _base(
            "generation",
            "generation.ch01.final",
            content_sha256=digest,
            generation_stage="final",
            review_round=3,
        ),
    )
    with pytest.raises(BookEvidenceError, match="相同正文"):
        record_evidence(tmp_path, "demo", duplicate)


def test_degraded_generation_requires_runtime_failure_evidence():
    data = _base(
        "generation",
        "generation.ch01.degraded",
        draft_mode="degraded_exploration",
        content_sha256="0" * 64,
        agent_harness="writer-a",
        sandbox_profile="no_shell",
        tool_capabilities=["read_file", "write_file"],
        tool_failures=["shell: sandbox denied"],
    )

    record = parse_evidence_markdown(render_evidence_markdown(data))
    assert record.data["tool_failures"] == ["shell: sandbox denied"]

    for missing in (
        "agent_harness",
        "sandbox_profile",
        "tool_capabilities",
        "tool_failures",
    ):
        invalid = dict(data)
        invalid.pop(missing)
        with pytest.raises(BookEvidenceError, match=missing):
            render_evidence_markdown(invalid)


def test_third_generation_requires_explicit_human_authorization(
    tmp_path: Path,
):
    book_dir = _make_book(tmp_path)
    chapter = book_dir / "chapters/e01/ch-01/正文.md"
    for number in range(1, 3):
        chapter.write_text(
            f"# 第一章\n\n第 {number} 个正文版本。\n",
            encoding="utf-8",
        )
        source = tmp_path / f"generation-{number}.md"
        _write_input(
            source,
            _base(
                "generation",
                f"generation.ch01.r{number}",
                content_sha256=hashlib.sha256(
                    chapter.read_bytes()
                ).hexdigest(),
            ),
        )
        record_evidence(tmp_path, "demo", source)

    chapter.write_text("# 第一章\n\n第三个正文版本。\n", encoding="utf-8")
    third = tmp_path / "generation-third.md"
    third_data = _base(
        "generation",
        "generation.ch01.r3",
        content_sha256=hashlib.sha256(chapter.read_bytes()).hexdigest(),
    )
    _write_input(third, third_data)
    with pytest.raises(BookEvidenceError, match="人工授权"):
        record_evidence(tmp_path, "demo", third)

    authorized = tmp_path / "generation-third-authorized.md"
    _write_input(
        authorized,
        {
            **third_data,
            "id": "generation.ch01.r3-authorized",
            "authority": "human_delegate",
            "human_regeneration_authorized": True,
            "human_decision_reference": "user-request-2026-07-18",
        },
    )
    result = record_evidence(tmp_path, "demo", authorized)
    assert result["record_id"] == "generation.ch01.r3-authorized"


def test_evidence_status_collapses_legacy_duplicate_generations(
    tmp_path: Path,
):
    book_dir = _make_book(tmp_path)
    chapter = book_dir / "chapters/e01/ch-01/正文.md"
    digest = hashlib.sha256(chapter.read_bytes()).hexdigest()
    generation_dir = book_dir / "evidence/generations"
    generation_dir.mkdir(parents=True, exist_ok=True)
    for number, stage in ((1, "raw"), (2, "final")):
        data = _base(
            "generation",
            f"generation.ch01.legacy-{number}",
            content_sha256=digest,
            generation_stage=stage,
            review_round=number - 1,
        )
        (generation_dir / f"{data['id']}.md").write_text(
            render_evidence_markdown(data),
            encoding="utf-8",
        )

    status = evidence_status(tmp_path, "demo", chapter=1)

    assert status["generation_record_count"] == 2
    assert status["generation_count"] == 1
    assert status["review_cycle_status"] == "initial"
    assert status["another_generation_requires_human"] is False
    assert status["duplicate_generation_groups"] == [
        {
            "chapter": 1,
            "content_sha256": digest,
            "record_ids": [
                "generation.ch01.legacy-1",
                "generation.ch01.legacy-2",
            ],
        }
    ]


def test_evidence_status_reports_generation_convergence_budget(tmp_path: Path):
    book_dir = _make_book(tmp_path)
    chapter = book_dir / "chapters/e01/ch-01/正文.md"
    for number, stage in ((1, "raw"), (2, "final")):
        chapter.write_text(
            f"# 第一章\n\n第 {number} 版正文，陈拾没有开门。\n",
            encoding="utf-8",
        )
        digest = hashlib.sha256(chapter.read_bytes()).hexdigest()
        source = tmp_path / f"generation-{number}.md"
        _write_input(
            source,
            _base(
                "generation",
                f"generation.ch01.r{number}",
                content_sha256=digest,
                review_round=number - 1,
                generation_stage=stage,
                metrics_source="unknown",
            ),
        )
        record_evidence(tmp_path, "demo", source)

    status = evidence_status(tmp_path, "demo", chapter=1)

    assert status["generation_count"] == 2
    assert status["automatic_generation_limit"] == 2
    assert status["review_cycle_status"] == "budget_exhausted"
    assert status["another_generation_requires_human"] is True


def test_book_wide_generation_status_does_not_merge_chapter_budgets(
    tmp_path: Path,
):
    book_dir = _make_book(tmp_path)
    chapter1 = book_dir / "chapters/e01/ch-01/正文.md"
    chapter2 = book_dir / "chapters/e01/ch-02/正文.md"
    chapter2.parent.mkdir(parents=True, exist_ok=True)
    chapter2.write_text("# 第二章\n\n门又响了。\n", encoding="utf-8")
    for number, chapter_path in ((1, chapter1), (2, chapter2)):
        source = tmp_path / f"generation-ch{number:02d}.md"
        content_path = f"chapters/e01/ch-{number:02d}/正文.md"
        _write_input(
            source,
            _base(
                "generation",
                f"generation.ch{number:02d}.raw",
                chapter=number,
                source_paths=[content_path],
                content_path=content_path,
                content_sha256=hashlib.sha256(
                    chapter_path.read_bytes()
                ).hexdigest(),
            ),
        )
        record_evidence(tmp_path, "demo", source)

    status = evidence_status(tmp_path, "demo")

    assert status["generation_count"] == 2
    assert status["review_cycle_status"] == "not_applicable"
    assert status["another_generation_requires_human"] is False
    assert status["generation_cycles"] == [
        {
            "chapter": 1,
            "generation_count": 1,
            "review_cycle_status": "initial",
            "another_generation_requires_human": False,
        },
        {
            "chapter": 2,
            "generation_count": 1,
            "review_cycle_status": "initial",
            "another_generation_requires_human": False,
        },
    ]


@pytest.mark.parametrize(
    "overrides, message",
    [
        ({"selection_mode": "blend"}, "single_winner"),
        ({"winner": ["A", "B"]}, "winner"),
        ({"winner": "C"}, "candidates"),
        ({"discarded_tradeoffs": {}}, "discarded_tradeoffs"),
    ],
)
def test_branch_decision_rejects_select_all_and_unrecorded_blend(
    tmp_path: Path, overrides: dict, message: str
):
    _make_book(tmp_path)
    source = tmp_path / "branch.md"
    _write_input(
        source,
        _base("branch", "branch.opening", **overrides),
        validate=False,
    )

    with pytest.raises(BookEvidenceError, match=message):
        record_evidence(tmp_path, "demo", source)


def test_preference_requires_authority_and_never_mutates_canon(tmp_path: Path):
    book_dir = _make_book(tmp_path)
    canon = book_dir / "memory/canon/facts/handwritten.md"
    canon.parent.mkdir(parents=True, exist_ok=True)
    canon.write_text("人工事实。\n", encoding="utf-8")
    before = hashlib.sha256(canon.read_bytes()).hexdigest()

    invalid = tmp_path / "model-preference.md"
    _write_input(
        invalid,
        _base(
            "preference",
            "preference.model-choice",
            authority="author",
            decision_authority="model",
        ),
        validate=False,
    )
    with pytest.raises(BookEvidenceError, match="decision_authority"):
        record_evidence(tmp_path, "demo", invalid)

    valid = tmp_path / "author-preference.md"
    evaluation = tmp_path / "evaluation.md"
    _write_input(
        evaluation,
        _base("evaluation", "evaluation.opening.reader-1"),
    )
    record_evidence(tmp_path, "demo", evaluation)
    branch = tmp_path / "branch.md"
    _write_input(branch, _base("branch", "branch.opening"))
    record_evidence(tmp_path, "demo", branch)
    _write_input(
        valid,
        _base(
            "preference",
            "preference.author-choice",
            authority="author",
        ),
    )
    record_evidence(tmp_path, "demo", valid)

    assert hashlib.sha256(canon.read_bytes()).hexdigest() == before


def test_status_reports_unresolved_experiments_and_recent_preferences(
    tmp_path: Path,
):
    _make_book(tmp_path)

    unresolved = evidence_status(tmp_path, "demo")
    assert unresolved["unresolved_branch_experiments"] == ["opening"]
    assert unresolved["resolved_branch_experiments"] == []
    assert unresolved["recent_preference_ids"] == []

    evaluation = tmp_path / "evaluation.md"
    _write_input(
        evaluation,
        _base("evaluation", "evaluation.opening.reader-1"),
    )
    record_evidence(tmp_path, "demo", evaluation)
    branch = tmp_path / "branch.md"
    _write_input(branch, _base("branch", "branch.opening"))
    record_evidence(tmp_path, "demo", branch)
    preference = tmp_path / "preference.md"
    _write_input(
        preference,
        _base(
            "preference",
            "preference.opening.author",
            authority="author",
        ),
    )
    record_evidence(tmp_path, "demo", preference)

    resolved = evidence_status(tmp_path, "demo")
    assert resolved["unresolved_branch_experiments"] == []
    assert resolved["resolved_branch_experiments"] == ["opening"]
    assert resolved["recent_preference_ids"] == ["preference.opening.author"]


def test_arc_and_rule_evidence_validation_and_status(tmp_path: Path):
    book_dir = _make_book(tmp_path)
    due = evidence_status(tmp_path, "demo", chapter=5)
    assert due["arc_audit_due"] is True
    assert due["arc_audit_satisfied"] is False

    arc = tmp_path / "arc.md"
    _write_input(arc, _arc_with_current_hash(book_dir, "arc.checkpoint.01-05"))
    rule = tmp_path / "rule.md"
    _write_input(rule, _base("rule_decision", "rule.decision-questions"))

    record_evidence(tmp_path, "demo", arc)
    record_evidence(tmp_path, "demo", rule)
    status = evidence_status(tmp_path, "demo")

    assert status["counts"]["arc_audit"] == 1
    assert status["counts"]["rule_decision"] == 1
    assert status["record_ids"] == [
        "arc.checkpoint.01-05",
        "rule.decision-questions",
    ]
    checkpoint = evidence_status(tmp_path, "demo", chapter=5)
    assert checkpoint["arc_audit_due"] is True
    assert checkpoint["arc_audit_satisfied"] is True

    chapter = book_dir / "chapters/e01/ch-01/正文.md"
    chapter.write_text(
        chapter.read_text(encoding="utf-8") + "\n审计后修改。\n",
        encoding="utf-8",
    )
    stale_checkpoint = evidence_status(tmp_path, "demo", chapter=5)
    assert stale_checkpoint["arc_audit_satisfied"] is False
    assert stale_checkpoint["stale_record_ids"] == ["arc.checkpoint.01-05"]

    bad = tmp_path / "bad-rule.md"
    _write_input(
        bad,
        _base(
            "rule_decision",
            "rule.random-errors",
            intervention_type="deliberate_typo",
        ),
        validate=False,
    )
    with pytest.raises(BookEvidenceError, match="deliberate_typo"):
        record_evidence(tmp_path, "demo", bad)

    premature_blocking = tmp_path / "premature-blocking.md"
    _write_input(
        premature_blocking,
        _base(
            "rule_decision",
            "rule.premature-blocking",
            lifecycle="blocking",
        ),
        validate=False,
    )
    with pytest.raises(BookEvidenceError, match="至少需要 3"):
        record_evidence(tmp_path, "demo", premature_blocking)


def test_record_evidence_rejects_duplicate_id_and_path_escape(tmp_path: Path):
    book_dir = _make_book(tmp_path)
    source = tmp_path / "first.md"
    _write_input(source, _arc_with_current_hash(book_dir, "arc.duplicate"))
    record_evidence(tmp_path, "demo", source)

    with pytest.raises(BookEvidenceError, match="已存在"):
        record_evidence(tmp_path, "demo", source)

    escaped = tmp_path / "escaped.md"
    _write_input(
        escaped,
        _base(
            "rule_decision",
            "rule.escape",
            source_paths=["../outside.md"],
        ),
    )
    with pytest.raises(BookEvidenceError, match="source_paths"):
        record_evidence(tmp_path, "demo", escaped)


def test_adapter_evidence_status_and_record_contract(tmp_path: Path, capsys):
    book_dir = _make_book(tmp_path)
    chapter = book_dir / "chapters/e01/ch-01/正文.md"
    source = tmp_path / "generation.md"
    _write_input(
        source,
        _base(
            "generation",
            "generation.adapter",
            content_sha256=hashlib.sha256(chapter.read_bytes()).hexdigest(),
            summary="不得从 adapter 泄露的摘要。",
        ),
    )

    code = adapter_main(
        [
            "--root",
            str(tmp_path),
            "record-evidence",
            "demo",
            "--file",
            str(source),
        ]
    )
    denied = _json_output(capsys)
    assert code == 0
    assert denied["ok"] is False
    assert denied["error"]["code"] == "confirmation_required"

    code = adapter_main(
        [
            "--root",
            str(tmp_path),
            "--confirm",
            "record-evidence",
            "record-evidence",
            "demo",
            "--file",
            str(source),
        ]
    )
    recorded = _json_output(capsys)
    assert code == 0
    assert recorded["ok"] is True
    assert recorded["state_changed"] is True
    assert recorded["data"]["record_id"] == "generation.adapter"
    assert "不得从 adapter 泄露" not in json.dumps(recorded, ensure_ascii=False)
    project_state = (
        book_dir / "planning/chapter-state/ch01.md"
    ).read_text(encoding="utf-8")
    assert "- generation_id: generation.adapter" in project_state

    code = adapter_main(
        ["--root", str(tmp_path), "evidence-status", "demo", "1"]
    )
    status = _json_output(capsys)
    assert code == 0
    assert status["ok"] is True
    assert status["state_changed"] is False
    assert status["data"]["counts"]["generation"] == 1
    assert "不得从 adapter 泄露" not in json.dumps(status, ensure_ascii=False)
