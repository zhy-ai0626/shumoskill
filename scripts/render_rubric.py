#!/usr/bin/env python3
"""从 `config/rubric.json` 生成 md 里的 rubric 表格，并检查有没有漂移。

为什么需要这个脚本
------------------
同一份 L1 rubric 曾散在**四个地方**，没有任何一致性检查：

| 位置 | 是什么 |
|---|---|
| `scripts/score_artifact.py: DIM_WHITELIST` | 代码白名单，Critic 产出的键不在里面就 FAIL |
| `references/rubrics.md` | 声明为 canonical 的人读表格 |
| `references/stage_0N_*.md` | 每个 stage 文件里的平行副本（agent 运行时真正读的） |
| `config/dim_weights.json` | 按题型加权，键必须在白名单里 |

**实测漂移**（重构前逐份抽出来比对的结果）：

- stage 1 / 3 / 6 / 7 的维度**名称两边完全不同**——「命名准确性」vs
  「模型命名真实性」、「局限真实」vs「缺点真实」。键相同，所以
  **既有的每一项检查都查不出来**：Critic 照 stage 文件打分，
  评的却是和 canonical 表描述不同的东西；
- stage 5 的 stage-level 五维、stage 9 的五维，在 `rubrics.md` 里**干脆没有表**
  （前者只有两条散文，后者只写了 L3 panel）——白名单有键、没有满分行为，
  Critic 只能自己编判据；
- 四份副本不可能靠记性同步，而它们不同步的表现是"某条判据静默失效"。

所以：**`config/rubric.json` 是唯一数据源**，md 里的表格由本脚本生成，
`score_artifact.py` 的白名单也从同一份 JSON 加载。改判据改 JSON，然后 `--write`。

用法
----
    python scripts/render_rubric.py --check    # 有漂移就退出 1（doctor 会跑）
    python scripts/render_rubric.py --write    # 按 JSON 重写全部表格
    python scripts/render_rubric.py --diff      # 只看差异，不改文件
    python scripts/render_rubric.py --whitelist # 打印维度键白名单

退出码：0 = 一致；1 = 有漂移或缺 marker；2 = 没跑成。
"""

from __future__ import annotations

import argparse
import difflib
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _console  # noqa: E402

SKILL_ROOT = Path(__file__).resolve().parent.parent
RUBRIC_JSON = SKILL_ROOT / "config" / "rubric.json"

# 表格插到哪。**同一个 stage 键可以出现在多个文件里**——canonical 表在
# rubrics.md，运行时副本在 stage 文件；两边由同一份 JSON 生成，因此不可能再漂。
TARGETS: tuple[tuple[str, str], ...] = (
    ("references/rubrics.md", "0"),
    ("references/rubrics.md", "1"),
    ("references/rubrics.md", "2"),
    ("references/rubrics.md", "3"),
    ("references/rubrics.md", "4"),
    ("references/rubrics.md", "5"),
    ("references/rubrics.md", "5_per_qi"),
    ("references/rubrics.md", "6"),
    ("references/rubrics.md", "7"),
    ("references/rubrics.md", "8"),
    ("references/rubrics.md", "9"),
    ("references/stage_00_kickoff.md", "0"),
    ("references/stage_01_problem_selection.md", "1"),
    ("references/stage_02_analysis.md", "2"),
    ("references/stage_03_model_selection.md", "3"),
    ("references/stage_04_foundation.md", "4"),
    ("references/stage_05_subproblem_loop.md", "5_per_qi"),
    ("references/stage_05_subproblem_loop.md", "5"),
    ("references/stage_06_robustness.md", "6"),
    ("references/stage_07_evaluation.md", "7"),
    ("references/stage_08_writing.md", "8"),
    ("references/stage_09_review.md", "9"),
)

BEGIN = "<!-- RUBRIC:BEGIN %s -->"
END = "<!-- RUBRIC:END %s -->"


def load() -> dict:
    try:
        return json.loads(RUBRIC_JSON.read_text(encoding="utf-8"))
    except OSError as exc:
        raise SystemExit("读不到 %s: %s" % (RUBRIC_JSON, exc))
    except json.JSONDecodeError as exc:
        raise SystemExit("%s 不是合法 JSON: %s" % (RUBRIC_JSON, exc))


def whitelist(data: dict | None = None) -> dict:
    """{stage_key: {dim_key, ...}}。stage 键是 int（"5_per_qi" 保持字符串）。

    `score_artifact.py` 用它替代原来硬编码的 DIM_WHITELIST。
    int/str 混用的键型是上游约定，这里如实保留——**改键型会静默改掉
    `load_dim_whitelist` 的查表结果**。
    """
    data = data or load()
    out: dict = {}
    for key, node in (data.get("stages") or {}).items():
        k = int(key) if key.isdigit() else key
        out[k] = {d["key"] for d in node["dims"]}
    return out


def render(data: dict, stage_key: str) -> str:
    node = (data.get("stages") or {}).get(stage_key)
    if node is None:
        raise SystemExit("config/rubric.json 里没有 stage %r" % stage_key)
    n = data.get("dims_per_stage", 5)
    dims = node["dims"]
    if len(dims) != n:
        raise SystemExit("stage %s 有 %d 维，应为 %d —— L1 架构是固定 %d 维，"
                         "要加判据请折进已有维度" % (stage_key, len(dims), n, n))
    # `fail_marks` 是可选的 1 分锚点。任一维有它就出三列——
    # **给 Critic 两端锚点比只给满分行为更好**，而原 stage 0 表就是三列的，
    # 一律出两列会把那一列信息静默丢掉。
    has_fail = any((d.get("fail_marks") or "").strip() for d in dims)
    if has_fail:
        lines = ["| 维度 | 满分行为 (10) | 失败行为 (1) |",
                 "|------|-------------|-------------|"]
    else:
        lines = ["| 维度 | 满分行为 |", "|------|---------|"]
    for i, d in enumerate(dims, 1):
        num = int(d["key"].split("_", 1)[0])
        if num != i:
            raise SystemExit("stage %s 第 %d 维的键是 %r，编号对不上"
                             % (stage_key, i, d["key"]))
        cells = ["%d. %s (`%s`)" % (i, d["name"], d["key"]), d["full_marks"]]
        if has_fail:
            cells.append((d.get("fail_marks") or "").strip() or "—")
        # 单元格里出现裸 `|` 会把表格撑出多余一列，必须转义
        lines.append("| " + " | ".join(c.replace("|", r"\|") for c in cells)
                     + " |")
    return "\n".join(lines)


def _split(text: str, stage_key: str) -> tuple[str, str, str] | None:
    """按 marker 切成 (前, 块内, 后)。找不到 marker 返回 None。"""
    b, e = BEGIN % stage_key, END % stage_key
    i = text.find(b)
    if i < 0:
        return None
    j = text.find(e, i)
    if j < 0:
        return None
    return text[: i + len(b)], text[i + len(b): j], text[j:]


def process(write: bool, show_diff: bool = True) -> tuple[int, list[str]]:
    """返回 (漂移数, 报告行)。write=True 时顺手改文件。"""
    data = load()
    msgs: list[str] = []
    drift = 0
    # 同一个文件里有多个块，逐个替换后一次写回
    by_file: dict[Path, list[str]] = {}
    for rel, key in TARGETS:
        by_file.setdefault(SKILL_ROOT / rel, []).append(key)

    for path, keys in by_file.items():
        if not path.is_file():
            msgs.append("缺文件 %s" % path.relative_to(SKILL_ROOT))
            drift += 1
            continue
        text = original = path.read_text(encoding="utf-8")
        for key in keys:
            want = "\n" + render(data, key) + "\n"
            part = _split(text, key)
            if part is None:
                msgs.append(
                    "%s 缺 marker：请在该 stage 的 rubric 表格外包一对\n"
                    "    %s\n    %s"
                    % (path.relative_to(SKILL_ROOT), BEGIN % key, END % key))
                drift += 1
                continue
            head, body, tail = part
            if body == want:
                continue
            drift += 1
            msgs.append("%s [stage %s] 与 config/rubric.json 不一致"
                        % (path.relative_to(SKILL_ROOT), key))
            if show_diff:
                d = difflib.unified_diff(
                    body.splitlines(), want.splitlines(),
                    fromfile="md（现状）", tofile="rubric.json（应为）",
                    lineterm="", n=0)
                msgs.extend("    " + ln for ln in list(d)[2:])
            text = head + want + tail
        if write and text != original:
            path.write_text(text, encoding="utf-8")
            msgs.append("已重写 %s" % path.relative_to(SKILL_ROOT))
    return drift, msgs


def main(argv: list[str] | None = None) -> int:
    _console.init()
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--check", action="store_true",
                   help="只检查是否一致，有漂移退出 1（默认）")
    g.add_argument("--write", action="store_true", help="按 JSON 重写表格")
    g.add_argument("--diff", action="store_true", help="打印差异，不改文件")
    g.add_argument("--whitelist", action="store_true",
                   help="打印维度键白名单（JSON）")
    args = ap.parse_args(argv)

    if args.whitelist:
        wl = whitelist()
        print(json.dumps({str(k): sorted(v) for k, v in wl.items()},
                         ensure_ascii=False, indent=2))
        return 0

    drift, msgs = process(write=args.write, show_diff=not args.check or args.diff)
    for line in msgs:
        print(line)
    if args.write:
        print(_console.sym("\n✓ 已按 config/rubric.json 重写 %d 处。" % drift
                           if drift else "\n✓ 本来就一致，未改动任何文件。"))
        return 0
    if drift:
        print("\n%d 处与 config/rubric.json 不一致。" % drift)
        print("**config/rubric.json 是唯一数据源**——不要手改 md 表格。"
              "改 JSON 后跑 `python scripts/render_rubric.py --write`。")
        return 1
    print(_console.sym("✓ %d 处表格与 config/rubric.json 完全一致。"
                       % len(TARGETS)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
