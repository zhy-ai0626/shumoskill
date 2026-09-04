# Scripts 工具说明

这里的脚本分为两组：比赛过程中使用的运行时工具，以及维护资料库时才使用的离线工具。下列命令均假设当前目录是 skill 根目录；用户项目中的动态文件统一放在项目工作目录，不写回 skill。

## 运行时工具

### `doctor.py` — 环境与包结构预检

在启动工作流或切换竞赛时运行。默认同时检查 skill 结构、竞赛包、JSON 配置和本地渲染工具；`--skip-tools` 适合 CI 或只做静态检查。

```bash
python scripts/doctor.py --competition cumcm --workspace /path/to/project
python scripts/doctor.py --competition mcm --skip-tools --json
python scripts/doctor.py --competition diangong --require-renderer --require-modeling
```

### `score_artifact.py` — L1 Critic 结果处理

校验 critique JSON、计算实际 verdict，并把阶段分数与迭代记录写入项目的 `state/decision_log.json`。

```bash
python scripts/score_artifact.py \
  --stage 5 \
  --critique /path/to/project/state/critique_v0.json \
  --decision-log /path/to/project/state/decision_log.json
```

不传 `--decision-log` 时，脚本按 `MATHMODEL_STATE_DIR`、兼容变量 `CUMCM_STATE_DIR`、最后 `<cwd>/state/decision_log.json` 的顺序解析路径。

所有子问完成后，可聚合 per-Qi 结果并把 `qi_status`、`review_qis`、`refine_qis` 与最终 verdict 原子写回 Stage 5：

```bash
python scripts/score_artifact.py \
  --mode aggregate_qi \
  --qi-results /path/to/project/state/qi_results.json \
  --decision-log /path/to/project/state/decision_log.json
```

### `extract_diff.py` — 定向修补辅助器

根据 Critic 指出的问题生成 section patch prompt，或应用已经生成的 section patch / unified diff。它的价值是缩小修改范围并保留已通过章节；实际节省量取决于论文和修补范围，不设固定比例。

```bash
# 生成定向修补 prompt
python scripts/extract_diff.py \
  --artifact /path/to/project/paper_workspace/06_models.md \
  --critique /path/to/project/state/critique_v0.json \
  --mode section \
  --output /path/to/project/state/refine_prompt.md

# 应用模型返回的 patch；--apply 模式不需要 --critique
python scripts/extract_diff.py \
  --artifact /path/to/project/paper_workspace/06_models.md \
  --apply /path/to/project/state/refine_patch.md \
  --mode section \
  > /path/to/project/paper_workspace/06_models_v1.md
```

### `render_paper.py` — Markdown 章节装配与 LaTeX 编译

把 `paper_workspace/` 中的编号 Markdown 章节装入所选竞赛的 `main.tex`。三类模板统一使用显式 section marker；正式编译要求 Pandoc 和对应 LaTeX 引擎，并在必需的 `01`–`10` 章节缺失、为空，或 marker 缺失、重复、未知时停止。内置简化转换器只用于 `--no-compile` 结构预检。

正式渲染还会检查提交元数据：CUMCM 要求最终题目和关键词，MCM/ICM 要求控制号、题号、题目和关键词，电工杯要求报名序号、题号、题目和关键词。CLI 参数优先于 `decision_log.paper_metadata`；`XXXX`、`X`、`keyword1` 等占位值会阻断编译。只有显式组合 `--allow-placeholders --no-compile` 才会生成带醒目标记的结构预览。

CUMCM 模板按 2026 电子论文基线提供 A4、四边 2.5 cm、第一页摘要、无目录、正文 >20 页警告（官方原文"尽量控制在 20 页以内"，>30 页才硬报错）和匿名字段最小化等 guard；它是仓库原创装配模板，不是官方模板，仍须在 Stage 0 与 Stage 9 重新核对当届通知。

```bash
python scripts/render_paper.py \
  --workspace /path/to/project/paper_workspace \
  --competition cumcm \
  --decision-log /path/to/project/state/decision_log.json \
  --output-dir /path/to/project/paper_output

# 只检查模板装配，不编译 PDF
python scripts/render_paper.py \
  --workspace /path/to/project/paper_workspace \
  --competition mcm \
  --output-dir /path/to/project/paper_output \
  --no-compile \
  --allow-placeholders
```

### `render_ai_usage.py` — AI 使用记录导出

从 `decision_log.compliance.ai_usage` 生成竞赛要求的披露材料，并直接放到渲染器约定的位置。CUMCM 使用 AI 时输出到 `support_materials/AI工具使用详情.{md,pdf}`；显式未使用时只输出 `paper_workspace/AI工具未使用声明.md`，渲染器把它接在参考文献之前。MCM 输出 `paper_workspace/11_ai_use_report.md`，且不重复模板提供的标题。CUMCM 的 PDF 生成依赖 ReportLab。

```bash
python scripts/render_ai_usage.py \
  --decision-log /path/to/project/state/decision_log.json \
  --competition cumcm \
  --paper-workspace /path/to/project/paper_workspace \
  --support-dir /path/to/project/support_materials

# 先只检查 Markdown 内容
python scripts/render_ai_usage.py \
  --decision-log /path/to/project/state/decision_log.json \
  --competition cumcm \
  --paper-workspace /path/to/project/paper_workspace \
  --support-dir /path/to/project/support_materials \
  --markdown-only
```

每条 AI 使用记录都必须含 `use_stage`，并完整记录 `query` + `output`，或为代码补全等非对话式工具提供 `disclosure`。`ai_usage: []` 只在团队明确核对“未使用”后填写；缺失或 `null` 会报错。

### `check_numbers.py` — 数值可追溯性

论文里的数字大多是从终端手抄进 LaTeX 的，抄错一位不报错、评委却能核出来。这个脚本把论文里的每个数值拿去 `results/` 下的 `.json`/`.csv` 里找同一个值，报出找不到的那些。单向检查：结果文件里有而论文没用到的值不算问题。

```bash
python scripts/check_numbers.py --paper paper.tex --results results/
```

### `scan_attachments.py` — 附件结构体检（Stage 1 有附件就必跑）

题型判据里有几条依赖**附件的结构性事实**，读题面看不出来，而看漏的代价是整条方法主线错。这个脚本把它们扫出来：一组列之和是否为（近似）常数（→ 成分数据，必须 CLR）、同一对象是否有多条记录（→ 观测不独立）、名字像标签的列是否只有一个取值（→ 真标签在别处，监督学习会退化成零正例且不报错）、是否有 Excel 合并单元格残留（→ 分组前必须 ffill）。

```bash
python scripts/scan_attachments.py <附件目录或文件>
python scripts/scan_attachments.py 附件1.xlsx --json
```

**这是体检不是门**，有发现也退出 0。但 `compositional` 与 `repeated_measures` 两类会改变方法主线，必须写进 `decision_log.problem_shape_modifiers`。

实测：2021B 六个"选择性"列之和恒为 100.0000（114 行无一例外）；2022C 化学成分和集中在 100 附近但范围 71.89~100（题面自己给了 85%~105% 的有效区间）；2025C 女胎表『胎儿是否健康』605 行全是"是"，真标签在『染色体的非整倍体』列。

### `check_selfaudit.py` — 自检承诺与局限的了结检查（Stage 6 与 Stage 9 强制项）

针对本 skill 演练里重复次数最多的失效模式：**写了自检却没执行**，以及**把本来就该做掉的活写成了"局限"**。脚本扫论文里的三类句子——自检承诺、局限（含整个「局限」小节）、自陈取常数/文献值——每一类都必须在 `state/self_audit.json` 台账里被了结，否则 FAIL。

台账条目用 `source_quote` 引用它所了结的那句原文，匹配靠子串包含，不做模糊匹配。**承诺写在论文里而台账没有也算 FAIL**：只查台账等于自己查自己，而演练里栽掉的恰恰是"承诺只写在散文里"。

```bash
# 首次：扫出待办生成台账骨架
python scripts/check_selfaudit.py --paper paper.tex --workspace paper_workspace/ \
    --scaffold > state/self_audit.json

python scripts/check_selfaudit.py --ledger state/self_audit.json \
    --paper paper.tex --workspace paper_workspace/ --results results/
```

模板与字段含义见 `templates/shared/self_audit.json`。退出码 1 = 有未了结项，2 = 没跑成。

### `check_compliance.py` — 提交前合规自查（Stage 9 强制项）

把 `stage_09_review.md` 的散文清单里能机器判定的部分变成一条命令：A4、≤20 MB、摘要单页、无目录/承诺书、正文页数、**中文能否从 PDF 提取**、AI 声明三项、附录源程序、正文与 **PDF 元数据**里的身份信息、未解析交叉引用，以及支撑材料压缩包的大小、是否含源程序、是否含 `AI工具使用详情.pdf`、有无凭据文件。

```bash
python scripts/check_compliance.py --paper paper_output/paper.pdf \
    --support support_materials/支撑材料.zip
python scripts/check_compliance.py --paper paper_output/paper.pdf --json
```

退出码 1 表示有 FAIL，不得提交（WARN 与人工项不影响退出码）；2 表示没跑成（文件不存在、缺 pypdf、或传了非 cumcm 的赛事）。`--json` 里的 `compliance_checks` 可直接写进 Stage 9，其中 `null` 表示该项没测到，必须人工确认后改成布尔值。

只编码 CUMCM 2026 规则。MCM/ICM 与电工杯条款不同，脚本会直接拒绝运行而不是冒充检查。

## 离线维护工具

这两个脚本用于维护样本资料，不应在比赛主流程中自动运行。先安装精简维护依赖：

```bash
python -m pip install -r scripts/requirements-maintenance.txt
python -m playwright install chromium  # 仅下载官方展廊页面时需要
```

### `download_cumcm_papers.py` — 官方展廊下载与 PDF 重建

当前下载器覆盖脚本内登记的 2023、2024 官方展廊页面。页面以图片形式展示论文，因此脚本使用 Playwright 发现详情页，再用 Pillow 重建 PDF。

```bash
python scripts/download_cumcm_papers.py \
  --papers-dir /path/to/cumcm-papers \
  --years 2023 2024
```

下载内容可能受站点结构、网络和来源授权影响；运行前应确认使用范围，并保留脚本生成的下载报告。

### `ingest_papers.py` — 可提取 PDF 的统计蒸馏

扫描指定目录中的 PDF，过滤无法提取足够文字的图片型文件，再生成描述性统计 Markdown。仓库记录了 91 份来源文件，其中 59 份满足当前提取条件；重新运行时以命令输出的“成功解析 / 文本可提取”计数为准。

```bash
python scripts/ingest_papers.py \
  --papers-dir /path/to/cumcm-papers \
  --output /path/to/empirical_distribution.md
```

生成值是样本子集的观察结果，不是官方评分线，也不会自动覆盖 `competitions/cumcm/empirical.json`。采用任何阈值前仍需人工审阅样本构成、提取误差和当年规则。

## 路径协议

| 类型 | 位置 | 覆盖方式 |
|---|---|---|
| skill 静态资源 | `<skill>/{references,templates,scripts,competitions}` | 不覆盖 |
| 项目状态 | `<project>/state/decision_log.json` | `--decision-log` 或 `MATHMODEL_STATE_DIR` |
| 项目产物 | `<project>/{results,figures,paper_workspace,paper_output}` | 通过各脚本参数指定 |

`<cwd>` 只是命令启动时的当前目录，不是一个应当原样创建的文件夹名。

## 测试 fixture

Critic schema 样本位于 `tests/fixtures/`：

- `test_critique_good.json`：有效的 stage-level critique。
- `test_critique_bad_keys.json`：包含不在白名单中的维度键，预期校验失败。

在临时项目目录运行写入型示例，避免修改仓库内的模板状态：

```bash
python scripts/score_artifact.py \
  --stage 1 \
  --critique tests/fixtures/test_critique_good.json \
  --decision-log /tmp/mathmodel-test/state/decision_log.json
```
