"""Tests for the zfile CLI: compress (c), extract (x), list (l).

Each archive format round-trips; safety rules (no overwrite, -p only on 7z,
br only for a single file) are enforced.
"""

import subprocess
import sys
import zipfile

import pytest
from typer.testing import CliRunner

from zfile.cli import app

runner = CliRunner()


@pytest.fixture(autouse=True)
def in_tmpdir(monkeypatch, tmp_path):
    """Relative -o / default extraction land in the test dir."""
    monkeypatch.chdir(tmp_path)


def make_file(path, content=b"zfile test content hello"):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return path


def test_roundtrip_br(tmp_path):
    src = make_file(tmp_path / "notes.txt", b"google brotli data")
    out = runner.invoke(app, ["c", str(src)])
    assert out.exit_code == 0
    archive = tmp_path / "notes.txt.br"
    assert archive.exists()

    # extract without -o lands in the cwd
    dest = tmp_path / "out"
    dest.mkdir()
    (tmp_path / "cwd").mkdir()
    res = runner.invoke(app, ["x", str(archive), "-o", str(dest)])
    assert res.exit_code == 0
    assert (dest / "notes.txt").read_bytes() == b"google brotli data"


def test_default_single_file_is_br(tmp_path):
    src = make_file(tmp_path / "a.txt")
    res = runner.invoke(app, ["c", str(src)])
    assert res.exit_code == 0
    assert (tmp_path / "a.txt.br").exists()


def test_default_dir_or_multiple_files_is_7z(tmp_path, monkeypatch):
    d = tmp_path / "proj"
    (d / "sub").mkdir(parents=True)
    make_file(d / "f.txt")
    make_file(d / "sub/g.txt")

    res = runner.invoke(app, ["c", str(d)])
    assert res.exit_code == 0, res.output
    archive = tmp_path / "proj.7z"
    assert archive.exists()

    # giải nén không -o → vào thư mục hiện tại (cwd rỗng để không đụng thư mục nguồn)
    work = tmp_path / "work"
    work.mkdir()
    monkeypatch.chdir(work)
    res = runner.invoke(app, ["x", str(archive)])
    assert res.exit_code == 0, res.output
    assert (work / "proj/f.txt").read_bytes() == b"zfile test content hello"
    assert (work / "proj/sub/g.txt").read_bytes() == b"zfile test content hello"


def test_roundtrip_zip_with_dir(tmp_path):
    d = tmp_path / "docs"
    (d / "nested").mkdir(parents=True)
    make_file(d / "one.txt")
    make_file(d / "nested/two.txt")

    res = runner.invoke(app, ["c", str(d), "-f", "zip", "-o", "bundle.zip"])
    assert res.exit_code == 0, res.output
    assert zipfile.is_zipfile(tmp_path / "bundle.zip")

    dest = tmp_path / "out"
    res = runner.invoke(app, ["x", str(tmp_path / "bundle.zip"), "-o", str(dest)])
    assert res.exit_code == 0
    assert (dest / "docs/one.txt").read_bytes() == b"zfile test content hello"
    assert (dest / "docs/nested/two.txt").read_bytes() == b"zfile test content hello"


def test_roundtrip_7z(tmp_path):
    d = tmp_path / "doc"
    make_file(d / "seven.txt", b"py7zr data")
    res = runner.invoke(app, ["c", str(d), "-f", "7z", "-o", "a.7z"])
    assert res.exit_code == 0, res.output

    dest = tmp_path / "out"
    res = runner.invoke(app, ["x", str(tmp_path / "a.7z"), "-o", str(dest)])
    assert res.exit_code == 0
    assert (dest / "doc/seven.txt").read_bytes() == b"py7zr data"


def test_compress_multiple_without_output_fails(tmp_path):
    a = make_file(tmp_path / "a.txt")
    b = make_file(tmp_path / "b.txt")
    res = runner.invoke(app, ["c", str(a), str(b)])
    assert res.exit_code != 0
    assert "--output" in res.output


def test_compress_output_inside_input_not_corrupted(tmp_path):
    make_file(tmp_path / "d/f.txt", b"data")
    # -o points inside the directory being compressed
    res = runner.invoke(app, ["c", str(tmp_path / "d"), "-o", str(tmp_path / "d/out.zip")])
    assert res.exit_code == 0, res.output
    assert zipfile.is_zipfile(tmp_path / "d/out.zip")  # the open output was not zipped into itself
    # same for 7z: the archive must not contain itself
    res = runner.invoke(app, ["c", str(tmp_path / "d"), "-o", str(tmp_path / "d/out.7z")])
    assert res.exit_code == 0, res.output
    import py7zr

    with py7zr.SevenZipFile(tmp_path / "d/out.7z") as zf:
        assert "out.7z" not in [i.filename for i in zf.list()]


def run_via_main(tmp_path, args, capsys, monkeypatch):
    """Run through the real entrypoint main() so top-level error handling is exercised."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("sys.argv", ["zfile"] + args)
    with pytest.raises(SystemExit) as si:
        from zfile.cli import main

        main()
    return si.value.code, capsys.readouterr().out


def test_short_corrupt_br_does_not_hang(tmp_path):
    """Brotli stream decoder stuck on short garbage (5-byte junk) — the drain loop never ends and tilts."""
    (tmp_path / "bad.br").write_bytes(b"junk\n")
    proc = subprocess.run(
        [sys.executable, "-c", "from zfile.cli import main; main()", "x", "bad.br"],
        capture_output=True, timeout=10, cwd=tmp_path,
    )
    assert proc.returncode != 0
    assert b"Traceback" not in proc.stderr
    assert b"error" in proc.stdout


def test_corrupt_archives_fail_clean(tmp_path, capsys, monkeypatch):
    (tmp_path / "bad.zip").write_bytes(b"junk that is not a zip")
    (tmp_path / "bad.br").write_bytes(b"junk that is not brotli")

    code, out = run_via_main(tmp_path, ["l", "bad.zip"], capsys, monkeypatch)
    assert code != 0
    assert "Traceback" not in out
    assert "error" in out

    code, out = run_via_main(tmp_path, ["x", "bad.br"], capsys, monkeypatch)
    assert code != 0
    assert "Traceback" not in out
    assert "error" in out


def test_compress_output_parent_created(tmp_path):
    src = make_file(tmp_path / "src.txt")
    res = runner.invoke(app, ["c", str(src), "-o", str(tmp_path / "newdir/deep/x.zip")])
    assert res.exit_code == 0, res.output
    assert (tmp_path / "newdir/deep/x.zip").exists()


def test_large_file_br_roundtrip(tmp_path):
    src = tmp_path / "big.bin"
    src.write_bytes(b"x" * (2 << 20))  # 2 MB > the 1 MB streaming chunk
    res = runner.invoke(app, ["c", str(src)])
    assert res.exit_code == 0, res.output
    dest = tmp_path / "out"
    res = runner.invoke(app, ["x", str(tmp_path / "big.bin.br"), "-o", str(dest)])
    assert res.exit_code == 0, res.output
    assert (dest / "big.bin").read_bytes() == b"x" * (2 << 20)


def test_compress_missing_input_fails_clean(tmp_path):
    res = runner.invoke(app, ["c", "missing.txt", "missing2.txt", "-o", "out.7z"])
    assert res.exit_code != 0
    assert "Traceback" not in res.output  # clean error, not a traceback
    assert "no such file" in res.output
    assert not (tmp_path / "out.7z").exists()  # no leftover junk archive


def test_compress_duplicate_names_fails(tmp_path):
    make_file(tmp_path / "dir1/a.txt", b"one")
    make_file(tmp_path / "dir2/a.txt", b"two")
    res = runner.invoke(app, ["c", str(tmp_path / "dir1/a.txt"), str(tmp_path / "dir2/a.txt"), "-o", "out.zip"])
    assert res.exit_code != 0
    assert "Traceback" not in res.output
    assert "duplicate" in res.output
    assert not (tmp_path / "out.zip").exists()
    # same rule for 7z
    res = runner.invoke(app, ["c", str(tmp_path / "dir1/a.txt"), str(tmp_path / "dir2/a.txt"), "-o", "out.7z"])
    assert res.exit_code != 0
    assert not (tmp_path / "out.7z").exists()


def test_br_rejects_directory(tmp_path):
    d = tmp_path / "d"
    d.mkdir()
    res = runner.invoke(app, ["c", str(d), "-f", "br", "-o", "d.br"])
    assert res.exit_code != 0


def test_password_only_7z(tmp_path):
    d = tmp_path / "sec"
    make_file(d / "secret.txt", b"top secret")

    ok = runner.invoke(app, ["c", str(d), "-f", "7z", "-p", "pw123", "-o", "sec.7z"])
    assert ok.exit_code == 0, ok.output

    res = runner.invoke(app, ["x", str(tmp_path / "sec.7z"), "-o", str(tmp_path / "out")])
    assert res.exit_code != 0  # wrong/missing password refused

    good = runner.invoke(
        app, ["x", str(tmp_path / "sec.7z"), "-o", str(tmp_path / "out"), "-p", "pw123"]
    )
    assert good.exit_code == 0, good.output
    assert (tmp_path / "out/sec/secret.txt").read_bytes() == b"top secret"

    bad = runner.invoke(app, ["c", str(d), "-f", "zip", "-p", "pw", "-o", "s.zip"])
    assert bad.exit_code != 0


def test_extract_refuses_overwrite(tmp_path):
    src = make_file(tmp_path / "f.txt")
    archive = tmp_path / "f.txt.br"
    assert runner.invoke(app, ["c", str(src)]).exit_code == 0

    other = tmp_path / "out"
    other.mkdir()
    (other / "f.txt").write_bytes(b"old data")

    res = runner.invoke(app, ["x", str(archive), "-o", str(other)])
    assert res.exit_code != 0
    assert (other / "f.txt").read_bytes() == b"old data"

    res = runner.invoke(app, ["x", str(archive), "-o", str(other), "--overwrite"])
    assert res.exit_code == 0
    assert (other / "f.txt").read_bytes() == b"zfile test content hello"


def test_list_zip(tmp_path):
    d = tmp_path / "docs"
    make_file(d / "one.txt", b"a" * 100)
    make_file(d / "nested.txt", b"b" * 50)
    assert (
        runner.invoke(app, ["c", str(d), "-f", "zip", "-o", "d.zip"]).exit_code == 0
    )

    res = runner.invoke(app, ["l", str(tmp_path / "d.zip")])
    assert res.exit_code == 0
    assert "docs/one.txt" in res.output
    assert "docs/nested.txt" in res.output


def test_unknown_extension_fails(tmp_path):
    weird = tmp_path / "weird.rar"
    weird.write_bytes(b"junk")
    res = runner.invoke(app, ["x", str(weird)])
    assert res.exit_code != 0
    assert "format" in res.output.lower()
