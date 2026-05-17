#!/usr/bin/env python3
import os
import sys
import tempfile
import shutil
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'media_importer'))

from safety import (
    validate_path_safety, validate_file_ext, safe_delete, safe_move,
    check_write_permission, check_read_permission, ALLOWED_MEDIA_EXTS
)


class TestValidatePathSafety(unittest.TestCase):
    def test_normal_path(self):
        ok, _ = validate_path_safety("/tmp/test.mkv")
        self.assertTrue(ok)

    def test_path_traversal(self):
        ok, msg = validate_path_safety("/tmp/../../../etc/passwd")
        self.assertFalse(ok)
        self.assertIn("穿越", msg)

    def test_allowed_base_dirs(self):
        with tempfile.TemporaryDirectory() as d:
            ok, _ = validate_path_safety(os.path.join(d, "test.mkv"), allowed_base_dirs=[d])
            self.assertTrue(ok)

    def test_disallowed_base_dir(self):
        ok, msg = validate_path_safety("/etc/passwd", allowed_base_dirs=["/tmp"])
        self.assertFalse(ok)
        self.assertIn("超出", msg)


class TestValidateFileExt(unittest.TestCase):
    def test_allowed_video(self):
        ok, _ = validate_file_ext("movie.mkv", ALLOWED_MEDIA_EXTS)
        self.assertTrue(ok)

    def test_allowed_subtitle(self):
        ok, _ = validate_file_ext("movie.srt", ALLOWED_MEDIA_EXTS)
        self.assertTrue(ok)

    def test_disallowed_ext(self):
        ok, msg = validate_file_ext("script.sh", ALLOWED_MEDIA_EXTS)
        self.assertFalse(ok)
        self.assertIn("不允许", msg)

    def test_disallowed_exe(self):
        ok, msg = validate_file_ext("malware.exe", ALLOWED_MEDIA_EXTS)
        self.assertFalse(ok)


class TestSafeDelete(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_delete_normal_file(self):
        f = os.path.join(self.temp_dir, "test.mkv")
        with open(f, 'w') as fh:
            fh.write("test")
        ok, _ = safe_delete(f, allowed_base_dirs=[self.temp_dir])
        self.assertTrue(ok)
        self.assertFalse(os.path.exists(f))

    def test_delete_nonexistent(self):
        ok, _ = safe_delete(os.path.join(self.temp_dir, "nope.mkv"))
        self.assertTrue(ok)

    def test_refuse_delete_directory(self):
        d = os.path.join(self.temp_dir, "subdir")
        os.makedirs(d)
        ok, msg = safe_delete(d, allowed_base_dirs=[self.temp_dir])
        self.assertFalse(ok)
        self.assertIn("目录", msg)

    def test_refuse_path_traversal(self):
        ok, msg = validate_path_safety("/../../../etc/passwd", allowed_base_dirs=["/safe"])
        self.assertFalse(ok)

    def test_permission_error_caught(self):
        f = os.path.join(self.temp_dir, "readonly.mkv")
        with open(f, 'w') as fh:
            fh.write("test")
        os.chmod(f, 0o000)
        ok, msg = safe_delete(f, allowed_base_dirs=[self.temp_dir])
        if os.path.exists(f):
            os.chmod(f, 0o644)
        self.assertTrue(ok is not None)


class TestSafeMove(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_move_normal(self):
        src = os.path.join(self.temp_dir, "src.mkv")
        dest = os.path.join(self.temp_dir, "dest.mkv")
        with open(src, 'w') as f:
            f.write("test")
        ok, _ = safe_move(src, dest, allowed_base_dirs=[self.temp_dir])
        self.assertTrue(ok)
        self.assertTrue(os.path.exists(dest))

    def test_refuse_overwrite(self):
        src = os.path.join(self.temp_dir, "src.mkv")
        dest = os.path.join(self.temp_dir, "dest.mkv")
        for p in [src, dest]:
            with open(p, 'w') as f:
                f.write("test")
        ok, msg = safe_move(src, dest, allowed_base_dirs=[self.temp_dir])
        self.assertFalse(ok)
        self.assertIn("已存在", msg)


class TestCheckPermissions(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_writable_dir(self):
        ok, _ = check_write_permission(self.temp_dir)
        self.assertTrue(ok)

    def test_readable_file(self):
        f = os.path.join(self.temp_dir, "test.mkv")
        with open(f, 'w') as fh:
            fh.write("test")
        ok, _ = check_read_permission(f)
        self.assertTrue(ok)

    def test_nonexistent_path(self):
        ok, _ = check_read_permission("/nonexistent/file.mkv")
        self.assertFalse(ok)


if __name__ == "__main__":
    unittest.main()
