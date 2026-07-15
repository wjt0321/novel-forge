"""Shared test helpers for Novel Forge."""

from pathlib import Path

import pytest

from app.novel_forge.service import NovelForgeService


def filled_voice_bible(path: Path) -> None:
    path.write_text(
        "# Voice Bible\n\n"
        "## narrative_distance\nclose-third limited\n\n"
        "## tense_or_time_handling\npast\n\n"
        "## focalization\nhero only\n\n"
        "## sentence_rhythm\nshort in action\n\n"
        "## dialogue_rules\nno tags\n\n"
        "## sensory_palette\nsmell and sound\n\n"
        "## taboo_patterns\nno info-dumps\n\n"
        "## emotional_restraint\nshow don't tell\n\n"
        "## exemplar_notes\nnone\n",
        encoding="utf-8",
    )


def filled_scene_contract_v3(path: Path) -> None:
    path.write_text(
        "# Scene Contract\n\n"
        "## scene_question\nCan she escape?\n\n"
        "## viewpoint_character\nhero\n\n"
        "## present_want\nget out\n\n"
        "## opposing_force\nlocked door\n\n"
        "## irreversible_turn\ndoor locks\n\n"
        "## cost_or_tradeoff\nleave the bag\n\n"
        "## information_change\nshe knows\n\n"
        "## emotional_shift\nhope to fear\n\n"
        "## concrete_anchor\n- rusty key\n- broken window\n\n"
        "## entry_late_exit_early_note\nlate\n\n"
        "## continuity_dependencies\nnone\n\n"
        "## forbidden_easy_moves\ncalling police\n\n"
        "## ending_pressure\npursuers close\n\n"
        "## character_blindspot_or_pressure\nher pride won't let her beg for help\n\n"
        "## irreversible_choice\nshe chooses to break the window instead of waiting\n\n"
        "## choice_consequence\nshe loses her last clean escape and cuts her hand\n\n"
        "## detail_payoff_plan\n- rusty key → opens the back door in scene 12\n\n"
        "## scene_necessity\nlosing the bag forces her to confront her hoarding guilt\n\n"
        "## ending_change\nshe is no longer a passive victim; she has blood on her hands\n\n"
        "---\n\n"
        "contract_version: 3\n",
        encoding="utf-8",
    )


def ready_memo(
    svc: NovelForgeService,
    slug: str,
    number: int,
    verdict: str = "ready_for_editor_decision",
    blocking_issues: list[dict] | None = None,
) -> int:
    """Submit a valid editorial memo for the current revision."""
    memo = svc.submit_editorial_memo(
        slug,
        number,
        narrative_necessity="This chapter is necessary because it forces the protagonist to act rather than wait.",
        character_agency="She chooses to break the window; alternative is surrender; cost is a cut hand and lost alibi.",
        detail_selection="rusty key (functional), broken window (irreversible), blood (consequence).",
        causal_chain="locked door → refusal to wait → broken window → cut hand → active escape.",
        prose_observation="S1 行动段落节奏有效；选择瞬间通过窗框碎裂展示。若未来精修，可将个别解释句进一步改为动作。",
        verdict=verdict,
        blocking_issues=blocking_issues or [],
    )
    return memo.id


@pytest.fixture
def service(tmp_path: Path) -> NovelForgeService:
    return NovelForgeService(tmp_path)
