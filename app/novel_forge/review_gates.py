"""Reader Review, Blind Experience, and Editorial Memo gates.

Extracted from service.py as a mixin. Expects self._conn(), self.root,
and path helpers from the inheriting NovelForgeService.
"""

import difflib
import hashlib
import json
import re
import sqlite3
from pathlib import Path
from typing import Any

from app.novel_forge.models import (
    BlindExperienceReview,
    BlindExperienceSummary,
    BlindReaderPacket,
    EditorialMemo,
    EditorialMemoSummary,
    NovelForgeError,
    ReaderReview,
    ReaderReviewSummary,
    ReviewVerdict,
)
from app.novel_forge.repository import (
    AuditRepository,
    BlindExperienceRepository,
    BookRepository,
    ChapterRepository,
    EditorialMemoRepository,
    ReaderReviewRepository,
    RevisionRepository,
)


def _validate_prose_observation(prose_observation: str, revision_text: str | None = None) -> None:
    """Ensure prose_observation contains at least one locatable evidence.

    This is a heuristic gate: it prevents memos that are purely abstract
    praise. It does not require perfect formatting, but it must show that
    the reviewer pointed to a concrete passage or a specific issue.
    """
    text = prose_observation.strip()
    if not text:
        raise NovelForgeError("Memo field 'prose_observation' cannot be empty.")

    # 1. Explicit location markers.
    has_location = bool(
        re.search(r"S\d+", text)
        or re.search(r"第\s*\d+\s*[行段]", text)
        or re.search(r"第[一二三四五六七八九十百千万0-9]+[行段]", text)
    )

    # 2. Concrete issue / revision vocabulary.
    issue_keywords = [
        "失效", "可优化", "问题", "缺陷", "生硬", "不自然", "awkward",
        "删除", "改为", "建议", "偏", "过", "太短", "太长", "重复",
        "解释", "总结", "告诉", "而非", "代替",
    ]
    has_issue_language = any(kw in text for kw in issue_keywords)

    # 3. Quoted evidence from the revision text itself.
    has_quoted_evidence = False
    if revision_text:
        # Use SequenceMatcher to find the longest common substring in O(n*m)
        # but with efficient C implementation, instead of the previous O(n²)
        # sliding window over every length.
        matcher = difflib.SequenceMatcher(None, text, revision_text)
        match = matcher.find_longest_match(0, len(text), 0, len(revision_text))
        if match.size >= 6 and re.search(r"[\u4e00-\u9fff]", text[match.a : match.a + match.size]):
            has_quoted_evidence = True
        # If the single longest match isn't CJK, try the next few matches.
        if not has_quoted_evidence:
            for block in matcher.get_matching_blocks():
                if block.size >= 6 and re.search(r"[\u4e00-\u9fff]", text[block.a : block.a + block.size]):
                    has_quoted_evidence = True
                    break

    if not (has_location or has_issue_language or has_quoted_evidence):
        raise NovelForgeError(
            "Memo field 'prose_observation' must contain at least one locatable "
            "evidence (e.g., scene reference S1, line reference, quoted passage) "
            "or describe a concrete prose issue. Pure praise is not sufficient."
        )


class ReviewGatesMixin:
    """Reader Review, Blind Experience, and Editorial Memo gates."""

    # ------------------------------------------------------------------
    # Reader Reviews
    # ------------------------------------------------------------------
    def add_reader_review(
        self,
        slug: str,
        number: int,
        lens: str,
        severity: str,
        location_start: int,
        location_end: int,
        evidence: str,
        reader_effect: str,
        revision_intent: str,
        actor: str = "human_or_agent_review",
    ) -> int:
        if lens not in self._VALID_READER_REVIEW_LENS:
            raise NovelForgeError(f"Invalid reader review lens: {lens}")
        if severity not in {"S1", "S2", "S3", "S4"}:
            raise NovelForgeError(f"Invalid severity: {severity}")
        if not evidence or not evidence.strip():
            raise NovelForgeError("evidence is required.")
        if not reader_effect or not reader_effect.strip():
            raise NovelForgeError("reader_effect is required.")
        if not revision_intent or not revision_intent.strip():
            raise NovelForgeError("revision_intent is required.")
        if location_start < 1 or location_end < location_start:
            raise NovelForgeError(
                "location_start must be >= 1 and location_end must be >= location_start."
            )

        with self._conn() as conn:
            book = BookRepository.get_by_slug(conn, slug)
            if book is None:
                raise NovelForgeError(f"Book not found: {slug}")
            chapter = ChapterRepository.get_by_book_and_number(conn, book["id"], number)
            if chapter is None:
                raise NovelForgeError(f"Chapter {number} not found in book {slug}.")
            if chapter["current_revision_id"] is None:
                raise NovelForgeError(
                    f"Chapter {number} has no current revision; add a revision before adding a reader review."
                )
            if chapter["state"] == "approved":
                raise NovelForgeError(
                    f"Chapter {number} is approved. Use write-revision with "
                    "--reopen-reason before adding a reader review."
                )

            review_id = ReaderReviewRepository.add(
                conn,
                chapter_id=chapter["id"],
                revision_id=chapter["current_revision_id"],
                lens=lens,
                severity=severity,
                location_start=location_start,
                location_end=location_end,
                evidence=evidence,
                reader_effect=reader_effect,
                revision_intent=revision_intent,
                actor=actor,
            )
            AuditRepository.add(
                conn,
                book_id=book["id"],
                entity_type="reader_review",
                entity_id=review_id,
                action="add",
                details=json.dumps(
                    {
                        "chapter_id": chapter["id"],
                        "lens": lens,
                        "severity": severity,
                    },
                    ensure_ascii=False,
                ),
            )
            return review_id

    def resolve_reader_review(self, review_id: int, note: str) -> None:
        with self._conn() as conn:
            review = ReaderReviewRepository.get_by_id(conn, review_id)
            if review is None:
                raise NovelForgeError(f"Reader review not found: {review_id}")
            if review["status"] != "open":
                raise NovelForgeError(
                    f"Reader review {review_id} is already {review['status']}."
                )

            ReaderReviewRepository.resolve(conn, review_id, note)
            cur = conn.execute(
                "SELECT book_id FROM chapters WHERE id = ?", (review["chapter_id"],)
            )
            row = cur.fetchone()
            if row is None:
                raise NovelForgeError(
                    f"Chapter for reader review {review_id} no longer exists."
                )
            AuditRepository.add(
                conn,
                book_id=row["book_id"],
                entity_type="reader_review",
                entity_id=review_id,
                action="resolve",
                details=json.dumps({"note": note}, ensure_ascii=False),
            )

    def reader_review_summary_for_chapter(
        self, slug: str, number: int
    ) -> ReaderReviewSummary:
        with self._conn() as conn:
            book = BookRepository.get_by_slug(conn, slug)
            if book is None:
                raise NovelForgeError(f"Book not found: {slug}")
            chapter = ChapterRepository.get_by_book_and_number(conn, book["id"], number)
            if chapter is None:
                raise NovelForgeError(f"Chapter {number} not found in book {slug}.")
            rev_id = chapter["current_revision_id"]
            lens_counts, severity_counts = ReaderReviewRepository.open_counts_for_revision(
                conn, rev_id
            )
            total = sum(severity_counts.values())
            return ReaderReviewSummary(
                lens_counts=lens_counts,
                severity_counts=severity_counts,
                total_open=total,
            )

    # ------------------------------------------------------------------
    # Blind Experience Gate
    # ------------------------------------------------------------------
    _BLIND_FORBIDDEN_SOURCE_TERMS = (
        "scene contract",
        "voice bible",
        "drafting packet",
        "chapter plan",
        "story engine",
        "作者意图",
        "场景合同",
        "声线圣经",
        "写作包",
        "章节计划",
        "故事发动机",
    )

    _BLIND_MIN_EVIDENCE_LENGTH = 6

    @classmethod
    def _blind_review_contains_forbidden_source_terms(
        cls,
        fields: dict[str, str],
        images: list[dict[str, str]],
        gaps: list[str],
        issues: list[dict[str, str]],
    ) -> bool:
        """Return True if any user-provided string contains planning-source language.

        The scan covers the five free-text fields, every nested string inside
        memorable_images and blocking_issues, and every knowledge_gap. This keeps
        the blind reader isolated from author intent regardless of where the leak
        is attempted.
        """
        texts: list[str] = list(fields.values())
        texts.extend(gap for gap in gaps)
        for image in images:
            texts.extend(image.get(k, "") for k in ("location", "evidence", "reader_image"))
        for issue in issues:
            texts.extend(
                issue.get(k, "")
                for k in ("location", "evidence", "reader_effect", "revision_intent")
            )
        combined = " ".join(str(v).lower() for v in texts)
        return any(term in combined for term in cls._BLIND_FORBIDDEN_SOURCE_TERMS)

    def build_blind_reader_packet(
        self, slug: str, number: int, output_file: Path
    ) -> BlindReaderPacket:
        """Write a prose-only, line-numbered packet for an isolated reader.

        No planning asset is loaded by this method. The packet is deliberately
        ignorant of intent so missing images cannot be supplied from memory.
        """
        output_file = Path(output_file)
        if not output_file.is_absolute():
            raise NovelForgeError("output_file must be an absolute path.")
        resolved = output_file.resolve()
        if resolved.exists():
            raise NovelForgeError(f"output_file already exists: {output_file}")
        try:
            resolved.relative_to((self.root / "library").resolve())
            raise NovelForgeError(
                "output_file must not be inside the project library directory."
            )
        except ValueError:
            pass

        with self._conn() as conn:
            book = BookRepository.get_by_slug(conn, slug)
            if book is None:
                raise NovelForgeError(f"Book not found: {slug}")
            chapter = ChapterRepository.get_by_book_and_number(
                conn, book["id"], number
            )
            if chapter is None:
                raise NovelForgeError(f"Chapter {number} not found in book {slug}.")
            revision_id = chapter["current_revision_id"]
            if revision_id is None:
                raise NovelForgeError(
                    f"Chapter {number} has no current revision; cannot build blind packet."
                )
            revision = RevisionRepository.get_by_id(conn, revision_id)
            if revision is None:
                raise NovelForgeError(f"Revision not found: {revision_id}")
            revision_path = self.root / revision["file_path"]
            prose = revision_path.read_text(encoding="utf-8")

        lines = [
            "# Blind Reader Packet",
            "",
            "> SOURCE SCOPE: PROSE ONLY.",
            "> Do not infer author intent, planning notes, world rules, or missing images.",
            "> Report only what a first-time reader can reconstruct from the text below.",
            "",
            f"- book_slug: {slug}",
            f"- chapter_number: {number}",
            f"- revision_id: {revision_id}",
            "",
            "## Prose With Line Numbers",
            "",
        ]
        for idx, line in enumerate(prose.splitlines(), 1):
            lines.append(f"{idx:03d} | {line}")
        lines.extend(
            [
                "",
                "## Required Reconstruction",
                "",
                "Describe spatial layout, body position/contact, action constraints, emotional trajectory, dialogue change, and at least three memorable images. List every place where outside knowledge would be required.",
            ]
        )
        content = "\n".join(lines) + "\n"
        resolved.parent.mkdir(parents=True, exist_ok=True)
        resolved.write_text(content, encoding="utf-8")
        digest = hashlib.sha256(content.encode("utf-8")).hexdigest()
        try:
            recorded = str(resolved.relative_to(self.root))
        except ValueError:
            recorded = str(resolved)

        with self._conn() as conn:
            AuditRepository.add(
                conn,
                book_id=book["id"],
                entity_type="blind_reader_packet",
                entity_id=revision_id,
                action="build",
                details=json.dumps(
                    {"output_file": recorded, "content_hash": digest},
                    ensure_ascii=False,
                ),
            )

        return BlindReaderPacket(
            file_path=recorded,
            absolute_path=str(resolved),
            content_hash=digest,
            book_slug=slug,
            chapter_number=number,
            revision_id=revision_id,
        )

    def submit_blind_experience_review(
        self,
        slug: str,
        number: int,
        spatial_reconstruction: str,
        body_position_and_contact: str,
        action_constraints: str,
        emotional_trajectory: str,
        dialogue_dynamics: str,
        memorable_images: list[dict[str, Any]],
        knowledge_gaps: list[str],
        verdict: str,
        blocking_issues: list[dict[str, Any]],
    ) -> BlindExperienceReview:
        if verdict not in {"experience_reconstructable", "revision_required"}:
            raise NovelForgeError(f"Invalid blind review verdict: {verdict!r}.")
        fields = {
            "spatial_reconstruction": spatial_reconstruction,
            "body_position_and_contact": body_position_and_contact,
            "action_constraints": action_constraints,
            "emotional_trajectory": emotional_trajectory,
            "dialogue_dynamics": dialogue_dynamics,
        }
        for name, value in fields.items():
            if not value or not str(value).strip():
                raise NovelForgeError(f"Blind review field '{name}' cannot be empty.")
        images: list[dict[str, str]] = []
        image_evidence_seen: set[str] = set()
        for idx, image in enumerate(memorable_images):
            if not isinstance(image, dict):
                raise NovelForgeError(
                    f"Memorable image at index {idx} must be an object."
                )
            normalized: dict[str, str] = {}
            for required in ("location", "evidence", "reader_image"):
                value = str(image.get(required, "")).strip()
                if not value:
                    raise NovelForgeError(
                        f"Memorable image at index {idx} is missing '{required}'."
                    )
                normalized[required] = value
            if len(normalized["evidence"]) < self._BLIND_MIN_EVIDENCE_LENGTH:
                raise NovelForgeError(
                    f"Memorable image at index {idx} evidence must be at least "
                    f"{self._BLIND_MIN_EVIDENCE_LENGTH} characters."
                )
            if normalized["evidence"] in image_evidence_seen:
                raise NovelForgeError(
                    f"Memorable image at index {idx} duplicates evidence from an earlier image."
                )
            image_evidence_seen.add(normalized["evidence"])
            images.append(normalized)
        if verdict == "experience_reconstructable" and len(images) < 3:
            raise NovelForgeError(
                "A passing blind review requires at least 3 memorable_images."
            )
        gaps = [str(x).strip() for x in knowledge_gaps if str(x).strip()]
        validated_issues: list[dict[str, str]] = []
        issue_evidence_seen: set[str] = set()
        for idx, issue in enumerate(blocking_issues):
            if not isinstance(issue, dict):
                raise NovelForgeError(
                    f"Blind blocking issue at index {idx} must be an object."
                )
            normalized: dict[str, str] = {}
            for required in (
                "location",
                "evidence",
                "reader_effect",
                "revision_intent",
            ):
                value = str(issue.get(required, "")).strip()
                if not value:
                    raise NovelForgeError(
                        f"Blind blocking issue at index {idx} is missing '{required}'."
                    )
                normalized[required] = value
            if len(normalized["evidence"]) < self._BLIND_MIN_EVIDENCE_LENGTH:
                raise NovelForgeError(
                    f"Blind blocking issue at index {idx} evidence must be at least "
                    f"{self._BLIND_MIN_EVIDENCE_LENGTH} characters."
                )
            if normalized["evidence"] in issue_evidence_seen:
                raise NovelForgeError(
                    f"Blind blocking issue at index {idx} duplicates evidence from an earlier issue."
                )
            issue_evidence_seen.add(normalized["evidence"])
            validated_issues.append(normalized)
        if self._blind_review_contains_forbidden_source_terms(
            {k: str(v).strip() for k, v in fields.items()},
            images,
            gaps,
            validated_issues,
        ):
            raise NovelForgeError(
                "Blind review contains planning-source language; the reader must use prose only."
            )
        if verdict == "revision_required" and not validated_issues:
            raise NovelForgeError(
                "Blind review verdict 'revision_required' requires blocking_issues."
            )
        if verdict == "experience_reconstructable" and (validated_issues or gaps):
            raise NovelForgeError(
                "A passing blind review cannot contain knowledge_gaps or blocking_issues."
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
            revision_id = chapter["current_revision_id"]
            if revision_id is None:
                raise NovelForgeError(
                    f"Chapter {number} has no current revision; cannot attach blind review."
                )
            revision = RevisionRepository.get_by_id(conn, revision_id)
            if revision is None:
                raise NovelForgeError(f"Revision not found: {revision_id}")
            revision_text = (self.root / revision["file_path"]).read_text(
                encoding="utf-8"
            )
            for idx, image in enumerate(images):
                if image["evidence"] not in revision_text:
                    raise NovelForgeError(
                        f"Memorable image at index {idx} evidence was not found "
                        "in the current revision."
                    )
            for idx, issue in enumerate(validated_issues):
                if issue["evidence"] not in revision_text:
                    raise NovelForgeError(
                        f"Blind blocking issue at index {idx} evidence was not found "
                        "in the current revision."
                    )
            BlindExperienceRepository.supersede_active_for_chapter(
                conn, chapter["id"]
            )
            review_id = BlindExperienceRepository.create(
                conn,
                chapter_id=chapter["id"],
                revision_id=revision_id,
                spatial_reconstruction=spatial_reconstruction.strip(),
                body_position_and_contact=body_position_and_contact.strip(),
                action_constraints=action_constraints.strip(),
                emotional_trajectory=emotional_trajectory.strip(),
                dialogue_dynamics=dialogue_dynamics.strip(),
                memorable_images=json.dumps(images, ensure_ascii=False),
                knowledge_gaps=json.dumps(gaps, ensure_ascii=False),
                verdict=verdict,
                blocking_issues=json.dumps(validated_issues, ensure_ascii=False),
            )
            AuditRepository.add(
                conn,
                book_id=book["id"],
                entity_type="blind_experience_review",
                entity_id=review_id,
                action="submit",
                details=json.dumps(
                    {
                        "chapter_id": chapter["id"],
                        "revision_id": revision_id,
                        "verdict": verdict,
                        "memorable_image_count": len(images),
                        "knowledge_gap_count": len(gaps),
                        "blocking_issue_count": len(validated_issues),
                        "source_scope": "prose_only",
                    },
                    ensure_ascii=False,
                ),
            )
            row = BlindExperienceRepository.get_by_id(conn, review_id)
        return BlindExperienceReview.model_validate(dict(row))

    def blind_experience_status(
        self, slug: str, number: int
    ) -> BlindExperienceSummary:
        with self._conn() as conn:
            book = BookRepository.get_by_slug(conn, slug)
            if book is None:
                raise NovelForgeError(f"Book not found: {slug}")
            chapter = ChapterRepository.get_by_book_and_number(
                conn, book["id"], number
            )
            if chapter is None:
                raise NovelForgeError(f"Chapter {number} not found in book {slug}.")
            revision_id = chapter["current_revision_id"]
            if revision_id is None:
                return BlindExperienceSummary()
            row = BlindExperienceRepository.get_active_by_revision(
                conn, chapter["id"], revision_id
            )
            return self._blind_experience_summary_from_row(row)

    @staticmethod
    def _blind_experience_summary_from_row(
        row: sqlite3.Row | None,
    ) -> BlindExperienceSummary:
        if row is None:
            return BlindExperienceSummary()
        images = json.loads(row["memorable_images"] or "[]")
        gaps = json.loads(row["knowledge_gaps"] or "[]")
        issues = json.loads(row["blocking_issues"] or "[]")
        passes = (
            row["source_scope"] == "prose_only"
            and row["verdict"] == "experience_reconstructable"
            and len(images) >= 3
            and not gaps
            and not issues
        )
        return BlindExperienceSummary(
            exists=True,
            review_id=row["id"],
            revision_id=row["revision_id"],
            verdict=row["verdict"],
            passes=passes,
            memorable_image_count=len(images),
            knowledge_gap_count=len(gaps),
            blocking_issue_count=len(issues),
            created_at=row["created_at"],
        )

    # ------------------------------------------------------------------
    # Narrative Editorial Memo
    # ------------------------------------------------------------------
    def submit_editorial_memo(
        self,
        slug: str,
        number: int,
        narrative_necessity: str,
        character_agency: str,
        detail_selection: str,
        causal_chain: str,
        prose_observation: str,
        verdict: str,
        blocking_issues: list[dict[str, Any]],
        reviewer_role: str = "independent_reader_editor",
    ) -> EditorialMemo:
        """Submit an editorial memo for the current revision.

        The memo is coverage evidence, not a literature grade. Only one active
        memo per chapter (for the current revision) is allowed; a new memo
        supersedes the previous active one with an audit trail.
        """
        if verdict not in {"ready_for_editor_decision", "revision_required"}:
            raise NovelForgeError(
                f"Invalid memo verdict: {verdict!r}. Use "
                "'ready_for_editor_decision' or 'revision_required'."
            )
        if reviewer_role != "independent_reader_editor":
            raise NovelForgeError(
                f"Invalid reviewer_role: {reviewer_role!r}. "
                "Only 'independent_reader_editor' is allowed."
            )

        for field_name, value in (
            ("narrative_necessity", narrative_necessity),
            ("character_agency", character_agency),
            ("detail_selection", detail_selection),
            ("causal_chain", causal_chain),
        ):
            if not value or not str(value).strip():
                raise NovelForgeError(f"Memo field '{field_name}' cannot be empty.")

        validated_issues: list[dict[str, Any]] = []
        for idx, issue in enumerate(blocking_issues):
            if not isinstance(issue, dict):
                raise NovelForgeError(
                    f"Blocking issue at index {idx} must be an object."
                )
            for required in ("location", "evidence", "effect", "revision_intent"):
                if not issue.get(required) or not str(issue[required]).strip():
                    raise NovelForgeError(
                        f"Blocking issue at index {idx} is missing '{required}'."
                    )
            validated_issues.append(
                {
                    "location": str(issue["location"]),
                    "evidence": str(issue["evidence"]),
                    "effect": str(issue["effect"]),
                    "revision_intent": str(issue["revision_intent"]),
                }
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

            revision_id = chapter["current_revision_id"]
            if revision_id is None:
                raise NovelForgeError(
                    f"Chapter {number} has no current revision; cannot attach memo."
                )

            rev = RevisionRepository.get_by_id(conn, revision_id)
            revision_text = None
            if rev is not None:
                rev_path = self.root / rev["file_path"]
                if rev_path.exists():
                    revision_text = rev_path.read_text(encoding="utf-8")

            _validate_prose_observation(prose_observation, revision_text)

            EditorialMemoRepository.supersede_active_for_chapter(
                conn, chapter["id"]
            )
            memo_id = EditorialMemoRepository.create(
                conn,
                chapter_id=chapter["id"],
                revision_id=revision_id,
                reviewer_role=reviewer_role,
                narrative_necessity=narrative_necessity.strip(),
                character_agency=character_agency.strip(),
                detail_selection=detail_selection.strip(),
                causal_chain=causal_chain.strip(),
                prose_observation=prose_observation.strip(),
                verdict=verdict,
                blocking_issues=json.dumps(validated_issues, ensure_ascii=False),
            )

            AuditRepository.add(
                conn,
                book_id=book["id"],
                entity_type="editorial_memo",
                entity_id=memo_id,
                action="submit",
                details=json.dumps(
                    {
                        "chapter_id": chapter["id"],
                        "revision_id": revision_id,
                        "verdict": verdict,
                        "blocking_issue_count": len(validated_issues),
                    },
                    ensure_ascii=False,
                ),
            )

            row = EditorialMemoRepository.get_by_id(conn, memo_id)

        return EditorialMemo.model_validate(dict(row))

    def editorial_memo_status(
        self, slug: str, number: int
    ) -> EditorialMemoSummary:
        """Return metadata-only summary of the active editorial memo."""
        with self._conn() as conn:
            book = BookRepository.get_by_slug(conn, slug)
            if book is None:
                raise NovelForgeError(f"Book not found: {slug}")
            chapter = ChapterRepository.get_by_book_and_number(
                conn, book["id"], number
            )
            if chapter is None:
                raise NovelForgeError(f"Chapter {number} not found in book {slug}.")

            row = EditorialMemoRepository.get_active_by_chapter(conn, chapter["id"])
            if row is None:
                return EditorialMemoSummary(exists=False)
            return EditorialMemoSummary(
                exists=True,
                memo_id=row["id"],
                revision_id=row["revision_id"],
                verdict=row["verdict"],
                blocking_issue_count=len(
                    json.loads(row["blocking_issues"] or "[]")
                ),
                superseded_at=row["superseded_at"],
                created_at=row["created_at"],
            )

    def _active_memo_for_current_revision(
        self, conn: sqlite3.Connection, chapter: sqlite3.Row
    ) -> sqlite3.Row | None:
        """Return active memo only if it belongs to the chapter's current revision."""
        revision_id = chapter["current_revision_id"]
        if revision_id is None:
            return None
        return EditorialMemoRepository.get_active_by_revision(
            conn, chapter["id"], revision_id
        )

    @staticmethod
    def _editorial_memo_status_from_row(
        row: sqlite3.Row | None,
    ) -> dict[str, Any]:
        if row is None:
            return {
                "exists": False,
                "memo_id": None,
                "revision_id": None,
                "verdict": None,
                "blocking_issue_count": 0,
            }
        return {
            "exists": True,
            "memo_id": row["id"],
            "revision_id": row["revision_id"],
            "verdict": row["verdict"],
            "blocking_issue_count": len(
                json.loads(row["blocking_issues"] or "[]")
            ),
        }

    # ------------------------------------------------------------------
    # Drafting Readiness Gate
    # ------------------------------------------------------------------
