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


def filled_scene_contract_v4(path: Path) -> None:
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
        "## spatial_layout_and_routes\n"
        "The hero stands with her back to the locked door; the broken window is to her left, "
        "three paces away, with a shard-strewn ledge between her and the drop.\n\n"
        "## body_state_and_contacts\n"
        "She is barefoot, shirt torn at the shoulder, left hand pressed against the wall to steady herself.\n\n"
        "## object_affordances\n"
        "- rusty key → can open the back door if she reaches it; cannot help with the window → "
        "action changes when she realizes the key is in the other room\n"
        "- broken window → can be climbed through; cannot be opened quietly → "
        "action changes when the noise alerts the pursuers\n\n"
        "## environmental_constraints\n"
        "The floor is wet, so every quick step risks a slip; the slip forces her to grab the ledge, "
        "which exposes her to the window light.\n\n"
        "## embodied_action_chain\n"
        "- foot touches wet floor → she shifts weight → floor squeaks under the boards\n"
        "- hand finds the lock → key turns halfway → metal jams and the shaft bends\n"
        "- shoulder hits the window frame → glass cracks → cut palm makes her lose grip on the bag\n\n"
        "---\n\n"
        "contract_version: 4\n",
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
    # Existing approval-oriented tests use this helper to satisfy all independent
    # editorial gates. The dedicated Blind Experience tests exercise that gate
    # separately and do not use this helper when proving memo-only failure.
    blind = svc.blind_experience_status(slug, number)
    if not blind.passes:
        current = svc.get_current_revision(slug, number)
        revision_text = (svc.root / current.file_path).read_text(encoding="utf-8")

        def evidence_spans(text: str) -> list[str]:
            spans: list[str] = []
            for width in range(6, min(len(text), 24) + 1):
                for start in range(len(text) - width + 1):
                    candidate = text[start : start + width]
                    if candidate != candidate.strip() or candidate in spans:
                        continue
                    spans.append(candidate)
                    if len(spans) == 3:
                        return spans
            return spans

        evidence = evidence_spans(revision_text)
        if len(evidence) < 3:
            # Approval tests sometimes use a four-character placeholder body.
            # Expand only that test fixture; production evidence rules stay strict.
            source = svc.root / f".ready-memo-{slug}-{number}.md"
            source.write_text(
                revision_text.rstrip()
                + "\n\nThe chair blocks the door. Her knee presses the desk. "
                + "One hand locks the window.\n",
                encoding="utf-8",
            )
            try:
                svc.write_revision(slug, number, source)
                svc.lint_chapter(slug, number)
            finally:
                source.unlink(missing_ok=True)
            current = svc.get_current_revision(slug, number)
            revision_text = (svc.root / current.file_path).read_text(encoding="utf-8")
            evidence = evidence_spans(revision_text)

        assert len(evidence) == 3
        svc.submit_blind_experience_review(
            slug,
            number,
            spatial_reconstruction="The prose establishes a bounded room with a door and reachable objects.",
            body_position_and_contact="The character contacts the immediate setting rather than floating in abstraction.",
            action_constraints="The setting constrains the available action and forces a concrete choice.",
            emotional_trajectory="Pressure becomes visible through the character's action.",
            dialogue_dynamics="Any spoken line changes the immediate action or resistance.",
            memorable_images=[
                {"location": "current revision", "evidence": evidence[0], "reader_image": "the bounded room"},
                {"location": "current revision", "evidence": evidence[1], "reader_image": "the physical obstacle"},
                {"location": "current revision", "evidence": evidence[2], "reader_image": "the consequential action"},
            ],
            knowledge_gaps=[],
            verdict="experience_reconstructable",
            blocking_issues=[],
        )

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
