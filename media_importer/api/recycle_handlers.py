#!/usr/bin/env python3
from media_importer.api.utils import json_response
from media_importer.api import globals
from media_importer.features.recycle import (
    delete_from_recycle,
    list_recycle_dir,
    restore_from_recycle,
)


class RecycleHandlers:

    def recycle_list(self, handler):
        config = globals._config or {}
        recycle_dir = config.get("source_policy", {}).get("recycle_dir", "")
        zone = handler.query_params.get("zone", [None])[0] if hasattr(handler, "query_params") else None
        partition = handler.query_params.get("partition", [None])[0] if hasattr(handler, "query_params") else None
        if not zone and partition:
            zone = partition
        reason = handler.query_params.get("reason", [None])[0] if hasattr(handler, "query_params") else None
        limit = int(handler.query_params.get("limit", ["100"])[0]) if hasattr(handler, "query_params") else 100
        offset = int(handler.query_params.get("offset", ["0"])[0]) if hasattr(handler, "query_params") else 0
        result = list_recycle_dir(recycle_dir, zone=zone, reason=reason, limit=limit, offset=offset)
        return json_response(handler, 200, result)

    def recycle_restore(self, handler, body=None):
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
            return json_response(handler, 400, {"restored": [], "failed": []}, "未指定要恢复的回收项")

        result = restore_from_recycle(restore_items, conflict_mode=conflict_mode)
        restored_count = len(result.get("restored", []))
        failed_count = len(result.get("failed", []))
        if failed_count == 0:
            return json_response(handler, 200, result, f"成功恢复 {restored_count} 个文件")
        elif restored_count == 0:
            return json_response(handler, 400, result, f"恢复失败 {failed_count} 个文件")
        else:
            return json_response(handler, 207, result, f"恢复 {restored_count} 个成功，{failed_count} 个失败")

    def recycle_delete(self, handler, body=None):
        body = body or {}
        items = body.get("items", [])

        delete_items = []
        for it in items:
            if isinstance(it, str):
                delete_items.append({"recycle_path": it})
            elif isinstance(it, dict):
                delete_items.append(it)

        if not delete_items:
            return json_response(handler, 400, {"deleted": [], "failed": []}, "未指定要删除的回收项")

        result = delete_from_recycle(delete_items)
        deleted_count = len(result.get("deleted", []))
        failed_count = len(result.get("failed", []))
        if failed_count == 0:
            return json_response(handler, 200, result, f"成功删除 {deleted_count} 个文件")
        elif deleted_count == 0:
            return json_response(handler, 400, result, f"删除失败 {failed_count} 个文件")
        else:
            return json_response(handler, 207, result, f"删除 {deleted_count} 个成功，{failed_count} 个失败")
