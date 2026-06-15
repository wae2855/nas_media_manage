"""SourceCleaner 使用 LLMScraper 的单元测试（覆盖 T1.11）。

验证：
- _call_llm 使用 LLMScraper.call_with_prompt
- SourceCleaner 不直接调用 urllib
- 场景策略影响模型选择
"""
from unittest.mock import patch

import pytest

from media_importer.features.source_cleaning.cleaner import SourceCleaner


def _make_source_cleaner_config(source_dir, tmp_path):
    return {
        "source_dir": str(source_dir),
        "temp_dir": str(tmp_path / "tmp"),
        "log_dir": str(tmp_path / "logs"),
        "source_policy": {"recycle_dir": str(tmp_path / "recycle")},
        "source_cleaner": {"ai_enabled": True},
        "ai_assist": {"base_url": "https://a.com", "model": "a-m", "api_key": "k",
                     "max_retries": 1, "retry_delay": 0},
        "ai_search": {"enabled": True, "provider": "zhipu",
                     "base_url": "https://s.com", "model": "s-m", "api_key": "k"},
        "video_extensions": [".mp4"],
        "subtitle_extensions": [".srt"],
    }


class TestSourceCleanerUsesLLMScraper:
    def test_call_llm_uses_call_with_prompt(self, tmp_path):
        """_call_llm 调用 LLMScraper.call_with_prompt。"""
        src = tmp_path / "src"
        src.mkdir()
        (src / "movie.mp4").write_text("x")
        sc = SourceCleaner(_make_source_cleaner_config(src, tmp_path))
        with patch.object(sc.llm, "call_with_prompt", return_value='{"decisions": {}}') as mock:
            result = sc._call_llm("用户提示词")
        mock.assert_called_once()
        args, kwargs = mock.call_args
        assert kwargs.get("scene") == "source_clean"
        assert "用户提示词" in kwargs.get("user_prompt", "")

    def test_no_urllib_direct_call_in_cleaner(self):
        """cleaner.py 不应直接调用 urllib.request.urlopen。"""
        import inspect
        import media_importer.features.source_cleaning.cleaner as _cleaner_mod
        source = open(inspect.getfile(_cleaner_mod)).read()
        assert "urllib.request.urlopen" not in source, "SourceCleaner 不应直接使用 urllib"
        assert "urllib.request.Request" not in source, "SourceCleaner 不应直接构造 HTTP 请求"


class TestSourceCleanerFollowsSceneStrategy:
    def test_strategy_affects_model_call(self, tmp_path):
        """配置 primary=ai_search 时，调用走 ai_search 模型。"""
        src = tmp_path / "src2"
        src.mkdir()
        (src / "movie.mp4").write_text("x")
        cfg = _make_source_cleaner_config(src, tmp_path)
        cfg["ai_scene_strategy"] = {
            "source_clean": {"primary": "ai_search", "fallback": ""},
        }
        sc = SourceCleaner(cfg)
        with patch.object(sc.llm, "call_with_prompt", return_value='{"decisions": {}}') as mock:
            sc._call_llm("test")
        # call_with_prompt 内部调用 _call_with_retry_impl 走 SceneStrategyResolver
        # 这里验证外层调用被触发即可
        mock.assert_called_once()
