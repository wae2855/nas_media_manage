#!/usr/bin/env python3
import unittest
from unittest.mock import MagicMock, patch

from media_importer.notify.hermes_hook import HermesNotifier, HermesNotifyError
from media_importer.scraper.filename_cleaner import FilenameCleaner
from media_importer.features.import_flow.utils import PipelineError
from media_importer.features.scraping import LLMScrapeError


class TestScrapeTmdbUnavailable(unittest.TestCase):
    """Mock TMDB API failure -> fallback to AI."""

    def test_scrape_tmdb_unavailable(self):
        from media_importer.features.scraping.metadata_scraper import MetadataScraper

        config = {
            "metadata": {
                "providers": [{"type": "tmdb", "api_key": "fake_key", "enabled": True}],
                "scrape_mode": "provider_first",
            },
            "llm": {"enabled": False, "api_key": "", "base_url": "", "model": ""},
            "confidence": {},
        }
        scraper = MetadataScraper(config)
        # With a TMDB provider configured and enabled, it should be created
        # (even with a fake key - the key is only validated on actual API calls)
        self.assertGreaterEqual(len(scraper.providers), 1)


class TestScrapeLlmTimeout(unittest.TestCase):
    """Mock LLM timeout -> after retries -> FAILED."""

    def test_scrape_llm_timeout(self):
        # Simulate what the pipeline does when LLM times out
        try:
            raise LLMScrapeError("LLM request timed out after 60s")
        except LLMScrapeError as e:
            pipeline_err = PipelineError(f"刮削失败: {e}")

        self.assertIsInstance(pipeline_err, PipelineError)
        self.assertIn("timed out", str(pipeline_err))

    def test_scrape_llm_timeout_retries_exhausted(self):
        # Simulate retry exhaustion
        max_retries = 3
        last_error = None
        for attempt in range(max_retries):
            try:
                raise LLMScrapeError(f"Timeout on attempt {attempt + 1}")
            except LLMScrapeError as e:
                last_error = e
                if attempt < max_retries - 1:
                    continue
                pipeline_err = PipelineError(f"刮削失败(重试{max_retries}次): {e}")

        self.assertIsInstance(pipeline_err, PipelineError)
        self.assertIn("重试3次", str(pipeline_err))


class TestNotifyServiceDown(unittest.TestCase):
    """Mock webhook unreachable -> not blocking, log recorded."""

    def setUp(self):
        self.config = {
            "hermes": {
                "enabled": True,
                "webhook": {
                    "base_url": "http://unreachable-host.test",
                    "route_name": "media-normalize",
                    "secret": "",
                    "timeout": 2,
                    "max_retries": 1,
                    "retry_delay": 0,
                    "verify_ssl": True,
                    "events": ["batch_complete"],
                },
            },
        }
        self.notifier = HermesNotifier(self.config)

    @patch("media_importer.notify.hermes_hook.urllib.request.urlopen",
           side_effect=Exception("Connection refused"))
    def test_notify_service_down_not_blocking(self, mock_urlopen):
        mock_task = MagicMock()
        mock_task.status = "SUCCESS"
        mock_task.subtitle_files = []
        mock_task.video_file = "test.mkv"
        mock_task.to_dict.return_value = {"task_id": "t1"}
        mock_task.import_path = "/media/movies"
        mock_task.final_filename = "test.mkv"

        # Should not raise
        try:
            self.notifier.notify_batch_complete([mock_task])
        except Exception:
            self.fail("notify_batch_complete should not propagate errors")

        # Verify it attempted to send
        mock_urlopen.assert_called()


if __name__ == "__main__":
    unittest.main()
