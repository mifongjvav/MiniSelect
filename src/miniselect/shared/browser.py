"""File browser menu generation for MiniSelect."""

import os
import shlex


def generate_ls_menu(path: str = ".", show_hidden: bool = False) -> dict:
    """Generate a menu from directory contents. Directories become lazy submenus, files become commands.

    Args:
        path: Directory path to list.
        show_hidden: If True, include files/directories starting with '.'
    """
    menu = {}
    try:
        entries = sorted(os.listdir(path))
        dirs = []
        files = []
        for entry in entries:
            # Skip hidden files unless show_hidden is True
            if not show_hidden and entry.startswith("."):
                continue
            full_path = os.path.abspath(os.path.join(path, entry))
            if os.path.isdir(full_path):
                dirs.append((entry, full_path))
            else:
                files.append((entry, full_path))

        # Directories first as LAZY submenus (only scan when entered)
        for name, full_path in dirs:
            menu[name + "/"] = {"__lazy_path__": full_path}

        # Files second as xdg-open commands
        for name, full_path in files:
            menu[name] = f"xdg-open {shlex.quote(full_path)}"
    except PermissionError:
        menu["Permission denied"] = "echo " + shlex.quote(
            f"Permission denied: {os.path.abspath(path)}"
        )
    except Exception as e:
        menu["Error"] = "echo " + shlex.quote(str(e))
    return menu
