#!/usr/bin/env python3
"""提交前合规自查：机器能判定的格式与规则项，一次跑完。

为什么需要这个脚本
------------------
`references/stage_09_review.md` §1 把合规项写成了一张散文清单（摘要页、无目录、
无身份信息、AI 声明、附录源程序……），全靠人在交卷前逐条肉眼核。而这类项的特点是
**违规不报错、后果却是取消评奖资格**——《论文格式规范（2026 修订稿）》第六条身份信息、
《人工智能工具使用规定（2026 试行）》第 3 条 AI 声明，都属于"错了就没得商量"。

本脚本把清单里能机器判定的部分变成一条命令。相对散文清单，它额外抓三类
肉眼很难查的东西：

1. **中文提取不出来**。用 ctexart 的 fandol 字体编译不报错、屏幕显示也正常，
   但 PDF 缺 ToUnicode CMap，评委检索不到、相似度检测读不出（改用 fontset=windows）。
2. **PDF 元数据里的身份信息**。正文清干净了，文件属性里的作者/单位还在——
   这是"文件属性是否已清空"那条人工项，其实可以直接读。
3. **支撑材料压缩包的内容**。用了 AI 就必须有文件名完全一致的 `AI工具使用详情.pdf`；
   附录声称有源程序，压缩包里却可能一个代码文件都没有。

用法
----
    python scripts/check_compliance.py --paper paper.pdf
    python scripts/check_compliance.py --paper paper.pdf --support 支撑材料.zip
    python scripts/check_compliance.py --paper paper.pdf --json

退出码：0 = 无 FAIL（WARN 与人工项不影响退出码）；1 = 有 FAIL，不要提交。

边界：只编码 **CUMCM 2026** 的规则。MCM/ICM 与电工杯的条款不同，本脚本不冒充检查，
传 `--competition` 为其它值会直接拒绝运行（退出码 2），请回 `current_rules.md` 人工核。
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _console  # noqa: E402

ZH = re.compile(r"[一-鿿]")
AI_NONE = "本参赛队在竞赛过程中未使用任何 AI 工具"
AI_USED = "本参赛队在竞赛过程中使用了 AI 工具"
AI_DETAIL_NAME = "AI工具使用详情.pdf"

# 身份信息关键词：出现即高危（论文格式规范第六条）
IDENTITY = re.compile(r"大学|学院|学校|赛区|队员|指导教师|学号|参赛队号")
# 合法出现的固定措辞。先从全文剔掉再查，
# 免得"全国大学生数学建模竞赛"里的"大学"把整份论文报成身份泄露。
SAFE_PHRASES = (
    "全国大学生数学建模竞赛",
    "大学生数学建模竞赛",
    "中国大学生在线",
    "高教社杯",
    "美国大学生数学建模竞赛",
)

CODE_SUFFIXES = (".py", ".m", ".r", ".ipynb", ".c", ".cpp", ".java",
                 ".jl", ".mod", ".lp", ".mat", ".sh", ".txt")
# 压缩包里不该出现的凭据类文件名片段
SECRET_HINTS = ("id_rsa", ".env", "credential", "token", "secret", "password")

# 只能人工判断的项。脚本每升级一条为机器判定，就从这里删掉一条。
MANUAL_ITEMS = (
    "图表的坐标轴含义与单位是否齐全",
    "结果文件名/列名/单位/行列顺序是否严格照题目模板",
    "摘要与正文里每个数字能否在结果文件里查到同一个值"
    "（可先跑 scripts/check_numbers.py，它只查可追溯性，不查语义）",
    "每个结果后面是否有分析，而不只是罗列数字",
    "AI 生成的参考文献是否逐条打开核对过",
)


class Report:
    """收集检查项。level: FAIL / WARN / MANUAL；ok=True 一律记 PASS。"""

    def __init__(self) -> None:
        self.items: list[dict] = []

    def add(self, cid: str, name: str, ok: bool | None,
            note: str = "", level: str = "FAIL", detail: str = "") -> None:
        """note 只在没通过时显示（解释怎么错、怎么修）；
        detail 无论通过与否都显示（观测到的值）。混用会让 PASS 项打出失败说明。"""
        if ok is True:
            lvl = "PASS"
        elif ok is None:
            lvl = "MANUAL"
        else:
            lvl = level
        self.items.append({"id": cid, "name": name, "ok": ok,
                           "level": lvl, "note": note, "detail": detail})

    def count(self, level: str) -> int:
        return sum(1 for i in self.items if i["level"] == level)


def _page_index(pages: list[str], pattern: str) -> int:
    """返回首次匹配 pattern 的页码（1 起）；找不到返回 0。

    必须带 re.M：标题多半出现在页面中段的某个行首，不带 re.M 时 `^` 只匹配
    整页文本的开头，`^\\s*附\\s*录` 就永远找不到附录页。
    """
    rx = re.compile(pattern, re.M)
    for i, text in enumerate(pages, 1):
        if rx.search(text):
            return i
    return 0


def _decode_entry_name(name: str, utf8_flag: bool) -> str:
    """还原 zip 条目名里的中文。

    WinRAR / 资源管理器在中文 Windows 上打的包，条目名存的是 **GBK 字节且不置
    UTF-8 标志位**。ZipFile 对这类条目一律按 cp437 解码，`AI工具使用详情.pdf`
    会变成 `AI╣ñ╛▀╩╣╙├╧Ω╟Θ.pdf`——不还原就会把"文件名完全一致"误判成不一致。
    """
    if utf8_flag:
        return name
    try:
        return name.encode("cp437").decode("gbk")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return name


def _zip_names(path: str) -> list[str] | None:
    """列出 zip 内的文件名。非 zip（.rar 等）或读不开返回 None。"""
    if not zipfile.is_zipfile(path):
        return None
    try:
        with zipfile.ZipFile(path) as zf:
            return [_decode_entry_name(i.filename, bool(i.flag_bits & 0x800))
                    for i in zf.infolist()]
    except (zipfile.BadZipFile, OSError):
        return None


def check_paper(pdf_path: str, support: str | None, rep: Report) -> dict:
    from pypdf import PdfReader

    reader = PdfReader(pdf_path)
    pages = [(p.extract_text() or "") for p in reader.pages]
    n_pages = len(pages)
    # 必须用 "\n" 拼，不能 "".join：一页只有『目录』两个字时，直接粘上下一页会得到
    # "目录摘 要…"，`^\s*目\s*录\s*$` 就匹配不上，整页目录反而漏检。
    # 反过来也会造出跨页的假匹配。
    all_text = "\n".join(pages)
    first = pages[0] if pages else ""
    box = reader.pages[0].mediabox
    w_mm = float(box.width) / 72 * 25.4
    h_mm = float(box.height) / 72 * 25.4
    size_mb = os.path.getsize(pdf_path) / 1024 / 1024

    # —— 硬性格式 ——
    rep.add("a4", "A4 纸张", abs(w_mm - 210) < 2 and abs(h_mm - 297) < 2,
            detail="%.0f×%.0f mm" % (w_mm, h_mm))
    rep.add("size", "论文 ≤20 MB", size_mb <= 20, detail="%.2f MB" % size_mb)
    rep.add("abstract_first", "第 1 页是摘要页",
            "摘" in first and ("关键词" in first or "关键字" in first),
            "第 1 页应含『摘要』与『关键词』，且不含承诺书/编号页")
    rep.add("abstract_one_page", "摘要未超过一页",
            not re.search(r"问\s*题\s*重\s*述", first),
            "第 1 页出现『问题重述』说明摘要溢出。"
            "溢出往往不是字数问题——先数摘要里的独立公式块，"
            "把 \\[...\\] 改成行内 $...$ 通常就回来了（见 摘要写法.md §4.5）")
    rep.add("no_cover", "承诺书/编号页未混入",
            not re.search(r"承\s*诺\s*书|编\s*号\s*专\s*用\s*页", all_text),
            "电子版不得包含这两页")
    rep.add("no_toc", "正文无目录",
            not re.search(r"^\s*目\s*录\s*$", all_text, re.M), "规范第四条")

    # —— 正文页数（规范：尽量控制在 20 页以内；是"尽量"，所以报 WARN 不报 FAIL）——
    body_start = _page_index(pages, r"问\s*题\s*重\s*述")
    # 附录标题前面常有编号：LaTeX 的 \appendix 会渲染成 "A 附录：源程序清单"，
    # 也有写成 "1 附录" 的。只认行首裸『附录』会把这类论文全判成"定位不到"，
    # 于是正文页数永远退化成人工项（2023A 演练实测）。
    # 但仍必须锚在行首：正文里的"按题面附录"「见附录 B」满地都是。
    appendix_start = _page_index(pages, r"^\s*(?:[A-Z]|\d+)?[\s.、:：]*附\s*录")
    if body_start and appendix_start and appendix_start > body_start:
        body_pages = appendix_start - body_start
        rep.add("body_pages", "正文页数 ≤20 页", body_pages <= 20,
                note="规范说『尽量控制在 20 页以内』，超一两页不是硬性违规，"
                     "但压缩正文优先于删结果分析",
                level="WARN",
                detail="正文约 %d 页（第 %d 页『问题重述』到第 %d 页『附录』之前，"
                       "含参考文献），全文 %d 页"
                       % (body_pages, body_start, appendix_start, n_pages))
    else:
        rep.add("body_pages", "正文页数 ≤20 页", None,
                "定位不到『问题重述』或『附录』的页码，请自行核算（全文 %d 页）" % n_pages)

    # —— 中文可提取（相似度检测 / 评委检索都依赖它）——
    zh_total = len(ZH.findall(all_text))
    rep.add("zh_extractable", "中文可从 PDF 提取", zh_total > 200,
            note="字体缺 ToUnicode CMap：编译不报错、屏幕显示也正常，但评委检索不到、"
                 "相似度检测读不出。ctexart 把 fontset=fandol 改成 fontset=windows "
                 "（无中易字体的机器用 ubuntu / macnew）后重编译，再跑本项确认",
            detail="提取到 %d 个中文字符" % zh_total)

    # —— AI 规定（2026 试行）——
    has_decl = "AI 工具使用声明" in all_text or "AI工具使用声明" in all_text
    rep.add("ai_decl", "有 AI 工具使用声明", has_decl, "2026 年试行规定第 3 条")
    used = AI_USED in all_text
    none = AI_NONE in all_text
    rep.add("ai_verbatim", "声明用官方原句", used or none,
            "必须照抄二者之一，不能改写")
    i_ai = max(all_text.find("AI 工具使用声明"), all_text.find("AI工具使用声明"))
    i_ref = all_text.find("参考文献")
    rep.add("ai_before_ref", "AI 声明在参考文献之前",
            (0 <= i_ai < i_ref) if (i_ai >= 0 and i_ref >= 0) else False,
            "位置 ai=%d ref=%d" % (i_ai, i_ref))

    # —— 附录与源程序 ——
    rep.add("appendix_code", "有附录且含源程序",
            bool(re.search(r"附\s*录", all_text))
            and (bool(re.search(r"源\s*程\s*序|代\s*码", all_text))
                 or "本论文没有用到程序" in all_text),
            "规范第五条：缺程序可能取消评奖资格")

    # —— 身份信息：正文 ——
    scrubbed = all_text
    for phrase in SAFE_PHRASES:
        scrubbed = scrubbed.replace(phrase, "")
    hits = sorted(set(IDENTITY.findall(scrubbed)))
    if hits:
        ctx = []
        for h in hits[:4]:
            i = scrubbed.find(h)
            ctx.append(scrubbed[max(0, i - 12):i + 14].replace("\n", " "))
        rep.add("identity_text", "正文无身份信息痕迹", False,
                "命中 %s；上下文：%s。逐处确认是否为题面原有措辞；"
                "规范第六条违规可取消资格" % (hits, ctx))
    else:
        rep.add("identity_text", "正文无身份信息痕迹", True,
                detail="已排除 %d 条合法固定措辞后无命中" % len(SAFE_PHRASES))

    # —— 身份信息：PDF 元数据（原来是人工项「文件属性是否已清空」）——
    meta = reader.metadata or {}
    dirty = []
    for key in ("/Author", "/Title", "/Subject", "/Keywords"):
        val = str(meta.get(key) or "").strip()
        if not val:
            continue
        if IDENTITY.search(val):
            dirty.append("%s=%r（含身份关键词）" % (key, val))
        elif key == "/Author":
            dirty.append("%s=%r" % (key, val))
    rep.add("identity_meta", "PDF 元数据无身份信息", not dirty,
            note="；".join(dirty) + "。在编译前清空 \\author{}，"
                 "或用 pypdf 重写元数据后重新导出",
            detail="已检查 /Author /Title /Subject /Keywords")

    # —— 编译残留 ——
    unresolved = len(re.findall(r"\?\?", all_text))
    rep.add("no_unresolved_ref", "无未解析的交叉引用", unresolved == 0,
            note="全文出现 %d 处 `??`，xelatex 需要再编译一遍" % unresolved,
            level="WARN")

    # —— 支撑材料 ——
    if support:
        if not os.path.exists(support):
            rep.add("support_exists", "支撑材料存在", False, "找不到 %s" % support)
        else:
            s_mb = os.path.getsize(support) / 1024 / 1024
            rep.add("support_size", "支撑材料 ≤20 MB", s_mb <= 20,
                    detail="%.2f MB" % s_mb)
            names = _zip_names(support)
            if names is None:
                rep.add("support_content", "支撑材料内容", None,
                        "不是 zip（RAR 无法用标准库读），请手工确认："
                        "含可运行源程序" + ("、含 %s" % AI_DETAIL_NAME if used else ""))
            else:
                base = [os.path.basename(x) for x in names]
                has_code = any(x.lower().endswith(CODE_SUFFIXES) for x in base)
                rep.add("support_code", "支撑材料含源程序", has_code,
                        note="未见 %s 等代码文件；规范第五条缺程序可能取消评奖资格"
                             % "/".join(CODE_SUFFIXES[:5]),
                        detail="压缩包 %d 个条目" % len(names))
                if used:
                    rep.add("support_ai_detail",
                            "用了 AI → 压缩包含 %s" % AI_DETAIL_NAME,
                            AI_DETAIL_NAME in base,
                            "文件名必须完全一致（含中文、无空格、扩展名 .pdf）；"
                            "压缩包内现有：%s" % (base[:12]))
                leaked = [x for x in base
                          if any(h in x.lower() for h in SECRET_HINTS)]
                rep.add("support_no_secret", "支撑材料无凭据文件", not leaked,
                        "命中 %s，确认是否为个人密钥/令牌" % leaked, level="WARN")
    else:
        rep.add("support_given", "支撑材料", None,
                "未传 --support，压缩包相关项全部未检查")

    return {"pages": n_pages, "size_mb": round(size_mb, 2),
            "ai_used": used, "ai_none": none}


def stage9_fields(rep: Report) -> dict:
    """映射到 decision_log.stages.9.compliance_checks，避免手填。

    有贡献项落在『人工』上时返回 None(JSON null) 而不是 false——
    「没测到」和「测了没过」是两回事，把前者写成 false 会让人去修一个不存在的问题，
    写成 true 则更糟。null 会在 Stage 9 的 exit condition 上卡住，逼人真去确认。
    """
    def ok(*ids: str) -> bool | None:
        levels = [i["level"] for i in rep.items if i["id"] in ids]
        if any(l == "MANUAL" for l in levels):
            return None
        return all(l == "PASS" for l in levels)

    return {
        "rules_verified": rep.count("FAIL") == 0,
        "anonymity_passed": ok("identity_text", "identity_meta"),
        "page_limit_passed": ok("body_pages", "size", "abstract_one_page"),
        "ai_disclosure_passed": ok("ai_decl", "ai_verbatim", "ai_before_ref"),
    }


def main(argv: list[str] | None = None) -> int:
    _console.init()
    ap = argparse.ArgumentParser(
        description="CUMCM 2026 提交前合规自查（机器可判定项）")
    ap.add_argument("--paper", required=True, help="最终 PDF")
    ap.add_argument("--support", help="支撑材料 .zip（.rar 只能查大小）")
    ap.add_argument("--competition", default="cumcm")
    ap.add_argument("--json", action="store_true", help="输出 JSON")
    args = ap.parse_args(argv)

    if args.competition.lower() != "cumcm":
        print("本脚本只编码 CUMCM 2026 规则，不检查 %s；"
              "请回 competitions/<comp>/current_rules.md 人工核对。"
              % args.competition, file=sys.stderr)
        return 2
    if not os.path.exists(args.paper):
        print("找不到 %s" % args.paper, file=sys.stderr)
        return 2
    try:
        import pypdf  # noqa: F401
    except ImportError:
        print("需要 pypdf：pip install pypdf", file=sys.stderr)
        return 2

    rep = Report()
    info = check_paper(args.paper, args.support, rep)
    fields = stage9_fields(rep)

    if args.json:
        print(json.dumps({"paper": args.paper, **info,
                          "checks": rep.items,
                          "compliance_checks": fields,
                          "manual": list(MANUAL_ITEMS),
                          "fails": rep.count("FAIL"),
                          "warns": rep.count("WARN")},
                         ensure_ascii=False, indent=2))
        return 1 if rep.count("FAIL") else 0

    print(_console.sym("=== %s 合规自查（CUMCM 2026）===\n"
                       % os.path.basename(args.paper)))
    for item in rep.items:
        tag = {"PASS": "✓ PASS", "FAIL": "✗ FAIL",
               "WARN": "⚠ WARN", "MANUAL": "  人工"}[item["level"]]
        line = "  %s  %s" % (tag, item["name"])
        if item["detail"]:
            line += "  (%s)" % item["detail"]
        if item["note"] and item["level"] != "PASS":
            line += "\n          " + item["note"]
        print(_console.sym(line))

    n_auto = sum(1 for i in rep.items if i["level"] != "MANUAL")
    print("\n机器可判定 %d 项：%d PASS，%d FAIL，%d WARN"
          % (n_auto, rep.count("PASS"), rep.count("FAIL"), rep.count("WARN")))
    print("\nStage 9 compliance_checks（可直接写入 decision_log）：")
    print("  " + json.dumps(fields, ensure_ascii=False))
    print("\n以下仍需人工确认：")
    for m in MANUAL_ITEMS:
        print("  [ ] " + m)
    if rep.count("FAIL"):
        print(_console.sym("\n★ 有 FAIL 项，不要提交。"))
    return 1 if rep.count("FAIL") else 0


if __name__ == "__main__":
    sys.exit(main())
