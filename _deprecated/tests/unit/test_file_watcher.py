#!/usr/bin/env python3
import os
import sys
import tempfile
import time
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'media_importer'))

from file_watcher import FileWatcher


class TestFileWatcher(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.source_dir = os.path.join(self.temp_dir, "source")
        os.makedirs(self.source_dir)
        self.detected_files = []

    def tearDown(self):
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def _on_new_files(self, new_files):
        self.detected_files.extend(new_files)

    def _make_config(self, enabled=True, poll_interval=1):
        return {
            "source_dir": self.source_dir,
            "file_watcher": {
                "enabled": enabled,
                "poll_interval": poll_interval,
                "ignore_patterns": ["*.tmp", ".DS_Store"]
            },
            "video_extensions": [".mkv", ".mp4"],
            "subtitle_extensions": [".srt"],
            "source_dir_scan": {
                "recursive": True,
                "max_depth": 5,
                "ignore_patterns": ["*.tmp"]
            }
        }

    def test_watcher_disabled(self):
        config = self._make_config(enabled=False)
        watcher = FileWatcher(config, on_new_files=self._on_new_files)
        watcher.start()
        time.sleep(0.5)
        self.assertFalse(watcher.status["running"])
        watcher.stop()

    def test_watcher_detects_new_file(self):
        config = self._make_config(poll_interval=1)
        watcher = FileWatcher(config, on_new_files=self._on_new_files)
        watcher.start()
        time.sleep(1.5)

        video_path = os.path.join(self.source_dir, "test.mkv")
        with open(video_path, "w") as f:
            f.write("fake video")

        time.sleep(2.5)

        watcher.stop()
        self.assertGreater(len(self.detected_files), 0)

    def test_watcher_status(self):
        config = self._make_config(enabled=True)
        watcher = FileWatcher(config, on_new_files=self._on_new_files)
        watcher.start()
        time.sleep(0.5)

        status = watcher.status
        self.assertTrue(status["enabled"])
        self.assertTrue(status["running"])
        self.assertEqual(status["source_dir"], self.source_dir)

        watcher.stop()

    def test_watcher_no_source_dir(self):
        config = self._make_config()
        config["source_dir"] = "/nonexistent/path"
        watcher = FileWatcher(config, on_new_files=self._on_new_files)
        watcher.start()
        time.sleep(0.5)
        self.assertFalse(watcher.status["running"])
        watcher.stop()

    def test_watcher_stop(self):
        config = self._make_config(poll_interval=1)
        watcher = FileWatcher(config, on_new_files=self._on_new_files)
        watcher.start()
        time.sleep(0.5)
        self.assertTrue(watcher.status["running"])

        watcher.stop()
        self.assertFalse(watcher.status["running"])

    def test_scan_known_files(self):
        video_path = os.path.join(self.source_dir, "movie.mkv")
        with open(video_path, "w") as f:
            f.write("fake")

        config = self._make_config(enabled=False)
        watcher = FileWatcher(config, on_new_files=self._on_new_files)
        known = watcher._scan_known_files()
        self.assertIn(video_path, known)


if __name__ == "__main__":
    unittest.main()
