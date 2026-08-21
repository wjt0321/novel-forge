"""FastAPI local API for Novel Forge."""

from pathlib import Path

from fastapi import FastAPI, HTTPException, Query

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
            # Single-connection detail payload (was five separate calls,
            # each opening its own database connection).
            return svc.chapter_detail(slug, number)
        except NovelForgeError as exc:
            raise HTTPException(status_code=404, detail=exc.message)

    @app.get("/books/{slug}/audit")
    def get_audit(
        slug: str,
        limit: int | None = Query(default=None, ge=1, le=1000),
    ) -> list[AuditEvent]:
        try:
            return svc.audit(slug, limit=limit)
        except NovelForgeError as exc:
            raise HTTPException(status_code=404, detail=exc.message)

    return app
