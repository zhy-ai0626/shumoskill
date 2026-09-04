---
stage: 1
name: problem_selection
duration_h: 2-3
inputs:
  - "stage.0.problem_scan"
  - "problem_pdfs[<topic_letters>]"
  - "decision_log.competition"
outputs:
  - "stage.1.{selected, rationale, rejected_alternatives, candidates_assessed, risks_identified}"
  - "root.task_type"
  - "root.problem_shape"
  - "root.problem_shape_modifiers"
loads_reference:
  - "references/rubrics.md§Stage_1"
  - "references/model_catalog.md§0"
  - "competitions/<comp>/topic_specs.json"
feedback: ["L1"]
next: stage_02_analysis
---

# Stage 1 — 选题 (多题对比 → 1)

**时长**: 2-3h | **反馈层**: L1 | **关键决策点**: 选题依据写入状态；出现新证据时可审计地重开决策

---

## 目标

在本科组 A / B / C 三题中，选出**最契合团队优势 + 时间预算 + 数据可获取性**的一题，
并让选择、否决与后续变更都有据可查；同时**从题面判定题型**（不是从题号推）。

**第一步必做**: 加载 `competitions/<comp>/topic_specs.json` 获取题号清单与每题 `task_type_key`；选定后写两个字段：

- `decision_log.task_type` ← `topic_specs.json[selected].task_type_key`。**只供 stage 3+ 的 dim_weights 查表**，键名里的 optimization/evaluation/data 是上游遗留，不是题型判断。
- `decision_log.problem_shape` ← **从题面判定的题型**，取值见 `topic_specs.json._problem_shapes` 五选一。判据见 `competitions/cumcm/题型与算法对照.md` 第一节。**Stage 3 按它选方法主线**（`winning_patterns.md` §1 五类），所以判错的代价远大于 task_type 判错。

---

## 输入

- stage 0 元信息 + 题目预扫
- `topic_specs.json` 所列候选题的官方 PDF (用户提供路径)

## 产出

- `decision_log.stages.1.selected`: 选定题号
- `decision_log.stages.1.rationale`: 选择理由与证据
- `decision_log.stages.1.rejected_alternatives`: 其余已评估候选及不选理由
- `decision_log.stages.1.candidates_assessed`: 全部可选题的对比矩阵

---

## 操作流程

### Step 0: 加载竞赛题号体系 (5 min, 必做)

```bash
# 路径: <skill>/competitions/<comp>/topic_specs.json
# 加载后得到题号清单 (本 fork 只有 cumcm A/B/C) 与每题的 task_type_key + 近五年实际题型
```

本 fork 只覆盖 **CUMCM 本科组 A / B / C**，中文论文、xelatex、72 小时。

> **⚠ 题号不是题型。** 上游那张「A 优化 / B 评价 / C 数据」的表已删除，因为它是错的：
> B 题最近四年是 2022B 计算几何、2023B 几何+优化、2024B 统计决策、2025B 光学反演，
> **零次评价类**。上游还把 B 题的典型方法写成 AHP/熵权/TOPSIS——
> 那恰好是组委会连续四年点名的套路化方法，照着选就直接踩反模式。
>
> `topic_specs.json` 里每题都列了近五年的**实际**题型，用它做先验可以，
> 但**题型必须从当届题面重新判定**，判据见 `题型与算法对照.md` 第一节。

### Step 0.5: 附件结构体检 (10 min, 有附件就必做)

```bash
python <skill>/scripts/scan_attachments.py <附件目录>
```

题型判据里有几条依赖**附件的结构性事实**，读题面看不出来：

| 扫到什么 | 意味着 |
|---|---|
| `compositional` / `compositional_approx` | 有一组列之和为（近似）常数 → **成分数据，方法全变**，必须 CLR。即使主线不是成分数据类，也要加进 `problem_shape_modifiers` |
| `repeated_measures` | 同一对象多条记录 → 观测不独立，回归要用混合效应/GEE |
| `constant`（列名像标签却只有一个取值） | **真标签在别处**。拿它做监督学习会得到零正例的退化模型，且不报错 |
| `merged_cells` | Excel 合并单元格残留，当分组键前必须 `ffill()`，否则每组只剩 1 行 |

实测三例：2021B 六个"选择性"列之和恒为 100（主线是数据统计，但成分约束是真的）；
2022C 化学成分和集中在 100 附近、范围 71.89~100（题面自己给了 85%~105% 的有效性区间）；
2025C 女胎表『胎儿是否健康』605 行全是"是"，真标签在『染色体的非整倍体』列。

结果写进 `decision_log.problem_shape_modifiers`。

### Step 1: 候选题信息提取 (45 min,可并行)

为 `topic_specs.json` 中每道当前可选题提取；不要截取固定数量的候选，也不要为凑数量加入未发布或不适用的题:
- **核心任务** (1 句话)
- **子问题数与各自难点**
- **附件数据** (大小、格式、是否需清洗)
- **预估问题类型** (model_catalog.md 1-10 类)
- **历年类似题** (若知道)

每题输出一张同构卡片 (markdown):

```
## A 题: <标题>
- 核心: ...
- 子问题: `<按官方题面逐项列出>`
- 数据: `<附件路径、实际格式与扫描大小>`
- 类型: 优化类 + 预测类
- 类似题: `<有已核验来源时填写，否则写未检索到>`
```

### Step 2: 5 维对比矩阵 (30 min)

| 维度 | 权重 | `<题号 1>` | `...` | `<题号 N>` |
|------|-----|-----------|-------|-----------|
| 1. 数据可处理性 | 0.20 | `<score>` | `...` | `<score>` |
| 2. 团队工具匹配 | 0.25 | `<score>` | `...` | `<score>` |
| 3. 模型族契合 | 0.20 | `<score>` | `...` | `<score>` |
| 4. 时间可行性 | 0.20 | `<score>` | `...` | `<score>` |
| 5. 创新空间 | 0.15 | `<score>` | `...` | `<score>` |
| **加权总分** | | `<weighted>` | `...` | `<weighted>` |

每维评分必须有**一句话依据** (写在表下方)。

### Step 3: 风险识别 (30 min)

为领先候选列出所有**有题面、数据或团队能力证据的实质风险**及应对策略。没有额外风险时明确写“未发现新的实质风险”，不要换措辞凑数:

```
风险 <ID>: <由题面、附件或团队能力暴露的风险>
  证据: <可追溯来源>
  应对: <可执行缓解措施与触发 fallback 的条件>
```

### Step 4: 决策与锁定 (15 min) — 问答式

**呈现给用户** (Claude Code: AskUserQuestion; Codex CLI: 编号列表):

```
【基于 5 维对比矩阵, 推荐选题】

  1) <题号> — <加权结果>, 主要依据: <可核验依据>
  2) <题号> — <加权结果>, 主要依据: <可核验依据>
  ...
  N) 让我决定 (推荐当前证据最充分的题)

回复数字。
```

用户选定后, **agent 自动写入** `decision_log.stages.1` (不要让用户编辑 json):
```json
{
  "selected": "<selected topic>",
  "rationale": "... 可追溯依据 ...",
  "rejected_alternatives": [
    {"题号": "<other>", "reason": "... 有证据的不选理由 ..."}
  ],
  "candidates_assessed": [...],
  "risks_identified": [...]
}
```

**同步写 root 字段**:
- `decision_log.task_type` ← `topic_specs.json[selected].task_type_key` (e.g. `A_optimization` for cumcm-A)
- `decision_log.problem_shape` ← 五类题型之一，**从题面判定**，并写明判定依据（题面里的哪句话/哪个附件特征）。
  与 `topic_specs.json` 里该题号的"近年实际题型"不一致时，**以题面为准**，并在 rationale 里说明为什么不同。
- `decision_log.stages.5.qi_count` ← 优先使用官方题面解析出的实际子问题数；题面未到时才用 `topic_specs.json[selected].expected_subproblem_count` 做 provisional 估计，并在 stage 2 覆盖
- `decision_log.stages.5.qi_weights` ← `[1.0] * qi_count` (默认均匀, 用户后续可在 stage 5 调整)

**决策版本**: 选定题号作为当前有效版本。若附件不可用、官方更正或新增团队约束等新证据足以改变排序，触发 L2 并向用户做一次编号确认；在 `decision_log.events.log` 记录原题号、新题号、证据、时间与受影响阶段，然后从最早受影响阶段恢复。不得因短暂犹豫无证据换题，也不得用固定时间窗阻止有依据的纠错。

### Step 5: 移交 (5 min)

输出给 stage 2 的"问题输入包":
- 选定题号
- 子问题清单
- 附件数据路径
- 预估问题类型
- 风险清单

---

## L1 Rubric (`rubrics.md` Stage 1)

| 维度 | 满分行为 |
|------|---------|
| 1. 候选覆盖与对比深度 | 当前全部可选题均按同一维度评估，依据可追溯 |
| 2. 团队优势匹配 | 选题理由含"我们擅长 X,本题需要 X" |
| 3. 风险识别 | 实质风险均有证据与应对；不重复凑数 |
| 4. 时间可行性 | 已估各阶段所需 h,合计不超过实际截止预算 |
| 5. 决策记录质量 | rationale 与 rejected_alternatives 能回溯到题面、数据或团队约束 |

退出: 全维 ≥7。

---

## 常见坑

- **J2** 选题摇摆: 无新证据不重开；有决定性新证据则按 L2 留痕重开
- 候选题都说不清: 信号是 Step 1 没读透题,回 stage 0 重读题目 PDF
- 选了团队最擅长但题目本身证据空间不足: 回看创新空间的事实依据，而不是用最低分数掩盖问题

---

## 退出条件

1. 已评估当前全部可选题并选定一个当前有效题号
2. decision_log.stages.1 完整 (5 个 key 都有内容)
3. L1 rubric 全维 ≥7
4. 风险清单已有应对

→ 跳转 `stage_02_analysis.md`
