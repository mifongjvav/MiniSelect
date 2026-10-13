"""GTK4 dialog utilities for MiniSelect."""

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import GLib, Gtk

from ..shared.config import _


def copy_to_clipboard(window: Gtk.Window, text: str) -> None:
    """Copy text to the system clipboard."""
    display = window.get_display()
    if display:
        clipboard = display.get_clipboard()
        clipboard.set(text)


def show_error_dialog(message: str) -> None:
    """Show a native GTK4 error dialog and exit."""
    app = Gtk.Application(application_id="com.miniselect.error")

    def on_activate(app):
        win = Gtk.ApplicationWindow(application=app)
        win.set_title(_("error_title"))
        win.set_default_size(400, 200)
        win.set_resizable(False)

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        box.set_margin_top(20)
        box.set_margin_bottom(20)
        box.set_margin_start(20)
        box.set_margin_end(20)

        icon = Gtk.Image.new_from_icon_name("dialog-error-symbolic")
        icon.set_pixel_size(48)
        box.append(icon)

        title_label = Gtk.Label(label=_("error_title"))
        title_label.add_css_class("title-2")
        box.append(title_label)

        msg_label = Gtk.Label(label=message)
        msg_label.set_wrap(True)
        msg_label.set_selectable(False)
        box.append(msg_label)

        btn_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        btn_box.set_halign(Gtk.Align.CENTER)

        btn = Gtk.Button(label=_("ok"))
        btn.add_css_class("suggested-action")
        btn.connect("clicked", lambda b: app.quit())
        btn_box.append(btn)

        copy_btn = Gtk.Button(label=_("copy"))
        copy_btn.connect("clicked", lambda b: copy_to_clipboard(win, message))
        btn_box.append(copy_btn)

        box.append(btn_box)

        win.set_child(box)
        win.present()

        # Focus the OK button by default instead of the text
        GLib.idle_add(btn.grab_focus)

    app.connect("activate", on_activate)
    app.run(None)
