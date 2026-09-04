#!/usr/bin/env python3
"""区分「外部工具没装」和「装了，但这个终端的 PATH 是旧的」。

**为什么需要**：Windows 上装完 TeX Live / Pandoc，安装器把 bin 目录写进注册表 PATH，
但**已经打开的进程不会继承**——它们拿的是启动那一刻的环境快照。
于是 `shutil.which("xelatex")` 返回 None，而同一台机器上新开一个终端明明能用。

2026-09-03 本机实测踩到两次：TeX Live 装于当天 18:28、Pandoc 装于 15:14，
两者都在用户 PATH 里，但更早启动的 shell 一个都看不见。
doctor.py 把这判成「Stage 0 的 block，不允许推迟」——
一个「新开个终端就好」的问题被报成致命环境缺失，开赛当天足以让一支队白掉半小时。

所以查找按三级递进，且**把命中来源一起返回**，让调用方能给出对症的说法：

1. 当前进程 PATH —— 真能直接调，`source="path"`；
2. 注册表里的持久 PATH（HKCU\\Environment 与 HKLM 的系统环境）——
   `source="stale-shell"`，说明装了，重开终端即可；
3. 常见安装目录（TeX Live 的静默安装在某些配置下确实不写 PATH）——
   `source="install-dir"`，说明要手动加 PATH。

后两种情况会把目录前插进 `os.environ["PATH"]`，**只在本进程内生效**。
不动注册表——改用户 PATH 是有副作用的操作，不该由一个体检脚本悄悄替用户做。
"""

from __future__ import annotations

import glob
import os
import shutil
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Found:
    """一次工具查找的结果。`directory` 为 None 表示没找到。"""

    directory: Path | None
    source: str  # "path" | "stale-shell" | "install-dir" | "missing"

    @property
    def ok(self) -> bool:
        return self.directory is not None or self.source == "path"

    @property
    def recovered(self) -> bool:
        """找到了，但不是靠当前进程的 PATH——即需要向用户解释一句的情形。"""
        return self.source in ("stale-shell", "install-dir")


# 只有那些"安装器可能漏掉 PATH"的工具才需要列安装目录。
_INSTALL_DIRS: dict[str, list[str]] = {
    "xelatex": [
        r"C:\texlive\*\bin\*",
        r"C:\Program Files\MiKTeX*\miktex\bin\x64",
        r"C:\Program Files\MiKTeX*\miktex\bin",
        r"C:\Program Files (x86)\MiKTeX*\miktex\bin*",
        r"%LOCALAPPDATA%\Programs\MiKTeX\miktex\bin\x64",
        "/usr/local/texlive/*/bin/*",
        "/opt/texlive/*/bin/*",
        "/Library/TeX/texbin",
        "~/.TinyTeX/bin/*",
    ],
    "pandoc": [
        r"C:\Program Files\Pandoc",
        r"%LOCALAPPDATA%\Pandoc",
        r"%USERPROFILE%\tools\pandoc*",
        "/usr/local/bin",
        "/opt/homebrew/bin",
    ],
}


def _persistent_path_dirs() -> list[str]:
    """注册表里的持久 PATH。取不到就返回空表（非 Windows、或权限不足）。"""
    if os.name != "nt":
        return []
    import winreg

    keys = (
        (winreg.HKEY_CURRENT_USER, "Environment"),
        (winreg.HKEY_LOCAL_MACHINE,
         r"SYSTEM\CurrentControlSet\Control\Session Manager\Environment"),
    )
    dirs: list[str] = []
    for hive, subkey in keys:
        try:
            with winreg.OpenKey(hive, subkey) as key:
                raw, _ = winreg.QueryValueEx(key, "Path")
        except OSError:
            continue
        for part in str(raw).split(os.pathsep):
            # REG_EXPAND_SZ 里可能写着 %USERPROFILE% 一类，得展开才能当路径用
            cleaned = os.path.expandvars(part).strip().strip('"')
            if cleaned:
                dirs.append(cleaned)
    return dirs


def _exe_names(tool: str) -> tuple[str, ...]:
    if os.name != "nt":
        return (tool,)
    exts = os.environ.get("PATHEXT", ".EXE;.BAT;.CMD").split(os.pathsep)
    return tuple(tool + ext.lower() for ext in exts if ext) or (f"{tool}.exe",)


def find(tool: str) -> Found:
    """按 PATH → 持久 PATH → 常见安装目录 三级查找 `tool`。"""
    if shutil.which(tool) is not None:
        return Found(None, "path")

    names = _exe_names(tool)
    for directory in _persistent_path_dirs():
        for name in names:
            if (Path(directory) / name).is_file():
                return Found(Path(directory), "stale-shell")

    for pattern in _INSTALL_DIRS.get(tool, []):
        expanded = os.path.expandvars(os.path.expanduser(pattern))
        for name in names:
            # 倒序：C:\texlive\2026b 排在 2026、2025 前面，优先用最新的发行版
            for hit in sorted(glob.glob(os.path.join(expanded, name)), reverse=True):
                if Path(hit).is_file():
                    return Found(Path(hit).parent, "install-dir")

    return Found(None, "missing")


def ensure_on_path(tool: str) -> Found:
    """查找 `tool`，必要时把它的目录前插进本进程 PATH。"""
    found = find(tool)
    if found.directory is not None:
        os.environ["PATH"] = f"{found.directory}{os.pathsep}{os.environ.get('PATH', '')}"
    return found


def advice(tool: str, found: Found) -> str | None:
    """针对命中来源给出的一句人话建议。已经在 PATH 上时返回 None。"""
    if found.source == "path":
        return None
    if found.source == "stale-shell":
        return (
            f"{tool} 装了（{found.directory}），只是**这个终端的环境变量是安装之前的快照**。"
            "本次已在进程内补好，但同一个终端里手敲命令仍然找不到它——"
            "新开一个终端（或重启编辑器）就正常了。"
        )
    if found.source == "install-dir":
        return (
            f"{tool} 装在 {found.directory}，但没进 PATH。本次已在进程内补入；"
            f"永久修：把该目录加进用户 PATH（Windows: 系统属性 → 环境变量 → Path → 新建），"
            "改完新开一个终端。"
        )
    return None
