"""Tests for vendor-neutral isolated writer capsules."""

from __future__ import annotations

import hashlib
import importlib
import importlib.util
import json
from pathlib import Path

import pytest

from app.novel_forge import book_project
from app.novel_forge.chapter_sequence import (
    begin_chapter_sequence,
    chapter_sequence_status,
    claim_chapter_session,
    invalidate_chapter_session,
)
from app.novel_forge.project_templates import init_book_project
from app.novel_forge.session_audit import (
    audit_session_log,
    evaluate_session_budget,
    record_runtime_audit,
)
from app.novel_forge.skill_adapter import main as adapter_main


def _guardian():
    spec = importlib.util.find_spec("app.novel_forge.guardian")
    assert spec is not None, "isolated writer guardian module is missing"
    return importlib.import_module("app.novel_forge.guardian")


def _book(root: Path) -> Path:
    init_book_project(root, "demo", "演示书", "现实悬疑")
    book_dir = root / "books" / "demo"
    (book_dir / "planning/scene-package-ch01.md").write_text(
        "# Scene Package\n\n"
        "## 1. 场景压力\n"
        "- 本章目标：主角必须决定是否开门。\n"
        "- 停止边界：门锁第一次转动后结束。\n",
        encoding="utf-8",
    )
    begin_chapter_sequence(
        root,
        "demo",
        start_chapter=1,
        chapter_count=1,
        sequence_id="seq-guardian",
    )
    claim_chapter_session(
        root,
        "demo",
        "seq-guardian",
        "native-writer-001",
    )
    return book_dir


def _runtime_snapshot(
    session_id: str,
    *,
    capsule_id: str | None = None,
) -> dict:
    payload = {
        "schema": "novel-forge-runtime/v1",
        "session_id": session_id,
        "scope": {"chapter_count": 1},
        "harness": {"name": "Generic Runner", "version": "1"},
        "model": {
            "provider": "generic-provider",
            "name": "generic-model",
            "reasoning_effort": "standard",
        },
        "timing": {"elapsed_seconds": 12.5},
        "usage": {
            "request_count": 2,
            "input_tokens": 100,
            "output_tokens": 200,
            "cached_input_tokens": 300,
            "total_tokens": 600,
            "max_request_context_tokens": 400,
            "context_reset_count": 0,
        },
        "tools": {
            "call_count": 1,
            "failure_count": 0,
            "by_name": {"write": 1},
        },
    }
    if capsule_id is not None:
        payload["guardian"] = {
            "capsule_id": capsule_id,
            "workspace_mode": "isolated_writer_capsule",
            "filesystem_scope": "capsule_only",
            "book_control_plane_visible": False,
            "validator_source_visible": False,
            "reported_by": "external_harness",
            "sandbox_implementation": "test-capsule-runner",
        }
    return payload


def _record_runtime_for_generation(
    book_dir: Path,
    runtime_path: Path,
    generation_id: str,
) -> None:
    report = audit_session_log(runtime_path)
    report["budget"] = evaluate_session_budget(report, chapter_count=1)
    report["provenance_mismatches"] = []
    report["provenance_status"] = "verified"
    report["generation_record_ids"] = [generation_id]
    record_runtime_audit(book_dir, report)


def _generation(chapter_path: Path) -> dict:
    return {
        "id": "generation.ch01.guardian",
        "chapter": 1,
        "writer_type": "agent",
        "run_id": "native-writer-001",
        "provider": "generic-provider",
        "model": "generic-model",
        "agent_harness": "Generic Runner/1",
        "reasoning_effort": "standard",
        "tool_failures": [],
        "content_path": "chapters/e01/ch-01/正文.md",
        "content_sha256": hashlib.sha256(chapter_path.read_bytes()).hexdigest(),
        "draft_write_count": 1,
        "draft_edit_count": 0,
        "review_call_count": 2,
    }


def _complete_capsule(
    guardian,
    root: Path,
    capsule: Path,
    prepared: dict,
    prose: str,
) -> dict:
    (capsule / "draft/正文.md").write_text(prose, encoding="utf-8")
    _record_runtime_sidecar(
        guardian,
        root,
        prepared,
        capsule.parent / "runtime-sidecars" / f"{prepared['capsule_id']}.json",
    )
    return guardian.ingest_writer_capsule(
        root,
        "demo",
        prepared["capsule_id"],
    )


def _record_runtime_sidecar(
    guardian,
    root: Path,
    prepared: dict,
    runtime_path: Path,
) -> Path:
    runtime_path.parent.mkdir(parents=True, exist_ok=True)
    runtime_path.write_text(
        json.dumps(
            _runtime_snapshot(
                prepared["session_id"],
                capsule_id=prepared["capsule_id"],
            ),
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    guardian.record_capsule_runtime(
        root,
        "demo",
        prepared["capsule_id"],
        runtime_path.resolve(),
    )
    return runtime_path


def test_guardian_contract_is_vendor_neutral_and_token_bounded():
    guardian = _guardian()

    contract = guardian.guardian_contract()

    assert contract["schema"] == "novel-forge-guardian-contract/v1"
    assert contract["workspace"]["mode"] == "isolated_writer_capsule"
    assert contract["workspace"]["book_control_plane_visible"] is False
    assert contract["workspace"]["validator_source_visible"] is False
    assert contract["outputs"]["allowed"] == ["draft/正文.md"]
    assert contract["runtime"]["record_operation"] == "record-capsule-runtime"
    assert contract["runtime"]["schema"] == "novel-forge-runtime/v1"
    assert contract["runtime"]["written_by"] == "external_harness"
    assert contract["runtime"]["writer_may_write_runtime_snapshot"] is False
    assert contract["runtime"]["full_transcript_required"] is False
    assert contract["token_policy"]["guardian_checks_use_model_context"] is False
    serialized = json.dumps(contract, ensure_ascii=False).lower()
    for vendor in ("claude", "deepseek", "minimax", "openai", "anthropic"):
        assert vendor not in serialized


def test_prepare_capsule_exposes_only_bounded_inputs(tmp_path: Path):
    guardian = _guardian()
    root = tmp_path / "repo"
    _book(root)
    capsule = tmp_path / "capsules" / "writer-001"

    result = guardian.prepare_writer_capsule(
        root,
        "demo",
        "seq-guardian",
        "native-writer-001",
        capsule,
        "chapters/e01/ch-01/正文.md",
    )

    assert result["chapter"] == 1
    assert result["capsule_dir"] == str(capsule.resolve())
    assert result["control_plane_exposed"] is False
    assert set(path.relative_to(capsule).as_posix() for path in capsule.rglob("*")) == {
        "capsule.json",
        "draft",
        "guardian-contract.json",
        "handoff.md",
    }
    assert not (capsule / ".git").exists()
    assert not (capsule / "planning").exists()
    assert not (capsule / "evidence").exists()
    assert not (capsule / "app").exists()
    assert len((capsule / "handoff.md").read_text(encoding="utf-8")) < 30_000


def test_ingest_capsule_imports_only_draft_and_records_clean_receipt(
    tmp_path: Path,
):
    guardian = _guardian()
    root = tmp_path / "repo"
    book_dir = _book(root)
    capsule = tmp_path / "capsules" / "writer-001"
    prepared = guardian.prepare_writer_capsule(
        root,
        "demo",
        "seq-guardian",
        "native-writer-001",
        capsule,
        "chapters/e01/ch-01/正文.md",
    )
    prose = "# 第一章\n\n" + "他把手放在门锁上。" * 900 + "\n"
    (capsule / "draft/正文.md").write_text(prose, encoding="utf-8")
    _record_runtime_sidecar(
        guardian,
        root,
        prepared,
        tmp_path / "runtime" / "clean.json",
    )

    result = guardian.ingest_writer_capsule(
        root,
        "demo",
        prepared["capsule_id"],
    )

    chapter = book_dir / "chapters/e01/ch-01/正文.md"
    assert chapter.read_text(encoding="utf-8") == prose
    assert result["status"] == "clean"
    assert result["body_sha256"] == hashlib.sha256(
        chapter.read_bytes()
    ).hexdigest()
    receipt_path = book_dir / result["receipt_path"]
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    assert receipt["schema"] == "novel-forge-guardian-receipt/v1"
    assert receipt["status"] == "clean"
    assert receipt["control_plane_exposed"] is False
    assert receipt["unexpected_files"] == []
    assert receipt["session_id"] == "native-writer-001"
    assert receipt["body_sha256"] == result["body_sha256"]


def test_unexpected_script_compromises_capsule_and_invalidates_session(
    tmp_path: Path,
):
    guardian = _guardian()
    root = tmp_path / "repo"
    book_dir = _book(root)
    capsule = tmp_path / "capsules" / "writer-001"
    prepared = guardian.prepare_writer_capsule(
        root,
        "demo",
        "seq-guardian",
        "native-writer-001",
        capsule,
        "chapters/e01/ch-01/正文.md",
    )
    (capsule / "draft/正文.md").write_text("# 第一章\n\n正文。\n", encoding="utf-8")
    (capsule / "fix_evidence.py").write_text("print('bypass')\n", encoding="utf-8")

    with pytest.raises(guardian.GuardianError, match="compromised"):
        guardian.ingest_writer_capsule(
            root,
            "demo",
            prepared["capsule_id"],
        )

    receipt_path = (
        book_dir
        / "evidence/guardian-receipts"
        / f"{prepared['capsule_id']}.json"
    )
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    assert receipt["status"] == "compromised"
    assert receipt["unexpected_files"] == ["fix_evidence.py"]
    assert not (book_dir / "chapters/e01/ch-01/正文.md").exists()
    sequence = chapter_sequence_status(
        root,
        "demo",
        "seq-guardian",
    )
    assert sequence["status"] == "awaiting_session"
    assert sequence["active_session_id"] is None
    assert sequence["used_session_ids"] == ["native-writer-001"]
    assert sequence["invalidated_session_count"] == 1


def test_missing_external_harness_isolation_attestation_compromises_capsule(
    tmp_path: Path,
):
    guardian = _guardian()
    root = tmp_path / "repo"
    book_dir = _book(root)
    capsule = tmp_path / "capsules" / "writer-001"
    prepared = guardian.prepare_writer_capsule(
        root,
        "demo",
        "seq-guardian",
        "native-writer-001",
        capsule,
        "chapters/e01/ch-01/正文.md",
    )
    (capsule / "draft/正文.md").write_text(
        "# 第一章\n\n正文。\n",
        encoding="utf-8",
    )
    runtime = tmp_path / "runtime" / "missing-attestation.json"
    runtime.parent.mkdir(parents=True, exist_ok=True)
    runtime.write_text(
        json.dumps(_runtime_snapshot("native-writer-001"), ensure_ascii=False),
        encoding="utf-8",
    )

    with pytest.raises(guardian.GuardianError, match="隔离证明"):
        guardian.record_capsule_runtime(
            root,
            "demo",
            prepared["capsule_id"],
            runtime.resolve(),
        )

    assert not (
        book_dir
        / "evidence/guardian-receipts"
        / f"{prepared['capsule_id']}.json"
    ).exists()


def test_inactive_session_capsule_cannot_arrive_late_and_replace_draft(
    tmp_path: Path,
):
    guardian = _guardian()
    root = tmp_path / "repo"
    book_dir = _book(root)
    capsule = tmp_path / "capsules" / "writer-001"
    prepared = guardian.prepare_writer_capsule(
        root,
        "demo",
        "seq-guardian",
        "native-writer-001",
        capsule,
        "chapters/e01/ch-01/正文.md",
    )
    invalidate_chapter_session(
        root,
        "demo",
        "seq-guardian",
        "native-writer-001",
        reason="external_harness_terminated",
    )
    (capsule / "draft/正文.md").write_text(
        "# 第一章\n\n迟到的正文。\n",
        encoding="utf-8",
    )
    _record_runtime_sidecar(
        guardian,
        root,
        prepared,
        tmp_path / "runtime" / "late.json",
    )

    with pytest.raises(guardian.GuardianError, match="compromised"):
        guardian.ingest_writer_capsule(
            root,
            "demo",
            prepared["capsule_id"],
        )

    receipt = json.loads(
        (
            book_dir
            / "evidence/guardian-receipts"
            / f"{prepared['capsule_id']}.json"
        ).read_text(encoding="utf-8")
    )
    assert "sequence_session_not_active" in receipt["reasons"]
    assert not (book_dir / "chapters/e01/ch-01/正文.md").exists()


def test_clean_receipt_must_match_current_generation_body(tmp_path: Path):
    guardian = _guardian()
    root = tmp_path / "repo"
    book_dir = _book(root)
    capsule = tmp_path / "capsules" / "writer-001"
    prepared = guardian.prepare_writer_capsule(
        root,
        "demo",
        "seq-guardian",
        "native-writer-001",
        capsule,
        "chapters/e01/ch-01/正文.md",
    )
    prose = "# 第一章\n\n" + "他把手放在门锁上。" * 900 + "\n"
    (capsule / "draft/正文.md").write_text(prose, encoding="utf-8")
    _record_runtime_sidecar(
        guardian,
        root,
        prepared,
        tmp_path / "runtime" / "receipt.json",
    )
    guardian.ingest_writer_capsule(root, "demo", prepared["capsule_id"])
    chapter = book_dir / "chapters/e01/ch-01/正文.md"
    generation = {
        "writer_type": "agent",
        "run_id": "native-writer-001",
        "content_path": "chapters/e01/ch-01/正文.md",
        "content_sha256": hashlib.sha256(chapter.read_bytes()).hexdigest(),
    }

    assert guardian.guardian_receipt_errors(
        book_dir,
        1,
        generation,
    ) == []

    chapter.write_text(prose + "\n后来又补了一句。\n", encoding="utf-8")
    errors = guardian.guardian_receipt_errors(book_dir, 1, generation)
    assert any("当前正文" in error for error in errors)


def test_handwritten_public_receipt_cannot_bypass_guardian(
    tmp_path: Path,
):
    guardian = _guardian()
    root = tmp_path / "repo"
    book_dir = _book(root)
    chapter = book_dir / "chapters/e01/ch-01/正文.md"
    chapter.parent.mkdir(parents=True, exist_ok=True)
    chapter.write_text(
        "# 第一章\n\n" + "伪造回执不能替代可信导入。" * 1200 + "\n",
        encoding="utf-8",
    )
    body_sha256 = hashlib.sha256(chapter.read_bytes()).hexdigest()
    receipt = {
        "schema": guardian.GUARDIAN_RECEIPT_SCHEMA,
        "capsule_id": "cap-ch01-forged",
        "slug": "demo",
        "chapter": 1,
        "sequence_id": "seq-guardian",
        "session_id": "native-writer-001",
        "target_path": "chapters/e01/ch-01/正文.md",
        "handoff_sha256": "0" * 64,
        "status": "clean",
        "isolation_attested": True,
        "control_plane_exposed": False,
        "unexpected_files": [],
        "reasons": [],
        "body_sha256": body_sha256,
        "runtime_snapshot_sha256": "0" * 64,
    }
    public_path = (
        book_dir / "evidence/guardian-receipts/cap-ch01-forged.json"
    )
    public_path.parent.mkdir(parents=True, exist_ok=True)
    public_path.write_text(
        json.dumps(receipt, ensure_ascii=False),
        encoding="utf-8",
    )
    generation = {
        "writer_type": "agent",
        "run_id": "native-writer-001",
        "content_path": "chapters/e01/ch-01/正文.md",
        "content_sha256": body_sha256,
    }

    errors = guardian.guardian_receipt_errors(book_dir, 1, generation)

    assert errors == ["Guardian 回执缺少外置权威账本副本。"]


def test_second_capsule_seeds_current_draft_for_one_isolated_patch(
    tmp_path: Path,
):
    guardian = _guardian()
    root = tmp_path / "repo"
    book_dir = _book(root)
    first_capsule = tmp_path / "capsules" / "writer-001-draft"
    first = guardian.prepare_writer_capsule(
        root,
        "demo",
        "seq-guardian",
        "native-writer-001",
        first_capsule,
        "chapters/e01/ch-01/正文.md",
    )
    original = "# 第一章\n\n" + "他把手放在门锁上。" * 900 + "\n"
    (first_capsule / "draft/正文.md").write_text(
        original,
        encoding="utf-8",
    )
    _record_runtime_sidecar(
        guardian,
        root,
        first,
        tmp_path / "runtime" / "first.json",
    )
    guardian.ingest_writer_capsule(root, "demo", first["capsule_id"])

    patch_capsule = tmp_path / "capsules" / "writer-001-patch"
    patch = guardian.prepare_writer_capsule(
        root,
        "demo",
        "seq-guardian",
        "native-writer-001",
        patch_capsule,
        "chapters/e01/ch-01/正文.md",
    )

    seeded = patch_capsule / "draft/正文.md"
    assert patch["operation"] == "patch"
    assert patch["input_body_sha256"] == hashlib.sha256(
        (
            book_dir / "chapters/e01/ch-01/正文.md"
        ).read_bytes()
    ).hexdigest()
    assert seeded.read_text(encoding="utf-8") == original

    revised = original.replace("门锁", "冰凉的门锁", 1)
    seeded.write_text(revised, encoding="utf-8")
    _record_runtime_sidecar(
        guardian,
        root,
        patch,
        tmp_path / "runtime" / "patch.json",
    )
    result = guardian.ingest_writer_capsule(
        root,
        "demo",
        patch["capsule_id"],
    )

    assert result["operation"] == "patch"
    chapter = book_dir / "chapters/e01/ch-01/正文.md"
    assert chapter.read_text(
        encoding="utf-8"
    ) == revised
    generation = {
        "writer_type": "agent",
        "run_id": "native-writer-001",
        "content_path": "chapters/e01/ch-01/正文.md",
        "content_sha256": hashlib.sha256(chapter.read_bytes()).hexdigest(),
    }
    assert guardian.guardian_receipt_errors(book_dir, 1, generation) == []


def test_third_distinct_body_requires_prior_human_authorization(
    tmp_path: Path,
):
    guardian = _guardian()
    root = tmp_path / "repo"
    _book(root)
    target = "chapters/e01/ch-01/正文.md"

    first_capsule = tmp_path / "capsules" / "draft"
    first = guardian.prepare_writer_capsule(
        root,
        "demo",
        "seq-guardian",
        "native-writer-001",
        first_capsule,
        target,
    )
    _complete_capsule(
        guardian,
        root,
        first_capsule,
        first,
        "# 第一章\n\n" + "初稿。" * 2000 + "\n",
    )

    second_capsule = tmp_path / "capsules" / "patch"
    second = guardian.prepare_writer_capsule(
        root,
        "demo",
        "seq-guardian",
        "native-writer-001",
        second_capsule,
        target,
    )
    _complete_capsule(
        guardian,
        root,
        second_capsule,
        second,
        "# 第一章\n\n" + "集中修订稿。" * 1200 + "\n",
    )

    with pytest.raises(guardian.GuardianError, match="human_decision_required"):
        guardian.prepare_writer_capsule(
            root,
            "demo",
            "seq-guardian",
            "native-writer-001",
            tmp_path / "capsules" / "unauthorized-third",
            target,
        )

    authorization = guardian.authorize_regeneration(
        root,
        "demo",
        "seq-guardian",
        "native-writer-001",
        authority="author",
        decision_reference="decision://author/ch01-third-body",
    )
    authorized = guardian.prepare_writer_capsule(
        root,
        "demo",
        "seq-guardian",
        "native-writer-001",
        tmp_path / "capsules" / "authorized-third",
        target,
        regeneration_authorization_id=authorization["authorization_id"],
    )
    assert authorized["human_regeneration_authorized"] is True
    assert (
        authorized["human_decision_reference"]
        == "decision://author/ch01-third-body"
    )
    assert (
        authorized["regeneration_authorization_id"]
        == authorization["authorization_id"]
    )


def test_tampered_regeneration_authorization_is_rejected(tmp_path: Path):
    guardian = _guardian()
    root = tmp_path / "repo"
    _book(root)
    target = "chapters/e01/ch-01/正文.md"
    for name, prose in (
        ("draft", "初稿。"),
        ("patch", "集中修订稿。"),
    ):
        capsule = tmp_path / "capsules" / name
        prepared = guardian.prepare_writer_capsule(
            root,
            "demo",
            "seq-guardian",
            "native-writer-001",
            capsule,
            target,
        )
        _complete_capsule(
            guardian,
            root,
            capsule,
            prepared,
            "# 第一章\n\n" + prose * 2000 + "\n",
        )
    authorization = guardian.authorize_regeneration(
        root,
        "demo",
        "seq-guardian",
        "native-writer-001",
        authority="human_delegate",
        decision_reference="decision://delegate/ch01-third-body",
    )
    path = (
        root
        / ".local-guardian/demo/authorizations"
        / f"{authorization['authorization_id']}.json"
    )
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["decision_reference"] = "decision://tampered"
    path.write_text(
        json.dumps(payload, ensure_ascii=False),
        encoding="utf-8",
    )

    with pytest.raises(guardian.GuardianError, match="不匹配"):
        guardian.prepare_writer_capsule(
            root,
            "demo",
            "seq-guardian",
            "native-writer-001",
            tmp_path / "capsules" / "tampered-auth",
            target,
            regeneration_authorization_id=authorization["authorization_id"],
        )


def test_newer_capsule_supersedes_older_prepared_capsule(
    tmp_path: Path,
):
    guardian = _guardian()
    root = tmp_path / "repo"
    book_dir = _book(root)
    target = "chapters/e01/ch-01/正文.md"

    first_capsule = tmp_path / "capsules" / "draft"
    first = guardian.prepare_writer_capsule(
        root,
        "demo",
        "seq-guardian",
        "native-writer-001",
        first_capsule,
        target,
    )
    _complete_capsule(
        guardian,
        root,
        first_capsule,
        first,
        "# 第一章\n\n" + "初稿。" * 2000 + "\n",
    )

    second_capsule = tmp_path / "capsules" / "patch"
    second = guardian.prepare_writer_capsule(
        root,
        "demo",
        "seq-guardian",
        "native-writer-001",
        second_capsule,
        target,
    )
    newer_capsule = tmp_path / "capsules" / "newer"
    guardian.prepare_writer_capsule(
        root,
        "demo",
        "seq-guardian",
        "native-writer-001",
        newer_capsule,
        target,
    )

    with pytest.raises(guardian.GuardianError, match="superseded"):
        _record_runtime_sidecar(
            guardian,
            root,
            second,
            tmp_path / "runtime" / "superseded.json",
        )

    control = json.loads(
        (
            book_dir
            / "planning/guardian-sessions"
            / f"{second['capsule_id']}.json"
        ).read_text(encoding="utf-8")
    )
    assert control["status"] == "superseded"


def test_patch_capsule_rejects_target_changed_after_prepare(tmp_path: Path):
    guardian = _guardian()
    root = tmp_path / "repo"
    book_dir = _book(root)
    target = "chapters/e01/ch-01/正文.md"
    first_capsule = tmp_path / "capsules" / "draft"
    first = guardian.prepare_writer_capsule(
        root,
        "demo",
        "seq-guardian",
        "native-writer-001",
        first_capsule,
        target,
    )
    _complete_capsule(
        guardian,
        root,
        first_capsule,
        first,
        "# 第一章\n\n" + "初稿。" * 2000 + "\n",
    )
    patch_capsule = tmp_path / "capsules" / "patch"
    patch = guardian.prepare_writer_capsule(
        root,
        "demo",
        "seq-guardian",
        "native-writer-001",
        patch_capsule,
        target,
    )
    chapter = book_dir / target
    chapter.write_text(
        "# 第一章\n\n" + "控制面中的正文已经变化。" * 1200 + "\n",
        encoding="utf-8",
    )
    (patch_capsule / "draft/正文.md").write_text(
        "# 第一章\n\n" + "基于旧版本完成的补丁。" * 1200 + "\n",
        encoding="utf-8",
    )
    _record_runtime_sidecar(
        guardian,
        root,
        patch,
        tmp_path / "runtime" / "stale-patch.json",
    )

    with pytest.raises(guardian.GuardianError, match="target_changed"):
        guardian.ingest_writer_capsule(root, "demo", patch["capsule_id"])

    receipt = json.loads(
        (
            book_dir
            / "evidence/guardian-receipts"
            / f"{patch['capsule_id']}.json"
        ).read_text(encoding="utf-8")
    )
    assert "target_changed_since_prepare" in receipt["reasons"]


def test_runtime_ready_integrity_requires_clean_guardian_receipt(
    tmp_path: Path,
):
    root = tmp_path / "repo"
    book_dir = _book(root)
    chapter = book_dir / "chapters/e01/ch-01/正文.md"
    chapter.parent.mkdir(parents=True, exist_ok=True)
    chapter.write_text("# 第一章\n\n" + "正文。" * 2000 + "\n", encoding="utf-8")
    runtime = tmp_path / "runtime-direct.json"
    runtime.write_text(
        json.dumps(_runtime_snapshot("native-writer-001"), ensure_ascii=False),
        encoding="utf-8",
    )
    generation = _generation(chapter)
    _record_runtime_for_generation(book_dir, runtime, generation["id"])

    errors = book_project._runtime_audit_errors(book_dir, generation)

    assert any("Guardian" in error for error in errors)


def test_runtime_ready_integrity_accepts_matching_capsule_receipt(
    tmp_path: Path,
):
    guardian = _guardian()
    root = tmp_path / "repo"
    book_dir = _book(root)
    capsule = tmp_path / "capsules" / "writer-001"
    prepared = guardian.prepare_writer_capsule(
        root,
        "demo",
        "seq-guardian",
        "native-writer-001",
        capsule,
        "chapters/e01/ch-01/正文.md",
    )
    (capsule / "draft/正文.md").write_text(
        "# 第一章\n\n" + "正文。" * 2000 + "\n",
        encoding="utf-8",
    )
    runtime = _record_runtime_sidecar(
        guardian,
        root,
        prepared,
        tmp_path / "runtime" / "ready.json",
    )
    guardian.ingest_writer_capsule(root, "demo", prepared["capsule_id"])
    chapter = book_dir / "chapters/e01/ch-01/正文.md"
    generation = _generation(chapter)
    _record_runtime_for_generation(book_dir, runtime, generation["id"])

    assert book_project._runtime_audit_errors(book_dir, generation) == []


def test_adapter_exposes_guardian_capsule_without_prose(
    tmp_path: Path,
    capsys,
):
    root = tmp_path / "repo"
    _book(root)
    capsule = tmp_path / "capsules" / "writer-001"

    code = adapter_main(
        [
            "--root",
            str(root.resolve()),
            "guardian-contract",
        ]
    )
    contract = json.loads(capsys.readouterr().out)
    assert code == 0
    assert contract["ok"] is True
    assert contract["data"]["workspace"]["book_control_plane_visible"] is False

    code = adapter_main(
        [
            "--root",
            str(root.resolve()),
            "prepare-writer-capsule",
            "demo",
            "seq-guardian",
            "--session-id",
            "native-writer-001",
            "--capsule-dir",
            str(capsule.resolve()),
            "--target-path",
            "chapters/e01/ch-01/正文.md",
        ]
    )
    denied = json.loads(capsys.readouterr().out)
    assert code == 0
    assert denied["error"]["code"] == "confirmation_required"

    code = adapter_main(
        [
            "--root",
            str(root.resolve()),
            "--confirm",
            "prepare-writer-capsule",
            "prepare-writer-capsule",
            "demo",
            "seq-guardian",
            "--session-id",
            "native-writer-001",
            "--capsule-dir",
            str(capsule.resolve()),
            "--target-path",
            "chapters/e01/ch-01/正文.md",
        ]
    )
    prepared = json.loads(capsys.readouterr().out)
    assert code == 0
    assert prepared["ok"] is True
    serialized = json.dumps(prepared, ensure_ascii=False)
    assert "本次 writer scope" not in serialized
    assert "Scene Package" not in serialized
    assert prepared["data"]["control_plane_exposed"] is False


def test_control_plane_bypass_sample_is_sanitized_and_actionable():
    sample_path = (
        Path(__file__).parents[1]
        / "docs/examples/agent-demo-v43-claude-deepseek-control-plane-bypass.json"
    )
    sample = json.loads(sample_path.read_text(encoding="utf-8"))

    assert sample["sample"]["chapter_count"] == 5
    assert sample["sample"]["workflow_truth"]["effective_integrity"] == "blocked"
    assert sample["external_observation"]["required_for_future_formal_runs"] is False
    assert sample["protocol_decision"]["architecture"].startswith(
        "vendor-neutral"
    )
    assert sample["privacy"]["full_raw_prose_stored"] is False
    assert sample["privacy"]["raw_reasoning_stored"] is False
    assert sample["cleanup"]["source_projects_removed"] is True
    assert sample["cleanup"]["external_book_git_histories_removed"] is True
