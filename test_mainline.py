"""Frozen-stage behavior tests; artifacts remain in .test-runs."""

from contextlib import contextmanager
import json
import copy
import os
from pathlib import Path
import signal
import subprocess
import sys
import threading
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, build_opener, ProxyHandler
import uuid
import warnings

import mainline

ROOT = Path(__file__).resolve().parent / ".test-runs" / uuid.uuid4().hex
urlopen = build_opener(ProxyHandler({})).open


@contextmanager
def running(path):
    server = mainline.make_server(path)
    thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def get(url):
    with urlopen(url, timeout=2) as response:
        return json.load(response), response.headers


class MainlineTests(unittest.TestCase):
    def setUp(self):
        self.directory = ROOT / self._testMethodName / "中文任务"
        self.path = self.directory / "state.json"
        self.stages = ["确定方案", "实现", "验收"]
        self.state = mainline.init_state(self.path, "测试任务", self.stages)

    def legacy(self):
        state = {
            "task_id": "原任务", "mainline": "旧目标", "completion_criterion": "旧标准",
            "current_action": "旧动作", "next_action": "旧下一步", "verified_results": [],
            "updated_at": "2026-09-12T01:02:03+00:00", "revision": 8, "timeline": [],
        }
        mainline.atomic_json(self.path, state)
        return self.path.read_bytes()

    def test_init_freezes_stages_and_refuses_overwrite(self):
        self.assertEqual(self.state["stages"], self.stages)
        self.assertEqual(self.state["stage_statuses"], ["active", "pending", "pending"])
        self.assertEqual(set(self.state), mainline.STATE_FIELDS)
        original = self.path.read_bytes()
        with self.assertRaises(FileExistsError):
            mainline.init_state(self.path, "另一个任务", ["新阶段"])
        self.assertEqual(self.path.read_bytes(), original)

    def test_position_only_moves_pointer_and_noop_preserves_revision(self):
        original = self.path.read_bytes()
        self.assertEqual(mainline.position_state(self.path, "确定方案"), self.state)
        self.assertEqual(self.path.read_bytes(), original)
        advanced = mainline.position_state(self.path, "实现")
        self.assertEqual(advanced["stages"], self.stages)
        self.assertEqual(advanced["stage_statuses"], ["pending", "active", "pending"])
        self.assertEqual(advanced["revision"], 2)
        self.assertEqual(set(advanced), mainline.STATE_FIELDS)
        returned = mainline.position_state(self.path, "确定方案")
        self.assertEqual(returned["stages"], self.stages)
        self.assertEqual(returned["stage_statuses"], ["active", "pending", "pending"])

    def test_finish_requires_last_stage_and_return_cancels_completion(self):
        original = self.path.read_bytes()
        with self.assertRaises(ValueError):
            mainline.finish_state(self.path)
        self.assertEqual(self.path.read_bytes(), original)
        mainline.position_state(self.path, "验收")
        with self.assertRaises(ValueError):
            mainline.finish_state(self.path)
        mainline.status_state(self.path, done=["确定方案", "实现"])
        complete = mainline.finish_state(self.path)
        self.assertEqual(complete["stage_statuses"], ["done", "done", "done"])
        self.assertEqual(mainline.finish_state(self.path), complete)
        reopened = mainline.position_state(self.path, "实现")
        self.assertEqual(reopened["stage_statuses"], ["done", "active", "done"])
        self.assertEqual(reopened["stages"], self.stages)

    def test_bad_inputs_preserve_original(self):
        original = self.path.read_bytes()
        for stages in ([], [""], ["阶段", " 阶段 "], ["阶段", 5]):
            with self.subTest(stages=stages), self.assertRaises(ValueError):
                mainline.replan_state(self.path, stages, "阶段", "重大变化")
            self.assertEqual(self.path.read_bytes(), original)
        for name in ("未知阶段", " "):
            with self.assertRaises(ValueError):
                mainline.position_state(self.path, name)
            self.assertEqual(self.path.read_bytes(), original)

    def test_replan_requires_reason_and_changes_only_explicitly(self):
        original = self.path.read_bytes()
        with self.assertRaises(ValueError):
            mainline.replan_state(self.path, ["新阶段"], "新阶段", " ")
        self.assertEqual(self.path.read_bytes(), original)
        changed = mainline.replan_state(self.path, ["重定范围", "交付"], "重定范围", "需求范围发生重大变化")
        self.assertEqual(changed["stages"], ["重定范围", "交付"])
        self.assertEqual(changed["task_id"], self.state["task_id"])
        self.assertEqual(mainline.replan_state(self.path, changed["stages"], "重定范围", "确认计划"), changed)
        self.assertEqual(list(self.directory.glob("*.legacy-*.json")), [])

    def test_legacy_requires_explicit_replan_and_exact_backup(self):
        original = self.legacy()
        with self.assertRaisesRegex(ValueError, "replan"):
            mainline.read_state(self.path)
        self.assertEqual(self.path.read_bytes(), original)
        migrated = mainline.replan_state(self.path, ["方案", "实现", "验收"], "实现", "简化产品")
        backups = list(self.directory.glob("state.legacy-*.json"))
        self.assertEqual(len(backups), 1)
        self.assertEqual(backups[0].read_bytes(), original)
        self.assertEqual(migrated["task_id"], "原任务")
        self.assertEqual(migrated["revision"], 9)
        self.assertEqual(migrated["stage_statuses"], ["pending", "active", "pending"])
        self.assertEqual(set(migrated), mainline.STATE_FIELDS | {"mainline"})
        self.assertEqual(migrated["mainline"], "旧目标")

    def test_atomic_failure_preserves_plan_and_position(self):
        original = self.path.read_bytes()
        with patch.object(mainline.os, "replace", side_effect=OSError("测试故障")):
            with self.assertRaises(OSError):
                mainline.status_state(self.path, active=["实现", "验收"], done=["确定方案"])
        self.assertEqual(self.path.read_bytes(), original)

    def test_migration_failure_preserves_original_and_backup(self):
        original = self.legacy()
        with patch.object(mainline.os, "replace", side_effect=OSError("测试故障")):
            with self.assertRaises(OSError):
                mainline.replan_state(self.path, ["交付"], "交付", "重新规划")
        self.assertEqual(self.path.read_bytes(), original)
        backups = list(self.directory.glob("state.legacy-*.json"))
        self.assertEqual(len(backups), 1)
        self.assertEqual(backups[0].read_bytes(), original)

    def test_task_isolation(self):
        other = self.directory / "其他任务" / "state.json"
        mainline.init_state(other, "任务乙", ["准备", "完成"])
        original = other.read_bytes()
        with running(self.path) as a, running(other) as b:
            mainline.position_state(self.path, "实现")
            self.assertEqual(get(a + "/state")[0]["state"]["stage_statuses"], ["pending", "active", "pending"])
            self.assertEqual(get(b + "/state")[0]["state"]["stage_statuses"], ["active", "pending"])
        self.assertEqual(other.read_bytes(), original)

    def test_http_last_good_recovery_and_restart(self):
        with running(self.path) as url:
            initial, headers = get(url + "/state")
            self.assertEqual(headers["Cache-Control"], "no-store")
            self.path.write_text("{损坏", encoding="utf-8")
            bad, _ = get(url + "/state")
            self.assertEqual(bad["state"], initial["state"])
            self.assertTrue(bad["error"])
            mainline.atomic_json(self.path, self.state)
            restored = mainline.position_state(self.path, ["确定方案", "验收"])
            self.assertEqual(get(url + "/state")[0], {"state": restored, "error": None})
            mainline.atomic_json(self.path, dict(restored, task_id="其他任务"))
            rejected, _ = get(url + "/state")
            self.assertEqual(rejected["state"], restored)
            self.assertTrue(rejected["error"])
            mainline.atomic_json(self.path, restored)
        with running(self.path) as restarted:
            self.assertEqual(get(restarted + "/state")[0]["state"], restored)

    def test_http_fixed_routes_read_only_and_host_check(self):
        with running(self.path) as url:
            for route in ("/state.json", "/../mainline.py", "/unknown"):
                with self.assertRaises(HTTPError) as caught:
                    get(url + route)
                self.assertEqual(caught.exception.code, 404)
                self.assertEqual(caught.exception.headers["Cache-Control"], "no-store")
            with self.assertRaises(HTTPError) as caught:
                urlopen(Request(url + "/state", data=b"{}", method="POST"), timeout=2)
            self.assertEqual(caught.exception.code, 405)
            for headers in ({"Host": "other.test"}, {"Origin": "https://other.test"}):
                with self.assertRaises(HTTPError) as caught:
                    urlopen(Request(url + "/state", headers=headers), timeout=2)
                self.assertEqual(caught.exception.code, 403)

    def test_language_query_serves_the_same_read_only_view(self):
        original = self.path.read_bytes()
        with running(self.path) as url:
            for language in ("en", "zh", "unsupported"):
                with urlopen(url + "/?lang=" + language, timeout=2) as response:
                    self.assertEqual(response.status, 200)
                    self.assertIn("text/html", response.headers["Content-Type"])
                    self.assertIn(b"new URLSearchParams", response.read())
                self.assertEqual(get(url + "/state?lang=" + language)[0]["state"], self.state)
        self.assertEqual(self.path.read_bytes(), original)

    def test_local_service_does_not_require_name_resolution(self):
        with patch("socket.getfqdn", side_effect=AssertionError("Unexpected DNS lookup")):
            with running(self.path) as url:
                self.assertEqual(get(url + "/state")[0]["state"], self.state)

    def test_start_background_and_verified_reuse(self):
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", ResourceWarning)
            first = mainline.start(self.path)
        try:
            self.assertFalse(first["reused"])
            self.assertEqual(get(first["url"] + "/health")[0], {
                "task_id": "测试任务", "state_path": str(self.path),
            })
            second = mainline.start(self.path)
            self.assertTrue(second["reused"])
            self.assertEqual(first["pid"], second["pid"])
            self.assertIsNone(mainline.discover(self.path, "错误任务"))
        finally:
            identity = mainline.discover(self.path, "测试任务")
            if identity and identity["pid"] == first["pid"]:
                os.kill(first["pid"], signal.SIGTERM)

    def test_schema_rejects_unknown_fields_and_invalid_completion(self):
        for changes in ({"extra": True}, {"stage_statuses": ["active"]},
                        {"stage_statuses": ["active", "unknown", "done"]},
                        {"stage_statuses": "active"}, {"stages": ["A", "A"]}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                mainline.validate_state(dict(self.state, **changes))

    def test_cli_requires_explicit_replan_and_supports_stage_position(self):
        original = self.path.read_bytes()
        cli = [sys.executable, str(Path(mainline.__file__)), "replan", "--state", str(self.path),
               "--stage", "新阶段", "--current", "新阶段"]
        rejected = subprocess.run(cli, capture_output=True)
        self.assertNotEqual(rejected.returncode, 0)
        self.assertEqual(self.path.read_bytes(), original)
        moved = subprocess.run([sys.executable, str(Path(mainline.__file__)), "position",
                                "--state", str(self.path), "--current", "确定方案", "--current", "验收"], capture_output=True)
        self.assertEqual(moved.returncode, 0, moved.stderr.decode("utf-8"))
        self.assertEqual(json.loads(moved.stdout.decode("utf-8"))["stage_statuses"], ["active", "pending", "active"])

    def test_nonadjacent_active_stages_do_not_complete_middle(self):
        state = mainline.status_state(self.path, active=["确定方案", "验收"])
        self.assertEqual(state["stage_statuses"], ["active", "pending", "active"])
        self.assertEqual(state["stages"], self.stages)
        done = mainline.status_state(self.path, done="确定方案")
        self.assertEqual(done["stage_statuses"], ["done", "pending", "active"])
        reopened = mainline.status_state(self.path, active="确定方案")
        self.assertEqual(reopened["stage_statuses"], ["active", "pending", "active"])
        self.assertEqual(mainline.status_state(self.path, active="确定方案"), reopened)

    def test_position_replaces_only_activity_and_can_reopen_done(self):
        mainline.status_state(self.path, done="确定方案", active=["实现", "验收"])
        updated = mainline.position_state(self.path, ["确定方案", "验收"])
        self.assertEqual(updated["stage_statuses"], ["active", "pending", "active"])
        mainline.status_state(self.path, done="实现")
        shifted = mainline.position_state(self.path, "验收")
        self.assertEqual(shifted["stage_statuses"], ["pending", "done", "active"])

    def test_status_rejects_duplicates_conflicts_unknown_and_empty(self):
        original = self.path.read_bytes()
        for arguments in ({}, {"active": ["实现", "实现"]},
                          {"active": ["实现"], "done": ["实现"]},
                          {"done": ["不存在"]}):
            with self.subTest(arguments=arguments), self.assertRaises(ValueError):
                mainline.status_state(self.path, **arguments)
            self.assertEqual(self.path.read_bytes(), original)

    def test_pointer_migration_is_memory_only_and_preserves_mainline(self):
        pointer = {"task_id": "测试任务", "stages": self.stages, "current_stage": 1,
                   "completed": False, "updated_at": self.state["updated_at"],
                   "revision": 9, "mainline": "交付主线工具"}
        mainline.atomic_json(self.path, pointer)
        original = self.path.read_bytes()
        migrated = mainline.read_state(self.path)
        self.assertEqual(migrated["stage_statuses"], ["done", "active", "pending"])
        self.assertEqual(migrated["mainline"], pointer["mainline"])
        self.assertEqual(mainline.position_state(self.path, "实现"), migrated)
        self.assertEqual(self.path.read_bytes(), original)
        with running(self.path) as url:
            self.assertEqual(get(url + "/state")[0]["state"], migrated)
        updated = mainline.status_state(self.path, active="验收")
        self.assertEqual(updated["stage_statuses"], ["done", "active", "active"])
        self.assertEqual(updated["mainline"], pointer["mainline"])
        self.assertEqual(set(json.loads(self.path.read_text(encoding="utf-8"))), mainline.STATE_FIELDS | {"mainline"})
        complete = dict(pointer, current_stage=2, completed=True)
        self.assertEqual(mainline.validate_state(complete)["stage_statuses"], ["done"] * 3)

    def test_init_multiple_active_and_describe_preserve_all_statuses(self):
        path = self.directory / "多阶段.json"
        initial = mainline.init_state(path, "多阶段", self.stages, ["确定方案", "验收"], "项目主线")
        self.assertEqual(initial["stage_statuses"], ["active", "pending", "active"])
        described = mainline.describe_state(path, "澄清后的主线")
        self.assertEqual(described["stage_statuses"], initial["stage_statuses"])
        self.assertEqual(described["stages"], initial["stages"])
        self.assertEqual(described["mainline"], "澄清后的主线")
        replanned = mainline.replan_state(path, ["设计", "实现", "核验"], ["设计", "实现"], "范围改变")
        self.assertEqual(replanned["mainline"], described["mainline"])
        self.assertEqual(replanned["stage_statuses"], ["active", "active", "pending"])

    def test_cli_status_updates_specified_stages_only(self):
        command = [sys.executable, str(Path(mainline.__file__)), "status", "--state", str(self.path)]
        rejected = subprocess.run(command, capture_output=True)
        self.assertNotEqual(rejected.returncode, 0)
        changed = subprocess.run(command + ["--active", "实现", "--active", "验收", "--done", "确定方案"], capture_output=True)
        self.assertEqual(changed.returncode, 0, changed.stderr.decode("utf-8"))
        self.assertEqual(json.loads(changed.stdout.decode("utf-8"))["stage_statuses"], ["done", "active", "active"])


    def test_subdivide_defaults_follow_parent_status(self):
        mainline.status_state(self.path, done="验收")
        for parent, expected in (("确定方案", ["active", "pending"]),
                                 ("实现", ["pending", "pending"]),
                                 ("验收", ["done", "done"])):
            state = mainline.subdivide_state(self.path, parent, ["准备", "交付"])
            self.assertEqual(state["substages"][parent]["stage_statuses"], expected)
        self.assertEqual(state["stage_statuses"], ["active", "pending", "done"])
        self.assertEqual(state["stages"], self.stages)
        self.assertEqual(mainline.subdivide_state(self.path, "实现", ["准备", "交付"]), state)

    def test_substage_parallel_completion_and_reopening_roll_up(self):
        state = mainline.subdivide_state(self.path, "实现", ["数据", "接口", "页面"], ["数据", "页面"])
        self.assertEqual(state["stage_statuses"], ["active", "active", "pending"])
        self.assertEqual(state["substages"]["实现"]["stage_statuses"], ["active", "pending", "active"])
        state = mainline.status_state(self.path, parent="实现", done="数据")
        self.assertEqual(state["substages"]["实现"]["stage_statuses"], ["done", "pending", "active"])
        state = mainline.status_state(self.path, parent="实现", done="页面")
        self.assertEqual(state["stage_statuses"][1], "active")
        state = mainline.status_state(self.path, parent="实现", done="接口")
        self.assertEqual(state["stage_statuses"][1], "done")
        state = mainline.status_state(self.path, parent="实现", active="数据")
        self.assertEqual(state["stage_statuses"][1], "active")
        self.assertEqual(state["substages"]["实现"]["stage_statuses"], ["active", "done", "done"])
        state = mainline.status_state(self.path, parent="实现", pending=["数据", "接口", "页面"])
        self.assertEqual(state["stage_statuses"][1], "pending")

    def test_top_level_commands_cannot_override_substage_summary(self):
        state = mainline.subdivide_state(self.path, "确定方案", ["范围", "方案"])
        original = self.path.read_bytes()
        self.assertEqual(mainline.status_state(self.path, active="确定方案"), state)
        self.assertEqual(mainline.position_state(self.path, "确定方案"), state)
        for operation in (
                lambda: mainline.status_state(self.path, done="确定方案"),
                lambda: mainline.status_state(self.path, pending="确定方案"),
                lambda: mainline.position_state(self.path, "实现")):
            with self.assertRaisesRegex(ValueError, "derived"):
                operation()
            self.assertEqual(self.path.read_bytes(), original)
        mainline.status_state(self.path, parent="确定方案", done=["范围", "方案"])
        mainline.status_state(self.path, done="实现", active="验收")
        mainline.subdivide_state(self.path, "验收", ["测试", "确认"])
        with self.assertRaisesRegex(ValueError, "derived"):
            mainline.finish_state(self.path)
        finished = mainline.status_state(self.path, parent="验收", done=["测试", "确认"])
        self.assertEqual(mainline.finish_state(self.path), finished)

    def test_existing_subdivision_changes_require_reason(self):
        initial = mainline.subdivide_state(self.path, "实现", ["数据", "接口"], "数据")
        original = self.path.read_bytes()
        with self.assertRaisesRegex(ValueError, "reason"):
            mainline.subdivide_state(self.path, "实现", ["接口", "数据"])
        self.assertEqual(self.path.read_bytes(), original)
        same_structure = mainline.subdivide_state(self.path, "实现", ["数据", "接口"], "接口")
        self.assertEqual(same_structure["substages"]["实现"]["stage_statuses"], ["pending", "active"])
        changed = mainline.subdivide_state(self.path, "实现", ["服务", "页面"], reason="架构发生变化")
        self.assertEqual(changed["substages"]["实现"]["stages"], ["服务", "页面"])
        self.assertEqual(changed["stages"], initial["stages"])

    def test_replan_clears_substages_even_when_top_plan_matches(self):
        state = mainline.subdivide_state(self.path, "确定方案", ["范围", "方案"])
        replanned = mainline.replan_state(self.path, self.stages, "确定方案", "重大范围变更，重新规划")
        self.assertNotIn("substages", replanned)
        self.assertEqual(replanned["revision"], state["revision"] + 1)

    def test_invalid_substage_schema_and_depth_are_rejected(self):
        state = mainline.subdivide_state(self.path, "实现", ["数据", "接口"])
        for group in (
                {"stages": ["数据"], "stage_statuses": ["invalid"]},
                {"stages": ["数据"], "stage_statuses": []},
                {"stages": ["数据", "数据"], "stage_statuses": ["pending", "pending"]},
                {"stages": ["数据"], "stage_statuses": ["pending"], "substages": {}},
                {"stages": ["数据"], "stage_statuses": ["done"]}):
            candidate = copy.deepcopy(state)
            candidate["substages"]["实现"] = group
            with self.subTest(group=group), self.assertRaises(ValueError):
                mainline.validate_state(candidate)
        candidate = copy.deepcopy(state)
        candidate["substages"]["未知父阶段"] = candidate["substages"].pop("实现")
        with self.assertRaises(ValueError):
            mainline.validate_state(candidate)
        with self.assertRaisesRegex(ValueError, "has no substages"):
            mainline.status_state(self.path, parent="验收", active="数据")

    def test_substage_update_is_atomic_and_survives_restart(self):
        mainline.subdivide_state(self.path, "实现", ["数据", "接口"])
        original = self.path.read_bytes()
        with patch.object(mainline.os, "replace", side_effect=OSError("测试故障")):
            with self.assertRaises(OSError):
                mainline.status_state(self.path, parent="实现", active=["数据", "接口"])
        self.assertEqual(self.path.read_bytes(), original)
        with running(self.path) as url:
            state = mainline.status_state(self.path, parent="实现", active=["数据", "接口"])
            self.assertEqual(get(url + "/state")[0]["state"], state)
        with running(self.path) as restarted:
            self.assertEqual(get(restarted + "/state")[0]["state"], state)

    def test_cli_subdivide_and_scoped_status(self):
        command = [sys.executable, str(Path(mainline.__file__))]
        split = subprocess.run(command + ["subdivide", "--state", str(self.path),
            "--parent", "实现", "--stage", "数据", "--stage", "接口", "--current", "数据"], capture_output=True)
        self.assertEqual(split.returncode, 0, split.stderr.decode("utf-8"))
        result = subprocess.run(command + ["status", "--state", str(self.path), "--parent", "实现",
            "--done", "数据", "--active", "接口"], capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr.decode("utf-8"))
        state = json.loads(result.stdout.decode("utf-8"))
        self.assertEqual(state["substages"]["实现"]["stage_statuses"], ["done", "active"])
        self.assertEqual(state["stage_statuses"], ["active", "active", "pending"])


    def test_parallel_stage_labels_are_independent_and_explicit_updates_clear(self):
        first = mainline.status_state(self.path, active="确定方案", label="核对需求")
        self.assertEqual(first["stage_labels"], {"确定方案": "核对需求"})
        both = mainline.status_state(self.path, active="实现", label="修复错误")
        self.assertEqual(both["stage_labels"], {"确定方案": "核对需求", "实现": "修复错误"})
        self.assertEqual(mainline.status_state(self.path, active="实现", label="修复错误"), both)
        cleared = mainline.status_state(self.path, active="实现")
        self.assertEqual(cleared["stage_labels"], {"确定方案": "核对需求"})
        completed = mainline.status_state(self.path, done="确定方案")
        self.assertNotIn("stage_labels", completed)
        reopened = mainline.status_state(self.path, active="确定方案")
        self.assertNotIn("stage_labels", reopened)

    def test_position_and_finish_do_not_reuse_stale_labels(self):
        mainline.status_state(self.path, active="确定方案", label="核对需求")
        mainline.status_state(self.path, active="实现", label="修复错误")
        moved = mainline.position_state(self.path, "实现")
        self.assertEqual(moved["stage_labels"], {"实现": "修复错误"})
        self.assertEqual(mainline.position_state(self.path, "实现"), moved)
        returned = mainline.position_state(self.path, "确定方案")
        self.assertNotIn("stage_labels", returned)
        mainline.status_state(self.path, done=["确定方案", "实现"], active="验收", label="验证修复")
        finished = mainline.finish_state(self.path)
        self.assertNotIn("stage_labels", finished)
        self.assertNotIn("stage_labels", mainline.position_state(self.path, "验收"))

    def test_child_labels_roll_up_only_when_all_active_labels_match(self):
        mainline.subdivide_state(self.path, "实现", ["数据", "接口"], ["数据", "接口"])
        missing = mainline.status_state(self.path, parent="实现", active="数据", label="修复错误")
        self.assertNotIn("实现", missing.get("stage_labels", {}))
        matching = mainline.status_state(self.path, parent="实现", active="接口", label="修复错误")
        self.assertEqual(matching["stage_labels"]["实现"], "修复错误")
        self.assertEqual(mainline.status_state(self.path, active="实现"), matching)
        conflict = mainline.status_state(self.path, parent="实现", active="接口", label="核对接口")
        self.assertNotIn("实现", conflict.get("stage_labels", {}))
        one_left = mainline.status_state(self.path, parent="实现", done="接口")
        self.assertEqual(one_left["stage_labels"]["实现"], "修复错误")
        self.assertEqual(one_left["substages"]["实现"]["stage_labels"], {"数据": "修复错误"})
        completed = mainline.status_state(self.path, parent="实现", done="数据")
        self.assertNotIn("stage_labels", completed)
        self.assertNotIn("stage_labels", completed["substages"]["实现"])
        reopened = mainline.status_state(self.path, parent="实现", active="数据")
        self.assertNotIn("stage_labels", reopened)
        mainline.status_state(self.path, parent="实现", active="数据", label="修复错误")
        pending = mainline.status_state(self.path, parent="实现", pending=["数据", "接口"])
        self.assertEqual(pending["stage_statuses"][1], "pending")
        self.assertNotIn("stage_labels", pending)
        self.assertNotIn("stage_labels", pending["substages"]["实现"])

    def test_subdivide_and_replan_clear_old_parent_labels(self):
        mainline.status_state(self.path, active="确定方案", label="核对需求")
        split = mainline.subdivide_state(self.path, "确定方案", ["范围", "方案"])
        self.assertNotIn("stage_labels", split)
        with self.assertRaisesRegex(ValueError, "Parent labels"):
            mainline.status_state(self.path, active="确定方案", label="直接覆盖")
        mainline.status_state(self.path, parent="确定方案", active="范围", label="核对需求")
        moved = mainline.subdivide_state(self.path, "确定方案", ["范围", "方案"], "方案")
        self.assertNotIn("stage_labels", moved)
        self.assertNotIn("stage_labels", moved["substages"]["确定方案"])
        replanned = mainline.replan_state(self.path, self.stages, "确定方案", "重大变化")
        self.assertNotIn("substages", replanned)
        mainline.status_state(self.path, active="确定方案", label="核对需求")
        same_plan = mainline.replan_state(self.path, self.stages, "确定方案", "重新开始")
        self.assertNotIn("stage_labels", same_plan)

    def test_invalid_labels_and_ambiguous_targets_preserve_original(self):
        original = self.path.read_bytes()
        for changes in ({"active": "实现", "label": " "}, {"active": "实现", "label": "字" * 13},
                        {"active": "实现", "label": "修复\n错误"},
                        {"active": ["实现", "验收"], "label": "修复错误"},
                        {"done": "确定方案", "label": "修复错误"}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                mainline.status_state(self.path, **changes)
            self.assertEqual(self.path.read_bytes(), original)
        for labels in ({"不存在": "修复错误"}, {"实现": "修复错误"},
                       {"确定方案": {"深层": "修复错误"}}, []):
            with self.subTest(labels=labels), self.assertRaises(ValueError):
                mainline.validate_state(dict(self.state, stage_labels=labels))
        split = mainline.subdivide_state(self.path, "实现", ["数据", "接口"], "数据")
        invalid = copy.deepcopy(split)
        invalid["stage_labels"] = {"实现": "未汇总的标签"}
        with self.assertRaises(ValueError):
            mainline.validate_state(invalid)

    def test_label_updates_and_parent_summary_are_atomic(self):
        mainline.subdivide_state(self.path, "实现", ["数据", "接口"], "数据")
        original = self.path.read_bytes()
        with patch.object(mainline.os, "replace", side_effect=OSError("测试故障")):
            with self.assertRaises(OSError):
                mainline.status_state(self.path, parent="实现", active="数据", label="修复错误")
        self.assertEqual(self.path.read_bytes(), original)
        state = mainline.status_state(self.path, parent="实现", active="数据", label="修复错误")
        with running(self.path) as url:
            self.assertEqual(get(url + "/state")[0]["state"], state)

    def test_cli_label_can_accompany_other_completed_stage(self):
        command = [sys.executable, str(Path(mainline.__file__)), "status", "--state", str(self.path),
                   "--active", "实现", "--done", "确定方案", "--label", "修复错误"]
        result = subprocess.run(command, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr.decode("utf-8"))
        state = json.loads(result.stdout.decode("utf-8"))
        self.assertEqual(state["stage_statuses"], ["done", "active", "pending"])
        self.assertEqual(state["stage_labels"], {"实现": "修复错误"})



    def test_stage_description_preserves_progress_labels_and_is_idempotent(self):
        mainline.describe_state(self.path, "项目主线")
        before = mainline.status_state(self.path, active="实现", label="修复错误")
        described = mainline.describe_state(self.path, "  完成稳定可用的实现。  ", stage=" 实现 ")
        expected = dict(before, stage_mainlines={"实现": "完成稳定可用的实现。"},
                        revision=described["revision"], updated_at=described["updated_at"])
        self.assertEqual(described, expected)
        self.assertEqual(described["revision"], before["revision"] + 1)
        original = self.path.read_bytes()
        self.assertEqual(mainline.describe_state(self.path, "完成稳定可用的实现。", stage="实现"), described)
        self.assertEqual(self.path.read_bytes(), original)
        # Descriptions apply to pending/done stages too, not just active ones.
        long_mainline = "验证" * 100 + "全部目标。"
        other = mainline.describe_state(self.path, long_mainline, stage="验收")
        self.assertEqual(other["stage_mainlines"]["实现"], described["stage_mainlines"]["实现"])
        self.assertEqual(other["stage_mainlines"]["验收"], long_mainline)

    def test_same_named_child_descriptions_do_not_cross_parent_boundaries(self):
        for parent in ("实现", "验收"):
            mainline.subdivide_state(self.path, parent, ["检查", "交付"], "检查")
        mainline.describe_state(self.path, "完成实现。", stage="实现")
        mainline.describe_state(self.path, "检查接口约定。", stage="检查", parent="实现")
        mainline.status_state(self.path, parent="验收", active="检查", label="核对结果")
        before = mainline.read_state(self.path)
        changed = mainline.describe_state(self.path, "检查验收结果。", stage="检查", parent="验收")
        expected = copy.deepcopy(before)
        expected["substages"]["验收"]["stage_mainlines"] = {"检查": "检查验收结果。"}
        expected.update(revision=changed["revision"], updated_at=changed["updated_at"])
        self.assertEqual(changed, expected)
        self.assertEqual(changed["substages"]["实现"]["stage_mainlines"], {"检查": "检查接口约定。"})
        renamed = mainline.describe_state(self.path, "项目整体目标。")
        self.assertEqual(renamed["substages"], changed["substages"])
        self.assertEqual(renamed["stage_mainlines"], changed["stage_mainlines"])

    def test_progress_updates_preserve_stage_descriptions(self):
        mainline.describe_state(self.path, "完成稳定实现。", stage="实现")
        mainline.status_state(self.path, active="实现")
        mainline.position_state(self.path, "验收")
        mainline.status_state(self.path, done=["确定方案", "实现"])
        finished = mainline.finish_state(self.path)
        self.assertEqual(finished["stage_mainlines"], {"实现": "完成稳定实现。"})
        mainline.subdivide_state(self.path, "实现", ["数据", "接口"], "数据")
        mainline.describe_state(self.path, "验证数据契约。", stage="数据", parent="实现")
        mainline.status_state(self.path, parent="实现", active="数据", label="核对数据")
        mainline.status_state(self.path, parent="实现", done="数据", active="接口")
        same = mainline.subdivide_state(self.path, "实现", ["数据", "接口"], "数据")
        self.assertEqual(same["substages"]["实现"]["stage_mainlines"], {"数据": "验证数据契约。"})
        self.assertEqual(same["stage_mainlines"], {"实现": "完成稳定实现。"})
        self.assertEqual(mainline.subdivide_state(self.path, "实现", ["数据", "接口"]), same)

    def test_redivision_and_replan_clear_only_obsolete_stage_descriptions(self):
        mainline.describe_state(self.path, "项目主线")
        mainline.describe_state(self.path, "实现目标。", stage="实现")
        for parent in ("实现", "验收"):
            mainline.subdivide_state(self.path, parent, ["检查", "交付"])
            mainline.describe_state(self.path, "对应范围的检查目标。", stage="检查", parent=parent)
        changed = mainline.subdivide_state(self.path, "实现", ["检查", "发布"], reason="交付方式变化")
        self.assertNotIn("stage_mainlines", changed["substages"]["实现"])
        self.assertIn("stage_mainlines", changed["substages"]["验收"])
        self.assertEqual(changed["stage_mainlines"], {"实现": "实现目标。"})
        replanned = mainline.replan_state(self.path, self.stages, "确定方案", "范围变化")
        self.assertNotIn("stage_mainlines", replanned)
        self.assertNotIn("substages", replanned)
        self.assertEqual(replanned["mainline"], "项目主线")
        described = mainline.describe_state(self.path, "重新确认范围。", stage="确定方案")
        same_plan = mainline.replan_state(self.path, self.stages, "确定方案", "明确重新规划")
        self.assertNotIn("stage_mainlines", same_plan)
        self.assertEqual(same_plan["revision"], described["revision"] + 1)

    def test_invalid_stage_descriptions_preserve_file_and_reject_extra_depth(self):
        self.assertNotIn("stage_mainlines", mainline.read_state(self.path))
        original = self.path.read_bytes()
        for text, arguments in ((" ", {"stage": "实现"}),
                                ("第一行\n第二行", {"stage": "实现"}),
                                ("第一行\u2028第二行", {"stage": "实现"}),
                                ("目标。", {"parent": "实现"}),
                                ("目标。", {"stage": "未知阶段"}),
                                ("目标。", {"stage": "检查", "parent": "实现"})):
            with self.subTest(text=text, arguments=arguments), self.assertRaises(ValueError):
                mainline.describe_state(self.path, text, **arguments)
            self.assertEqual(self.path.read_bytes(), original)
        for mapping in ([], {"未知阶段": "目标。"}, {"实现": ""},
                        {"实现": "第一行\n第二行"}, {"实现": {"更深一层": "目标。"}}):
            with self.subTest(mapping=mapping), self.assertRaises(ValueError):
                mainline.validate_state(dict(self.state, stage_mainlines=mapping))
        split = mainline.subdivide_state(self.path, "实现", ["数据", "接口"])
        for mapping in ({"未知子阶段": "目标。"}, {"数据": {"更深一层": "目标。"}}):
            invalid = copy.deepcopy(split)
            invalid["substages"]["实现"]["stage_mainlines"] = mapping
            with self.assertRaises(ValueError):
                mainline.validate_state(invalid)

    def test_stage_description_update_is_atomic(self):
        mainline.subdivide_state(self.path, "实现", ["数据", "接口"])
        original = self.path.read_bytes()
        with patch.object(mainline.os, "replace", side_effect=OSError("测试故障")):
            with self.assertRaises(OSError):
                mainline.describe_state(self.path, "确保接口一致。", stage="接口", parent="实现")
        self.assertEqual(self.path.read_bytes(), original)

    def test_cli_describe_scopes_project_stage_and_child(self):
        mainline.subdivide_state(self.path, "实现", ["数据", "接口"])
        command = [sys.executable, str(Path(mainline.__file__)), "describe", "--state", str(self.path)]
        for arguments in (["--mainline", "项目主线"],
                          ["--stage", "实现", "--mainline", "实现目标。"],
                          ["--parent", "实现", "--stage", "接口", "--mainline", "  确保接口一致。  "]):
            result = subprocess.run(command + arguments, capture_output=True)
            self.assertEqual(result.returncode, 0, result.stderr.decode("utf-8"))
        state = mainline.read_state(self.path)
        self.assertEqual(state["mainline"], "项目主线")
        self.assertEqual(state["stage_mainlines"], {"实现": "实现目标。"})
        self.assertEqual(state["substages"]["实现"]["stage_mainlines"], {"接口": "确保接口一致。"})
        original = self.path.read_bytes()
        rejected = subprocess.run(command + ["--parent", "实现", "--mainline", "目标。"], capture_output=True)
        self.assertNotEqual(rejected.returncode, 0)
        self.assertEqual(self.path.read_bytes(), original)



    def test_details_only_update_preserves_all_other_state_and_noop(self):
        mainline.describe_state(self.path, "项目主线")
        mainline.describe_state(self.path, "实现目标。", stage="实现")
        mainline.describe_state(self.path, stage="验收", details="验收说明。")
        before = mainline.status_state(self.path, active="实现", label="修复错误")
        text = "说明" * 300 + "。\n保留自然换行。"
        changed = mainline.describe_state(self.path, stage="实现", details="  " + text + "  ")
        expected = copy.deepcopy(before)
        expected["stage_details"]["实现"] = text
        expected.update(revision=changed["revision"], updated_at=changed["updated_at"])
        self.assertEqual(changed, expected)
        original = self.path.read_bytes()
        self.assertEqual(mainline.describe_state(self.path, stage="实现", details=text), changed)
        self.assertEqual(self.path.read_bytes(), original)
        cleared = mainline.describe_state(self.path, stage="实现", details="")
        self.assertEqual(cleared["stage_details"], {"验收": "验收说明。"})
        self.assertEqual(cleared["stage_mainlines"], before["stage_mainlines"])
        self.assertEqual(cleared["stage_labels"], before["stage_labels"])

    def test_cli_details_only_combined_and_clear(self):
        mainline.describe_state(self.path, "项目主线")
        command = [sys.executable, str(Path(mainline.__file__)), "describe", "--state", str(self.path),
                   "--stage", "实现"]
        for arguments in (["--details", "先完成接口。\n再验证行为。"],
                          ["--mainline", "实现目标。", "--details", "同时更新后的说明。"],
                          ["--details", ""]):
            result = subprocess.run(command + arguments, capture_output=True)
            self.assertEqual(result.returncode, 0, result.stderr.decode("utf-8"))
            state = json.loads(result.stdout.decode("utf-8"))
            self.assertEqual(state["mainline"], "项目主线")
            if arguments[-1] == "":
                self.assertNotIn("stage_details", state)
            else:
                self.assertEqual(state["stage_details"]["实现"], arguments[-1])
        self.assertEqual(state["stage_mainlines"], {"实现": "实现目标。"})
        mainline.subdivide_state(self.path, "实现", ["数据", "接口"])
        child = subprocess.run(command[:-2] + ["--parent", "实现", "--stage", "接口",
            "--details", "校对接口契约。"], capture_output=True)
        self.assertEqual(child.returncode, 0, child.stderr.decode("utf-8"))
        self.assertEqual(json.loads(child.stdout.decode("utf-8"))["substages"]["实现"]["stage_details"],
                         {"接口": "校对接口契约。"})

    def test_child_details_with_same_names_are_isolated(self):
        for parent in ("实现", "验收"):
            mainline.subdivide_state(self.path, parent, ["检查", "交付"], "检查")
        mainline.describe_state(self.path, stage="实现", details="顶层说明。")
        mainline.describe_state(self.path, stage="检查", parent="实现", details="实现检查。")
        before = mainline.status_state(self.path, parent="验收", active="检查", label="核对结果")
        changed = mainline.describe_state(self.path, stage="检查", parent="验收", details="验收检查。")
        expected = copy.deepcopy(before)
        expected["substages"]["验收"]["stage_details"] = {"检查": "验收检查。"}
        expected.update(revision=changed["revision"], updated_at=changed["updated_at"])
        self.assertEqual(changed, expected)
        cleared = mainline.describe_state(self.path, stage="检查", parent="实现", details="")
        self.assertNotIn("stage_details", cleared["substages"]["实现"])
        self.assertEqual(cleared["substages"]["验收"], changed["substages"]["验收"])
        self.assertEqual(cleared["stage_details"], {"实现": "顶层说明。"})

    def test_details_survive_progress_and_clear_only_on_replanning(self):
        mainline.describe_state(self.path, stage="实现", details="顶层说明。")
        mainline.status_state(self.path, active="实现")
        mainline.position_state(self.path, "验收")
        mainline.status_state(self.path, done=["确定方案", "实现"])
        finished = mainline.finish_state(self.path)
        self.assertEqual(finished["stage_details"], {"实现": "顶层说明。"})
        for parent in ("实现", "验收"):
            mainline.subdivide_state(self.path, parent, ["数据", "接口"], "数据")
            mainline.describe_state(self.path, stage="数据", parent=parent, details="该组的数据说明。")
        mainline.status_state(self.path, parent="实现", done="数据", active="接口")
        same = mainline.subdivide_state(self.path, "实现", ["数据", "接口"], "数据")
        self.assertEqual(same["substages"]["实现"]["stage_details"], {"数据": "该组的数据说明。"})
        changed = mainline.subdivide_state(self.path, "实现", ["数据", "页面"], reason="架构变化")
        self.assertNotIn("stage_details", changed["substages"]["实现"])
        self.assertIn("stage_details", changed["substages"]["验收"])
        self.assertEqual(changed["stage_details"], {"实现": "顶层说明。"})
        reset = mainline.replan_state(self.path, self.stages, "确定方案", "重定范围")
        self.assertNotIn("stage_details", reset)
        self.assertNotIn("substages", reset)
        described = mainline.describe_state(self.path, stage="确定方案", details="新说明。")
        identical_plan = mainline.replan_state(self.path, self.stages, "确定方案", "明确重启计划")
        self.assertNotIn("stage_details", identical_plan)
        self.assertEqual(identical_plan["revision"], described["revision"] + 1)

    def test_invalid_details_are_rejected_without_modifying_state(self):
        original = self.path.read_bytes()
        for arguments in ({}, {"details": "说明"}, {"parent": "实现", "details": "说明"},
                          {"stage": "实现", "details": 3}, {"stage": "实现", "details": []},
                          {"stage": "不存在", "details": "说明"},
                          {"stage": "接口", "parent": "实现", "details": "说明"}):
            with self.subTest(arguments=arguments), self.assertRaises(ValueError):
                mainline.describe_state(self.path, **arguments)
            self.assertEqual(self.path.read_bytes(), original)
        for mapping in ([], {"不存在": "说明"}, {"实现": ""}, {"实现": " "},
                        {"实现": 1}, {"实现": {"更深层": "说明"}}):
            with self.subTest(mapping=mapping), self.assertRaises(ValueError):
                mainline.validate_state(dict(self.state, stage_details=mapping))
        split = mainline.subdivide_state(self.path, "实现", ["数据", "接口"])
        for mapping in ({"不存在": "说明"}, {"数据": []}, {"数据": {"更深层": "说明"}}):
            candidate = copy.deepcopy(split)
            candidate["substages"]["实现"]["stage_details"] = mapping
            with self.assertRaises(ValueError):
                mainline.validate_state(candidate)

    def test_old_state_needs_no_details_and_clearing_missing_details_is_noop(self):
        original = self.path.read_bytes()
        self.assertNotIn("stage_details", mainline.read_state(self.path))
        self.assertEqual(mainline.describe_state(self.path, stage="实现", details=""), self.state)
        self.assertEqual(self.path.read_bytes(), original)

    def test_combined_details_and_mainline_update_is_atomic(self):
        mainline.subdivide_state(self.path, "实现", ["数据", "接口"])
        original = self.path.read_bytes()
        with patch.object(mainline.os, "replace", side_effect=OSError("测试故障")):
            with self.assertRaises(OSError):
                mainline.describe_state(self.path, "保证一致。", stage="接口", parent="实现", details="验证接口契约。")
        self.assertEqual(self.path.read_bytes(), original)
        updated = mainline.describe_state(self.path, "保证一致。", stage="接口", parent="实现", details="验证接口契约。")
        with running(self.path) as url:
            self.assertEqual(get(url + "/state")[0]["state"], updated)


if __name__ == "__main__":
    print(f"Test artifacts: {ROOT}")
    unittest.main(verbosity=2)
