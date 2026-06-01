#!/usr/bin/env python3
import json
from media_importer.api.utils import json_response, get_db
from media_importer.api import globals
from media_importer.domains.source_cleaning import SourceCleaner
from media_importer.domains.source_cleaning.records import (
    get_cleaner_records,
    get_cleaner_status,
    save_cleaner_record,
)
from media_importer.monitor.permission_checker import check_path_permission


class SourceCleanerHandlers:

    def source_cleaner_preview(self, handler):
        config = globals._config or {}
        cleaner = SourceCleaner(config)
        task_paths = self._get_task_paths(handler)
        items = cleaner.preview(task_paths)
        return json_response(handler, 200, {"items": items, "total": len(items)})

    def source_cleaner_ai_preview(self, handler):
        config = globals._config or {}
        cleaner = SourceCleaner(config)
        task_paths = self._get_task_paths(handler)
        result = cleaner.ai_preview(task_paths)
        return json_response(handler, 200, result)

    def source_cleaner_records(self, handler):
        conn = get_db(handler)
        limit = int(handler.query_params.get("limit", "20"))
        offset = int(handler.query_params.get("offset", "0"))
        records = get_cleaner_records(conn, limit=limit, offset=offset)
        return json_response(handler, 200, records)

    def source_cleaner_execute(self, handler):
        config = globals._config or {}
        recycle_dir = config.get("source_policy", {}).get("recycle_dir", "")
        if recycle_dir:
            r = check_path_permission(recycle_dir, need_write=True)
            if not r["ok"]:
                return json_response(handler, 400, None, f"回收站目录权限不足: {r['message']}")

        cleaner = SourceCleaner(config)
        task_paths = self._get_task_paths(handler)
        body = {}
        try:
            content_length = int(handler.headers.get("Content-Length", 0))
            if content_length > 0:
                body = json.loads(handler.rfile.read(content_length).decode("utf-8"))
        except (json.JSONDecodeError, ValueError):
            pass
        merge_strategy = body.get("merge_strategy", None)
        record = cleaner.execute(task_paths=task_paths,
                                 merge_strategy=merge_strategy)
        conn = get_db(handler)
        save_cleaner_record(conn, record)
        return json_response(handler, 200, record)

    def source_cleaner_status(self, handler):
        conn = get_db(handler)
        status = get_cleaner_status(conn)
        config = globals._config or {}
        cleaner_config = config.get("source_cleaner", {})
        status["enabled"] = cleaner_config.get("enabled", False)
        status["cleanup_mode"] = cleaner_config.get("cleanup_mode", "media_only")
        status["ai_enabled"] = cleaner_config.get("ai_enabled", False)
        status["merge_strategy"] = cleaner_config.get("merge_strategy", "intersection")
        status["schedule"] = cleaner_config.get("schedule", "0 3 * * *")
        return json_response(handler, 200, status)

    def _get_task_paths(self, handler) -> set:
        try:
            from media_importer.core.db.task_repo import list_all_tasks
            conn = get_db(handler)
            tasks = list_all_tasks(conn, limit=5000)
            paths = set()
            for t in tasks:
                for key in ("source_path", "video_path", "import_video_path"):
                    p = t.get(key, "")
                    if p:
                        paths.add(p)
                for sub in t.get("subtitle_files", []):
                    if isinstance(sub, str):
                        paths.add(sub)
                    elif isinstance(sub, dict):
                        sp = sub.get("target_path") or sub.get("source_path", "")
                        if sp:
                            paths.add(sp)
            return paths
        except Exception:
            return set()
