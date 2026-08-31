import json
import os
import shutil
import stat
import uuid
from datetime import datetime
from typing import Optional

from media_importer.infrastructure.filesystem.safety import safe_move, verified_copy


def _write_json_exclusive(path: str, payload: dict) -> tuple[int, int]:
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(path, flags, 0o600)
    try:
        file_stat = os.fstat(descriptor)
        if not stat.S_ISREG(file_stat.st_mode) or file_stat.st_nlink != 1:
            raise OSError(f"回收记录不是独立普通文件: {path}")
        with os.fdopen(descriptor, "w", encoding="utf-8", closefd=False) as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
            handle.flush()
            os.fsync(handle.fileno())
        return file_stat.st_dev, file_stat.st_ino
    finally:
        os.close(descriptor)


def _remove_owned_file(path: str, identity: tuple[int, int]) -> None:
    try:
        file_stat = os.lstat(path)
        if (
            stat.S_ISREG(file_stat.st_mode)
            and (file_stat.st_dev, file_stat.st_ino) == identity
        ):
            os.unlink(path)
    except OSError:
        pass


def _path_in_roots(path: str, roots: list) -> bool:
    real = os.path.realpath(path)
    for root in roots or []:
        if not root:
            continue
        root_real = os.path.realpath(root)
        try:
            if os.path.commonpath((real, root_real)) == root_real:
                return True
        except ValueError:
            continue
    return False


def _protected_target_error(path: str, import_roots: list, reason: str) -> str:
    if _path_in_roots(path, import_roots) and reason != "confirmed_target_replace":
        return "目标片库受保护：只有用户逐项确认替换时，现有片库文件才能移入回收区"
    return ""


def _validate_no_path_traversal(path: str) -> tuple:
    real = os.path.realpath(path)
    if ".." in path or ".." in real:
        return False, f"路径包含目录穿越: {path}"
    return True, ""


def _recycle_subpath(original_path: str, source_dir: str, import_roots: list, reason: str = "") -> str:
    abs_path = os.path.abspath(original_path)
    source_abs = os.path.abspath(source_dir) if source_dir else ""

    if reason.startswith("source_cleaner:"):
        if source_abs and abs_path.startswith(source_abs + os.sep):
            rel = os.path.relpath(abs_path, source_abs)
            return os.path.join("[清理器-源目录]", rel)
        return os.path.join("[清理器-源目录]", os.path.basename(abs_path))

    if source_abs and abs_path.startswith(source_abs + os.sep):
        rel = os.path.relpath(abs_path, source_abs)
        return os.path.join("[源目录]", rel)
    for root in (import_roots or []):
        root_abs = os.path.abspath(root)
        if abs_path.startswith(root_abs + os.sep):
            rel = os.path.relpath(abs_path, root_abs)
            return os.path.join("[入库目录]", rel)
    return os.path.join("[其他]", os.path.basename(abs_path))


def _determine_source_zone(original_path: str, source_dir: str, import_roots: list) -> str:
    abs_path = os.path.abspath(original_path)
    source_abs = os.path.abspath(source_dir) if source_dir else ""
    if source_abs and abs_path.startswith(source_abs + os.sep):
        return "source"
    for root in (import_roots or []):
        root_abs = os.path.abspath(root)
        if abs_path.startswith(root_abs + os.sep):
            return "import"
    return "other"


def move_dir_to_recycle(dir_path: str, recycle_dir: str,
                        reason: str = "", task_id: str = "",
                        source_dir: str = "", import_roots: Optional[list] = None,
                        extra_meta: Optional[dict] = None) -> tuple:
    if not os.path.exists(dir_path):
        return True, "", ""

    if os.path.islink(dir_path):
        return False, "", "拒绝回收符号链接目录"

    protected_error = _protected_target_error(dir_path, import_roots or [], reason)
    if protected_error:
        return False, "", protected_error

    if not recycle_dir:
        return False, "", "回收站目录未配置"
    if not os.path.isdir(recycle_dir):
        return False, "", "回收站目录不存在，可能挂载已失效；已保留原目录"

    ok, msg = _validate_no_path_traversal(dir_path)
    if not ok:
        return False, "", msg

    real = os.path.realpath(dir_path)
    if not os.path.isdir(real):
        return False, "", f"不是目录: {dir_path}"

    try:
        date_str = datetime.now().strftime("%Y-%m-%d")
        original_path = str((extra_meta or {}).get("original_path") or dir_path)
        sub_path = _recycle_subpath(original_path, source_dir, import_roots or [], reason=reason)
        dest_dir = os.path.join(recycle_dir, date_str, sub_path)
        os.makedirs(os.path.dirname(dest_dir), exist_ok=True)

        base_name = os.path.basename(original_path.rstrip(os.sep))
        dest_path = os.path.join(os.path.dirname(dest_dir), base_name)
        counter = 1
        while os.path.lexists(dest_path) or os.path.lexists(dest_path + ".dir.meta"):
            dest_path = os.path.join(os.path.dirname(dest_dir), f"{base_name}_{counter}")
            counter += 1

        source_zone = _determine_source_zone(original_path, source_dir, import_roots or [])
        total_size = 0
        file_count = 0
        for dp, _dn, fns in os.walk(real):
            for fn in fns:
                try:
                    total_size += os.path.getsize(os.path.join(dp, fn))
                    file_count += 1
                except OSError:
                    pass
        meta = {
            "original_path": os.path.abspath(original_path),
            "source_zone": source_zone,
            "reason": reason,
            "task_id": task_id,
            "moved_at": datetime.now().isoformat(),
            "is_dir": True,
            "file_count": file_count,
            "total_size_mb": round(total_size / (1024 * 1024), 1),
        }
        if extra_meta:
            meta.update(extra_meta)
        meta_path = dest_path + ".dir.meta"
        try:
            meta_identity = _write_json_exclusive(meta_path, meta)
        except FileExistsError:
            return False, "", "回收记录位置发生冲突，原目录已保留"
        except OSError as exc:
            return False, "", f"无法安全创建回收记录，原目录已保留: {exc}"

        try:
            os.rename(real, dest_path)
        except OSError:
            staging_path = dest_path + f".{uuid.uuid4().hex}.copying"
            os.makedirs(staging_path, exist_ok=True)
            for current_dir, dir_names, file_names in os.walk(real):
                relative = os.path.relpath(current_dir, real)
                target_dir = staging_path if relative == "." else os.path.join(staging_path, relative)
                os.makedirs(target_dir, exist_ok=True)
                for dir_name in dir_names:
                    os.makedirs(os.path.join(target_dir, dir_name), exist_ok=True)
                for file_name in file_names:
                    source_file = os.path.join(current_dir, file_name)
                    target_file = os.path.join(target_dir, file_name)
                    if os.path.exists(target_file):
                        continue
                    copied, copy_message = verified_copy(source_file, target_file)
                    if not copied:
                        _remove_owned_file(meta_path, meta_identity)
                        return False, "", f"跨盘回收校验失败，原目录已保留: {copy_message}"
            if os.path.lexists(dest_path):
                _remove_owned_file(meta_path, meta_identity)
                return False, "", "回收目标在复制期间出现，原目录已保留"
            os.rename(staging_path, dest_path)
            shutil.rmtree(real)

        return True, dest_path, f"已移入回收站(目录): {os.path.basename(dir_path)}"

    except PermissionError:
        return False, "", f"权限不足，无法移入回收站: {dir_path}"
    except OSError as e:
        return False, "", f"移入回收站失败: {e}"


def move_to_recycle(src_path: str, recycle_dir: str,
                    reason: str = "", task_id: str = "",
                        source_dir: str = "", import_roots: Optional[list] = None,
                        extra_meta: Optional[dict] = None) -> tuple:
    if not os.path.exists(src_path):
        return True, "", ""

    if os.path.islink(src_path):
        return False, "", "拒绝回收符号链接文件"

    protected_error = _protected_target_error(src_path, import_roots or [], reason)
    if protected_error:
        return False, "", protected_error

    if not recycle_dir:
        return False, "", "回收站目录未配置"
    if not os.path.isdir(recycle_dir):
        return False, "", "回收站目录不存在，可能挂载已失效；已保留源文件"

    ok, msg = _validate_no_path_traversal(src_path)
    if not ok:
        return False, "", msg

    real = os.path.realpath(src_path)
    if os.path.isdir(real):
        return move_dir_to_recycle(src_path, recycle_dir,
                                   reason=reason, task_id=task_id,
                                   source_dir=source_dir, import_roots=import_roots,
                                   extra_meta=extra_meta)

    try:
        date_str = datetime.now().strftime("%Y-%m-%d")
        original_path = str((extra_meta or {}).get("original_path") or src_path)
        sub_path = _recycle_subpath(original_path, source_dir, import_roots or [], reason=reason)
        dest_dir = os.path.join(recycle_dir, date_str, os.path.dirname(sub_path))
        os.makedirs(dest_dir, exist_ok=True)

        base_name = os.path.basename(original_path)
        dest_path = os.path.join(dest_dir, base_name)
        counter = 1
        while os.path.lexists(dest_path) or os.path.lexists(dest_path + ".meta"):
            name, ext = os.path.splitext(base_name)
            dest_path = os.path.join(dest_dir, f"{name}_{counter}{ext}")
            counter += 1

        source_zone = _determine_source_zone(original_path, source_dir, import_roots or [])
        meta = {
            "original_path": os.path.abspath(original_path),
            "source_zone": source_zone,
            "reason": reason,
            "task_id": task_id,
            "moved_at": datetime.now().isoformat(),
            "file_size_mb": round(os.path.getsize(real) / (1024 * 1024), 1),
        }
        if extra_meta:
            meta.update(extra_meta)

        meta_path = dest_path + ".meta"
        try:
            meta_identity = _write_json_exclusive(meta_path, meta)
        except FileExistsError:
            return False, "", "回收记录位置发生冲突，源文件已保留"
        except OSError as exc:
            return False, "", f"无法安全创建回收记录，源文件已保留: {exc}"

        moved, move_message = safe_move(real, dest_path)
        if not moved:
            _remove_owned_file(meta_path, meta_identity)
            return False, "", f"移入回收站失败，源文件已保留: {move_message}"

        return True, dest_path, f"已移入回收站: {os.path.basename(src_path)}"

    except PermissionError:
        return False, "", f"权限不足，无法移入回收站: {src_path}"
    except OSError as e:
        return False, "", f"移入回收站失败: {e}"


def move_to_recycle_with_companions(video_path: str, subtitle_paths: list,
                                     video_exts: list, sub_exts: list,
                                     recycle_dir: str,
                                     reason: str = "source_cleanup",
                                     task_id: str = "",
                                     source_dir: str = "",
                                      import_roots: Optional[list] = None,
                                      allowed_base_dirs: Optional[list] = None) -> int:
    if not os.path.exists(video_path):
        return 0

    moved = 0
    ok, _, _ = move_to_recycle(
        video_path, recycle_dir,
        reason=reason, task_id=task_id,
        source_dir=source_dir, import_roots=import_roots,
    )
    if ok:
        moved += 1

    video_dir = os.path.dirname(video_path)
    video_stem = os.path.splitext(os.path.basename(video_path))[0]

    companion_subs = []
    if subtitle_paths:
        companion_subs = list(subtitle_paths)
    else:
        for f in os.listdir(video_dir):
            f_lower = f.lower()
            if any(f_lower.endswith(ext) for ext in sub_exts):
                sub_stem = os.path.splitext(f)[0]
                if sub_stem.startswith(video_stem):
                    companion_subs.append(os.path.join(video_dir, f))

    for sub_path in companion_subs:
        if os.path.exists(sub_path):
            ok, _, _ = move_to_recycle(
                sub_path, recycle_dir,
                reason=reason, task_id=task_id,
                source_dir=source_dir, import_roots=import_roots,
            )
            if ok:
                moved += 1

    return moved
