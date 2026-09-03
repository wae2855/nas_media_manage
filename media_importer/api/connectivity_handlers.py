
import os
import time

from media_importer.app_version import get_app_version
from media_importer.core.metrics import get_metrics

from . import globals
from .utils import json_response


class ConnectivityHandlersMixin:
    def _config_test_llm(self, *, body: dict, params: dict, query: dict):
        """LLM 连通测试（ADR-0010 后仅服务源目录清理器，读 llm 块配置）。"""
        cfg = (globals._config or {}).get("llm", {}) if globals._config else {}
        api_key = body.get("api_key") or cfg.get("api_key", "")
        base_url = body.get("base_url") or cfg.get("base_url", "")
        model = body.get("model") or cfg.get("model", "")

        if api_key and self._is_masked_value(api_key):
            api_key = cfg.get("api_key", "")
        if base_url and self._is_masked_value(base_url):
            base_url = cfg.get("base_url", "")

        if not api_key:
            json_response(self, 200, data={"success": False, "message": "llm.api_key 未配置"})
            return
        if not base_url:
            json_response(self, 200, data={"success": False, "message": "llm.base_url 未配置"})
            return
        if not model:
            json_response(self, 200, data={"success": False, "message": "llm.model 未配置"})
            return

        try:
            from media_importer.features.configuration import test_llm_api
            ok, msg = test_llm_api(base_url, api_key, model, timeout=15)
            json_response(self, 200, data={"success": ok, "message": msg})
        except Exception as e:
            json_response(self, 200, data={"success": False, "message": "测试异常: " + str(e)})

    def _config_test_tmdb(self, *, body: dict, params: dict, query: dict):
        api_key = body.get("api_key", "")

        if not api_key or globals._is_masked_value(api_key):
            api_key = globals._get_real_config_value("metadata", "tmdb", "api_key")
            if not api_key:
                json_response(self, 200, data={"success": False, "message": "API Key 未配置"})
                return

        try:
            from media_importer.features.scraping import TMDbClient
            client = TMDbClient(api_key)
            ok = client.test_connection()
            msg = "连接成功" if ok else "连接失败，请检查 API Key 是否正确"
            json_response(self, 200, data={"success": ok, "message": msg})
        except Exception as e:
            json_response(self, 200, data={"success": False, "message": "测试异常: " + str(e)})

    def _health(self, *, body: dict, params: dict, query: dict):
        from media_importer.infrastructure.filesystem import check_write_permission
        checks = {}
        overall = "ok"

        try:
            source_dir = globals._config.get("source_dir", "")
            if os.path.isdir(source_dir):
                if os.access(source_dir, os.R_OK):
                    checks["source_dir"] = "ok"
                else:
                    checks["source_dir"] = "no_read_permission"
            else:
                checks["source_dir"] = "error"
        except Exception:
            checks["source_dir"] = "error"
            overall = "degraded"

        try:
            log_dir = globals._config.get("log_dir", "") if globals._config else ""
            checks["log_dir_path"] = log_dir
            if os.path.isdir(log_dir):
                ok, _ = check_write_permission(log_dir)
                checks["log_dir"] = "ok" if ok else "no_write_permission"
            else:
                checks["log_dir"] = "error"
        except Exception:
            checks["log_dir"] = "error"
            overall = "degraded"

        # LLM 配置检查（ADR-0010：LLM 仅服务源目录清理器；未配置为 skipped 非 error）
        try:
            llm_cfg = globals._config.get("llm", {}) if globals._config else {}
            llm_ok = bool(
                llm_cfg.get("api_key") and llm_cfg.get("base_url") and llm_cfg.get("model")
            )
            checks["llm"] = "ok" if llm_ok else "skipped"
        except Exception:
            checks["llm"] = "skipped"

        try:
            roots = globals._config.get("library_roots") or []
            disk_check_dir = next(
                (
                    str(root.get("path") or "")
                    for root in roots
                    if isinstance(root, dict) and root.get("enabled", True) is not False
                ),
                globals._config.get("source_dir", "/tmp"),
            )
            stat = os.statvfs(disk_check_dir)
            free_gb = stat.f_bavail * stat.f_frsize / (1024**3)
            checks["disk_space"] = "ok" if free_gb > 1 else "low"
        except Exception:
            checks["disk_space"] = "error"
            overall = "degraded"

        if "error" in checks.values():
            overall = "degraded"

        json_response(self, 200, data={
            "status": overall,
            "version": get_app_version(),
            "checks": checks,
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S")
        }, message=f"Health check: {overall}")

    def _metrics(self, *, body: dict, params: dict, query: dict):
        m = get_metrics()
        counts = globals._global_task_manager.count_by_status_and_stage() if globals._global_task_manager else {}
        json_response(self, 200, data={
            **m.to_dict(),
            "queue_by_status": counts
        })

    def _logs(self, *, body: dict, params: dict, query: dict):
        limit = int(query.get("limit", [100])[0])
        task_id = query.get("task_id", [None])[0]

        if globals._global_logger:
            result_lines = globals._global_logger.get_recent_logs(limit=limit, task_id=task_id)
        else:
            result_lines = []

        json_response(self, 200, data={"logs": result_lines})
