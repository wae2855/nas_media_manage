#!/usr/bin/env python3
import hashlib
import os
from typing import Optional

_COPY_CHUNK_SIZE = 1024 * 1024


def validate_path_safety(path: str, allowed_base_dirs: Optional[list] = None) -> tuple:
    real = os.path.realpath(path)
    if ".." in os.path.normpath(path).split(os.sep):
        return False, f"路径包含目录穿越: {path}"
    if allowed_base_dirs:
        allowed_real = [os.path.realpath(d) for d in allowed_base_dirs if d]
        if not any(_is_within(real, base) for base in allowed_real):
            return False, "Path not in allowed directories"
    return True, ""


def _is_within(path: str, base: str) -> bool:
    try:
        return os.path.commonpath([path, base]) == base
    except ValueError:
        return False


def _file_snapshot(path: str) -> tuple[int, int, int]:
    stat = os.stat(path, follow_symlinks=False)
    return stat.st_size, stat.st_mtime_ns, stat.st_ino


def hash_file(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        while chunk := handle.read(_COPY_CHUNK_SIZE):
            digest.update(chunk)
    return digest.hexdigest()


def _prefix_matches(src: str, partial: str, length: int) -> bool:
    if length <= 0:
        return True
    with open(src, "rb") as source, open(partial, "rb") as current:
        remaining = length
        while remaining:
            chunk_size = min(_COPY_CHUNK_SIZE, remaining)
            if source.read(chunk_size) != current.read(chunk_size):
                return False
            remaining -= chunk_size
    return True


def _fsync_parent(path: str) -> None:
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
    try:
        descriptor = os.open(os.path.dirname(path) or ".", flags)
    except OSError:
        return
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def verified_copy(src: str, dest: str, *, remove_source: bool = False,
                  progress_callback=None) -> tuple:
    """可续传、校验后发布的复制。

    中断只会留下 ``.copying``；源文件仅在目标完成 SHA-256 校验并原子
    发布后才会删除。续传前会逐字节校验已有前缀，防止把其他源版本拼接进来。
    """
    if not os.path.isfile(src):
        return False, f"源文件不存在或不是普通文件: {src}"
    if os.path.exists(dest):
        return False, f"目标文件已存在: {dest}"
    dest_dir = os.path.dirname(dest) or "."
    if not os.path.isdir(dest_dir):
        return False, f"目标目录不存在: {dest_dir}"

    source_snapshot = _file_snapshot(src)
    partial = dest + ".copying"
    copied = 0
    if os.path.exists(partial):
        copied = os.path.getsize(partial)
        if copied > source_snapshot[0] or not _prefix_matches(src, partial, copied):
            copied = 0

    mode = "ab" if copied else "wb"
    try:
        with open(src, "rb") as source, open(partial, mode) as target:
            source.seek(copied)
            while chunk := source.read(_COPY_CHUNK_SIZE):
                target.write(chunk)
                copied += len(chunk)
                if progress_callback:
                    progress_callback(copied, source_snapshot[0])
            target.flush()
            os.fsync(target.fileno())

        if _file_snapshot(src) != source_snapshot:
            return False, "复制期间源文件发生变化，保留源文件并等待稳定后重试"
        if os.path.getsize(partial) != source_snapshot[0]:
            return False, "目标临时文件大小校验失败"
        if hash_file(src) != hash_file(partial):
            return False, "目标临时文件 SHA-256 校验失败"
        if _file_snapshot(src) != source_snapshot:
            return False, "完整性校验期间源文件发生变化，保留源文件并等待重试"

        os.replace(partial, dest)
        _fsync_parent(dest)
        if remove_source:
            if _file_snapshot(src) != source_snapshot:
                return False, "目标已发布，但源文件随后发生变化，已保留源文件等待人工确认"
            os.remove(src)
            _fsync_parent(src)
        return True, f"已校验复制: {os.path.basename(src)} -> {dest}"
    except PermissionError:
        return False, f"权限不足，复制失败: {src} -> {dest}"
    except OSError as exc:
        return False, f"复制失败，源文件已保留: {exc}"


def validate_file_ext(path: str, allowed_exts: Optional[set] = None) -> tuple:
    ext = os.path.splitext(path)[1].lower()
    if allowed_exts is None:
        return True, ""
    if ext not in allowed_exts:
        return False, f"不允许的文件扩展名: {ext} (文件: {os.path.basename(path)})"
    return True, ""


def safe_delete(path: str, allowed_base_dirs: Optional[list] = None) -> tuple:
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
    except OSError as exc:
        return False, f"删除失败: {exc}"


def safe_move(src: str, dest: str, allowed_base_dirs: Optional[list] = None) -> tuple:
    ok, msg = validate_path_safety(src, allowed_base_dirs)
    if not ok:
        return False, f"源路径安全检查失败: {msg}"

    ok, msg = validate_path_safety(dest, allowed_base_dirs)
    if not ok:
        return False, f"目标路径安全检查失败: {msg}"

    if os.path.exists(dest):
        return False, f"目标文件已存在: {dest}"

    dest_dir = os.path.dirname(dest)
    if not os.path.isdir(dest_dir):
        return False, f"目标目录不存在，拒绝自动创建以避免挂载掉线误写: {dest_dir}"

    try:
        os.rename(src, dest)
        return True, f"已移动: {os.path.basename(src)} -> {dest}"
    except OSError:
        return verified_copy(src, dest, remove_source=True)


def check_write_permission(directory: str) -> tuple:
    if not os.path.exists(directory):
        try:
            os.makedirs(directory, exist_ok=True)
        except PermissionError:
            return False, f"权限不足，无法创建目录: {directory}"
        except OSError as exc:
            return False, f"创建目录失败: {exc}"

    test_file = os.path.join(directory, ".write_test")
    try:
        with open(test_file, "w") as file:
            file.write("test")
        os.remove(test_file)
        return True, ""
    except PermissionError:
        return False, f"目录无写入权限: {directory}"
    except OSError as exc:
        return False, f"写入测试失败: {exc}"


def check_read_permission(path: str) -> tuple:
    if not os.path.exists(path):
        return False, f"路径不存在: {path}"
    try:
        if os.path.isdir(path):
            os.listdir(path)
            return True, ""
        with open(path, "rb") as file:
            file.read(1)
        return True, ""
    except PermissionError:
        return False, f"无读取权限: {path}"
    except OSError as exc:
        return False, f"读取测试失败: {exc}"


def make_fingerprint(file_path: str) -> str:
    try:
        stat = os.stat(file_path)
        raw = f"{stat.st_size}:{stat.st_mtime:.1f}"
        return hashlib.sha256(raw.encode()).hexdigest()[:16]
    except OSError:
        return ""
