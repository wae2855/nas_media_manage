#!/usr/bin/env python3
import os
import shutil
from pathlib import Path
from safety import validate_file_ext, check_read_permission, check_write_permission, ALLOWED_MEDIA_EXTS


class FileCopier:
    def __init__(self, temp_dir: str):
        self.temp_dir = temp_dir
        os.makedirs(temp_dir, exist_ok=True)

    def check_disk_space(self, file_size: int) -> bool:
        stat = shutil.disk_usage(self.temp_dir)
        return stat.free >= file_size * 1.5

    def copy_file_with_marker(self, src: str, dest: str, progress_callback=None):
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

        os.rename(temp_dest, dest)
        return dest

    def copy_to_temp(self, video_path: str, subtitle_paths: list[str],
                     progress_callback=None) -> list[str]:
        ok, msg = check_write_permission(self.temp_dir)
        if not ok:
            raise IOError(f"临时目录不可写: {msg}")

        copied_files = []

        video_filename = os.path.basename(video_path)
        dest_video = os.path.join(self.temp_dir, video_filename)
        self.copy_file_with_marker(video_path, dest_video, progress_callback)
        copied_files.append(dest_video)

        for sub_path in subtitle_paths:
            sub_filename = os.path.basename(sub_path)
            dest_sub = os.path.join(self.temp_dir, sub_filename)
            self.copy_file_with_marker(sub_path, dest_sub, progress_callback)
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
