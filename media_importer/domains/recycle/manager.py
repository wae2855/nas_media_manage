import os
import shutil
import json
from datetime import datetime


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
                        source_dir: str = "", import_roots: list = None,
                        extra_meta: dict = None) -> tuple:
    if not os.path.exists(dir_path):
        return True, "", ""

    if not recycle_dir:
        return False, "", "回收站目录未配置"

    ok, msg = _validate_no_path_traversal(dir_path)
    if not ok:
        return False, "", msg

    real = os.path.realpath(dir_path)
    if not os.path.isdir(real):
        return False, "", f"不是目录: {dir_path}"

    try:
        date_str = datetime.now().strftime("%Y-%m-%d")
        sub_path = _recycle_subpath(dir_path, source_dir, import_roots or [], reason=reason)
        dest_dir = os.path.join(recycle_dir, date_str, sub_path)
        os.makedirs(os.path.dirname(dest_dir), exist_ok=True)

        base_name = os.path.basename(dir_path.rstrip(os.sep))
        dest_path = os.path.join(os.path.dirname(dest_dir), base_name)
        counter = 1
        while os.path.exists(dest_path):
            dest_path = os.path.join(os.path.dirname(dest_dir), f"{base_name}_{counter}")
            counter += 1

        try:
            os.rename(real, dest_path)
        except OSError:
            shutil.copytree(real, dest_path)
            shutil.rmtree(real)

        source_zone = _determine_source_zone(dir_path, source_dir, import_roots or [])
        total_size = 0
        file_count = 0
        for dp, dn, fns in os.walk(dest_path):
            for fn in fns:
                try:
                    total_size += os.path.getsize(os.path.join(dp, fn))
                    file_count += 1
                except OSError:
                    pass

        meta = {
            "original_path": os.path.abspath(dir_path),
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
            with open(meta_path, "w", encoding="utf-8") as f:
                json.dump(meta, f, ensure_ascii=False, indent=2)
        except OSError:
            pass

        return True, dest_path, f"已移入回收站(目录): {os.path.basename(dir_path)}"

    except PermissionError:
        return False, "", f"权限不足，无法移入回收站: {dir_path}"
    except OSError as e:
        return False, "", f"移入回收站失败: {e}"


def move_to_recycle(src_path: str, recycle_dir: str,
                    reason: str = "", task_id: str = "",
                    source_dir: str = "", import_roots: list = None,
                    extra_meta: dict = None) -> tuple:
    if not os.path.exists(src_path):
        return True, "", ""

    if not recycle_dir:
        return False, "", "回收站目录未配置"

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
        sub_path = _recycle_subpath(src_path, source_dir, import_roots or [], reason=reason)
        dest_dir = os.path.join(recycle_dir, date_str, os.path.dirname(sub_path))
        os.makedirs(dest_dir, exist_ok=True)

        base_name = os.path.basename(src_path)
        dest_path = os.path.join(dest_dir, base_name)
        counter = 1
        while os.path.exists(dest_path):
            name, ext = os.path.splitext(base_name)
            dest_path = os.path.join(dest_dir, f"{name}_{counter}{ext}")
            counter += 1

        try:
            os.rename(real, dest_path)
        except OSError:
            shutil.copy2(real, dest_path)
            os.remove(real)

        source_zone = _determine_source_zone(src_path, source_dir, import_roots or [])
        meta = {
            "original_path": os.path.abspath(src_path),
            "source_zone": source_zone,
            "reason": reason,
            "task_id": task_id,
            "moved_at": datetime.now().isoformat(),
            "file_size_mb": round(os.path.getsize(dest_path) / (1024 * 1024), 1),
        }
        if extra_meta:
            meta.update(extra_meta)

        meta_path = dest_path + ".meta"
        try:
            with open(meta_path, "w", encoding="utf-8") as f:
                json.dump(meta, f, ensure_ascii=False, indent=2)
        except OSError:
            pass

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
                                     import_roots: list = None,
                                     allowed_base_dirs: list = None) -> int:
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
