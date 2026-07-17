"""Tests for the per-book Markdown-authoritative memory kernel."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from app.novel_forge.book_memory import (
    BookMemoryError,
    build_context_packet,
    memory_status,
    parse_memory_markdown,
    promote_candidate,
    rebuild_memory_index,
    record_candidate,
    render_memory_markdown,
)
from app.novel_forge.project_templates import init_book_project
from app.novel_forge.skill_adapter import main as adapter_main


def _json_output(capsys) -> dict:
    return json.loads(capsys.readouterr().out.strip())


def _make_book(tmp_path: Path, slug: str = "demo") -> Path:
    result = init_book_project(tmp_path, slug, "演示书", "现实悬疑")
    book_dir = Path(result["book_dir"])
    chapter = book_dir / "chapters" / "e01" / "ch-01" / "正文.md"
    chapter.parent.mkdir(parents=True, exist_ok=True)
    chapter.write_text("# 第一章\n\n陈拾还活着。\n", encoding="utf-8")
    chapter5 = book_dir / "chapters" / "e01" / "ch-05" / "正文.md"
    chapter5.parent.mkdir(parents=True, exist_ok=True)
    chapter5.write_text("# 第五章\n\n陈拾死在井边。\n", encoding="utf-8")
    return book_dir


def _metadata(kind: str, record_id: str, **overrides) -> dict:
    data = {
        "schema_version": 1,
        "id": record_id,
        "kind": kind,
        "status": "candidate",
        "tier": "hard",
        "salience": "medium",
        "chapter": 1,
        "source_path": "chapters/e01/ch-01/正文.md",
        "evidence": "第一章井边场景",
        "summary": "陈拾当前仍然活着。",
        "supersedes": None,
    }
    kind_fields = {
        "entity": {
            "name": "陈拾",
            "entity_type": "character",
            "aliases": ["小陈"],
        },
        "fact": {
            "subject": "char.chen-shi",
            "predicate": "life_state",
            "object": "alive",
            "valid_from": 1,
            "valid_to": None,
        },
        "event": {
            "event_type": "arrival",
            "participants": ["char.chen-shi"],
            "location": "place.old-well",
        },
        "knowledge": {
            "knower": "char.chen-shi",
            "proposition": "井底藏有尸骨",
            "knowledge_state": "suspected",
        },
        "promise": {
            "promise": "井底尸骨的身份需要揭示",
            "promise_status": "planted",
            "planted_chapter": 1,
            "target_chapter": 5,
            "resolved_chapter": None,
            "related_entities": ["char.chen-shi"],
        },
    }
    data.update(kind_fields[kind])
    data.update(overrides)
    return data


def _write_record(path: Path, metadata: dict, title: str = "记忆记录") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_memory_markdown(metadata, title=title), encoding="utf-8")


def test_memory_markdown_round_trip_and_validation(tmp_path: Path):
    metadata = _metadata("fact", "fact.chen-shi.life-state.ch01")
    text = render_memory_markdown(metadata, title="陈拾生存状态")

    record = parse_memory_markdown(text)

    assert record.id == metadata["id"]
    assert record.kind == "fact"
    assert record.data["object"] == "alive"
    assert parse_memory_markdown(render_memory_markdown(record)).data == record.data

    bad = dict(metadata, id="../outside")
    with pytest.raises(BookMemoryError, match="id"):
        parse_memory_markdown(render_memory_markdown(bad))

    missing = dict(metadata)
    del missing["predicate"]
    with pytest.raises(BookMemoryError, match="predicate"):
        parse_memory_markdown(render_memory_markdown(missing))


def test_memory_salience_defaults_for_legacy_records_and_validates_values():
    metadata = _metadata("fact", "fact.legacy")
    del metadata["salience"]

    record = parse_memory_markdown(render_memory_markdown(metadata))

    assert record.data["salience"] == "medium"
    with pytest.raises(BookMemoryError, match="salience"):
        render_memory_markdown({**metadata, "salience": "urgent"})


def test_record_candidate_rejects_source_path_escape(tmp_path: Path):
    _make_book(tmp_path)
    candidate = tmp_path / "candidate.md"
    _write_record(
        candidate,
        _metadata(
            "fact",
            "fact.escape",
            source_path="../outside.md",
        ),
    )

    with pytest.raises(BookMemoryError, match="source_path"):
        record_candidate(tmp_path, "demo", candidate)


def test_rebuild_index_covers_all_record_kinds_and_detects_staleness(tmp_path: Path):
    book_dir = _make_book(tmp_path)
    kinds = ("entity", "fact", "event", "knowledge", "promise")
    for kind in kinds:
        metadata = _metadata(kind, f"{kind}.one", status="canonical")
        _write_record(
            book_dir / "memory" / "canon" / f"{kind}s" / f"{kind}.one.md",
            metadata,
        )

    result = rebuild_memory_index(tmp_path, "demo")

    assert result["record_count"] == 5
    assert result["counts_by_kind"] == {kind: 1 for kind in kinds}
    assert (book_dir / ".novel-forge" / "index.sqlite3").exists()
    assert (book_dir / ".novel-forge" / "source-manifest.json").exists()
    assert memory_status(tmp_path, "demo")["state"] == "clean"

    db_path = book_dir / ".novel-forge" / "index.sqlite3"
    with sqlite3.connect(db_path) as conn:
        assert conn.execute("SELECT COUNT(*) FROM source_files").fetchone()[0] == 5
        assert conn.execute("SELECT COUNT(*) FROM facts").fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM promises").fetchone()[0] == 1

    fact_path = book_dir / "memory" / "canon" / "facts" / "fact.one.md"
    fact_path.write_text(
        fact_path.read_text(encoding="utf-8") + "\n人工补充说明。\n",
        encoding="utf-8",
    )
    status = memory_status(tmp_path, "demo")
    assert status["state"] == "stale"
    assert status["changed_sources"] == ["memory/canon/facts/fact.one.md"]


def test_source_prose_change_marks_index_stale(tmp_path: Path):
    book_dir = _make_book(tmp_path)
    _write_record(
        book_dir / "memory/canon/facts/fact.alive.md",
        _metadata("fact", "fact.alive", status="canonical"),
    )
    rebuild_memory_index(tmp_path, "demo")

    chapter = book_dir / "chapters/e01/ch-01/正文.md"
    chapter.write_text("# 第一章\n\n陈拾的状态被改写。\n", encoding="utf-8")

    status = memory_status(tmp_path, "demo")
    assert status["state"] == "stale"
    assert status["changed_evidence_sources"] == [
        "chapters/e01/ch-01/正文.md"
    ]


def test_rebuild_rejects_overlapping_canonical_facts(tmp_path: Path):
    book_dir = _make_book(tmp_path)
    _write_record(
        book_dir / "memory/canon/facts/fact.alive.md",
        _metadata("fact", "fact.alive", status="canonical", valid_from=1),
    )
    _write_record(
        book_dir / "memory/canon/facts/fact.dead.md",
        _metadata(
            "fact",
            "fact.dead",
            status="canonical",
            chapter=5,
            source_path="chapters/e01/ch-05/正文.md",
            object="dead",
            valid_from=5,
        ),
    )

    with pytest.raises(BookMemoryError, match="事实冲突"):
        rebuild_memory_index(tmp_path, "demo")


def test_promotion_blocks_overlapping_fact_without_supersedes(tmp_path: Path):
    book_dir = _make_book(tmp_path)
    _write_record(
        book_dir / "memory/canon/facts/fact.alive.md",
        _metadata(
            "fact",
            "fact.alive",
            status="canonical",
            valid_from=1,
            valid_to=None,
        ),
    )
    rebuild_memory_index(tmp_path, "demo")

    source = tmp_path / "dead-candidate.md"
    _write_record(
        source,
        _metadata(
            "fact",
            "fact.dead",
            chapter=5,
            source_path="chapters/e01/ch-05/正文.md",
            evidence="第五章井边死亡场景",
            summary="陈拾已经死亡。",
            object="dead",
            valid_from=5,
        ),
    )
    record_candidate(tmp_path, "demo", source)

    with pytest.raises(BookMemoryError, match="冲突"):
        promote_candidate(tmp_path, "demo", "fact.dead")


def test_explicit_supersession_closes_old_fact_and_rebuilds(tmp_path: Path):
    book_dir = _make_book(tmp_path)
    old_path = book_dir / "memory/canon/facts/fact.alive.md"
    _write_record(
        old_path,
        _metadata(
            "fact",
            "fact.alive",
            status="canonical",
            valid_from=1,
            valid_to=None,
        ),
    )
    old_path.write_text(
        old_path.read_text(encoding="utf-8") + "\n旧事实的人工说明必须保留。\n",
        encoding="utf-8",
    )
    rebuild_memory_index(tmp_path, "demo")

    source = tmp_path / "dead-candidate.md"
    _write_record(
        source,
        _metadata(
            "fact",
            "fact.dead",
            chapter=5,
            source_path="chapters/e01/ch-05/正文.md",
            evidence="第五章井边死亡场景",
            summary="陈拾已经死亡。",
            object="dead",
            valid_from=5,
            supersedes="fact.alive",
        ),
    )
    source.write_text(
        source.read_text(encoding="utf-8") + "\n死亡场景由作者人工确认。\n",
        encoding="utf-8",
    )
    candidate = record_candidate(tmp_path, "demo", source)
    result = promote_candidate(tmp_path, "demo", "fact.dead")

    assert candidate["candidate_path"] == "memory/candidates/ch05/fact.dead.md"
    assert result["canonical_path"] == "memory/canon/facts/fact.dead.md"
    assert result["index"]["record_count"] == 2
    assert memory_status(tmp_path, "demo")["state"] == "clean"

    old = parse_memory_markdown(old_path.read_text(encoding="utf-8"))
    assert old.data["valid_to"] == 4
    assert old.data["superseded_by"] == "fact.dead"
    assert "旧事实的人工说明必须保留" in old_path.read_text(encoding="utf-8")

    canonical_text = (book_dir / result["canonical_path"]).read_text(
        encoding="utf-8"
    )
    assert "死亡场景由作者人工确认" in canonical_text

    promoted_candidate = parse_memory_markdown(
        (book_dir / candidate["candidate_path"]).read_text(encoding="utf-8")
    )
    assert promoted_candidate.status == "promoted"
    assert promoted_candidate.data["canonical_path"] == result["canonical_path"]
    assert "死亡场景由作者人工确认" in (
        book_dir / candidate["candidate_path"]
    ).read_text(encoding="utf-8")


def test_context_packet_uses_time_valid_facts_and_due_promises(tmp_path: Path):
    book_dir = _make_book(tmp_path)
    _write_record(
        book_dir / "memory/canon/facts/fact.alive.md",
        _metadata(
            "fact",
            "fact.alive",
            status="canonical",
            valid_from=1,
            valid_to=4,
            superseded_by="fact.dead",
        ),
    )
    _write_record(
        book_dir / "memory/canon/facts/fact.dead.md",
        _metadata(
            "fact",
            "fact.dead",
            status="canonical",
            chapter=5,
            source_path="chapters/e01/ch-05/正文.md",
            object="dead",
            summary="陈拾已经死亡。",
            valid_from=5,
            supersedes="fact.alive",
        ),
    )
    _write_record(
        book_dir / "memory/canon/promises/promise.bones.md",
        _metadata("promise", "promise.bones", status="canonical", tier="active"),
    )
    rebuild_memory_index(tmp_path, "demo")

    packet = build_context_packet(tmp_path, "demo", 5)

    assert packet["context_path"] == "memory/context-cache/ch05-memory.md"
    assert packet["counts"]["facts"] == 1
    assert packet["counts"]["due_promises"] == 1
    text = (book_dir / packet["context_path"]).read_text(encoding="utf-8")
    assert "fact.dead" in text
    assert "fact.alive" not in text
    assert "promise.bones" in text
    assert "陈拾已经死亡" in text

    canon = book_dir / "memory/canon/facts/fact.dead.md"
    canon.write_text(canon.read_text(encoding="utf-8") + "\n变化。\n", encoding="utf-8")
    with pytest.raises(BookMemoryError, match="stale"):
        build_context_packet(tmp_path, "demo", 5)


def test_context_packet_prioritizes_salience_within_memory_sections(tmp_path: Path):
    book_dir = _make_book(tmp_path)
    _write_record(
        book_dir / "memory/canon/events/event.low.md",
        _metadata(
            "event",
            "event.low",
            status="canonical",
            tier="active",
            salience="low",
            summary="低显著性环境变化。",
        ),
    )
    _write_record(
        book_dir / "memory/canon/events/event.high.md",
        _metadata(
            "event",
            "event.high",
            status="canonical",
            tier="active",
            salience="high",
            summary="高显著性关系断裂。",
        ),
    )
    rebuild_memory_index(tmp_path, "demo")

    packet = build_context_packet(tmp_path, "demo", 5)
    text = (book_dir / packet["context_path"]).read_text(encoding="utf-8")

    assert text.index("event.high") < text.index("event.low")
    assert packet["counts"]["salience"]["high"] == 1


def test_memory_status_warns_when_one_chapter_is_over_recorded(tmp_path: Path):
    book_dir = _make_book(tmp_path)
    for number in range(16):
        source = tmp_path / f"candidate-{number}.md"
        _write_record(
            source,
            _metadata(
                "event",
                f"event.ch01.{number}",
                summary=f"候选事件 {number}。",
            ),
        )
        record_candidate(tmp_path, "demo", source)

    status = memory_status(tmp_path, "demo")

    assert status["candidate_records_by_chapter"]["1"] == 16
    assert status["volume_warnings"] == [
        {
            "chapter": 1,
            "candidate_records": 16,
            "canonical_records": 0,
            "threshold": 15,
            "warning": "memory_volume_high",
        }
    ]


def test_adapter_memory_operations_require_confirmation_and_hide_bodies(
    tmp_path: Path, capsys
):
    _make_book(tmp_path)
    source = tmp_path / "candidate.md"
    _write_record(source, _metadata("fact", "fact.adapter"))

    code = adapter_main(
        [
            "--root",
            str(tmp_path),
            "record-memory-candidate",
            "demo",
            "--file",
            str(source),
        ]
    )
    assert code == 0
    data = _json_output(capsys)
    assert data["ok"] is False
    assert data["error"]["code"] == "confirmation_required"

    code = adapter_main(
        [
            "--root",
            str(tmp_path),
            "--confirm",
            "record-memory-candidate",
            "record-memory-candidate",
            "demo",
            "--file",
            str(source),
        ]
    )
    assert code == 0
    data = _json_output(capsys)
    assert data["ok"] is True
    assert data["data"]["record_id"] == "fact.adapter"
    assert "陈拾当前仍然活着" not in json.dumps(data, ensure_ascii=False)

    code = adapter_main(["--root", str(tmp_path), "memory-status", "demo"])
    assert code == 0
    data = _json_output(capsys)
    assert data["ok"] is True
    assert data["data"]["candidate_count"] == 1
