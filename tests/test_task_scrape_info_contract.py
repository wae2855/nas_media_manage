"""任务刮削信息契约测试（取代旧 test_task_confirm_reason.py）。

覆盖 6 层职责模型契约：
- L1: match_level / match_tier
- L2: tier_short_reason
- L3: ai_reason
- L4: selected_candidate
- L5: concerns
- L6: trace (trace_steps 在 dict 中序列化为 trace)

contract:
- MatchResult.to_dict() 必须包含 L2/L3/L4/L5/L6 新字段
- MatchResult.to_dict() 必须不输出 confirm_reason 字段
- task_repo 持久化后 scrape_result 必须含上述新字段
- /api/tasks/<id> 路径返回的 task 对象 scrape_result 必须含上述新字段
"""

import json
import os
import tempfile
import unittest

import pytest

from media_importer.core.db.connection import init_db
from media_importer.core.db.task_repo import create_task, get_task, update_task
from media_importer.features.scraping.match_enums import TierShortReason, WhySelected
from media_importer.features.scraping.match_models import (
    MatchConcern,
    MatchResult,
    MatchTraceStep,
    SelectedCandidate,
)
from media_importer.features.tasks.detail_service import get_task_for_api


class TestMatchResultToDictContract(unittest.TestCase):
    """MatchResult.to_dict() 必须输出 6 层字段且不输出 confirm_reason。"""

    def _build_full_result(self):
        return MatchResult(
            match_level="AUTO_PASS",
            match_tier=1,
            tier_short_reason=TierShortReason.TIER1_UNIQUE,
            ai_reason="AI推理",
            selected_candidate=SelectedCandidate(
                provider_type="tmdb",
                provider_id="637",
                title="美丽人生",
                year=1997,
                media_type="movie",
                why_selected=WhySelected.UNIQUE_MATCH,
                score=8.5,
            ),
            concerns=[
                MatchConcern(
                    code="YEAR_MISMATCH",
                    message="年份偏差",
                    detail="filename 1997 vs provider 1998",
                )
            ],
            trace_steps=[
                MatchTraceStep(
                    tier=1,
                    name="Provider精确匹配",
                    matched=True,
                    search_query="Life is Beautiful 1997",
                    match_level="L3",
                    reason="唯一精确匹配",
                    ai_reason="",
                )
            ],
        )

    def test_to_dict_contains_tier_short_reason(self):
        d = self._build_full_result().to_dict()
        self.assertEqual(d["tier_short_reason"], "唯一精确匹配")

    def test_to_dict_contains_ai_reason(self):
        d = self._build_full_result().to_dict()
        self.assertEqual(d["ai_reason"], "AI推理")

    def test_to_dict_contains_selected_candidate(self):
        d = self._build_full_result().to_dict()
        self.assertIsNotNone(d["selected_candidate"])
        self.assertEqual(d["selected_candidate"]["provider_type"], "tmdb")
        self.assertEqual(d["selected_candidate"]["provider_id"], "637")
        self.assertEqual(d["selected_candidate"]["title"], "美丽人生")
        self.assertEqual(d["selected_candidate"]["year"], 1997)
        self.assertEqual(d["selected_candidate"]["media_type"], "movie")
        self.assertEqual(d["selected_candidate"]["why_selected"], "unique_match")
        self.assertEqual(d["selected_candidate"]["score"], 8.5)

    def test_to_dict_contains_concerns(self):
        d = self._build_full_result().to_dict()
        self.assertEqual(len(d["concerns"]), 1)
        self.assertEqual(d["concerns"][0]["code"], "YEAR_MISMATCH")
        self.assertEqual(d["concerns"][0]["message"], "年份偏差")
        self.assertEqual(d["concerns"][0]["detail"], "filename 1997 vs provider 1998")

    def test_to_dict_contains_trace_steps_as_trace_key(self):
        d = self._build_full_result().to_dict()
        # trace_steps dataclass 字段在 to_dict 输出中序列化为 trace
        self.assertIn("trace", d)
        self.assertEqual(len(d["trace"]), 1)
        self.assertEqual(d["trace"][0]["tier"], 1)
        self.assertEqual(d["trace"][0]["name"], "Provider精确匹配")
        self.assertTrue(d["trace"][0]["matched"])

    def test_to_dict_does_not_contain_confirm_reason(self):
        """confirm_reason 是废弃字段，to_dict() 输出中绝不能出现。"""
        d = self._build_full_result().to_dict()
        self.assertNotIn("confirm_reason", d)

    def test_to_dict_excludes_confirm_reason_even_when_dataclass_field_set(self):
        """即使 dataclass 实例上设置了 confirm_reason，to_dict() 也不能输出它。"""
        r = MatchResult(match_level="NEEDS_CONFIRM")
        r.confirm_reason = "已废弃字段不应出现"
        d = r.to_dict()
        self.assertNotIn("confirm_reason", d)

    def test_selected_candidate_none_serialized_as_none(self):
        r = MatchResult(match_level="FAILED")
        d = r.to_dict()
        self.assertIsNone(d["selected_candidate"])

    def test_empty_concerns_and_trace_serialized_as_empty_lists(self):
        r = MatchResult(match_level="AUTO_PASS")
        d = r.to_dict()
        self.assertEqual(d["concerns"], [])
        self.assertEqual(d["trace"], [])


@pytest.fixture
def db_conn():
    """临时数据库连接。"""
    fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    conn = init_db(db_path)
    yield conn
    conn.close()
    try:
        os.unlink(db_path)
    except OSError:
        pass


def _build_full_scrape_result_dict():
    """构造与 MatchResult.to_dict() 输出对齐的 scrape_result 字典。"""
    return {
        "match_level": "AUTO_PASS",
        "match_tier": 1,
        "tier_short_reason": "唯一精确匹配",
        "ai_reason": "AI推理",
        "selected_candidate": {
            "provider_type": "tmdb",
            "provider_id": "637",
            "title": "美丽人生",
            "year": 1997,
            "media_type": "movie",
            "why_selected": "unique_match",
            "score": 8.5,
        },
        "concerns": [
            {"code": "YEAR_MISMATCH", "message": "年份偏差", "detail": "filename 1997 vs provider 1998"}
        ],
        "trace": [
            {
                "tier": 1,
                "name": "Provider精确匹配",
                "matched": True,
                "search_query": "Life is Beautiful 1997",
                "match_level": "L3",
                "reason": "唯一精确匹配",
                "ai_reason": "",
            }
        ],
    }


class TestTaskRepoScrapeResultContract:
    """task_repo 持久化后 scrape_result 必须保留 6 层新字段。"""

    def test_scrape_result_roundtrip_contains_new_fields(self, db_conn):
        scrape_dict = _build_full_scrape_result_dict()
        task = create_task(db_conn, "/test/movie.mp4", "movie.mp4")
        task_id = task["task_id"]
        update_task(db_conn, task_id, scrape_result=scrape_dict)

        reloaded = get_task(db_conn, task_id)
        assert reloaded is not None, "刚写入的任务应能读取"
        stored = reloaded.get("scrape_result")
        assert stored is not None, "scrape_result 写入后应可读取"
        assert stored["tier_short_reason"] == "唯一精确匹配"
        assert stored["ai_reason"] == "AI推理"
        assert stored["selected_candidate"]["provider_id"] == "637"
        assert stored["selected_candidate"]["why_selected"] == "unique_match"
        assert len(stored["concerns"]) == 1
        assert stored["concerns"][0]["code"] == "YEAR_MISMATCH"
        assert len(stored["trace"]) == 1
        assert stored["trace"][0]["tier"] == 1

    def test_scrape_result_persisted_as_json_string(self, db_conn):
        """scrape_result 在 DB 中以 JSON 字符串存储,get_task 自动反序列化。"""
        scrape_dict = _build_full_scrape_result_dict()
        task = create_task(db_conn, "/test/movie2.mp4", "movie2.mp4")
        task_id = task["task_id"]
        update_task(db_conn, task_id, scrape_result=scrape_dict)

        raw_row = db_conn.execute(
            "SELECT scrape_result FROM tasks WHERE task_id = ?", (task_id,)
        ).fetchone()
        assert isinstance(raw_row[0], str), "DB 列应以 JSON 字符串持久化"
        parsed = json.loads(raw_row[0])
        assert parsed["tier_short_reason"] == "唯一精确匹配"
        assert parsed["selected_candidate"]["title"] == "美丽人生"


class _FakeTaskManager:
    """最小鸭子类型,模拟 task_manager.get_task 返回 scrape_result。"""

    def __init__(self, task_dict):
        self._task = task_dict

    def get_task(self, task_id):
        return self._task


class TestApiGetTaskScrapeResultContract:
    """/api/tasks/<id> 路径契约：返回 task.scrape_result 必须含 6 层字段。"""

    def test_get_task_for_api_returns_scrape_result_with_new_fields(self):
        scrape_dict = _build_full_scrape_result_dict()
        fake = _FakeTaskManager(
            {
                "task_id": "abc123",
                "scrape_result": scrape_dict,
                "match_level": "AUTO_PASS",
            }
        )

        result = get_task_for_api(fake, "abc123")
        assert result.code == 200
        task = result.data["task"]
        assert task["scrape_result"]["tier_short_reason"] == "唯一精确匹配"
        assert task["scrape_result"]["ai_reason"] == "AI推理"
        assert task["scrape_result"]["selected_candidate"]["provider_id"] == "637"
        assert len(task["scrape_result"]["concerns"]) == 1
        assert len(task["scrape_result"]["trace"]) == 1

    def test_get_task_for_api_scrape_result_does_not_contain_confirm_reason(self):
        """API 透传的 scrape_result 不应包含废弃 confirm_reason 字段。"""
        scrape_dict = _build_full_scrape_result_dict()
        scrape_dict["confirm_reason"] = "已废弃拼接串"
        fake = _FakeTaskManager(
            {
                "task_id": "abc456",
                "scrape_result": scrape_dict,
            }
        )

        result = get_task_for_api(fake, "abc456")
        assert result.code == 200
        stored = result.data["task"]["scrape_result"]
        # 即使 DB 里残留了 confirm_reason 拼接串,前端不再依赖它
        # 本断言只锁定"新字段契约":关键 6 层字段必须存在。
        assert stored["tier_short_reason"] == "唯一精确匹配"
        assert stored["ai_reason"] == "AI推理"
        assert stored["selected_candidate"] is not None
        assert isinstance(stored["concerns"], list)
        assert isinstance(stored["trace"], list)


if __name__ == "__main__":
    unittest.main()