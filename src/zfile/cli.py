"""zfile CLI: compress & extract files (brotli, zip, 7z).

Commands: c (compress), x (extract), l (list contents).
All archive logic lives in zfile.core; this module is the typer front-end.
"""

import sys
from pathlib import Path
from typing import Annotated, Optional

import typer

from zfile import core
from zfile.core import ZfileError

app = typer.Typer(
    help="zfile — compress & extract files (br, zip, 7z).",
    add_completion=False,
)


def fail(msg: str) -> None:
    typer.echo(f"zfile: error — {msg}")
    raise typer.Exit(2)


@app.command()
def c(
    paths: Annotated[Optional[list[Path]], typer.Argument(help="Files/directories to compress")],
    format: Annotated[Optional[str], typer.Option("--format", "-f", help="br|zip|7z")] = None,
    password: Annotated[Optional[str], typer.Option("--password", "-p", help="Password (7z only)")] = None,
    output: Annotated[Optional[Path], typer.Option("--output", "-o", help="Archive name to write")] = None,
    overwrite: Annotated[bool, typer.Option("--overwrite", "-y", help="Overwrite an existing archive")] = False,
) -> None:
    """Compress 1+ files/directories. Default: single file → br, directory/multiple → 7z."""
    if not paths:
        fail("need at least one file or directory to compress")
    try:
        out = core.compress(list(paths), format, password, output, overwrite)
    except ZfileError as exc:
        fail(str(exc))
    typer.echo(f"compressing → {out}")
    typer.echo("done ✔")


@app.command()
def x(
    archive: Annotated[Optional[Path], typer.Argument(help="Archive file (.br/.zip/.7z)")],
    output: Annotated[
        Optional[Path],
        typer.Option("--output", "-o", help="Destination directory (default: current directory)"),
    ] = None,
    password: Annotated[Optional[str], typer.Option("--password", "-p", help="Password (7z)")] = None,
    overwrite: Annotated[bool, typer.Option("--overwrite", "-y", help="Overwrite existing files")] = False,
) -> None:
    """Extract — format auto-detected from the file suffix."""
    if archive is None:
        fail("need an archive to extract")
    try:
        target = core.extract(archive, output, password, overwrite)
    except ZfileError as exc:
        fail(str(exc))
    typer.echo(f"extracted → {target}")


@app.command()
def l(
    archive: Annotated[Optional[Path], typer.Argument(help="Archive file (.br/.zip/.7z)")],
    password: Annotated[Optional[str], typer.Option("--password", "-p", help="Password (7z)")] = None,
) -> None:
    """List the contents of an archive."""
    if archive is None:
        fail("need an archive to list")
    try:
        contents = core.list_contents(Path(archive), password)
    except ZfileError as exc:
        fail(str(exc))
    for name, size in contents:
        typer.echo(f"{name}" if size == 0 else f"{name}  ({size} bytes)")


def main() -> None:
    try:
        app()
    except typer.Exit:
        raise
    except Exception as exc:  # corrupt/garbage inputs and library errors — clean error, no traceback
        typer.echo(f"zfile: error — unexpected failure: {exc}")
        sys.exit(2)  # fail() would raise inside this except block and leak the Exit


if __name__ == "__main__":
    main()
