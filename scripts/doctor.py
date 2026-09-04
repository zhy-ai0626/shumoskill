#!/usr/bin/env python3
"""Preflight checks for the mathmodel-skill package and local toolchain."""

from __future__ import annotations

import argparse
import importlib.util
import json
import re
import shutil
import subprocess
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

# tests/ 用 spec_from_file_location 按路径加载本文件，那种方式不会把 scripts/
# 放到 sys.path 上，同目录的 helper 就 import 不到。显式补一下。
sys.path.insert(0, str(Path(__file__).resolve().parent))
import _console  # noqa: E402
import _toolpath  # noqa: E402


SKILL_ROOT = Path(__file__).resolve().parent.parent
COMPETITIONS = ("cumcm",)  # 本 fork 只做 CUMCM ABC 题；MCM/电工杯已移除
COMPETITION_FILES = (
    "README.md",
    "winning_patterns.md",
    "phrase_bank.md",
    "anti_patterns.md",
    "abstract_template.md",
    "paper_skeleton.md",
    "rubric_overlay.json",
    "topic_specs.json",
    "empirical.json",
    "current_rules.md",
)
RENDER_ENGINES = {"cumcm": "xelatex"}
REQUIRED_TEX_FILES = {
    "cumcm": ("ctexart.cls",),
}
MODELING_MODULES = ("numpy", "scipy", "pandas", "matplotlib", "sklearn")
# 合规链路的依赖：render_ai_usage.py 用 reportlab 生成《AI工具使用详情.pdf》。
# 那个文件名是 2026 规定写死的强制支撑材料，缺了它等于交不齐材料——
# 所以这一项必须进 Stage 0 预检，而不是等到 Stage 9 才发现。
COMPLIANCE_MODULES = ("reportlab",)
CORE_SECTION_MARKERS = {
    "abstract",
    "1_problem_restate",
    "2_problem_analysis",
    "3_assumptions",
    "4_notation",
    "5_models",
    "6_sensitivity",
    "7_evaluation",
    "8_references",
    "appendix_code",
}
# 两个 AI 声明 marker 都必须在模板里（2026 规定二选一必须出现在论文里，
# 参考文献之前）。渲染时按台账只保留其中一个，另一个整块删掉。
EXPECTED_RENDER_MARKERS = {
    "cumcm": CORE_SECTION_MARKERS | {"cumcm_no_ai_statement", "cumcm_ai_statement"},
}


@dataclass(frozen=True)
class Check:
    name: str
    status: str
    detail: str
    fix: str | None = None


def _check(name: str, ok: bool, detail: str, fix: str | None = None) -> Check:
    return Check(name=name, status="pass" if ok else "fail", detail=detail, fix=fix)


def _optional(name: str, ok: bool, detail: str, fix: str | None = None) -> Check:
    return Check(name=name, status="pass" if ok else "warn", detail=detail, fix=fix)


def _load_json(path: Path) -> tuple[bool, object | str]:
    try:
        return True, json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return False, str(exc)


def _frontmatter_name(path: Path) -> str | None:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return None
    match = re.search(r"\A---\s*\n.*?^name:\s*[\"']?([^\n\"']+)", text, re.DOTALL | re.MULTILINE)
    return match.group(1).strip() if match else None


def _anti_pattern_count(path: Path) -> int:
    text = path.read_text(encoding="utf-8")
    return len(re.findall(r"^###\s+[A-Z]\d+\.\s", text, re.MULTILINE))


def _tex_file_available(filename: str) -> bool:
    """Ask the active TeX distribution whether a required class/package exists."""
    kpsewhich = shutil.which("kpsewhich")
    if not kpsewhich:
        return False
    try:
        result = subprocess.run(
            [kpsewhich, filename], capture_output=True, text=True, check=False
        )
    except OSError:
        return False
    return result.returncode == 0 and bool(result.stdout.strip())


def _template_packages(competition: str) -> list[str]:
    """模板里实际 \\usepackage 的宏包名。

    只查 ctexart.cls 是不够的：2026-09-03 实测，本机 TeX Live 是 scheme-small，
    `siunitx` 不存在，而它一旦被引用就是 `! Emergency stop`、连残缺 PDF 都不出。
    latex-smoke 会真编译模板、能兜住这种情况；但把清单逐个报出来，
    才能让人在 Stage 0 就知道"哪些能用、哪些别碰"。
    """
    template = SKILL_ROOT / "templates" / "latex" / competition / "main.tex"
    if not template.is_file():
        return []
    text = template.read_text(encoding="utf-8")
    names: list[str] = []
    for group in re.findall(r"^\s*\\usepackage(?:\[[^\]]*\])?\{([^}]+)\}",
                            text, re.MULTILINE):
        for name in group.split(","):
            name = name.strip()
            if name and name not in names:
                names.append(name)
    return names


SMOKE_TEX = {"cumcm": SKILL_ROOT / "templates" / "latex" / "cumcm" / "smoke.tex"}
SMOKE_TIMEOUT_S = 120


def _render_smoke(competition: str) -> tuple[bool, str]:
    """真的编译一次 smoke.tex，而不是只问 `xelatex --version`。

    `shutil.which(engine)` 与 `kpsewhich ctexart.cls` 都只能证明"装了"，
    证明不了"能出 PDF"——中文字体缺失、xeCJK 配置、宏包版本冲突都只在真编译时才暴露。
    72 小时赛制里这类问题必须在 Stage 0 暴露，拖到 Stage 9 就来不及了。

    返回 (是否成功, 面向人的说明)。
    """
    engine = RENDER_ENGINES.get(competition)
    tex = SMOKE_TEX.get(competition)
    if engine is None or tex is None:
        return False, f"no smoke template configured for {competition}"
    if not tex.exists():
        return False, f"smoke template missing: {tex}"
    if shutil.which(engine) is None:
        return False, f"{engine} not found; cannot compile"

    import tempfile

    with tempfile.TemporaryDirectory(prefix="mathmodel-smoke-") as tmp:
        workdir = Path(tmp)
        target = workdir / "smoke.tex"
        target.write_text(tex.read_text(encoding="utf-8"), encoding="utf-8")
        try:
            proc = subprocess.run(
                [engine, "-interaction=nonstopmode", "-halt-on-error", "smoke.tex"],
                cwd=workdir, capture_output=True, text=True,
                check=False, timeout=SMOKE_TIMEOUT_S,
            )
        except subprocess.TimeoutExpired:
            return False, f"{engine} timed out after {SMOKE_TIMEOUT_S}s"
        except OSError as exc:
            return False, f"{engine} failed to start: {exc}"

        pdf = workdir / "smoke.pdf"
        if pdf.exists() and pdf.stat().st_size > 1024:
            return True, f"{engine} produced a {pdf.stat().st_size // 1024} KiB PDF"

        # 从 .log 里挑出第一条真正的 TeX 报错，比甩几百行 stdout 有用
        log = workdir / "smoke.log"
        reason = ""
        if log.exists():
            for line in log.read_text(encoding="utf-8", errors="replace").splitlines():
                if line.startswith("!"):
                    reason = line.strip()
                    break
        if not reason:
            tail = (proc.stdout or proc.stderr or "").strip().splitlines()
            reason = tail[-1].strip() if tail else f"exit code {proc.returncode}"
        return False, f"compile failed: {reason}"


def run_checks(
    competition: str,
    workspace: Path | None = None,
    check_tools: bool = True,
    require_renderer: bool = False,
    require_modeling: bool = False,
) -> list[Check]:
    checks: list[Check] = []

    py_ok = sys.version_info >= (3, 10)
    checks.append(_check(
        "python",
        py_ok,
        f"Python {sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
        "Install Python 3.10 or newer." if not py_ok else None,
    ))

    required_paths = (
        "SKILL.md",
        "AGENTS.md",
        "config/dim_weights.json",
        "templates/shared/decision_log.json",
        "scripts/score_artifact.py",
        "scripts/extract_diff.py",
        "scripts/render_paper.py",
        "scripts/render_ai_usage.py",
        "templates/shared/ai_usage_ledger.json",
        "templates/latex/cumcm/main.tex",
    )
    missing = [item for item in required_paths if not (SKILL_ROOT / item).is_file()]
    checks.append(_check(
        "package-structure",
        not missing,
        "all core entrypoints present" if not missing else f"missing: {', '.join(missing)}",
    ))

    skill_name = _frontmatter_name(SKILL_ROOT / "SKILL.md")
    shim_name = skill_name  # 本 fork 无 Codex plugin shim
    checks.append(_check(
        "skill-metadata",
        skill_name == "cumcm-abc" and shim_name == skill_name,  # 本 fork 改名为 cumcm-abc
        f"root={skill_name!r}, plugin-shim={shim_name!r}",
    ))

    json_paths = [
        SKILL_ROOT / "config" / "dim_weights.json",
        SKILL_ROOT / "templates" / "shared" / "decision_log.json",
        SKILL_ROOT / "templates" / "shared" / "ai_usage_ledger.json",
    ]
    for comp in COMPETITIONS:
        json_paths.extend((
            SKILL_ROOT / "competitions" / comp / "rubric_overlay.json",
            SKILL_ROOT / "competitions" / comp / "topic_specs.json",
            SKILL_ROOT / "competitions" / comp / "empirical.json",
        ))
    invalid_json = []
    parsed: dict[Path, object] = {}
    for path in json_paths:
        ok, value = _load_json(path)
        if ok:
            parsed[path] = value
        else:
            invalid_json.append(f"{path.relative_to(SKILL_ROOT)}: {value}")
    checks.append(_check(
        "json-config",
        not invalid_json,
        f"{len(json_paths)} files parsed" if not invalid_json else "; ".join(invalid_json),
    ))

    decision_path = SKILL_ROOT / "templates" / "shared" / "decision_log.json"
    decision = parsed.get(decision_path, {})
    decision_schema_ok = (
        isinstance(decision, dict)
        and decision.get("_schema_version") == "3.1"
        and isinstance(decision.get("stages"), dict)
        and isinstance(decision.get("scores"), dict)
        and isinstance(decision.get("iterations"), dict)
        and isinstance(decision.get("compliance"), dict)
        and isinstance(decision.get("compliance", {}).get("ruleset"), dict)
        and "ai_usage" in decision.get("compliance", {})
    )
    checks.append(_check(
        "decision-log-schema",
        decision_schema_ok,
        "decision_log schema 3.1 with compliance state"
        if decision_schema_ok else "decision_log template is not a complete v3.1 state",
        "Restore the v3.1 decision-log template before using the workflow."
        if not decision_schema_ok else None,
    ))

    comp_dir = SKILL_ROOT / "competitions" / competition
    missing_comp = [name for name in COMPETITION_FILES if not (comp_dir / name).is_file()]
    checks.append(_check(
        "competition-pack",
        not missing_comp,
        f"{competition}: {len(COMPETITION_FILES)} required files"
        if not missing_comp else f"{competition} missing: {', '.join(missing_comp)}",
    ))

    anti_path = comp_dir / "anti_patterns.md"
    if anti_path.is_file():
        anti_count = _anti_pattern_count(anti_path)
        checks.append(_check(
            "anti-pattern-index",
            anti_count > 0,
            f"{competition}: {anti_count} indexed checks",
        ))
        declared = (
            decision.get("stages", {}).get("9", {})
            .get("anti_patterns_check", {}).get("total")
            if isinstance(decision, dict) else None
        )
        checks.append(_check(
            "anti-pattern-state-init",
            declared is None,
            f"template defers total; {competition} source currently has {anti_count}",
            "Keep the shared template total null; Stage 9 initializes it from the active competition pack."
            if declared is not None else None,
        ))

    if competition in EXPECTED_RENDER_MARKERS:
        template = SKILL_ROOT / "templates" / "latex" / competition / "main.tex"
        markers = re.findall(
            r"^\s*%\s*MATHMODEL:SECTION\s+([A-Za-z0-9_]+)\s*$",
            template.read_text(encoding="utf-8"),
            re.MULTILINE,
        ) if template.is_file() else []
        expected = EXPECTED_RENDER_MARKERS[competition]
        actual = set(markers)
        duplicates = sorted({marker for marker in markers if markers.count(marker) > 1})
        missing_markers = sorted(expected - actual)
        unexpected_markers = sorted(actual - expected)
        markers_ok = (
            not duplicates
            and not missing_markers
            and not unexpected_markers
            and len(markers) == len(expected)
        )
        if markers_ok:
            marker_detail = f"{competition}: {len(markers)}/{len(expected)} section markers"
        else:
            marker_detail = (
                f"{competition}: missing={missing_markers}, "
                f"unexpected={unexpected_markers}, duplicates={duplicates}"
            )
        checks.append(_check(
            "render-markers",
            markers_ok,
            marker_detail,
            "Restore the exact unique MATHMODEL section-marker set."
            if not markers_ok else None,
        ))

    if workspace:
        decision_path = workspace / "state" / "decision_log.json"
        if decision_path.is_file():
            ok, value = _load_json(decision_path)
            compliance = value.get("compliance") if isinstance(value, dict) else None
            valid = (
                ok and isinstance(value, dict)
                and value.get("_schema_version") == "3.1"
                and value.get("competition") == competition
                and isinstance(value.get("current_stage"), int)
                and not isinstance(value.get("current_stage"), bool)
                and 0 <= value["current_stage"] <= 9
                and isinstance(value.get("stages"), dict)
                and isinstance(value.get("scores"), dict)
                and isinstance(value.get("iterations"), dict)
                and isinstance(compliance, dict)
                and isinstance(compliance.get("ruleset"), dict)
                and "ai_usage" in compliance
            )
            checks.append(_check(
                "workspace-state",
                valid,
                str(decision_path) if valid else f"invalid state: {value}",
            ))
        else:
            checks.append(_optional(
                "workspace-state",
                False,
                f"not initialized: {decision_path}",
                "Start the skill once; the agent will initialize state automatically.",
            ))

    if check_tools:
        engine = RENDER_ENGINES[competition]
        # 「装了但当前终端看不见」是最常见的情形：安装器写了注册表 PATH，
        # 而已经开着的 shell 拿的是安装之前的环境快照。先三级查找并补进本进程 PATH，
        # 再判定"有没有装"，否则会把一个重开终端就好的问题误报成致命环境缺失。
        engine_found = _toolpath.ensure_on_path(engine)
        engine_ok = shutil.which(engine) is not None
        engine_check = _check if require_renderer else _optional
        checks.append(engine_check(
            "latex-engine",
            engine_ok,
            f"{engine} found at {engine_found.directory} ({engine_found.source})"
            if engine_ok and engine_found.recovered
            else f"{engine} {'found' if engine_ok else 'not found'}",
            f"Install a TeX distribution that provides {engine}." if not engine_ok
            else _toolpath.advice(engine, engine_found),
        ))
        # 进程内补 PATH 只解决"本次能不能编"，不解决"下一个终端能不能编"。
        # 单独留一条 warn，免得这件事被 latex-engine 那个 ✓ 盖过去。
        if engine_ok and engine_found.recovered:
            checks.append(_optional(
                "latex-engine-on-path",
                False,
                f"{engine} 不在本终端的 PATH 上（命中来源：{engine_found.source}）；"
                "doctor 进程内补的路径不会传给这个终端里手敲的命令",
                _toolpath.advice(engine, engine_found),
            ))
        required_tex_files = REQUIRED_TEX_FILES[competition]
        if required_tex_files:
            missing_tex_files = [
                filename for filename in required_tex_files
                if not _tex_file_available(filename)
            ]
            checks.append(engine_check(
                "latex-support",
                not missing_tex_files,
                "required TeX classes/packages found" if not missing_tex_files
                else f"missing TeX support: {', '.join(missing_tex_files)}",
                "Install the TeX distribution's Chinese-language/ctex package set."
                if missing_tex_files else None,
            ))
        # 模板里逐个 \usepackage 的宏包也要在本机存在，否则 Stage 8 才会炸
        packages = _template_packages(competition)
        if packages and engine_ok:
            missing_pkgs = [
                name for name in packages
                if not _tex_file_available(f"{name}.sty")
            ]
            checks.append(engine_check(
                "latex-template-packages",
                not missing_pkgs,
                f"{len(packages)} 个模板宏包全部可用" if not missing_pkgs
                else f"模板引用但本机缺失: {', '.join(missing_pkgs)}",
                "缺失的宏包一旦被引用就是 `! Emergency stop`、连残缺 PDF 都不出。"
                "要么用 tlmgr 装上，要么从模板里删掉并改写对应记号"
                "（详见 competitions/cumcm/静默陷阱.md §3.5.2c）。"
                if missing_pkgs else None,
            ))
        # 真编译一次。这是唯一能证明"最后交得出 PDF"的检查。
        smoke_ok, smoke_detail = _render_smoke(competition)
        checks.append(engine_check(
            "latex-smoke",
            smoke_ok,
            smoke_detail,
            "编译链跑不通就交不出论文，且这是 Stage 0 的 block，不允许推迟到 Stage 9。修复顺序："
            "① 装 TeX 发行版（Windows: MiKTeX 或 TeX Live；Linux: texlive-full）；"
            "② 装中文支持宏包集 ctex（MiKTeX 会按需自动装，TeX Live 需 texlive-lang-chinese）；"
            "③ 装中文字体（Windows 自带宋体/黑体；Linux 装 fonts-fandol 或思源宋体）；"
            f"④ 手动复现看完整报错：xelatex -interaction=nonstopmode {SMOKE_TEX[competition]}；"
            "⑤ 实在装不上，改用 scripts/render_paper.py 的 Pandoc 路径出 docx，"
            "但正文公式与排版会降级，必须提前告知队伍。"
            if not smoke_ok else None,
        ))

        pandoc_found = _toolpath.ensure_on_path("pandoc")
        pandoc_ok = shutil.which("pandoc") is not None
        pandoc_check = _check if require_renderer else _optional
        checks.append(pandoc_check(
            "pandoc",
            pandoc_ok,
            f"pandoc found at {pandoc_found.directory} ({pandoc_found.source})"
            if pandoc_ok and pandoc_found.recovered
            else "pandoc found" if pandoc_ok else (
                "pandoc not found; formal compilation is unavailable "
                "(structural --no-compile remains available)"
            ),
            "Install Pandoc before formal paper compilation." if not pandoc_ok
            else _toolpath.advice("pandoc", pandoc_found),
        ))

    missing_compliance = [
        name for name in COMPLIANCE_MODULES if importlib.util.find_spec(name) is None
    ]
    checks.append(_check(
        "compliance-stack",
        not missing_compliance,
        "AI 披露链路依赖就绪" if not missing_compliance
        else f"缺少 {', '.join(missing_compliance)}，无法生成《AI工具使用详情.pdf》",
        "python -m pip install " + " ".join(missing_compliance)
        if missing_compliance else None,
    ))

    if require_modeling:
        missing_modules = [name for name in MODELING_MODULES if importlib.util.find_spec(name) is None]
        checks.append(_check(
            "modeling-stack",
            not missing_modules,
            "core modeling modules found" if not missing_modules else f"missing: {', '.join(missing_modules)}",
            "Install templates/shared/requirements.txt." if missing_modules else None,
        ))

    return checks


def _print_human(checks: list[Check]) -> None:
    symbols = {"pass": _console.sym("✓"), "warn": "!", "fail": _console.sym("✗")}
    arrow = _console.sym("↳")
    for item in checks:
        print(f"{symbols[item.status]} {item.name}: {item.detail}")
        if item.fix and item.status != "pass":
            print(f"  {arrow} {item.fix}")
    counts = {status: sum(item.status == status for item in checks) for status in symbols}
    print(
        f"\nSummary: {counts['pass']} passed, "
        f"{counts['warn']} optional warnings, {counts['fail']} failed"
    )


def main() -> int:
    _console.init()
    parser = argparse.ArgumentParser(description="Check mathmodel-skill readiness.")
    parser.add_argument("--competition", choices=COMPETITIONS, default="cumcm")
    parser.add_argument("--workspace", type=Path, default=None)
    parser.add_argument("--json", action="store_true", dest="as_json")
    parser.add_argument("--skip-tools", action="store_true", help="skip local Pandoc/TeX checks")
    parser.add_argument("--require-renderer", action="store_true")
    parser.add_argument("--require-modeling", action="store_true")
    args = parser.parse_args()

    if args.skip_tools and args.require_renderer:
        parser.error("--require-renderer 不能与 --skip-tools 同时使用")

    checks = run_checks(
        competition=args.competition,
        workspace=args.workspace.resolve() if args.workspace else None,
        check_tools=not args.skip_tools,
        require_renderer=args.require_renderer,
        require_modeling=args.require_modeling,
    )
    if args.as_json:
        print(json.dumps([asdict(item) for item in checks], ensure_ascii=False, indent=2))
    else:
        _print_human(checks)
    return 1 if any(item.status == "fail" for item in checks) else 0


if __name__ == "__main__":
    raise SystemExit(main())
