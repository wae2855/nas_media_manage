#!/usr/bin/env python3
import errno
import hashlib
import os
import stat
import tempfile
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


def _file_snapshot(path: str) -> tuple[int, int, int, int]:
    file_stat = os.stat(path, follow_symlinks=False)
    return file_stat.st_size, file_stat.st_mtime_ns, file_stat.st_dev, file_stat.st_ino


def _descriptor_snapshot(descriptor: int) -> tuple[int, int, int, int]:
    file_stat = os.fstat(descriptor)
    return file_stat.st_size, file_stat.st_mtime_ns, file_stat.st_dev, file_stat.st_ino


def _open_regular_nofollow(path: str, flags: int, mode: int = 0o600) -> int:
    descriptor = os.open(path, flags | getattr(os, "O_NOFOLLOW", 0), mode)
    file_stat = os.fstat(descriptor)
    if not stat.S_ISREG(file_stat.st_mode):
        os.close(descriptor)
        raise OSError(errno.EINVAL, f"不是普通文件: {path}")
    return descriptor


def hash_file(path: str) -> str:
    digest = hashlib.sha256()
    descriptor = _open_regular_nofollow(path, os.O_RDONLY)
    with os.fdopen(descriptor, "rb") as handle:
        while chunk := handle.read(_COPY_CHUNK_SIZE):
            digest.update(chunk)
    return digest.hexdigest()


def _prefix_matches(source, partial, length: int) -> bool:
    if length <= 0:
        return True
    source.seek(0)
    partial.seek(0)
    remaining = length
    while remaining:
        chunk_size = min(_COPY_CHUNK_SIZE, remaining)
        if source.read(chunk_size) != partial.read(chunk_size):
            return False
        remaining -= chunk_size
    return True


def _hash_open_file(handle) -> str:
    digest = hashlib.sha256()
    handle.seek(0)
    while chunk := handle.read(_COPY_CHUNK_SIZE):
        digest.update(chunk)
    return digest.hexdigest()


def _path_matches_snapshot(path: str, snapshot: tuple[int, int, int, int]) -> bool:
    try:
        file_stat = os.lstat(path)
    except OSError:
        return False
    return (
        stat.S_ISREG(file_stat.st_mode)
        and file_stat.st_nlink == 1
        and (file_stat.st_size, file_stat.st_mtime_ns, file_stat.st_dev, file_stat.st_ino) == snapshot
    )


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


def _publish_file_noreplace(
    staged: str,
    dest: str,
    *,
    expected_snapshot: Optional[tuple[int, int, int, int]] = None,
) -> None:
    """Atomically publish one same-filesystem file without replacing dest."""
    if expected_snapshot is not None and not _path_matches_snapshot(staged, expected_snapshot):
        raise OSError(errno.ESTALE, f"待发布临时文件发生变化: {staged}")
    staged_stat = os.lstat(staged)
    if not stat.S_ISREG(staged_stat.st_mode) or staged_stat.st_nlink != 1:
        raise OSError(errno.EINVAL, f"待发布路径不是独立普通文件: {staged}")
    os.link(staged, dest, follow_symlinks=False)
    try:
        os.unlink(staged)
    except OSError:
        # The destination is already a complete hard link to the verified bytes.
        pass
    _fsync_parent(dest)


def verified_copy(src: str, dest: str, *, remove_source: bool = False,
                  progress_callback=None) -> tuple:
    """可续传、校验后发布的复制。

    中断只会留下 ``.copying``；源文件仅在目标完成 SHA-256 校验并原子
    发布后才会删除。续传前会逐字节校验已有前缀，防止把其他源版本拼接进来。
    """
    if os.path.islink(src) or not os.path.isfile(src):
        return False, f"源文件不存在或不是普通文件: {src}"
    if os.path.lexists(dest):
        return False, f"目标文件已存在: {dest}"
    dest_dir = os.path.dirname(dest) or "."
    if not os.path.isdir(dest_dir):
        return False, f"目标目录不存在: {dest_dir}"

    partial = dest + ".copying"
    try:
        source_fd = _open_regular_nofollow(src, os.O_RDONLY)
        source_snapshot = _descriptor_snapshot(source_fd)
        source_stat = os.fstat(source_fd)
        if remove_source and source_stat.st_nlink != 1:
            os.close(source_fd)
            return False, f"源文件存在硬链接，拒绝复制后删除: {src}"

        if os.path.lexists(partial):
            partial_lstat = os.lstat(partial)
            if (
                not stat.S_ISREG(partial_lstat.st_mode)
                or partial_lstat.st_nlink != 1
                or partial_lstat.st_uid != os.geteuid()
            ):
                os.close(source_fd)
                return False, f"断点临时文件不是本应用可安全续传的独立普通文件: {partial}"
            partial_fd = _open_regular_nofollow(partial, os.O_RDWR)
            opened_partial = os.fstat(partial_fd)
            if (
                opened_partial.st_dev != partial_lstat.st_dev
                or opened_partial.st_ino != partial_lstat.st_ino
            ):
                os.close(partial_fd)
                os.close(source_fd)
                return False, f"断点临时文件在打开时发生变化，已停止复制: {partial}"
        else:
            try:
                partial_fd = _open_regular_nofollow(
                    partial,
                    os.O_RDWR | os.O_CREAT | os.O_EXCL,
                )
            except FileExistsError:
                os.close(source_fd)
                return False, f"断点临时文件在复制启动时出现，已停止复制: {partial}"

        with os.fdopen(source_fd, "rb") as source, os.fdopen(partial_fd, "r+b") as target:
            copied = os.fstat(target.fileno()).st_size
            if copied > source_snapshot[0] or not _prefix_matches(source, target, copied):
                target.seek(0)
                target.truncate(0)
                copied = 0
            source.seek(copied)
            target.seek(copied)
            while chunk := source.read(_COPY_CHUNK_SIZE):
                target.write(chunk)
                copied += len(chunk)
                if progress_callback:
                    progress_callback(copied, source_snapshot[0])
            target.flush()
            os.fsync(target.fileno())
            partial_snapshot = _descriptor_snapshot(target.fileno())
            source_after_copy = _descriptor_snapshot(source.fileno())
            source_digest = _hash_open_file(source)
            partial_digest = _hash_open_file(target)
            source_after_hash = _descriptor_snapshot(source.fileno())

        if source_after_copy != source_snapshot:
            return False, "复制期间源文件发生变化，保留源文件并等待稳定后重试"
        if partial_snapshot[0] != source_snapshot[0]:
            return False, "目标临时文件大小校验失败"
        if source_digest != partial_digest:
            return False, "目标临时文件 SHA-256 校验失败"
        if source_after_hash != source_snapshot:
            return False, "完整性校验期间源文件发生变化，保留源文件并等待重试"

        try:
            _publish_file_noreplace(partial, dest, expected_snapshot=partial_snapshot)
        except FileExistsError:
            return False, f"目标文件在复制期间出现，已保留双方文件并停止发布: {dest}"
        except OSError as exc:
            return False, f"目标文件无法安全原子发布，源文件已保留: {exc}"
        if remove_source:
            if not _path_matches_snapshot(src, source_snapshot):
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
    if not os.path.lexists(path):
        return True, ""

    if os.path.islink(path):
        return False, f"符号链接不允许直接删除: {path}"

    ok, msg = validate_path_safety(path, allowed_base_dirs)
    if not ok:
        return False, msg

    try:
        file_stat = os.lstat(path)
    except OSError as exc:
        return False, f"无法读取文件状态: {exc}"
    if stat.S_ISDIR(file_stat.st_mode):
        return False, f"拒绝删除目录: {path}"

    if not stat.S_ISREG(file_stat.st_mode):
        return False, f"非普通文件，拒绝删除: {path}"

    try:
        file_size = file_stat.st_size
        if file_size > 50 * 1024 * 1024 * 1024:
            return False, f"文件过大({file_size/(1024**3):.1f}GB)，拒绝删除: {path}"
    except OSError:
        return False, f"无法获取文件大小: {path}"

    try:
        current_stat = os.lstat(path)
        if (
            current_stat.st_dev != file_stat.st_dev
            or current_stat.st_ino != file_stat.st_ino
            or not stat.S_ISREG(current_stat.st_mode)
        ):
            return False, f"文件在删除前发生变化，已停止操作: {path}"
        os.unlink(path)
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

    if os.path.lexists(dest):
        return False, f"目标文件已存在: {dest}"

    if os.path.islink(src) or not os.path.isfile(src):
        return False, f"源路径不是可安全移动的普通文件: {src}"

    dest_dir = os.path.dirname(dest)
    if not os.path.isdir(dest_dir):
        return False, f"目标目录不存在，拒绝自动创建以避免挂载掉线误写: {dest_dir}"

    try:
        source_snapshot = _file_snapshot(src)
        _publish_file_noreplace(src, dest, expected_snapshot=source_snapshot)
        return True, f"已移动: {os.path.basename(src)} -> {dest}"
    except FileExistsError:
        return False, f"目标文件在移动期间出现，已保留双方文件: {dest}"
    except OSError as exc:
        if exc.errno == errno.EXDEV:
            return verified_copy(src, dest, remove_source=True)
        return False, f"无法安全移动文件，源文件已保留: {exc}"


def check_write_permission(directory: str) -> tuple:
    if not os.path.exists(directory):
        try:
            os.makedirs(directory, exist_ok=True)
        except PermissionError:
            return False, f"权限不足，无法创建目录: {directory}"
        except OSError as exc:
            return False, f"创建目录失败: {exc}"

    descriptor = -1
    test_file = ""
    created_snapshot = None
    try:
        descriptor, test_file = tempfile.mkstemp(prefix=".write_test_", dir=directory)
        created_stat = os.fstat(descriptor)
        created_snapshot = (created_stat.st_dev, created_stat.st_ino)
        os.write(descriptor, b"test")
        os.fsync(descriptor)
        os.close(descriptor)
        descriptor = -1
        current_stat = os.lstat(test_file)
        if (
            not stat.S_ISREG(current_stat.st_mode)
            or current_stat.st_nlink != 1
            or (current_stat.st_dev, current_stat.st_ino) != created_snapshot
        ):
            return False, f"写入探针在检查期间发生变化，拒绝继续: {directory}"
        os.unlink(test_file)
        return True, ""
    except PermissionError:
        return False, f"目录无写入权限: {directory}"
    except OSError as exc:
        return False, f"写入测试失败: {exc}"
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        if test_file and created_snapshot:
            try:
                current_stat = os.lstat(test_file)
                if (current_stat.st_dev, current_stat.st_ino) == created_snapshot:
                    os.unlink(test_file)
            except OSError:
                pass


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
