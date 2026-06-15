import os
import time

from media_importer.api import globals
from .utils import json_response
from media_importer.core.metrics import get_metrics


# AI 场景 → 配置节映射
# 场景归属遵循 plan §3.10：dimension_supplement 单归一 AI_SEARCH；
# AI_ASSIST 场景包含 AI 辅助相关场景。
AI_ASSIST_SCENARIOS = frozenset({
    "extract_title",
    "source_cleaner",
    "match_assist",
    "dimension_mapping",
})
AI_SEARCH_SCENARIOS = frozenset({
    "scrape",
    "series_scrape",
    "dimension_supplement",
})


class ConnectivityHandlersMixin:
    def _resolve_ai_endpoint(self, scenario: str, body: dict, *, config_override: dict = None):
        """根据场景从 ai_assist / ai_search 配置中解析 (base_url, api_key, model)。

        - assist 场景：标题提取 / 源目录清理 / 匹配辅助 / 维度映射 → 走 ai_assist
        - search 场景：刮削 / 系列刮削 / 联网增强 → 走 ai_search
        - body 字段优先（前端掩码 *** 时按配置回退）
        """
        config_override = config_override or {}

        def _merge_section(current_cfg: dict, override: dict) -> dict:
            """合并 override 到 current_cfg，跳过掩码值，避免掩码覆盖真实配置。"""
            merged = dict(current_cfg or {})
            for k, v in (override or {}).items():
                if isinstance(v, str) and self._is_masked_value(v):
                    continue
                merged[k] = v
            return merged

        if scenario in AI_ASSIST_SCENARIOS:
            base_cfg = globals._config.get("ai_assist", {}) if globals._config else {}
            cfg = _merge_section(base_cfg, config_override.get("ai_assist", {}))
            section = "ai_assist"
        elif scenario in AI_SEARCH_SCENARIOS:
            base_cfg = globals._config.get("ai_search", {}) if globals._config else {}
            cfg = _merge_section(base_cfg, config_override.get("ai_search", {}))
            section = "ai_search"
        else:
            return None, None, None, f"未知场景: {scenario}"

        base_url = body.get("base_url") or cfg.get("base_url", "")
        api_key = body.get("api_key") or cfg.get("api_key", "")
        model = body.get("model") or cfg.get("model", "")

        if api_key and self._is_masked_value(api_key):
            api_key = base_cfg.get("api_key", "")
        if base_url and self._is_masked_value(base_url):
            base_url = base_cfg.get("base_url", "")

        if not api_key:
            return None, None, None, f"{section}.api_key 未配置"
        if not base_url:
            return None, None, None, f"{section}.base_url 未配置"
        if not model:
            return None, None, None, f"{section}.model 未配置"
        return base_url, api_key, model, None

    def _config_test_llm(self, *, body: dict, params: dict, query: dict):
        scenario = body.get("scenario", "extract_title")
        base_url, api_key, model, err = self._resolve_ai_endpoint(scenario, body)
        if err:
            json_response(self, 200, data={"success": False, "message": err})
            return

        try:
            from media_importer.features.configuration import test_llm_api
            ok, msg = test_llm_api(base_url, api_key, model, timeout=15)
            json_response(self, 200, data={"success": ok, "message": msg})
        except Exception as e:
            json_response(self, 200, data={"success": False, "message": "测试异常: " + str(e)})

    def _config_ai_demo(self, *, body: dict, params: dict, query: dict):
        scenario = body.get("scenario", "")
        demo_content = body.get("demo_content", "")
        config_override = body.get("config_override", {})

        if not scenario:
            json_response(self, 200, data={"success": False, "message": "缺少 scenario 参数"})
            return

        if scenario not in AI_ASSIST_SCENARIOS and scenario not in AI_SEARCH_SCENARIOS:
            json_response(self, 200, data={"success": False, "message": "未知场景: " + scenario})
            return

        base_url, api_key, model, err = self._resolve_ai_endpoint(
            scenario, body, config_override=config_override,
        )
        if err:
            json_response(self, 200, data={"success": False, "message": err})
            return

        try:
            import time as _time

            start = _time.time()
            if scenario in AI_ASSIST_SCENARIOS:
                if scenario == "extract_title":
                    from media_importer.scraper.llm_scraper import LLMScraper
                    test_config = dict(globals._config or {})
                    test_config["ai_assist"] = {
                        "api_key": api_key,
                        "base_url": base_url,
                        "model": model,
                    }
                    scraper = LLMScraper(test_config)
                    filename = demo_content or "The.Dark.Knight.2008.2160p.UHD.BluRay.x265.mkv"
                    result = scraper.extract_title(filename)
                    elapsed = int((_time.time() - start) * 1000)
                    json_response(self, 200, data={
                        "success": True,
                        "scenario": scenario,
                        "input": filename,
                        "result": result,
                        "model": model,
                        "elapsed_ms": elapsed,
                    })
                elif scenario == "source_cleaner":
                    from media_importer.features.configuration import test_llm_api
                    ok, msg = test_llm_api(base_url, api_key, model, timeout=15)
                    elapsed = int((_time.time() - start) * 1000)
                    json_response(self, 200, data={
                        "success": ok,
                        "scenario": scenario,
                        "model": model,
                        "result": {"message": msg},
                        "elapsed_ms": elapsed,
                    })
                else:
                    from media_importer.features.configuration import test_llm_api
                    ok, msg = test_llm_api(base_url, api_key, model, timeout=15)
                    elapsed = int((_time.time() - start) * 1000)
                    json_response(self, 200, data={
                        "success": ok,
                        "scenario": scenario,
                        "model": model,
                        "result": {"message": msg},
                        "elapsed_ms": elapsed,
                    })
                return

            # AI search 场景：scrape / series_scrape
            from media_importer.scraper.llm_scraper import LLMScraper
            saved_config = dict(globals._config) if globals._config else {}
            demo_config = dict(saved_config)
            demo_config["ai_search"] = {
                "api_key": api_key,
                "base_url": base_url,
                "model": model,
            }
            scraper = LLMScraper(demo_config)
            if not scraper.enabled:
                json_response(self, 200, data={"success": False, "message": "AI 刮削未生效，请检查配置是否完整（API Key、接口地址、模型）"})
                return

            search_enhanced = scraper.web_search_config.should_search(scenario) if hasattr(scraper, 'web_search_config') else False
            filename = demo_content or "Inception.2010.1080p.BluRay.x264.mp4"
            if scenario == "series_scrape":
                filename = demo_content or "Breaking.Bad.S01E01.1080p.BluRay.x264.mp4"

            result = scraper.scrape(filename)
            elapsed = int((_time.time() - start) * 1000)
            json_response(self, 200, data={
                "success": True,
                "scenario": scenario,
                "input": filename,
                "result": result,
                "search_enhanced": search_enhanced,
                "elapsed_ms": elapsed,
            })

        except Exception as e:
            import traceback
            json_response(self, 200, data={"success": False, "message": "演示异常: " + str(e)})

    def _config_test_hermes(self, *, body: dict, params: dict, query: dict):
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

    def _config_test_tmdb(self, *, body: dict, params: dict, query: dict):
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

        # AI 配置检查：ai_assist 或 ai_search 任一配置完整即视为可用
        try:
            ai_assist = globals._config.get("ai_assist", {}) if globals._config else {}
            ai_search = globals._config.get("ai_search", {}) if globals._config else {}
            assist_ok = bool(
                ai_assist.get("api_key") and ai_assist.get("base_url") and ai_assist.get("model")
            )
            search_ok = bool(
                ai_search.get("api_key") and ai_search.get("model")
            )
            checks["ai_api"] = "ok" if (assist_ok or search_ok) else "skipped"
            checks["ai_assist_configured"] = "ok" if assist_ok else "skipped"
            checks["ai_search_configured"] = "ok" if search_ok else "skipped"
        except Exception:
            checks["ai_api"] = "skipped"

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
