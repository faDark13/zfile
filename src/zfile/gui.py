"""zfile GUI: GTK4 window for compress / extract / list.

Same rules as the CLI (shared zfile.core): password is 7z-only, brotli is a
single file, extraction refuses clobbering without overwrite. Work runs in a
background thread so the window stays responsive; brotli reports a real byte
fraction, zip/7z pulse. GTK-native widgets keep focus/contrast/a11y defaults.
"""

import sys
import threading
from pathlib import Path

try:
    import gi
    gi.require_version("Gtk", "4.0")
    from gi.repository import Gtk, GLib
except (ImportError, ValueError):
    print(
        "zfile-gui: error — GTK4 not available "
        "(Ubuntu: sudo apt install libgtk-4-1 gir1.2-gtk-4.0)",
        file=sys.stderr,
    )
    sys.exit(2)

from zfile import core
from zfile.core import ZfileError


class _Pick:
    """File-chooser descriptor: single file / multiple files / a folder."""

    def __init__(self, multiple=False, folder=False):
        self.multiple = multiple
        self.folder = folder


def fmt_size(n: int) -> str:
    for unit in ("B", "KiB", "MiB", "GiB"):
        if n < 1024:
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} TiB"


class Win(Gtk.ApplicationWindow):
    def __init__(self, app):
        super().__init__(application=app, title="zfile", default_width=620, default_height=560)
        self.busy = 0
        self._bars: list[Gtk.ProgressBar] = []

        stack = Gtk.Stack(transition_type=Gtk.StackTransitionType.SLIDE_LEFT_RIGHT)
        header = Gtk.HeaderBar()
        header.set_title_widget(Gtk.StackSwitcher(stack=stack))
        self.set_titlebar(header)
        stack.add_titled(self._compress_page(), "c", "Nén")
        stack.add_titled(self._extract_page(), "x", "Giải nén")
        stack.add_titled(self._list_page(), "l", "Xem nội dung")
        self.set_child(stack)

        # one pulse loop: bars pulse while a background job has no fraction
        GLib.timeout_add(90, self._pulse)

    # ---------- shared helpers ----------

    def _page(self) -> Gtk.Box:
        return Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL, spacing=12,
            margin_top=18, margin_bottom=18, margin_start=18, margin_end=18,
        )

    def _row(self, text: str, widget, hint: str | None = None) -> Gtk.Box:
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        row.append(Gtk.Label(label=text, xalign=0))
        widget.hexpand = True
        row.append(widget)
        if hint:  # one-word scope note, e.g. password applies to 7z only
            row.append(Gtk.Label(label=hint, xalign=1))
        return row

    def _status(self) -> Gtk.Label:
        return Gtk.Label(xalign=0, wrap=True, max_width_chars=60)

    def _chooser(self, text: str, pick: _Pick, on_pick) -> Gtk.Button:
        btn = Gtk.Button(label=text)

        def clicked(*_):
            dlg = Gtk.FileDialog()
            if pick.multiple:
                dlg.open_multiple(self, None, self._picked(dlg, on_pick, "open_multiple_finish"))
            elif pick.folder:
                dlg.select_folder(self, None, self._picked(dlg, on_pick, "select_folder_finish"))
            else:
                dlg.open(self, None, self._picked(dlg, on_pick, "open_finish"))

        btn.connect("clicked", clicked)
        return btn

    def _picked(self, dlg, on_pick, finish_name):
        def cb(_dlg, result):
            try:
                f = getattr(dlg, finish_name)(result)
            except GLib.Error:
                return  # dialog cancelled — nothing to pick
            if f is None:
                return
            if finish_name == "open_multiple_finish":
                on_pick([Path(f.get_item(i).get_path()) for i in range(f.get_n_items())])
            else:
                on_pick(Path(f.get_path()))

        return cb

    def _spawn(self, fn, done):
        """Run `fn` in a daemon thread; deliver (result, error) on the main loop."""
        self.busy += 1

        def run():
            result, err = None, None
            try:
                result = fn()
            except BaseException as exc:
                err = exc
            GLib.idle_add(lambda: (done(result, err), GLib.SOURCE_REMOVE))

        threading.Thread(target=run, daemon=True).start()

    def _pulse(self):
        if self.busy:
            for bar in self._bars:
                bar.pulse()
        return GLib.SOURCE_CONTINUE  # single loop for the window's lifetime

    def _archive_filter(self) -> Gtk.FileFilter:
        f = Gtk.FileFilter()
        f.set_name("Kho lưu (.br/.zip/.7z)")
        for pattern in ("*.br", "*.zip", "*.7z"):
            f.add_pattern(pattern)
        return f

    def _ask_password(self, msg: str, cb) -> None:
        dlg = Gtk.Window(transient_for=self, modal=True, title="Mật khẩu 7z", default_width=420)
        box = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL, spacing=12,
            margin_top=18, margin_bottom=18, margin_start=18, margin_end=18,
        )
        box.append(Gtk.Label(label=msg, wrap=True, xalign=0))
        entry = Gtk.PasswordEntry(show_peek_icon=True, activates_default=True)
        box.append(entry)
        buttons = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8, halign=Gtk.Align.END)
        cancel = Gtk.Button(label="Hủy")
        cancel.connect("clicked", lambda *_: dlg.destroy())
        ok = Gtk.Button(label="Tiếp tục", css_classes=["suggested-action"])
        ok.connect("clicked", lambda *_: (dlg.destroy(), cb(entry.get_text())))
        buttons.append(cancel)
        buttons.append(ok)
        box.append(buttons)
        dlg.set_child(box)
        dlg.set_default_widget(ok)
        dlg.present()

    def _flag(self, status: Gtk.Label, err) -> None:
        """One status label per page handles both ok and error text."""
        if isinstance(err, ZfileError):
            status.set_text(f"⚠ {err}")
        else:  # library crash — explain through a dialog too
            status.set_text(f"⚠ Lỗi hệ thống: {err}")
            dlg = Gtk.AlertDialog(message="Có gì đó hỏng rồi", detail=str(err))
            dlg.show(self)

    # ---------- page: compress (CLI `c`) ----------

    def _compress_page(self):
        box = self._page()
        self.c_paths: list[Path] = []
        self.c_btn.set_sensitive(False) if hasattr(self, "c_btn") else None  # set again below

        files_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        files_row.append(self._chooser("Thêm file…", _Pick(multiple=True), self._c_add))
        files_row.append(self._chooser("Thêm thư mục…", _Pick(folder=True), self._c_add))
        box.append(files_row)
        self.c_files_label = Gtk.Label(xalign=0, wrap=True, max_width_chars=60, label="Chưa chọn gì")
        box.append(self.c_files_label)

        self.c_fmt = Gtk.DropDown.new_from_strings(["Tự động", "br", "zip", "7z"])
        box.append(self._row("Định dạng:", self.c_fmt))
        self.c_pass = Gtk.PasswordEntry(show_peek_icon=True)
        box.append(self._row("Mật khẩu:", self.c_pass, hint="chỉ 7z"))
        self.c_out = Gtk.Entry(placeholder_text="vd: out.7z — để trống là tự đặt tên")
        box.append(self._row("Lưu vào:", self.c_out))
        self.c_over = Gtk.CheckButton(label="Cho phép đè file đã có")
        box.append(self.c_over)

        self.c_bar = Gtk.ProgressBar()
        self._bars.append(self.c_bar)
        box.append(self.c_bar)

        self.c_status = self._status()
        box.append(self.c_status)

        self.c_btn = Gtk.Button(label="Nén", css_classes=["suggested-action"], halign=Gtk.Align.START, sensitive=False)
        self.c_btn.connect("clicked", self.run_compress)
        box.append(self.c_btn)
        return box

    def _c_add(self, paths: list[Path]):
        self.c_paths += list(paths)
        self.c_files_label.set_text(", ".join(str(p) for p in self.c_paths))
        self.c_btn.set_sensitive(True)

    def run_compress(self, *_):
        fmt = [None, "br", "zip", "7z"][self.c_fmt.get_selected()]
        out_text = self.c_out.get_text().strip()
        out = Path(out_text) if out_text else None
        paths = list(self.c_paths)
        self.c_btn.set_sensitive(False)
        self.c_status.set_text("Đang nén…")
        self._spawn(
            lambda: core.compress(
                paths, fmt, self.c_pass.get_text() or None, out, self.c_over.get_active(),
                progress=lambda frac: GLib.idle_add(self.c_bar.set_fraction, frac),
            ),
            self._c_done,
        )

    def _c_done(self, result, err):
        if err is not None:
            self._flag(self.c_status, err)
        else:
            self.c_status.set_text(f"✔ Đã nén → {result}")
        self.c_btn.set_sensitive(True)

    # ---------- page: extract (CLI `x`) ----------

    def _extract_page(self):
        box = self._page()
        self.x_retried = False
        self.x_file: Path | None = None
        self.x_dir: Path | None = None

        box.append(self._chooser("Chọn kho lưu…", _Pick(), self._x_file))
        self.x_label = Gtk.Label(xalign=0, wrap=True, max_width_chars=60, label="")
        box.append(self.x_label)
        self.x_dest_btn = self._chooser(
            "Thư mục đích: (mặc định · thư mục hiện tại)", _Pick(folder=True), self._x_dest
        )
        box.append(self.x_dest_btn)

        self.x_pass = Gtk.PasswordEntry(show_peek_icon=True)
        box.append(self._row("Mật khẩu:", self.x_pass, hint="chỉ 7z"))
        self.x_over = Gtk.CheckButton(label="Cho phép đè file trùng tên ở đích")
        box.append(self.x_over)

        self.x_bar = Gtk.ProgressBar()
        self._bars.append(self.x_bar)
        box.append(self.x_bar)

        self.x_status = self._status()
        box.append(self.x_status)

        self.x_btn = Gtk.Button(label="Giải nén", css_classes=["suggested-action"], halign=Gtk.Align.START, sensitive=False)
        self.x_btn.connect("clicked", lambda *_: self.run_extract())
        box.append(self.x_btn)

    def _x_file(self, p: Path):
        self.x_file = p
        self.x_label.set_text(str(p))
        self.x_btn.set_sensitive(True)

    def _x_dest(self, p: Path):
        self.x_dir = p
        self.x_dest_btn.set_label(f"Thư mục đích: {p}")

    def run_extract(self, password: str | None = None):
        if self.x_file is None:
            return
        self.x_btn.set_sensitive(False)
        self.x_status.set_text("Đang giải nén…")
        pw = password if password is not None else (self.x_pass.get_text() or None)
        self._spawn(
            lambda: core.extract(
                self.x_file, self.x_dir, pw, self.x_over.get_active(),
                progress=lambda frac: GLib.idle_add(self.x_bar.set_fraction, frac),
            ),
            self._x_done,
        )

    def _x_done(self, result, err):
        if err is not None:
            msg = str(err)
            if "password" in msg and not self.x_retried:
                # encrypted 7z opened without a password: ask once, then retry
                self.x_retried = True
                self.x_btn.set_sensitive(True)
                self._ask_password(msg, lambda pw: self.run_extract(pw))
                return
            self._flag(self.x_status, err)
        else:
            self.x_status.set_text(f"✔ Đã giải nén → {result}")
        self.x_btn.set_sensitive(True)

    # ---------- page: list contents (CLI `l`) ----------

    def _list_page(self):
        box = self._page()
        self.ls_file: Path | None = None
        box.append(self._chooser("Chọn kho lưu…", _Pick(), self._ls_file))
        self.ls_btn = Gtk.Button(label="Xem nội dung", halign=Gtk.Align.START, sensitive=False)
        self.ls_btn.connect("clicked", lambda *_: self.run_list())
        box.append(self.ls_btn)

        view = Gtk.TextView(editable=False, monospace=True, top_margin=6, left_margin=6)
        self.ls_view = view
        scroller = Gtk.ScrolledWindow(vexpand=True, min_content_height=320)
        scroller.set_child(view)
        box.append(scroller)

        self.ls_status = self._status()
        box.append(self.ls_status)

    def _ls_file(self, p: Path):
        self.ls_file = p
        self.ls_btn.set_sensitive(True)

    def run_list(self):
        if self.ls_file is None:
            return
        self.ls_btn.set_sensitive(False)
        self._spawn(
            lambda: core.list_contents(self.ls_file), self._ls_done,
        )

    def _ls_done(self, result, err):
        self.ls_btn.set_sensitive(True)
        if err is not None:
            self._flag(self.ls_status, err)
            self.ls_view.get_buffer().set_text("")
            return
        self.ls_status.set_text("")
        lines = "\n".join(
            f"{name}  ({fmt_size(size)})" if size else name for name, size in result
        ) or "(kho trống)"
        self.ls_view.get_buffer().set_text(lines)


def main() -> None:
    app = Gtk.Application(application_id="vn.zapp.zfile")
    app.connect("activate", lambda a: Win(a).present())
    app.run(sys.argv)


if __name__ == "__main__":
    main()
