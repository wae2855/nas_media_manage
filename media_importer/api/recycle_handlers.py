#!/usr/bin/env python3
from urllib.parse import parse_qs

from media_importer.api.utils import json_response
from media_importer.api import globals
from media_importer.features.recycle import (
    delete_from_recycle,
    list_recycle_dir,
    restore_from_recycle,
)


def _query_first(query, key, default=""):
    if not isinstance(query, dict):
        parsed = parse_qs(query or "")
        val = parsed.get(key)
        return val[0] if val else default
    val = query.get(key)
    if isinstance(val, list):
        return val[0] if val else default
    return val if val is not None else default


class RecycleHandlers:

    def recycle_list(self, *, body: dict, params: dict, query: dict):
        config = globals._config or {}
        recycle_dir = config.get("source_policy", {}).get("recycle_dir", "")
        zone = _query_first(query, "zone") or _query_first(query, "partition")
        reason = _query_first(query, "reason")
        limit = int(_query_first(query, "limit", "100"))
        offset = int(_query_first(query, "offset", "0"))
        result = list_recycle_dir(recycle_dir, zone=zone, reason=reason, limit=limit, offset=offset)
        return json_response(self, 200, result)

    def recycle_restore(self, *, body: dict, params: dict, query: dict):
        body = body or {}
        items = body.get("items", [])
        conflict_mode = body.get("conflict_mode", "skip")

        restore_items = []
        for it in items:
            if isinstance(it, str):
                restore_items.append({"recycle_path": it})
            elif isinstance(it, dict):
                restore_items.append(it)

        if not restore_items:
            return json_response(self, 400, {"restored": [], "failed": []}, "未指定要恢复的回收项")

        result = restore_from_recycle(restore_items, conflict_mode=conflict_mode)
        restored_count = len(result.get("restored", []))
        failed_count = len(result.get("failed", []))
        if failed_count == 0:
            return json_response(self, 200, result, f"成功恢复 {restored_count} 个文件")
        elif restored_count == 0:
            return json_response(self, 400, result, f"恢复失败 {failed_count} 个文件")
        else:
            return json_response(self, 207, result, f"恢复 {restored_count} 个成功，{failed_count} 个失败")

    def recycle_delete(self, *, body: dict, params: dict, query: dict):
        body = body or {}
        items = body.get("items", [])

        delete_items = []
        for it in items:
            if isinstance(it, str):
                delete_items.append({"recycle_path": it})
            elif isinstance(it, dict):
                delete_items.append(it)

        if not delete_items:
            return json_response(self, 400, {"deleted": [], "failed": []}, "未指定要删除的回收项")

        result = delete_from_recycle(delete_items)
        deleted_count = len(result.get("deleted", []))
        failed_count = len(result.get("failed", []))
        if failed_count == 0:
            return json_response(self, 200, result, f"成功删除 {deleted_count} 个文件")
        elif deleted_count == 0:
            return json_response(self, 400, result, f"删除失败 {failed_count} 个文件")
        else:
            return json_response(self, 207, result, f"删除 {deleted_count} 个成功，{failed_count} 个失败")
