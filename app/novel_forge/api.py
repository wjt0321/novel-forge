"""FastAPI local API for Novel Forge."""

from pathlib import Path

from fastapi import FastAPI, HTTPException

from app.novel_forge.models import AuditEvent, Book, BookSummary, ChapterSummary
from app.novel_forge.service import NovelForgeError, NovelForgeService


def create_app(root: Path) -> FastAPI:
    """Create a FastAPI app bound to a project root."""
    root = Path(root).resolve()
    svc = NovelForgeService(root)

    app = FastAPI(title="S-Black Novel Forge API", version="0.1.0")

    @app.get("/health")
    def health() -> dict:
        return {"status": "ok", "root": str(root)}

    @app.get("/books")
    def list_books() -> list[BookSummary]:
        return svc.list_books()

    @app.get("/books/{slug}")
    def get_book(slug: str) -> Book:
        try:
            return svc.get_book(slug)
        except NovelForgeError as exc:
            raise HTTPException(status_code=404, detail=exc.message)

    @app.get("/books/{slug}/chapters")
    def list_chapters(slug: str) -> list[ChapterSummary]:
        try:
            return svc.list_chapters(slug)
        except NovelForgeError as exc:
            raise HTTPException(status_code=404, detail=exc.message)

    @app.get("/books/{slug}/chapters/{number}")
    def get_chapter(slug: str, number: int) -> dict:
        try:
            chapter = svc.get_chapter(slug, number)
            current_revision = svc.get_current_revision(slug, number)
            finding_counts = svc.get_chapter_finding_counts(slug, number)
            canon_rows = svc.list_canon_facts_for_chapter(slug, number)
            canon_facts = [
                {
                    "kind": r["kind"],
                    "subject": r["subject"],
                    "predicate": r["predicate"],
                    "object": r["object"],
                    "evidence": r["evidence"],
                }
                for r in canon_rows
            ]
            return {
                "id": chapter.id,
                "book_id": chapter.book_id,
                "number": chapter.number,
                "title": chapter.title,
                "state": chapter.state.value,
                "current_revision": {
                    "id": current_revision.id,
                    "number": current_revision.revision_number,
                    "hash": current_revision.content_hash,
                    "file_path": current_revision.file_path,
                }
                if current_revision
                else None,
                "current_revision_id": chapter.current_revision_id,
                "current_revision_number": chapter.current_revision_number,
                "current_hash": chapter.current_hash,
                "finding_counts": finding_counts,
                "canon_facts": canon_facts,
                # No full body returned.
            }
        except NovelForgeError as exc:
            raise HTTPException(status_code=404, detail=exc.message)

    @app.get("/books/{slug}/audit")
    def get_audit(slug: str, limit: int | None = None) -> list[AuditEvent]:
        try:
            return svc.audit(slug, limit=limit)
        except NovelForgeError as exc:
            raise HTTPException(status_code=404, detail=exc.message)

    return app
