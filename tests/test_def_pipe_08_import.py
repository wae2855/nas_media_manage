#!/usr/bin/env python3
import os
import shutil
import stat
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from media_importer.features.import_flow.services.import_service import ImportService, ImportResult
from media_importer.features.import_flow.services.file_operations import move_to_import
from media_importer.features.source_files import SourceCleanupResult


def _make_config(source_dir=None, temp_dir=None, import_dir=None,
                 cleanup_source=False, recycle_dir=None):
    source = source_dir or tempfile.mkdtemp()
    temp = temp_dir or tempfile.mkdtemp()
    imp = import_dir or tempfile.mkdtemp()
    recycle = recycle_dir or tempfile.mkdtemp()
    return {
        "source_dir": source,
        "temp_dir": temp,
        "path_rules": [{"conditions": {}, "template": imp}],
        "video_extensions": [".mkv", ".mp4"],
        "subtitle_extensions": [".srt", ".ass"],
        "filename_templates": {
            "movie": "{title_cn}.{title_en}.{year}.{ext}",
            "tv": "{title_cn}.{title_en}.{year}.S{season}E{episode}.{ext}",
        },
        "source_policy": {
            "recycle_dir": recycle,
            "cleanup_source_after_done": cleanup_source,
        },
        "duplicate_handling": {"enabled": False, "strategy": "skip"},
        "manual_review": {"enabled": False},
    }


class TestImportBasic(unittest.TestCase):
    def setUp(self):
        self.src_dir = tempfile.mkdtemp()
        self.tmp_dir = tempfile.mkdtemp()
        self.imp_dir = tempfile.mkdtemp()
        self.video_path = os.path.join(self.tmp_dir, "video.mkv")
        with open(self.video_path, "wb") as f:
            f.write(b"video_content")

    def tearDown(self):
        shutil.rmtree(self.src_dir, ignore_errors=True)
        shutil.rmtree(self.tmp_dir, ignore_errors=True)
        shutil.rmtree(self.imp_dir, ignore_errors=True)

    def test_import_basic(self):
        config = _make_config(
            source_dir=self.src_dir,
            temp_dir=self.tmp_dir,
            import_dir=self.imp_dir,
        )
        task = {
            "task_id": "test-1",
            "video_path": self.video_path,
            "subtitle_files": [],
            "import_path": self.imp_dir,
            "scrape_result": {
                "title_cn": "测试",
                "title_en": "Test",
                "year": "2024",
                "type": "movie",
            },
        }
        mock_cleanup = MagicMock()
        mock_cleanup.cleanup_source_after_import.return_value = SourceCleanupResult()
        mock_cleanup.cleanup_temp_file.return_value = SourceCleanupResult()

        service = ImportService(config, conn=None, cleanup_service=mock_cleanup)
        result = service.import_task(
            task, self.video_path, [], overwrite=False
        )
        self.assertIsInstance(result, ImportResult)
        self.assertTrue(os.path.isfile(result.video_path))


class TestImportCreateTargetDir(unittest.TestCase):
    def setUp(self):
        self.src_dir = tempfile.mkdtemp()
        self.tmp_dir = tempfile.mkdtemp()
        self.base_dir = tempfile.mkdtemp()
        self.new_target = os.path.join(self.base_dir, "new_subdir", "deeper")
        self.video_path = os.path.join(self.tmp_dir, "video.mkv")
        with open(self.video_path, "wb") as f:
            f.write(b"video_content")

    def tearDown(self):
        shutil.rmtree(self.src_dir, ignore_errors=True)
        shutil.rmtree(self.tmp_dir, ignore_errors=True)
        shutil.rmtree(self.base_dir, ignore_errors=True)

    def test_import_create_target_dir(self):
        config = _make_config(
            source_dir=self.src_dir,
            temp_dir=self.tmp_dir,
            import_dir=self.new_target,
        )
        task = {
            "task_id": "test-2",
            "video_path": self.video_path,
            "subtitle_files": [],
            "import_path": self.new_target,
            "scrape_result": {
                "title_cn": "测试",
                "title_en": "Test",
                "year": "2024",
                "type": "movie",
            },
        }
        mock_cleanup = MagicMock()
        mock_cleanup.cleanup_source_after_import.return_value = SourceCleanupResult()
        mock_cleanup.cleanup_temp_file.return_value = SourceCleanupResult()

        service = ImportService(config, conn=None, cleanup_service=mock_cleanup)
        result = service.import_task(
            task, self.video_path, [], overwrite=False
        )
        self.assertTrue(os.path.isdir(self.new_target))
        self.assertTrue(os.path.isfile(result.video_path))


class TestImportNoWritePerm(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp()
        self.imp_dir = tempfile.mkdtemp()
        self.video_path = os.path.join(self.tmp_dir, "video.mkv")
        with open(self.video_path, "wb") as f:
            f.write(b"video_content")
        # Remove write permission from import dir
        os.chmod(self.imp_dir, stat.S_IRUSR | stat.S_IXUSR)

    def tearDown(self):
        try:
            os.chmod(self.imp_dir, stat.S_IRWXU)
        except OSError:
            pass
        shutil.rmtree(self.tmp_dir, ignore_errors=True)
        shutil.rmtree(self.imp_dir, ignore_errors=True)

    def test_import_no_write_perm(self):
        with self.assertRaises(IOError):
            move_to_import(
                self.video_path,
                [],
                self.imp_dir,
                {"title_cn": "Test", "title_en": "Test", "year": "2024", "type": "movie"},
                {"movie": "{title_cn}.{ext}"},
                allowed_base_dirs=[self.tmp_dir, self.imp_dir],
                overwrite=False,
            )


class TestImportExistingFileNoOverwrite(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp()
        self.imp_dir = tempfile.mkdtemp()
        self.video_path = os.path.join(self.tmp_dir, "video.mkv")
        with open(self.video_path, "wb") as f:
            f.write(b"new_video")
        # Create existing file in import dir with the name that the template will produce
        existing = os.path.join(self.imp_dir, "测试.Test.2024.mkv")
        with open(existing, "wb") as f:
            f.write(b"old_video")

    def tearDown(self):
        shutil.rmtree(self.tmp_dir, ignore_errors=True)
        shutil.rmtree(self.imp_dir, ignore_errors=True)

    def test_import_existing_file_no_overwrite(self):
        with self.assertRaises(IOError) as ctx:
            move_to_import(
                self.video_path,
                [],
                self.imp_dir,
                {"title_cn": "测试", "title_en": "Test", "year": "2024", "type": "movie"},
                {"movie": "{title_cn}.{title_en}.{year}.{ext}"},
                allowed_base_dirs=[self.tmp_dir, self.imp_dir],
                overwrite=False,
            )
        self.assertIn("同名文件", str(ctx.exception))


class TestImportOverwrite(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp()
        self.imp_dir = tempfile.mkdtemp()
        self.video_path = os.path.join(self.tmp_dir, "video.mkv")
        with open(self.video_path, "wb") as f:
            f.write(b"new_video_content")
        # Create existing file
        existing = os.path.join(self.imp_dir, "测试.Test.2024.mkv")
        with open(existing, "wb") as f:
            f.write(b"old_video_content")

    def tearDown(self):
        shutil.rmtree(self.tmp_dir, ignore_errors=True)
        shutil.rmtree(self.imp_dir, ignore_errors=True)

    def test_import_overwrite(self):
        # Mock move_to_recycle and also remove the existing file so safe_move succeeds
        existing = os.path.join(self.imp_dir, "测试.Test.2024.mkv")

        def _fake_recycle(path, recycle_dir, **kwargs):
            if os.path.exists(path):
                os.remove(path)
            return (True, "/recycle/old.mkv", "ok")

        with patch("media_importer.features.import_flow.services.file_operations.move_to_recycle",
                    side_effect=_fake_recycle):
            result = move_to_import(
                self.video_path,
                [],
                self.imp_dir,
                {"title_cn": "测试", "title_en": "Test", "year": "2024", "type": "movie"},
                {"movie": "{title_cn}.{title_en}.{year}.{ext}"},
                allowed_base_dirs=[self.tmp_dir, self.imp_dir],
                overwrite=True,
            )
        self.assertTrue(os.path.isfile(result["video"]))
        with open(result["video"], "rb") as f:
            self.assertEqual(f.read(), b"new_video_content")


class TestImportSubtitleHandling(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp()
        self.imp_dir = tempfile.mkdtemp()
        self.video_path = os.path.join(self.tmp_dir, "video.mkv")
        self.sub_path = os.path.join(self.tmp_dir, "video.zh.srt")
        with open(self.video_path, "wb") as f:
            f.write(b"video_content")
        with open(self.sub_path, "wb") as f:
            f.write(b"subtitle_content")

    def tearDown(self):
        shutil.rmtree(self.tmp_dir, ignore_errors=True)
        shutil.rmtree(self.imp_dir, ignore_errors=True)

    def test_import_subtitle_handling(self):
        result = move_to_import(
            self.video_path,
            [self.sub_path],
            self.imp_dir,
            {"title_cn": "测试", "title_en": "Test", "year": "2024", "type": "movie"},
            {"movie": "{title_cn}.{title_en}.{year}.{ext}"},
            allowed_base_dirs=[self.tmp_dir, self.imp_dir],
            overwrite=False,
        )
        self.assertTrue(os.path.isfile(result["video"]))
        self.assertEqual(len(result["subtitles"]), 1)
        # Subtitle should have language tag in filename
        sub_name = os.path.basename(result["subtitles"][0])
        self.assertIn(".zh.", sub_name)


class TestImportSourceCleanup(unittest.TestCase):
    def setUp(self):
        self.src_dir = tempfile.mkdtemp()
        self.tmp_dir = tempfile.mkdtemp()
        self.imp_dir = tempfile.mkdtemp()
        self.recycle_dir = tempfile.mkdtemp()
        self.source_video = os.path.join(self.src_dir, "original.mkv")
        with open(self.source_video, "wb") as f:
            f.write(b"source_video")
        self.temp_video = os.path.join(self.tmp_dir, "video.mkv")
        with open(self.temp_video, "wb") as f:
            f.write(b"temp_video")

    def tearDown(self):
        shutil.rmtree(self.src_dir, ignore_errors=True)
        shutil.rmtree(self.tmp_dir, ignore_errors=True)
        shutil.rmtree(self.imp_dir, ignore_errors=True)
        shutil.rmtree(self.recycle_dir, ignore_errors=True)

    def test_import_source_cleanup(self):
        config = _make_config(
            source_dir=self.src_dir,
            temp_dir=self.tmp_dir,
            import_dir=self.imp_dir,
            cleanup_source=True,
            recycle_dir=self.recycle_dir,
        )
        task = {
            "task_id": "test-cleanup",
            "video_path": self.temp_video,
            "subtitle_files": [],
            "import_path": self.imp_dir,
            "scrape_result": {
                "title_cn": "测试",
                "title_en": "Test",
                "year": "2024",
                "type": "movie",
            },
        }
        # Mock the cleanup service to verify it's called
        mock_cleanup = MagicMock()
        mock_cleanup.cleanup_source_after_import.return_value = SourceCleanupResult(
            moved_count=1, message="已将源文件移入回收站: original.mkv"
        )
        mock_cleanup.cleanup_temp_file.return_value = SourceCleanupResult(
            deleted_count=1, message="已清理临时文件: video.mkv"
        )

        service = ImportService(config, conn=None, cleanup_service=mock_cleanup)
        result = service.import_task(
            task, self.source_video, [], overwrite=False
        )
        mock_cleanup.cleanup_source_after_import.assert_called_once()
        self.assertIn("移入回收站", result.source_cleanup.message)


if __name__ == "__main__":
    unittest.main()
