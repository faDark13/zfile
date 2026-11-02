"""Smoke test that the setup works: the app package and every dependency import,
and Brotli actually compresses on this Python.
"""


def test_deps_import():
    import typer  # CLI
    import brotli  # Google
    import py7zr  # 7zip

    assert brotli.decompress(brotli.compress(b"zfile")) == b"zfile"


def test_package_imports():
    import zfile

    assert zfile.__name__ == "zfile"
