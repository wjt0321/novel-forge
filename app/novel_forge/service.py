"""Business logic and state machine for Novel Forge."""

import hashlib
import json
import re
import shutil
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from app.novel_forge.db import get_db_path, init_db
from app.novel_forge.export import (
    compile_markdown,
    convert_with_pandoc,
    find_pandoc,
    hash_text,
    now_iso,
)
from app.novel_forge.lint import _count_cjk_chars, lint_file
from app.novel_forge.models import (
    AuditEvent,
    Book,
    BookSummary,
    Chapter,
    ChapterState,
    ChapterSummary,
    DraftingPacket,
    DraftingReadiness,
    EditorialMemo,
    EditorialMemoSummary,
    ReaderReview,
    ReaderReviewSummary,
    Revision,
    ReviewResult,
    ReviewVerdict,
    SceneContract,
    SceneContractRevision,
    VoiceBible,
    VoiceBibleRevision,
)
from app.novel_forge.readiness import (
    count_concrete_anchors,
    detect_contract_version,
    is_missing_content,
    parse_markdown_sections,
)
from app.novel_forge.repository import (
    AuditRepository,
    BookRepository,
    ChapterRepository,
    EditorialMemoRepository,
    ExportRepository,
    FactRepository,
    FindingRepository,
    ReaderReviewRepository,
    RevisionRepository,
    SceneContractRepository,
    VoiceBibleRepository,
)


class NovelForgeError(Exception):
    """Base exception with a user-facing message."""

    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


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
        # Try to find any substring of the memo that appears in the revision.
        # We slide a small window to catch partial quotes.
        min_len = 6
        max_len = min(40, len(text))
        if max_len >= min_len:
            for length in range(max_len, min_len - 1, -1):
                for start in range(0, len(text) - length + 1):
                    window = text[start:start + length]
                    # Skip windows that are mostly punctuation or location markers.
                    if re.search(r"[\u4e00-\u9fff]", window) and window in revision_text:
                        has_quoted_evidence = True
                        break
                if has_quoted_evidence:
                    break

    if not (has_location or has_issue_language or has_quoted_evidence):
        raise NovelForgeError(
            "Memo field 'prose_observation' must contain at least one locatable "
            "evidence (e.g., scene reference S1, line reference, quoted passage) "
            "or describe a concrete prose issue. Pure praise is not sufficient."
        )


# State-machine guards. Each operation verifies the chapter is in an
# allowed state before mutating it, preventing skip-level approvals.
_ALLOWED_LINT_STATES = {"draft", "linted", "revised", "reviewed", "revision_requested"}
_ALLOWED_REVIEW_STATES = {"linted", "revised", "reviewed"}
_ALLOWED_APPROVE_STATES = {"reviewed"}
_ALLOWED_ROLLBACK_STATES = {
    "linted",
    "reviewed",
    "revision_requested",
    "approved",
    "exported",
}


class NovelForgeService:
    def __init__(self, root: Path):
        self.root = Path(root).resolve()
        self.library_root = self.root / "library"
        self.data_root = self.root / "data"
        # Ensure DB is initialized and migrated on first use. Close the
        # bootstrap connection; operational connections come from _conn().
        conn = init_db(self.root)
        conn.close()

    # ------------------------------------------------------------------
    # Connection / transaction
    # ------------------------------------------------------------------
    @contextmanager
    def _conn(self):
        conn = sqlite3.connect(str(get_db_path(self.root)))
        conn.execute("PRAGMA foreign_keys = ON")
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    # ------------------------------------------------------------------
    # Path helpers
    # ------------------------------------------------------------------
    def _book_dir(self, slug: str) -> Path:
        return self.library_root / slug

    def _manuscript_dir(self, slug: str) -> Path:
        return self._book_dir(slug) / "manuscript"

    def _revisions_dir(self, slug: str, number: int) -> Path:
        return self._manuscript_dir(slug) / "revisions" / f"ch{number:04d}"

    def _canon_dir(self, slug: str) -> Path:
        return self._book_dir(slug) / "canon"

    def _planning_dir(self, slug: str) -> Path:
        return self._book_dir(slug) / "planning"

    def _exports_dir(self, slug: str) -> Path:
        return self._book_dir(slug) / "exports"

    def _voice_bible_dir(self, slug: str) -> Path:
        return self._planning_dir(slug) / "voice-bible"

    def _voice_bible_revisions_dir(self, slug: str) -> Path:
        return self._voice_bible_dir(slug) / "revisions"

    def _scene_contract_dir(self, slug: str, number: int) -> Path:
        return self._planning_dir(slug) / "chapters" / f"ch{number:04d}-contract"

    def _scene_contract_revisions_dir(self, slug: str, number: int) -> Path:
        return self._scene_contract_dir(slug, number) / "revisions"

    @staticmethod
    def _hash_file(path: Path) -> str:
        h = hashlib.sha256()
        h.update(path.read_bytes())
        return h.hexdigest()

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
            "---\n\n"
            "contract_version: 3\n"
        )

    # ------------------------------------------------------------------
    # Book lifecycle
    # ------------------------------------------------------------------
    def _work_root(self, slug: str) -> Path:
        return self.root / "work" / slug

    def initialize_book_workspace(self, slug: str) -> dict[str, Any]:
        """Create a non-destructive human-readable work directory for a book.

        The workspace is a read-only mirror and index into library/<slug>/.
        It never writes back to the library and never deletes existing files.
        """
        book = self.get_book(slug)
        work_root = self._work_root(slug)
        work_root.mkdir(parents=True, exist_ok=True)

        dirs = ["manuscript", "planning", "research", "reviews", "iterations", "archive"]
        for d in dirs:
            (work_root / d).mkdir(exist_ok=True)

        current_md = work_root / "CURRENT.md"
        current_md.write_text(
            f"# Current Canonical Source\n\n"
            f"Book: `{slug}`\n\n"
            f"The authoritative manuscript is in `library/{slug}/manuscript/revisions/`.\n"
            f"This workspace is a read-only mirror. Do not edit files here directly.\n",
            encoding="utf-8",
        )

        readme = work_root / "README.md"
        readme_lines = [
            f"# Work Space: {book.title}",
            "",
            f"**Book slug:** `{slug}`  ",
            f"**Human entry point:** open `manuscript/chapter-<number>-current.md` to read the latest revision of any chapter.  ",
            f"**Canonical library path:** `library/{slug}/` (authoritative source of truth).",
            "",
            "This directory is a human-readable workspace and mirror. "
            "Files under `manuscript/` and `planning/` are regenerated by `refresh-workspace` operations. "
            "Do not edit generated mirrors directly; your changes will be overwritten on the next refresh.",
            "",
            "## Directory map",
            "",
            "- `manuscript/` — read-only mirror of the current revision for each chapter.",
            "- `planning/` — read-only mirror of the current Voice Bible and Scene Contracts.",
            "- `research/` — research ledger exports (future / manual).",
            "- `reviews/` — independent editor reviews and editorial memos.",
            "- `iterations/` — writer responses, blocking issues, iteration records.",
            "- `archive/` — non-current historical drafts and reviews.",
            "",
            "## How to read the current manuscript",
            "",
            f"1. Open `manuscript/chapter-0001-current.md` (or `chapter-0002-current.md`, etc.) for the latest revision.",
            f"2. Or check `CURRENT.md` for a summary of every chapter's revision, word count, and state.",
            f"3. The official immutable revisions remain in `library/{slug}/manuscript/revisions/ch<chapter>/`.",
            f"4. Run `refresh-workspace {slug}` to update the mirrors after new revisions are written.",
            "",
            "## Legacy files",
            "",
            "Any files previously placed directly under this directory remain where they are. "
            "They are considered legacy and are not deleted by workspace operations.",
            "",
        ]
        readme.write_text("\n".join(readme_lines), encoding="utf-8")

        return {
            "work_root": str(work_root.relative_to(self.root)),
            "created_dirs": dirs,
            "readme": str(readme.relative_to(self.root)),
            "current": str(current_md.relative_to(self.root)),
        }

    def _is_generated_mirror(self, path: Path) -> bool:
        """Return True if the file looks like a mirror we generated."""
        if not path.exists():
            return False
        try:
            first_line = path.read_text(encoding="utf-8").split("\n", 1)[0]
        except UnicodeDecodeError:
            return False
        return first_line.startswith("<!-- MIRROR of")

    def refresh_book_workspace(self, slug: str) -> dict[str, Any]:
        """Refresh read-only mirrors in the work directory from library state.

        Only updates generated index files (CURRENT.md, README.md) and
        manuscript/planning mirrors. Never deletes user files. If a mirror
        file has been edited by the user (it no longer starts with our
        generated MIRROR header), it is skipped and reported as a warning.
        """
        book = self.get_book(slug)
        work_root = self._work_root(slug)
        if not work_root.exists():
            self.initialize_book_workspace(slug)

        warnings: list[str] = []
        current_lines = [
            f"# Current Canonical Source\n",
            f"",
            f"Book: `{slug}`",
            f"",
            "| Chapter | Title | State | Words (CJK) | Current Revision | Hash | Mirror |",
            "|--------:|-------|-------|------------:|-----------------:|------|--------|",
        ]

        mirrored_chapters: list[dict[str, Any]] = []
        chapters = self.list_chapters(slug)
        for chapter_summary in chapters:
            number = chapter_summary.number
            current_revision = self.get_current_revision(slug, number)
            if current_revision is None:
                current_lines.append(
                    f"| {number} | {chapter_summary.title} | {chapter_summary.state.value} | — | — | — | — |"
                )
                continue

            source_path = self.root / current_revision.file_path
            if not source_path.exists():
                warnings.append(
                    f"Chapter {number}: current revision file missing: {current_revision.file_path}"
                )
                current_lines.append(
                    f"| {number} | {chapter_summary.title} | {chapter_summary.state.value} | — | "
                    f"rev {current_revision.revision_number} | `{current_revision.content_hash[:16]}` | — |"
                )
                continue

            mirror_path = work_root / "manuscript" / f"chapter-{number:04d}-current.md"
            body = source_path.read_text(encoding="utf-8")
            word_count = _count_cjk_chars(body)
            mirror_content = (
                f"<!-- MIRROR of library/{slug}/manuscript/revisions/ch{number:04d}/ -->\n"
                f"<!-- revision_id={current_revision.id} revision_number={current_revision.revision_number} hash={current_revision.content_hash} -->\n"
                f"<!-- DO NOT EDIT: refresh with adapter refresh-workspace {slug} -->\n\n"
                f"{body}"
            )

            if mirror_path.exists() and not self._is_generated_mirror(mirror_path):
                warnings.append(
                    f"Skipped overwriting {mirror_path.relative_to(self.root)} because it appears to be user-edited."
                )
            else:
                mirror_path.write_text(mirror_content, encoding="utf-8")

            current_lines.append(
                f"| {number} | {chapter_summary.title} | {chapter_summary.state.value} | {word_count} | "
                f"rev {current_revision.revision_number} | `{current_revision.content_hash[:16]}` | "
                f"`{mirror_path.relative_to(self.root)}` |"
            )
            mirrored_chapters.append(
                {
                    "number": number,
                    "revision_id": current_revision.id,
                    "mirror_path": str(mirror_path.relative_to(self.root)),
                }
            )

        # Voice Bible mirror.
        voice_bible = self.get_voice_bible(slug)
        if voice_bible.exists and voice_bible.current_file_path:
            vb_source = self.root / voice_bible.current_file_path
            if vb_source.exists():
                vb_mirror = work_root / "planning" / "voice-bible-current.md"
                vb_body = vb_source.read_text(encoding="utf-8")
                if vb_mirror.exists() and not self._is_generated_mirror(vb_mirror):
                    warnings.append(
                        f"Skipped overwriting {vb_mirror.relative_to(self.root)} because it appears to be user-edited."
                    )
                else:
                    vb_mirror.write_text(
                        f"<!-- MIRROR of {voice_bible.current_file_path} -->\n\n{vb_body}",
                        encoding="utf-8",
                    )
                current_lines.append(
                    f""
                )
                current_lines.append(
                    f"- Voice Bible: `{voice_bible.current_file_path}`"
                )

        # Scene Contract mirrors.
        for chapter_summary in chapters:
            number = chapter_summary.number
            sc = self.get_scene_contract(slug, number)
            if sc.exists and sc.current_file_path:
                sc_source = self.root / sc.current_file_path
                if sc_source.exists():
                    sc_mirror = work_root / "planning" / f"chapter-{number:04d}-contract-current.md"
                    sc_body = sc_source.read_text(encoding="utf-8")
                    if sc_mirror.exists() and not self._is_generated_mirror(sc_mirror):
                        warnings.append(
                            f"Skipped overwriting {sc_mirror.relative_to(self.root)} because it appears to be user-edited."
                        )
                    else:
                        sc_mirror.write_text(
                            f"<!-- MIRROR of {sc.current_file_path} -->\n\n{sc_body}",
                            encoding="utf-8",
                        )

        current_lines.extend([
            "",
            "The authoritative source is `library/<slug>/`. "
            "This file is regenerated by `refresh-workspace`.",
        ])
        if warnings:
            current_lines.extend(["", "## Warnings", ""])
            current_lines.extend(f"- {w}" for w in warnings)

        (work_root / "CURRENT.md").write_text(
            "\n".join(current_lines), encoding="utf-8"
        )

        return {
            "work_root": str(work_root.relative_to(self.root)),
            "mirrored_chapters": mirrored_chapters,
            "warnings": warnings,
        }

    def init_book(self, slug: str, title: str) -> Book:
        if not slug or not slug.replace("-", "").replace("_", "").isalnum():
            raise NovelForgeError(
                f"Invalid book slug: {slug!r}. Use alphanumeric, dash, or underscore."
            )

        book_dir = self._book_dir(slug)
        if book_dir.exists():
            raise NovelForgeError(f"Book already exists: {slug}")

        # Create directories before DB so filesystem is ready.
        (book_dir / "manuscript" / "revisions").mkdir(parents=True)
        (book_dir / "canon").mkdir(parents=True)
        (book_dir / "planning" / "chapters").mkdir(parents=True)
        (book_dir / "exports").mkdir(parents=True)
        self._voice_bible_revisions_dir(slug).mkdir(parents=True)

        # Initial voice-bible template asset.
        ts = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
        vb_path = self._voice_bible_revisions_dir(slug) / f"0001-{ts}-template.md"
        vb_template = self._voice_bible_template(title)
        vb_path.write_text(vb_template, encoding="utf-8")
        vb_hash = self._hash_file(vb_path)

        # Ensure DB initialized and migrated (idempotent).
        conn = init_db(self.root)
        conn.close()

        with self._conn() as conn:
            book_id = BookRepository.create(conn, slug=slug, title=title)
            vb_rev_id = VoiceBibleRepository.create_revision(
                conn,
                book_id=book_id,
                revision_number=1,
                file_path=str(vb_path.relative_to(self.root)),
                content_hash=vb_hash,
                note="initial template",
            )
            VoiceBibleRepository.update_current(
                conn,
                book_id=book_id,
                revision_id=vb_rev_id,
                file_path=str(vb_path.relative_to(self.root)),
                content_hash=vb_hash,
            )
            AuditRepository.add(
                conn,
                book_id=book_id,
                entity_type="voice_bible",
                entity_id=vb_rev_id,
                action="init",
                details=json.dumps({"title": title, "revision_id": vb_rev_id}),
            )
            AuditRepository.add(
                conn,
                book_id=book_id,
                entity_type="book",
                action="init",
                details=json.dumps({"title": title}),
            )
            row = BookRepository.get_by_id(conn, book_id)

        return Book.model_validate(dict(row))

    def get_book(self, slug: str) -> Book:
        with self._conn() as conn:
            row = BookRepository.get_by_slug(conn, slug)
            if row is None:
                raise NovelForgeError(f"Book not found: {slug}")
            return Book.model_validate(dict(row))

    def list_books(self) -> list[BookSummary]:
        with self._conn() as conn:
            rows = BookRepository.list(conn)
            summaries = []
            for row in rows:
                chapters = ChapterRepository.list_by_book(conn, row["id"])
                approved = sum(1 for c in chapters if c["state"] == "approved")
                summaries.append(
                    BookSummary(
                        id=row["id"],
                        slug=row["slug"],
                        title=row["title"],
                        chapter_count=len(chapters),
                        approved_count=approved,
                        created_at=row["created_at"],
                    )
                )
            return summaries

    # ------------------------------------------------------------------
    # Chapter lifecycle
    # ------------------------------------------------------------------
    def create_chapter(self, slug: str, number: int, title: str) -> Chapter:
        if number < 1:
            raise NovelForgeError("Chapter number must be a positive integer.")

        with self._conn() as conn:
            book = BookRepository.get_by_slug(conn, slug)
            if book is None:
                raise NovelForgeError(f"Book not found: {slug}")

            existing = ChapterRepository.get_by_book_and_number(conn, book["id"], number)
            if existing is not None:
                raise NovelForgeError(
                    f"Chapter {number} already exists in book {slug}."
                )

            chapter_id = ChapterRepository.create(
                conn, book_id=book["id"], number=number, title=title
            )

            # Scene Contract v2 template as revision 1.
            contract_revs_dir = self._scene_contract_revisions_dir(slug, number)
            contract_revs_dir.mkdir(parents=True)
            ts = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
            contract_path = contract_revs_dir / f"0001-{ts}-template.md"
            contract_template = self._scene_contract_template(number, title)
            contract_path.write_text(contract_template, encoding="utf-8")
            contract_hash = self._hash_file(contract_path)

            contract_rev_id = SceneContractRepository.create_revision(
                conn,
                chapter_id=chapter_id,
                revision_number=1,
                file_path=str(contract_path.relative_to(self.root)),
                content_hash=contract_hash,
                note="initial v2 template",
            )
            SceneContractRepository.update_current(
                conn,
                chapter_id=chapter_id,
                revision_id=contract_rev_id,
                file_path=str(contract_path.relative_to(self.root)),
                content_hash=contract_hash,
            )

            AuditRepository.add(
                conn,
                book_id=book["id"],
                entity_type="scene_contract",
                entity_id=contract_rev_id,
                action="create",
                details=json.dumps(
                    {"number": number, "title": title, "revision_id": contract_rev_id}
                ),
            )
            AuditRepository.add(
                conn,
                book_id=book["id"],
                entity_type="chapter",
                entity_id=chapter_id,
                action="create",
                details=json.dumps({"number": number, "title": title}),
            )
            row = ChapterRepository.get_by_id(conn, chapter_id)

        return Chapter.model_validate(dict(row))

    def get_chapter(self, slug: str, number: int) -> Chapter:
        with self._conn() as conn:
            book = BookRepository.get_by_slug(conn, slug)
            if book is None:
                raise NovelForgeError(f"Book not found: {slug}")
            row = ChapterRepository.get_by_book_and_number(conn, book["id"], number)
            if row is None:
                raise NovelForgeError(f"Chapter {number} not found in book {slug}.")
            data = dict(row)
            if data.get("current_revision_id"):
                rev = RevisionRepository.get_by_id(conn, data["current_revision_id"])
                data["current_revision_number"] = rev["revision_number"] if rev else None
            return Chapter.model_validate(data)

    def list_chapters(self, slug: str) -> list[ChapterSummary]:
        with self._conn() as conn:
            book = BookRepository.get_by_slug(conn, slug)
            if book is None:
                raise NovelForgeError(f"Book not found: {slug}")
            rows = ChapterRepository.list_by_book(conn, book["id"])
            summaries = []
            for row in rows:
                rev_id = row["current_revision_id"]
                lint_counts = FindingRepository.lint_counts_for_revision(conn, rev_id)
                review_counts = FindingRepository.open_review_counts_for_revision(
                    conn, rev_id
                )
                rev_row = None
                if row["current_revision_id"]:
                    rev_row = RevisionRepository.get_by_id(
                        conn, row["current_revision_id"]
                    )
                summaries.append(
                    ChapterSummary(
                        id=row["id"],
                        book_id=row["book_id"],
                        number=row["number"],
                        title=row["title"],
                        state=ChapterState(row["state"]),
                        current_revision_id=row["current_revision_id"],
                        current_revision_number=rev_row["revision_number"]
                        if rev_row
                        else None,
                        open_s1=review_counts["S1"],
                        open_s2=review_counts["S2"],
                        open_s3=review_counts["S3"],
                        open_s4=review_counts["S4"],
                        blocking_lint=lint_counts["blocking"],
                    )
                )
            return summaries

    # ------------------------------------------------------------------
    # Revision
    # ------------------------------------------------------------------
    def write_revision(
        self,
        slug: str,
        number: int,
        from_file: Path,
        note: str | None = None,
        reopen_reason: str | None = None,
    ) -> Chapter:
        from_file = Path(from_file)
        if not from_file.exists():
            raise NovelForgeError(f"Source file not found: {from_file}")

        with self._conn() as conn:
            book = BookRepository.get_by_slug(conn, slug)
            if book is None:
                raise NovelForgeError(f"Book not found: {slug}")
            chapter = ChapterRepository.get_by_book_and_number(conn, book["id"], number)
            if chapter is None:
                raise NovelForgeError(f"Chapter {number} not found in book {slug}.")

            current_state = chapter["state"]
            if current_state == "approved" and not reopen_reason:
                raise NovelForgeError(
                    "Chapter is approved. Use --reopen-reason to write a new revision."
                )

            # Copy source to a new revision file.
            revs_dir = self._revisions_dir(slug, number)
            revs_dir.mkdir(parents=True, exist_ok=True)
            revision_number = ChapterRepository.get_next_revision_number(
                conn, chapter["id"]
            )
            content_hash = self._hash_file(from_file)
            ts = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
            dest_name = f"{revision_number:04d}-{ts}-{content_hash[:16]}.md"
            dest_path = revs_dir / dest_name
            shutil.copy2(from_file, dest_path)

            rev_id = RevisionRepository.create(
                conn,
                chapter_id=chapter["id"],
                revision_number=revision_number,
                file_path=str(dest_path.relative_to(self.root)),
                content_hash=content_hash,
                note=note,
            )
            ChapterRepository.update_current_revision(
                conn, chapter["id"], rev_id, content_hash
            )

            # State transition.
            new_state = "revised" if current_state == "approved" else "draft"
            ChapterRepository.set_state(conn, chapter["id"], new_state)

            details = {
                "revision_id": rev_id,
                "revision_number": revision_number,
                "content_hash": content_hash,
                "previous_state": current_state,
                "new_state": new_state,
            }
            if reopen_reason:
                details["reopen_reason"] = reopen_reason

            AuditRepository.add(
                conn,
                book_id=book["id"],
                entity_type="chapter",
                entity_id=chapter["id"],
                action="write_revision",
                details=json.dumps(details, ensure_ascii=False),
            )

            row = ChapterRepository.get_by_id(conn, chapter["id"])

        return Chapter.model_validate(dict(row))

    def write_revision_patch(
        self,
        slug: str,
        number: int,
        patch_file: Path,
        note: str | None = None,
        reopen_reason: str | None = None,
    ) -> Chapter:
        """Apply a JSON patch to the current revision and write a new revision.

        The patch file must contain a JSON array of objects with:
        - location: human-readable location hint (e.g. "S3 第61行")
        - evidence: exact substring of the current revision to replace
        - replacement: replacement text
        - reason: why the change is being made

        Each evidence must match exactly once in the current revision text.
        Patches are applied in reverse position order so earlier replacements
        do not shift the positions of later ones. The original revision file is
        never modified; a new immutable revision file is created.
        """
        patch_file = Path(patch_file)
        if not patch_file.exists():
            raise NovelForgeError(f"Patch file not found: {patch_file}")
        try:
            raw_bytes = patch_file.read_bytes()
            patch_text = raw_bytes.decode("utf-8-sig")
        except UnicodeDecodeError as exc:
            raise NovelForgeError(
                f"Patch file is not valid UTF-8: {patch_file} ({exc})"
            )
        try:
            patch_data = json.loads(patch_text)
        except json.JSONDecodeError as exc:
            raise NovelForgeError(f"Patch file is not valid JSON: {patch_file} ({exc})")

        if not isinstance(patch_data, list):
            raise NovelForgeError("Patch file must contain a JSON array.")
        if not patch_data:
            raise NovelForgeError("Patch file is empty.")

        with self._conn() as conn:
            book = BookRepository.get_by_slug(conn, slug)
            if book is None:
                raise NovelForgeError(f"Book not found: {slug}")
            chapter = ChapterRepository.get_by_book_and_number(conn, book["id"], number)
            if chapter is None:
                raise NovelForgeError(f"Chapter {number} not found in book {slug}")

            current_revision_id = chapter["current_revision_id"]
            if current_revision_id is None:
                raise NovelForgeError(
                    f"Chapter {number} has no current revision to patch."
                )

            rev = RevisionRepository.get_by_id(conn, current_revision_id)
            if rev is None:
                raise NovelForgeError(
                    f"Current revision {current_revision_id} not found."
                )
            rev_path = self.root / rev["file_path"]
            if not rev_path.exists():
                raise NovelForgeError(f"Current revision file missing: {rev['file_path']}")
            current_text = rev_path.read_text(encoding="utf-8")

        # Validate each patch item and resolve unique match positions.
        resolved_patches: list[dict[str, Any]] = []
        for idx, item in enumerate(patch_data):
            if not isinstance(item, dict):
                raise NovelForgeError(f"Patch item at index {idx} must be an object.")
            for required in ("location", "evidence", "replacement", "reason"):
                if required not in item:
                    raise NovelForgeError(
                        f"Patch item at index {idx} is missing '{required}'."
                    )
            evidence = str(item["evidence"])
            replacement = str(item["replacement"])
            if not evidence:
                raise NovelForgeError(
                    f"Patch item at index {idx} has empty 'evidence'."
                )
            if replacement == "":
                raise NovelForgeError(
                    f"Patch item at index {idx} has empty 'replacement'. "
                    "Use write-revision for full rewrites."
                )

            matches = [
                m.start() for m in re.finditer(re.escape(evidence), current_text)
            ]
            if len(matches) == 0:
                raise NovelForgeError(
                    f"Patch item at index {idx}: evidence not found in current revision: "
                    f"{evidence[:40]}"
                )
            if len(matches) > 1:
                raise NovelForgeError(
                    f"Patch item at index {idx}: evidence matches {len(matches)} times; "
                    "must be unique. Provide a longer or more specific evidence string."
                )
            resolved_patches.append(
                {
                    "location": str(item["location"]),
                    "evidence": evidence,
                    "replacement": replacement,
                    "reason": str(item["reason"]),
                    "position": matches[0],
                    "length": len(evidence),
                }
            )

        # Reject overlapping evidence intervals before applying.
        sorted_by_pos = sorted(resolved_patches, key=lambda p: p["position"])
        for i in range(len(sorted_by_pos) - 1):
            a = sorted_by_pos[i]
            b = sorted_by_pos[i + 1]
            if a["position"] + a["length"] > b["position"]:
                raise NovelForgeError(
                    f"Patch items overlap: item at {a['location']} and item at {b['location']}. "
                    "Provide non-overlapping evidence strings."
                )

        # Apply from end to start so positions remain stable.
        resolved_patches.sort(key=lambda p: p["position"], reverse=True)
        patched_text = current_text
        for p in resolved_patches:
            pos = p["position"]
            evidence = p["evidence"]
            replacement = p["replacement"]
            if patched_text[pos : pos + len(evidence)] != evidence:
                raise NovelForgeError(
                    "Internal patch error: evidence moved after prior replacement."
                )
            patched_text = (
                patched_text[:pos] + replacement + patched_text[pos + len(evidence) :]
            )

        # Write patched text to a temporary external file, then reuse write_revision.
        import tempfile
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", suffix=".md", delete=False
        ) as tmp:
            tmp.write(patched_text)
            tmp_path = Path(tmp.name)

        try:
            patch_note = note or f"patch from {patch_file.name}"
            return self.write_revision(
                slug,
                number,
                tmp_path,
                note=patch_note,
                reopen_reason=reopen_reason,
            )
        finally:
            tmp_path.unlink(missing_ok=True)

    # ------------------------------------------------------------------
    # Lint
    # ------------------------------------------------------------------
    def lint_chapter(self, slug: str, number: int) -> tuple[int, int]:
        with self._conn() as conn:
            book = BookRepository.get_by_slug(conn, slug)
            if book is None:
                raise NovelForgeError(f"Book not found: {slug}")
            chapter = ChapterRepository.get_by_book_and_number(conn, book["id"], number)
            if chapter is None:
                raise NovelForgeError(f"Chapter {number} not found in book {slug}.")

            current_state = chapter["state"]
            current_revision_id = chapter["current_revision_id"]
            if current_revision_id is None:
                raise NovelForgeError(
                    f"Chapter {number} has no revision to lint."
                )
            if current_state == "approved":
                raise NovelForgeError(
                    f"Chapter {number} is approved. Use write-revision with "
                    "--reopen-reason before linting."
                )
            if current_state not in _ALLOWED_LINT_STATES:
                raise NovelForgeError(
                    f"Cannot lint chapter {number} from state {current_state}."
                )

            rev = RevisionRepository.get_by_id(conn, current_revision_id)
            rev_path = self.root / rev["file_path"]
            findings = lint_file(rev_path)

            # Clear previous unresolved lint findings for this revision.
            conn.execute(
                "UPDATE lint_findings SET resolved = 1 WHERE revision_id = ? AND resolved = 0",
                (current_revision_id,),
            )

            blocking = 0
            advisory = 0
            for f in findings:
                if f.rule_code == "colon-density":
                    continue
                FindingRepository.add_lint_finding(
                    conn,
                    revision_id=current_revision_id,
                    rule_code=f.rule_code,
                    severity=f.severity,
                    line_number=f.line_number,
                    message=f.message,
                    evidence=f.evidence,
                )
                if f.severity == "blocking":
                    blocking += 1
                else:
                    advisory += 1

            # A successful lint run always advances the chapter to linted,
            # regardless of whether any findings were reported.
            ChapterRepository.set_state(conn, chapter["id"], "linted")

            AuditRepository.add(
                conn,
                book_id=book["id"],
                entity_type="chapter",
                entity_id=chapter["id"],
                action="lint",
                details=json.dumps(
                    {
                        "revision_id": current_revision_id,
                        "blocking": blocking,
                        "advisory": advisory,
                    }
                ),
            )

        return blocking, advisory

    # ------------------------------------------------------------------
    # Review findings
    # ------------------------------------------------------------------
    def add_finding(
        self,
        slug: str,
        number: int,
        perspective: str,
        severity: str,
        location: str,
        evidence: str,
        issue: str,
        fix: str,
    ) -> int:
        if perspective not in {"structure", "character", "narrative", "continuity"}:
            raise NovelForgeError(f"Invalid perspective: {perspective}")
        if severity not in {"S1", "S2", "S3", "S4"}:
            raise NovelForgeError(f"Invalid severity: {severity}")

        with self._conn() as conn:
            book = BookRepository.get_by_slug(conn, slug)
            if book is None:
                raise NovelForgeError(f"Book not found: {slug}")
            chapter = ChapterRepository.get_by_book_and_number(conn, book["id"], number)
            if chapter is None:
                raise NovelForgeError(f"Chapter {number} not found in book {slug}.")
            if chapter["current_revision_id"] is None:
                raise NovelForgeError(
                    f"Chapter {number} has no current revision; add a revision before adding findings."
                )
            if chapter["state"] == "approved":
                raise NovelForgeError(
                    f"Chapter {number} is approved. Use write-revision with "
                    "--reopen-reason before adding findings."
                )

            finding_id = FindingRepository.add_review_finding(
                conn,
                chapter_id=chapter["id"],
                revision_id=chapter["current_revision_id"],
                perspective=perspective,
                severity=severity,
                location=location,
                evidence=evidence,
                issue=issue,
                fix=fix,
            )
            AuditRepository.add(
                conn,
                book_id=book["id"],
                entity_type="finding",
                entity_id=finding_id,
                action="add",
                details=json.dumps(
                    {
                        "chapter_id": chapter["id"],
                        "perspective": perspective,
                        "severity": severity,
                    },
                    ensure_ascii=False,
                ),
            )
            return finding_id

    def resolve_finding(self, finding_id: int, note: str) -> None:
        with self._conn() as conn:
            finding = FindingRepository.get_review_finding(conn, finding_id)
            if finding is None:
                raise NovelForgeError(f"Finding not found: {finding_id}")
            if finding["resolved"]:
                raise NovelForgeError(
                    f"Finding {finding_id} is already resolved."
                )

            FindingRepository.resolve_review_finding(conn, finding_id, note)
            cur = conn.execute(
                "SELECT book_id FROM chapters WHERE id = ?",
                (finding["chapter_id"],),
            )
            row = cur.fetchone()
            if row is None:  # pragma: no cover - foreign key should prevent this
                raise NovelForgeError(
                    f"Chapter for finding {finding_id} no longer exists."
                )
            AuditRepository.add(
                conn,
                book_id=row["book_id"],
                entity_type="finding",
                entity_id=finding_id,
                action="resolve",
                details=json.dumps({"note": note}, ensure_ascii=False),
            )

    # ------------------------------------------------------------------
    # Review & approval
    # ------------------------------------------------------------------
    def review_chapter(self, slug: str, number: int) -> ReviewResult:
        with self._conn() as conn:
            book = BookRepository.get_by_slug(conn, slug)
            if book is None:
                raise NovelForgeError(f"Book not found: {slug}")
            chapter = ChapterRepository.get_by_book_and_number(conn, book["id"], number)
            if chapter is None:
                raise NovelForgeError(f"Chapter {number} not found in book {slug}.")

            current_state = chapter["state"]
            if current_state not in _ALLOWED_REVIEW_STATES:
                raise NovelForgeError(
                    f"Review requires chapter state linted, revised, or reviewed. "
                    f"Current state: {current_state}."
                )

            current_revision_id = chapter["current_revision_id"]
            lint_counts = FindingRepository.lint_counts_for_revision(
                conn, current_revision_id
            )
            review_counts = FindingRepository.open_review_counts_for_revision(
                conn, current_revision_id
            )
            open_findings = FindingRepository.list_open_by_revision(
                conn, current_revision_id
            )

            # Reader review ledger for the current revision.
            rr_lens_counts, rr_severity_counts = ReaderReviewRepository.open_counts_for_revision(
                conn, current_revision_id
            )
            open_reader_reviews = ReaderReviewRepository.list_open_by_revision(
                conn, current_revision_id
            )

            # Narrative editorial memo gate.
            active_memo = self._active_memo_for_current_revision(conn, chapter)
            memo_status = self._editorial_memo_status_from_row(active_memo)
            memo_blocks = (
                active_memo is None
                or active_memo["verdict"] != "ready_for_editor_decision"
                or len(json.loads(active_memo["blocking_issues"] or "[]")) > 0
            )

            if review_counts["S1"] > 0 or rr_severity_counts["S1"] > 0:
                verdict = ReviewVerdict.REJECT
            elif (
                review_counts["S2"] > 0
                or rr_severity_counts["S2"] > 0
                or lint_counts["blocking"] > 0
                or memo_blocks
            ):
                verdict = ReviewVerdict.CONCERNS
            else:
                verdict = ReviewVerdict.APPROVE

            ChapterRepository.set_state(conn, chapter["id"], "reviewed")
            AuditRepository.add(
                conn,
                book_id=book["id"],
                entity_type="chapter",
                entity_id=chapter["id"],
                action="review",
                details=json.dumps(
                    {
                        "verdict": verdict.value,
                        "severity_counts": review_counts,
                        "lint_counts": lint_counts,
                        "reader_review_severity_counts": rr_severity_counts,
                        "editorial_memo_id": memo_status.get("memo_id"),
                        "editorial_memo_verdict": memo_status.get("verdict"),
                        "editorial_memo_blocking_issues": memo_status.get(
                            "blocking_issue_count", 0
                        ),
                    },
                    ensure_ascii=False,
                ),
            )

            from app.novel_forge.models import ReviewFinding

            return ReviewResult(
                verdict=verdict,
                severity_counts=review_counts,
                lint_counts=lint_counts,
                findings=[ReviewFinding.model_validate(dict(r)) for r in open_findings],
                reader_review_summary=ReaderReviewSummary(
                    lens_counts=rr_lens_counts,
                    severity_counts=rr_severity_counts,
                    total_open=sum(rr_severity_counts.values()),
                ),
                reader_reviews=[
                    ReaderReview.model_validate(dict(r)) for r in open_reader_reviews
                ],
                editorial_memo_status=memo_status,
            )

    def approve_chapter(self, slug: str, number: int, note: str) -> Chapter:
        with self._conn() as conn:
            book = BookRepository.get_by_slug(conn, slug)
            if book is None:
                raise NovelForgeError(f"Book not found: {slug}")
            chapter = ChapterRepository.get_by_book_and_number(conn, book["id"], number)
            if chapter is None:
                raise NovelForgeError(f"Chapter {number} not found in book {slug}.")

            current_state = chapter["state"]
            if current_state not in _ALLOWED_APPROVE_STATES:
                raise NovelForgeError(
                    f"Approve requires chapter state reviewed. Current state: {current_state}."
                )

            current_revision_id = chapter["current_revision_id"]
            if current_revision_id is None:
                raise NovelForgeError(
                    f"Chapter {number} has no revision to approve."
                )

            lint_counts = FindingRepository.lint_counts_for_revision(
                conn, current_revision_id
            )
            if lint_counts["blocking"] > 0:
                raise NovelForgeError(
                    "Cannot approve: unresolved blocking lint findings on the current revision."
                )

            review_counts = FindingRepository.open_review_counts_for_revision(
                conn, current_revision_id
            )
            if review_counts["S1"] > 0 or review_counts["S2"] > 0:
                raise NovelForgeError(
                    "Cannot approve: unresolved S1/S2 review findings on the current revision."
                )

            _, rr_severity_counts = ReaderReviewRepository.open_counts_for_revision(
                conn, current_revision_id
            )
            if rr_severity_counts["S1"] > 0 or rr_severity_counts["S2"] > 0:
                raise NovelForgeError(
                    "Cannot approve: unresolved S1/S2 reader reviews on the current revision."
                )

            # Narrative editorial memo gate.
            active_memo = self._active_memo_for_current_revision(conn, chapter)
            if active_memo is None:
                raise NovelForgeError(
                    "Cannot approve: no active editorial memo for the current revision. "
                    "A coverage review must be recorded before approval."
                )
            if active_memo["verdict"] != "ready_for_editor_decision":
                raise NovelForgeError(
                    "Cannot approve: editorial memo verdict is not "
                    "'ready_for_editor_decision'."
                )
            blocking_issue_count = len(
                json.loads(active_memo["blocking_issues"] or "[]")
            )
            if blocking_issue_count > 0:
                raise NovelForgeError(
                    "Cannot approve: editorial memo has unresolved blocking issues."
                )

            ChapterRepository.set_state(conn, chapter["id"], "approved")
            AuditRepository.add(
                conn,
                book_id=book["id"],
                entity_type="chapter",
                entity_id=chapter["id"],
                action="approve",
                details=json.dumps({"note": note}, ensure_ascii=False),
            )
            row = ChapterRepository.get_by_id(conn, chapter["id"])

        return Chapter.model_validate(dict(row))

    # ------------------------------------------------------------------
    # Facts
    # ------------------------------------------------------------------
    def add_candidate_fact(
        self,
        slug: str,
        number: int,
        kind: str,
        subject: str,
        predicate: str,
        object: str,
        evidence: str,
    ) -> int:
        with self._conn() as conn:
            book = BookRepository.get_by_slug(conn, slug)
            if book is None:
                raise NovelForgeError(f"Book not found: {slug}")
            chapter = ChapterRepository.get_by_book_and_number(conn, book["id"], number)
            if chapter is None:
                raise NovelForgeError(f"Chapter {number} not found in book {slug}.")
            if chapter["current_revision_id"] is None:
                raise NovelForgeError(
                    f"Chapter {number} has no current revision; "
                    "add a revision before adding a candidate fact."
                )

            fact_id = FactRepository.add_candidate(
                conn,
                chapter_id=chapter["id"],
                revision_id=chapter["current_revision_id"],
                kind=kind,
                subject=subject,
                predicate=predicate,
                object=object,
                evidence=evidence,
            )
            AuditRepository.add(
                conn,
                book_id=book["id"],
                entity_type="candidate_fact",
                entity_id=fact_id,
                action="add",
                details=json.dumps(
                    {"subject": subject, "predicate": predicate, "object": object},
                    ensure_ascii=False,
                ),
            )
            return fact_id

    def approve_fact(self, candidate_id: int, note: str | None = None) -> None:
        with self._conn() as conn:
            candidate = FactRepository.get_candidate(conn, candidate_id)
            if candidate is None:
                raise NovelForgeError(f"Candidate fact not found: {candidate_id}")
            if candidate["status"] != "pending":
                raise NovelForgeError(
                    f"Candidate fact {candidate_id} is already {candidate['status']}."
                )

            chapter = ChapterRepository.get_by_id(conn, candidate["chapter_id"])
            if chapter is None:
                raise NovelForgeError(
                    f"Chapter for candidate fact {candidate_id} no longer exists."
                )
            book_id = chapter["book_id"]

            existing = FactRepository.get_canon_by_subject_predicate_book(
                conn, book_id, candidate["subject"], candidate["predicate"]
            )
            if existing is not None:
                raise NovelForgeError(
                    f"Canon conflict in book: {candidate['subject']} "
                    f"{candidate['predicate']} already exists as {existing['object']}."
                )

            FactRepository.update_candidate_status(conn, candidate_id, "approved", note)
            canon_id = FactRepository.add_canon(
                conn,
                source_candidate_id=candidate_id,
                book_id=book_id,
                chapter_id=candidate["chapter_id"],
                revision_id=candidate["revision_id"],
                kind=candidate["kind"],
                subject=candidate["subject"],
                predicate=candidate["predicate"],
                object=candidate["object"],
                evidence=candidate["evidence"],
            )

            AuditRepository.add(
                conn,
                book_id=book_id,
                entity_type="canon_fact",
                entity_id=canon_id,
                action="approve",
                details=json.dumps(
                    {
                        "source_candidate_id": candidate_id,
                        "subject": candidate["subject"],
                        "predicate": candidate["predicate"],
                        "object": candidate["object"],
                        "note": note,
                    },
                    ensure_ascii=False,
                ),
            )

    def reject_fact(self, candidate_id: int, note: str | None = None) -> None:
        with self._conn() as conn:
            candidate = FactRepository.get_candidate(conn, candidate_id)
            if candidate is None:
                raise NovelForgeError(f"Candidate fact not found: {candidate_id}")
            if candidate["status"] != "pending":
                raise NovelForgeError(
                    f"Candidate fact {candidate_id} is already {candidate['status']}."
                )

            FactRepository.update_candidate_status(conn, candidate_id, "rejected", note)
            cur = conn.execute(
                "SELECT book_id FROM chapters WHERE id = ?", (candidate["chapter_id"],)
            )
            book_id = cur.fetchone()["book_id"]
            AuditRepository.add(
                conn,
                book_id=book_id,
                entity_type="candidate_fact",
                entity_id=candidate_id,
                action="reject",
                details=json.dumps({"note": note}, ensure_ascii=False),
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
                    checked_fields = list(required_scene_contract)
                    if contract_version >= 3:
                        checked_fields.extend(required_scene_contract_v3)
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
                        elif key == "concrete_anchor":
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
                        elif is_missing_content(section.content):
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
            "- Do not paste this packet's instructions or metadata into the prose draft."
        )
        lines.append(
            "- Do not label the output as 'human-written' or claim human authorship automatically."
        )
        lines.append(
            "- When finished, produce a separate UTF-8 Markdown draft file outside the library for review; do not write it into the manuscript revisions directly."
        )
        lines.append("")

        lines.append("## Voice Bible")
        if voice_bible_text:
            lines.append(voice_bible_text)
        else:
            lines.append("**MISSING**: No Voice Bible has been written for this book.")
        lines.append("")

        lines.append("## Scene Contract")
        lines.append(scene_contract_text)
        lines.append("")

        lines.append("## Approved Canon Facts")
        if canon_rows:
            for row in canon_rows:
                lines.append(f"### {row['subject']} {row['predicate']}")
                lines.append(f"- object: {row['object']}")
                lines.append(f"- evidence: {row['evidence']}")
                lines.append(f"- source_chapter_id: {row['chapter_id']}")
                lines.append(f"- source_revision_id: {row['revision_id']}")
                lines.append("")
        else:
            lines.append("No approved canon facts for this book.")
            lines.append("")

        if predecessor_text is not None:
            lines.append(
                f"## Predecessor Context (approved chapter {chapter['number'] - 1}, last {previous_context_chars} characters)"
            )
            lines.append(
                "This is a continuity hand-off fragment. Do not copy it verbatim; use it to maintain voice and causal thread."
            )
            lines.append("```")
            lines.append(predecessor_text)
            lines.append("```")
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
            "- [ ] Checking these boxes does not guarantee quality; human/editor review remains the gate."
        )
        lines.append("")

        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Rollback
    # ------------------------------------------------------------------
    def rollback_chapter(
        self, slug: str, number: int, revision_id: int, note: str
    ) -> Chapter:
        with self._conn() as conn:
            book = BookRepository.get_by_slug(conn, slug)
            if book is None:
                raise NovelForgeError(f"Book not found: {slug}")
            chapter = ChapterRepository.get_by_book_and_number(conn, book["id"], number)
            if chapter is None:
                raise NovelForgeError(f"Chapter {number} not found in book {slug}.")

            if chapter["current_revision_id"] is None:
                raise NovelForgeError(
                    f"Chapter {number} has no revision to roll back."
                )
            if chapter["state"] == "draft":
                raise NovelForgeError(
                    f"Rollback is not allowed from draft state for chapter {number}."
                )

            old_rev = RevisionRepository.get_by_id(conn, revision_id)
            if old_rev is None or old_rev["chapter_id"] != chapter["id"]:
                raise NovelForgeError(
                    f"Revision {revision_id} does not belong to chapter {number}."
                )

            old_path = self.root / old_rev["file_path"]
            if not old_path.exists():
                raise NovelForgeError(
                    f"Revision file missing: {old_rev['file_path']}"
                )

            revs_dir = self._revisions_dir(slug, number)
            revs_dir.mkdir(parents=True, exist_ok=True)
            revision_number = ChapterRepository.get_next_revision_number(
                conn, chapter["id"]
            )
            content_hash = self._hash_file(old_path)
            ts = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
            dest_name = f"{revision_number:04d}-{ts}-{content_hash[:16]}.md"
            dest_path = revs_dir / dest_name
            shutil.copy2(old_path, dest_path)

            new_rev_id = RevisionRepository.create(
                conn,
                chapter_id=chapter["id"],
                revision_number=revision_number,
                file_path=str(dest_path.relative_to(self.root)),
                content_hash=content_hash,
                note=f"rollback from revision {revision_id}: {note}",
            )
            ChapterRepository.update_current_revision(
                conn, chapter["id"], new_rev_id, content_hash
            )
            ChapterRepository.set_state(conn, chapter["id"], "revised")

            AuditRepository.add(
                conn,
                book_id=book["id"],
                entity_type="chapter",
                entity_id=chapter["id"],
                action="rollback",
                details=json.dumps(
                    {
                        "from_revision_id": revision_id,
                        "new_revision_id": new_rev_id,
                        "note": note,
                    },
                    ensure_ascii=False,
                ),
            )
            row = ChapterRepository.get_by_id(conn, chapter["id"])

        return Chapter.model_validate(dict(row))

    # ------------------------------------------------------------------
    # Export
    # ------------------------------------------------------------------
    def export_book(self, slug: str, fmt: str) -> Path:
        fmt = fmt.lower()
        if fmt not in {"markdown", "docx", "epub", "pdf"}:
            raise NovelForgeError(f"Unsupported export format: {fmt}")

        with self._conn() as conn:
            book = BookRepository.get_by_slug(conn, slug)
            if book is None:
                raise NovelForgeError(f"Book not found: {slug}")

            chapters = ChapterRepository.list_by_book(conn, book["id"])
            approved = [c for c in chapters if c["state"] == "approved"]
            approved.sort(key=lambda c: c["number"])

            chapter_data = []
            for chapter in approved:
                rev = RevisionRepository.get_by_id(conn, chapter["current_revision_id"])
                chapter_data.append(
                    {
                        "number": chapter["number"],
                        "title": chapter["title"],
                        "revision_id": rev["id"],
                        "revision_number": rev["revision_number"],
                        "content_hash": rev["content_hash"],
                        "file_path": rev["file_path"],
                    }
                )

            md_path, manifest_path, manifest = compile_markdown(
                root=self.root,
                slug=book["slug"],
                title=book["title"],
                approved_chapters=chapter_data,
            )

            ExportRepository.create(
                conn,
                book_id=book["id"],
                format="markdown",
                file_path=str(md_path.relative_to(self.root)),
                manifest_path=str(manifest_path.relative_to(self.root)),
                status="success",
            )
            AuditRepository.add(
                conn,
                book_id=book["id"],
                entity_type="export",
                action="export",
                details=json.dumps(
                    {
                        "format": "markdown",
                        "status": "success",
                        "path": str(md_path),
                        "manifest": str(manifest_path),
                        "chapters": [c["number"] for c in approved],
                    },
                    ensure_ascii=False,
                ),
            )

            if fmt == "markdown":
                return md_path

            pandoc = find_pandoc()
            if pandoc is None:
                ExportRepository.create(
                    conn,
                    book_id=book["id"],
                    format=fmt,
                    status="failure",
                    message="Pandoc is not installed.",
                )
                AuditRepository.add(
                    conn,
                    book_id=book["id"],
                    entity_type="export",
                    action="export",
                    details=json.dumps(
                        {"format": fmt, "status": "failure", "reason": "no pandoc"},
                        ensure_ascii=False,
                    ),
                )
                raise NovelForgeError(
                    f"Pandoc is not installed. Cannot export to {fmt}."
                )

            exports_dir = self._exports_dir(slug)
            out_path = exports_dir / f"{slug}.{fmt}"
            try:
                convert_with_pandoc(pandoc, md_path, out_path)
            except Exception as exc:
                message = str(exc)
                ExportRepository.create(
                    conn,
                    book_id=book["id"],
                    format=fmt,
                    status="failure",
                    message=message,
                )
                AuditRepository.add(
                    conn,
                    book_id=book["id"],
                    entity_type="export",
                    action="export",
                    details=json.dumps(
                        {"format": fmt, "status": "failure", "error": message},
                        ensure_ascii=False,
                    ),
                )
                raise NovelForgeError(f"Export to {fmt} failed: {message}")

            ExportRepository.create(
                conn,
                book_id=book["id"],
                format=fmt,
                file_path=str(out_path.relative_to(self.root)),
                status="success",
            )
            AuditRepository.add(
                conn,
                book_id=book["id"],
                entity_type="export",
                action="export",
                details=json.dumps(
                    {"format": fmt, "status": "success", "path": str(out_path)},
                    ensure_ascii=False,
                ),
            )
            return out_path

    # ------------------------------------------------------------------
    # Audit
    # ------------------------------------------------------------------
    def audit(self, slug: str, limit: int | None = None) -> list[AuditEvent]:
        with self._conn() as conn:
            book = BookRepository.get_by_slug(conn, slug)
            if book is None:
                raise NovelForgeError(f"Book not found: {slug}")
            rows = AuditRepository.list(conn, book["id"], limit=limit)
            return [AuditEvent.model_validate(dict(r)) for r in rows]

    # ------------------------------------------------------------------
    # API helpers
    # ------------------------------------------------------------------
    def get_current_revision(self, slug: str, number: int) -> Revision | None:
        """Return the current revision metadata for a chapter, or None."""
        with self._conn() as conn:
            book = BookRepository.get_by_slug(conn, slug)
            if book is None:
                raise NovelForgeError(f"Book not found: {slug}")
            chapter = ChapterRepository.get_by_book_and_number(conn, book["id"], number)
            if chapter is None:
                raise NovelForgeError(f"Chapter {number} not found in book {slug}.")
            rev_id = chapter["current_revision_id"]
            if rev_id is None:
                return None
            row = RevisionRepository.get_by_id(conn, rev_id)
            if row is None:
                return None
            return Revision.model_validate(dict(row))

    def get_chapter_finding_counts(self, slug: str, number: int) -> dict[str, int]:
        """Return finding counts scoped to the current revision only."""
        with self._conn() as conn:
            book = BookRepository.get_by_slug(conn, slug)
            if book is None:
                raise NovelForgeError(f"Book not found: {slug}")
            chapter = ChapterRepository.get_by_book_and_number(conn, book["id"], number)
            if chapter is None:
                raise NovelForgeError(f"Chapter {number} not found in book {slug}.")
            rev_id = chapter["current_revision_id"]
            lint_counts = FindingRepository.lint_counts_for_revision(conn, rev_id)
            review_counts = FindingRepository.open_review_counts_for_revision(
                conn, rev_id
            )
            return {
                "blocking": lint_counts["blocking"],
                "advisory": lint_counts["advisory"],
                "S1": review_counts["S1"],
                "S2": review_counts["S2"],
                "S3": review_counts["S3"],
                "S4": review_counts["S4"],
            }

    # ------------------------------------------------------------------
    # Canon helpers for API
    # ------------------------------------------------------------------
    def list_canon_facts_for_chapter(
        self, slug: str, number: int
    ) -> list[sqlite3.Row]:
        with self._conn() as conn:
            book = BookRepository.get_by_slug(conn, slug)
            if book is None:
                raise NovelForgeError(f"Book not found: {slug}")
            chapter = ChapterRepository.get_by_book_and_number(conn, book["id"], number)
            if chapter is None:
                raise NovelForgeError(f"Chapter {number} not found in book {slug}.")
            return FactRepository.list_canon_by_chapter(conn, chapter["id"])
