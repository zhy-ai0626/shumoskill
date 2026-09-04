#!/usr/bin/env python3
"""自检承诺与局限的了结检查：写下来的自检必须真的跑过，说出口的局限必须被裁定。

为什么需要这个脚本
------------------
这是本 skill 演练记录里**重复次数最多的失效模式**，三轮各栽一次：

- 第 2 轮（2023B）：方案里写了「β=0/90° 极限退化自检」，**没有执行**，
  结果 sin/cos 配反一直没被发现。
- 2025C 端到端：混合模型边际 R² 虚高一倍多，靠方差分解恒等式才查出来。
- 2025B 端到端：论文 §3.2 自己写下「精度上限由折射率的已知程度决定」——
  这句话本身就指出了应该去反演折射率，**却被写成了『局限』**。
  官方讲评原话点名「按常数计算…没有达到题目的要求」。

`交付/README.md` 把它总结成一句：「skill 能提醒该做什么，不能保证真去做。」
纯散文提醒治不了，因为提醒和执行是同一个人做的。所以要一个**外部可判定**的 gate。

两条判据
--------
1. **承诺必须了结**。论文/工作区里凡出现自检承诺句（「极限退化」「量纲」「守恒」
   「作为自检」……），台账 `state/self_audit.json` 里必须有一条引用了那句话的条目，
   且状态是 done（带结果文件）或 dropped（带真实理由）。
   只写在台账里而不执行 = FAIL；写在论文里而台账没有 = 也 FAIL——
   后者才是演练里真正发生的那种，只查台账等于自己查自己。

2. **局限必须被裁定**。论文里每句「本方法的局限是 X / 未考虑 X / 尚未 X」，
   都要在台账里裁定成三者之一：
   - `inherent`（题目/数据决定的固有边界，做不掉）
   - `out-of-scope`（能做但明确不在本题要求内，须说明依据）
   - `should-have-done`（**本来就该做掉的**）→ 未解决即 FAIL

   第三类就是 2025B 栽的那处。判据很简单：**如果这句话自己指出了出路，
   它就不是局限，是没做完的活。**

台账怎么写
----------
台账是人（或 agent）维护的 JSON，模板见 `templates/shared/self_audit.json`。
每条 `source_quote` 必须是它所了结的那句话里的一段原文——匹配靠子串包含，
不做模糊匹配，所以引用错了会直接报出来，不会悄悄放过。

用法
----
    python scripts/check_selfaudit.py --ledger state/self_audit.json --paper paper.tex
    python scripts/check_selfaudit.py --ledger state/self_audit.json \
        --paper paper.tex --workspace paper_workspace/ --results results/
    python scripts/check_selfaudit.py --ledger state/self_audit.json --paper paper.tex --json

    # 首次使用：从论文里扫出所有待了结的句子，生成台账骨架
    python scripts/check_selfaudit.py --paper paper.tex --scaffold > state/self_audit.json

退出码：0 = 全部了结；1 = 有未了结项；2 = 没跑成（文件缺失、JSON 坏）。
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _console  # noqa: E402

VALID_STATUS = ("done", "promised", "dropped")
VALID_VERDICT = ("pass", "fail")
VALID_RULING = ("inherent", "out-of-scope", "should-have-done")

# —— 承诺句式 ——
# 只收**强承诺**词。像「验证」「检查」这种词在论文里满地都是（"验证了模型的有效性"），
# 收进来会把整份论文报成待办，用的人第一时间就会把这个 gate 关掉。
# 宁可漏，不可吵：这里每一条都是"写下来就意味着要跑一段代码"的说法。
PROMISE_PATTERNS = (
    r"极限[退化情形]",
    r"退化[到为]",
    r"量纲(?:检查|分析|一致|齐次)",
    r"守恒(?:检查|校验|律验证)",
    r"作为(?:一个)?自检",
    r"自检",
    r"应(?:当|该)?满足",
    r"必须满足",
    r"边界(?:情形|条件)检验",
    r"独立(?:复算|重算|实现)",
    r"交叉验证该结论",
    r"敏感性分析",
    r"留待(?:后文|下文)(?:验证|检验)",
)
# —— 局限句式 ——
# 同样要窄。裸 `尚未` 会把「对一位尚未检测过的新孕妇」这种**人群描述**报成局限
# （2025C 实测命中），所以一律要求后面跟着"做某件事"的动词——
# 局限说的是"没做某事"，不是"某物没发生过"。
LIMIT_PATTERNS = (
    # 「布局限于两个族」「格局限制」里的"局限"是切错词，不是在讲局限性。
    # 中文没有词边界，只能对高频假友做负向断言（2023A 演练实测踩到"布局限于"）。
    r"(?<![布格])局限",
    r"不足之处",
    r"未(?:能|曾)?考虑",
    r"没有考虑",
    r"尚未(?:能)?(?:考虑|处理|验证|实现|解决|讨论|建模|给出|纳入|做)",
    r"未(?:做|给出|纳入|建模)",
    r"有待(?:进一步)?(?:研究|验证|改进|完善|讨论|检验)",
    r"受限于",
    r"本文(?:并)?未(?:能)?",
)
# 标题里出现这些词，整个区块的句子都要逐条裁定。
# 光靠句式会漏掉最要命的那种：2025B 的局限写在 `\paragraph{局限。}` 底下，
# 分条列举时每条里都没有"局限"二字，剥掉命令后标题本身又短到被当碎片丢弃。
# 用「不足之处」而不是裸「不足」：2025A 有个正文小节叫『搜索覆盖不足，不是题目性质』，
# 裸词会把整节正文都拖进待裁定清单。
LIMIT_SECTION_PATTERN = (r"(?<![布格])局限|不足之处|缺陷|改进方向|模型评价"
                         r"|误差来源|适用范围")

# 自陈"这个量我取了个定值"。这是反模式 Z22 的机器可检形式：
# 2025B 官方讲评原话点名「折射率按常数计算…没有达到题目的要求」，
# 而本项目那轮演练的 paper.tex 里就明写着「硅在中红外取常数」。
# 泛化判据：**题面若说某参数与别的量有关，那是要你把它当待估量，不是让你去查文献值。**
SHORTCUT_PATTERNS = (
    r"取(?:为)?常数", r"视为常数", r"按常数", r"设(?:为|成)常数", r"当作常数",
    r"取(?:自)?文献值", r"采用文献值", r"引用文献值",
    r"取(?:经验值|典型值|标称值|默认值)",
)

_TEX_STRIP = (
    (re.compile(r"(?<!\\)%.*"), ""),               # 注释
    # 代码清单整块丢掉：里面的注释会把「# 八项自检」这种行报成承诺句。
    (re.compile(r"\\begin\{(lstlisting|verbatim|minted)\}[\s\S]*?"
                r"\\end\{\1\}"), " "),
    (re.compile(r"\\(?:label|ref|cite|eqref|includegraphics)\{[^}]*\}"), ""),
    (re.compile(r"\$[^$]*\$"), " 〈公式〉 "),       # 行内公式整体折叠
    (re.compile(r"\\\[[\s\S]*?\\\]"), " 〈公式〉 "),
    (re.compile(r"\\begin\{(equation|align|gather)\*?\}[\s\S]*?"
                r"\\end\{\1\*?\}"), " 〈公式〉 "),
    (re.compile(r"\n\s*\n"), "。"),                # 空行 = 段落边界，当句号
    (re.compile(r"\\\\"), "。"),                   # 表格/换行命令同样断句
    # 环境名要连 \begin{} 一起删，**并且带上后面的可选参数**。只删 \begin{name}
    # 会把 `[label=(\arabic*),leftmargin=2em]` 整串留在正文里当句子扫
    # （2023A 演练实测）；只删命令名还会把 enumerate / itemize 留下来。
    (re.compile(r"\\(?:begin|end)\{[^}]*\}(?:\[[^\]]*\])?"), "。"),
    (re.compile(r"\\[a-zA-Z]+\*?"), " "),          # 其余命令名
    (re.compile(r"[{}]"), ""),
)
_SENT_SPLIT = re.compile(r"[。！？；]")


def strip_markup(text: str) -> str:
    for rx, rep in _TEX_STRIP:
        text = rx.sub(rep, text)
    return text


def sentences(text: str) -> list[str]:
    """切句。

    **不能按 \\n 断句**：LaTeX 源码是硬换行的，一句话在文件里横跨好几行，
    按 \\n 切会把「……但无法排除 X」截成「……但无」，扫出来的句子读不通，
    引用进台账的 source_quote 也就成了半截话。
    只在真正的句子边界（。！？；、空行、\\\\）上断。
    """
    out = []
    for raw in _SENT_SPLIT.split(strip_markup(text)):
        s = re.sub(r"\s+", " ", raw).strip()
        if len(s) < 8:             # 太短的多半是标题或表格残片
            continue
        if " & " in s:             # tabular 行，不是散文
            continue
        out.append(s)
    return out


_PRE_STRIP = (
    (re.compile(r"(?<!\\)%.*"), ""),
    (re.compile(r"\\begin\{(lstlisting|verbatim|minted)\}[\s\S]*?"
                r"\\end\{\1\}"), " "),
)
# 不收 \textbf：它是段落里的强调，不是小节标题。收了会把
# `\textbf{布局限于两个参数化族}` 当成"局限"区块的开头，把整段正文拖进待裁定清单。
_HEADING_RX = re.compile(
    r"\\(?:section|subsection|subsubsection|paragraph)\*?\{([^}]*)\}")
_LIMIT_SECTION_RX = re.compile(LIMIT_SECTION_PATTERN)


def _blocks(text: str) -> list[tuple[str, str]]:
    """按标题把正文切成 (标题, 区块正文)。标题之前的部分标题为 ""。"""
    for rx, rep in _PRE_STRIP:
        text = rx.sub(rep, text)
    out: list[tuple[str, str]] = []
    pos, heading = 0, ""
    for m in _HEADING_RX.finditer(text):
        out.append((heading, text[pos:m.start()]))
        heading, pos = m.group(1), m.end()
    out.append((heading, text[pos:]))
    return out


def scan(paths: list[Path]) -> tuple[list[dict], list[dict], list[dict]]:
    """返回 (承诺句, 待裁定的局限句, 取定值的自陈)，每项 {file, sentence, why}。"""
    promises, limits, shortcuts = [], [], []
    p_rx = [re.compile(p) for p in PROMISE_PATTERNS]
    l_rx = [re.compile(p) for p in LIMIT_PATTERNS]
    s_rx = [re.compile(p) for p in SHORTCUT_PATTERNS]
    for path in paths:
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        for heading, body in _blocks(text):
            in_limit_section = bool(_LIMIT_SECTION_RX.search(heading))
            for s in sentences(body):
                rec = {"file": path.name, "sentence": s}
                if any(rx.search(s) for rx in p_rx):
                    promises.append(rec)
                if in_limit_section:
                    limits.append({**rec, "why": "在『%s』区块内" % heading.strip()})
                elif any(rx.search(s) for rx in l_rx):
                    limits.append({**rec, "why": "句式"})
                if any(rx.search(s) for rx in s_rx):
                    shortcuts.append({**rec, "why": "自陈取定值"})
    return promises, limits, shortcuts


def collect_paths(paper: str | None, workspace: str | None) -> list[Path]:
    paths: list[Path] = []
    if paper:
        paths.append(Path(paper))
    if workspace:
        paths.extend(sorted(Path(workspace).glob("*.md")))
    return [p for p in paths if p.is_file()]


def _covered(sentence: str, quotes: list[str]) -> str | None:
    """台账里哪条 source_quote 落在这句话里。引用必须是原文子串。"""
    for q in quotes:
        if q and q in sentence:
            return q
    return None


def check(ledger: dict, paper_promises: list[dict], paper_limits: list[dict],
          paper_shortcuts: list[dict], results_dir: Path | None) -> list[dict]:
    """返回问题列表；每项 {level, kind, msg, hint}。"""
    issues: list[dict] = []

    def bad(kind: str, msg: str, hint: str = "", level: str = "FAIL") -> None:
        issues.append({"level": level, "kind": kind, "msg": msg, "hint": hint})

    claims = ledger.get("claims", [])
    limitations = ledger.get("limitations", [])

    # —— 1. 台账自身的条目 ——
    for i, c in enumerate(claims):
        cid = c.get("id") or "claims[%d]" % i
        status = c.get("status")
        if status not in VALID_STATUS:
            bad("schema", "%s 的 status=%r 不合法" % (cid, status),
                "只能是 %s" % "/".join(VALID_STATUS))
            continue
        if not c.get("source_quote"):
            bad("schema", "%s 缺 source_quote" % cid,
                "必须引用论文里那句话的一段原文，否则无法判断它了结了什么")
        if status == "promised":
            # scaffold 生成的条目 claim 是空的，退回引用原文，否则这行看不出是哪一条
            what = (c.get("claim") or c.get("source_quote") or "").strip()
            bad("unrun", "%s 承诺了但没执行：%s" % (cid, what[:60]),
                "跑掉它并把结果写进 results/，或改成 dropped 并写明理由。"
                "第 2 轮演练就是卡在这里——写了极限自检没跑，sin/cos 配反没被发现")
        elif status == "dropped":
            reason = (c.get("dropped_reason") or "").strip()
            if len(reason) < 10:
                bad("thin-reason", "%s 标了 dropped，理由太短或为空" % cid,
                    "写清为什么这条自检不必做；『时间不够』不是理由，"
                    "那说明它该降级成已知风险写进 Stage 7")
        elif status == "done":
            ev = c.get("result_file")
            if not ev:
                bad("no-evidence", "%s 标了 done 但没有 result_file" % cid,
                    "自检结果要落到 results/ 下的 .json，评委核的是可机读的结果文件")
            elif results_dir is not None and not (results_dir / Path(ev).name).exists() \
                    and not Path(ev).exists():
                bad("missing-evidence", "%s 的 result_file 不存在：%s" % (cid, ev),
                    "路径写错，或者文件根本没生成")
            verdict = c.get("verdict")
            if verdict not in VALID_VERDICT:
                bad("no-verdict", "%s 标了 done 但 verdict=%r" % (cid, verdict),
                    "跑完了必须给结论：pass 或 fail")
            elif verdict == "fail" and not (c.get("action") or "").strip():
                bad("unhandled-fail", "%s 的自检没通过，但没写后续处理" % cid,
                    "自检 fail 是**好事**——它抓到了一个错。"
                    "写清改了什么；如果决定接受，说明为何不影响主结论")

    # —— 2. 论文里的承诺是否都进了台账 ——
    quotes = [c.get("source_quote", "") for c in claims]
    for rec in paper_promises:
        if _covered(rec["sentence"], quotes) is None:
            bad("unlogged-promise",
                "%s 里这句承诺不在台账里：%s" % (rec["file"], rec["sentence"][:70]),
                "加一条 claims 条目引用它。**这一类才是演练里真正栽掉的**："
                "承诺写在散文里、从没进过台账，只查台账等于自己查自己。"
                "确实不是承诺就加一条 status=dropped 并写明")

    # —— 3. 论文里的局限是否都被裁定 ——
    lim_quotes = [l.get("quote", "") for l in limitations]
    for rec in paper_limits:
        if _covered(rec["sentence"], lim_quotes) is None:
            bad("unadjudicated-limit",
                "%s 里这句局限没有裁定：%s" % (rec["file"], rec["sentence"][:70]),
                "裁成 inherent / out-of-scope / should-have-done。"
                "判据：**这句话是不是自己指出了出路**——是就不是局限，是没做完的活")

    # —— 4. 自陈"取常数/文献值"的量是否被裁定过（反模式 Z22）——
    for rec in paper_shortcuts:
        if _covered(rec["sentence"], lim_quotes) is None:
            bad("unadjudicated-shortcut",
                "%s 里有一处取定值没有裁定：%s"
                % (rec["file"], rec["sentence"][:70]),
                "回题面确认：题目有没有说这个量『与 X 有关』/『随 Y 变化』？"
                "说了就是要你把它当待估量。2025B 官方原话："
                "「折射率按常数计算…没有达到题目的要求」（反模式 Z22）。"
                "确认题面没这么要求，就裁定成 out-of-scope 并写明依据")

    for i, l in enumerate(limitations):
        lid = l.get("id") or "limitations[%d]" % i
        ruling = l.get("ruling")
        if ruling not in VALID_RULING:
            bad("schema", "%s 的 ruling=%r 不合法" % (lid, ruling),
                "只能是 %s" % "/".join(VALID_RULING))
            continue
        if ruling == "should-have-done" and not l.get("resolved"):
            bad("should-have-done",
                "%s 被裁定为『本来就该做掉』但未解决：%s"
                % (lid, (l.get("quote") or "")[:60]),
                "去做掉它，或降级裁定并说明为什么做不了。"
                "2025B 就是把『精度上限由折射率的已知程度决定』写成了局限，"
                "官方原话点名『按常数计算…没有达到题目的要求』")
        if ruling in ("inherent", "out-of-scope") and \
                len((l.get("basis") or "").strip()) < 10:
            bad("thin-basis", "%s 裁定为 %s 但没写依据" % (lid, ruling),
                "说清凭什么做不了 / 凭什么不在本题范围内", level="WARN")

    return issues


def scaffold(promises: list[dict], limits: list[dict],
             shortcuts: list[dict]) -> dict:
    """扫出来的句子直接生成台账骨架，省得手抄 source_quote。"""
    def quote(s: str) -> str:
        return s[:40]

    to_rule = limits + shortcuts
    return {
        "_readme": "每条 source_quote / quote 必须是论文原文的子串；"
                   "改论文措辞后要同步改这里，否则会报『不在台账里』——"
                   "这是有意的，措辞改了就得重新确认它有没有被了结。",
        "claims": [
            {"id": "SA%d" % (i + 1), "claim": "", "source_quote": quote(r["sentence"]),
             "from_file": r["file"], "status": "promised",
             "result_file": "", "verdict": "", "action": "", "dropped_reason": ""}
            for i, r in enumerate(promises)
        ],
        "limitations": [
            {"id": "LM%d" % (i + 1), "quote": quote(r["sentence"]),
             "from_file": r["file"], "why_flagged": r.get("why", ""),
             "ruling": "", "basis": "", "resolved": False}
            for i, r in enumerate(to_rule)
        ],
    }


def main(argv: list[str] | None = None) -> int:
    _console.init()
    ap = argparse.ArgumentParser(description="自检承诺与局限的了结检查")
    ap.add_argument("--ledger", help="state/self_audit.json")
    ap.add_argument("--paper", help="paper.tex 或 paper.md")
    ap.add_argument("--workspace", help="paper_workspace/，扫其中的 *.md")
    ap.add_argument("--results", help="results/，用来验证 result_file 是否真存在")
    ap.add_argument("--scaffold", action="store_true",
                    help="只扫描并输出台账骨架 JSON，不做检查")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)

    paths = collect_paths(args.paper, args.workspace)
    if not paths:
        print("没有可扫描的文件，--paper / --workspace 至少给一个有效路径",
              file=sys.stderr)
        return 2
    promises, limits, shortcuts = scan(paths)

    if args.scaffold:
        print(json.dumps(scaffold(promises, limits, shortcuts),
                         ensure_ascii=False, indent=2))
        return 0

    if not args.ledger:
        print("缺 --ledger；首次使用先跑 --scaffold 生成台账骨架", file=sys.stderr)
        return 2
    lpath = Path(args.ledger)
    if not lpath.is_file():
        print("找不到台账 %s；先跑 --scaffold 生成" % args.ledger, file=sys.stderr)
        return 2
    try:
        ledger = json.loads(lpath.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        print("台账读不了：%s" % exc, file=sys.stderr)
        return 2

    results_dir = Path(args.results) if args.results else None
    issues = check(ledger, promises, limits, shortcuts, results_dir)
    fails = [i for i in issues if i["level"] == "FAIL"]
    warns = [i for i in issues if i["level"] == "WARN"]

    if args.json:
        print(json.dumps({
            "scanned_files": [p.name for p in paths],
            "promise_sentences": len(promises),
            "limit_sentences": len(limits),
            "shortcut_sentences": len(shortcuts),
            "claims": len(ledger.get("claims", [])),
            "limitations": len(ledger.get("limitations", [])),
            "issues": issues, "fails": len(fails), "warns": len(warns),
        }, ensure_ascii=False, indent=2))
        return 1 if fails else 0

    print(_console.sym("=== 自检了结检查 ==="))
    print("扫描 %d 个文件：承诺句 %d，待裁定局限 %d，取定值自陈 %d；"
          "台账 claims %d，limitations %d\n"
          % (len(paths), len(promises), len(limits), len(shortcuts),
             len(ledger.get("claims", [])), len(ledger.get("limitations", []))))
    if not issues:
        print(_console.sym("✓ 全部了结。"))
        return 0
    for it in issues:
        print(_console.sym("  %s [%s] %s"
                           % ("✗ FAIL" if it["level"] == "FAIL" else "⚠ WARN",
                              it["kind"], it["msg"])))
        if it["hint"]:
            print("          " + it["hint"])
    print("\n%d FAIL，%d WARN" % (len(fails), len(warns)))
    if fails:
        print(_console.sym("\n★ 有未了结的自检或局限。"
                           "这正是本 skill 三轮演练重复栽掉的地方，别跳过。"))
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
