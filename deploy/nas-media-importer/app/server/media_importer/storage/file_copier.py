#!/usr/bin/env python3
import os
import sys
import time
import shutil
from media_importer.core.safety import validate_file_ext, check_read_permission, check_write_permission, ALLOWED_MEDIA_EXTS


class FileCopier:
    def __init__(self, temp_dir: str):
        self.temp_dir = temp_dir
        self._available = True
        try:
            if temp_dir:
                os.makedirs(temp_dir, exist_ok=True)
            else:
                self._available = False
        except (OSError, PermissionError) as e:
            print(f"WARNING: 无法创建中转目录 {temp_dir}: {e}，请在前台配置页修改", file=sys.stderr)
            self._available = False

    def check_disk_space(self, file_size: int) -> bool:
        try:
            stat = shutil.disk_usage(self.temp_dir)
            return stat.free >= file_size * 1.5
        except (AttributeError, OSError):
            # 如果 shutil.disk_usage 不可用，尝试简化检查
            return True

    def copy_file_with_marker(self, src: str, dest: str, progress_callback=None, 
                              heartbeat_callback=None, heartbeat_interval=30):
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

        ok, msg = validate_file_ext(src, ALLOWED_MEDIA_EXTS)
        if not ok:
            raise IOError(f"源文件类型不允许: {msg}")

        temp_dest = dest + '.copying'
        file_size = os.path.getsize(src)

        if not self.check_disk_space(file_size):
            raise IOError(f"磁盘空间不足，需要 {file_size * 1.5} 字节")

        copied_bytes = 0
        if os.path.exists(temp_dest):
            copied_bytes = os.path.getsize(temp_dest)

        mode = 'ab' if copied_bytes > 0 else 'wb'
        last_heartbeat = time.time()

        with open(src, 'rb') as fsrc, open(temp_dest, mode) as fdst:
            if copied_bytes > 0:
                fsrc.seek(copied_bytes)

            while True:
                buf = fsrc.read(1024 * 1024)
                if not buf:
                    break
                fdst.write(buf)
                copied_bytes += len(buf)

                if progress_callback:
                    progress_callback(copied_bytes, file_size)

                # 心跳检查
                if heartbeat_callback and (time.time() - last_heartbeat >= heartbeat_interval):
                    heartbeat_callback()
                    last_heartbeat = time.time()

        os.rename(temp_dest, dest)
        return dest

    def copy_to_temp(self, video_path: str, subtitle_paths: list[str],
                     progress_callback=None, heartbeat_callback=None, 
                     heartbeat_interval=30) -> list[str]:
        ok, msg = check_write_permission(self.temp_dir)
        if not ok:
            raise IOError(f"临时目录不可写: {msg}")

        copied_files = []

        video_filename = os.path.basename(video_path)
        dest_video = os.path.join(self.temp_dir, video_filename)
        self.copy_file_with_marker(
            video_path, dest_video, 
            progress_callback, 
            heartbeat_callback, 
            heartbeat_interval
        )
        copied_files.append(dest_video)

        for sub_path in subtitle_paths:
            sub_filename = os.path.basename(sub_path)
            dest_sub = os.path.join(self.temp_dir, sub_filename)
            self.copy_file_with_marker(
                sub_path, dest_sub, 
                progress_callback, 
                heartbeat_callback, 
                heartbeat_interval
            )
            copied_files.append(dest_sub)

        return copied_files

    def cleanup_residual_copies(self):
        for filename in os.listdir(self.temp_dir):
            if filename.endswith('.copying'):
                filepath = os.path.join(self.temp_dir, filename)
                try:
                    os.remove(filepath)
                except OSError:
                    pass
