from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.novel_forge.models import NovelForgeError
from app.novel_forge.workflow_observability import (
    record_call_observation,
    sanitize_call_telemetry,
    workflow_cost_summary,
)


def _observation(
    action_id: str,
    *,
    role: str,
    purpose: str,
    input_tokens: int | None,
    output_tokens: int | None,
    elapsed_seconds: float | None,
    retry_index: int = 0,
    revision_round: int = 0,
    changed: bool | None = False,
    effect: str = "none",
    scopes: dict[str, int] | None = None,
    texture_risk: str = "low",
) -> dict:
    before = {
        "sha256": "1" * 64,
        "cjk_chars": 5000,
        "literary_texture_risk": "low",
    }
    after = {
        "sha256": "2" * 64,
        "cjk_chars": 5100,
        "literary_texture_risk": texture_risk,
    }
    if changed is False:
        after = dict(before)
    if changed is None:
        before = None
        after = None
    return {
        "action_id": action_id,
        "chapter": 1,
        "role": role,
        "purpose": purpose,
        "action_kind": "run_role",
        "outcome": "completed",
        "started_at": "2026-07-31T01:00:00+00:00",
        "completed_at": "2026-07-31T01:00:10+00:00",
        "provider": "provider",
        "model": "model",
        "technical_retry_index": retry_index,
        "revision_round": revision_round,
        "telemetry": {
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "cached_input_tokens": None,
            "total_tokens": (
                input_tokens + output_tokens
                if input_tokens is not None and output_tokens is not None
                else None
            ),
            "request_count": 1 if input_tokens is not None else None,
            "elapsed_seconds": elapsed_seconds,
            "elapsed_source": "host_telemetry" if elapsed_seconds is not None else "unknown",
            "warnings": [],
        },
        "body_before": before,
        "body_after": after,
        "body_changed": changed,
        "must_scope_counts": scopes
        or {"local": 0, "structural": 0, "blocking": 0, "unclassified": 0},
        "workflow_effect": effect,
    }


def test_sanitize_call_telemetry_keeps_unknowns_null_and_never_raises():
    telemetry = sanitize_call_telemetry(
        {
            "input_tokens": "bad",
            "output_tokens": 300,
            "cached_input_tokens": -1,
            "total_tokens": None,
            "request_count": True,
            "elapsed_seconds": "2.5",
        }
    )

    assert telemetry["input_tokens"] is None
    assert telemetry["output_tokens"] == 300
    assert telemetry["cached_input_tokens"] is None
    assert telemetry["request_count"] is None
    assert telemetry["elapsed_seconds"] == 2.5
    assert telemetry["elapsed_source"] == "host_telemetry"
    assert telemetry["warnings"] == [
        "input_tokens_invalid",
        "cached_input_tokens_invalid",
        "request_count_invalid",
    ]


def test_call_observation_is_write_once_and_idempotent(tmp_path: Path):
    observation = _observation(
        "native-action-001",
        role="writer",
        purpose="draft",
        input_tokens=100,
        output_tokens=6000,
        elapsed_seconds=10,
        changed=True,
    )

    first = record_call_observation(tmp_path, "demo", observation)
    second = record_call_observation(tmp_path, "demo", observation)

    assert second == first
    path = (
        tmp_path
        / ".local-guardian/demo/workflow-observations/ch01/native-action-001.json"
    )
    assert json.loads(path.read_text(encoding="utf-8"))["slug"] == "demo"

    changed = dict(observation)
    changed["model"] = "other-model"
    with pytest.raises(NovelForgeError, match="不得覆盖"):
        record_call_observation(tmp_path, "demo", changed)


def test_workflow_cost_summary_aggregates_phases_retries_and_scope_samples(
    tmp_path: Path,
):
    records = [
        _observation(
            "draft",
            role="writer",
            purpose="draft",
            input_tokens=100,
            output_tokens=5000,
            elapsed_seconds=20,
            changed=True,
        ),
        _observation(
            "blind-1",
            role="blind-reader",
            purpose="review",
            input_tokens=5100,
            output_tokens=300,
            elapsed_seconds=5,
            scopes={"local": 1, "structural": 0, "blocking": 0, "unclassified": 0},
        ),
        _observation(
            "editor-1",
            role="chapter-editor",
            purpose="review",
            input_tokens=None,
            output_tokens=None,
            elapsed_seconds=None,
            retry_index=1,
            scopes={"local": 0, "structural": 1, "blocking": 0, "unclassified": 0},
            effect="revision_requested",
            texture_risk="high",
            changed=True,
        ),
        _observation(
            "patch",
            role="writer",
            purpose="patch",
            input_tokens=900,
            output_tokens=250,
            elapsed_seconds=4,
            revision_round=1,
            changed=True,
        ),
        _observation(
            "blind-2",
            role="blind-reader",
            purpose="review",
            input_tokens=5200,
            output_tokens=200,
            elapsed_seconds=5,
            revision_round=1,
        ),
    ]
    for record in records:
        record_call_observation(tmp_path, "demo", record)

    summary = workflow_cost_summary(tmp_path, "demo", chapter=1)
    chapter = summary["chapters"][0]

    assert summary["selected_chapters"] == [1]
    assert chapter["call_count"] == 5
    assert chapter["phases"]["writer_draft"]["total_tokens"] == 5100
    assert chapter["phases"]["initial_review"]["call_count"] == 2
    assert chapter["phases"]["initial_review"]["unknown_token_calls"] == 1
    assert chapter["phases"]["patch"]["body_change_count"] == 1
    assert chapter["phases"]["patch"]["known_token_share"] == round(1150 / 17050, 4)
    assert chapter["phases"]["re_review"]["total_tokens"] == 5400
    assert chapter["retry_overlay"]["call_count"] == 1
    assert chapter["must_scope_counts"] == {
        "local": 1,
        "structural": 1,
        "blocking": 0,
        "unclassified": 0,
    }
    assert chapter["workflow_effect_counts"]["revision_requested"] == 1
    assert chapter["literary_texture_risk_counts"] == {
        "low": 4,
        "medium": 0,
        "high": 1,
        "unknown": 0,
    }
    assert summary["totals"]["literary_texture_risk_counts"] == {
        "low": 4,
        "medium": 0,
        "high": 1,
        "unknown": 0,
    }
    assert summary["author_approval"] is False
    assert summary["publication_eligibility"] is False


def test_invalid_texture_risk_is_normalized_to_unknown(tmp_path: Path):
    observation = _observation(
        "draft-texture-unknown",
        role="writer",
        purpose="draft",
        input_tokens=1,
        output_tokens=1,
        elapsed_seconds=1,
        changed=True,
        texture_risk="not-a-risk",
    )

    stored = record_call_observation(tmp_path, "demo", observation)
    summary = workflow_cost_summary(tmp_path, "demo", chapter=1)

    assert stored["body_after"]["literary_texture_risk"] == "unknown"
    assert summary["chapters"][0]["literary_texture_risk_counts"] == {
        "low": 0,
        "medium": 0,
        "high": 0,
        "unknown": 1,
    }



def test_workflow_cost_summary_defaults_to_most_recent_chapters(tmp_path: Path):
    for chapter in range(1, 8):
        observation = _observation(
            f"draft-{chapter}",
            role="writer",
            purpose="draft",
            input_tokens=chapter,
            output_tokens=chapter,
            elapsed_seconds=chapter,
            changed=True,
        )
        observation["chapter"] = chapter
        record_call_observation(tmp_path, "demo", observation)

    summary = workflow_cost_summary(tmp_path, "demo", recent_chapters=3)

    assert summary["selected_chapters"] == [5, 6, 7]
    assert [item["chapter"] for item in summary["chapters"]] == [5, 6, 7]

def test_workflow_observability_rejects_slug_path_escape(tmp_path: Path):
    with pytest.raises(NovelForgeError, match="slug"):
        workflow_cost_summary(tmp_path, "../escape")

    observation = _observation(
        "safe-action",
        role="writer",
        purpose="draft",
        input_tokens=1,
        output_tokens=1,
        elapsed_seconds=1,
        changed=True,
    )
    with pytest.raises(NovelForgeError, match="slug"):
        record_call_observation(tmp_path, "../escape", observation)
