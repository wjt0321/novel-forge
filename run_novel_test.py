from pathlib import Path

from app.novel_forge.project_templates import init_book_project

root = Path.cwd()
result = init_book_project(
    root=root,
    slug="穿越问道",
    title="穿越问道",
    genre="穿越修仙悬疑",
)
print(result["book_dir"])
