"""AI 调用统一日志测试（覆盖 T1.15）。

验证以下日志事件：
- ai.scene.start
- ai.scene.success
- ai.scene.retry
- ai.scene.fallback
- ai.scene.failure
- ai.scene.prompt_summary（受 log_prompt 控制）
- ai.scene.business（场景 3/4/5 入口业务上下文）
"""
import logging
from unittest.mock import patch

import pytest

from media_importer.scraper.llm_scraper import LLMScraper
from media_importer.scraper.exceptions import LLMApiError


AI_LOGGER = "media_importer.ai"


class _LogCapture:
    def __init__(self, logger_name=AI_LOGGER, level=logging.INFO):
        self.logger = logging.getLogger(logger_name)
        self.logger.setLevel(level)
        self.records = []
        self.handler = logging.Handler()

        def emit(record):
            self.records.append(record.getMessage())

        self.handler.emit = emit
        self.logger.addHandler(self.handler)

    def remove(self):
        self.logger.removeHandler(self.handler)

    def messages(self):
        return list(self.records)


@pytest.fixture
def ai_log_capture():
    cap = _LogCapture()
    yield cap
    cap.remove()


def _make_config(**overrides):
    cfg = {
        "ai_assist": {"base_url": "https://a.com", "model": "a-m", "api_key": "k",
                     "max_retries": 2, "retry_delay": 0},
        "ai_search": {"enabled": True, "provider": "zhipu",
                     "base_url": "https://s.com", "model": "s-m", "api_key": "k",
                     "search_type": "search_std"},
        "ai_scene_strategy": {
            "match_assist": {"primary": "ai_assist", "fallback": ""},
        },
    }
    cfg.update(overrides)
    return cfg


def test_log_ai_scene_start_on_call(ai_log_capture):
    s = LLMScraper(_make_config())
    with patch.object(s, "_do_call", return_value='{"result":"ok"}'):
        s._retry_with_fallback("p", "u", scene="match_assist", scenario="scrape")
    msgs = ai_log_capture.messages()
    assert any(m.startswith("ai.scene.start scene=match_assist model=ai_assist") for m in msgs), msgs


def test_log_ai_scene_success_with_elapsed(ai_log_capture):
    s = LLMScraper(_make_config())
    with patch.object(s, "_do_call", return_value='{"result":"ok"}'):
        s._retry_with_fallback("p", "u", scene="match_assist", scenario="scrape")
    msgs = ai_log_capture.messages()
    assert any("ai.scene.success" in m and "elapsed_ms=" in m for m in msgs), msgs


def test_log_ai_scene_retry_on_failure(ai_log_capture):
    s = LLMScraper(_make_config())
    state = {"n": 0}

    def _call(*a, **kw):
        state["n"] += 1
        if state["n"] == 1:
            raise LLMApiError("rate limited")
        return '{"result":"ok"}'

    with patch.object(s, "_do_call", side_effect=_call):
        s._retry_with_fallback("p", "u", scene="match_assist", scenario="scrape")
    msgs = ai_log_capture.messages()
    assert any("ai.scene.retry" in m and "error=LLMApiError" in m and "reason=" in m for m in msgs), msgs


def test_log_ai_scene_fallback_on_model_switch(ai_log_capture):
    cfg = _make_config()
    cfg["ai_scene_strategy"] = {"match_assist": {"primary": "ai_assist", "fallback": "ai_search"}}
    s = LLMScraper(cfg)

    def _call(*a, **kw):
        if a[2] == "a-m":
            raise LLMApiError("primary fail")
        return '{"result":"ok"}'

    with patch.object(s, "_do_call", side_effect=_call):
        s._retry_with_fallback("p", "u", scene="match_assist", scenario="scrape")
    msgs = ai_log_capture.messages()
    assert any("ai.scene.fallback scene=match_assist from=ai_assist to=ai_search" in m for m in msgs), msgs


def test_log_ai_scene_failure_when_all_fail(ai_log_capture):
    cfg = _make_config()
    cfg["ai_scene_strategy"] = {"match_assist": {"primary": "ai_assist", "fallback": "ai_search"}}
    s = LLMScraper(cfg)
    with patch.object(s, "_do_call", side_effect=LLMApiError("always fail")):
        try:
            s._retry_with_fallback("p", "u", scene="match_assist", scenario="scrape")
        except LLMApiError:
            pass
    msgs = ai_log_capture.messages()
    assert any("ai.scene.failure" in m and "last_error=LLMApiError" in m and "total_elapsed_ms=" in m for m in msgs), msgs


def test_log_ai_scene_prompt_summary_info_level(ai_log_capture):
    s = LLMScraper(_make_config())
    long_system = "A" * 500
    long_user = "B" * 500
    with patch.object(s, "_do_call", return_value='{"result":"ok"}'):
        s._retry_with_fallback(long_system, long_user, scene="match_assist", scenario="scrape")
    msgs = ai_log_capture.messages()
    summary = [m for m in msgs if m.startswith("ai.scene.prompt_summary")]
    assert summary, "应输出 prompt_summary"
    assert "system_prompt_preview=" in summary[0]
    assert "user_prompt_preview=" in summary[0]
    # 前 200 字符
    assert "A" * 200 in summary[0]
    assert "B" * 200 in summary[0]


def test_log_ai_scene_prompt_summary_disabled_when_log_prompt_false(ai_log_capture):
    cfg = _make_config()
    cfg["ai_assist"]["log_prompt"] = False
    s = LLMScraper(cfg)
    with patch.object(s, "_do_call", return_value='{"result":"ok"}'):
        s._retry_with_fallback("p", "u", scene="match_assist", scenario="scrape")
    msgs = ai_log_capture.messages()
    assert not any("ai.scene.prompt_summary" in m for m in msgs), msgs


def test_log_ai_scene_business_title_clean(ai_log_capture):
    s = LLMScraper(_make_config())
    with patch.object(s, "_do_call", return_value="cleaned"):
        s.extract_title("some.movie.2020.mkv")
    msgs = ai_log_capture.messages()
    assert any("ai.scene.business scene=title_clean" in m for m in msgs), msgs


def test_log_ai_scene_business_match_assist(ai_log_capture):
    s = LLMScraper(_make_config())
    import json as _json
    with patch.object(s, "_do_call", return_value='{"corrected_title": "x", "certainty": "high"}'):
        s.tier2_correct("movie.mkv")
    msgs = ai_log_capture.messages()
    assert any("ai.scene.business scene=match_assist" in m for m in msgs), msgs


def test_log_ai_scene_business_source_clean(ai_log_capture, tmp_path):
    import os
    from media_importer.features.source_cleaning.cleaner import SourceCleaner
    src = tmp_path / "src"
    src.mkdir()
    (src / "a.txt").write_text("x")
    (src / "sub").mkdir()
    cfg = _make_config()
    cfg["source_dir"] = str(src)
    cfg["temp_dir"] = str(tmp_path / "tmp")
    cfg["log_dir"] = str(tmp_path / "logs")
    cfg["source_policy"] = {"recycle_dir": str(tmp_path / "recycle")}
    cfg["source_cleaner"] = {"ai_enabled": True}
    sc = SourceCleaner(cfg)
    with patch.object(sc.llm, "_do_call", return_value='{"decisions": {}}'):
        sc._ai_analyze_directory(str(src), [{"name": "a.txt", "size_mb": 0, "ext": ".txt"}])
    msgs = ai_log_capture.messages()
    assert any("ai.scene.business scene=source_clean" in m for m in msgs), msgs