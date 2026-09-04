#!/usr/bin/env python3
"""Windows 上的输出编码兜底。

**症状**：Windows 中文版把 `sys.stdout` 的编码定成 cp936(GBK)，它编不出
U+2713(✓)、U+2717(✗)、U+21B3(↳)。于是 `print("✓ ...")` 直接抛：

    UnicodeEncodeError: 'gbk' codec can't encode character '\\u2713'

2026-09-03 本机实测，`python scripts/doctor.py | tail -30` 在打印第一项检查时就崩——
而 doctor.py 是《开赛操作手册》的第一条命令。

**为什么只在重定向时崩**：stdout 接的是真控制台时，CPython 走
`_io._WindowsConsoleIO`，内部按 UTF-16 调 Windows API，什么符号都打得出。
一旦被管道或文件接走，就退回按 locale 编码（GBK）编码文本，符号才编不出去。

**所以 `init()` 只在非 tty 时才改编码**：

- 非 tty（管道 / 重定向 / Git Bash 的 mintty——它用管道而不是 Windows 控制台）
  → 切 UTF-8。mintty 和现代编辑器都按 UTF-8 读，切了中文与符号都正确；
  留着 GBK 则中文在 mintty 里全是乱码。
- 真 tty（cmd.exe / PowerShell 交互）→ **不动编码**。那里已经能正确输出，
  强行切 UTF-8 反而会让 cp936 控制台里的中文变乱码。

两条路都额外挂 ``errors="replace"`` 兜底，`sym()` 再把状态符号降级成 ASCII，
保证「不管在哪个终端下，最坏也只是符号变丑，绝不会崩」。
"""

from __future__ import annotations

import sys


# 只降级这张表里的符号。中文、数学符号等一概原样透传，
# 免得在真正的 ASCII locale 下把整段中文打成 "?"（那种情况交给 errors="replace"）。
_ASCII = {
    "✓": "[OK]",
    "✅": "[OK]",
    "✗": "[X]",
    "❌": "[X]",
    "⚠": "[!]",
    "↳": "->",
    "→": "->",
}


def _fix(stream: object) -> None:
    reconfigure = getattr(stream, "reconfigure", None)
    if reconfigure is None:  # 被换成 StringIO 之类的非 TextIOWrapper 对象
        return
    isatty = getattr(stream, "isatty", None)
    try:
        redirected = not (isatty() if callable(isatty) else False)
    except (ValueError, OSError):
        redirected = True
    encoding = (getattr(stream, "encoding", None) or "").lower().replace("-", "")
    try:
        if redirected and encoding not in ("utf8", "utf8sig"):
            reconfigure(encoding="utf-8", errors="replace")
        else:
            reconfigure(errors="replace")
    except (ValueError, OSError):
        pass


def init() -> None:
    """修好 stdout / stderr 的编码。每个可执行脚本在 main() 开头调一次。"""
    _fix(sys.stdout)
    _fix(sys.stderr)


def _encodable(ch: str) -> bool:
    encoding = getattr(sys.stdout, "encoding", None) or "ascii"
    try:
        ch.encode(encoding)
    except (UnicodeEncodeError, LookupError):
        return False
    return True


def sym(text: str) -> str:
    """把当前编码编不出的状态符号换成 ASCII 等价物，其余字符原样返回。"""
    return "".join(
        _ASCII[ch] if ch in _ASCII and not _encodable(ch) else ch
        for ch in text
    )
