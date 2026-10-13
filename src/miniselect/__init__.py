"""MiniSelect - A GTK4 floating menu application.

Public API:
    from miniselect import run_menu, generate_ls_menu, validate_commands
    from miniselect import MiniSelectApp, MiniSelectWindow, show_error_dialog

CLI usage:
    miniselect '{"Menu": "command"}'
    miniselect /path/to/dir
    miniselect /path/a /path/b /path/c   # one window per directory
    miniselect  # browse current directory
"""

from .shared.browser import generate_ls_menu
from .shared.config import STRINGS, _, load_config
from .shared.validation import validate_commands

__all__ = [
    "STRINGS",
    "MiniSelectApp",
    "MiniSelectWindow",
    "_",
    "generate_ls_menu",
    "load_config",
    "run_menu",
    "show_error_dialog",
    "validate_commands",
]

# These live in the GTK-backed subpackage; import them lazily so that pure
# helpers (validation, config) can be used without pulling in Gtk.
_LAZY_EXPORTS = {
    "MiniSelectApp": (".gtk.app", "MiniSelectApp"),
    "MiniSelectWindow": (".gtk.app", "MiniSelectWindow"),
    "show_error_dialog": (".gtk.dialogs", "show_error_dialog"),
}


def __getattr__(name):
    if name in _LAZY_EXPORTS:
        module_name, attr = _LAZY_EXPORTS[name]
        from importlib import import_module

        return getattr(import_module(module_name, __name__), attr)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def run_menu(
    menu_data: dict, file_browser_mode: bool = False, on_select=None, initial_path: str = "."
) -> None:
    """Run MiniSelect with GTK4 backend.

    Args:
        menu_data: Menu structure dictionary.
        file_browser_mode: Show folder/file icons.
        on_select: Optional callback(key, value) instead of executing commands.
        initial_path: Initial directory path for file browser mode (used for hidden file toggle).
    """
    from .gtk.app import MiniSelectApp

    app = MiniSelectApp(
        menu_data,
        file_browser_mode=file_browser_mode,
        on_select=on_select,
        initial_path=initial_path,
    )
    app.run(None)
