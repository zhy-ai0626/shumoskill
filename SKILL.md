---
name: cumcm-abc
description: 全国大学生数学建模竞赛（CUMCM）本科组 A/B/C 题的端到端工作流。Use when the user works on CUMCM problem A, B or C — from problem selection through modeling, solving, robustness, writing, compliance, to final submission review. 10 stages with persistent decision state, 2026 rules baseline with AI-disclosure gating, and an empirical layer distilled from 18 official commentaries and 44 award-winning papers. Do not trigger for MCM/ICM, 电工杯, D/E 题, generic model selection, or ordinary data analysis.
---

# cumcm-abc — CUMCM 本科组 A/B/C 题工作流 (v6.1)

10 阶段把 72 小时的竞赛协作变成可恢复、可检查的流程。用户回答关键问题，agent 维护状态与脚本。每阶段产出经过 rubric 自评、定向精修与跨阶段一致性回检；Stage 8–9 先遵守当届官方规则，再做多视角终审。实证层来自 **18 份官方讲评全文 + 112 篇 ABC 论文**（见下文「语料规模」）。

**v6.1 更新**: 加入竞赛规则基线与 AI 使用披露链路；marker 模板对提交元数据 fail closed；修复状态路径错位、评分 verdict 持久化、题型权重合并和 YAML frontmatter 等问题；新增 preflight doctor 与自动化验证。

**本 fork 与上游的关系**：骨架来自 `handsomeZR-netizen/mathmodel-skill`（MIT），
**蒸馏层全部重做**，MCM/ICM 与电工杯的模板、配置、语料已移除——只做国赛 ABC。

---

## Codex 原生入口

Codex 优先按 skill 目录发现本文件:

- 用户级安装: `$HOME/.agents/skills/cumcm-abc/`
- 项目级安装: `<repo>/.agents/skills/cumcm-abc/`
- UI 元数据: `agents/openai.yaml`
- 项目指导: `AGENTS.md` 仍可作为 repo / workspace 级 instructions, 但不是唯一入口

当 skill 已安装后, 用户可直接说"开始建模"或显式说"使用 `$cumcm-abc` 开始建模"。

---

## Harness 兼容 (Claude Code / Codex)

本 skill v6.1 以 Codex Skills 为一等入口, 同时保持 harness-agnostic 设计:

| harness | 入口文件 | 用户交互工具 | 状态文件 |
|---------|---------|-------------|---------|
| Claude Code | `SKILL.md` (本文件) | `AskUserQuestion` 工具 | `<cwd>/state/decision_log.json` |
| Codex CLI / Codex app | skill 目录中的 `SKILL.md` + 可选 `AGENTS.md` | markdown 编号列表 | 同上 (**互通**) |

跨 harness 互通: day 1 用 Codex 跑 stage 0-2, day 2 切回 Claude Code 接着 stage 3+, 状态完全保留。详见 `references/harness_compat.md`。

---

## 问答式优先 (Friendly Mode)

**核心原则**: 用户只需回答**编号问题**, 不应被要求手敲 bash / python / json。

- 离散选项 (选竞赛 / 选题 / 选模型 / verdict 决策) → **必须**用问答式
- 自由文本 (PDF 路径 / 截止时间) → 单行回复
- 状态读写 (decision_log.json) → agent 自动完成
- 每个 stage 的关键决策点都有 "让我决定 (推荐 X)" 兜底选项

优先使用当前 harness 可用的原生选择 UI；没有时回退到 markdown 编号列表。两者语义等价，见 `references/harness_compat.md` §1。

---

## 路径解析协议 (任何阶段必读)

| 类型 | 位置 | 例 |
|------|------|-----|
| skill 内通用 | skill 根目录的相对路径 | `references/stage_05_subproblem_loop.md`, `templates/shared/decision_log.json` |
| 用户产物 | 用户工作目录的相对路径 | `<cwd>/state/`, `<cwd>/results/`, `<cwd>/figures/`, `<cwd>/paper_workspace/` |
| state 持久化 | `<cwd>/state/decision_log.json` | 各 stage 必读必写 |
| 环境变量 | `MATHMODEL_STATE_DIR` (兼容 `CUMCM_STATE_DIR`) / `MATHMODEL_COMPETITION` 可覆盖 | scripts 用此变量 |

约定: `<skill>/` = skill 安装目录, `<cwd>/` = 用户 cwd。本 fork 只有 `cumcm` 一个竞赛包，
路径里的 `competitions/cumcm/` 是固定的（上游那套 competition 切换机制保留但只剩一个取值）。

---

## 本地蒸馏层（相对上游的差异，优先读这里）

本 skill 由 `handsomeZR-netizen/mathmodel-skill`(MIT) 改造，**工作流保留，蒸馏层重做**。
以下文件是本地新增/修正的，与上游同名文件冲突时**一律以这里为准**：

| 文件 | 内容 | 何时读 |
|---|---|---|
| `competitions/cumcm/current_rules.md` | **2026 规则基线 + AI 披露链路**。修正了上游"正文限 30 页"的错误（官方是**尽量 20 页以内**），并把 AI 规定从 2025 试行版更新到 2026 试行版 | Stage 0 必读；Stage 9 提交前逐条核 |
| `competitions/cumcm/winning_patterns.md` | **运行时主入口**，已接入 Stage 0/3/4/5/6/7/8：题型→算法主线、反模式速查、结果呈现清单、摘要成分、结构分位 | 各 Stage 自动读取 |
| `competitions/cumcm/anti_patterns.md` | 66 条反模式（上游 A–J 共 42 条 + 本项目 Z1–Z24），Z 段每条都有官方原文或演练实测出处；含**使用边界告示**（别把简化近似判成错误） | Stage 3 选模型、Stage 9 终审 |
| `competitions/cumcm/题型与算法对照.md` | 给人读的**完整版**知识总结（与交付包 `4_知识点总结` 同一文档），运行时不必全读 | 赛前通读一遍 |
| `assets/official/` | **随 skill 分发的官方原件**：2026 AI 规定、论文格式规范、参赛规则、format2025.doc、AI 详情模板 | Stage 0 / Stage 9 |
| `competitions/cumcm/摘要写法.md` | 44 篇一等奖摘要的成分命中率与真实句式 | Stage 8 写摘要 |
| `competitions/cumcm/empirical_abc.json` | **按 题号×年份×来源 分层**的实证分位 | L1 critic 取锚点 |
| `figures/cumcm_style.py` + `figures/gallery.py` | **图表模板**：中文字体、经验证的分类色板、**灰度打印可读**（颜色与线型/填充网格/标记捆绑，颜色拿不到单独用）、按题型的 7 张范例。图是主要得分位——2022A 讲评 9 条评阅问题里 5 条是呈现类，一等奖图数中位 20 张 | Stage 5 出结果图、Stage 8 排版 |
| `code-templates/` | 30 个可跑代码模板(python/matlab) + 12 个 playbook，来自 `Lupynow/math-modeling-skills`(MIT)，**未改其内部约定** | Stage 5 求解 |

**语料规模**：上游收录 91 份、仅 59 份可提取文本、2025 年 n=1；
本地为 **112 篇 ABC（44 篇官方展示 + 68 篇社区），2020–2025，2025 年 n=5**，
另有 **18 份官方讲评全文（42.4 万字）——上游完全没有这一层**。

**可信度边界（必须遵守）**：
- 蒸馏文档里的散文与结论来自 OCR，可信；
- **公式不可直接引用**，OCR 对复杂公式有错误，需回 资料库的 `2_官方讲评/`、`3_优秀论文/官方展示/` 原 PDF 核对（这两处体积大，不随 skill 分发，见 `assets/official/README.md`）；
- 分位数只用于"这篇是不是明显异常"的提示，**不是评分线，也不预测获奖**。

**弃用的上游文件**：`empirical.json` / `empirical_notes.md` / `distilled_*.md`
（基于 59 份混合样本，已被上表前四项取代，保留仅供对照）。

---

## Quick Start (用户首次说"开始建模")

```
1. 一段话介绍 (≤50 字): "启动 CUMCM ABC 题工作流, 10 阶段, 全程问答式."

2. 收集下列 5 个启动字段；用户已经提供或 state 已记录的字段不再询问，只把尚缺字段合并成一轮问答 (Claude Code: AskUserQuestion; Codex: 编号列表):
   - 题号 (A / B / C；"未公布"亦可。本 skill 不覆盖 D/E 题与美赛)
   - 队员数 + 各人擅长 (建模/编程/写作)
   - 截止时间 (ISO 字符串或 "距现在 X 小时")
   - 题目 PDF 路径 ("未公布"亦可)

3. 自动初始化 (agent 自动完成, 不要让用户编辑 json):
   - 不存在 `<cwd>/state/decision_log.json` → 创建目录并复制 `<skill>/templates/shared/decision_log.json` 到该路径
   - 写入 decision_log.competition = <选定竞赛>
   - 已存在 → 读 current_stage 字段决定恢复点

4. **先读 `competitions/cumcm/current_rules.md`**（这是 2026 基线，含 AI 披露要求），核对当届官网有无更新并写入 compliance；再按需读 `题型与算法对照.md`

5. 进入 Stage 0 (`references/stage_00_kickoff.md`), 不重复问已知字段；若题面未公布，完成环境与协作准备后保持 `qi_count=null` 并等待题面，不进入 Stage 1
```

**已有 state 触发** (用户中途回到 skill，或上下文被压缩后换了会话):
```
1. 读 `<cwd>/state/decision_log.json` 的 competition 与 current_stage
2. **读 resume 段**：
   - `settled_conventions` → 这些口径已经定死，不许重新决定
   - `in_flight` → 上次停在哪个 Qi、做到哪一步
   - `next_actions` → 下一步做什么，照做，不要重新读题面自己另想一套
   - `open_questions` → 有未决问题就先问用户，不要自己替他拍板
   - `reproduce` → 要复现数值就按 entrypoints 与 seed 跑，别重写脚本
3. 清点磁盘：results/ figures/ paper_workspace/ 里已有什么，别重算已有的
4. 加载对应 stage_NN.md (按需结合 competitions/cumcm/* 内容)
5. 不重复读 winning_patterns
```
> 恢复时最容易犯、也最难发现的错不是"忘了做什么"，而是**把某个口径换了个同样合理的定法**
> ——比如平均改成加权、起算点换一个、异常值判据松一档。前后两问的数字就不可比了，
> 而且**任何脚本都不会报错**。`settled_conventions` 就是为这件事存在的。

---

## 竞赛 × 三模式 矩阵

时长 / 语言 / 模板 / 数据状态 由 competition 决定; token 预算 / 反馈深度由 mode 决定。两者**正交组合**。

| Competition | 时长 | 语言 | LaTeX | 规则基线 | 经验数据状态 |
|---|---|---|---|---|---|
| cumcm | 72h | 中文 | xelatex / 原创 ctexart | CUMCM 2026 | 18 份官方讲评 + 112 篇 ABC 论文（2025 年 n=5） |

| Mode | 上下文策略 | 反馈层 | 用途 |
|---|---|---|---|
| fast | 只保留当前阻断项与最小证据 | L1 单次 | 选题试跑 / sanity check |
| standard | 按阶段加载并保留决策摘要 | L1+L2 | 默认主流程 |
| championship | 在终审阶段扩展证据与独立视角 | L1+L2+L3+L4 + red-team | 提交前最后冲刺 |

模式自动推荐 (按距 deadline 剩余):
- > 60h: standard (最后 6h 升 championship)
- 24-60h: standard
- 6-24h: fast 关键阶段 + championship 终审
- < 6h: 直接进 stage 9 (championship)

---

## 10 阶段索引

| # | 阶段 | reference | 时长 | 反馈 | 竞赛差异点 |
|---|------|-----------|------|------|-----------|
| 0 | 团队启动 + 资料预扫 | `stage_00_kickoff.md` | 1h | L1 | 时长 / 语言 / 编译器 / 题号体系 |
| 1 | 选题 (多题对比 → 1) | `stage_01_problem_selection.md` | 2-4h | L1 | 题号体系 (A-E/A-F/A-B) + task_type 写入 |
| 2 | 问题深度解析与分解 | `stage_02_analysis.md` | 2-3h | L1 | 通用 |
| 3 | 模型选型 (证据驱动的候选比较) | `stage_03_model_selection.md` | 2-4h | L1 + 反事实 | 通用 |
| 4 | Foundation (假设+符号+术语) | `stage_04_foundation.md` | 1h | L1 | 通用 |
| 5 | **递归子问题循环** Q1..Qn + per-Qi 加权聚合 | `stage_05_subproblem_loop.md` | 按题目分配 | L1 + 子检查点 | 从题面提取实际子问数；per-Qi 加权 |
| 6 | 全局灵敏度 / 稳健性 | `stage_06_robustness.md` | 2-3h | L1 + L2 | A 题多为物理/工程参数，B/C 题多为统计与政策参数 |
| 7 | 模型评价 + 推广 | `stage_07_evaluation.md` | 1-2h | L1 | 通用 |
| 8 | 论文写作 + 合规装配 | `stage_08_writing.md` | 12-30h | L1 + L2 | 当届规则、AI 披露、摘要类型与 LaTeX 模板 |
| 9 | 提交合规 + Panel | `stage_09_review.md` | 2-6h | L1 + L3 panel | 页数/匿名/披露 + anti-patterns + personas |

---

## 加载协议 (节省 token 的关键)

**只在进入阶段 N 时加载** `references/stage_NN_*.md`。**切勿**一次性全读。

各阶段额外加载 (按需 + 按 competition 切换):
- 每阶段开头: `<cwd>/state/decision_log.json` 必读。**先读 `resume` 段**——`in_flight` 说明上次停在哪、`next_actions` 是下一步、`settled_conventions` 是不许重新决定的口径
- 每阶段结尾: `<cwd>/state/decision_log.json` 必写 (核心决策 + 5 维评分 + **`resume` 段**)
- **`resume` 段每阶段结尾必更新**：72 小时赛期里上下文必然被压缩多次、大概率换会话，届时只有磁盘上的东西还在。恢复时最危险的不是忘了做什么，而是把某个口径换了个同样合理的定法——前后两问的数字就不可比了，且不会报错
- stage 1-9: `references/rubrics.md` 对应章节 (L1 评分用)
- **stage 1**: `competitions/cumcm/topic_specs.json`（题号清单 + 近五年**实际**题型 + task_type 权重键）。选定后必须写两个字段：`task_type`（题号，只供评分权重）与 **`problem_shape`（题型，从题面判定，五选一）**。**题号不是题型**——B 题最近四年零次评价类，照题号套 AHP/熵权/TOPSIS 正是组委会连续四年点名的套路化
- **stage 3**: 先按 `problem_shape` 去 `winning_patterns.md` §1 取对应题型的算法主线，再看 `model_catalog.md` 通用清单
- stage 5: `references/model_catalog.md` (通用模型清单)
- **stage 5**: per-Qi 评分跑完后调 `scripts/score_artifact.py --mode aggregate_qi` 聚合
- **stage 0 / 8 / 9**: `competitions/cumcm/current_rules.md` 存在时读取，并核对其中官方链接
- **stage 8**: `competitions/cumcm/{winning_patterns, phrase_bank, abstract_template, paper_skeleton}.md`
- **stage 8 经验锚点**: 用 `competitions/cumcm/empirical_abc.json`（按 题号×年份×来源 分层）；根目录那个 `empirical.json` 是上游 59 份混合样本的遗留物，只在分层数据某格样本量过小时作对照。两者都只是观察分位，**不得推断成数值门槛**
- **stage 5 / 8 出图**: `figures/cumcm_style.py`。**评委会打印**：这套色板灰度下有几对几乎同色（aqua↔magenta ΔL=0.017），所以第二通道（线型/填充网格/标记）是默认而非选项；`cs.save()` 会顺手出灰度校样，**必须翻一遍**
- **stage 6**: `scripts/check_selfaudit.py` 必跑——自检承诺写了没执行、"局限"其实是没做完的活，是本 skill 演练里重复次数最多的两类失分，靠读文档挡不住
- **stage 9**: 先做规则合规门（`scripts/check_compliance.py`，退出码非零不得提交），再跑 `check_numbers.py` 与 `check_selfaudit.py`，最后用 `anti_patterns.md` 与 `rubric_overlay.json` 的 panel personas
- 触发反馈时: 对应 `references/feedback_layer*.md`
- harness 适配差异 (Codex 用户必读): `references/harness_compat.md`

---

## 收敛准则 (统一定义, 三处一致)

**verdict 优先级 (从高到低)**:

| verdict | 触发 | 行为 |
|---------|------|------|
| `block` | issues 含 ≥1 high-severity | 暂停 skill, 用户介入 |
| `pass_early` | raw_min ≥ 9 AND weighted_mean ≥ 9 | iter-1 早退 |
| `pass` | raw_min ≥ 7 AND weighted_mean ≥ 8 | 进下一阶段 |
| `pass_with_review` *(stage 5)* | 任 Qi mark_for_review 但加权阈值满足 | 进 stage 6, L2 必读 review_qis |
| `refine` | 其他 | section-patch 精修, iter+=1 (cap 3) |
| `refine_partial` *(stage 5)* | 任 Qi.min < 7, 其他 Qi 已 pass | 仅 refine 该 Qi, 不动其他 |
| `carryover` | iter == 3 仍 refine | 进下一阶段, 标记由 L2 处理 |

`weighted_mean` = Σ(s_i × w_i) / Σ(w_i), 权重来自 `config/dim_weights.json[<comp>][<task_type>]` (clamp [0.7, 1.5]); `task_type=default` 全 1.0 等价老逻辑。

此定义在 `feedback_layer1_critic.md` / `rubrics.md` / `scripts/score_artifact.py` 三处必须**完全一致**。

---

## 状态持久化

每阶段:
- 开头: 读取 `<cwd>/state/decision_log.json`, 核对 current_stage 与上下文
- 结尾: 更新 stage 节点 (核心决策 + 摒弃方案 + 评分), `current_stage += 1`

`decision_log.json` v3.1 schema 关键字段 (与 `templates/shared/decision_log.json` 对齐):
- root: `competition`, `task_type`, `mode`, `current_stage`, `budget`, `events`, `compliance`
- stage_5 扩展: `qi_count`, `qi_weights`, `qi_status`
- scores 扩展: 含 `weighted_mean`, `review_qis`, `refine_qis` (stage 5 加权聚合用)

L2 跨阶段回检 (stage 5/6/8 末尾) 读这个文件主动找冲突, 触发**定向回滚**: 不重做整阶段, 只针对冲突点。

---

## 上下文预算纪律

- L1 Critic 强制 JSON 输出, ~500 token/次
- 精修策略: section-level patch (`scripts/extract_diff.py`), 优先只传相关 section
- references/ 与 competitions/ 文件**懒加载**, 本 SKILL.md 主体 ≤ 6k tokens
- 阶段完成后, artifact 摘要 + 关键数据 + 路径写入 decision_log, 不在上下文保留全文
- 只有当前 harness / API 提供可靠 usage 时才记录 token 消耗；不可观测时保留为 `null`，不得估算成已用额度
- 上下文压力或剩余时间不足时，向用户建议从 championship → standard → fast 降级，并把确认后的 mode change 写入 events；不要声称已自动计量或静默切换

---

## 用户指令快捷

- "进入 stage N" / "重做 stage N" → 跳转
- "切到 A 题 / B 题 / C 题" → 改 decision_log.problem_meta.letter 与 task_type（本 fork 无其他竞赛可切）
- "升级到 championship" → 启用 L3 + L4 + red-team
- "切到 fast" → 关闭迭代
- "回退到 stage M" → 读 decision_log, 回退 current_stage 并清理 ≥M 节点
- "做 L2 回检" → 立即触发 cross-stage backtrack
- "看进度" → 输出 decision_log 摘要 + 当前评分

---

## 数据来源声明

- `competitions/cumcm/`: 18 份官方讲评全文（42.4 万字，OCR）+ 112 篇 ABC 论文（44 篇官方展示 + 68 篇社区，2020–2025）进入观察分位；OCR 的散文可信、**复杂公式有识别错误**，分位数不能解释为官方阈值或获奖预测
- 通用模型清单 `references/model_catalog.md` 与题型无关，可跨题号复用

当前 `scripts/ingest_papers.py` 是维护期归档工具，不能直接重建 `empirical_abc.json`。新增语料前先补来源 provenance、提取 QA 与分组样本量。

---

## 与外部资源的关系

核心工作流可离线运行；当届规则与问题要求必须从官方来源重新核对。下列资源可作人工补充:
- `personqianduixue/Math_Model`, `datawhalechina/intro-mathmodel`
- `dxs.moe.gov.cn` 优秀论文展廊（官方展示论文与讲评的来源）
- 当届赛题与规则：`mcm.edu.cn`
