"""Command validation utilities for MiniSelect."""

import shutil
from typing import Any


def validate_commands(data: Any, path: str = "root") -> list[str]:
    """
    Recursively validate that all leaf commands exist in PATH.
    Returns a list of error messages for missing commands.
    Supports str commands and list [cmd, stdin_mode] commands.
    """
    errors = []
    if isinstance(data, dict):
        for key, value in data.items():
            current_path = f"{path} -> {key}"
            if isinstance(value, dict):
                # Skip lazy-loaded directory markers
                if "__lazy_path__" in value:
                    continue
                errors.extend(validate_commands(value, current_path))
            elif isinstance(value, str):
                cmd_parts = value.strip().split()
                if not cmd_parts:
                    errors.append(f"[{current_path}] Empty command")
                    continue
                base_cmd = cmd_parts[0]
                # Skip shell builtins and special cases
                if base_cmd in ("cd", "export", "source", ".", "eval", "exec"):
                    continue
                if not shutil.which(base_cmd):
                    errors.append(f"[{current_path}] Command not found: {base_cmd}")
            elif isinstance(value, list):
                if len(value) < 1 or len(value) > 2:
                    errors.append(f"[{current_path}] Array command must have 1 or 2 items")
                    continue
                cmd_str = value[0]
                if not isinstance(cmd_str, str):
                    errors.append(f"[{current_path}] First item of array must be a string command")
                    continue
                if len(value) == 2:
                    stdin_mode = value[1]
                    if stdin_mode is not None and not isinstance(stdin_mode, bool):
                        errors.append(f"[{current_path}] Second item must be a boolean or null")
                        continue
                cmd_parts = cmd_str.strip().split()
                if not cmd_parts:
                    errors.append(f"[{current_path}] Empty command in array")
                    continue
                base_cmd = cmd_parts[0]
                if base_cmd in ("cd", "export", "source", ".", "eval", "exec"):
                    continue
                if not shutil.which(base_cmd):
                    errors.append(f"[{current_path}] Command not found: {base_cmd}")
            else:
                errors.append(f"[{current_path}] Invalid value type: {type(value).__name__}")
    return errors
