"""Configuration and localization for MiniSelect."""

import os

try:
    import yaml
    HAS_YAML = True
except ImportError:
    HAS_YAML = False

STRINGS = {
    "zh_CN": {
        "error_title": "错误",
        "ok": "确定",
        "invalid_json": "无效的 JSON:\n",
        "invalid_structure": "无效的菜单结构:\n",
        "root_must_be_object": "根元素必须是一个 JSON 对象。",
        "invalid_paths": "以下路径不是有效目录:\n",
        "commands_not_found": "以下命令未找到:\n\n",
        "back": "返回",
        "exit": "退出",
        "copy": "复制",
        "help_title": "帮助",
        "help_text": "快捷键:\n  ↑/↓  导航\n  Enter 确认/进入\n  Esc   返回/退出\n  .     显示/隐藏隐藏文件\n  H     显示此帮助\n\nMiniSelect v0.3.0\nGTK4 浮动菜单应用",
    },
    "en_US": {
        "error_title": "Error",
        "ok": "OK",
        "invalid_json": "Invalid JSON:\n",
        "invalid_structure": "Invalid Menu Structure:\n",
        "root_must_be_object": "The root element must be a JSON object.",
        "invalid_paths": "The following paths are not valid directories:\n",
        "commands_not_found": "The following commands were not found:\n\n",
        "back": "Back",
        "exit": "Exit",
        "copy": "Copy",
        "help_title": "Help",
        "help_text": "Shortcuts:\n  ↑/↓  Navigate\n  Enter Confirm/Enter\n  Esc   Back/Exit\n  .     Toggle hidden files\n  H     Show this help\n\nMiniSelect v0.3.0\nGTK4 Floating Menu App",
    }
}


def load_config():
    """Load config.yaml from the project root, the working directory, or
    ~/.config/miniselect/config.yaml (first match wins)."""
    config = {"language": "zh_CN"}

    # src/miniselect/shared/config.py -> project root is four levels up.
    package_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(
        os.path.dirname(os.path.dirname(package_dir))
    )

    candidates = [
        os.path.join(project_root, "config.yaml"),
        os.path.join(os.getcwd(), "config.yaml"),
        os.path.expanduser("~/.config/miniselect/config.yaml"),
    ]

    if HAS_YAML:
        for path in dict.fromkeys(candidates):
            if os.path.exists(path):
                try:
                    with open(path, "r", encoding="utf-8") as f:
                        loaded = yaml.safe_load(f)
                        if isinstance(loaded, dict):
                            config.update(loaded)
                except Exception:
                    pass
                break
    return config


CONFIG = load_config()
LANG = CONFIG.get("language", "zh_CN")
if LANG not in STRINGS:
    LANG = "zh_CN"


def _(key: str) -> str:
    """Get localized string by key."""
    return STRINGS[LANG].get(key, STRINGS["zh_CN"].get(key, key))
