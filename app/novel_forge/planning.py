"""Voice Bible, Scene Contract, Drafting Readiness, and Drafting Packet.

Extracted from service.py as a mixin. Expects self._conn(), self.root,
and path helpers from the inheriting NovelForgeService.
"""

import hashlib
import json
import shutil
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.novel_forge.export import hash_text, now_iso
from app.novel_forge.models import (
    DraftingPacket,
    DraftingReadiness,
    NovelForgeError,
    SceneContract,
    SceneContractRevision,
    VoiceBible,
    VoiceBibleRevision,
)
from app.novel_forge.readiness import (
    count_concrete_anchors,
    count_valid_list_items,
    detect_contract_version,
    has_causal_chain,
    is_missing_content,
    is_parameter_only_spatial_layout,
    parse_markdown_sections,
)
from app.novel_forge.repository import (
    AuditRepository,
    BookRepository,
    ChapterRepository,
    FactRepository,
    PromiseRepository,
    RevisionRepository,
    SceneContractRepository,
    VoiceBibleRepository,
)


class PlanningMixin:
    """Voice Bible, Scene Contract, Drafting Readiness, and Drafting Packet."""

    @staticmethod
    def _voice_bible_template(title: str) -> str:
        return (
            f"# Voice Bible：{title}\n\n"
            "## 叙述距离 (narrative_distance)\n\n"
            "## 时态/时间处理 (tense_or_time_handling)\n\n"
            "## 视角焦点与禁止越界 (focalization)\n\n"
            "## 句长、段落节奏 (sentence_rhythm)\n\n"
            "## 人物对白差异与禁忌 (dialogue_rules)\n\n"
            "## 感官/意象偏好 (sensory_palette)\n\n"
            "## 本书禁用套路、解释腔、陈词滥调 (taboo_patterns)\n\n"
            "## 情绪克制规则 (emotional_restraint)\n\n"
            "## 正反例说明 (exemplar_notes)\n\n"
            "---\n\n"
            f"updated_at: {datetime.now(timezone.utc).isoformat()}\n"
            "revision_note: initial template\n"
        )

    @staticmethod
    def _scene_contract_template(number: int, title: str) -> str:
        return (
            f"# 第 {number} 章场景合同：{title}\n\n"
            "## scene_question\n"
            "本场读者想知道什么？\n\n"
            "## viewpoint_character\n\n"
            "## present_want\n\n"
            "## opposing_force\n\n"
            "## irreversible_turn\n\n"
            "## cost_or_tradeoff\n\n"
            "## information_change\n\n"
            "## emotional_shift\n\n"
            "## concrete_anchor\n"
            "- 锚点 1：\n"
            "- 锚点 2：\n\n"
            "## entry_late_exit_early_note\n\n"
            "## continuity_dependencies\n\n"
            "## forbidden_easy_moves\n\n"
            "## ending_pressure\n\n"
            "## character_blindspot_or_pressure\n"
            "待填写\n\n"
            "## irreversible_choice\n"
            "待填写\n\n"
            "## choice_consequence\n"
            "待填写\n\n"
            "## detail_payoff_plan\n"
            "待填写\n\n"
            "## scene_necessity\n"
            "待填写\n\n"
            "## ending_change\n"
            "待填写\n\n"
            "## spatial_layout_and_routes\n"
            "待填写\n\n"
            "## body_state_and_contacts\n"
            "待填写\n\n"
            "## object_affordances\n"
            "- 物体 1：可做什么 / 不可做什么 / 何时改变行动\n"
            "- 物体 2：可做什么 / 不可做什么 / 何时改变行动\n\n"
            "## environmental_constraints\n"
            "待填写\n\n"
            "## embodied_action_chain\n"
            "- 第一步：感知/接触 → 动作 → 环境反馈/代价\n"
            "- 第二步：感知/接触 → 动作 → 环境反馈/代价\n"
            "- 第三步：感知/接触 → 动作 → 环境反馈/代价\n\n"
            "---\n\n"
            "contract_version: 4\n"
        )

    # ------------------------------------------------------------------
    # External source validation (reused by voice-bible / scene-contract writes)
    # ------------------------------------------------------------------
    def _validate_external_source(self, from_file: Path) -> Path:
        from_file = Path(from_file)
        if not from_file.is_absolute():
            raise NovelForgeError("Source file must be an absolute path.")
        resolved = from_file.resolve()
        if not resolved.exists():
            raise NovelForgeError(f"Source file not found: {from_file}")
        try:
            resolved.read_bytes().decode("utf-8-sig")
        except UnicodeDecodeError as exc:
            raise NovelForgeError(
                f"Source file is not valid UTF-8: {from_file} ({exc})"
            )
        library_root = (self.root / "library").resolve()
        try:
            resolved.relative_to(library_root)
            is_inside = True
        except ValueError:
            is_inside = False
        if is_inside:
            raise NovelForgeError(
                "Source file must not be inside the project library directory."
            )
        return resolved

    # ------------------------------------------------------------------
    # Voice Bible
    # ------------------------------------------------------------------
    def get_voice_bible(self, slug: str) -> VoiceBible:
        with self._conn() as conn:
            book = BookRepository.get_by_slug(conn, slug)
            if book is None:
                raise NovelForgeError(f"Book not found: {slug}")
            current = VoiceBibleRepository.get_current(conn, book["id"])
            if current is None:
                return VoiceBible(book_id=book["id"], exists=False)
            rev = None
            if current["current_revision_id"]:
                rev = VoiceBibleRepository.get_revision(
                    conn, current["current_revision_id"]
                )
            return VoiceBible(
                book_id=book["id"],
                exists=True,
                current_revision_id=current["current_revision_id"],
                current_revision_number=rev["revision_number"] if rev else None,
                current_file_path=current["current_file_path"],
                current_hash=current["current_hash"],
                updated_at=current["updated_at"],
            )

    def write_voice_bible(
        self, slug: str, from_file: Path, note: str | None = None
    ) -> VoiceBible:
        resolved = self._validate_external_source(from_file)
        content_hash = self._hash_file(resolved)

        with self._conn() as conn:
            book = BookRepository.get_by_slug(conn, slug)
            if book is None:
                raise NovelForgeError(f"Book not found: {slug}")

            revs_dir = self._voice_bible_revisions_dir(slug)
            revs_dir.mkdir(parents=True, exist_ok=True)
            revision_number = VoiceBibleRepository.get_next_revision_number(
                conn, book["id"]
            )
            ts = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
            dest_name = f"{revision_number:04d}-{ts}-{content_hash[:16]}.md"
            dest_path = revs_dir / dest_name
            shutil.copy2(resolved, dest_path)

            rev_id = VoiceBibleRepository.create_revision(
                conn,
                book_id=book["id"],
                revision_number=revision_number,
                file_path=str(dest_path.relative_to(self.root)),
                content_hash=content_hash,
                note=note,
            )
            VoiceBibleRepository.update_current(
                conn,
                book_id=book["id"],
                revision_id=rev_id,
                file_path=str(dest_path.relative_to(self.root)),
                content_hash=content_hash,
            )
            AuditRepository.add(
                conn,
                book_id=book["id"],
                entity_type="voice_bible",
                entity_id=rev_id,
                action="write",
                details=json.dumps(
                    {"revision_id": rev_id, "revision_number": revision_number},
                    ensure_ascii=False,
                ),
            )
        # Read back after the transaction commits so the current pointer is
        # visible to a fresh connection.
        return self.get_voice_bible(slug)

    # ------------------------------------------------------------------
    # Scene Contract v2
    # ------------------------------------------------------------------
    def get_scene_contract(self, slug: str, number: int) -> SceneContract:
        with self._conn() as conn:
            book = BookRepository.get_by_slug(conn, slug)
            if book is None:
                raise NovelForgeError(f"Book not found: {slug}")
            chapter = ChapterRepository.get_by_book_and_number(conn, book["id"], number)
            if chapter is None:
                raise NovelForgeError(f"Chapter {number} not found in book {slug}.")
            current = SceneContractRepository.get_current(conn, chapter["id"])
            if current is None:
                return SceneContract(chapter_id=chapter["id"], exists=False)
            rev = None
            if current["current_revision_id"]:
                rev = SceneContractRepository.get_revision(
                    conn, current["current_revision_id"]
                )
            return SceneContract(
                chapter_id=chapter["id"],
                exists=True,
                current_revision_id=current["current_revision_id"],
                current_revision_number=rev["revision_number"] if rev else None,
                current_file_path=current["current_file_path"],
                current_hash=current["current_hash"],
                updated_at=current["updated_at"],
            )

    def write_scene_contract(
        self, slug: str, number: int, from_file: Path, note: str | None = None
    ) -> SceneContract:
        resolved = self._validate_external_source(from_file)
        content_hash = self._hash_file(resolved)

        with self._conn() as conn:
            book = BookRepository.get_by_slug(conn, slug)
            if book is None:
                raise NovelForgeError(f"Book not found: {slug}")
            chapter = ChapterRepository.get_by_book_and_number(conn, book["id"], number)
            if chapter is None:
                raise NovelForgeError(f"Chapter {number} not found in book {slug}.")

            revs_dir = self._scene_contract_revisions_dir(slug, number)
            revs_dir.mkdir(parents=True, exist_ok=True)
            revision_number = SceneContractRepository.get_next_revision_number(
                conn, chapter["id"]
            )
            ts = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
            dest_name = f"{revision_number:04d}-{ts}-{content_hash[:16]}.md"
            dest_path = revs_dir / dest_name
            shutil.copy2(resolved, dest_path)

            rev_id = SceneContractRepository.create_revision(
                conn,
                chapter_id=chapter["id"],
                revision_number=revision_number,
                file_path=str(dest_path.relative_to(self.root)),
                content_hash=content_hash,
                note=note,
            )
            SceneContractRepository.update_current(
                conn,
                chapter_id=chapter["id"],
                revision_id=rev_id,
                file_path=str(dest_path.relative_to(self.root)),
                content_hash=content_hash,
            )
            AuditRepository.add(
                conn,
                book_id=book["id"],
                entity_type="scene_contract",
                entity_id=rev_id,
                action="write",
                details=json.dumps(
                    {
                        "chapter_id": chapter["id"],
                        "revision_id": rev_id,
                        "revision_number": revision_number,
                    },
                    ensure_ascii=False,
                ),
            )
        # Read back after the transaction commits so the current pointer is
        # visible to a fresh connection.
        return self.get_scene_contract(slug, number)

    # ------------------------------------------------------------------
    # Reader Review Ledger
    # ------------------------------------------------------------------
    _VALID_READER_REVIEW_LENS = {
        "immersion",
        "causality",
        "character_truth",
        "tension",
        "language",
        "continuity",
    }
    def assess_drafting_readiness(
        self, slug: str, number: int
    ) -> DraftingReadiness:
        """Assess whether a chapter has sufficient preparation for drafting.

        Read-only: no state changes, no audit events, no file writes.
        """
        with self._conn() as conn:
            book = BookRepository.get_by_slug(conn, slug)
            if book is None:
                raise NovelForgeError(f"Book not found: {slug}")
            chapter = ChapterRepository.get_by_book_and_number(
                conn, book["id"], number
            )
            if chapter is None:
                raise NovelForgeError(f"Chapter {number} not found in book {slug}.")

            blockers: list[dict[str, str | None]] = []
            warnings: list[dict[str, str | None]] = []

            # Voice Bible metadata.
            vb_current = VoiceBibleRepository.get_current(conn, book["id"])
            vb_metadata = VoiceBible(
                book_id=book["id"],
                exists=vb_current is not None,
                current_revision_id=vb_current["current_revision_id"]
                if vb_current
                else None,
                current_revision_number=None,
                current_file_path=vb_current["current_file_path"]
                if vb_current
                else None,
                current_hash=vb_current["current_hash"] if vb_current else None,
                updated_at=vb_current["updated_at"] if vb_current else None,
            )

            # Scene Contract metadata.
            sc_current = SceneContractRepository.get_current(conn, chapter["id"])
            sc_metadata = SceneContract(
                chapter_id=chapter["id"],
                exists=sc_current is not None,
                current_revision_id=sc_current["current_revision_id"]
                if sc_current
                else None,
                current_revision_number=None,
                current_file_path=sc_current["current_file_path"]
                if sc_current
                else None,
                current_hash=sc_current["current_hash"] if sc_current else None,
                updated_at=sc_current["updated_at"] if sc_current else None,
            )

            # Voice Bible checks.
            required_voice_bible = {
                "narrative_distance",
                "focalization",
                "sentence_rhythm",
                "dialogue_rules",
                "taboo_patterns",
                "emotional_restraint",
            }
            if vb_current is None:
                blockers.append(
                    {
                        "code": "voice_bible_missing",
                        "asset": "voice_bible",
                        "field": None,
                        "message": "Voice Bible has not been created.",
                    }
                )
            else:
                vb_path = self.root / vb_current["current_file_path"]
                if not vb_path.exists():
                    blockers.append(
                        {
                            "code": "voice_bible_file_missing",
                            "asset": "voice_bible",
                            "field": None,
                            "message": "Voice Bible file is missing.",
                        }
                    )
                else:
                    vb_text = vb_path.read_text(encoding="utf-8")
                    vb_sections = {
                        section.key: section for section in parse_markdown_sections(vb_text)
                    }
                    for key in required_voice_bible:
                        section = vb_sections.get(key)
                        if section is None:
                            blockers.append(
                                {
                                    "code": f"voice_bible_missing_{key}",
                                    "asset": "voice_bible",
                                    "field": key,
                                    "message": f"Voice Bible section '{key}' is missing.",
                                }
                            )
                        elif is_missing_content(section.content):
                            blockers.append(
                                {
                                    "code": f"voice_bible_empty_{key}",
                                    "asset": "voice_bible",
                                    "field": key,
                                    "message": f"Voice Bible section '{key}' is empty or placeholder.",
                                }
                            )

            # Scene Contract checks.
            required_scene_contract = [
                "scene_question",
                "viewpoint_character",
                "present_want",
                "opposing_force",
                "irreversible_turn",
                "cost_or_tradeoff",
                "information_change",
                "emotional_shift",
                "concrete_anchor",
                "forbidden_easy_moves",
                "ending_pressure",
            ]
            required_scene_contract_v3 = [
                "character_blindspot_or_pressure",
                "irreversible_choice",
                "choice_consequence",
                "detail_payoff_plan",
                "scene_necessity",
                "ending_change",
            ]
            required_scene_contract_v4 = [
                "spatial_layout_and_routes",
                "body_state_and_contacts",
                "object_affordances",
                "environmental_constraints",
                "embodied_action_chain",
            ]
            if sc_current is None:
                blockers.append(
                    {
                        "code": "scene_contract_missing",
                        "asset": "scene_contract",
                        "field": None,
                        "message": "Scene Contract has not been created.",
                    }
                )
            else:
                sc_path = self.root / sc_current["current_file_path"]
                if not sc_path.exists():
                    blockers.append(
                        {
                            "code": "scene_contract_file_missing",
                            "asset": "scene_contract",
                            "field": None,
                            "message": "Scene Contract file is missing.",
                        }
                    )
                else:
                    sc_text = sc_path.read_text(encoding="utf-8")
                    sc_sections = {
                        section.key: section
                        for section in parse_markdown_sections(sc_text)
                    }
                    contract_version = detect_contract_version(sc_text)
                    if contract_version < 3:
                        warnings.append(
                            {
                                "code": "scene_contract_legacy_v2",
                                "asset": "scene_contract",
                                "field": None,
                                "message": (
                                    "Scene Contract is v2. Narrative editorial gate "
                                    "expects v3 fields but will not block existing work."
                                ),
                            }
                        )
                    if contract_version < 4:
                        warnings.append(
                            {
                                "code": "scene_contract_upgrade_to_v4",
                                "asset": "scene_contract",
                                "field": None,
                                "message": (
                                    "Scene Contract is below v4. Consider upgrading to v4 "
                                    "to include the embodied scene model."
                                ),
                            }
                        )
                    checked_fields = list(required_scene_contract)
                    if contract_version >= 3:
                        checked_fields.extend(required_scene_contract_v3)
                    if contract_version >= 4:
                        checked_fields.extend(required_scene_contract_v4)
                    for key in checked_fields:
                        section = sc_sections.get(key)
                        if section is None:
                            blockers.append(
                                {
                                    "code": f"scene_contract_missing_{key}",
                                    "asset": "scene_contract",
                                    "field": key,
                                    "message": f"Scene Contract section '{key}' is missing.",
                                }
                            )
                            continue
                        if key == "concrete_anchor":
                            anchor_count = count_concrete_anchors(section.content)
                            if anchor_count < 2:
                                blockers.append(
                                    {
                                        "code": "scene_contract_insufficient_anchors",
                                        "asset": "scene_contract",
                                        "field": key,
                                        "message": (
                                            f"Scene Contract 'concrete_anchor' needs at least "
                                            f"2 non-placeholder anchors (found {anchor_count})."
                                        ),
                                    }
                                )
                            continue
                        if key in required_scene_contract_v4:
                            if is_missing_content(section.content):
                                blockers.append(
                                    {
                                        "code": f"scene_contract_empty_{key}",
                                        "asset": "scene_contract",
                                        "field": key,
                                        "message": f"Scene Contract section '{key}' is empty or placeholder.",
                                    }
                                )
                                continue
                            if key == "spatial_layout_and_routes" and is_parameter_only_spatial_layout(
                                section.content
                            ):
                                blockers.append(
                                    {
                                        "code": "scene_contract_spatial_layout_parameter_only",
                                        "asset": "scene_contract",
                                        "field": key,
                                        "message": (
                                            "Scene Contract 'spatial_layout_and_routes' "
                                            "appears to list dimensions/parameters without "
                                            "relative positions or passable routes."
                                        ),
                                    }
                                )
                            elif key == "object_affordances":
                                affordance_count = count_valid_list_items(section.content)
                                if affordance_count < 2:
                                    blockers.append(
                                        {
                                            "code": "scene_contract_insufficient_object_affordances",
                                            "asset": "scene_contract",
                                            "field": key,
                                            "message": (
                                                f"Scene Contract 'object_affordances' needs "
                                                f"at least 2 valid items (found {affordance_count})."
                                            ),
                                        }
                                    )
                                elif affordance_count > 5:
                                    blockers.append(
                                        {
                                            "code": "scene_contract_too_many_object_affordances",
                                            "asset": "scene_contract",
                                            "field": key,
                                            "message": (
                                                f"Scene Contract 'object_affordances' allows at "
                                                f"most 5 valid items (found {affordance_count})."
                                            ),
                                        }
                                    )
                            elif key == "environmental_constraints" and not has_causal_chain(
                                section.content
                            ):
                                blockers.append(
                                    {
                                        "code": "scene_contract_environmental_constraint_no_causal_chain",
                                        "asset": "scene_contract",
                                        "field": key,
                                        "message": (
                                            "Scene Contract 'environmental_constraints' "
                                            "needs at least one causal chain."
                                        ),
                                    }
                                )
                            elif key == "embodied_action_chain":
                                chain_count = count_valid_list_items(section.content)
                                if chain_count < 3:
                                    blockers.append(
                                        {
                                            "code": "scene_contract_insufficient_embodied_action_chain",
                                            "asset": "scene_contract",
                                            "field": key,
                                            "message": (
                                                f"Scene Contract 'embodied_action_chain' needs "
                                                f"at least 3 valid items (found {chain_count})."
                                            ),
                                        }
                                    )
                            continue
                        if is_missing_content(section.content):
                            blockers.append(
                                {
                                    "code": f"scene_contract_empty_{key}",
                                    "asset": "scene_contract",
                                    "field": key,
                                    "message": f"Scene Contract section '{key}' is empty or placeholder.",
                                }
                            )

            ready = len(blockers) == 0
            return DraftingReadiness(
                ready=ready,
                blockers=blockers,
                warnings=warnings,
                voice_bible_metadata=vb_metadata,
                scene_contract_metadata=sc_metadata,
            )

    # ------------------------------------------------------------------
    # Drafting Packet
    # ------------------------------------------------------------------
    def build_drafting_packet(
        self,
        slug: str,
        number: int,
        output_file: Path,
        note: str | None = None,
        previous_context_chars: int = 1200,
        allow_incomplete: bool = False,
    ) -> DraftingPacket:
        """Build an external Markdown drafting packet for a chapter.

        The packet is a human/Skill-readable context document written outside
        the library. It never modifies chapter state or creates a revision.
        """
        output_file = Path(output_file)
        if not output_file.is_absolute():
            raise NovelForgeError("output_file must be an absolute path.")
        if not (0 <= previous_context_chars <= 4000):
            raise NovelForgeError(
                "previous_context_chars must be between 0 and 4000."
            )

        resolved = output_file.resolve()
        if resolved.exists():
            raise NovelForgeError(f"output_file already exists: {output_file}")

        library_root = (self.root / "library").resolve()
        try:
            resolved.relative_to(library_root)
            is_inside_library = True
        except ValueError:
            is_inside_library = False
        if is_inside_library:
            raise NovelForgeError(
                "output_file must not be inside the project library directory."
            )

        # Drafting readiness gate.
        readiness = self.assess_drafting_readiness(slug, number)
        if not readiness.ready and not allow_incomplete:
            blocker_codes = [b["code"] for b in readiness.blockers]
            raise NovelForgeError(
                f"Drafting readiness gate blocked: {', '.join(blocker_codes)}"
            )

        with self._conn() as conn:
            book = BookRepository.get_by_slug(conn, slug)
            if book is None:
                raise NovelForgeError(f"Book not found: {slug}")
            chapter = ChapterRepository.get_by_book_and_number(
                conn, book["id"], number
            )
            if chapter is None:
                raise NovelForgeError(f"Chapter {number} not found in book {slug}.")

            # Scene Contract is mandatory.
            sc_current = SceneContractRepository.get_current(conn, chapter["id"])
            if sc_current is None:
                raise NovelForgeError(
                    f"Chapter {number} has no scene contract; cannot build packet."
                )
            sc_path = self.root / sc_current["current_file_path"]
            if not sc_path.exists():
                raise NovelForgeError(
                    f"Scene contract file missing: {sc_current['current_file_path']}"
                )
            scene_contract_text = sc_path.read_text(encoding="utf-8")

            # Voice Bible is optional; include full text or explicit MISSING.
            vb_current = VoiceBibleRepository.get_current(conn, book["id"])
            voice_bible_text: str | None = None
            if vb_current is not None and vb_current["current_file_path"]:
                vb_path = self.root / vb_current["current_file_path"]
                if vb_path.exists():
                    voice_bible_text = vb_path.read_text(encoding="utf-8")

            # Current revision metadata (if any).
            current_rev = None
            current_rev_number = None
            if chapter["current_revision_id"]:
                current_rev = RevisionRepository.get_by_id(
                    conn, chapter["current_revision_id"]
                )
                current_rev_number = current_rev["revision_number"] if current_rev else None

            # Approved canon facts scoped to this book.
            canon_rows = FactRepository.list_canon_by_book(conn, book["id"])

            # Unfulfilled promises relevant to this chapter (RTCO P2 layer).
            promise_rows = PromiseRepository.list_open_by_book(conn, book["id"])
            promise_reminders = self._categorize_promise_reminders(
                promise_rows, chapter["number"]
            )

            # Predecessor context: only the immediately previous chapter,
            # only if approved and has a revision.
            predecessor_text: str | None = None
            if previous_context_chars > 0 and number > 1:
                prev_chapter = ChapterRepository.get_by_book_and_number(
                    conn, book["id"], number - 1
                )
                if (
                    prev_chapter is not None
                    and prev_chapter["state"] == "approved"
                    and prev_chapter["current_revision_id"]
                ):
                    prev_rev = RevisionRepository.get_by_id(
                        conn, prev_chapter["current_revision_id"]
                    )
                    if prev_rev is not None:
                        prev_path = self.root / prev_rev["file_path"]
                        if prev_path.exists():
                            full_text = prev_path.read_text(encoding="utf-8")
                            predecessor_text = full_text[-previous_context_chars:]

        packet = self._build_packet_markdown(
            book=book,
            chapter=chapter,
            current_rev_number=current_rev_number,
            voice_bible_text=voice_bible_text,
            voice_bible_hash=vb_current["current_hash"] if vb_current else None,
            scene_contract_text=scene_contract_text,
            scene_contract_hash=sc_current["current_hash"],
            canon_rows=canon_rows,
            promise_reminders=promise_reminders,
            predecessor_text=predecessor_text,
            note=note,
            previous_context_chars=previous_context_chars,
            readiness=readiness,
            allow_incomplete=allow_incomplete,
        )

        resolved.parent.mkdir(parents=True, exist_ok=True)
        resolved.write_text(packet, encoding="utf-8")
        content_hash = self._hash_file(resolved)

        # External drafting packets may live outside the project root. Store a
        # root-relative path when possible, otherwise the absolute path.
        try:
            output_file_recorded = str(resolved.relative_to(self.root))
        except ValueError:
            output_file_recorded = str(resolved)

        with self._conn() as conn:
            AuditRepository.add(
                conn,
                book_id=book["id"],
                entity_type="drafting_packet",
                entity_id=chapter["id"],
                action="build",
                details=json.dumps(
                    {
                        "chapter_id": chapter["id"],
                        "output_file": output_file_recorded,
                        "output_hash": content_hash,
                        "note": note,
                        "previous_context_chars": previous_context_chars,
                    },
                    ensure_ascii=False,
                ),
            )

        return DraftingPacket(
            file_path=output_file_recorded,
            absolute_path=str(resolved),
            content_hash=content_hash,
            book_slug=slug,
            chapter_number=number,
            chapter_title=chapter["title"],
            current_revision_id=chapter["current_revision_id"],
        )

    def _categorize_promise_reminders(
        self,
        promise_rows: list[sqlite3.Row],
        chapter_number: int,
    ) -> list[dict[str, Any]]:
        """Categorize open promises for the RTCO P2 layer.

        This mirrors the logic in AutonomousWritingService.build_promise_reminders
        so that the drafting packet can include continuity reminders without
        depending on the experimental autonomous layer.
        """
        reminders: list[dict[str, Any]] = []
        for row in promise_rows:
            target = row["target_chapter_number"]
            if target is None:
                category = "unscoped"
            elif target < chapter_number:
                category = "overdue"
            elif target == chapter_number:
                category = "must_resolve"
            else:
                continue

            if category == "must_resolve":
                message = (
                    f"Promise (ID {row['id']}) is scheduled for this chapter "
                    f"and is still {row['status']}."
                )
            elif category == "overdue":
                message = (
                    f"Promise (ID {row['id']}) was scheduled for chapter {target} "
                    f"but is still {row['status']}."
                )
            else:
                message = (
                    f"Promise (ID {row['id']}) has no target chapter and is still "
                    f"{row['status']}."
                )

            reminders.append(
                {
                    "promise_id": row["id"],
                    "promise_text": row["promise_text"],
                    "status": row["status"],
                    "category": category,
                    "target_chapter_number": target,
                    "target_scene_ref": row["target_scene_ref"],
                    "message": message,
                }
            )
        return reminders

    def _build_packet_markdown(
        self,
        book: sqlite3.Row,
        chapter: sqlite3.Row,
        current_rev_number: int | None,
        voice_bible_text: str | None,
        voice_bible_hash: str | None,
        scene_contract_text: str,
        scene_contract_hash: str | None,
        canon_rows: list[sqlite3.Row],
        promise_reminders: list[dict[str, Any]],
        predecessor_text: str | None,
        note: str | None,
        previous_context_chars: int,
        readiness: DraftingReadiness,
        allow_incomplete: bool,
    ) -> str:
        now = datetime.now(timezone.utc).isoformat()
        lines: list[str] = []
        lines.append(
            f"# Drafting Packet: {book['title']} — Chapter {chapter['number']}: {chapter['title']}"
        )
        lines.append("")

        if allow_incomplete and not readiness.ready:
            lines.append("> **READINESS BYPASSED**")
            lines.append("> This packet was generated despite the following blockers:")
            for blocker in readiness.blockers:
                lines.append(f"> - `{blocker['code']}`: {blocker['message']}")
            lines.append("")

        lines.append("## Metadata")
        lines.append(f"- readiness_ready: {readiness.ready}")
        lines.append(f"- readiness_bypassed: {allow_incomplete and not readiness.ready}")
        lines.append(f"- readiness_blocker_count: {len(readiness.blockers)}")
        lines.append(f"- built_at: {now}")
        lines.append(f"- book_slug: {book['slug']}")
        lines.append(f"- book_title: {book['title']}")
        lines.append(f"- chapter_number: {chapter['number']}")
        lines.append(f"- chapter_title: {chapter['title']}")
        lines.append(f"- chapter_state: {chapter['state']}")
        lines.append(f"- current_revision_id: {chapter['current_revision_id']}")
        lines.append(f"- current_revision_number: {current_rev_number}")
        lines.append(f"- note: {note or ''}")
        lines.append("- source_hashes:")
        if voice_bible_hash:
            lines.append(f"  - voice_bible_hash: {voice_bible_hash}")
        else:
            lines.append("  - voice_bible_hash: MISSING")
        lines.append(f"  - scene_contract_hash: {scene_contract_hash or 'MISSING'}")
        lines.append("")

        sc_sections = {
            section.key: section
            for section in parse_markdown_sections(scene_contract_text)
        }

        lines.append("## Writer Operating Contract")
        lines.append(
            "- Write only this scene. Do not advance past the boundary set by the Scene Contract."
        )
        lines.append(
            "- Show the scene through action, dialogue, and concrete sensory detail. Do not explain or summarize for the reader."
        )
        lines.append(
            "- Do not decide a character's emotions in authorial voice; let actions and perceptions carry the feeling."
        )
        lines.append(
            "- 数字/术语必须落到身体接触、相对位置、可操作物与受阻动作中，不得用参数替代画面。"
        )
        lines.append(
            "- Do not paste this packet's instructions or metadata into the prose draft."
        )
        lines.append(
            "- Do not label the output as 'human-written' or claim human authorship automatically."
        )
        lines.append(
            "- When finished, produce a separate UTF-8 Markdown draft file outside the library for review; do not write it into the manuscript revisions directly."
        )
        lines.append("")

        # ------------------------------------------------------------------
        # P0 — Core: must-follow constraints for this scene.
        # ------------------------------------------------------------------
        lines.append("## P0 — Core (must follow)")
        lines.append("")

        lines.append("### Scene Contract")
        lines.append(scene_contract_text)
        lines.append("")

        lines.append("### Scene Embodiment Model")
        lines.append(
            "Summarized from the Scene Contract embodied fields. "
            "Missing fields are marked 'not specified'. "
            "Do not use external planning knowledge to infer them; "
            "upgrade the Scene Contract before drafting. "
            "In allow-incomplete exploration mode, the gap must remain visible "
            "and be addressed in the next revision."
        )
        lines.append("")
        embodied_fields = [
            "spatial_layout_and_routes",
            "body_state_and_contacts",
            "object_affordances",
            "environmental_constraints",
            "embodied_action_chain",
        ]
        exploration_mode = allow_incomplete and not readiness.ready
        for key in embodied_fields:
            section = sc_sections.get(key)
            if section and not is_missing_content(section.content):
                lines.append(f"#### {section.title}")
                lines.append(section.content)
                lines.append("")
            else:
                if exploration_mode:
                    lines.append(
                        f"- **{key}**: not specified — exploration mode; "
                        f"do not infer, fix before final draft."
                    )
                else:
                    lines.append(
                        f"- **{key}**: not specified — do not infer; "
                        f"upgrade the Scene Contract with this field."
                    )
                lines.append("")

        lines.append("### Chapter Goal")
        lines.append("Extracted from the Scene Contract:")
        lines.append("")
        goal_found = False
        for key in ("scene_question", "present_want"):
            section = sc_sections.get(key)
            if section and not is_missing_content(section.content):
                lines.append(f"- **{key}**: {section.content.strip()}")
                goal_found = True
        if not goal_found:
            lines.append(
                "- No explicit `scene_question` / `present_want` found; follow the Scene Contract directly."
            )
        lines.append("")

        if predecessor_text is not None:
            lines.append(
                f"### Predecessor Context (approved chapter {chapter['number'] - 1}, last {previous_context_chars} characters)"
            )
            lines.append(
                "This is a continuity hand-off fragment. Do not copy it verbatim; use it to maintain voice and causal thread."
            )
            lines.append("```")
            lines.append(predecessor_text)
            lines.append("```")
            lines.append("")

        # ------------------------------------------------------------------
        # P1 — Important context: book-level assets scoped as tightly as possible.
        # ------------------------------------------------------------------
        lines.append("## P1 — Important Context")
        lines.append("")

        lines.append("### Voice Bible")
        if voice_bible_text:
            lines.append(voice_bible_text)
        else:
            lines.append("**MISSING**: No Voice Bible has been written for this book.")
        lines.append("")

        lines.append("### Approved Canon Facts")
        lines.append(
            "Book-wide approved facts (conservative fallback; chapter-level character/relationship filtering is not yet implemented)."
        )
        lines.append("")
        if canon_rows:
            for row in canon_rows:
                lines.append(f"#### {row['subject']} {row['predicate']}")
                lines.append(f"- object: {row['object']}")
                lines.append(f"- evidence: {row['evidence']}")
                lines.append(f"- source_chapter_id: {row['chapter_id']}")
                lines.append(f"- source_revision_id: {row['revision_id']}")
                lines.append("")
        else:
            lines.append("No approved canon facts for this book.")
            lines.append("")

        # ------------------------------------------------------------------
        # P2 — Reference: unfulfilled promises / foreshadows relevant to this chapter.
        # ------------------------------------------------------------------
        lines.append("## P2 — Reference: Unfulfilled Promises / Foreshadows")
        lines.append(
            "> These reminders are continuity signals only. They do not auto-approve anything and must be reviewed by a human/editor."
        )
        lines.append("")
        if promise_reminders:
            for category, title in (
                ("must_resolve", "Must Resolve This Chapter"),
                ("overdue", "Overdue From Earlier Chapters"),
                ("unscoped", "Unscoped / No Target Chapter"),
            ):
                cat_reminders = [r for r in promise_reminders if r["category"] == category]
                if not cat_reminders:
                    continue
                lines.append(f"#### {title}")
                for r in cat_reminders:
                    lines.append(
                        f"- ID:{r['promise_id']} | `{r['status']}` | {r['promise_text']}"
                    )
                    target = r["target_chapter_number"]
                    scene = r["target_scene_ref"] or "unspecified"
                    if target is not None:
                        lines.append(f"  - target: chapter {target}, scene {scene}")
                    lines.append(f"  - {r['message']}")
                lines.append("")
        else:
            lines.append("No unfulfilled promises flagged for this chapter.")
            lines.append("")

        lines.append("## Delivery Checklist")
        lines.append(
            "After completing the draft, verify the following before handing it to lint/review:"
        )
        lines.append("- [ ] The scene answers the `scene_question` from the Scene Contract.")
        lines.append("- [ ] The `irreversible_turn` has happened and cannot be undone.")
        lines.append("- [ ] The `cost_or_tradeoff` is present or implied through action.")
        lines.append("- [ ] The `ending_pressure` is left intact for the next scene.")
        lines.append(
            "- [ ] 开场能定位身体与关键物体；身体的姿态、接触面与空间位置在读者脑中可定位。"
        )
        lines.append(
            "- [ ] 至少一项环境约束真实改变动作；环境不仅是背景，而是让某个动作受阻、变慢、暴露或付出代价。"
        )
        lines.append(
            "- [ ] 不可逆选择由连续身体动作触发，而非摘要宣布；让读者在身体动作链中意识到选择已发生。"
        )
        lines.append(
            "- [ ] Checking these boxes does not guarantee quality; human/editor review remains the gate."
        )
        lines.append("")

        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Rollback
    # ------------------------------------------------------------------
