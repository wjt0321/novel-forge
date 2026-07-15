"""Export helpers for Novel Forge."""

import hashlib
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from app.novel_forge.models import ExportManifest


def hash_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def compile_markdown(
    root: Path,
    slug: str,
    title: str,
    approved_chapters: list[dict],
) -> tuple[Path, Path, ExportManifest]:
    """Compile approved chapters into a single Markdown file and manifest.

    Each chapter dict must have keys: number, title, revision_id,
    revision_number, content_hash, file_path (relative to root).
    """
    exports_dir = root / "library" / slug / "exports"
    exports_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    md_path = exports_dir / f"{slug}-{ts}.md"

    source_revisions = []
    lines = [f"# {title}\n\n"]
    for chapter in approved_chapters:
        rev_path = root / chapter["file_path"]
        content = rev_path.read_text(encoding="utf-8")
        lines.append(f"## 第 {chapter['number']} 章 {chapter['title']}\n\n")
        lines.append(content)
        lines.append("\n\n")
        source_revisions.append(
            {
                "chapter_number": chapter["number"],
                "chapter_title": chapter["title"],
                "revision_id": chapter["revision_id"],
                "revision_number": chapter["revision_number"],
                "content_hash": chapter["content_hash"],
            }
        )

    compiled = "".join(lines)
    md_path.write_text(compiled, encoding="utf-8")

    manifest = ExportManifest(
        format="markdown",
        book_slug=slug,
        created_at=now_iso(),
        source_revisions=source_revisions,
        sha256=hash_text(compiled),
    )
    manifest_path = exports_dir / f"{slug}-{ts}-manifest.json"
    manifest_path.write_text(
        manifest.model_dump_json(indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return md_path, manifest_path, manifest


def find_pandoc() -> str | None:
    return shutil.which("pandoc")


def convert_with_pandoc(pandoc: str, md_path: Path, out_path: Path) -> None:
    """Call Pandoc to convert md_path to out_path. Raises on failure."""
    subprocess.run(
        [pandoc, str(md_path), "-o", str(out_path)],
        check=True,
        capture_output=True,
        text=True,
    )
