#!/usr/bin/env python3
import subprocess
import os


class HookRunner:
    def __init__(self, config: dict, logger=None):
        hooks_cfg = config.get("hooks", {})
        self.allowed_dir = hooks_cfg.get("allowed_dir", "")
        self.before_process = hooks_cfg.get("before_process", "")
        self.after_success = hooks_cfg.get("after_success", "")
        self.after_failure = hooks_cfg.get("after_failure", "")
        self.logger = logger

    def _log(self, level: str, message: str):
        if self.logger:
            log_method = getattr(self.logger, level.lower(), self.logger.info)
            log_method(message)

    def _validate_hook_path(self, hook_path: str, hook_name: str) -> bool:
        if not hook_path or not hook_path.strip():
            return True

        hook_path = hook_path.strip()

        if not os.path.isabs(hook_path):
            self._log("error", f"钩子 {hook_name} 路径必须是绝对路径: {hook_path}")
            return False

        if ".." in hook_path:
            self._log("error", f"钩子 {hook_name} 路径包含目录穿越: {hook_path}")
            return False

        real_path = os.path.realpath(hook_path)

        if self.allowed_dir:
            allowed_real = os.path.realpath(self.allowed_dir)
            if not real_path.startswith(allowed_real + os.sep) and real_path != allowed_real:
                self._log("error", f"钩子 {hook_name} 脚本不在允许目录 {self.allowed_dir} 内: {hook_path}")
                return False

        return True

    def _run_hook(self, hook_path: str, hook_name: str, env: dict = None) -> bool:
        if not hook_path or not hook_path.strip():
            return True

        hook_path = hook_path.strip()

        if not self._validate_hook_path(hook_path, hook_name):
            self._log("error", f"钩子 {hook_name} 路径校验失败，拒绝执行")
            return False

        if not os.path.isfile(hook_path):
            self._log("warn", f"钩子脚本不存在: {hook_path} ({hook_name})")
            return True

        if not os.access(hook_path, os.X_OK):
            self._log("warn", f"钩子脚本无执行权限: {hook_path} ({hook_name})")
            return True

        hook_env = os.environ.copy()
        if env:
            hook_env.update({k: str(v) for k, v in env.items()})

        try:
            result = subprocess.run(
                [hook_path],
                env=hook_env,
                capture_output=True,
                text=True,
                timeout=60
            )
            if result.returncode != 0:
                self._log("warn",
                    f"钩子 {hook_name} 返回非零退出码 {result.returncode}: "
                    f"{result.stderr.strip()[:200]}")
            else:
                self._log("info", f"钩子 {hook_name} 执行成功")
            return True
        except subprocess.TimeoutExpired:
            self._log("warn", f"钩子 {hook_name} 执行超时 (60s)")
            return True
        except Exception as e:
            self._log("warn", f"钩子 {hook_name} 执行异常: {e}")
            return True

    def run_before_process(self, task_info: dict) -> bool:
        env = {
            "HOOK_NAME": "before_process",
            "TASK_ID": task_info.get("task_id", ""),
            "VIDEO_FILE": task_info.get("video_file", ""),
            "VIDEO_PATH": task_info.get("video_path", ""),
        }
        return self._run_hook(self.before_process, "before_process", env)

    def run_after_success(self, task_info: dict) -> bool:
        env = {
            "HOOK_NAME": "after_success",
            "TASK_ID": task_info.get("task_id", ""),
            "VIDEO_FILE": task_info.get("video_file", ""),
            "IMPORT_PATH": task_info.get("import_path", ""),
            "FINAL_FILENAME": task_info.get("final_filename", ""),
        }
        return self._run_hook(self.after_success, "after_success", env)

    def run_after_failure(self, task_info: dict) -> bool:
        env = {
            "HOOK_NAME": "after_failure",
            "TASK_ID": task_info.get("task_id", ""),
            "VIDEO_FILE": task_info.get("video_file", ""),
            "ERROR_MESSAGE": task_info.get("error_message", ""),
        }
        return self._run_hook(self.after_failure, "after_failure", env)
