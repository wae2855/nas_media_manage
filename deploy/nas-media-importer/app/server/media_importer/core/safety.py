#!/usr/bin/env python3
import os
import shutil
import json
import hashlib
from datetime import datetime

ALLOWED_VIDEO_EXTS = {".mkv", ".mp4", ".avi", ".ts", ".mov", ".wmv", ".m2ts", ".flv"}
ALLOWED_SUBTITLE_EXTS = {".srt", ".ass", ".ssa", ".vtt", ".sub"}
ALLOWED_MEDIA_EXTS = ALLOWED_VIDEO_EXTS | ALLOWED_SUBTITLE_EXTS


def validate_path_safety(path: str, allowed_base_dirs: list = None) -> tuple:
    real = os.path.realpath(path)
    if ".." in path or ".." in real:
        return False, f"路径包含目录穿越: {path}"
    if allowed_base_dirs:
        allowed_real = [os.path.realpath(d) for d in allowed_base_dirs if d]
        # 简单处理：只要路径前缀匹配任一允许目录即可，不管中间层级
        if not any(real.startswith(base) for base in allowed_real):
            return False, "Path not in allowed directories"
    return True, ""


def validate_file_ext(path: str, allowed_exts: set = None) -> tuple:
    ext = os.path.splitext(path)[1].lower()
    exts = allowed_exts or ALLOWED_MEDIA_EXTS
    if ext not in exts:
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

    ok, msg = validate_path_safety(dir_path)
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

    ok, msg = validate_path_safety(src_path)
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


def recycle_cleanup(recycle_dir: str, retention_days: int) -> list:
    if not recycle_dir or not os.path.isdir(recycle_dir):
        return []
    if retention_days <= 0:
        return []

    now = datetime.now()
    deleted = []

    dir_metas = []
    file_metas = []

    for dirpath, dirnames, filenames in os.walk(recycle_dir):
        for fname in filenames:
            if fname.endswith(".dir.meta"):
                dir_metas.append(os.path.join(dirpath, fname))
            elif fname.endswith(".meta"):
                file_metas.append(os.path.join(dirpath, fname))

    for meta_path in dir_metas:
        try:
            with open(meta_path, "r", encoding="utf-8") as f:
                meta = json.load(f)
            moved_at_str = meta.get("moved_at", "")
            if not moved_at_str:
                continue
            moved_at = datetime.fromisoformat(moved_at_str)
            age_days = (now - moved_at).days
            if age_days > retention_days:
                dir_data_path = meta_path[:-9]
                if os.path.isdir(dir_data_path):
                    shutil.rmtree(dir_data_path)
                    deleted.append({"path": dir_data_path, "age_days": age_days, "reason": "recycle_expired_dir"})
                os.remove(meta_path)
                deleted.append({"path": meta_path, "age_days": age_days, "reason": "dir_meta_expired"})
        except (OSError, json.JSONDecodeError, ValueError):
            continue

    for meta_path in file_metas:
        try:
            with open(meta_path, "r", encoding="utf-8") as f:
                meta = json.load(f)
            moved_at_str = meta.get("moved_at", "")
            if not moved_at_str:
                continue
            moved_at = datetime.fromisoformat(moved_at_str)
            age_days = (now - moved_at).days
            if age_days > retention_days:
                data_path = meta_path[:-5]
                if os.path.isfile(data_path):
                    os.remove(data_path)
                    deleted.append({"path": data_path, "age_days": age_days, "reason": "recycle_expired"})
                os.remove(meta_path)
                deleted.append({"path": meta_path, "age_days": age_days, "reason": "meta_expired"})
        except (OSError, json.JSONDecodeError, ValueError):
            continue

    return deleted


def list_recycle_dir(recycle_dir: str, zone: str = None, reason: str = None,
                     limit: int = 100, offset: int = 0) -> dict:
    if not recycle_dir or not os.path.isdir(recycle_dir):
        return {
            "items": [], "total": 0, "total_count": 0, "total_size": 0,
            "total_size_mb": 0, "zones": {}, "partition_stats": {},
            "partitions": [], "reasons": [],
        }

    items = []
    zones = {}
    total_size = 0
    reasons_set = set()

    for dirpath, dirnames, filenames in os.walk(recycle_dir):
        for fname in filenames:
            meta_path = os.path.join(dirpath, fname)
            is_dir_meta = fname.endswith(".dir.meta")
            is_file_meta = fname.endswith(".meta") and not is_dir_meta

            if not is_file_meta and not is_dir_meta:
                continue

            try:
                with open(meta_path, "r", encoding="utf-8") as f:
                    meta = json.load(f)
            except (OSError, json.JSONDecodeError):
                continue

            original_path = meta.get("original_path", "")
            meta_reason = meta.get("reason", "")
            moved_at = meta.get("moved_at", "")
            file_size_mb = meta.get("file_size_mb", 0) or meta.get("total_size_mb", 0)
            source_zone = meta.get("source_zone", "other")
            task_id = meta.get("task_id", "")
            is_dir = meta.get("is_dir", False)

            if is_dir_meta:
                data_path = meta_path[:-9]
            else:
                data_path = meta_path[:-5]

            recycle_path = data_path if os.path.exists(data_path) else ""

            zone_name = ""
            if meta_reason.startswith("source_cleaner:"):
                zone_name = "[清理器-源目录]"
            elif source_zone == "source":
                zone_name = "[源目录]"
            elif source_zone == "import":
                zone_name = "[入库目录]"
            else:
                zone_name = "[其他]"

            if zone and zone_name != zone:
                continue
            if reason and meta_reason != reason:
                continue

            parent_dir = os.path.dirname(original_path)
            restorable = False
            if original_path and not os.path.exists(original_path):
                if os.path.isdir(parent_dir) and os.access(parent_dir, os.W_OK):
                    restorable = True

            file_size_bytes = int(file_size_mb * 1024 * 1024) if file_size_mb else 0

            zones.setdefault(zone_name, {"count": 0, "size": 0})
            zones[zone_name]["count"] += 1
            zones[zone_name]["size"] += file_size_bytes
            total_size += file_size_bytes

            reasons_set.add(meta_reason)

            items.append({
                "id": recycle_path or meta_path,
                "recycle_path": recycle_path,
                "original_path": original_path,
                "source_zone": source_zone,
                "zone_name": zone_name,
                "partition": zone_name,
                "reason": meta_reason,
                "moved_at": moved_at,
                "file_size_mb": file_size_mb,
                "size": file_size_bytes,
                "task_id": task_id,
                "is_dir": is_dir,
                "restorable": restorable,
            })

    items.sort(key=lambda x: x.get("moved_at", ""), reverse=True)
    total = len(items)
    paged = items[offset:offset + limit]

    return {
        "items": paged,
        "total": total,
        "total_count": total,
        "total_size": total_size,
        "total_size_mb": round(total_size / (1024 * 1024), 1) if total_size else 0,
        "zones": zones,
        "partition_stats": zones,
        "partitions": list(zones.keys()),
        "reasons": list(reasons_set),
    }


def restore_from_recycle(items: list, conflict_mode: str = "skip") -> dict:
    restored = []
    failed = []

    for item in items:
        recycle_path = item.get("recycle_path", "")
        if not recycle_path or not os.path.exists(recycle_path):
            failed.append({"recycle_path": recycle_path, "status": "not_found", "message": "回收站文件不存在"})
            continue

        is_dir = os.path.isdir(recycle_path)
        meta_suffix = ".dir.meta" if is_dir else ".meta"
        meta_path = recycle_path + meta_suffix

        original_path = ""
        if os.path.exists(meta_path):
            try:
                with open(meta_path, "r", encoding="utf-8") as f:
                    meta = json.load(f)
                original_path = meta.get("original_path", "")
            except (OSError, json.JSONDecodeError):
                pass

        if not original_path:
            failed.append({"recycle_path": recycle_path, "status": "no_meta", "message": "无法获取原始路径"})
            continue

        parent_dir = os.path.dirname(original_path)
        if not os.path.isdir(parent_dir):
            failed.append({"recycle_path": recycle_path, "status": "parent_missing", "message": f"原位置父目录不存在: {parent_dir}"})
            continue

        if not os.access(parent_dir, os.W_OK):
            failed.append({"recycle_path": recycle_path, "status": "no_write", "message": f"原位置无写入权限: {parent_dir}"})
            continue

        if os.path.exists(original_path):
            if conflict_mode == "skip":
                failed.append({"recycle_path": recycle_path, "status": "conflict", "message": f"原位置已存在同名文件: {original_path}"})
                continue
            elif conflict_mode == "overwrite":
                if os.path.isdir(original_path):
                    shutil.rmtree(original_path)
                else:
                    os.remove(original_path)
            elif conflict_mode == "rename":
                name, ext = os.path.splitext(original_path)
                original_path = f"{name}_restored{ext}"

        try:
            os.rename(recycle_path, original_path)
        except OSError:
            try:
                if is_dir:
                    shutil.copytree(recycle_path, original_path)
                    shutil.rmtree(recycle_path)
                else:
                    shutil.copy2(recycle_path, original_path)
                    os.remove(recycle_path)
            except (OSError, shutil.Error) as e:
                failed.append({"recycle_path": recycle_path, "status": "move_failed", "message": str(e)})
                continue

        if os.path.exists(meta_path):
            try:
                os.remove(meta_path)
            except OSError:
                pass

        restored.append({"recycle_path": recycle_path, "restored_to": original_path, "status": "ok"})

    return {"restored": restored, "failed": failed}


def delete_from_recycle(items: list) -> dict:
    deleted = []
    failed = []

    for item in items:
        recycle_path = item.get("recycle_path", "")
        if not recycle_path or not os.path.exists(recycle_path):
            failed.append({"recycle_path": recycle_path, "status": "not_found"})
            continue

        is_dir = os.path.isdir(recycle_path)
        meta_suffix = ".dir.meta" if is_dir else ".meta"
        meta_path = recycle_path + meta_suffix

        try:
            if is_dir:
                shutil.rmtree(recycle_path)
            else:
                os.remove(recycle_path)
            deleted.append({"recycle_path": recycle_path, "status": "ok"})
        except OSError as e:
            failed.append({"recycle_path": recycle_path, "status": "error", "message": str(e)})
            continue

        if os.path.exists(meta_path):
            try:
                os.remove(meta_path)
            except OSError:
                pass

    return {"deleted": deleted, "failed": failed}
