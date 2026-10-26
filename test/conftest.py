"""Root test modules are historical; active Python checks live in active/."""

from pathlib import Path

collect_ignore = [p.name for p in Path(__file__).parent.glob("test*.py")]
