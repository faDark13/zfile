"""Core logic (used by both CLI and GTK4 GUI): round-trips + user-facing errors."""

import pytest

from zfile import core
from zfile.core import ZfileError


def test_roundtrip_and_list(tmp_path):
    src = tmp_path / "a.txt"
    src.write_bytes(b"core data")
    out = core.compress([src], "zip")
    assert out == tmp_path / "a.zip" and out.exists()
    assert core.list_contents(out) == [("a.txt", 9)]
    dest = tmp_path / "out"
    assert core.extract(out, dest) == dest
    assert (dest / "a.txt").read_bytes() == b"core data"


def test_user_errors_are_explicit(tmp_path):
    src = tmp_path / "x.txt"
    src.write_bytes(b"data")
    with pytest.raises(ZfileError, match="no such file"):
        core.compress([tmp_path / "missing.txt"])
    with pytest.raises(ZfileError, match="--password"):
        core.compress([src], "zip", password="pw")
    with pytest.raises(ZfileError, match="no such file"):
        core.extract(tmp_path / "nope.7z", overwrite=False)

    # the real password rule needs an actual archive
    d = tmp_path / "d"
    d.mkdir()
    (d / "s.txt").write_bytes(b"secret")
    locked = core.compress([d], "7z", password="pw123", output=tmp_path / "d.7z")
    with pytest.raises(ZfileError, match="password"):
        core.extract(locked, tmp_path / "out")
    core.extract(locked, tmp_path / "out", password="pw123")
    assert (tmp_path / "out/d/s.txt").read_bytes() == b"secret"


def test_zip_slip_entry_is_blocked(tmp_path):
    import zipfile

    hostile = tmp_path / "hostile.zip"
    with zipfile.ZipFile(hostile, "w") as zf:
        zf.writestr("../outside.txt", b"evil")  # escapes dest when extracted
        zf.writestr("normal.txt", b"ok")
    dest = tmp_path / "dest"
    with pytest.raises(ZfileError, match="unsafe path"):
        core.extract(hostile, dest)
    assert not (tmp_path / "outside.txt").exists()
