# 评分细则 (rubrics)

> **本文件里的 rubric 表格是生成物，不要手改。**
> 唯一数据源是 `config/rubric.json`；改完跑 `python scripts/render_rubric.py --write`。
> `doctor.py` 的 `rubric-sync` 每次都核，手改会被报出来。
> 各 stage 文件里的同名表格由同一份 JSON 渲染，因此不可能再漂。

> 三竞赛通用 5 维 rubric (国赛 / 美赛 / 电工杯 共享 stage 0-7 框架, stage 8/9 由 `competitions/cumcm/rubric_overlay.json` 特化)。L1 Critic 直接 JSON 化使用。

---

## Overlay 协议 (v3.1)

| 层级 | 来源 | 加载 |
|------|------|------|
| 通用基础 | 本文件 stage 0-9 表格 | 三竞赛共享 |
| 竞赛特化 dim 名 | `competitions/cumcm/rubric_overlay.json` 的 `dim_whitelist` | score_artifact.py 自动合并 |
| 题型 dim 权重 | `config/dim_weights.json[<comp>][<task_type>]` | compute_verdict 加权 mean |
| 样本观察 | `competitions/cumcm/empirical.json` | Critic 评分前按竞赛加载；只作参照 |

`task_type` 由 stage 1 选题后填入 decision_log; null 时 default 全 1.0 等价老逻辑。

---

## 三竞赛约束与内部质量视角

### CUMCM 国赛（内部启发式，不是官方评分权重）

| 维度 | 内部关注度 | 关键检查项 |
|------|-----|----------|
| **摘要质量** | 高 | 任务覆盖 / 可追溯的量化结果 / 验证与边界 / 信息密度 |
| **模型建立** | 高 | 与问题契合 / 假设有支撑 / 数学严谨 / 设计真实可解释 |
| **求解与结果** | 高 | 算法合理 / 代码可复现 / 结果可视化 / 现实意义 |
| **写作呈现** | 中 | 章节完整 / 公式编号规范 / 图表清晰 / 语言流畅 |
| **创新性** | 中 | 真实机制改进 / 跨学科融合 / 合理的子问题复用 |

### MCM/ICM 美赛（官方约束 + 内部质量检查）

> 当前没有可用于统计校准的语料；`competitions/cumcm/empirical.json` 只是结构占位，不能把其中数值用于评分。

| 维度 | 关键检查项 |
|------|----------|
| **Summary Sheet** | 第 1 页 / 方法与结果可追溯 / 限制诚实 |
| **Approach & Modeling** | 问题契合 / 假设支撑 / 设计选择有证据 |
| **Solution & Results** | 算法 / 复现性 / 与模型风险匹配的验证 |
| **Communication** | 写作清晰 / 图表 self-contained / 术语精确 |
| **Problem-specific deliverable** | 仅题目明确要求时加入 / 面向目标读者 / 保留证据与 caveat |

### 电工杯（内部工程质量检查）

> 当前没有可用于统计校准的语料；`competitions/cumcm/empirical.json` 只是结构占位，不能把其中数值用于评分。

| 维度 | 关键检查项 |
|------|----------|
| **工程实用性** | 落地可行 / 适用时的成本估算 / 实施条件 |
| **物理意义** | 数值带 kW/kWh/% / 工程语义 |
| **数据完整性** | 关键字段可追溯 / 未用字段说明取舍 / 预处理有据 |
| **多场景对比** | 场景覆盖主要工程风险 / 参数扰动有现实依据 |
| **写作呈现** | 引用格式按当年规则 / 工程惯用图表 / 单位与图例完整 |

---

## L1 阶段级 rubric (5 维 × 1-10)

每阶段产出后,Critic 输出以下 JSON:

```json
{
  "stage_id": 0-9,
  "iteration": 0-3,
  "scores": {
    "<dim_key_snake_case>": {"name": "中文名称", "score": 1-10, "evidence": "≤30字"},
    ...
  },
  "min_score": <number>,
  "mean_score": <number>,
  "issues": [
    {"severity": "high|medium|low", "where": "...", "anti_pattern_id": "A1|null", "fix": "..."},
    ...
  ],
  "verdict": "block | pass_early | pass | refine"
}
```

**dim key 命名约定**: 各 stage 的 5 个 `scores` 字段必须用**英文 snake_case**, 与 `feedback_layer1_critic.md §6` 各 stage 列出的固定集合精确一致 (`scripts/score_artifact.py` 加白名单校验)。下面各 stage 表第一列写中文是为了人读, 实际 JSON 输出用英文 key, **中文写在 `name` 子字段**。

退出条件: 见本文件末尾"阈值汇总"节, 与 SKILL.md / feedback_layer1_critic.md / score_artifact.py 三处统一。

---

### Stage 0 — 团队启动

<!-- RUBRIC:BEGIN 0 -->
| 维度 | 满分行为 (10) | 失败行为 (1) |
|------|-------------|-------------|
| 1. 角色分工明确性 (`1_role_clarity`) | 按实际人数覆盖建模/编程/写作责任，并设置互备 | 职责和交接人不明确 |
| 2. 工具就绪度 (`2_tools_ready`) | 题目需要的计算、写作、版本与沟通工具已验证 | 关键工具尚未试运行 |
| 3. 时间盒规划 (`3_time_planning`) | 按实际截止时间设置里程碑、关键路径和缓冲 | 无计划 |
| 4. 题目预扫信号 (`4_problem_scan`) | 已识别问题域 (优化/预测/评价等) | 未读题 |
| 5. 协作约定 (`5_collab_protocol`) | 命名规范、版本控制、daily standup 时间 | 无规范 |
<!-- RUBRIC:END 0 -->

---

### Stage 1 — 选题

<!-- RUBRIC:BEGIN 1 -->
| 维度 | 满分行为 |
|------|---------|
| 1. 候选覆盖与对比深度 (`1_three_options_depth`) | 当前全部可选题按同一组维度评估（难度 / 数据 / 契合度 / 工具 / 资料 / 主要风险），依据可追溯 |
| 2. 团队优势匹配 (`2_team_strength_match`) | 选题理由含"我们擅长 X,本题需要 X" |
| 3. 风险识别 (`3_risk_identification`) | 实质风险均有证据与应对；不重复凑数 |
| 4. 时间可行性 (`4_time_feasibility`) | 已估各阶段所需 h,合计不超过实际截止预算 |
| 5. 决策记录质量 (`5_decision_record_quality`) | rationale 与 rejected_alternatives 能回溯到题面、数据或团队约束 |
<!-- RUBRIC:END 1 -->

退出条件: 选定题号 + decision_log.json stage 1 节点完整 + 全维 ≥7。

---

### Stage 2 — 问题深度解析

<!-- RUBRIC:BEGIN 2 -->
| 维度 | 满分行为 |
|------|---------|
| 1. 子问题分解清晰度 (`1_subproblem_decomposition`) | 每个 Qi 卡片完整：输入 / 输出 / 约束 / 目标均明确 |
| 2. 关键变量识别 (`2_key_variables_count`) | 覆盖目标、约束与数据接口，标注类型，无占位变量 |
| 3. 数学化程度 (`3_math_skeleton_present`) | 每个 Qi 有符号化目标雏形；数学对象、输入输出、约束或评价关系与题意对应 |
| 4. 数据契合度 (`4_data_alignment`) | 题目附件数据已扫描（`scan_attachments.py` 已跑），与变量映射清楚；**且预处理决策逐问记录在 `preprocessing_decisions`，每个「做」的动作都写了非「统计习惯」的依据**（判据见 `题型与算法对照.md` §四第一步 / `anti_patterns.md` Z3+Z18；`check_data_decisions.py` 退出码须为 0） |
| 5. 子问题关联性 (`5_subproblem_dependency_identified`) | 每个 Qi 的依赖或独立理由均已识别 |
<!-- RUBRIC:END 2 -->

---

### Stage 3 — 模型选型

<!-- RUBRIC:BEGIN 3 -->
| 维度 | 满分行为 |
|------|---------|
| 1. 候选质量与反事实覆盖 (`1_candidate_diversity`) | 所有合理替代均被评估；无合理替代时检索范围与原因可审计 |
| 2. 选型理由 (`2_selection_rationale`) | 每个候选有 (a) 适配理由 (b) 不选的原因，两者都能追溯到题面、数据或团队约束 |
| 3. 命名准确性 (`3_naming_variant`) | 每个修饰词均能定位到公式、代码与验证；允许标准名称 |
| 4. 求解可行性 (`4_solver_feasibility`) | 已确认求解库存在、时间复杂度可承受，且 toy demo 真跑通 |
| 5. 文献/理论支撑 (`5_literature_support`) | 关键选型主张有相关且已核验的来源；不以篇数代替相关性 |
<!-- RUBRIC:END 3 -->

championship 模式额外：red-team 提出最可能推翻模型选择的反例或证据缺口，并给出验证动作。

---

### Stage 4 — Foundation (假设 + 符号 + 术语)

<!-- RUBRIC:BEGIN 4 -->
| 维度 | 满分行为 |
|------|---------|
| 1. 假设必要性 (`1_assumption_count`) | 每条都对应实际模型依赖，无同义凑数项 |
| 2. 假设支撑 (`2_assumption_support`) | 每条都有来源与证据路径（文献 / 附件数据 / 物理或业务机制 / 可执行检验）；必要但尚未验证的标 `provisional` 并在 Stage 5/6 安排检验（反模式 B1） |
| 3. 符号唯一性 (`3_symbol_uniqueness`) | 同一符号不跨语境换义；需要单位的量均标明单位 |
| 4. 与模型一致性 (`4_consistency_with_model`) | 与 Stage 3 选定模型无矛盾；Stage 5 结束后回检一次 |
| 5. 术语规范 (`5_terminology_standard`) | 专业术语首次出现即给定义并中英对照；正文中可能歧义的术语均已定义，无未使用术语 |
<!-- RUBRIC:END 4 -->

---

### Stage 5 — 子问题递归循环 (per Qi)

每个 sub-problem 跑一次 5 维 rubric,**外加** stage-level overall:

#### Per-Qi rubric:

<!-- RUBRIC:BEGIN 5_per_qi -->
| 维度 | 满分行为 |
|------|---------|
| 1. 模型与问题契合 (`1_problem_fit`) | 目标函数 / 决策变量 / 约束 与题面一一对应 |
| 2. 数学严谨性 (`2_math_rigor`) | 符号一致, 推导无跳跃 |
| 3. 求解正确性 (`3_solve_correctness`) | 代码运行 + sanity check 通过 |
| 4. 结果表达 (`4_visualization`) | 每个关键论点有最合适的图、表或数值证据；不重复、不凑数量 |
| 5. 物理意义讨论 (`5_physical_meaning`) | 解释与结果证据绑定；baseline 仅在公平可比时使用 |
<!-- RUBRIC:END 5_per_qi -->

#### Stage-level (跨子问题):

原来这里只有「复用链」「变量一致性」两条散文，而白名单有 5 个键——
**另外三维在 canonical 表里根本不存在**，Critic 只能自己编判据。现已补齐：

<!-- RUBRIC:BEGIN 5 -->
| 维度 | 满分行为 |
|------|---------|
| 1. 子问题完整性 (`1_subproblem_completeness`) | 所有 Qi 都跑完 |
| 2. 依赖链 (`2_cross_reference_chain`) | 有依据的上下游接口均显式传递；无合理依赖时理由已记录 |
| 3. 符号一致 (`3_symbol_consistency`) | 全 Qi 用同一套 stage 4 符号 |
| 4. 证据表达 (`4_visual_density`) | 图、表与数值产物足以支持关键论点且无装饰性重复 |
| 5. 时间预算 (`5_time_budget`) | 在已确认的 stage 5 预算内完成；偏差已留痕并获用户确认 |
<!-- RUBRIC:END 5 -->

退出条件: 所有 Qi 通过 + 复用链满足 + 全维 ≥7。

---

### Stage 6 — 全局灵敏度 / 稳健性

<!-- RUBRIC:BEGIN 6 -->
| 维度 | 满分行为 |
|------|---------|
| 1. 验证设计契合度 (`1_multivariate_perturbation`) | 按核心风险选择 OAT / 联合扰动 / 重采样 / 数据留出 / 情景或边界分析，并说明为什么是这一种 |
| 2. 范围真实性 (`2_perturbation_realism`) | 参数域、数据切分与场景有题目、数据或领域依据 |
| 3. 输出完整性 (`3_output_completeness`) | 同时追踪关键性能、决策变化、可行性与失败样本中适用的部分 |
| 4. 定量可复核 (`4_robust_interval_quantitative`) | 报告样本、种子、计算方法、区间及判断标准 |
| 5. 边界诚实度 (`5_failure_warning`) | 不虚构临界点，明确已观察边界与未测试区域 |
<!-- RUBRIC:END 6 -->

L2 触发: 末尾跨阶段回检 stage 3 的模型选择前提是否被本节结果推翻。

---

### Stage 7 — 模型评价 + 推广

<!-- RUBRIC:BEGIN 7 -->
| 维度 | 满分行为 |
|------|---------|
| 1. 优点具体 (`1_strengths_specific`) | 每项都有证据路径、适用范围和不外推声明 |
| 2. 局限真实 (`2_weaknesses_real`) | 覆盖证据、受影响结论、替代方案与验证代价 |
| 3. 改进可执行 (`3_improvements_actionable`) | 有对照设计、指标、资源，并区分 planned / tested / adopted / rejected；未做对照实验时不填收益 |
| 4. 推广具体 (`4_generalization_concrete`) | 说明可复用结构、重新标定、新风险与最低验证，或诚实不主张推广 |
| 5. 自我批判可信 (`5_self_critique_credibility`) | 不隐瞒失败样本，不把计划当结果，不虚构提升幅度；不写「假设理想化」这类套话（`anti_patterns.md` 会自动检） |
<!-- RUBRIC:END 7 -->

---

### Stage 8 — 论文写作

<!-- RUBRIC:BEGIN 8 -->
| 维度 | 满分行为 |
|------|---------|
| 1. 摘要信息闭环 (`1_abstract_5_paragraph`) | 覆盖问题、逐问方法、可追溯结果、验证与边界；不机械凑段或字数 |
| 2. 章节完整性 (`2_section_completeness`) | 题目要求与证据链所需章节齐全,无空节 |
| 3. 公式 / 图表 / 引用 (`3_formulas_figures_citations`) | 编号规范,首次引用先解释,引用格式符合所选竞赛当年要求 |
| 4. 语言质量 (`4_language_quality`) | 句长适度,无明显语病 (phrase_bank 关键词命中率) |
| 5. 视觉一致性 (`5_visual_consistency`) | 字号/配色/字体 全文统一,无 Word/Excel 默认输出 |
<!-- RUBRIC:END 8 -->

---

### Stage 9 — 终稿审核

**Stage 9 有两层反馈**（`stage_09_review.md` 的 `feedback: ["L1", "L3_panel", ...]`），
下面两张表各管一层。**别把它们混起来**：L1 是 5 维阶段级打分、键在
`score_artifact.py: DIM_WHITELIST[9]` 里；L3 是 5 视角 panel，走 `feedback_layer3_panel.md`。

#### L1 阶段级 (5 维，与其它阶段同构)

<!-- RUBRIC:BEGIN 9 -->
| 维度 | 满分行为 |
|------|---------|
| 1. 反模式覆盖 (`1_anti_pattern_coverage`) | `anti_patterns.md` 的全部索引项都过了一遍（`doctor.py` 报的 66 条），命中的每一条**要么已修，要么在论文里写明为什么不适用**；不允许"看过了"但无结论 |
| 2. 图表定稿质量 (`2_visual_polish`) | 逐张过 `figures/README.md` 的硬规矩：轴标签带单位、无双纵轴、≥2 系列有图例、只标结论点、顺序色非彩虹；灰度校样已翻过一遍 |
| 3. Panel 共识 (`3_panel_consensus`) | L3 五视角无 high-severity 未决项；verdict 不靠权重覆盖异议（任一 high-severity 保持 `block`） |
| 4. 瓶颈已处理 (`4_bottleneck_addressed`) | 最低分维度与高影响 issue 已**定向修补并让受影响视角复核**，不是记录在案就算完 |
| 5. 提交件可编可查 (`5_pdf_compile_clean`) | `check_compliance.py` 无 FAIL：PDF 能编、中文可从 PDF 提取、页数/大小/摘要单页合规、AI 声明三项齐、附录含源程序、正文与 PDF 元数据无身份信息 |
<!-- RUBRIC:END 9 -->

时间压力不把已知违规或错误算成满分——第 5 维由脚本判定，不接受人工"应该没问题"。

#### L3 五视角 panel

每个 panelist 独立打分:

| Panelist | 关注 |
|----------|------|
| **数学严谨** | 定理引用、推导、边界条件、单位 |
| **模型贡献** | 设计必要性、基线比较、实质改动证据 |
| **代码正确** | 复现性、注释、变量名、可读性 |
| **写作呈现** | 摘要、章节、图表、引用、配色 |
| **评委视角** | 30 秒内能否看懂核心问题、方法、结果与可信度 |

每位 panelist 输出:
```json
{"panelist": "...", "scores": {"1_dim": {"score": 8, "evidence": "..."}}, "issues": [], "verdict": "ready|refine|block"}
```

聚合器:
- 任一 high-severity issue 保持 `block`，权重不能覆盖
- 找最低分与高影响 issue，定向修补对应阶段一次
- 只让受影响视角复核；时间压力不把已知违规或错误变成 `ready`

---

## 阈值汇总 (与 SKILL.md / feedback_layer1_critic.md / score_artifact.py 统一)

**verdict 优先级 (从高到低)**:

| verdict | 触发条件 | 行为 |
|---------|---------|-----|
| `block` | issues 含 ≥1 high-severity | 暂停 skill, 用户介入 |
| `pass_early` | raw_min ≥ 9 AND weighted_mean ≥ 9 | iter-1 早退, 节省 token |
| `pass` | raw_min ≥ 7 AND weighted_mean ≥ 8 | 进下一阶段 |
| `pass_with_review` *(stage 5)* | 任 Qi mark_for_review 但加权阈值满足 | 进 stage 6, L2 必读 review_qis |
| `refine` | 其他 | section-patch 精修, iter+=1 (cap 3) |
| `refine_partial` *(stage 5)* | 任 Qi.min < 7, 但其他 Qi 已 pass | 仅 refine 标记 Qi, 不动其他 |
| `carryover` | iter == 3 仍 refine 或 refine_partial | 进下一阶段, 标记由 L2 处理 |

`weighted_mean` = Σ(s_i × w_i) / Σ(w_i), 其中 w_i 来自 `config/dim_weights.json` 题型加权 (clamp [0.7, 1.5]); `task_type=default` 全 1.0 等价老逻辑。

**内部质量档位**（用于工作流自检，不对应、也不预测竞赛奖项）：

| 档位 | 单维最低 | 均值 |
|---|---:|---:|
| 强 | ≥8 | ≥9 |
| 可交付 | ≥7 | ≥8 |
| 待复核 | ≥6 | ≥7 |
| 阻塞 | <6 | - |

---

## 与 winning_patterns / anti_patterns / empirical 的对应

本文件 rubric 项 ↔ `competitions/cumcm/winning_patterns.md` 段落 (路径按 decision_log.competition dispatch):
- abstract.* (stage 8 dim 1) → patterns §1, §9 + anti_patterns §A
- paper.section_completeness (stage 8 dim 2) → patterns §2 + anti_patterns §I
- paper.figure_density → patterns §3 + anti_patterns §E
- model.naming (stage 3 dim 3) → patterns §4 + anti_patterns §C1
- subproblems.cross_reference (stage 5 stage-level dim 2) → patterns §5 + anti_patterns §G
- assumptions.support (stage 4 dim 2) → patterns §6 + anti_patterns §B
- sensitivity.multivariate (stage 6 dim 1) → patterns §7 + anti_patterns §F
- evaluation.limitations_real (stage 7 dim 2) → patterns §8 + anti_patterns §H
- evaluation.real_critique → patterns §8

字数、图表数和公式数不作为官方硬阈值。CUMCM 的 `empirical.json` 记录 91 份来源中的 59 份可提取子集，只能用于异常提示。MCM/ICM 与电工杯的 `empirical.json` 均为无语料结构占位，不得引用其中数值。若 critique 提供 `evidence_metrics`，`score_artifact.py` 会打印可用的分位比较；它不会据此自动改分或把样本观察当作官方阈值。
