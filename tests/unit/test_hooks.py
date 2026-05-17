#!/usr/bin/env python3
import json
import os
import stat
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'media_importer'))

from hooks import HookRunner


class TestHookRunner(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.config = {
            "hooks": {
                "before_process": "",
                "after_success": "",
                "after_failure": ""
            }
        }
        self.runner = HookRunner(self.config)

    def tearDown(self):
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_empty_hooks(self):
        self.assertTrue(self.runner.run_before_process({"task_id": "abc"}))
        self.assertTrue(self.runner.run_after_success({"task_id": "abc"}))
        self.assertTrue(self.runner.run_after_failure({"task_id": "abc"}))

    def test_no_hooks_config(self):
        runner = HookRunner({})
        self.assertTrue(runner.run_before_process({"task_id": "abc"}))

    def test_hook_script_not_found(self):
        config = {
            "hooks": {
                "before_process": "/nonexistent/script.sh",
                "after_success": "",
                "after_failure": ""
            }
        }
        runner = HookRunner(config)
        self.assertTrue(runner.run_before_process({"task_id": "abc"}))

    def test_hook_script_no_execute_permission(self):
        script = os.path.join(self.temp_dir, "hook.sh")
        with open(script, "w") as f:
            f.write("#!/bin/bash\necho ok\n")
        os.chmod(script, stat.S_IRUSR)

        config = {
            "hooks": {
                "before_process": script,
                "after_success": "",
                "after_failure": ""
            }
        }
        runner = HookRunner(config)
        self.assertTrue(runner.run_before_process({"task_id": "abc"}))

    def test_hook_script_success(self):
        output_file = os.path.join(self.temp_dir, "output.txt")
        script = os.path.join(self.temp_dir, "hook.sh")
        with open(script, "w") as f:
            f.write(f"#!/bin/bash\necho $TASK_ID > {output_file}\n")
        os.chmod(script, stat.S_IRUSR | stat.S_IXUSR)

        config = {
            "hooks": {
                "before_process": script,
                "after_success": "",
                "after_failure": ""
            }
        }
        runner = HookRunner(config)
        self.assertTrue(runner.run_before_process({"task_id": "test123", "video_file": "a.mkv"}))

        with open(output_file) as f:
            self.assertEqual(f.read().strip(), "test123")

    def test_hook_after_success_env(self):
        output_file = os.path.join(self.temp_dir, "output.txt")
        script = os.path.join(self.temp_dir, "hook.sh")
        with open(script, "w") as f:
            f.write(f"#!/bin/bash\necho $HOOK_NAME:$IMPORT_PATH > {output_file}\n")
        os.chmod(script, stat.S_IRUSR | stat.S_IXUSR)

        config = {
            "hooks": {
                "before_process": "",
                "after_success": script,
                "after_failure": ""
            }
        }
        runner = HookRunner(config)
        self.assertTrue(runner.run_after_success({
            "task_id": "abc",
            "import_path": "/movies/Inception/"
        }))

        with open(output_file) as f:
            content = f.read().strip()
            self.assertIn("after_success", content)
            self.assertIn("/movies/Inception/", content)

    def test_hook_after_failure_env(self):
        output_file = os.path.join(self.temp_dir, "output.txt")
        script = os.path.join(self.temp_dir, "hook.sh")
        with open(script, "w") as f:
            f.write(f"#!/bin/bash\necho $HOOK_NAME:$ERROR_MESSAGE > {output_file}\n")
        os.chmod(script, stat.S_IRUSR | stat.S_IXUSR)

        config = {
            "hooks": {
                "before_process": "",
                "after_success": "",
                "after_failure": script
            }
        }
        runner = HookRunner(config)
        self.assertTrue(runner.run_after_failure({
            "task_id": "abc",
            "error_message": "disk full"
        }))

        with open(output_file) as f:
            content = f.read().strip()
            self.assertIn("after_failure", content)
            self.assertIn("disk full", content)

    def test_hook_nonzero_exit_does_not_crash(self):
        script = os.path.join(self.temp_dir, "hook.sh")
        with open(script, "w") as f:
            f.write("#!/bin/bash\nexit 1\n")
        os.chmod(script, stat.S_IRUSR | stat.S_IXUSR)

        config = {
            "hooks": {
                "before_process": script,
                "after_success": "",
                "after_failure": ""
            }
        }
        runner = HookRunner(config)
        self.assertTrue(runner.run_before_process({"task_id": "abc"}))

    def test_hook_timeout_does_not_crash(self):
        script = os.path.join(self.temp_dir, "hook.sh")
        with open(script, "w") as f:
            f.write("#!/bin/bash\nsleep 120\n")
        os.chmod(script, stat.S_IRUSR | stat.S_IXUSR)

        config = {
            "hooks": {
                "before_process": script,
                "after_success": "",
                "after_failure": ""
            }
        }
        runner = HookRunner(config)
        self.assertTrue(runner.run_before_process({"task_id": "abc"}))


if __name__ == "__main__":
    unittest.main()
