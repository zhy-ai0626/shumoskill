---
stage: 2
name: analysis
duration_h: 2-3
inputs:
  - "stage.1.selected"
  - "problem_pdf"
  - "attachment_data_paths"
outputs:
  - "stage.2.{decomposition, key_variables, key_constraints, objective_per_subproblem, data_schema, preprocessing_decisions, subproblem_dependency}"
loads_reference:
  - "references/rubrics.md§Stage_2"
  # 数据口径的判据在这两处。Stage 2 Step 4 是全流程里**唯一**扫附件的地方，
  # 也是唯一会顺手决定"要不要清洗"的地方——判据不在手上，这个决定就是瞎拍。
  - "competitions/<comp>/题型与算法对照.md§四"      # 第一步：判断要不要预处理
  - "competitions/<comp>/静默陷阱.md§四"            # 数据本身的静默坑
feedback: ["L1"]
next: stage_03_model_selection
---

# Stage 2 — 问题深度解析与分解

**时长**: 2-3h | **反馈层**: L1

---

## 目标

把题目从**自然语言描述**转化为**数学语言骨架**: 识别决策变量、目标函数、约束、子问题间关系。这一步质量决定后续 5/6/8 阶段的天花板。

---

## 输入

- stage 1 输出: 选定题号 + 子问题清单 + 数据路径
- 题目原文 (再读一次)
- 附件数据 (用 pandas/Read 扫一遍 schema)

## 产出

- 子问题分解树 (全部 Qi 的输入/输出/约束/目标)
- 关键变量清单 (覆盖实际模型所需变量并标注决策/状态/参数；不设凑数下限)
- 子问题间关联图 (谁依赖谁的结果)
- 目标函数雏形 (符号级,不必精确)
- 数据 schema 与变量映射
- **逐问的预处理决策表** (做什么、不做什么、凭什么；见 Step 4b)

---

## 操作流程

### Step 1: 题目精读 (30 min)

**精读三遍,每遍不同任务:**

第一遍 (10 min): 抓动词。题目让你做什么? "求最优..." / "预测..." / "评价..." → 决定问题类型。

第二遍 (10 min): 抓约束。哪些条件不能违反? 列出来。

第三遍 (10 min): 抓数据接口。哪些参数题目会给? 哪些要从附件提? 哪些要假设?

### Step 2: 子问题正式分解 (45 min)

对每个 sub-problem Qi,填写卡片:

```
Q1 卡片
├── 自然语言描述: <一句话提炼>
├── 输入:
│   - 题目给定参数: ...
│   - 附件数据: 附件 1 第 X 列
│   - 上游问题结果: 无 (Q1 是入口)
├── 输出 (最终决策变量):
│   - x_1, x_2, ... (含义、单位)
├── 约束:
│   - C1: ...
│   - C2: ...
├── 目标:
│   - 最小化/最大化 <什么>
├── 问题类型: <model_catalog 第几类>
└── 难度估计: easy / medium / hard
```

**关键**: 每张 Qi 卡片的“上游依赖”列必须明确写依赖哪些结果。只有题面、数学接口或业务机制支持时才建立依赖；“题目未禁止”不构成复用证据。没有合理依赖时写“无”，并保留理由。

### Step 3: 关键变量统一编号 (30 min)

跨子问题统一符号 (anti_pattern B4: 符号重复定义):

```
全局变量表 (stage 4 会复制到论文)

| 符号 | 含义 | 单位 | 类型 | 出现于 |
|------|-----|------|------|-------|
| x_i | 第 i 个产品的产量 | 件 | 决策变量 | Q1, Q2 |
| p_i | 第 i 个产品的单价 | 元/件 | 参数 (附件 1) | Q1, Q3 |
| α  | 折扣率 | 无量纲 | 参数 | Q3 |
| ξ  | 需求随机扰动 | 件 | 随机变量 | Q3 |
| ... |
```

只收录在目标、约束、数据映射或验证中实际使用的变量；缺少必要变量要补齐，无用途变量要删除。

### Step 4: 数据 schema 扫描 (30 min)

先跑脚本，再用 pandas 补细节。**脚本必跑**——它扫的四类结构性事实
（成分定和、重复测量、退化标签列、合并单元格残留）读题面看不出来，
漏掉任何一条都会让整条方法主线错，而且不报错：

```bash
python scripts/scan_attachments.py <附件目录>
```

然后人工补 schema：

```python
import pandas as pd
df = pd.read_excel("附件1.xlsx")
print(df.shape, df.dtypes, sep="\n")
print(df.describe(include="all"))
print(df.isnull().sum())
```

输出 schema 卡片:
```
附件 1 (xlsx):
- 行数/列数: `<由扫描结果写入>`
- 时间跨度: `<由原始字段计算>`
- 缺失: `<列名、计数与比例；不得预填>`
- 异常: `<检测口径与实际命中；不得预填>`
- 结构性发现: `<scan_attachments 的 findings；无发现写"无">`
- 与变量映射: p_i ← 列 "价格", d_i ← 列 "需求量"
```

### Step 4b: 预处理决策闸门 (15 min，**有附件就必做**)

**扫完不等于处理完，但也不等于什么都不做。** 这一格空着是本 skill 演练里
两个方向都栽过的地方，所以做成显式闸门而不是"注意一下"。

判据**不是**"附件长什么样"，而是**这一步是统计习惯，还是领域方法的组成部分**
（完整版见 `competitions/<comp>/题型与算法对照.md` §四第一步）：

| 步骤性质 | 做不做 |
|---|---|
| 常规统计预处理：去重、插补、类别平衡、按分位/按 3σ 删异常值 | **不做**，除非题目明确要求 |
| 原始流水/交易数据的聚合与口径统一（2023C 零售流水） | **做**——这是建模的一部分，不叫预处理 |
| 领域方法内在要求的质控（2025C 问题 4 的测序质量 QC） | **做**，并在论文里写明依据 |
| 量纲统一、仪器量程截断、单位换算 | **做**，写在数据口径一节 |

2025C 讲评末页原文：「对问题附件中的数据**无需进行清洗、删补、平衡等常规的、
无益于问题解决的预处理**」。限定语是"**常规的、无益于问题解决的**"，
不是"任何预处理"——同一份讲评里官方解问题 4 的第一步就是质控
（读段数等 5 个质量指标做中心 90% 截断，604 例筛到 501 例）。

**逐问填，不要在"数据口径"一节里一次性写死**（anti_pattern Z18）。
同一列在不同子问里可以有不同用法：过滤读段比例在建模里是**协变量**，
在判定质控里是**门槛**，两种用法并存不矛盾。

写入 `decision_log.stages.2.preprocessing_decisions`：

```json
{
  "<Qi>": [
    {"column": "<列名或列组>",
     "action": "keep_as_is | aggregate | qc_filter | unit_convert | impute",
     "nature": "统计习惯 | 领域方法组成部分 | 口径统一",
     "rationale": "<为什么；引题面/讲评/领域规范，不能只写『常规做法』>",
     "rows_affected": "<实际影响行数；keep_as_is 写 0>"}
  ]
}
```

`action` 不是 `keep_as_is` 时，`nature` **不允许**填"统计习惯"——
那正是讲评点名不要做的那一类。真要做就得说清它凭什么不是统计习惯。

### Step 4c: 静默坑排查 (10 min)

`competitions/<comp>/静默陷阱.md` §四列的四条，逐条在本题附件上验一遍。
它们的共同点是**不抛异常，只出错数**：

| 坑 | 怎么验 |
|---|---|
| 同一列混合类型（一半 `int`、一半被 Excel 读成 `datetime`） | `df[c].map(type).value_counts()`；别直接 `to_numeric(errors="coerce")`，它把错的静默变 `NaN` |
| 大小写/全半角不一致（孕周里混一个大写 `16W+1`） | `df[c].str.upper().nunique()` 比 `df[c].nunique()` 小就命中 |
| 两列本该自洽却对不上（2025C 孕周 vs 检测日期−末次月经，只有 38.4% 吻合） | 自己算一遍那个派生量，报吻合比例；**选哪一列当准要在论文里写理由** |
| 恒等式关系的变量同时入模（BMI ≡ 体重/身高²，VIF 到 10⁴） | 算 VIF；乘除关系取对数后是精确线性，log 空间的 VIF 更灵 |

这四条 `scan_attachments.py` 都会扫（`mixed_dtype` / `case_collision` /
`derived_mismatch` / `identity_collinear`），但**脚本只给候选，判断要人做**——
比如"两列对不上"到底哪一列可信，只有读题面才知道。

### Step 5: 子问题关系图 (15 min)

以 mermaid / ASCII 表达:

```
<上游 Qi> (<任务>)
  ↓ <有证据支持的输出接口>
<下游 Qj> (<任务>)
  ↓ <有证据支持的输出接口>
最终: <题面要求的交付>
```

写入 `decision_log.stages.2.decomposition`。

### Step 6: 目标函数雏形 (30 min)

每个 Qi 写出符号化目标 (不必完整,要框架):

```
Q1: max  Σ_i p_i * x_i  - C(x)
    s.t. Σ_i x_i ≤ B (预算)
         x_i ≥ 0, x_i ∈ Z

Q2: 在 Q1 基础上加约束 K_i ≤ K_max
    
Qi: <与该子问题匹配的符号化目标>
    若使用上游结果或 warm start，注明接口与依据；否则保持独立
```

### Step 7: 输出移交 (5 min)

写入 `decision_log.stages.2`:
```json
{
  "decomposition": [...],
  "key_variables": [...],
  "key_constraints": [...],
  "objective_per_subproblem": {"<Qi>": "..."},
  "data_schema": {...},
  "preprocessing_decisions": {"<Qi>": [{"column": "...", "action": "...",
                                        "nature": "...", "rationale": "...",
                                        "rows_affected": 0}]},
  "subproblem_dependency": {"<Qi>": ["<only evidence-backed upstream IDs>"]}
}
```

---

## L1 Rubric (`rubrics.md` Stage 2)

<!-- RUBRIC:BEGIN 2 -->
| 维度 | 满分行为 |
|------|---------|
| 1. 子问题分解清晰度 (`1_subproblem_decomposition`) | 每个 Qi 卡片完整：输入 / 输出 / 约束 / 目标均明确 |
| 2. 关键变量识别 (`2_key_variables_count`) | 覆盖目标、约束与数据接口，标注类型，无占位变量 |
| 3. 数学化程度 (`3_math_skeleton_present`) | 每个 Qi 有符号化目标雏形；数学对象、输入输出、约束或评价关系与题意对应 |
| 4. 数据契合度 (`4_data_alignment`) | 题目附件数据已扫描（`scan_attachments.py` 已跑），与变量映射清楚；**且预处理决策逐问记录在 `preprocessing_decisions`，每个「做」的动作都写了非「统计习惯」的依据**（判据见 `题型与算法对照.md` §四第一步 / `anti_patterns.md` Z3+Z18；`check_data_decisions.py` 退出码须为 0） |
| 5. 子问题关联性 (`5_subproblem_dependency_identified`) | 每个 Qi 的依赖或独立理由均已识别 |
<!-- RUBRIC:END 2 -->

> **不要在这里加第 6 维。** L1 rubric 全局固定 5 维（`rubrics.md` 标题即
> "5 维 × 1-10"），`score_artifact.py` 的 `DIM_WHITELIST[2]` 也只认 5 个键。
> 加第 6 维的后果是二选一，两个都坏：Critic 真产出第 6 个键 → 白名单校验 FAIL；
> 只产出 5 个键 → 新判据**永远不被打分**（写了等于没写）。
> 所以预处理决策折进 `4_data_alignment` —— 那一维本来就是"数据契合度"，
> 而且 `config/dim_weights.json` 对 C 题给它 **1.4** 权重，
> 正好是数据口径最要紧的题型。改判据请同时改 `references/rubrics.md`
> 的同一行，`tests/test_rubric_consistency.py` 会核对两边一致。

---

## 常见坑

- 题目仅读一次就开干 → 强制读 3 遍
- 子问题间符号不统一 (B4) → 统一变量表
- 附件数据没扫 → strictly 必做 Step 4
- 为了“串起来”强行复用上游结果 (G1) → 只保留题面、数学或业务机制支持的依赖
- **拿到附件先清洗、删补、做类别平衡** (Z3) → 走 Step 4b 闸门，默认不做
- **反过来把“无需预处理”泛化到所有子问** (Z18) → 逐问判断；领域方法要求的质控要做
  且写依据。2025C 复现里不做质控的合并模型 Sp 95% 时 Se 只有 0.373，
  官方逐染色体是 Se 0.92–1.00 @ Sp 99%——差一个量级

---

## 退出条件

1. 题面中的全部子问题卡片完整
2. 全局变量表覆盖后续模型实际所需项且无凑数项
3. 数据 schema 扫描完成（`scan_attachments.py` 已跑，findings 已入卡片）
4. 每个 Qi 的依赖关系明确 (依赖 / 独立,均有理由)
5. **数据口径闸门通过**（第 5、6 条不再靠人核，跑脚本）：

   ```bash
   python scripts/scan_attachments.py <附件目录> --json > state/scan.json
   python scripts/check_data_decisions.py \
       --decision-log state/decision_log.json --scan state/scan.json
   ```

   退出码 1 表示有 FAIL，**Stage 2 不得退出**。它查：有附件数据却没填决策、
   缺 Qi 的键、`action` 不在枚举、**动了数据却把 `nature` 写成"统计习惯"**（Z3）、
   `rationale` 是套话或没有可追溯出处、`data_schema.silent_traps` 缺失。
   反方向（全问全 `keep_as_is`）只报 WARN 并附 2025C 的量化证据（Z18）——
   **多数题目全 `keep_as_is` 是正确答案**，判成 FAIL 会逼人为过门去动数据，
   正好掉进 Z3。WARN 要逐条读完再决定。

   首次可从体检报告生成骨架：`--scan state/scan.json --scaffold`。
6. L1 rubric 全维 ≥7（数据口径与静默坑都计入 `4_data_alignment` 这一维）

→ 跳转 `stage_03_model_selection.md`
