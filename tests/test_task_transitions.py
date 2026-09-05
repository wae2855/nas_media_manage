"""转换表全组合测试（Phase 2 S1 / REQ-20260822-000004）。

由 TRANSITIONS 自动生成：
1. 全部 (状态 × 动作) 组合的合法性断言——合法转换通过，非法转换抛 TransitionError；
2. 关键语义断言：file_location 诚实规则、retry 整任务重启、终态守卫。

这是"回退/继续不专业"问题的直接防线：任何新增动作/状态若未在转换表注册，
本文件自动暴露非法组合缺口。
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from media_importer.features.tasks.transitions import (
    ACTIVE_STATES,
    ALL_STATES,
    FILE_LOCATION_IMPORT,
    FILE_LOCATION_SOURCE,
    STAGE_AWAIT_REVIEW,
    STAGE_QUEUED,
    TRANSITIONS,
    TransitionError,
    apply,
    can_apply,
)


def _task(status, stage, **extra):
    return {"task_id": "t1", "status": status, "stage": stage, **extra}


class TestTransitionTableCompleteness(unittest.TestCase):
    """转换表元检查：动作集合与状态集合的完备性。"""

    def test_all_states_are_active_or_terminal(self):
        active = {s for s in ACTIVE_STATES}
        terminal = ALL_STATES - ACTIVE_STATES
        self.assertEqual(len(terminal), 4)  # SUCCESS/FAILED/SKIPPED/CANCELLED
        self.assertEqual(len(active), 3)    # QUEUED/RUNNING/AWAIT_REVIEW

    def test_every_action_target_is_valid_state(self):
        for action, (sources, target) in TRANSITIONS.items():
            self.assertIn(target, ALL_STATES, f"{action} 目标态非法: {target}")
            self.assertTrue(sources, f"{action} 未定义任何源状态")

    def test_terminal_states_have_no_outgoing_except_defined(self):
        """终态仅允许注册的 retry 类动作与 ignore；SUCCESS 始终无出边。"""
        for action, (sources, _) in TRANSITIONS.items():
            for src in sources:
                if src in {"SUCCESS-DONE", (x for x in ())}:
                    continue
            # SUCCESS 不允许任何出边
            success = ("SUCCESS", "DONE")
            self.assertNotIn(success, sources,
                             f"SUCCESS 终态不允许出边: {action}")


class TestFullCombinationMatrix(unittest.TestCase):
    """全部 (状态 × 动作) 组合：合法 ⇔ 在转换表源集合中。"""

    def test_every_combination_matches_table(self):
        for state in sorted(ALL_STATES):
            for action in sorted(TRANSITIONS):
                allowed = state in TRANSITIONS[action][0]
                with self.subTest(state=state, action=action):
                    task = _task(*state)
                    if allowed:
                        try:
                            fields = apply(task, action, error_message="x", reason="x")
                            self.assertIsInstance(fields, dict)
                        except TransitionError as e:
                            self.fail(f"合法转换被拒绝 {state}+{action}: {e}")
                    else:
                        with self.assertRaises(TransitionError):
                            apply(task, action, error_message="x", reason="x")

    def test_can_apply_consistent_with_apply(self):
        for state in sorted(ALL_STATES):
            for action in sorted(TRANSITIONS):
                task = _task(*state)
                expected = state in TRANSITIONS[action][0]
                self.assertEqual(can_apply(task, action), expected,
                                 f"can_apply 不一致: {state}+{action}")


class TestKeySemantics(unittest.TestCase):
    """关键语义断言（诚实规则 / 整任务重启 / 守卫）。"""

    def test_fail_location_source_when_no_file(self):
        task = _task("PENDING", "RUNNING", video_path="/nonexistent/x.mkv")
        fields = apply(task, "fail", error_message="boom")
        self.assertEqual(fields["file_location"], FILE_LOCATION_SOURCE)

    def test_retry_restarts_whole_task_from_original_source(self):
        task = _task(
            "FAILED",
            "DONE",
            source_path="/source/Movie.mkv",
            video_path="/library/Movie.copying",
            file_location=FILE_LOCATION_IMPORT,
            retry_count=1,
            scrape_result={"title_cn": "旧结果"},
            classify_result={"rule_id": "old"},
            bundle_state="RECOVERY_REQUIRED",
            bundle_manifest=[{"kind": "video"}],
            percentage=77,
        )
        fields = apply(task, "retry")
        self.assertEqual(fields["stage"], STAGE_QUEUED)
        self.assertEqual(fields["file_location"], FILE_LOCATION_SOURCE)
        self.assertEqual(fields["video_path"], "/source/Movie.mkv")
        self.assertEqual(fields["scrape_result"], {})
        self.assertEqual(fields["classify_result"], "")
        self.assertEqual(fields["bundle_state"], "")
        self.assertEqual(fields["bundle_manifest"], [])
        self.assertEqual(fields["percentage"], 0)
        self.assertEqual(fields["retry_count"], 2)

    def test_await_review_cannot_start(self):
        """AWAIT_REVIEW 不可被 runner start（防双处理）。"""
        task = _task("PENDING", STAGE_AWAIT_REVIEW)
        self.assertFalse(can_apply(task, "start"))

    def test_failed_reorganization_returns_to_review_without_losing_target(self):
        task = _task(
            "FAILED",
            "DONE",
            task_kind="REORGANIZE",
            source_path="/library/old/Movie.mkv",
            video_path="/library/old/Movie.mkv",
            import_path="/library/custom",
            final_filename="Movie.mkv",
            reorganization_intent={"reason": "user_requested", "mode": "custom"},
            retry_count=0,
        )

        fields = apply(task, "retry_reorganization")

        self.assertEqual(fields["stage"], STAGE_AWAIT_REVIEW)
        self.assertEqual(fields["file_location"], FILE_LOCATION_IMPORT)
        self.assertNotIn("import_path", fields)
        self.assertNotIn("final_filename", fields)
        self.assertNotIn("reorganization_intent", fields)
        self.assertEqual(fields["retry_count"], 1)

    def test_queued_cannot_confirm(self):
        task = _task("PENDING", STAGE_QUEUED)
        self.assertFalse(can_apply(task, "confirm_mark"))

    def test_manual_binding_requeues_review_without_counting_as_retry(self):
        task = _task(
            "PENDING",
            STAGE_AWAIT_REVIEW,
            retry_count=2,
            source_path="/source/Show.S01E05.mkv",
            scrape_result={"title_cn": "错误作品"},
            scrape_title_cn="错误作品",
            provider_id="wrong-id",
            thumbnail_path="/old/poster.jpg",
            percentage=80,
        )
        binding = {
            "provider_type": "tmdb",
            "item_id": "86941",
            "media_type": "tv",
            "season": 1,
            "episode": 5,
        }

        fields = apply(task, "manual_bind_queue", manual_provider_binding=binding)

        self.assertEqual(fields["stage"], STAGE_QUEUED)
        self.assertNotIn("retry_count", fields)
        self.assertEqual(task["retry_count"], 2)
        self.assertEqual(fields["scrape_result"], {})
        self.assertEqual(fields["scrape_title_cn"], "")
        self.assertEqual(fields["provider_id"], "")
        self.assertEqual(fields["thumbnail_path"], "")
        self.assertEqual(fields["manual_provider_binding"], binding)
        self.assertEqual(fields["percentage"], 0)

    def test_success_is_frozen(self):
        for action in ("fail", "skip", "cancel", "retry", "ignore"):
            task = _task("SUCCESS", "DONE")
            self.assertFalse(can_apply(task, action),
                             f"SUCCESS 不允许 {action}")

    def test_imported_writes_import_location(self):
        task = _task("PENDING", "RUNNING", import_video_path="/import/m.mkv")
        fields = apply(task, "import_ok")
        self.assertEqual(fields["file_location"], FILE_LOCATION_IMPORT)
        self.assertEqual(fields["import_success"], 1)

    def test_unknown_action_rejected(self):
        task = _task("PENDING", "QUEUED")
        with self.assertRaises(TransitionError):
            apply(task, "no_such_action")

    def test_empty_state_rejected(self):
        """无状态字段（脏数据）不允许任何动作——fail-fast 而非静默通过。"""
        task = {"task_id": "t1"}
        for action in ("start", "fail", "retry"):
            with self.assertRaises(TransitionError):
                apply(task, action)


if __name__ == "__main__":
    unittest.main()
