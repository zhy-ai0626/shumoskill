---
stage: 8
name: writing
duration_h: 12-30
inputs: ["decision_log.stages.0-7", "decision_log.competition", "decision_log.task_type"]
outputs:
  - "stage.8.{section_word_counts, figures_per_subproblem, tables_per_subproblem, abstract_drafts, ai_use_log, compliance}"
  - "paper_workspace/*.md"
  - "paper.tex"
loads_reference:
  - "competitions/<competition>/current_rules.md"
  - "competitions/<competition>/winning_patterns.md"
  - "competitions/<competition>/phrase_bank.md"
  - "competitions/<competition>/empirical.json"
  - "competitions/cumcm/静默陷阱.md"
loads_template:
  - "competitions/<competition>/paper_skeleton.md"
  - "competitions/<competition>/abstract_template.md"
  - "templates/latex/<competition>/"
feedback: ["L1", "L2_at_end"]
next: stage_09_review
---

# Stage 8 — Assemble the paper

Turn the validated Stage 0–7 outputs into one coherent paper. Do not invent new results while writing. If the paper exposes a modeling contradiction, record it and trigger a targeted L2 backtrack.

## 1. Lock the current rules first

1. Read `competitions/<competition>/current_rules.md` when present.
2. Open the linked official rules and confirm they are still current for the contest year.
3. Record the verification date, source URL, page/font/file-size limits, anonymity rules, and AI-disclosure requirements in `decision_log.compliance.ruleset`.
4. If the repository baseline conflicts with the official source, follow the official source and flag the repository mismatch.

Do not treat empirical distributions, `winning_patterns.md`, or rubric scores as official rules. They are writing aids only.

## 2. Load only the active competition pack

Read from `competitions/<competition>/`:

- `paper_skeleton.md`
- `abstract_template.md`
- `winning_patterns.md`
- `phrase_bank.md`
- `empirical.json`

For CUMCM, 91 source documents were collected but only 59 text-extractable documents entered the aggregate statistics; the values are observational baselines, not award thresholds.

## 3. Write into a stable workspace contract

Create these files under `<cwd>/paper_workspace/`:

| File | Content |
|---|---|
| `01_abstract.md` | Abstract or Summary Sheet, written last |
| `02_problem_restate.md` | Problem context and restatement |
| `03_analysis.md` | Decomposition and technical route |
| `04_assumptions.md` | Supported assumptions |
| `05_notation.md` | Unique symbols and units |
| `06_models.md` | Models, algorithms, results, and interpretation |
| `07_sensitivity.md` | Robustness and failure regions |
| `08_evaluation.md` | Strengths, limitations, and transfer conditions |
| `09_references.md` | Verified references, including AI tools when required |
| `10_appendix.md` | Essential code and supporting-material manifest |

`01_abstract.md` contains abstract/summary content without a top-level heading because the template supplies its wrapper. Files `02`–`10` each own one clear top-level Markdown heading; the template supplies each wrapper.

Write the body first, then references and appendices, and write the abstract/summary last. Every number in the abstract must point to a result already present in the body.

## 4. Keep one evidence chain

For every subproblem, preserve this chain:

`question → assumptions → formulation → solver → result → validation → interpretation`

Before moving on, verify:

- symbols match Stage 4;
- chosen models match Stage 3;
- reported values match stored results rather than regenerated prose;
- figures have readable labels, units, captions, and source paths;
- claims and citations are verifiable;
- limitations name a concrete failure mode and mitigation.

## 5. Apply the competition branch

| Competition | Current repository baseline | Renderer |
|---|---|---|
| CUMCM | 2026 electronic paper: first page abstract, no commitment/numbering page, no TOC or identity; 正文**尽量控制在 20 页以内**（硬上限 30 页，>20 页即须自证必要性）；paper and support archive each ≤20 MB; AI disclosure and `AI工具使用详情.pdf` when AI is used | `xelatex` |

Problem-specific deliverables such as letters or memos also count toward the applicable page limit unless the current official problem states otherwise.

## 6. Maintain the AI-use ledger

Because this skill itself uses an AI agent, keep `decision_log.compliance.ai_usage` current. For each material use, record:

- tool, provider, and model/version;
- use date, stage, and purpose;
- key prompt and key response, or paths to those records;
- what was adopted;
- human changes and verification performed.

Use `<skill>/scripts/render_ai_usage.py` in Stage 9 to generate the contest-specific disclosure artifact. Never place API keys, tokens, private data, or credentials in the ledger.

## 7. Render without detached sections

From the user project root, call the installed script explicitly:

```bash
python <skill>/scripts/render_paper.py \
  --competition <competition> \
  --workspace paper_workspace/ \
  --output-dir paper_output/
```

A generated PDF with missing section inputs is a failure even if LaTeX exits successfully.

### 7.1 编译"成功"不等于内容完整——必须核页数和 log

**xelatex 会一边报错一边输出 PDF。** 2025A 端到端演练里，一个小节标题含 `\bm`
触发 hyperref 撑爆输入栈，`xelatex` 退出码非 0、却照样生成了一份 **2 页**的 PDF
（应有 11 页），从那一节起后面全部丢失。只看"PDF 在不在"完全发现不了。

同一形状的坑至少还有一个：**没有标题的 markdown 表格**会让 pandoc 生成
`\def\LTcaptype{none}`，与 `caption` 宏包冲突，10 节的论文只剩 1 页
（模板已修，详见 `competitions/cumcm/静默陷阱.md` §3.5.2b）。
**给每张表都写标题**，既避开这个坑，也是评委要看的东西。

编译后三条硬检查，缺一条不算完成：

```bash
L=paper_output/paper.log
grep -c "^!" $L                                  # 报错条数，必须为 0
grep -o "Output written on .*pages\?)" $L | tail -1   # 实际页数，与预期核对
grep -c "undefined" $L                           # 未解析的引用/标签，必须为 0
```

页数从 **log** 取，不要依赖 `pdfinfo`——TeX Live 的 scheme-small 不带它，
而 PDF 用了对象流压缩，直接在字节流里数 `/Type /Page` 会得到 0。
`Output written on ... (N pages).` 这一行是零依赖且一定有的。

页数与预期不符就去 log 里找**第一条** `!`，从那里往后的内容都可能已经丢了。
常见根因与修法见 `competitions/cumcm/静默陷阱.md` §三点五
（标题里的数学命令要用 `\texorpdfstring`）。

## 8. Score using the active overlay

Use the five Stage 8 dimensions from `competitions/<competition>/rubric_overlay.json` when that competition overrides the baseline.

## Exit conditions

- all required sections and problem-specific deliverables exist;
- the paper agrees with the Stage 0–7 decision log;
- the current official rules were rechecked and recorded;
- AI uses and citations are logged;
- the active competition's renderer includes every section;
- L1 passes and the final L2 consistency check has no unresolved high-severity conflict.

Then enter `stage_09_review.md`.

---

## 9. 图表与结果文件（本节为本地新增：上游此处缺失）

**为什么单列一节**：2022A 讲评「评阅中发现的问题」共 9 条，其中 **5 条与建模无关**，
全是呈现与交付——"计算方法不清楚""计算结果不完整""没有很好地呈现结果"
"**没有对结果进行分析**""**没有结果文件或文件格式不对**"。
同一模式跨年重复：2023B「没有给出测线的具体坐标」、2025A「没有给出具体算法」、
2025C「未能给出合理的落地判定方案」。上游 Stage 8 对"图"只提了 2 次、
对"结果文件/代码"零提及，这是覆盖面缺口。

### 9.1 工作量必须提前排

一等奖论文实测：**图 p50 = 20 张、表 p50 = 9 个**（见 `competitions/cumcm/empirical.json`）。
这不是写论文时顺手画的量，Stage 5 每解完一个子问题就要产出对应图表，
不要堆到 Stage 8。

### 9.2 每个结果必须配的五件

1. **具体数值表**——坐标、时刻、分组边界、参数值逐个列出。只报"最优 68 海里"不算交付。
2. **计算方法说明**——求解器、步长、初值、收敛判据、运行环境，写到能复现。
3. **结果文件严格照题目模板**——文件名、Sheet 名、列名、单位、精度、行列顺序。
   纯送分项，错了变送死项。
4. **对结果的分析**——物理/业务含义、是否符合直觉、不符合时解释、异常点归因、与基线对比。
5. **稳健性/灵敏度**——关键参数扰动后结论是否翻转。

### 9.3 图的硬要求

- 坐标轴含义与单位齐全；对比类结果画在同一张图上
- 优先等高线/热力图，而非一屏数字
- **中文字体**：matplotlib 用 `SimHei`/`Microsoft YaHei`；注意 SimHei **缺 `³` 和 `−` 字形**，
  轴标签写"立方米"而不是 `m³`，并设 `axes.unicode_minus=False`
- 结论如果与预期相反，**照实画并标注**，不要因为图"不好看"就换口径

### 9.4 数值一致性（组委会会查）

**论文里的数字不要硬编码。** 让脚本把关键结果写进一个 `summary.json`，
LaTeX 从它取值；改了代码重跑即同步。否则极易出现"摘要写 1.55、正文写 1.62"——
而"摘要与正文里每个数字都能在结果文件里查到同一个值"正是 Stage 9 的核对项。

### 9.5 退出条件

- [ ] 每个子问题都有：数值表 + 图 + 方法说明 + 分析段 + 结果文件
- [ ] 结果文件名与列格式逐项核对过题目模板
- [ ] 摘要与正文的每个数字都能在 `summary.json` 或结果文件里查到
- [ ] 图表数量与一等奖分位大致可比（图 ~20、表 ~9），显著偏少要检查是否交付不足
