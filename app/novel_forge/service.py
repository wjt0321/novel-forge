"""Business logic and state machine for Novel Forge."""

import hashlib
import json
import os
import re
import shutil
import sqlite3
import tempfile
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.novel_forge.db import get_connection, get_db_path, init_db
from app.novel_forge.export import (
    compile_markdown,
    convert_with_pandoc,
    find_pandoc,
    hash_text,
    now_iso,
)
from app.novel_forge.lint import _count_cjk_chars
from app.novel_forge.project_templates import ProjectTemplateError, init_book_project
from app.novel_forge.models import (
    AuditEvent,
    Book,
    BookSummary,
    Chapter,
    ChapterState,
    ChapterSummary,
    NovelForgeError,
    Revision,
)
from app.novel_forge.repository import (
    AuditRepository,
    BlindExperienceRepository,
    BookRepository,
    ChapterRepository,
    ExportRepository,
    FindingRepository,
    RevisionRepository,
    SceneContractRepository,
    VoiceBibleRepository,
)

from app.novel_forge.canon import CanonMixin
from app.novel_forge.planning import PlanningMixin
from app.novel_forge.quality import QualityMixin
from app.novel_forge.review_gates import ReviewGatesMixin


def _atomic_write(path: Path, content: str, encoding: str = "utf-8") -> None:
    """Write content to path atomically via a temp file + os.replace.

    On Windows, os.replace requires the destination to not exist or be on the
    same filesystem, which is satisfied since the temp file is created in the
    same directory.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = tempfile.NamedTemporaryFile(
        mode="w",
        encoding=encoding,
        dir=path.parent,
        prefix=f".{path.name}.",
        delete=False,
    )
    try:
        tmp.write(content)
        tmp.flush()
        os.fsync(tmp.fileno())
    finally:
        tmp.close()
    os.replace(tmp.name, str(path))



class NovelForgeService(QualityMixin, PlanningMixin, ReviewGatesMixin, CanonMixin):
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
        with get_connection(self.root) as conn:
            yield conn

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
        """Return True if the file looks like a mirror we generated.

        Checks both the first-line MIRROR marker AND the DO-NOT-EDIT warning
        in the header block, so that an accidental edit to the first line
        alone won't silently orphan the mirror.
        """
        if not path.exists():
            return False
        try:
            head = path.read_text(encoding="utf-8")[:400]
        except UnicodeDecodeError:
            return False
        return "<!-- MIRROR of" in head and "DO NOT EDIT" in head

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
                _atomic_write(mirror_path, mirror_content)

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
                    _atomic_write(
                        vb_mirror,
                        f"<!-- MIRROR of {voice_bible.current_file_path} -->\n\n{vb_body}",
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
                        _atomic_write(
                            sc_mirror,
                            f"<!-- MIRROR of {sc.current_file_path} -->\n\n{sc_body}",
                        )

        current_lines.extend([
            "",
            "The authoritative source is `library/<slug>/`. "
            "This file is regenerated by `refresh-workspace`.",
        ])
        if warnings:
            current_lines.extend(["", "## Warnings", ""])
            current_lines.extend(f"- {w}" for w in warnings)

        _atomic_write(work_root / "CURRENT.md", "\n".join(current_lines))

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

    def init_novel_project(
        self, slug: str, title: str, genre: str
    ) -> dict[str, Any]:
        """Create the new recommended `books/<slug>/` project layout.

        This is a filesystem-only operation and does not require or touch the
        SQLite-backed `library/` workflow. Existing files are never overwritten.
        """
        try:
            return init_book_project(self.root, slug, title, genre)
        except ProjectTemplateError as exc:
            raise NovelForgeError(str(exc)) from exc

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
                note="initial v4 template",
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
    def _require_formal_revision_length(self, from_file: Path) -> None:
        """Ensure a revision source is non-empty.

        Encoding validation is left to later stages so that legacy/non-UTF-8
        files can be copied into the library and reported by lint rather than
        crashing the revision write path.
        """
        if from_file.stat().st_size == 0:
            raise NovelForgeError("Revision source is empty.")

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
        self._require_formal_revision_length(from_file)

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

            # A new revision invalidates any previous blind experience review for
            # this chapter. The old review remains in the ledger but is superseded
            # so it cannot satisfy the current revision's approval gate.
            BlindExperienceRepository.supersede_active_for_chapter(
                conn, chapter["id"]
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
        allow_below_minimum: bool = False,
    ) -> dict[str, Any]:
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

        Short-story hard floor: the patched result must contain at least 5000
        CJK Han characters unless ``allow_below_minimum`` is explicitly set.
        This prevents local patches from silently shrinking a completed short
        story below the formal minimum.
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

        before_count = _count_cjk_chars(current_text)
        after_count = _count_cjk_chars(patched_text)
        MINIMUM_CJK = 5000
        if not allow_below_minimum and after_count < MINIMUM_CJK:
            raise NovelForgeError(
                f"Patch result has {after_count} CJK characters, below the "
                f"minimum {MINIMUM_CJK}. Use --allow-below-minimum only for "
                "exploratory drafts."
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
            chapter = self.write_revision(
                slug,
                number,
                tmp_path,
                note=patch_note,
                reopen_reason=reopen_reason,
            )
            return {
                "chapter": chapter,
                "before_count": before_count,
                "after_count": after_count,
            }
        finally:
            tmp_path.unlink(missing_ok=True)

    # ------------------------------------------------------------------
    # Lint
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
