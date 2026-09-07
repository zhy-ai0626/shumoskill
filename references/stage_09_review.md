---
stage: 9
name: review
duration_h: 2-6
inputs: ["paper.tex", "paper.pdf", "decision_log_full", "decision_log.competition"]
outputs:
  - "stage.9.{anti_patterns_check, compliance_checks, panel_scores, weakest_section, redo_log, red_team_record, final_pdf_path, submission_ready}"
loads_reference:
  - "competitions/<comp>/current_rules.md"
  - "competitions/<comp>/anti_patterns.md"
  - "competitions/<comp>/rubric_overlay.json"
  - "references/feedback_layer3_panel.md"
loads_template: ["templates/latex/<comp>/"]
feedback: ["L1", "L3_panel", "red_team_in_championship"]
next: SUBMIT
---

# Stage 9 — Submission review

The final gate is compliance first, content consistency second, presentation third. A polished paper that violates the current rules is not submission-ready.

## 1. Re-open the official rules

Read `competitions/<comp>/current_rules.md`, open its official links, and compare the final artifacts against the current contest year. Record the check in `decision_log.stages.9.compliance_checks`.

Minimum branches:

### CUMCM

**先跑脚本，再人工核**——下面这条命令覆盖清单里所有机器能判定的项，
不要用肉眼替代它（`--support` 传了才会检查压缩包内容）：

```bash
python <skill>/scripts/check_compliance.py --paper paper_output/paper.pdf \
    --support support_materials/支撑材料.zip
```

退出码非零就是有 FAIL，**不得进入提交**。它的 `--json` 输出里
`compliance_checks` 一段可直接写进 `decision_log.stages.9.compliance_checks`；
其中 `null` 表示"这项没测到"（例如没传 `--support`），
必须人工确认后改成布尔值才算通过 exit condition，不能当 `false` 也不能当 `true`。

脚本查不到而只能人工看的，它会在末尾列出来。以下条款仍需逐条对照官方原文：

- electronic paper starts with the abstract page;
- no commitment form, numbering page, table of contents, or identity information;
- main text and file size meet the current limits;
- appendix lists the supporting-material files;
- support ZIP/RAR contains runnable code and required evidence, is within the size limit, and excludes secrets;
- AI-assisted content is marked and cited;
- if AI was used, support materials contain `AI工具使用详情.pdf`; otherwise the required no-AI declaration is present.

### MCM/ICM

- Summary Sheet is page 1;
- main solution, including references, appendices, code, TOC, and required letter/memo, is at most 25 pages;
- readable font is at least 12pt;
- each solution page has the control number and page number, with no personal or institutional identity;
- AI tools are cited in the main solution;
- `Report on Use of AI` follows the main solution and is not counted inside the 25-page solution.

### Diangong

- page 1 is the anonymous cover with registration number and the official problem title; page 2 contains title, abstract and keywords and begins Arabic page numbering at 1;
- the body begins on page 3, contains no table of contents and stays within the current 25-page body limit; appendices follow the body;
- A4 margins are 2.5 cm and Chinese body text uses 小四; no team-member or school identity appears anywhere;
- the paper is a single uncompressed PDF or Word file, while support materials are ZIP/RAR no larger than 20 MB and contain the runnable code and necessary evidence;
- citations appear in the text and references follow citation order;
- the currently checked official pages do not define a dedicated AI-disclosure format, so recheck the annual notice and preserve the ledger rather than inventing one.

Any unresolved rule violation sets `submission_ready=false` and yields `block`.

## 2. Run the active anti-pattern checklist

Read `competitions/<comp>/anti_patterns.md` and derive the count from the active file rather than copying a remembered or example count.

These are maintainer heuristics, not official scoring weights. Fix high-severity hits; record accepted medium-risk items with an explicit rationale.

## 3. Verify the evidence chain

Cross-check the final paper against `decision_log.json` and the saved artifacts:

- no abandoned model remains in the abstract or conclusion;
- no symbol changes meaning between sections;
- all headline values reproduce from stored results — **run the checker, do not eyeball it**:

  ```bash
  python <skill>/scripts/check_numbers.py --paper paper.tex --results results/
  ```

  它把论文里每个数值和 `results/` 下 `.json`/`.csv` 的值按有效数字与相对容差比对，
  报出"论文里有、结果文件里找不到"的数字。论文里的数字多半是从终端手抄进 LaTeX 的，
  抄错一位不会报错，评委却能核出来。退出码非零就说明有未追溯的值。
  若某些值只写在 `results/` 下的 `.txt` 报告里，可加 `--include-text` 放宽，
  但更好的做法是把它们写进 `.json`/`.csv`——评委核的是可机读的结果文件；

- 自检承诺与局限全部了结——**Stage 6 跑过也要在这里再跑一次**，
  因为 Stage 8 改写论文时既可能新增承诺句，也可能改动措辞让台账引用失配：

  ```bash
  python <skill>/scripts/check_selfaudit.py --ledger state/self_audit.json \
      --paper paper.tex --workspace paper_workspace/ --results results/
  ```

- every figure/table path resolves and its caption matches the content
  —— **路径与交叉引用别用眼看，跑脚本**：

  ```bash
  python <skill>/scripts/check_figures.py --paper paper.tex \
      --figures figures/ --topic <A|B|C>
  ```

  FAIL 两类，都是评委看得见的：`\includegraphics` 指向的文件不存在
  （**LaTeX 缺图不一定报错**，有的引擎只在图位置留一个方框，PDF 照样出）、
  `\ref` 没有对应 `\label`（PDF 里印成 `??`）、`\label` 重复定义
  （编号看着对，指向是错的）。
  WARN 三类：图/表数量低于一等奖 p25、`figures/` 里有图没被引用、
  有 label 但正文从未引用它。**数量类 WARN 是经验分布不是规则**——
  图少不违规，但要回头确认每个子问都有"表 + 图 + 方法 + 分析段 + 结果文件"；
- every external claim has a verified source;
- AI-generated citations have been opened and checked manually.

## 4. Review presentation

- labels, units, legends, equations, and captions remain readable at final PDF size;
- fonts and colors are consistent and accessible;
- tables use consistent units and precision;
- there are no unresolved `??` references, missing glyphs, clipped figures, or large overfull boxes;
- all required sections are present in the compiled PDF, not merely on disk as detached `.tex` files.

## 5. Run the five-view panel

Use `references/feedback_layer3_panel.md` as the single source for panel roles and aggregation. Prefer independent parallel views when the harness supports them; otherwise run the views separately to reduce cross-contamination.

Map every high-severity concern back to one source section and apply a targeted patch. Re-run only the affected checks and panel views. Do not ask the panel to predict an award; use `ready`, `refine`, or `block` against the repository rubric.

## 6. Generate AI disclosure artifacts

For CUMCM or MCM, run from the user project root:

```bash
python <skill>/scripts/render_ai_usage.py \
  --competition <competition> \
  --decision-log state/decision_log.json \
  --paper-workspace paper_workspace/ \
  --support-dir support_materials/
```

For CUMCM with AI use, verify `support_materials/AI工具使用详情.pdf` is in the supporting archive and that inline marks and AI-tool references are present. For an explicit empty CUMCM ledger, the helper instead creates `paper_workspace/AI工具未使用声明.md`; rerender and verify that the declaration appears immediately **before** the references (2026 规则要求 AI 声明置于参考文献之前), with no details PDF. For MCM, verify `paper_workspace/11_ai_use_report.md` is rendered once, after the 25-page main solution. The helper intentionally does not invent a Diangong disclosure format; for Diangong, compare the ledger with the current official notice and record that manual check.

## 7. Compile and inspect the final PDF

Use `<skill>/scripts/render_paper.py` or the selected LaTeX engine. Compilation succeeds only when the PDF exists, includes all intended sections, and has no unresolved high-severity warnings. Visually inspect the first page, dense equations, wide tables, figure-heavy pages, references, appendices, and the AI report.

## 8. Persist the final gate

Write actual runtime-derived counts and paths. The schema is:

```json
{
  "anti_patterns_check": {
    "total": null,
    "passed": null,
    "fixed": null,
    "deferred": null
  },
  "compliance_checks": {
    "rules_verified": null,
    "anonymity_passed": null,
    "page_limit_passed": null,
    "ai_disclosure_passed": null
  },
  "final_pdf_path": "paper_output/paper.pdf",
  "submission_ready": null
}
```

The `null` values above are schema placeholders only. Replace every one with an observed count or verified boolean before persisting Stage 9; never copy a sample result into the final gate.

## L1 Rubric（阶段级 5 维）

Stage 9 有两层反馈：这张是 **L1 阶段级**打分（`feedback: ["L1", ...]`），
L3 五视角 panel 另见 `references/feedback_layer3_panel.md` 与 `rubrics.md §Stage 9`。
**别把两层混起来**——L1 的键在 `config/rubric.json` 里，panel 走另一套。

<!-- RUBRIC:BEGIN 9 -->
| 维度 | 满分行为 |
|------|---------|
| 1. 反模式覆盖 (`1_anti_pattern_coverage`) | `anti_patterns.md` 的全部索引项都过了一遍（`doctor.py` 报的 66 条），命中的每一条**要么已修，要么在论文里写明为什么不适用**；不允许"看过了"但无结论 |
| 2. 图表定稿质量 (`2_visual_polish`) | 逐张过 `figures/README.md` 的硬规矩：轴标签带单位、无双纵轴、≥2 系列有图例、只标结论点、顺序色非彩虹；灰度校样已翻过一遍 |
| 3. Panel 共识 (`3_panel_consensus`) | L3 五视角无 high-severity 未决项；verdict 不靠权重覆盖异议（任一 high-severity 保持 `block`） |
| 4. 瓶颈已处理 (`4_bottleneck_addressed`) | 最低分维度与高影响 issue 已**定向修补并让受影响视角复核**，不是记录在案就算完 |
| 5. 提交件可编可查 (`5_pdf_compile_clean`) | `check_compliance.py` 无 FAIL：PDF 能编、中文可从 PDF 提取、页数/大小/摘要单页合规、AI 声明三项齐、附录含源程序、正文与 PDF 元数据无身份信息 |
<!-- RUBRIC:END 9 -->

第 5 维由 `check_compliance.py` 判定，不接受人工"应该没问题"。

## Exit conditions

- `scripts/check_compliance.py` 退出码为 0，且 `compliance_checks` 四个字段
  全部是 `true`（没有 `null` 残留）；
- `scripts/check_numbers.py`、`scripts/check_selfaudit.py` 与
  `scripts/check_figures.py` 退出码均为 0（后者的 WARN 不影响退出码，
  但**数量类 WARN 要逐条读完再决定**，别当噪声划过去）；
- current official rules verified with no unresolved violation;
- anti-pattern and consistency checks completed;
- all high-severity panel findings resolved;
- PDF compiled and visually inspected;
- AI disclosure and supporting materials complete when required;
- `decision_log.stages.9.submission_ready == true`.

Only then hand the final submission package back to the team.
