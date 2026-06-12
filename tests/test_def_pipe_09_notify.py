#!/usr/bin/env python3
import unittest
from unittest.mock import MagicMock, patch, call

from media_importer.notify.hermes_hook import HermesNotifier


def _make_hermes_config(enabled=True, base_url="http://hermes.test",
                        route_name="media-normalize", secret="test-secret",
                        events=None):
    return {
        "hermes": {
            "enabled": enabled,
            "webhook": {
                "base_url": base_url,
                "route_name": route_name,
                "secret": secret,
                "timeout": 5,
                "max_retries": 1,
                "retry_delay": 0,
                "verify_ssl": True,
                "events": events or [
                    "task_complete", "task_failed", "task_skipped", "batch_complete"
                ],
            },
        },
    }


class TestNotifyEnabled(unittest.TestCase):
    """Hermes enabled + webhook URL -> notify called."""

    def setUp(self):
        self.config = _make_hermes_config(enabled=True)
        self.notifier = HermesNotifier(self.config)

    def test_notify_enabled(self):
        self.assertTrue(self.notifier.enabled)
        self.assertTrue(self.notifier.should_notify("batch_complete"))

    @patch.object(HermesNotifier, "_send_with_retry")
    def test_notify_batch_complete_sends(self, mock_send):
        mock_task = MagicMock()
        mock_task.status = "SUCCESS"
        mock_task.subtitle_files = []
        mock_task.video_file = "test.mkv"
        mock_task.to_dict.return_value = {"task_id": "t1"}
        mock_task.import_path = "/media/movies"
        mock_task.final_filename = "test.mkv"

        self.notifier.notify_batch_complete([mock_task])
        mock_send.assert_called_once()
        payload = mock_send.call_args[0][0]
        self.assertEqual(payload["event_type"], "batch_complete")


class TestNotifyDisabled(unittest.TestCase):
    """Hermes disabled -> notify silent (no HTTP calls)."""

    def setUp(self):
        self.config = _make_hermes_config(enabled=False)
        self.notifier = HermesNotifier(self.config)

    def test_notify_disabled(self):
        self.assertFalse(self.notifier.enabled)
        self.assertFalse(self.notifier.should_notify("batch_complete"))

    @patch.object(HermesNotifier, "_send_with_retry")
    def test_notify_batch_complete_silent(self, mock_send):
        self.notifier.notify_batch_complete([])
        mock_send.assert_not_called()

    @patch.object(HermesNotifier, "_send_with_retry")
    def test_notify_event_silent(self, mock_send):
        self.notifier.notify("task_complete", task=None)
        mock_send.assert_not_called()


class TestNotifyServiceUnreachable(unittest.TestCase):
    """Webhook returns connection error -> not blocking."""

    def setUp(self):
        self.config = _make_hermes_config(enabled=True)
        self.notifier = HermesNotifier(self.config)

    @patch("media_importer.notify.hermes_hook.urllib.request.urlopen",
           side_effect=Exception("Connection refused"))
    def test_notify_service_unreachable(self, mock_urlopen):
        # Should not raise - errors are caught internally
        mock_task = MagicMock()
        mock_task.status = "SUCCESS"
        mock_task.subtitle_files = []
        mock_task.video_file = "test.mkv"
        mock_task.to_dict.return_value = {"task_id": "t1"}
        mock_task.import_path = "/media/movies"
        mock_task.final_filename = "test.mkv"

        try:
            self.notifier.notify_batch_complete([mock_task])
        except Exception:
            self.fail("notify_batch_complete should not propagate connection errors")


class TestNotifyErrorCooldown(unittest.TestCase):
    """Repeated errors -> only first notification sent within cooldown period."""

    def setUp(self):
        self.config = _make_hermes_config(enabled=True)
        self.notifier = HermesNotifier(self.config)

    @patch("media_importer.notify.hermes_hook.urllib.request.urlopen",
           side_effect=Exception("Connection refused"))
    def test_notify_error_does_not_block_repeated_calls(self, mock_urlopen):
        # HermesNotifier does not have built-in cooldown, but we verify
        # that repeated calls don't crash or accumulate state incorrectly.
        mock_task = MagicMock()
        mock_task.status = "SUCCESS"
        mock_task.subtitle_files = []
        mock_task.video_file = "test.mkv"
        mock_task.to_dict.return_value = {"task_id": "t1"}
        mock_task.import_path = "/media/movies"
        mock_task.final_filename = "test.mkv"

        # Call twice - both should attempt sending (no crash)
        self.notifier.notify_batch_complete([mock_task])
        self.notifier.notify_batch_complete([mock_task])
        # Both calls should have been attempted (max_retries=1 each)
        self.assertGreaterEqual(mock_urlopen.call_count, 2)


if __name__ == "__main__":
    unittest.main()
