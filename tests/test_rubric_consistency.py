#!/usr/bin/env python3
"""rubric 单一数据源的守卫测试。

重构前：同一份 rubric 散在**四个地方**，没有任何一致性检查

| 位置 | 是什么 |
|---|---|
| `scripts/score_artifact.py: DIM_WHITELIST` | 硬编码白名单，Critic 的键不在里面就 FAIL |
| `references/rubrics.md` | 声明为 canonical 的人读表格 |
| `references/stage_0N_*.md` | 每个 stage 文件里的平行副本（agent 运行时真正读的） |
| `config/dim_weights.json` | 按题型加权，键必须在白名单里 |

实测漂移（逐份抽出来比对的结果）：

- stage 1 / 3 / 6 / 7 的维度**名称两边完全不同**——「命名准确性」vs
  「模型命名真实性」、「局限真实」vs「缺点真实」。**键相同，所以既有的每一项
  检查都查不出来**：Critic 照 stage 文件打分，评的却是和 canonical 表描述不同的东西；
- stage 5 的 stage-level 五维、stage 9 的五维在 `rubrics.md` 里**干脆没有表**，
  白名单有键、没有满分行为，Critic 只能自己编判据。

重构后：`config/rubric.json` 是唯一数据源，md 表格由 `scripts/render_rubric.py`
生成，`DIM_WHITELIST` 也从同一份 JSON 加载。本文件盯三件事：

1. **生成物没有漂移**（`--check` 零漂移）；
2. **漂移检测器不是空转**——故意改一个字，`--check` 必须报出来。
   一个检测不出漂移的检测器比没有更坏：它让人以为覆盖面在；
3. 白名单形状、加权键有效性、模板槽位齐全。
"""

from __future__ import annotations

import copy
import importlib.util
import json
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

EXPECTED_DIMS_PER_STAGE = 5
RUBRIC_JSON = ROOT / "config" / "rubric.json"


def load_script(name: str):
    path = ROOT / "scripts" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(f"rubric_test_{name}", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


score_artifact = load_script("score_artifact")
render_rubric = load_script("render_rubric")
WHITELIST = score_artifact.DIM_WHITELIST
RUBRIC = json.loads(RUBRIC_JSON.read_text(encoding="utf-8"))

STAGE_FILES = {
    0: "stage_00_kickoff.md", 1: "stage_01_problem_selection.md",
    2: "stage_02_analysis.md", 3: "stage_03_model_selection.md",
    4: "stage_04_foundation.md", 5: "stage_05_subproblem_loop.md",
    6: "stage_06_robustness.md", 7: "stage_07_evaluation.md",
    8: "stage_08_writing.md", 9: "stage_09_review.md",
}

# 生成出来的行长这样：`| 3. 命名准确性 (\`3_naming_variant\`) | ... |`
GEN_ROW = re.compile(r"^\|\s*(\d+)\.\s*(.+?)\s*\(`([^`]+)`\)\s*\|")


class DriftTest(unittest.TestCase):
    """md 里的表格必须与 JSON 完全一致，且检测器必须真能检出不一致。"""

    def test_no_drift(self):
        drift, msgs = render_rubric.process(write=False, show_diff=True)
        self.assertEqual(drift, 0, "\n".join(msgs))

    def test_every_target_file_exists_and_has_markers(self):
        for rel, key in render_rubric.TARGETS:
            path = ROOT / rel
            self.assertTrue(path.is_file(), rel)
            text = path.read_text(encoding="utf-8")
            self.assertIn(render_rubric.BEGIN % key, text, "%s %s" % (rel, key))
            self.assertIn(render_rubric.END % key, text, "%s %s" % (rel, key))

    def test_detector_is_not_vacuous(self):
        """**这条最重要。** 故意改一个字，`--check` 必须报出来。

        一个检测不出漂移的检测器比没有检测器更坏——它让人以为覆盖面在。
        改完立刻还原，不留副作用。
        """
        target = ROOT / render_rubric.TARGETS[0][0]
        original = target.read_text(encoding="utf-8")
        key = render_rubric.TARGETS[0][1]
        part = render_rubric._split(original, key)
        self.assertIsNotNone(part)
        head, body, tail = part
        try:
            target.write_text(head + body.replace("|", "|X", 1) + tail,
                              encoding="utf-8")
            drift, _ = render_rubric.process(write=False, show_diff=False)
            self.assertGreaterEqual(drift, 1, "改了一个字却没报漂移")
        finally:
            target.write_text(original, encoding="utf-8")
        drift, msgs = render_rubric.process(write=False, show_diff=False)
        self.assertEqual(drift, 0, "还原后应当无漂移：%s" % msgs)

    def test_write_is_idempotent(self):
        """`--write` 跑两遍不该产生第二次改动，否则 doctor 会反复报漂移。"""
        before = {ROOT / rel: (ROOT / rel).read_text(encoding="utf-8")
                  for rel, _ in render_rubric.TARGETS}
        try:
            drift, _ = render_rubric.process(write=True, show_diff=False)
            self.assertEqual(drift, 0, "本来就该是一致状态")
            after = {p: p.read_text(encoding="utf-8") for p in before}
            self.assertEqual(after, before, "--write 改动了本已一致的文件")
        finally:
            for p, t in before.items():
                if p.read_text(encoding="utf-8") != t:
                    p.write_text(t, encoding="utf-8")


class SingleSourceTest(unittest.TestCase):
    """`DIM_WHITELIST` 必须来自 JSON，而不是另一份硬编码副本。"""

    def test_whitelist_matches_json(self):
        self.assertEqual(WHITELIST, render_rubric.whitelist(RUBRIC))

    def test_score_artifact_no_longer_hardcodes_keys(self):
        """源码里不该再出现成套的硬编码维度键——那是第二份真相的来源。"""
        src = (ROOT / "scripts" / "score_artifact.py").read_text(
            encoding="utf-8")
        for key in ("1_role_clarity", "4_data_alignment", "5_time_budget"):
            self.assertNotIn('"%s"' % key, src,
                             "score_artifact.py 里仍硬编码 %r，"
                             "会和 config/rubric.json 形成第二份真相" % key)

    def test_missing_json_raises_instead_of_silent_fallback(self):
        """加载失败必须抛异常。**静默回落到过期副本会让键校验毫无意义。**"""
        fn = score_artifact._load_dim_whitelist_from_json
        original = score_artifact._SKILL_ROOT
        try:
            score_artifact._SKILL_ROOT = ROOT / "no_such_dir"
            with self.assertRaises(Exception):
                fn()
        finally:
            score_artifact._SKILL_ROOT = original


class WhitelistShapeTest(unittest.TestCase):
    def test_every_stage_has_exactly_five_dims(self):
        self.assertEqual(RUBRIC["dims_per_stage"], EXPECTED_DIMS_PER_STAGE)
        for key, dims in WHITELIST.items():
            self.assertEqual(len(dims), EXPECTED_DIMS_PER_STAGE,
                             "%s: %s" % (key, sorted(dims)))

    def test_dim_keys_are_numbered_one_to_five(self):
        for key, dims in WHITELIST.items():
            nums = sorted(int(d.split("_", 1)[0]) for d in dims)
            self.assertEqual(nums, [1, 2, 3, 4, 5], "%s: %s" % (key, sorted(dims)))

    def test_all_ten_stages_plus_per_qi_present(self):
        for stage in range(10):
            self.assertIn(stage, WHITELIST, "缺 stage %d" % stage)
        self.assertIn("5_per_qi", WHITELIST)

    def test_no_empty_or_placeholder_text(self):
        """名称和满分行为的长度下限**必须分开定**。

        第一版对两者都用 `len < 4`，把「依赖链」这个完全正当的三字名报成占位符
        ——判据写错了，不是数据错。名称短是常态（中文三个字就够），
        满分行为短才是问题（它要写清"什么样算满分"）。
        """
        limits = {"name": 2, "full_marks": 6}
        bad = []
        for key, node in RUBRIC["stages"].items():
            for d in node["dims"]:
                for field, floor in limits.items():
                    val = (d.get(field) or "").strip()
                    if not val or val.upper().startswith("TODO") \
                            or len(val) < floor:
                        bad.append("stage %s / %s / %s = %r（下限 %d 字）"
                                   % (key, d["key"], field, val, floor))
        self.assertEqual(bad, [], "\n".join(bad))

    def test_dim_keys_unique_within_stage(self):
        for key, node in RUBRIC["stages"].items():
            keys = [d["key"] for d in node["dims"]]
            self.assertEqual(len(keys), len(set(keys)), key)


class RenderTest(unittest.TestCase):
    def test_fail_marks_produces_third_column(self):
        """stage 0 原表是三列（多一列「失败行为 (1)」）。

        重构时抽取正则把第三列并进了 `full_marks`，第一次生成出来的表
        表头两列、行三列。**这一列是独有信息**，所以做成可选字段 `fail_marks`，
        任一维有它就出三列。这条盯住那次回归。
        """
        table = render_rubric.render(RUBRIC, "0")
        self.assertIn("失败行为 (1)", table.splitlines()[0])
        for line in table.splitlines()[2:]:
            self.assertEqual(line.count(" | "), 2, line)

    def test_two_column_when_no_fail_marks(self):
        table = render_rubric.render(RUBRIC, "3")
        self.assertEqual(table.splitlines()[0], "| 维度 | 满分行为 |")
        for line in table.splitlines()[2:]:
            self.assertEqual(line.count(" | "), 1, line)

    def test_pipe_in_cell_is_escaped(self):
        r"""单元格里的裸 `|` 会把 markdown 表格撑出多余一列。

        stage 8 第 3 维就叫「公式 / 图表 / 引用」，将来若改成 `公式|图表`
        就会命中；先把转义测住。
        """
        data = copy.deepcopy(RUBRIC)
        data["stages"]["3"]["dims"][0]["name"] = "a|b"
        line = [ln for ln in render_rubric.render(data, "3").splitlines()
                if "a" in ln and "`1_" in ln][0]
        self.assertIn(r"a\|b", line)
        self.assertEqual(line.count(" | "), 1)

    def test_render_rejects_wrong_dim_count(self):
        data = copy.deepcopy(RUBRIC)
        data["stages"]["3"]["dims"].append(
            {"key": "6_extra", "name": "x", "full_marks": "y"})
        with self.assertRaises(SystemExit):
            render_rubric.render(data, "3")

    def test_render_rejects_misnumbered_key(self):
        data = copy.deepcopy(RUBRIC)
        data["stages"]["3"]["dims"][2]["key"] = "9_wrong"
        with self.assertRaises(SystemExit):
            render_rubric.render(data, "3")


class NameConsistencyTest(unittest.TestCase):
    """**同一维度在所有副本里名称必须一致。** 这是重构要杀掉的那个 bug。"""

    def _rows(self, rel: str, key: str) -> list[tuple[int, str, str]]:
        text = (ROOT / rel).read_text(encoding="utf-8")
        part = render_rubric._split(text, key)
        self.assertIsNotNone(part, "%s 缺 %s 的 marker" % (rel, key))
        return [(int(m.group(1)), m.group(2), m.group(3))
                for m in (GEN_ROW.match(ln.strip())
                          for ln in part[1].splitlines()) if m]

    def test_same_dim_same_name_everywhere(self):
        seen: dict[tuple[str, str], set[str]] = {}
        for rel, key in render_rubric.TARGETS:
            for _, name, dim_key in self._rows(rel, key):
                seen.setdefault((key, dim_key), set()).add(name)
        conflicts = {k: v for k, v in seen.items() if len(v) > 1}
        self.assertEqual(conflicts, {}, "同一维度出现了不同名称：%s" % conflicts)

    def test_every_row_carries_its_dim_key(self):
        """表里带 `` `key` `` 是有意的：Critic 输出的是英文键，
        人读的是中文名。**两者印在同一行**，才不会再出现"名字对不上键"。"""
        for rel, key in render_rubric.TARGETS:
            rows = self._rows(rel, key)
            self.assertEqual(len(rows), EXPECTED_DIMS_PER_STAGE,
                             "%s [%s]" % (rel, key))
            self.assertEqual([r[2] for r in rows],
                             [d["key"] for d in RUBRIC["stages"][key]["dims"]])

    def test_stage2_data_alignment_covers_preprocessing_decision(self):
        dim = [d for d in RUBRIC["stages"]["2"]["dims"]
               if d["key"] == "4_data_alignment"][0]
        self.assertIn("preprocessing_decisions", dim["full_marks"],
                      "预处理决策折进了 4_data_alignment，判据必须写在它的满分行为里"
                      "——折进去而没写判据 = 没折")


class DimWeightsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.weights = json.loads(
            (ROOT / "config" / "dim_weights.json").read_text(encoding="utf-8"))

    def _iter(self):
        for comp, variants in self.weights.items():
            if comp.startswith("_"):
                continue
            for task_type, stages in variants.items():
                if task_type.startswith("_") or not isinstance(stages, dict):
                    continue
                for stage_id, dims in stages.items():
                    if stage_id.startswith("_") or not isinstance(dims, dict):
                        continue
                    for dim, w in dims.items():
                        if dim.startswith("_"):
                            continue
                        yield comp, task_type, stage_id, dim, w

    def test_weight_keys_exist_in_whitelist(self):
        bad = []
        for comp, tt, stage_id, dim, _ in self._iter():
            key = int(stage_id) if stage_id.isdigit() else stage_id
            if dim not in WHITELIST.get(key, set()):
                bad.append("%s/%s/stage %s: %r 不在白名单里"
                           % (comp, tt, stage_id, dim))
        self.assertEqual(bad, [], "\n".join(
            ["dim_weights.json 里这些键无效（权重会静默不生效）："] + bad))

    def test_weights_within_documented_clamp(self):
        lo = self.weights["_clamp"]["min"]
        hi = self.weights["_clamp"]["max"]
        for comp, tt, stage_id, dim, w in self._iter():
            self.assertTrue(lo <= w <= hi,
                            "%s/%s/%s/%s = %s 超出 [%s, %s]，"
                            "会被 clamp 掉，写的值不是生效的值"
                            % (comp, tt, stage_id, dim, w, lo, hi))


class DecisionLogSlotTest(unittest.TestCase):
    """文档让写的字段，模板里必须有槽。

    没有槽的后果：agent 要么现造键，要么干脆忘了写——而"忘了写"和
    "这题不需要写"在状态文件里长得一模一样。这条抓出过
    `stage.8.ai_use_log`：全仓只出现在一处 frontmatter，模板没槽、没人读。
    """

    @classmethod
    def setUpClass(cls):
        cls.log = json.loads(
            (ROOT / "templates" / "shared" / "decision_log.json")
            .read_text(encoding="utf-8"))

    def test_documented_stage_outputs_have_template_slots(self):
        missing = []
        for stage, fname in STAGE_FILES.items():
            path = ROOT / "references" / fname
            if not path.exists():
                continue
            fm = path.read_text(encoding="utf-8").split("---", 2)
            if len(fm) < 3:
                continue
            for m in re.finditer(r"stage\.%d\.\{([^}]*)\}" % stage, fm[1]):
                slot = self.log["stages"].get(str(stage), {})
                for field in m.group(1).split(","):
                    field = field.strip()
                    if not field or field.startswith("_"):
                        continue
                    if field not in slot:
                        missing.append(
                            "%s 声明产出 stage.%d.%s，但 decision_log 模板里没这个槽"
                            % (fname, stage, field))
        self.assertEqual(missing, [], "\n".join(missing))

    def test_stage2_has_preprocessing_decisions_slot(self):
        self.assertIn("preprocessing_decisions", self.log["stages"]["2"])


if __name__ == "__main__":
    unittest.main()
