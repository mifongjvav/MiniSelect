"""Unified CLI entry point for MiniSelect."""

import json
import os
import sys

from .gtk.dialogs import show_error_dialog
from .shared.browser import generate_ls_menu
from .shared.config import _
from .shared.validation import validate_commands


def _looks_like_json(arg: str) -> bool:
    return arg.lstrip().startswith("{")


def build_window_specs(args):
    """Turn CLI arguments into window specifications.

    Returns ``(specs, error)`` where ``specs`` is a list of
    ``(menu_data, file_browser_mode, initial_path)`` tuples and ``error`` is an
    optional localized message to show the user.

    Behaviour:
        * no arguments            -> browse the current directory
        * one JSON object string  -> JSON menu mode
        * any number of paths     -> file-browser mode, one window per directory
    """
    if not args:
        path = os.path.abspath(".")
        return [(generate_ls_menu(path), True, path)], None

    # Single JSON argument (but never shadow a real directory path).
    if len(args) == 1 and _looks_like_json(args[0]) and not os.path.isdir(args[0]):
        try:
            menu_data = json.loads(args[0])
        except json.JSONDecodeError as e:
            return [], f"{_('invalid_json')}{e}"
        if not isinstance(menu_data, dict):
            return [], f"{_('invalid_structure')}{_('root_must_be_object')}"
        errors = validate_commands(menu_data)
        if errors:
            return [], _("commands_not_found") + "\n".join(errors)
        return [(menu_data, False, ".")], None

    # File-browser mode: every argument is treated as a directory path.
    dir_paths = []
    invalid_paths = []
    for arg in args:
        abs_path = os.path.abspath(os.path.expanduser(arg))
        if os.path.isdir(abs_path):
            dir_paths.append(abs_path)
        else:
            invalid_paths.append(arg)

    error = None
    if invalid_paths:
        error = _("invalid_paths") + "\n".join(invalid_paths)

    specs = [(generate_ls_menu(path), True, path) for path in dir_paths]
    return specs, error


def _print_usage():
    print("Usage: miniselect [<directory_path> ...] | '<json_menu_string>'")
    print("Example: miniselect /home/user/Documents /tmp ~/Pictures")
    print('Example: miniselect \'{"Terminal": "kitty"}\'')


def main():
    args = sys.argv[1:]

    if args and args[0] in ("-h", "--help"):
        _print_usage()
        return

    specs, error = build_window_specs(args)

    if error:
        show_error_dialog(error)

    if not specs:
        _print_usage()
        sys.exit(1)

    from .gtk.app import MiniSelectApp

    app = MiniSelectApp(window_specs=specs)
    app.run(None)
