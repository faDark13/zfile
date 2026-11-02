"""PyInstaller runtime hook: point PyGObject at the GTK typelibs we copied.

PyInstaller's own gi hooks only collect typelibs for the module versions they
are configured for (Gtk 3.0 by default), so a plain `pyinstaller run_gui.py`
build ships no Gtk-4.0.typelib. The release workflow copies them into
gi_typelibs/ next to the bundle; this hook runs before `import gi` in the
frozen app so that directory is the first place searched.
"""

import os
import sys
from pathlib import Path

base = Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
for candidate in (base / "gi_typelibs", base / "_internal" / "gi_typelibs"):
    if candidate.is_dir():
        os.environ["GI_TYPELIB_PATH"] = str(candidate)
        break
