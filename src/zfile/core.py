"""zfile core: compress/extract/list logic, UI-free (no typer, no printing).

Raises ZfileError with user-facing messages; CLI prints "zfile: error — {msg}",
GUI shows the same message in a dialog. `progress` (optional) is called with a
completion fraction 0.0–1.0 wherever the format streams byte-wise (brotli only).
"""

from pathlib import Path

import brotli
import py7zr
import zipfile

FORMATS = ("br", "zip", "7z")
CHUNK = 1 << 20  # 1 MiB streaming chunk for brotli


class ZfileError(Exception):
    """User-facing error; message is shown as-is."""


def compress(
    paths: list[Path],
    format: str | None = None,
    password: str | None = None,
    output: Path | None = None,
    overwrite: bool = False,
    progress=None,
) -> Path:
    """Compress 1+ files/directories into `output` (or a default name) and return its path."""
    if not paths:
        raise ZfileError("need at least one file or directory to compress")
    paths = [Path(p) for p in paths]
    for p in paths:
        if not p.exists():
            raise ZfileError(f"no such file: {p}")

    # -o names the format (out.zip → zip); an explicit -f wins; otherwise default by input shape
    if format is None and output is not None:
        inferred = output.suffix.lower().lstrip(".")
        if inferred in FORMATS:
            format = inferred
    if format is None:
        fmt = "br" if len(paths) == 1 and paths[0].is_file() else "7z"
    else:
        if format not in FORMATS:
            raise ZfileError(f"invalid --format '{format}' (only br, zip, 7z)")
        fmt = format
    if password and fmt != "7z":
        raise ZfileError("--password is only supported for the 7z format")

    if fmt == "br" and not (len(paths) == 1 and paths[0].is_file()):
        raise ZfileError(
            "brotli can only compress a single file — "
            "use --format zip or 7z for directories/multiple files"
        )

    if output is None:
        if len(paths) > 1:
            raise ZfileError("compressing multiple items → name the archive with --output")
        # br keeps the original suffix (notes.txt → notes.txt.br); zip/7z replace it (proj → proj.7z)
        p = paths[0]
        out = Path(str(p) + ".br") if fmt == "br" else p.with_suffix("." + fmt)
    else:
        out = output
    out.parent.mkdir(parents=True, exist_ok=True)
    if out.exists() and not overwrite:
        raise ZfileError(f"archive already exists: {out} — use --overwrite to replace it")

    # collect (file, arcname) once; arcname is relative to the input's parent
    items = []
    for p in paths:
        files = sorted(f for f in p.rglob("*") if f.is_file()) if p.is_dir() else [p]
        items += [(f, f.relative_to(p.parent)) for f in files]
    # skip the output file itself: zipping it while it's open corrupts the archive
    items = [(f, arc) for f, arc in items if f.resolve() != out.resolve()]
    if len(items) != len({arc for _, arc in items}):
        raise ZfileError("duplicate names in archive — inputs must have distinct arcnames")

    if fmt == "br":
        # stream in chunks: no whole-file RAM cost on big inputs
        comp = brotli.Compressor()
        src = paths[0]
        total = src.stat().st_size
        with open(src, "rb") as f, open(out, "wb") as dst:
            for chunk in iter(lambda: f.read(CHUNK), b""):
                dst.write(comp.process(chunk))
                if progress:
                    progress(min(1.0, f.tell() / total) if total else 1.0)
            dst.write(comp.finish())
            if progress:
                progress(1.0)
    elif fmt == "zip":
        with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zf:
            for f, arc in items:
                zf.write(f, arc)
    else:
        with py7zr.SevenZipFile(out, "w", password=password or None) as zf:
            # walk from our own (filtered) list: writeall re-walks live and
            # would swallow the open output file into its own archive
            for f, arc in items:
                zf.write(f, arc)
    return out


def get_archive_format(archive: Path) -> str:
    fmt = archive.suffix.lower().lstrip(".")
    if fmt not in FORMATS:
        raise ZfileError(
            f"unrecognized format '{archive.suffix}' " "(supported: .br, .zip, .7z)"
        )
    return fmt


def extract(
    archive: Path,
    output: Path | None = None,
    password: str | None = None,
    overwrite: bool = False,
    progress=None,
) -> Path:
    """Extract `archive` (format auto-detected by suffix) and return where it went."""
    archive = Path(archive)
    if not archive.is_file():
        raise ZfileError(f"no such file: {archive}")
    fmt = get_archive_format(archive)

    if fmt == "br":
        target = archive.name.removesuffix(".br")
        target = (Path(output) / target) if output is not None else Path(target)
        if target.exists() and not overwrite:
            raise ZfileError(f"target file already exists: {target} — use --overwrite to replace it")
        target.parent.mkdir(parents=True, exist_ok=True)
        dec = brotli.Decompressor()
        with open(archive, "rb") as src, open(target, "wb") as dst:
            for chunk in iter(lambda: src.read(CHUNK), b""):
                dst.write(dec.process(chunk))
                if progress:
                    progress(min(1.0, src.tell() / archive.stat().st_size))
            while not dec.is_finished():
                piece = dec.process(b"")
                if not piece:
                    # no remaining input and no output → stream is corrupt; brotli's
                    # decoder silently stalls on short garbage instead of raising
                    raise ZfileError(f"{archive} is not valid brotli data")
                dst.write(piece)
            if progress:
                progress(1.0)
        return target

    # zip / 7z: extract into a directory
    dest = Path(output) if output is not None else Path(".")
    if fmt == "zip":
        with zipfile.ZipFile(archive) as zf:
            names = [n for n in zf.namelist() if not n.endswith("/")]
            _check_slip(names, dest)
            _check_collisions(names, dest, overwrite)
            zf.extractall(dest)
    else:
        with py7zr.SevenZipFile(archive, password=password or None) as zf:
            if zf.needs_password() and not password:
                raise ZfileError("this archive needs a 7z password — try -p")
            names = [i.filename for i in zf.list() if not i.is_directory]
            _check_slip(names, dest)
            _check_collisions(names, dest, overwrite)
            zf.extractall(dest)
    return dest


def _check_slip(names: list[str], dest: Path) -> None:
    """Refuse path traversal: a hostile archive must not write outside dest."""
    root = dest.resolve()
    for name in names:
        target = (dest / name).resolve()
        if target != root and root not in target.parents:
            raise ZfileError(f"unsafe path in archive: {name}")


def _check_collisions(names: list[str], dest: Path, overwrite: bool) -> None:
    """Refuse to extract over existing files unless overwrite is given."""
    if overwrite:
        return
    for name in names:
        if (dest / name).exists():
            raise ZfileError(f"{dest / name} already exists — use --overwrite to replace it")


def list_contents(archive: Path, password: str | None = None) -> list[tuple[str, int]]:
    """List archive contents as (filename, size) pairs; size may be 0 for brotli streams."""
    archive = Path(archive)
    if not archive.is_file():
        raise ZfileError(f"no such file: {archive}")
    fmt = get_archive_format(archive)

    if fmt == "br":
        return [(archive.name.removesuffix(".br"), 0)]
    if fmt == "zip":
        with zipfile.ZipFile(archive) as zf:
            return [(info.filename, info.file_size) for info in zf.infolist()]
    with py7zr.SevenZipFile(archive, password=password or None) as zf:
        return [(i.filename, i.uncompressed) for i in zf.list()]
