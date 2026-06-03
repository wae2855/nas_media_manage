import os
import time

from media_importer.api import globals
from .utils import json_response
from media_importer.core.metrics import get_metrics


class ConnectivityHandlersMixin:
    def _config_test_llm(self, body: dict):
        base_url = body.get("base_url", "")
        api_key = body.get("api_key", "")
        model = body.get("model", "")
        provider = body.get("provider", "openai")

        if not api_key or self._is_masked_value(api_key):
            api_key = self._get_real_config_value("llm", "api_key")
            if not api_key:
                json_response(self, 200, data={"success": False, "message": "API Key 未配置"})
                return

        if not base_url or self._is_masked_value(base_url):
            base_url = self._get_real_config_value("llm", "base_url")
            if not base_url:
                json_response(self, 200, data={"success": False, "message": "API 地址未配置"})
                return

        if not model:
            model = self._get_real_config_value("llm", "model")
            if not model:
                json_response(self, 200, data={"success": False, "message": "模型名称未配置"})
                return

        try:
            from media_importer.features.configuration import test_llm_api
            ok, msg = test_llm_api(base_url, api_key, model, timeout=15)
            json_response(self, 200, data={"success": ok, "message": msg})
        except Exception as e:
            json_response(self, 200, data={"success": False, "message": "测试异常: " + str(e)})

    def _config_test_hermes(self, body: dict):
        base_url = body.get("base_url", "")
        route_name = body.get("route_name", "")
        secret = body.get("secret", "")

        if not base_url or self._is_masked_value(base_url):
            base_url = self._get_real_config_value("hermes", "webhook", "base_url")
        if not route_name:
            route_name = self._get_real_config_value("hermes", "webhook", "route_name")
        if not secret or self._is_masked_value(secret):
            secret = self._get_real_config_value("hermes", "webhook", "secret")

        if not base_url:
            json_response(self, 200, data={"success": False, "message": "Webhook 地址未配置"})
            return

        if not route_name:
            json_response(self, 200, data={"success": False, "message": "路由名称未配置"})
            return

        try:
            from media_importer.features.configuration import test_hermes_webhook
            ok, msg = test_hermes_webhook(base_url, route_name, secret, timeout=15)
            json_response(self, 200, data={"success": ok, "message": msg})
        except Exception as e:
            json_response(self, 200, data={"success": False, "message": "测试异常: " + str(e)})

    def _config_test_tmdb(self, body: dict):
        api_key = body.get("api_key", "")

        if not api_key or self._is_masked_value(api_key):
            api_key = self._get_real_config_value("metadata", "tmdb", "api_key")
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

    def _health(self):
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
            temp_dir = globals._config.get("temp_dir", "")
            if os.path.isdir(temp_dir):
                ok, _ = check_write_permission(temp_dir)
                checks["temp_dir"] = "ok" if ok else "no_write_permission"
            else:
                checks["temp_dir"] = "error"
        except Exception:
            checks["temp_dir"] = "error"
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

        try:
            llm_config = globals._config.get("llm", {})
            api_key = llm_config.get("api_key", "")
            checks["llm_api"] = "ok" if api_key else "skipped"
        except Exception:
            checks["llm_api"] = "skipped"

        try:
            hermes_enabled = globals._config.get("hermes", {}).get("enabled", False)
            checks["hermes"] = "ok" if hermes_enabled else "disabled"
        except Exception:
            checks["hermes"] = "disabled"

        try:
            disk_check_dir = globals._config.get("temp_dir", "/tmp")
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
            "checks": checks,
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S")
        }, message=f"Health check: {overall}")

    def _metrics(self):
        m = get_metrics()
        counts = globals._global_task_manager.count_by_status() if globals._global_task_manager else {}
        json_response(self, 200, data={
            **m.to_dict(),
            "queue_by_status": counts
        })

    def _logs(self, query: dict):
        limit = int(query.get("limit", [100])[0])
        task_id = query.get("task_id", [None])[0]

        if globals._global_logger:
            result_lines = globals._global_logger.get_recent_logs(limit=limit, task_id=task_id)
        else:
            result_lines = []

        json_response(self, 200, data={"logs": result_lines})
