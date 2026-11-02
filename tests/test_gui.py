"""GUI structure checks (the GUI itself needs GTK4 + a display to run)."""

import re
from pathlib import Path

GUI = Path(__file__).resolve().parents[1] / "src" / "zfile" / "gui.py"


def method_block(name: str) -> str:
    """Source of one Win method, up to the next same-indent def."""
    text = GUI.read_text(encoding="utf-8")  # gui.py holds Vietnamese strings
    match = re.search(rf"\n    def {re.escape(name)}\(", text)
    assert match, f"{name} not found in gui.py"
    tail = text[match.start():]
    nxt = re.search(r"\n    def \w+\(", tail[1:5_000])
    return tail[: nxt.start() + 1] if nxt else tail


def test_every_gui_page_returns_its_box():
    # a page returning None lands as add_titled(None, …) → cryptic GTK error at startup
    for page in ("_compress_page", "_extract_page", "_list_page"):
        assert "return box" in method_block(page), f"{page} must return its box"


def test_page_names_used_in_add_titled_exist():
    text = GUI.read_text(encoding="utf-8")
    for page in re.findall(r"add_titled\(self\.(_\w+_page)\(\)", text):
        assert f"def {page}(" in text, f"add_titled references missing {page}"
