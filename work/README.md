# Novel Forge Workspace Root

This directory contains per-book human-readable workspaces.

Each book gets its own subdirectory created automatically by:

```bash
PYTHONPATH=. python -m app.novel_forge.skill_adapter --root D:\\s-black-novel --confirm init-workspace init-workspace <slug>
```

Do not place book content directly here; use the adapter or CLI to manage books.
