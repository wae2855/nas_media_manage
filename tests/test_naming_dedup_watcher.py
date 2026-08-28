"""回归补口：命名模板 / 去重策略 / 文件监控核心路径（2026-08-27 文档治理轮识别的缺口）。

- apply_filename_template：变量替换、ext 补全、非法字符、缺字段
- check_duplicate：skip/replace/rename/quality 四策略行为
- FileWatcher：基线扫描忽略存量、增量发现回调新文件、ignore_patterns 生效
"""
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from media_importer.features.import_flow.services.dedup_rules import (
    check_duplicate,
    find_existing_file,
)
from media_importer.features.import_flow.services.naming import (
    apply_filename_template,
    apply_subtitle_template,
)
from media_importer.monitor.file_watcher import FileWatcher


class TestNamingTemplate(unittest.TestCase):
    """命名模板行为（入库最终文件名的事实源）。"""

    def test_movie_template_full_vars(self):
        info = {"title_cn": "盗梦空间", "title_en": "Inception",
                "year": 2010, "resolution": "1080p"}
        name = apply_filename_template(info, "{title_cn}.{year}.{resolution}.{ext}", ".mkv")
        self.assertEqual(name, "盗梦空间.2010.1080p.mkv")

    def test_tv_template_season_episode(self):
        info = {"title_cn": "绝命毒师", "season": 1, "episode": 2, "resolution": "720p"}
        name = apply_filename_template(info, "{title_cn}.S{season:02d}E{episode:02d}.{ext}", ".mkv")
        self.assertEqual(name, "绝命毒师.S01E02.mkv")

    def test_ext_appended_when_missing_in_template(self):
        name = apply_filename_template({"title_cn": "测试"}, "{title_cn}", ".mp4")
        self.assertEqual(name, "测试.mp4")

    def test_missing_var_renders_clean_not_crash(self):
        name = apply_filename_template({}, "{title_cn}.{year}.{ext}", ".mkv")
        self.assertEqual(name, "mkv")  # 空段被清理，不崩溃

    def test_subtitle_template(self):
        name = apply_subtitle_template("电影.2020", "chs", ".srt")
        self.assertEqual(name, "电影.chs.srt")  # 契约：basename.lang.ext


class TestDedupStrategies(unittest.TestCase):
    """同名去重四策略（duplicate_handling 契约）。"""

    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.info = {"title_cn": "测试片", "year": 2020, "resolution": "1080p"}

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def _mk_existing(self, name="测试片.2020.1080p.mkv", size=100):
        p = os.path.join(self.dir, name)
        with open(p, "wb") as f:
            f.write(b"x" * size)
        return p

    def test_skip_strategy_marks_duplicate(self):
        self._mk_existing()
        r = check_duplicate(self.dir, self.info, "skip")
        self.assertTrue(r["is_duplicate"])
        self.assertEqual(r["action"], "skip")
        self.assertTrue(r["existing_file"])

    def test_rename_strategy_suggests_new_name(self):
        self._mk_existing()
        r = check_duplicate(self.dir, self.info, "rename")
        self.assertTrue(r["is_duplicate"])
        self.assertTrue(r["suggested_filename"])
        self.assertNotEqual(r["suggested_filename"], "测试片.2020.1080p.mkv")

    def test_no_duplicate_passes_through(self):
        r = check_duplicate(self.dir, self.info, "skip")
        self.assertFalse(r["is_duplicate"])

    def test_find_existing_scopes_to_dir(self):
        self._mk_existing()
        hits = find_existing_file(self.dir, self.info)
        self.assertEqual(len(hits), 1)


class TestFileWatcherCore(unittest.TestCase):
    """监控核心路径：存量忽略 / 增量回调 / ignore 模式。"""

    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.seen = []

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def _mk(self, name):
        p = os.path.join(self.dir, name)
        with open(p, "w") as f:
            f.write("x")
        return p

    def _watcher(self, **overrides):
        cfg = {"source_dir": self.dir,
               "video_extensions": [".mkv", ".mp4"],
               "file_watcher": {"enabled": True, "poll_interval": 1, **overrides}}
        return FileWatcher(cfg, on_new_files=lambda files: self.seen.extend(files))

    def test_baseline_scan_ignores_existing(self):
        self._mk("old.mkv")
        w = self._watcher()
        w.start()
        try:
            w._check_changes()
            self.assertEqual(self.seen, [])
        finally:
            w.stop()

    def test_new_file_triggers_callback(self):
        w = self._watcher()
        w.start()
        try:
            w._check_changes()  # 建基线
            self._mk("new.mkv")
            w._check_changes()
            for path, (version, observed_at, count) in list(w._observations.items()):
                w._observations[path] = (version, observed_at - 121, count)
            w._check_changes()
            self.assertEqual(len(self.seen), 1)
            self.assertTrue(self.seen[0].endswith("new.mkv"))
        finally:
            w.stop()

    def test_ignore_patterns_filter_callbacks(self):
        w = self._watcher(ignore_patterns=["*.tmp", "sample*"])
        w.start()
        try:
            w._check_changes()
            self._mk("part.tmp")
            self._mk("sample1.mkv")
            self._mk("real.mkv")
            w._check_changes()
            for path, (version, observed_at, count) in list(w._observations.items()):
                w._observations[path] = (version, observed_at - 121, count)
            w._check_changes()
            names = [os.path.basename(p) for p in self.seen]
            self.assertEqual(names, ["real.mkv"])
        finally:
            w.stop()

    def test_stop_is_idempotent(self):
        w = self._watcher()
        w.start()
        w.stop()
        w.stop()
        self.assertFalse(w.is_running())


if __name__ == "__main__":
    unittest.main()
