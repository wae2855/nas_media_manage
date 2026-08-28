import os
import shutil
import sys
import time
from typing import Optional

from media_importer.infrastructure.filesystem.safety import (
    check_read_permission,
    check_write_permission,
    hash_file,
    validate_file_ext,
    verified_copy,
)


class FileCopier:
    def __init__(self, temp_dir: str, media_extensions: Optional[set] = None):
        self.temp_dir = temp_dir
        self.media_extensions = media_extensions
        self._available = True
        if not temp_dir or not os.path.isdir(temp_dir):
            if temp_dir:
                print(f"WARNING: 中转目录不存在 {temp_dir}，请恢复挂载或在配置页修改", file=sys.stderr)
            self._available = False

    def check_disk_space(self, file_size: int) -> bool:
        try:
            stat = shutil.disk_usage(self.temp_dir)
            safety_reserve = max(1024 ** 3, int(stat.total * 0.05))
            return stat.free >= file_size + safety_reserve
        except (AttributeError, OSError):
            return False

    def copy_file_with_marker(
        self, src: str, dest: str, progress_callback=None, heartbeat_callback=None, heartbeat_interval=30
    ):
        """
        带标记的文件拷贝，支持断点续传、进度和心跳

        Args:
            src: 源文件路径
            dest: 目标文件路径
            progress_callback: 进度回调函数 (copied_bytes, total_bytes)
            heartbeat_callback: 心跳回调函数
            heartbeat_interval: 心跳间隔（秒）
        """
        ok, msg = check_read_permission(src)
        if not ok:
            raise IOError(f"源文件不可读: {msg}")

        ok, msg = validate_file_ext(src, self.media_extensions)
        if not ok:
            raise IOError(f"源文件类型不允许: {msg}")

        file_size = os.path.getsize(src)

        if not self.check_disk_space(file_size):
            raise IOError(f"磁盘空间不足，需要 {file_size * 1.5} 字节")

        last_heartbeat = time.time()

        if os.path.exists(dest):
            if os.path.getsize(dest) == file_size and hash_file(dest) == hash_file(src):
                return dest
            raise IOError(f"中转目标已存在且内容不同: {dest}")

        def on_progress(copied_bytes, total_bytes):
            nonlocal last_heartbeat
            if progress_callback:
                progress_callback(copied_bytes, total_bytes)
            if heartbeat_callback and (time.time() - last_heartbeat >= heartbeat_interval):
                heartbeat_callback()
                last_heartbeat = time.time()

        ok, message = verified_copy(src, dest, progress_callback=on_progress)
        if not ok:
            raise IOError(message)
        return dest

    def copy_to_temp(
        self,
        video_path: str,
        subtitle_paths: list[str],
        progress_callback=None,
        heartbeat_callback=None,
        heartbeat_interval=30,
    ) -> list[str]:
        if not self._available or not self.temp_dir or not os.path.isdir(self.temp_dir):
            raise IOError("中转目录不存在或挂载已失效，拒绝自动创建")
        ok, msg = check_write_permission(self.temp_dir)
        if not ok:
            raise IOError(f"临时目录不可写: {msg}")

        copied_files = []

        video_filename = os.path.basename(video_path)
        dest_video = os.path.join(self.temp_dir, video_filename)
        self.copy_file_with_marker(video_path, dest_video, progress_callback, heartbeat_callback, heartbeat_interval)
        copied_files.append(dest_video)

        for sub_path in subtitle_paths:
            sub_filename = os.path.basename(sub_path)
            dest_sub = os.path.join(self.temp_dir, sub_filename)
            self.copy_file_with_marker(sub_path, dest_sub, progress_callback, heartbeat_callback, heartbeat_interval)
            copied_files.append(dest_sub)

        return copied_files

    def cleanup_residual_copies(self):
        for filename in os.listdir(self.temp_dir):
            if filename.endswith(".copying"):
                filepath = os.path.join(self.temp_dir, filename)
                try:
                    os.remove(filepath)
                except OSError:
                    pass
