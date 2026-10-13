# MiniSelect

一个基于 **GTK4** 的轻量级浮动菜单 / 文件浏览器。它把目录内容或自定义的 JSON 菜单渲染成一个无边框、可用键盘操作的列表窗口，适合绑定到快捷键，快速选择文件、打开目录或执行命令。

## 特性

- **两种模式**
  - **文件浏览器模式**：列出目录内容，文件夹可逐层进入，文件点击后用 `xdg-open` 打开。接受**任意数量**的目录参数，每个目录各开一个独立窗口。
  - **JSON 菜单模式**：用一段 JSON 描述菜单，值可以是 shell 命令、子菜单，或带输入的交互行。
- **纯键盘操作**：方向键导航、Enter 确认、Esc 返回/退出。
- **隐藏文件切换**：按 `.` 显示或隐藏以 `.` 开头的文件。
- **目录实时刷新**：基于 GIO `FileMonitor` 监听当前目录，文件变化时自动刷新（带防抖）。
- **拖拽支持**：文件/文件夹可作为拖拽源；文件夹可作为拖拽目标以复制文件。
- **交互输入行**：菜单项可附带输入框，把用户输入追加到命令或通过 stdin 传入。
- **多语言**：内置 `zh_CN` / `en_US`，可通过 `config.yaml` 配置。
- **可用作库**：`run_menu`、`MiniSelectApp`、`generate_ls_menu`、`validate_commands` 等均可直接导入。

## 环境要求

- Python >= 3.13
- GTK4 及 PyGObject（`PyGObject >= 3.50`）
- `PyYAML >= 6.0`（用于读取配置，可选）

## 安装

项目使用 [`uv`](https://github.com/astral-sh/uv) 管理：

```bash
git clone https://github.com/mifongjvav/MiniSelect.git
cd MiniSelect
uv sync
```

安装后会提供两个等价的命令：`miniselect` 和 `miniselect-gtk`。

## 使用

### 文件浏览器模式

```bash
miniselect                       # 浏览当前目录
miniselect ~/Documents           # 浏览指定目录
miniselect ~/Documents /tmp ~/Music   # 每个目录一个窗口
```

### JSON 菜单模式

```bash
miniselect '{"终端": "kitty", "文件": {"主目录": "nautilus ~", "下载": "nautilus ~/Downloads"}}'
```

菜单结构规则：

| 值类型 | 含义 |
| --- | --- |
| 字符串 `"command"` | 直接以 shell 执行该命令 |
| 字典 `{...}` | 子菜单，Enter 进入 |
| 数组 `["cmd", mode]` | 带输入框的交互行 |

交互行 `mode` 的取值：

- `false` 或省略：把输入追加到命令后执行；
- `true`：把输入通过 stdin 传给命令；
- `null`：两者结合。

示例：

```json
{
  "搜索文件": ["find ~ -name", false],
  "写入文件": ["tee /tmp/out.txt", true]
}
```

## 快捷键

| 按键 | 功能 |
| --- | --- |
| `↑` / `↓` | 上下导航 |
| `Enter` | 确认 / 进入子菜单 |
| `Esc` | 返回上一级 / 退出 |
| `.` | 显示 / 隐藏隐藏文件（文件浏览器模式） |
| `H` | 显示帮助 |

## 配置

配置文件按以下顺序查找，第一个存在的生效：

1. 项目根目录下的 `config.yaml`
2. 当前工作目录下的 `config.yaml`
3. `~/.config/miniselect/config.yaml`

```yaml
# 默认语言: zh_CN (中文), en_US (英文)
language: zh_CN
```

## 作为库使用

```python
from miniselect import run_menu

run_menu(
    {"Terminal": "kitty", "Files": {"Home": "nautilus ~"}},
    file_browser_mode=False,
)

# 或者只要原生的选择回调，而不执行命令：
def on_select(key, value):
    print("selected:", key, value)

run_menu({"A": "echo a", "B": {"C": "echo c"}}, on_select=on_select)
```

常用导出：

- `run_menu(menu_data, file_browser_mode=False, on_select=None, initial_path=".")`
- `MiniSelectApp` / `MiniSelectWindow`（需要完全控制 GTK 生命周期时）
- `generate_ls_menu(path, show_hidden=False)`：把目录转换成菜单字典
- `validate_commands(menu_data)`：校验菜单中的命令是否存在

## 开发

```bash
uv sync
uv run miniselect --help
```

目录结构：

```
src/miniselect/
├── cli.py              # 统一的命令行入口与参数解析
├── gtk/
│   ├── app.py          # MiniSelectWindow / MiniSelectApp
│   └── dialogs.py      # 错误对话框、剪贴板工具
└── shared/
    ├── browser.py      # 目录 -> 菜单
    ├── config.py       # 配置与本地化
    └── validation.py   # 命令校验
```

## 许可证

本项目基于 [MIT License](LICENSE) 开源，Copyright (c) 2026 Argon。
