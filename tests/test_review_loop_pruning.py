"""Regression tests for docs/51 review-loop pruning (S2 / S5 / S6).

The admission review stays full-text; only deterministic hard-issue MUSTs
drive a revision, wording-level findings become SUGGEST, recurrence breaks
the loop, and the author can accept the current draft instead of paying
for another round.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.novel_forge.native_relay import NativeWorkflowRelay
from app.novel_forge.workflow import ReviewFinding, ReviewOutcome, WorkflowError
from app.novel_forge.workflow_iteration import (
    author_revision_budget_error,
    gate_must_findings,
    normalize_must_category,
)
from tests.test_native_relay import _complete_minimal, _request
from tests.test_native_relay_gate_decisions import (
    _blind_pass,
    _complete_reviews,
    _editor_pass,
    _formal_chapter,
    _short_prose,
    _start_lean_with_prose,
)
from tests.test_workflow import _prose


def _must(category: str = "", scope: str = "local", evidence: str = "林舟握住门把"):
    return ReviewFinding(
        severity="MUST",
        location="开头",
        evidence=evidence,
        reader_effect="读者出戏",
        revision_intent="统一口径",
        status="open",
        scope=scope,
        category=category,
    )


def _hard_must(evidence: str = "林舟握住门把", category: str = "object") -> dict:
    return {
        "severity": "MUST",
        "category": category,
        "scope": "local",
        "location": "开头",
        "evidence": evidence,
        "revision_intent": "同一物件不能同时在两处",
    }


def test_gate_downgrades_only_explicit_non_deterministic_must():
    triggering, downgraded = gate_must_findings(
        [
            _must("object"),
            _must("other"),
            _must(""),
            _must("other", scope="blocking"),
            ReviewFinding(
                severity="MAY", location="全文", evidence="",
                reader_effect="可选", revision_intent="可选",
            ),
        ]
    )
    assert len(triggering) == 3
    assert len(downgraded) == 1
    assert downgraded[0].severity == "SUGGEST"

    forced, none = gate_must_findings([_must("other")], force_revision=True)
    assert len(forced) == 1 and not none


def test_normalize_must_category_aliases():
    assert normalize_must_category("时间线") == "timeline"
    assert normalize_must_category("物件归属") == "object"
    assert normalize_must_category("硬锚") == "hard_anchor"
    assert normalize_must_category("章末钩子") == "hook"
    assert normalize_must_category("措辞") == "other"
    assert normalize_must_category("不认识的标签") == ""
    assert normalize_must_category(None) == ""


def test_author_revision_budget_requires_new_direction():
    assert author_revision_budget_error([], "方向一") is None
    assert author_revision_budget_error(["方向一"], "方向一") is not None
    assert author_revision_budget_error(["方向一"], " 方向一。 ") is not None
    assert author_revision_budget_error(["方向一"], "方向二：重排时间线") is None
    assert author_revision_budget_error(["方向一", "方向二"], "方向三") is not None


def test_wording_must_never_spends_a_revision_round(tmp_path: Path):
    root = tmp_path / "repo"
    relay = NativeWorkflowRelay(root, strict_audit=False)
    _start_lean_with_prose(relay, "demo", _prose("分档章"))
    wording = {
        "severity": "MUST",
        "category": "other",
        "scope": "local",
        "location": "开头",
        "evidence": "林舟握住门把",
        "revision_intent": "称谓口径建议统一",
    }
    result = _complete_reviews(
        relay,
        "demo",
        blind_payload=_blind_pass(
            verdict="needs_revision",
            human_likeness="uncertain",
            uncertain_note="开头一段解释偏充分。",
            must=[wording],
        ),
        editor_payload=_editor_pass(verdict="needs_revision", must=[wording]),
    )
    # No automatic revision round: the author decides once, with the
    # wording-level suggestions summarized on the decision card.
    assert result.user_state == "decision_required"
    state = relay._load_state("demo")
    assert state["decision_kind"] == "literary_revision_required"
    assert state["suggest_findings"]
    assert state["editor_outcome"]["findings"][0]["severity"] == "SUGGEST"
    card = relay.next_action("demo")
    assert card["kind"] == "user_decision"
    assert any("accept-draft" in option for option in card["options"])
    assert "措辞级建议" in card["message"]
    assert not _formal_chapter(root).exists()
    accepted = relay.accept_current_draft(
        "demo", decision_reference="作者接受措辞级建议现状"
    )
    assert accepted.user_state == "chapter_complete"
    assert "措辞级建议" in accepted.message
    assert _formal_chapter(root).is_file()


def test_suggest_tier_never_triggers_revision(tmp_path: Path):
    root = tmp_path / "repo"
    relay = NativeWorkflowRelay(root, strict_audit=False)
    _start_lean_with_prose(relay, "demo", _prose("建议章"))
    suggestion = {
        "location": "开头",
        "evidence": "林舟握住门把",
        "revision_intent": "称谓可以更口语一点",
    }
    result = _complete_reviews(
        relay,
        "demo",
        blind_payload=_blind_pass(suggest=[suggestion]),
        editor_payload=_editor_pass(suggest=[suggestion]),
    )
    assert result.user_state == "chapter_complete"
    assert "措辞级建议" in result.message
    assert _formal_chapter(root).is_file()


def test_deterministic_must_still_triggers_revision(tmp_path: Path):
    root = tmp_path / "repo"
    relay = NativeWorkflowRelay(root, strict_audit=False)
    _start_lean_with_prose(relay, "demo", _prose("硬伤章"))
    result = _complete_reviews(
        relay,
        "demo",
        editor_payload=_editor_pass(
            verdict="needs_revision", must=[_hard_must()]
        ),
    )
    assert result.user_state == "running"
    action = relay.next_action("demo")
    assert action["role"] == "writer"
    assert action["stage"] == "patch"
    assert action["must_findings"]


def test_legacy_must_without_category_keeps_conservative_routing(tmp_path: Path):
    root = tmp_path / "repo"
    relay = NativeWorkflowRelay(root, strict_audit=False)
    _start_lean_with_prose(relay, "demo", _prose("旧契约章"))
    legacy = _hard_must()
    del legacy["category"]
    result = _complete_reviews(
        relay,
        "demo",
        editor_payload=_editor_pass(verdict="needs_revision", must=[legacy]),
    )
    assert result.user_state == "running"
    assert relay.next_action("demo")["stage"] == "patch"


def test_synthetic_verdict_forces_revision_without_category(tmp_path: Path):
    root = tmp_path / "repo"
    relay = NativeWorkflowRelay(root, strict_audit=False)
    _start_lean_with_prose(relay, "demo", _prose("人工感章"))
    result = _complete_reviews(
        relay,
        "demo",
        blind_payload=_blind_pass(
            verdict="needs_revision",
            human_likeness="synthetic",
            must=[{
                "severity": "MUST",
                "scope": "structural",
                "location": "全文",
                "evidence": "林舟握住门把",
                "revision_intent": "删掉解释句，改成动作",
            }],
        ),
    )
    assert result.user_state == "running"
    assert relay.next_action("demo")["stage"] == "patch"


def _reach_recurrence_decision(relay: NativeWorkflowRelay, root: Path):
    _start_lean_with_prose(relay, "demo", _prose("复发章"))
    hard = _hard_must()
    result = _complete_reviews(
        relay,
        "demo",
        editor_payload=_editor_pass(verdict="needs_revision", must=[hard]),
    )
    assert result.user_state == "running"
    patch = relay.next_action("demo")
    (Path(patch["capsule"]["path"]) / "draft/正文.md").write_text(
        _prose("复发修订"), encoding="utf-8"
    )
    _complete_minimal(relay, "demo")
    return _complete_reviews(
        relay,
        "demo",
        editor_payload=_editor_pass(verdict="needs_revision", must=[hard]),
    )


def test_recurrence_breaker_hands_draft_to_author(tmp_path: Path):
    root = tmp_path / "repo"
    relay = NativeWorkflowRelay(root, strict_audit=False)
    result = _reach_recurrence_decision(relay, root)
    assert result.user_state == "decision_required"
    state = relay._load_state("demo")
    assert state["decision_kind"] == "recurrence_accept_draft"
    card = relay.next_action("demo")
    assert card["kind"] == "user_decision"
    assert any("accept-draft" in option for option in card["options"])
    assert "熔断" in card["message"]
    assert not _formal_chapter(root).exists()


def test_accept_draft_promotes_and_records_author_decision(tmp_path: Path):
    root = tmp_path / "repo"
    relay = NativeWorkflowRelay(root, strict_audit=False)
    _reach_recurrence_decision(relay, root)
    result = relay.accept_current_draft(
        "demo", decision_reference="作者接受当前稿，不再续修"
    )
    assert result.user_state == "chapter_complete"
    assert _formal_chapter(root).is_file()
    state = relay._load_state("demo")
    assert state["phase"] == "complete"
    assert state["author_accepted_draft"] is True
    records = list(
        (root / ".local-guardian/demo/native-relay/author-revisions").glob("*.json")
    )
    assert records
    record = json.loads(records[0].read_text(encoding="utf-8"))
    assert record["decision_action"] == "accept_draft"
    assert record["publication_eligibility"] is False


def test_accept_draft_refuses_gate_and_exploration_decisions(tmp_path: Path):
    root = tmp_path / "repo"
    relay = NativeWorkflowRelay(root, strict_audit=False)
    _start_lean_with_prose(relay, "demo", _short_prose())
    for _ in range(3):
        action = relay.next_action("demo")
        (Path(action["capsule"]["path"]) / "draft/正文.md").write_text(
            _short_prose(), encoding="utf-8"
        )
        result = _complete_minimal(relay, "demo")
    assert result.user_state == "decision_required"
    card = relay.next_action("demo")
    assert not any("accept-draft" in option for option in card["options"])
    with pytest.raises(WorkflowError):
        relay.accept_current_draft("demo", decision_reference="试图豁免硬门")


def test_author_authorization_cap_and_new_direction(tmp_path: Path):
    root = tmp_path / "repo"
    relay = NativeWorkflowRelay(root, strict_audit=False)
    _start_lean_with_prose(relay, "demo", _prose("授权章"))

    def round_with_must(evidence: str, category: str, label: str):
        result = _complete_reviews(
            relay,
            "demo",
            editor_payload=_editor_pass(
                verdict="needs_revision",
                must=[_hard_must(evidence, category)],
            ),
        )
        if result.user_state == "running":
            patch = relay.next_action("demo")
            (Path(patch["capsule"]["path"]) / "draft/正文.md").write_text(
                _prose(label), encoding="utf-8"
            )
            _complete_minimal(relay, "demo")
        return result

    def patch_then_review(evidence: str, category: str, label: str):
        patch = relay.next_action("demo")
        (Path(patch["capsule"]["path"]) / "draft/正文.md").write_text(
            _prose(label), encoding="utf-8"
        )
        _complete_minimal(relay, "demo")
        return _complete_reviews(
            relay,
            "demo",
            editor_payload=_editor_pass(
                verdict="needs_revision",
                must=[_hard_must(evidence, category)],
            ),
        )

    # Round 1 auto revision; round 2 a different anchor -> budget decision.
    round_with_must("林舟握住门把", "object", "授权一")
    result = round_with_must("只是把掌心压得更紧", "timeline", "授权二")
    assert result.user_state == "decision_required"
    assert relay._load_state("demo")["decision_kind"] == "literary_revision_required"

    resumed = relay.authorize_revision("demo", decision_reference="方向一：统一物件归属")
    assert resumed.user_state == "running"
    result = patch_then_review("他没有回头", "object", "授权三")
    assert result.user_state == "decision_required"

    with pytest.raises(WorkflowError, match="新修改方向"):
        relay.authorize_revision("demo", decision_reference="方向一：统一物件归属")
    resumed = relay.authorize_revision("demo", decision_reference="方向二：重排时间线")
    assert resumed.user_state == "running"
    result = patch_then_review("林舟握住门把", "object", "授权四")
    assert result.user_state == "decision_required"
    with pytest.raises(WorkflowError, match="上限"):
        relay.authorize_revision("demo", decision_reference="方向三：再修一轮")


def _realistic_prose() -> str:
    """A chapter with normal-length paragraphs (docs/51 cost model shape)."""
    paragraphs = [
        f"林舟在第{i}个巷口停下，把第{i}枚铜钱压进木盒的裂缝，更鼓从远处传来，"
        f"他没有回头，只是把掌心压得更紧，檐角的雨水顺着瓦当滴进石阶的凹处，"
        f"巷尾的灯笼被风掀起一角，又落回去。"
        for i in range(1, 73)
    ]
    return "# 第一章 门后的雨\n\n" + "\n\n".join(paragraphs) + "\n"


def test_paragraph_index_is_compact_and_locatable():
    from app.novel_forge.workflow_iteration import (
        paragraph_index,
        split_paragraphs,
    )

    body = "甲段第一句。甲段第二句。\n\n乙段第一句。"
    assert split_paragraphs(body) == ["甲段第一句。甲段第二句。", "乙段第一句。"]
    assert paragraph_index(body) == "1:甲段第一句。\n2:乙段第一句。"
    assert paragraph_index(body, first_sentence_chars=2) == "1:甲段\n2:乙段"


def test_local_patch_input_is_incremental_and_read_bounded(tmp_path: Path):
    from app.novel_forge.workflow_iteration import split_paragraphs

    root = tmp_path / "repo"
    relay = NativeWorkflowRelay(root, strict_audit=False)
    prose = (
        _realistic_prose()
        + "\n林舟把铜扣放回左侧口袋，这句解释只出现一次。\n"
    )
    _start_lean_with_prose(relay, "demo", prose)
    hard = {
        "severity": "MUST",
        "category": "object",
        "scope": "local",
        "location": "末段",
        "evidence": "林舟把铜扣放回左侧口袋，这句解释只出现一次。",
        "revision_intent": "铜扣归属前后矛盾",
    }
    result = _complete_reviews(
        relay,
        "demo",
        blind_payload=_blind_pass(evidence_quote="林舟把铜扣放回左侧口袋"),
        editor_payload=_editor_pass(
            verdict="needs_revision",
            must=[hard],
            evidence_quote="林舟把铜扣放回左侧口袋",
        ),
    )
    assert result.user_state == "running"
    patch = relay.next_action("demo")
    assert patch["stage"] == "local-patch"
    assert patch["full_body_read_forbidden"] is True
    assert len(patch["read_only_project_files"]) == 1
    assert patch["read_only_project_files"][0].endswith("local-patch/input.json")

    input_path = Path(patch["input_file"])
    payload = json.loads(input_path.read_text(encoding="utf-8"))
    assert "禁止打开 draft/正文.md" in payload["instruction"]
    target = payload["targets"][0]
    assert target["paragraph_number"] == len(split_paragraphs(prose))
    assert len(target["context_before"]) == 2
    assert target["context_after"] == []
    assert isinstance(payload["paragraph_index"], str)
    assert payload["paragraph_index"].startswith("1:")
    assert input_path.stat().st_size <= 4096, input_path.stat().st_size

    Path(patch["result_file"]).write_text(
        json.dumps(
            {"replacements": [{
                "target": target["target"],
                "replacement": "林舟把铜扣塞回左侧口袋。",
            }]},
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    completed = _complete_minimal(relay, "demo")
    assert completed.user_state == "running"
    staged = relay._staged_body_path(relay._load_state("demo"))
    assert "铜扣塞回左侧口袋" in staged.read_text(encoding="utf-8")


def _middle_marker_prose() -> str:
    """Realistic chapter with one unique marker paragraph in the middle."""
    paragraphs = [
        f"林舟在第{i}个巷口停下，把第{i}枚铜钱压进木盒的裂缝，更鼓从远处传来，"
        f"他没有回头，只是把掌心压得更紧，檐角的雨水顺着瓦当滴进石阶的凹处，"
        f"巷尾的灯笼被风掀起一角，又落回去。"
        for i in range(1, 73)
    ]
    paragraphs.insert(30, "林舟把铜扣放回左侧口袋，这句解释只出现一次。")
    return "# 第一章 门后的雨\n\n" + "\n\n".join(paragraphs) + "\n"


def test_build_regression_diff_bounds_and_context():
    from app.novel_forge.workflow_iteration import build_regression_diff

    base = "\n\n".join(f"第{i}段原文。" for i in range(1, 21))
    changed = base.replace("第10段原文。", "第10段改后。")
    diff = build_regression_diff(base, changed)
    assert diff is not None
    assert "第10段改后。" in diff and "[改]" in diff
    assert "第8段原文。" in diff and "第12段原文。" in diff
    assert "第1段原文。" not in diff
    assert build_regression_diff(base, base) is None
    mostly_new = "\n\n".join(f"全新第{i}段。" for i in range(1, 21))
    assert build_regression_diff(base, mostly_new) is None


def test_render_previous_review_marks_resolution():
    from app.novel_forge.workflow_iteration import render_previous_review

    fixed = _must("object", evidence="已被修掉的原文")
    open_item = _must("timeline", evidence="仍在正文的原文")
    outcome = ReviewOutcome(
        verdict="needs_revision", findings=(fixed, open_item)
    )
    text = render_previous_review(
        [("chapter-editor", outcome)], "仍在正文的原文 其余正文"
    )
    assert "已修复（原文已不在）" in text
    assert "未修复（原文仍在）" in text


def test_local_patch_middle_paragraph_gets_targeted_recheck(tmp_path: Path):
    root = tmp_path / "repo"
    relay = NativeWorkflowRelay(root, strict_audit=False)
    prose = _middle_marker_prose()
    _start_lean_with_prose(relay, "demo", prose)
    hard = {
        "severity": "MUST",
        "category": "object",
        "scope": "local",
        "location": "中段",
        "evidence": "林舟把铜扣放回左侧口袋，这句解释只出现一次。",
        "revision_intent": "铜扣归属前后矛盾",
    }
    result = _complete_reviews(
        relay,
        "demo",
        blind_payload=_blind_pass(
            verdict="needs_revision",
            human_likeness="uncertain",
            uncertain_note="中段解释停顿。",
            must=[hard],
            evidence_quote="林舟在第1个巷口停下",
        ),
        editor_payload=_editor_pass(
            verdict="needs_revision",
            must=[hard],
            evidence_quote="林舟在第1个巷口停下",
        ),
    )
    assert result.user_state == "running"
    patch = relay.next_action("demo")
    assert patch["stage"] == "local-patch"
    target = json.loads(Path(patch["input_file"]).read_text(encoding="utf-8"))["targets"][0]["target"]
    Path(patch["result_file"]).write_text(
        json.dumps(
            {"replacements": [{
                "target": target,
                "replacement": "林舟把铜扣塞回左侧口袋，指尖在袋口停了一拍。",
            }]},
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    completed = _complete_minimal(relay, "demo")

    # docs/51 S3: no escalation -> one targeted Chapter Editor recheck.
    assert completed.message == "局部修订完成，正在定向复核被改段。"
    state = relay._load_state("demo")
    assert state["phase"] == "awaiting_targeted_recheck"
    recheck = relay.next_action("demo")
    assert recheck["role"] == "chapter-editor"
    assert recheck["review_mode"] == "targeted"
    assert recheck["parallel_review"] is False
    capsule_dir = Path(recheck["review_capsule"]["path"])
    assert (capsule_dir / "regression-diff.md").is_file()
    assert (capsule_dir / "previous-review.md").is_file()
    assert (capsule_dir / "paragraph-index.md").is_file()
    assert not (capsule_dir / "prose.md").exists()
    assert "定向复核" in (capsule_dir / "instructions.md").read_text(encoding="utf-8")
    assert "铜扣塞回左侧口袋" in (capsule_dir / "regression-diff.md").read_text(encoding="utf-8")

    Path(recheck["result_file"]).write_text(
        json.dumps(_editor_pass(evidence_quote="林舟在第1个巷口停下"), ensure_ascii=False),
        encoding="utf-8",
    )
    finished = _complete_minimal(relay, "demo")
    assert finished.user_state == "chapter_complete"
    assert _formal_chapter(root).is_file()
    # The inherited Blind Reader MUST was deterministically closed.
    blind_md = (root / "books/demo/reviews/ch01-blind-reader.md").read_text(encoding="utf-8")
    assert "closed" in blind_md


def test_local_patch_hook_region_escalates_to_full_review(tmp_path: Path):
    root = tmp_path / "repo"
    relay = NativeWorkflowRelay(root, strict_audit=False)
    prose = _realistic_prose() + "\n林舟把铜扣放回左侧口袋，这句解释只出现一次。\n"
    _start_lean_with_prose(relay, "demo", prose)
    hard = {
        "severity": "MUST",
        "category": "object",
        "scope": "local",
        "location": "末段",
        "evidence": "林舟把铜扣放回左侧口袋，这句解释只出现一次。",
        "revision_intent": "铜扣归属前后矛盾",
    }
    _complete_reviews(
        relay,
        "demo",
        blind_payload=_blind_pass(evidence_quote="林舟把铜扣放回左侧口袋"),
        editor_payload=_editor_pass(
            verdict="needs_revision", must=[hard],
            evidence_quote="林舟把铜扣放回左侧口袋",
        ),
    )
    patch = relay.next_action("demo")
    target = json.loads(Path(patch["input_file"]).read_text(encoding="utf-8"))["targets"][0]["target"]
    Path(patch["result_file"]).write_text(
        json.dumps(
            {"replacements": [{
                "target": target,
                "replacement": "林舟把铜扣塞回左侧口袋。",
            }]},
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    _complete_minimal(relay, "demo")
    # Hook region touched -> full double review, admission capsules.
    blind = relay.next_action("demo")
    assert blind["role"] == "blind-reader"
    assert blind["review_mode"] == "admission"
    assert (Path(blind["review_capsule"]["path"]) / "prose.md").is_file()


def test_staged_revision_second_round_is_regression_review(tmp_path: Path):
    root = tmp_path / "repo"
    relay = NativeWorkflowRelay(root, strict_audit=False)
    prose = _middle_marker_prose()
    _start_lean_with_prose(relay, "demo", prose)
    hard = {
        "severity": "MUST",
        "category": "object",
        "scope": "structural",
        "location": "中段",
        "evidence": "林舟把铜扣放回左侧口袋，这句解释只出现一次。",
        "revision_intent": "铜扣归属需要跨段协调",
    }
    result = _complete_reviews(
        relay,
        "demo",
        blind_payload=_blind_pass(evidence_quote="林舟在第1个巷口停下"),
        editor_payload=_editor_pass(
            verdict="needs_revision", must=[hard],
            evidence_quote="林舟在第1个巷口停下",
        ),
    )
    assert result.user_state == "running"
    patch = relay.next_action("demo")
    assert patch["stage"] == "patch"
    fixed = prose.replace(
        "林舟把铜扣放回左侧口袋，这句解释只出现一次。",
        "林舟把铜扣塞回左侧口袋，指尖在袋口停了一拍。",
    )
    (Path(patch["capsule"]["path"]) / "draft/正文.md").write_text(fixed, encoding="utf-8")
    _complete_minimal(relay, "demo")

    # docs/51 S1: round 2 reads diff + previous conclusions, not full prose.
    blind = relay.next_action("demo")
    assert blind["role"] == "blind-reader"
    assert blind["review_mode"] == "regression"
    blind_dir = Path(blind["review_capsule"]["path"])
    assert not (blind_dir / "prose.md").exists()
    assert "回归审" in (blind_dir / "instructions.md").read_text(encoding="utf-8")
    diff_text = (blind_dir / "regression-diff.md").read_text(encoding="utf-8")
    assert "铜扣塞回左侧口袋" in diff_text
    previous = (blind_dir / "previous-review.md").read_text(encoding="utf-8")
    assert "已修复（原文已不在）" in previous
    editor = relay.next_action("demo")
    assert editor["role"] == "chapter-editor"
    assert editor["review_mode"] == "regression"
    editor_dir = Path(editor["review_capsule"]["path"])
    assert (editor_dir / "scene-package.md").is_file()
    assert not (editor_dir / "prose.md").exists()

    # Both cards were already issued above; complete them directly.
    Path(blind["result_file"]).write_text(
        json.dumps(
            _blind_pass(evidence_quote="林舟在第1个巷口停下"),
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    _complete_minimal(relay, "demo", role="blind-reader")
    Path(editor["result_file"]).write_text(
        json.dumps(
            _editor_pass(evidence_quote="林舟在第1个巷口停下"),
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    result = _complete_minimal(relay, "demo", role="chapter-editor")
    assert result.user_state == "chapter_complete"
    assert _formal_chapter(root).is_file()

