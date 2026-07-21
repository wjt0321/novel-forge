"""Thin command wrapper for the automatic Novel Forge workflow."""

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.novel_forge.workflow import main


if __name__ == "__main__":
    raise SystemExit(main())
