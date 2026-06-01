#!/usr/bin/env python3
import os
import shutil
import hashlib

from media_importer.domains.recycle import (
    move_to_recycle,
    move_to_recycle_with_companions,
    move_dir_to_recycle,
    list_recycle_dir,
    restore_from_recycle,
    delete_from_recycle,
    recycle_cleanup,
)


def validate_path_safety(path: str, allowed_base_dirs: list = None) -> tuple:
    real = os.path.realpath(path)
    if ".." in path or ".." in real:
        return False, f"路径包含目录穿越: {path}"
    if allowed_base_dirs:
        allowed_real = [os.path.realpath(d) for d in allowed_base_dirs if d]
        if not any(real.startswith(base) for base in allowed_real):
            return False, "Path not in allowed directories"
    return True, ""


def validate_file_ext(path: str, allowed_exts: set = None) -> tuple:
    ext = os.path.splitext(path)[1].lower()
    if allowed_exts is None:
        return True, ""
    if ext not in allowed_exts:
        return False, f"不允许的文件扩展名: {ext} (文件: {os.path.basename(path)})"
    return True, ""


def safe_delete(path: str, allowed_base_dirs: list = None) -> tuple:
    if not os.path.exists(path):
        return True, ""

    ok, msg = validate_path_safety(path, allowed_base_dirs)
    if not ok:
        return False, msg

    real = os.path.realpath(path)
    if os.path.isdir(real):
        return False, f"拒绝删除目录: {path}"

    if not os.path.isfile(real):
        return False, f"非普通文件，拒绝删除: {path}"

    try:
        file_size = os.path.getsize(real)
        if file_size > 50 * 1024 * 1024 * 1024:
            return False, f"文件过大({file_size/(1024**3):.1f}GB)，拒绝删除: {path}"
    except OSError:
        return False, f"无法获取文件大小: {path}"

    try:
        os.remove(real)
        return True, f"已删除: {os.path.basename(path)}"
    except PermissionError:
        return False, f"权限不足，无法删除: {path}"
    except OSError as e:
        return False, f"删除失败: {e}"


def safe_move(src: str, dest: str, allowed_base_dirs: list = None) -> tuple:
    ok, msg = validate_path_safety(src, allowed_base_dirs)
    if not ok:
        return False, f"源路径安全检查失败: {msg}"

    ok, msg = validate_path_safety(dest, allowed_base_dirs)
    if not ok:
        return False, f"目标路径安全检查失败: {msg}"

    if os.path.exists(dest):
        return False, f"目标文件已存在: {dest}"

    dest_dir = os.path.dirname(dest)
    try:
        os.makedirs(dest_dir, exist_ok=True)
    except PermissionError:
        return False, f"权限不足，无法创建目录: {dest_dir}"
    except OSError as e:
        return False, f"创建目录失败: {e}"

    try:
        os.rename(src, dest)
        return True, f"已移动: {os.path.basename(src)} -> {dest}"
    except OSError:
        try:
            shutil.copy2(src, dest)
            os.remove(src)
            return True, f"已复制+删除: {os.path.basename(src)} -> {dest}"
        except PermissionError:
            return False, f"权限不足，跨设备移动失败: {src} -> {dest}"
        except OSError as e:
            return False, f"移动失败: {e}"


def check_write_permission(directory: str) -> tuple:
    if not os.path.exists(directory):
        try:
            os.makedirs(directory, exist_ok=True)
        except PermissionError:
            return False, f"权限不足，无法创建目录: {directory}"
        except OSError as e:
            return False, f"创建目录失败: {e}"

    test_file = os.path.join(directory, ".write_test")
    try:
        with open(test_file, "w") as f:
            f.write("test")
        os.remove(test_file)
        return True, ""
    except PermissionError:
        return False, f"目录无写入权限: {directory}"
    except OSError as e:
        return False, f"写入测试失败: {e}"


def check_read_permission(path: str) -> tuple:
    if not os.path.exists(path):
        return False, f"路径不存在: {path}"
    try:
        if os.path.isdir(path):
            os.listdir(path)
            return True, ""
        else:
            with open(path, "rb") as f:
                f.read(1)
            return True, ""
    except PermissionError:
        return False, f"无读取权限: {path}"
    except OSError as e:
        return False, f"读取测试失败: {e}"


def make_fingerprint(file_path: str) -> str:
    try:
        stat = os.stat(file_path)
        raw = f"{stat.st_size}:{stat.st_mtime:.1f}"
        return hashlib.sha256(raw.encode()).hexdigest()[:16]
    except OSError:
        return ""
