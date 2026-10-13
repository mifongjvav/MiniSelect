#!/usr/bin/env python3
"""
MiniSelect - A GTK4 floating menu application using native widgets.

Can be used as a library:
    from miniselect import MiniSelectApp, run_menu, generate_ls_menu, validate_commands

Or as a CLI tool:
    miniselect '{"Menu Name": "command"}'
    miniselect /path/to/directory
    miniselect /path/a /path/b /path/c   # one window per directory
    miniselect  # browse current directory
"""

import shlex
import subprocess
import sys

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gtk, Gdk, GLib, Gio

from ..shared.config import _
from ..shared.browser import generate_ls_menu


# The CSS rule only needs to be installed once per display, no matter how many
# windows we create.
_CSS_INSTALLED = False


def _install_css():
    global _CSS_INSTALLED
    if _CSS_INSTALLED:
        return
    provider = Gtk.CssProvider()
    provider.load_from_string(
        """
        list row:focus:not(.keyboard-focus) {
            outline: none;
            box-shadow: none;
        }
        """
    )
    display = Gdk.Display.get_default()
    if display:
        Gtk.StyleContext.add_provider_for_display(
            display, provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )
        _CSS_INSTALLED = True


class MiniSelectWindow(Gtk.ApplicationWindow):
    """A single floating, keyboard-navigable menu window.

    All menu state lives on the window, so a single ``Gtk.Application`` can
    manage an arbitrary number of independent windows (one per directory in
    file-browser mode).

    Args:
        menu_data: Dictionary defining the menu structure.
            - str values are executed as shell commands.
            - dict values become submenus.
            - list values [cmd, mode] create input rows.
              mode: false/absent=append, true=stdin, null=hybrid.
            - {"__lazy_path__": path} dicts are lazy-loaded directory submenus.
        file_browser_mode: If True, show folder/file icons for menu items.
        on_select: Optional callback(selected_key, value) called instead of
            executing commands. Useful when embedding as a library.
        initial_path: Directory used for file-browser mode (hidden-file toggle).
    """

    BACK_KEY = "__miniselect_back__"
    EXIT_KEY = "__miniselect_exit__"

    def __init__(
        self,
        menu_data: dict,
        file_browser_mode: bool = False,
        on_select=None,
        initial_path: str = ".",
        **kwargs,
    ):
        super().__init__(**kwargs)
        self.menu_data = menu_data
        self.file_browser_mode = file_browser_mode
        self.on_select = on_select
        self.nav_stack = []  # (title, parent_data, prev_index, path_or_None)
        self.current_data = menu_data
        self.selected_index = 0
        self.keys = []
        self.input_rows = {}
        self.show_hidden = False
        self._current_path = initial_path if file_browser_mode else None

        self.list_box = None
        self._file_monitor = None
        self._monitor_debounce_id = None

        self.build_ui()
        self.refresh_list()

        # Make sure the directory monitor is torn down with the window.
        self.connect("close-request", lambda w: self._stop_file_monitor() or False)

    def build_ui(self):
        self.set_title("MiniSelect")
        self.set_default_size(300, 300)
        self.set_decorated(False)
        self.set_resizable(False)

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)

        scrolled = Gtk.ScrolledWindow()
        scrolled.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scrolled.set_vexpand(True)

        self.list_box = Gtk.ListBox()
        self.list_box.set_selection_mode(Gtk.SelectionMode.SINGLE)
        self.list_box.add_css_class("boxed-list")
        self.list_box.connect("row-activated", self.on_row_activated)
        scrolled.set_child(self.list_box)
        box.append(scrolled)

        self.set_child(box)

        key_controller = Gtk.EventControllerKey()
        key_controller.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
        key_controller.connect("key-pressed", self.on_key_pressed)
        self.add_controller(key_controller)

        motion_controller = Gtk.EventControllerMotion()
        motion_controller.connect("motion", self._on_mouse_motion)
        self.add_controller(motion_controller)

        _install_css()

        self.connect("map", self._on_window_map)

        # File system monitor for file browser mode
        if self.file_browser_mode and self._current_path:
            self._start_file_monitor()

    # ------------------------------------------------------------------
    # File system monitoring
    # ------------------------------------------------------------------
    def _start_file_monitor(self):
        """Start monitoring the current directory for changes using GIO."""
        if self._file_monitor is not None:
            self._file_monitor.cancel()
            self._file_monitor = None

        if not self._current_path:
            return

        try:
            gio_file = Gio.File.new_for_path(self._current_path)
            self._file_monitor = gio_file.monitor_directory(
                Gio.FileMonitorFlags.NONE, None
            )
            self._file_monitor.connect("changed", self._on_file_changed)
        except Exception:
            # Fallback: no monitoring if GIO fails
            pass

    def _stop_file_monitor(self):
        """Stop file system monitoring."""
        if self._file_monitor is not None:
            self._file_monitor.cancel()
            self._file_monitor = None
        if self._monitor_debounce_id is not None:
            GLib.source_remove(self._monitor_debounce_id)
            self._monitor_debounce_id = None

    def _on_file_changed(self, monitor, file, other_file, event_type):
        """Handle file system change events with debouncing."""
        if self._monitor_debounce_id is not None:
            GLib.source_remove(self._monitor_debounce_id)
        self._monitor_debounce_id = GLib.timeout_add(300, self._do_monitor_refresh)

    def _do_monitor_refresh(self):
        """Perform refresh after debounce period."""
        self._monitor_debounce_id = None
        if self.file_browser_mode and self._current_path:
            self._reload_current_directory()
        return False

    # ------------------------------------------------------------------
    # Focus / selection visuals
    # ------------------------------------------------------------------
    def _on_mouse_motion(self, controller, x, y):
        """Hide keyboard focus indicator when mouse is used."""
        child = self.list_box.get_first_child()
        while child:
            child.remove_css_class("keyboard-focus")
            child = child.get_next_sibling()

    def _on_window_map(self, window):
        GLib.idle_add(self._grab_focus_and_select)

    def _grab_focus_and_select(self):
        self.grab_focus()
        self.sync_selection_to_index()
        return False

    def _rows(self):
        rows = []
        child = self.list_box.get_first_child()
        while child:
            rows.append(child)
            child = child.get_next_sibling()
        return rows

    def sync_selection_to_index(self):
        """Sync the visual selection with our internal selected_index."""
        rows = self._rows()
        if 0 <= self.selected_index < len(rows):
            self.list_box.select_row(rows[self.selected_index])
            rows[self.selected_index].grab_focus()
            for row in rows:
                row.remove_css_class("keyboard-focus")
            rows[self.selected_index].add_css_class("keyboard-focus")

    # ------------------------------------------------------------------
    # List rendering
    # ------------------------------------------------------------------
    def refresh_list(self):
        while child := self.list_box.get_first_child():
            self.list_box.remove(child)

        self.keys = list(self.current_data.keys())
        self.input_rows = {}

        is_submenu = len(self.nav_stack) > 0
        if is_submenu:
            self.keys.append(self.BACK_KEY)

        self.keys.append(self.EXIT_KEY)

        for key in self.keys:
            row = Gtk.ListBoxRow()
            label_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
            label_box.set_margin_top(6)
            label_box.set_margin_bottom(6)
            label_box.set_margin_start(12)
            label_box.set_margin_end(12)

            if key == self.BACK_KEY:
                icon = Gtk.Image.new_from_icon_name("go-previous-symbolic")
                label_box.append(icon)
                label = Gtk.Label(label=_("back"), xalign=0)
                label.set_hexpand(True)
                label_box.append(label)
            elif key == self.EXIT_KEY:
                icon = Gtk.Image.new_from_icon_name("application-exit-symbolic")
                label_box.append(icon)
                label = Gtk.Label(label=_("exit"), xalign=0)
                label.set_hexpand(True)
                label_box.append(label)
            else:
                val = self.current_data[key]

                if isinstance(val, list):
                    cmd_str = val[0]
                    stdin_mode = val[1] if len(val) > 1 else False
                    self.input_rows[key] = (cmd_str, stdin_mode)

                    label = Gtk.Label(label=key, xalign=0)
                    label.set_hexpand(True)
                    label_box.append(label)

                    entry = Gtk.Entry()
                    entry.set_placeholder_text("")
                    entry.set_width_chars(10)
                    entry.set_max_width_chars(20)
                    entry.set_hexpand(False)
                    entry.connect(
                        "activate", lambda e, k=key: self._execute_input_row(k)
                    )
                    label_box.append(entry)

                    confirm_btn = Gtk.Button()
                    confirm_btn.set_has_frame(False)
                    confirm_img = Gtk.Image.new_from_icon_name("object-select-symbolic")
                    confirm_btn.set_child(confirm_img)
                    confirm_btn.add_css_class("flat")
                    confirm_btn.set_tooltip_text(_("ok"))
                    confirm_btn.connect(
                        "clicked", lambda b, k=key: self._execute_input_row(k)
                    )
                    label_box.append(confirm_btn)
                else:
                    if self.file_browser_mode and isinstance(val, dict):
                        icon = Gtk.Image.new_from_icon_name("folder-symbolic")
                        label_box.append(icon)
                    elif self.file_browser_mode and isinstance(val, str):
                        icon = Gtk.Image.new_from_icon_name("text-x-generic-symbolic")
                        label_box.append(icon)

                    label = Gtk.Label(label=key, xalign=0)
                    label.set_hexpand(True)
                    label_box.append(label)

                    if isinstance(val, dict):
                        arrow = Gtk.Image.new_from_icon_name("go-next-symbolic")
                        label_box.append(arrow)

            row.set_child(label_box)

            if self.file_browser_mode and key not in (self.BACK_KEY, self.EXIT_KEY):
                self._setup_drag_and_drop(row, key)

            self.list_box.append(row)

        if self.selected_index >= len(self.keys):
            self.selected_index = max(0, len(self.keys) - 1)

        self.sync_selection_to_index()

    def _setup_drag_and_drop(self, row, key):
        """Enable copy-drag for entries and copy-drop onto directories."""
        val = self.current_data.get(key)

        # Drag source: files and lazy directories expose their real path.
        drag_path = None
        if isinstance(val, dict) and "__lazy_path__" in val:
            drag_path = val["__lazy_path__"]
        elif isinstance(val, str):
            # Files are stored as "xdg-open '<path>'"; recover the path.
            try:
                parts = shlex.split(val)
                drag_path = parts[-1] if len(parts) > 1 else None
            except ValueError:
                drag_path = None

        if drag_path:
            drag_source = Gtk.DragSource()
            drag_source.set_actions(Gdk.DragAction.COPY)
            gfile = Gio.File.new_for_path(drag_path)
            uri = gfile.get_uri()
            uri_list_bytes = GLib.Bytes.new((uri + "\r\n").encode("utf-8"))

            def _prepare_drag(src, x, y, gf=gfile, ub=uri_list_bytes):
                providers = [
                    Gdk.ContentProvider.new_for_value(gf),
                    Gdk.ContentProvider.new_for_bytes("text/uri-list", ub),
                ]
                return Gdk.ContentProvider.new_union(providers)

            drag_source.connect("prepare", _prepare_drag)
            row.add_controller(drag_source)

        # Drop target: only lazy directories can receive files.
        if isinstance(val, dict) and "__lazy_path__" in val:
            drop_path = val["__lazy_path__"]
            drop_target = Gtk.DropTarget.new(Gdk.FileList, Gdk.DragAction.COPY)
            drop_target.set_gtypes([Gdk.FileList, Gio.File])
            drop_target.connect(
                "drop",
                lambda t, value, x, y, dp=drop_path: self._on_file_drop(value, dp),
            )
            row.add_controller(drop_target)

    # ------------------------------------------------------------------
    # Interaction
    # ------------------------------------------------------------------
    def on_row_activated(self, list_box, row):
        """Handle native row activation (Enter key or double-click)."""
        try:
            self.selected_index = self._rows().index(row)
        except ValueError:
            pass
        self.activate_selected()

    def on_key_pressed(self, controller, keyval, keycode, state):
        if keyval == Gdk.KEY_Up:
            if self.selected_index > 0:
                self.selected_index -= 1
            else:
                self.selected_index = len(self.keys) - 1
            self.sync_selection_to_index()
            return True

        elif keyval == Gdk.KEY_Down:
            if self.selected_index < len(self.keys) - 1:
                self.selected_index += 1
            else:
                self.selected_index = 0
            self.sync_selection_to_index()
            return True

        elif keyval in (Gdk.KEY_Return, Gdk.KEY_KP_Enter):
            self.activate_selected()
            return True

        elif keyval == Gdk.KEY_Escape:
            if self.nav_stack:
                self._go_back()
            else:
                self.close()
            return True

        elif keyval == Gdk.KEY_period and self.file_browser_mode:
            # Toggle hidden files visibility and reload the current directory.
            self.show_hidden = not self.show_hidden
            self._reload_current_directory()
            return True

        elif keyval in (Gdk.KEY_h, Gdk.KEY_H):
            self._show_help_dialog()
            return True

        return False

    def _go_back(self):
        title, parent_data, prev_index, path = self.nav_stack.pop()
        self.current_data = parent_data
        self._current_path = path
        self.selected_index = prev_index
        self.refresh_list()
        self._start_file_monitor()

    def _on_file_drop(self, value, dest_path: str) -> bool:
        """Handle file drop onto a directory row (copy mode)."""
        uris = []
        if isinstance(value, Gdk.FileList):
            uris = [f.get_uri() for f in value.get_files()]
        elif isinstance(value, Gio.File):
            uris = [value.get_uri()]
        else:
            return False

        if not uris:
            return False

        cmd_parts = ["gio", "copy", *uris, dest_path]
        try:
            subprocess.Popen(
                cmd_parts,
                start_new_session=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except Exception as e:
            print(f"Error copying files: {e}", file=sys.stderr)
            return False

        return True

    def _reload_current_directory(self):
        """Reload current directory listing with updated show_hidden setting."""
        if not self.file_browser_mode or self._current_path is None:
            return

        new_menu = generate_ls_menu(self._current_path, show_hidden=self.show_hidden)
        self.current_data.clear()
        self.current_data.update(new_menu)
        self.selected_index = 0
        self.refresh_list()

    def _show_help_dialog(self):
        """Show help dialog with shortcuts and project info."""
        dialog = Gtk.Window(transient_for=self, modal=True)
        dialog.set_title(_("help_title"))
        dialog.set_default_size(350, 280)
        dialog.set_resizable(False)
        dialog.set_decorated(False)

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        box.set_margin_top(20)
        box.set_margin_bottom(20)
        box.set_margin_start(20)
        box.set_margin_end(20)

        label = Gtk.Label(label=_("help_text"), xalign=0)
        label.set_wrap(True)
        label.set_selectable(True)
        box.append(label)

        close_btn = Gtk.Button(label=_("ok"))
        close_btn.set_halign(Gtk.Align.END)
        close_btn.connect("clicked", lambda b: dialog.close())
        box.append(close_btn)

        dialog.set_child(box)

        key_ctrl = Gtk.EventControllerKey()
        key_ctrl.connect(
            "key-pressed",
            lambda c, k, kc, s: (
                dialog.close()
                if k in (Gdk.KEY_Escape, Gdk.KEY_Return, Gdk.KEY_KP_Enter)
                else False
            ),
        )
        dialog.add_controller(key_ctrl)

        dialog.present()
        close_btn.grab_focus()

    def _execute_input_row(self, key):
        """Execute an input row command by key name."""
        if key not in self.input_rows:
            return
        if key in self.keys:
            self.selected_index = self.keys.index(key)
        self.activate_selected()

    def activate_selected(self):
        if not self.keys:
            return

        selected_key = self.keys[self.selected_index]

        if selected_key == self.EXIT_KEY:
            self.close()
            return

        if selected_key == self.BACK_KEY:
            if self.nav_stack:
                self._go_back()
            return

        value = self.current_data[selected_key]

        if isinstance(value, dict):
            # Check for lazy-loaded directory submenu
            new_path = None
            if "__lazy_path__" in value:
                new_path = value["__lazy_path__"]
                loaded_menu = generate_ls_menu(new_path, show_hidden=self.show_hidden)
                self.current_data[selected_key] = loaded_menu
                value = loaded_menu

            parent_path = self._current_path
            self.nav_stack.append(
                (selected_key, self.current_data, self.selected_index, parent_path)
            )
            self.current_data = value
            self._current_path = new_path
            self.selected_index = 0
            self.refresh_list()
            self._start_file_monitor()
        elif isinstance(value, list):
            self._run_input_command(selected_key, value)
        else:
            if self.on_select:
                self.on_select(selected_key, value)
                self.close()
                return

            try:
                subprocess.Popen(
                    value,
                    shell=True,
                    start_new_session=True,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
            except Exception as e:
                print(f"Error executing command: {e}", file=sys.stderr)
            finally:
                self.close()

    def _run_input_command(self, selected_key, value):
        """Execute a list/input row command, feeding user input as configured."""
        cmd_str = value[0]
        stdin_mode = value[1] if len(value) > 1 else False

        user_input = ""
        rows = self._rows()
        if 0 <= self.selected_index < len(rows):
            row_child = rows[self.selected_index].get_child()
            if isinstance(row_child, Gtk.Box):
                entry_child = row_child.get_first_child()
                while entry_child:
                    if isinstance(entry_child, Gtk.Entry):
                        user_input = entry_child.get_text()
                        break
                    entry_child = entry_child.get_next_sibling()

        if self.on_select:
            self.on_select(selected_key, value)
            self.close()
            return

        try:
            if stdin_mode is None:
                full_cmd = f"{cmd_str} {user_input}" if user_input else cmd_str
                proc = subprocess.Popen(
                    full_cmd,
                    shell=True,
                    start_new_session=True,
                    stdin=subprocess.PIPE,
                    stdout=None,
                    stderr=None,
                )
                proc.communicate(input=user_input.encode())
            elif stdin_mode:
                proc = subprocess.Popen(
                    cmd_str,
                    shell=True,
                    start_new_session=True,
                    stdin=subprocess.PIPE,
                    stdout=None,
                    stderr=None,
                )
                proc.communicate(input=user_input.encode())
            else:
                full_cmd = f"{cmd_str} {user_input}" if user_input else cmd_str
                subprocess.Popen(
                    full_cmd, shell=True, start_new_session=True, stdout=None, stderr=None
                )
        except Exception as e:
            print(f"Error executing command: {e}", file=sys.stderr)
        finally:
            self.close()


class MiniSelectApp(Gtk.Application):
    """GTK4 application hosting one or more :class:`MiniSelectWindow` windows.

    For library use with a single menu, pass ``menu_data`` directly. For
    file-browser mode with one window per directory, pass ``window_specs`` as a
    list of ``(menu_data, file_browser_mode, initial_path)`` tuples.
    """

    def __init__(
        self,
        menu_data: dict = None,
        file_browser_mode: bool = False,
        on_select=None,
        initial_path: str = ".",
        window_specs=None,
    ):
        super().__init__(application_id="com.miniselect.app")
        self.on_select = on_select
        if window_specs is None:
            window_specs = [(menu_data, file_browser_mode, initial_path)]
        self.window_specs = list(window_specs)
        self.windows = []

    def do_activate(self):
        if not self.windows:
            for menu_data, file_browser_mode, initial_path in self.window_specs:
                window = MiniSelectWindow(
                    menu_data,
                    file_browser_mode=file_browser_mode,
                    on_select=self.on_select,
                    initial_path=initial_path,
                    application=self,
                )
                window.connect("close-request", self._on_window_closed)
                self.windows.append(window)
        for window in list(self.windows):
            window.present()

    def _on_window_closed(self, window):
        if window in self.windows:
            self.windows.remove(window)
        return False


def run_menu(
    menu_data: dict,
    file_browser_mode: bool = False,
    on_select=None,
    initial_path: str = ".",
) -> None:
    """Convenience function to run MiniSelect as a library.

    Args:
        menu_data: Menu structure dictionary.
        file_browser_mode: Show folder/file icons.
        on_select: Optional callback(key, value) instead of executing commands.
        initial_path: Initial directory for file-browser mode.
    """
    app = MiniSelectApp(
        menu_data,
        file_browser_mode=file_browser_mode,
        on_select=on_select,
        initial_path=initial_path,
    )
    app.run(None)


def main():
    """Entry point for ``miniselect-gtk``; delegates to the unified CLI."""
    from ..cli import main as cli_main

    cli_main()


if __name__ == "__main__":
    main()
