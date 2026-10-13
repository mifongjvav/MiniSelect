# AGENTS.md

本文件为在此仓库中工作的 AI 编码代理提供上下文与约定。修改代码前请先读完本文件。

## 项目简介

**MiniSelect** 是一个基于 GTK4 的轻量级浮动菜单 / 文件浏览器。它把目录内容或自定义 JSON 菜单渲染成一个无边框、纯键盘操作的列表窗口，常用于绑定到全局快捷键。

- 语言 / 运行时：Python >= 3.13，GTK4 + PyGObject（`PyGObject >= 3.50`），`PyYAML`（可选）
- 许可证：MIT（见 `LICENSE`）
- 上游仓库：https://github.com/mifongjvav/MiniSelect
- 默认分支：`main`

## 开发环境与命令

使用 [`uv`](https://github.com/astral-sh/uv) 管理依赖：

```bash
uv sync                     # 安装依赖（含开发环境 .venv）
uv run miniselect --help    # 运行 CLI
uv build                    # 构建 wheel / sdist
```

等价的虚拟环境解释器路径是 `.venv/bin/python`。仓库已配置 `credential.helper=store`，推送走 HTTPS。

## 目录结构

```
src/miniselect/
├── __init__.py          # 公共 API（惰性导出 GTK 相关符号）
├── cli.py               # 统一的命令行入口 + 纯函数 build_window_specs
├── gtk/
│   ├── app.py           # MiniSelectWindow（单窗口全部状态） / MiniSelectApp（多窗口宿主）
│   └── dialogs.py       # 错误对话框、剪贴板工具
└── shared/
    ├── browser.py       # 目录 -> 菜单字典
    ├── config.py        # 配置加载 + 本地化字符串
    └── validation.py    # JSON 菜单命令校验
```

`pyproject.toml` 中的入口点：

- `miniselect = "miniselect.cli:main"`
- `miniselect-gtk = "miniselect.gtk.app:main"`（内部委托给 `cli.main`，行为一致）

## 架构要点

### 窗口状态属于窗口，不属于 Application

所有每窗口状态（`nav_stack`、`current_data`、`selected_index`、`list_box`、`_file_monitor` 等）都保存在 **`MiniSelectWindow`** 上。`MiniSelectApp` 只负责按 `window_specs` 创建 n 个独立窗口：

```python
MiniSelectApp(window_specs=[(menu_data, file_browser_mode, initial_path), ...])
```

> 不要把这些状态重新搬回 `MiniSelectApp`，否则多窗口会互相污染。

### 菜单数据格式

菜单是一个 `dict`，值的类型决定行为：

| 值 | 含义 |
| --- | --- |
| `str` | shell 命令，`subprocess.Popen(..., shell=True)` 执行 |
| `dict` | 子菜单；若含 `"__lazy_path__"` 则为懒加载目录 |
| `list` | `[cmd, mode]` 交互输入行 |

交互行 `mode`（`list[1]`）：

- `False` / 缺省：把用户输入追加到命令后
- `True`：把用户输入通过 stdin 传给命令
- `None`：二者结合

文件浏览器模式下，目录的值形如 `{"__lazy_path__": "/abs/path"}`，键一般以 `/` 结尾；文件的值形如 `"xdg-open '/abs/path'"`。子菜单只在进入时才扫描（懒加载）。

### 保留键

`MiniSelectWindow.BACK_KEY`（`__miniselect_back__`）和 `EXIT_KEY`（`__miniselect_exit__`）是内部保留的菜单键，渲染时替换为「返回 / 退出」行，不可与用户菜单项重名。

### 命令行解析

`cli.build_window_specs(args)` 是**纯函数**，返回 `(specs, error)`：

- 无参数 → 浏览当前目录
- 单个 `{...}` JSON → JSON 菜单模式（会调用 `validate_commands`）
- 任意个路径 → 文件浏览器模式，每个有效目录一个窗口；无效路径通过 `error` 返回，但仍会打开有效目录

优先修改并测试这个函数，而不是在 `main()` 里堆逻辑。

## 约定与注意事项

- **本地化**：所有面向用户的字符串都要在 `shared/config.py` 的 `STRINGS` 中为 `zh_CN` 和 `en_US` **同时**添加，并通过 `_("key")` 取用。当前默认语言由 `config.yaml` 决定。
- **配置文件查找顺序**：项目根 `config.yaml` → 当前工作目录 `config.yaml` → `~/.config/miniselect/config.yaml`，取第一个存在的。请勿改动 `load_config` 中 `project_root` 的层级（`shared/config.py` 距项目根 4 层）。
- **路径引用一律用 `shlex.quote`**，不要手写单引号，避免含空格或特殊字符的文件名出错。
- **判断目录**：文件浏览器模式下用 `isinstance(val, dict)` 判断目录。历史上有一个只在初始化时收集、进入子目录后即失效的 `dir_keys` 机制，已移除，**不要重新引入**。
- **外部命令**：用 `subprocess.Popen(..., start_new_session=True)` 启动并分离，避免子进程随窗口退出而终止。
- **目录监听**：文件浏览器窗口用 GIO `FileMonitor` 监听当前目录并做 300ms 防抖；窗口关闭时必须在 `close-request` 中调用 `_stop_file_monitor()` 释放。
- **命令校验**：`validate_commands` 只用于 JSON 菜单模式，不要对文件浏览器生成的内置命令做校验。
- 缩进使用 4 空格，保持现有代码风格。

## 验证方式

GTK 应用不易做单元测试，改动后至少执行：

```bash
.venv/bin/python -m compileall -q src          # 语法
.venv/bin/python -c "from miniselect.cli import build_window_specs"  # 纯逻辑导入
```

纯逻辑（`build_window_specs`、`generate_ls_menu`、`validate_commands`）可直接断言测试。涉及窗口的行为可用「在 `activate` 里挂一个 `GLib.timeout_add` 自动 `quit`」的方式做冒烟测试，例如：

```python
import gi; gi.require_version("Gtk", "4.0")
from gi.repository import GLib
from miniselect.gtk.app import MiniSelectApp

app = MiniSelectApp(window_specs=[...])
def on_activate(a):
    def check():
        assert len(a.windows) == expected
        a.quit(); return False
    GLib.timeout_add(500, check)
app.connect("activate", on_activate)
app.run(None)
```

运行 GUI 测试需要可用的显示（`DISPLAY` / `WAYLAND_DISPLAY`）；出现 `Gdk-WARNING ... swapchain` 之类的 Vulkan 警告属正常现象，可忽略。

## 完成任务后必须运行 Ruff

**每完成一项任务（改完代码准备提交前），都必须运行 Ruff，并且让它通过，不得提交未通过的结果。** 命令：

```bash
.venv/bin/ruff check --fix src    # 代码检查，自动修复可修复项
.venv/bin/ruff format src         # 格式化
.venv/bin/ruff check src          # 复查，必须显示 All checks passed!
.venv/bin/ruff format --check src # 必须显示 already formatted
```

- 规则集、行宽、忽略项在 `pyproject.toml` 的 `[tool.ruff]` 中显式固定，请遵循现有配置；如确需调整规则，请说明理由。
- 不要用 `# noqa` 绕过问题，除非确属误报并附简短说明。
- 新增的用户可见字符串若较长，可用括号内的隐式字符串拼接换行，不要为绕过 E501 而破坏内容。

## 提交约定

- 提交信息使用中文，首行为 `类型: 简要描述`（如 `feat:`、`fix:`、`docs:`、`refactor:`），正文分点说明。
- 不要提交 `.venv/`、`__pycache__/`、`dist/`、`build/`（均已在 `.gitignore` 中排除）。
