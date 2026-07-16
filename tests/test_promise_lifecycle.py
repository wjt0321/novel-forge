"""Tests for Promise Ledger lifecycle, reminders, and RTCO packet integration."""

import json
import sqlite3

import pytest

from app.novel_forge.autonomous import AutonomousError, AutonomousWritingService
from app.novel_forge.db import get_db_path
from app.novel_forge.models import Promise, PromiseStatus, ScenePlan
from app.novel_forge.service import NovelForgeError, NovelForgeService
from tests.conftest import filled_scene_contract_v3, filled_voice_bible, ready_memo


def _filled_book(service: NovelForgeService, slug: str = "promise") -> None:
    service.init_book(slug, "Promise Book")
    vb_src = service.root / "voice-bible.md"
    filled_voice_bible(vb_src)
    service.write_voice_bible(slug, vb_src, note="filled")


def _filled_chapter(service: NovelForgeService, slug: str, number: int) -> None:
    service.create_chapter(slug, number, f"Chapter {number}")
    sc_src = service.root / f"scene-contract-{number}.md"
    filled_scene_contract_v3(sc_src)
    service.write_scene_contract(slug, number, sc_src, note="filled")


def _auto(root) -> AutonomousWritingService:
    return AutonomousWritingService(root)


def _json_output(capsys) -> dict:
    out = capsys.readouterr().out.strip()
    return json.loads(out)


# ------------------------------------------------------------------
# Model and status space
# ------------------------------------------------------------------

def test_promise_status_enum_values():
    assert {s.value for s in PromiseStatus} == {
        "planned",
        "planted",
        "partially_paid",
        "paid_off",
        "abandoned",
    }


def test_promise_model_has_target_fields():
    promise = Promise(
        id=1,
        book_id=1,
        promise_text="the ring must be destroyed",
        status=PromiseStatus.PLANNED,
        planted_scene_ref=None,
        target_chapter_number=5,
        target_scene_ref="s3",
        advanced_scene_ref=None,
        resolved_scene_ref=None,
        abandoned_scene_ref=None,
        created_at="2026-07-15T00:00:00Z",
        updated_at="2026-07-15T00:00:00Z",
    )
    assert promise.status == "planned"
    assert promise.target_chapter_number == 5
    assert promise.target_scene_ref == "s3"


# ------------------------------------------------------------------
# Adding and lifecycle transitions
# ------------------------------------------------------------------

def test_add_planned_promise(service: NovelForgeService) -> None:
    _filled_book(service)
    auto = _auto(service.root)
    promise = auto.add_promise(
        "promise",
        "the hero's secret identity",
        target_chapter_number=3,
        target_scene_ref="s2",
    )
    assert promise.status == "planned"
    assert promise.target_chapter_number == 3
    assert promise.target_scene_ref == "s2"
    assert promise.planted_scene_ref is None


def test_set_chapter_plan_creates_planted_promises_without_target(
    service: NovelForgeService,
) -> None:
    """scene.promises only plants the promise; target must remain undefined."""
    _filled_book(service)
    _filled_chapter(service, "promise", 1)
    auto = _auto(service.root)
    scenes = [
        ScenePlan(
            scene_ref="s1",
            goal="enter",
            obstacle="guard",
            choice="bribe",
            cost="money",
            ending_change="inside",
            promises=["promise-a"],
        ),
        ScenePlan(
            scene_ref="s2",
            goal="find",
            obstacle="dark",
            choice="light",
            cost="exposed",
            ending_change="clue",
        ),
        ScenePlan(
            scene_ref="s3",
            goal="escape",
            obstacle="trap",
            choice="jump",
            cost="injury",
            ending_change="flees",
            promises=["promise-a", "promise-b"],
        ),
        ScenePlan(
            scene_ref="s4",
            goal="hide",
            obstacle="tracker",
            choice="split",
            cost="alone",
            ending_change="isolated",
        ),
    ]
    auto.set_chapter_plan("promise", 1, scenes, status="approved_for_writing")

    promises = auto.list_promises("promise")
    assert len(promises) == 2
    for p in promises:
        assert p.status == "planted"
        assert p.target_chapter_number is None
        assert p.target_scene_ref is None
        assert p.planted_scene_ref in {"s1", "s3"}


def test_legal_status_transitions_and_audits(service: NovelForgeService) -> None:
    _filled_book(service)
    auto = _auto(service.root)
    promise = auto.add_promise("promise", "the sword will break", target_scene_ref="s1")

    # planned -> planted
    p = auto.update_promise_status("promise", promise.id, "planted", scene_ref="s1")
    assert p.status == "planted"
    assert p.planted_scene_ref == "s1"

    # planted -> partially_paid
    p = auto.update_promise_status("promise", promise.id, "partially_paid", scene_ref="s2")
    assert p.status == "partially_paid"
    assert p.advanced_scene_ref == "s2"

    # partially_paid -> paid_off
    p = auto.update_promise_status("promise", promise.id, "paid_off", scene_ref="s4")
    assert p.status == "paid_off"
    assert p.resolved_scene_ref == "s4"

    # Each transition produced an audit event (plus the initial plan event).
    audit = [e for e in auto.audit("promise") if e.entity_type == "promise"]
    actions = {e.action for e in audit}
    assert actions == {"plan", "planted", "partially_paid", "paid_off"}


def test_illegal_status_transitions_raise(service: NovelForgeService) -> None:
    _filled_book(service)
    auto = _auto(service.root)
    promise = auto.add_promise("promise", "the map is false", target_scene_ref="s1")

    with pytest.raises(AutonomousError, match="Illegal promise status transition"):
        auto.update_promise_status("promise", promise.id, "paid_off", scene_ref="s1")

    # Move to planted, then attempt backwards / skip.
    auto.update_promise_status("promise", promise.id, "planted", scene_ref="s1")
    with pytest.raises(AutonomousError, match="Illegal promise status transition"):
        auto.update_promise_status("promise", promise.id, "planned", scene_ref="s0")
    with pytest.raises(AutonomousError, match="Illegal promise status transition"):
        auto.update_promise_status("promise", promise.id, "paid_off", scene_ref="s9")


def test_terminal_statuses_cannot_transition(service: NovelForgeService) -> None:
    _filled_book(service)
    auto = _auto(service.root)

    paid = auto.add_promise("promise", "paid promise", target_scene_ref="s1")
    for step, ref in [("planted", "s1"), ("partially_paid", "s2"), ("paid_off", "s3")]:
        paid = auto.update_promise_status("promise", paid.id, step, scene_ref=ref)
    with pytest.raises(AutonomousError, match="Illegal promise status transition"):
        auto.update_promise_status("promise", paid.id, "abandoned", scene_ref="s4")

    abandoned = auto.add_promise("promise", "abandoned promise", target_scene_ref="s1")
    abandoned = auto.update_promise_status(
        "promise", abandoned.id, "abandoned", scene_ref="s1"
    )
    assert abandoned.status == "abandoned"
    with pytest.raises(AutonomousError, match="Illegal promise status transition"):
        auto.update_promise_status("promise", abandoned.id, "planted", scene_ref="s2")


def test_audit_records_previous_and_new_status(service: NovelForgeService) -> None:
    _filled_book(service)
    auto = _auto(service.root)
    promise = auto.add_promise("promise", "audited promise", target_scene_ref="s1")
    auto.update_promise_status("promise", promise.id, "planted", scene_ref="s1")

    audit = [e for e in auto.audit("promise") if e.entity_type == "promise" and e.action == "planted"]
    assert len(audit) == 1
    details = audit[0].details
    assert '"previous_status": "planned"' in details
    assert '"new_status": "planted"' in details


# ------------------------------------------------------------------
# Reminder generation (read-only, idempotent)
# ------------------------------------------------------------------

def _add_promise(auto, slug, text, status="planned", target_chapter=None, target_scene=None):
    p = auto.add_promise(slug, text, target_chapter_number=target_chapter, target_scene_ref=target_scene)
    if status != "planned":
        p = auto.update_promise_status(slug, p.id, status, scene_ref=target_scene or "s1")
    return p


def test_build_promise_reminders_categorizes_by_target_chapter(
    service: NovelForgeService,
) -> None:
    _filled_book(service)
    auto = _auto(service.root)

    _add_promise(auto, "promise", "overdue promise", target_chapter=1, target_scene="s1")
    _add_promise(auto, "promise", "current promise", target_chapter=2, target_scene="s2")
    _add_promise(auto, "promise", "future promise", target_chapter=3, target_scene="s3")

    reminders = auto.build_promise_reminders("promise", current_chapter_number=2)
    categories = {r["category"] for r in reminders}
    texts = {r["promise_text"] for r in reminders}

    assert "overdue" in categories
    assert "must_resolve" in categories
    assert "future promise" not in texts

    overdue = [r for r in reminders if r["category"] == "overdue"]
    assert len(overdue) == 1
    assert overdue[0]["target_chapter_number"] == 1

    current = [r for r in reminders if r["category"] == "must_resolve"]
    assert len(current) == 1
    assert current[0]["target_chapter_number"] == 2


def test_build_promise_reminders_includes_unscoped_promises(
    service: NovelForgeService,
) -> None:
    _filled_book(service)
    auto = _auto(service.root)

    _add_promise(auto, "promise", "unscoped promise")
    reminders = auto.build_promise_reminders("promise", current_chapter_number=1)
    assert any(r["category"] == "unscoped" for r in reminders)


def test_build_promise_reminders_is_read_only(service: NovelForgeService) -> None:
    _filled_book(service)
    auto = _auto(service.root)
    p = _add_promise(
        auto, "promise", "read-only promise", target_chapter=1, target_scene="s1"
    )

    before_audit = len([e for e in auto.audit("promise") if e.entity_type == "promise"])
    before_status = p.status

    auto.build_promise_reminders("promise", current_chapter_number=2)
    auto.build_promise_reminders("promise", current_chapter_number=2)

    after = auto.get_promise("promise", p.id)
    after_audit = len([e for e in auto.audit("promise") if e.entity_type == "promise"])
    assert after.status == before_status
    assert after_audit == before_audit


def test_build_promise_reminders_excludes_paid_off_and_abandoned(
    service: NovelForgeService,
) -> None:
    _filled_book(service)
    auto = _auto(service.root)

    paid = _add_promise(
        auto, "promise", "paid promise", target_chapter=1, target_scene="s1"
    )
    for step, ref in [("planted", "s1"), ("partially_paid", "s2"), ("paid_off", "s3")]:
        paid = auto.update_promise_status("promise", paid.id, step, scene_ref=ref)

    abandoned = _add_promise(
        auto, "promise", "abandoned promise", target_chapter=1, target_scene="s1"
    )
    abandoned = auto.update_promise_status(
        "promise", abandoned.id, "abandoned", scene_ref="s1"
    )

    reminders = auto.build_promise_reminders("promise", current_chapter_number=2)
    texts = {r["promise_text"] for r in reminders}
    assert "paid promise" not in texts
    assert "abandoned promise" not in texts


# ------------------------------------------------------------------
# Review findings (never auto-approve)
# ------------------------------------------------------------------

def _open_review_findings_for_chapter(service: NovelForgeService, slug: str, number: int) -> list:
    """Return open review findings for a chapter regardless of revision."""
    import sqlite3
    from app.novel_forge.db import get_db_path

    db_path = get_db_path(service.root)
    with sqlite3.connect(str(db_path)) as conn:
        conn.row_factory = sqlite3.Row
        book = conn.execute("SELECT id FROM books WHERE slug = ?", (slug,)).fetchone()
        chapter = conn.execute(
            "SELECT id FROM chapters WHERE book_id = ? AND number = ?",
            (book["id"], number),
        ).fetchone()
        rows = conn.execute(
            """SELECT * FROM review_findings
               WHERE chapter_id = ? AND resolved = 0
               ORDER BY id""",
            (chapter["id"],),
        ).fetchall()
        return rows


def test_add_promise_review_findings_creates_continuity_findings(
    service: NovelForgeService,
) -> None:
    _filled_book(service)
    _filled_chapter(service, "promise", 1)
    _filled_chapter(service, "promise", 2)
    auto = _auto(service.root)

    _add_promise(auto, "promise", "overdue", target_chapter=1, target_scene="s1")
    _add_promise(auto, "promise", "current", target_chapter=2, target_scene="s2")
    _add_promise(auto, "promise", "future", target_chapter=3, target_scene="s3")

    finding_ids = auto.add_promise_review_findings("promise", 2)
    assert len(finding_ids) == 2

    rows = _open_review_findings_for_chapter(service, "promise", 2)
    assert len(rows) == 2
    assert {r["perspective"] for r in rows} == {"continuity"}
    assert {r["severity"] for r in rows} == {"S2", "S3"}


def test_add_promise_review_findings_is_idempotent(
    service: NovelForgeService,
) -> None:
    _filled_book(service)
    _filled_chapter(service, "promise", 1)
    _filled_chapter(service, "promise", 2)
    auto = _auto(service.root)
    _add_promise(auto, "promise", "overdue", target_chapter=1, target_scene="s1")

    first = auto.add_promise_review_findings("promise", 2)
    second = auto.add_promise_review_findings("promise", 2)
    assert first == second

    rows = _open_review_findings_for_chapter(service, "promise", 2)
    assert len(rows) == 1


def test_add_promise_review_findings_does_not_auto_approve(
    service: NovelForgeService,
) -> None:
    _filled_book(service)
    _filled_chapter(service, "promise", 1)
    auto = _auto(service.root)
    _add_promise(auto, "promise", "overdue", target_chapter=1, target_scene="s1")

    auto.add_promise_review_findings("promise", 1)
    chapter = service.get_chapter("promise", 1)
    assert chapter.state.value == "draft"


def test_add_promise_review_findings_uses_single_connection(
    service: NovelForgeService, monkeypatch
) -> None:
    """Nested connections hide uncommitted writes and waste resources."""
    _filled_book(service)
    _filled_chapter(service, "promise", 1)
    auto = _auto(service.root)
    _add_promise(auto, "promise", "overdue", target_chapter=1, target_scene="s1")

    real_connect = sqlite3.connect
    calls: list[tuple] = []

    def tracking_connect(*args, **kwargs):
        calls.append(args)
        return real_connect(*args, **kwargs)

    monkeypatch.setattr(sqlite3, "connect", tracking_connect)
    auto.add_promise_review_findings("promise", 1)
    assert len(calls) == 1


def _ready_chapter_for_approval(service: NovelForgeService, slug: str, number: int) -> None:
    """Prepare a chapter so it is otherwise eligible for approval."""
    body = service.root / f"ch{number}.md"
    body.write_text("正文长段落。" * 200 + "结尾。\n", encoding="utf-8")
    service.write_revision(slug, number, body)
    service.lint_chapter(slug, number)
    ready_memo(service, slug, number)
    service.review_chapter(slug, number)


def test_must_resolve_promise_blocks_approval_until_resolved(
    service: NovelForgeService,
) -> None:
    """A must_resolve promise creates an S2 finding that blocks approval."""
    _filled_book(service)
    _filled_chapter(service, "promise", 1)
    _ready_chapter_for_approval(service, "promise", 1)

    auto = _auto(service.root)
    auto.add_promise(
        "promise", "must resolve now", target_chapter_number=1, target_scene_ref="s1"
    )
    auto.add_promise_review_findings("promise", 1)

    with pytest.raises(NovelForgeError, match="Cannot approve: unresolved S1/S2 review findings"):
        service.approve_chapter("promise", 1, "ok")

    chapter = service.get_chapter("promise", 1)
    with sqlite3.connect(str(get_db_path(service.root))) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT id FROM review_findings WHERE chapter_id = ? AND resolved = 0",
            (chapter.id,),
        ).fetchone()
        assert row is not None
        finding_id = row["id"]

    service.resolve_finding(finding_id, "resolved by author")
    approved = service.approve_chapter("promise", 1, "ok")
    assert approved.state.value == "approved"


def test_update_promise_status_rejects_invalid_status_string(
    service: NovelForgeService,
) -> None:
    """An unknown status string must raise AutonomousError, not ValueError."""
    _filled_book(service)
    auto = _auto(service.root)
    promise = auto.add_promise("promise", "tracked", target_scene_ref="s1")
    with pytest.raises(AutonomousError, match="Invalid promise status"):
        auto.update_promise_status("promise", promise.id, "resolved", scene_ref="s1")


def test_add_promise_rejects_non_positive_target_chapter(
    service: NovelForgeService,
) -> None:
    """target_chapter_number must be a positive integer if provided."""
    _filled_book(service)
    auto = _auto(service.root)
    with pytest.raises(AutonomousError, match="target_chapter_number must be a positive integer"):
        auto.add_promise("promise", "bad", target_chapter_number=0)
    with pytest.raises(AutonomousError, match="target_chapter_number must be a positive integer"):
        auto.add_promise("promise", "bad", target_chapter_number=-1)


def test_set_chapter_plan_preserves_planned_promise_targets(
    service: NovelForgeService,
) -> None:
    """Planting a planned promise via chapter plan must not overwrite its explicit target."""
    _filled_book(service)
    _filled_chapter(service, "promise", 2)
    auto = _auto(service.root)
    auto.add_promise(
        "promise", "planned promise", target_chapter_number=5, target_scene_ref="s5"
    )

    scenes = [
        ScenePlan(
            scene_ref="s2",
            goal="enter",
            obstacle="guard",
            choice="bribe",
            cost="money",
            ending_change="inside",
            promises=["planned promise"],
        ),
        ScenePlan(
            scene_ref="s2b",
            goal="find",
            obstacle="dark",
            choice="light",
            cost="exposed",
            ending_change="clue",
        ),
        ScenePlan(
            scene_ref="s2c",
            goal="escape",
            obstacle="trap",
            choice="jump",
            cost="injury",
            ending_change="flees",
        ),
        ScenePlan(
            scene_ref="s2d",
            goal="hide",
            obstacle="tracker",
            choice="split",
            cost="alone",
            ending_change="isolated",
        ),
    ]
    auto.set_chapter_plan("promise", 2, scenes, status="approved_for_writing")

    promise = next(p for p in auto.list_promises("promise") if p.promise_text == "planned promise")
    assert promise.status == "planted"
    assert promise.target_chapter_number == 5
    assert promise.target_scene_ref == "s5"
    assert promise.planted_scene_ref == "s2"


# ------------------------------------------------------------------
# Explicit promise target management
# ------------------------------------------------------------------


def test_set_promise_target_updates_fields_and_audits(
    service: NovelForgeService,
) -> None:
    _filled_book(service)
    auto = _auto(service.root)
    promise = auto.add_promise(
        "promise", "seed", target_chapter_number=3, target_scene_ref="s3"
    )

    updated = auto.set_promise_target(
        "promise", promise.id, target_chapter_number=5, target_scene_ref="s5"
    )
    assert updated.target_chapter_number == 5
    assert updated.target_scene_ref == "s5"
    assert updated.status == "planned"

    audit = [
        e
        for e in auto.audit("promise")
        if e.entity_type == "promise" and e.action == "set_target"
    ]
    assert len(audit) == 1
    details = audit[0].details
    assert '"previous_target_chapter_number": 3' in details
    assert '"previous_target_scene_ref": "s3"' in details
    assert '"new_target_chapter_number": 5' in details
    assert '"new_target_scene_ref": "s5"' in details


def test_set_promise_target_clears_fields(service: NovelForgeService) -> None:
    _filled_book(service)
    auto = _auto(service.root)
    promise = auto.add_promise(
        "promise", "seed", target_chapter_number=3, target_scene_ref="s3"
    )

    updated = auto.set_promise_target("promise", promise.id, clear=True)
    assert updated.target_chapter_number is None
    assert updated.target_scene_ref is None
    assert updated.status == "planned"


def test_set_promise_target_rejects_clear_with_values(
    service: NovelForgeService,
) -> None:
    _filled_book(service)
    auto = _auto(service.root)
    promise = auto.add_promise("promise", "seed")

    with pytest.raises(
        AutonomousError, match="cannot combine --clear with target_chapter_number"
    ):
        auto.set_promise_target(
            "promise", promise.id, target_chapter_number=5, clear=True
        )


def test_set_promise_target_rejects_missing_chapter(
    service: NovelForgeService,
) -> None:
    _filled_book(service)
    auto = _auto(service.root)
    promise = auto.add_promise("promise", "seed")

    with pytest.raises(AutonomousError, match="target_chapter_number is required"):
        auto.set_promise_target("promise", promise.id, target_scene_ref="s5")


def test_set_promise_target_rejects_invalid_chapter_number(
    service: NovelForgeService,
) -> None:
    _filled_book(service)
    auto = _auto(service.root)
    promise = auto.add_promise("promise", "seed")

    with pytest.raises(AutonomousError, match="positive integer"):
        auto.set_promise_target("promise", promise.id, target_chapter_number=0)


def test_set_promise_target_rejects_cross_book(service: NovelForgeService) -> None:
    _filled_book(service)
    service.init_book("other", "Other Book")
    auto = _auto(service.root)
    promise = auto.add_promise("promise", "seed")

    with pytest.raises(AutonomousError, match=f"Promise {promise.id} not found"):
        auto.set_promise_target("other", promise.id, target_chapter_number=5)


def test_set_promise_target_does_not_change_status(
    service: NovelForgeService,
) -> None:
    _filled_book(service)
    auto = _auto(service.root)
    promise = auto.add_promise("promise", "seed", target_scene_ref="s1")
    promise = auto.update_promise_status(
        "promise", promise.id, "planted", scene_ref="s1"
    )

    updated = auto.set_promise_target(
        "promise", promise.id, target_chapter_number=5, target_scene_ref="s5"
    )
    assert updated.status == "planted"


# ------------------------------------------------------------------
# Skill adapter
# ------------------------------------------------------------------


def test_adapter_set_promise_target_requires_confirm(
    service: NovelForgeService, capsys
) -> None:
    _filled_book(service)
    auto = _auto(service.root)
    promise = auto.add_promise("promise", "seed")

    from app.novel_forge.skill_adapter import main

    code = main(
        [
            "--root",
            str(service.root),
            "set-promise-target",
            "promise",
            str(promise.id),
            "--target-chapter-number",
            "5",
        ]
    )
    assert code == 0
    data = _json_output(capsys)
    assert data["ok"] is False
    assert data["error"]["code"] == "confirmation_required"


def test_adapter_set_promise_target_success(
    service: NovelForgeService, capsys
) -> None:
    _filled_book(service)
    auto = _auto(service.root)
    promise = auto.add_promise("promise", "seed")

    from app.novel_forge.skill_adapter import main

    code = main(
        [
            "--root",
            str(service.root),
            "--confirm",
            "set-promise-target",
            "set-promise-target",
            "promise",
            str(promise.id),
            "--target-chapter-number",
            "5",
            "--target-scene-ref",
            "s5",
        ]
    )
    assert code == 0
    data = _json_output(capsys)
    assert data["ok"] is True
    assert data["operation"] == "set-promise-target"
    assert data["state_changed"] is True
    assert data["data"]["promise"]["target_chapter_number"] == 5
    assert data["data"]["promise"]["target_scene_ref"] == "s5"


def test_cli_set_promise_target(service: NovelForgeService, capsys) -> None:
    _filled_book(service)
    auto = _auto(service.root)
    promise = auto.add_promise("promise", "seed")

    from app.novel_forge.cli import main as cli_main

    code = cli_main(
        [
            "--root",
            str(service.root),
            "set-promise-target",
            "promise",
            str(promise.id),
            "--target-chapter-number",
            "5",
            "--target-scene-ref",
            "s5",
        ]
    )
    assert code == 0
    assert "Set promise 1 target to chapter 5, scene s5" in capsys.readouterr().out


def test_promise_close_auto_resolves_continuity_findings(service: NovelForgeService) -> None:
    """Paying off or abandoning a promise resolves its open continuity findings."""
    _filled_book(service)
    _filled_chapter(service, "promise", 1)
    auto = _auto(service.root)

    promise = auto.add_promise(
        "promise", "must resolve", target_chapter_number=1, target_scene_ref="s1"
    )
    auto.update_promise_status("promise", promise.id, "planted", scene_ref="s1")
    auto.update_promise_status(
        "promise", promise.id, "partially_paid", scene_ref="s1"
    )
    auto.add_promise_review_findings("promise", 1)
    rows_before = _open_review_findings_for_chapter(service, "promise", 1)
    assert len(rows_before) == 1

    auto.update_promise_status(
        "promise", promise.id, "paid_off", scene_ref="s1", resolution_note="resolved"
    )

    rows_after = _open_review_findings_for_chapter(service, "promise", 1)
    assert len(rows_after) == 0
    with sqlite3.connect(str(get_db_path(service.root))) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT * FROM review_findings WHERE id = ?", (rows_before[0]["id"],)
        ).fetchone()
        assert row["resolved"] == 1
        assert "paid_off" in row["resolution_note"]


def test_promise_close_does_not_resolve_another_books_matching_location(
    service: NovelForgeService,
) -> None:
    """Synthetic promise locations must remain scoped to their book."""
    _filled_book(service)
    _filled_chapter(service, "promise", 1)
    _filled_book(service, "other")
    _filled_chapter(service, "other", 1)
    auto = _auto(service.root)

    promise = auto.add_promise(
        "promise", "must resolve", target_chapter_number=1, target_scene_ref="s1"
    )
    auto.update_promise_status("promise", promise.id, "planted", scene_ref="s1")
    auto.update_promise_status(
        "promise", promise.id, "partially_paid", scene_ref="s1"
    )
    own_finding_id = auto.add_promise_review_findings("promise", 1)[0]

    with sqlite3.connect(str(get_db_path(service.root))) as conn:
        other_chapter_id = conn.execute(
            """SELECT chapters.id FROM chapters
               JOIN books ON books.id = chapters.book_id
               WHERE books.slug = 'other' AND chapters.number = 1"""
        ).fetchone()[0]
        other_finding_id = conn.execute(
            """INSERT INTO review_findings
               (chapter_id, perspective, severity, location, evidence, issue, fix)
               VALUES (?, 'continuity', 'S3', ?, 'collision', 'collision', 'keep open')""",
            (other_chapter_id, f"promise:{promise.id}"),
        ).lastrowid

    auto.update_promise_status(
        "promise", promise.id, "paid_off", scene_ref="s2", resolution_note="done"
    )

    with sqlite3.connect(str(get_db_path(service.root))) as conn:
        own_resolved = conn.execute(
            "SELECT resolved FROM review_findings WHERE id = ?", (own_finding_id,)
        ).fetchone()[0]
        other_resolved = conn.execute(
            "SELECT resolved FROM review_findings WHERE id = ?", (other_finding_id,)
        ).fetchone()[0]
    assert own_resolved == 1
    assert other_resolved == 0


def test_promise_abandon_auto_resolves_continuity_findings(service: NovelForgeService) -> None:
    _filled_book(service)
    _filled_chapter(service, "promise", 1)
    auto = _auto(service.root)

    promise = auto.add_promise(
        "promise", "abandon me", target_chapter_number=1, target_scene_ref="s1"
    )
    auto.add_promise_review_findings("promise", 1)
    auto.update_promise_status(
        "promise", promise.id, "abandoned", scene_ref="s1", resolution_note="no longer needed"
    )

    rows = _open_review_findings_for_chapter(service, "promise", 1)
    assert len(rows) == 0


def test_new_revision_supersedes_old_promise_finding(service: NovelForgeService) -> None:
    """A finding on an old revision is resolved when a new finding is created."""
    _filled_book(service)
    _filled_chapter(service, "promise", 1)
    auto = _auto(service.root)

    promise = auto.add_promise(
        "promise", "must resolve", target_chapter_number=1, target_scene_ref="s1"
    )

    # Create initial revision.
    body = service.root / "ch1.md"
    body.write_text("正文长段落。" * 200 + "结尾。\n", encoding="utf-8")
    service.write_revision("promise", 1, body)

    first_finding_ids = auto.add_promise_review_findings("promise", 1)
    assert len(first_finding_ids) == 1

    # Write a new revision and create findings again.
    body.write_text("新的正文长段落。" * 200 + "结尾。\n", encoding="utf-8")
    service.write_revision("promise", 1, body)

    second_finding_ids = auto.add_promise_review_findings("promise", 1)
    assert len(second_finding_ids) == 1
    assert second_finding_ids[0] != first_finding_ids[0]

    with sqlite3.connect(str(get_db_path(service.root))) as conn:
        conn.row_factory = sqlite3.Row
        old = conn.execute(
            "SELECT resolved FROM review_findings WHERE id = ?",
            (first_finding_ids[0],),
        ).fetchone()
        new = conn.execute(
            "SELECT resolved FROM review_findings WHERE id = ?",
            (second_finding_ids[0],),
        ).fetchone()
        assert old["resolved"] == 1
        assert new["resolved"] == 0
