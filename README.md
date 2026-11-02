# zfile

Compress and extract files from the command line — **brotli**, **zip** and **7z** — with a
GTK4 desktop window for the same three actions (compress / extract / list).

## Install

```bash
uv tool install .      # or: pipx install .
zfile --help
```

The CLI needs only Python ≥ 3.12. The GUI needs GTK4 and PyGObject as system packages:

| Platform | Command |
|----------|---------|
| Debian / Ubuntu | `sudo apt install libgtk-4-1 gir1.2-gtk-4.0 gir1.2-girepository-3.0` |
| Fedora | `sudo dnf install gtk4 python3-gobject` |
| macOS (Homebrew) | `brew install gtk4 gobject-introspection` |
| Arch | `sudo pacman -S gtk4 python-gobject` |

## CLI

```bash
zfile c <paths...>              # compress; single file → .br, dir/multiple → .7z
zfile c notes.txt -f zip -o notes.zip
zfile c src/ -o src.7z -p secret      # password works for 7z only
zfile x src.7z -o out/                # format detected from the suffix
zfile l src.7z                        # list contents
```

| Command | Options |
|---------|---------|
| `zfile c` | `-f/--format br\|zip\|7z`, `-p/--password` (7z), `-o/--output`, `-y/--overwrite` |
| `zfile x` | `-o/--output` destination dir, `-p/--password` (7z), `-y/--overwrite` |
| `zfile l` | `-p/--password` (7z) |

Rules: brotli holds exactly one file; `zipfile` cannot encrypt zips, so passwords are 7z-only;
`-o`'s suffix wins over `-f`; existing archives/files are not overwritten without `-y`.
Corrupt input exits with code 2 and a one-line message, never a traceback.

## GUI

```bash
zfile-gui
```

One window with three pages mirroring the commands. Long work runs in a background thread, brotli
shows real byte progress. On an encrypted 7z it asks for the password; overwriting is a checkbox.

## Downloads

`v*` tags publish three archives to the [Releases](../../releases) page. The CLI inside each needs
nothing; the GUI needs GTK4 from the table above.

| File | Note |
|------|------|
| `zfile-gui-windows-x64.zip` | GTK4 runtime bundled — unzip and run `zfile-gui.exe` |
| `zfile-gui-linux-x64.tar.gz` | needs the distro GTK4 packages above |
| `zfile-gui-macos-arm64.tar.gz` | Apple silicon; run `./zfile-gui.sh` (needs `brew install gtk4 gobject-introspection`) |

## Development

```bash
uv sync
uv run zfile --help
uv run zfile-gui
uv run pytest
```

Archive logic lives in `src/zfile/core.py` (UI-free); `cli.py` and `gui.py` are thin front-ends.
Builds: `.github/workflows/release.yml` (PyInstaller on Windows, Linux and macOS), entry script
`run_gui.py`.

## License

GNU General Public License v3.0 — see [LICENSE](LICENSE).
