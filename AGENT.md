# zfile

CLI app to compress and extract files. Run `zfile <command>`.

## Stack

- **Typer** (by the FastAPI team) for the CLI: `src/zfile/cli.py`, `zfile = "zfile.cli:main"` entry point.
- **GTK4** (PyGObject, system libs `libgtk-4-1` + `gir1.2-gtk-4.0`) for the GUI: `src/zfile/gui.py`, `zfile-gui = "zfile.gui:main"` entry point. One window, 3 pages (Compress / Extract / List) mirroring the CLI commands; work runs in a background thread, brotli reports a byte fraction, zip/7z pulse.
- **Split**: all archive logic (brotli/zip/7z) lives in `src/zfile/core.py` (UI-free, raises `ZfileError`); `cli.py` and `gui.py` are thin front-ends on top of it.
- **Release builds**: `.github/workflows/release.yml` builds the GUI on Windows, Linux and macOS (PyInstaller, entry script `run_gui.py`) and attaches `zfile-gui-windows-x64.zip`, `zfile-gui-linux-x64.tar.gz` and `zfile-gui-macos-arm64.tar.gz` to GitHub Releases for `v*` tags. Windows bundles the GTK4 runtime (MSYS2); Linux/macOS bundles use the system's GTK4 (`apt install libgtk-4-1 gir1.2-gtk-4.0` / `brew install gtk4`) — macOS ships a `zfile-gui.sh` launcher that points GI/DYLD at Homebrew.
- Compression formats/algorithms:
  - **Brotli** (Google, package `brotli`) — Google's compression algorithm for this project.
  - **zip** — Python stdlib `zipfile`, no extra dependency.
  - **7zip/7z** — `py7zr`.

## Status

Working. CLI commands in `src/zfile/cli.py`: `zfile c` (compress: single file default br, dir/multiple default 7z, format inferred from `-o` suffix, `-f`/`-p`/`-o`/`--overwrite`), `zfile x` (extract, format auto-detected by suffix, `-p` for 7z), `zfile l` (list contents). brotli streams in 1 MiB chunks (no whole-file RAM). Top-level error handling in `main()` — corrupt inputs exit 2, no tracebacks. `zipfile` can create but not encrypt zips → password is 7z-only.

GUI `src/zfile/gui.py` mirrors all three commands with the same rules (password dialogs on encrypted 7z, overwrite checkboxes). NOT smoke-tested locally: this machine has no GTK4 libs yet (`sudo apt install libgtk-4-1 gir1.2-gtk-4.0` first). The release workflows are untested until the first tag push (Linux is the one with a real launch test, under Xvfb).

## Mode

Ponytail mode is active by default in this project (skill id: `ponytail`; switch level: `/ponytail lite|full|ultra`). Smallest change that fully solves the task.
