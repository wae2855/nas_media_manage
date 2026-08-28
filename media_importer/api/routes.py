from dataclasses import dataclass, field
from typing import Optional


@dataclass(frozen=True)
class APIRoute:
    """API 路由声明。handler 统一签名：handler(self, *, body, params, query)。

    - `body`: POST/PUT 请求体 dict（GET 时为空 dict）
    - `params`: 路径参数 dict（如 {task_id} → {"task_id": "..."}）
    - `query`: URL 查询参数 dict（parse_qs 后的结果）
    """

    method: str
    pattern: str
    handler_name: str
    auth_required: bool = True
    param_names: tuple = field(init=False)
    pattern_parts: tuple = field(init=False)

    def __post_init__(self):
        parts = tuple(part for part in self.pattern.strip("/").split("/") if part)
        object.__setattr__(self, "pattern_parts", parts)
        object.__setattr__(
            self,
            "param_names",
            tuple(part[1:-1] for part in parts if part.startswith("{") and part.endswith("}")),
        )


@dataclass(frozen=True)
class RouteMatch:
    route: APIRoute
    params: dict


def _route(method: str, pattern: str, handler_name: str, **kwargs) -> APIRoute:
    return APIRoute(method=method, pattern=pattern, handler_name=handler_name, **kwargs)


API_ROUTES = [
    _route("GET", "/api/health", "_health", auth_required=False),
    _route("GET", "/api/metrics", "_metrics"),
    _route("GET", "/api/config", "_config"),
    _route("GET", "/api/config/validate", "_config_validate"),
    _route("GET", "/api/watcher/status", "_watcher_status"),
    _route("GET", "/api/tasks", "_list_tasks"),
    _route("GET", "/api/tasks/stats", "_task_stats"),
    _route("GET", "/api/tasks/{task_id}/subtitles", "_task_subtitles"),
    _route("GET", "/api/tasks/{task_id}", "_get_task"),
    _route("GET", "/api/queue/status", "_queue_status"),
    _route("GET", "/api/logs", "_logs"),
    _route("GET", "/api/dimensions", "_dimensions_list"),
    _route("GET", "/api/dimensions/enabled", "_dimensions_enabled"),
    _route("GET", "/api/dimensions/{dim_name}", "_dimension_get"),
    _route("GET", "/api/providers", "_providers_list"),
    _route("GET", "/api/providers/{provider_type}/genres", "_provider_genres_list"),
    _route("GET", "/api/source-cleaner/preview", "source_cleaner_preview"),
    _route("GET", "/api/source-cleaner/records", "source_cleaner_records"),
    _route("GET", "/api/source-cleaner/status", "source_cleaner_status"),
    _route("GET", "/api/source-cleaner/ai-preview", "source_cleaner_ai_preview"),
    _route("GET", "/api/thumbnails", "_thumbnails_list"),
    _route("GET", "/api/thumbnails/{filename}", "_thumbnails_serve"),
    _route("GET", "/api/recycle/list", "recycle_list"),
    _route("POST", "/api/run", "_run_batch"),
    _route("POST", "/api/restart", "_restart_service"),
    _route("POST", "/api/watcher/control", "_watcher_control"),
    _route("POST", "/api/run/file", "_run_file"),
    _route("POST", "/api/tasks/clear", "_clear_tasks"),
    _route("POST", "/api/tasks/confirm-all", "_task_confirm_all"),
    _route("POST", "/api/tasks/{task_id}/cancel", "_task_cancel"),
    _route("POST", "/api/tasks/{task_id}/retry", "_retry_task"),
    _route("POST", "/api/tasks/{task_id}/confirm", "_task_confirm"),
    _route("POST", "/api/tasks/{task_id}/preview", "_task_preview"),
    _route("POST", "/api/tasks/{task_id}/scrape-search", "_task_scrape_search"),
    _route("POST", "/api/tasks/{task_id}/reclassify", "_task_reclassify"),
    _route("POST", "/api/tasks/{task_id}/classify-preview", "_task_classify_preview"),
    _route("POST", "/api/tasks/{task_id}/ignore", "_task_ignore"),
    _route("POST", "/api/tasks/{task_id}/rename", "_task_rename"),
    _route("POST", "/api/tasks/{task_id}/delete", "_delete_task"),
    _route("POST", "/api/queue/pause", "_queue_pause"),
    _route("POST", "/api/queue/resume", "_queue_resume"),
    _route("POST", "/api/queue/retry-all", "_queue_retry_all"),
    _route("POST", "/api/config/reload", "_config_reload"),
    _route("POST", "/api/config/test-llm", "_config_test_llm"),
    _route("POST", "/api/scrape/preview/start", "_scrape_preview_start"),
    _route("GET", "/api/scrape/preview/status/{job_id}", "_scrape_preview_status"),
    _route("POST", "/api/providers/{provider_type}/test", "_provider_test"),
    _route("POST", "/api/providers/{provider_type}/preview", "_provider_preview"),
    _route("POST", "/api/providers/{provider_type}/search", "_provider_search"),
    _route("POST", "/api/providers/{provider_type}/details", "_provider_details"),
    _route("POST", "/api/config/check-permission", "_config_check_permission"),
    _route("POST", "/api/path/test", "_path_test"),
    _route("POST", "/api/config/section", "_config_save_section"),
    _route("POST", "/api/config", "_config_save"),
    _route("POST", "/api/dimensions/{dim_name}/enable", "_dimension_enable"),
    _route("POST", "/api/dimensions/{dim_name}/disable", "_dimension_disable"),
    _route("POST", "/api/dimensions/{dim_name}/reset", "_dimension_reset"),
    _route("POST", "/api/source-cleaner/execute", "source_cleaner_execute"),
    _route("POST", "/api/recycle/restore", "recycle_restore"),
    _route("POST", "/api/recycle/delete", "recycle_delete"),
    _route("PUT", "/api/dimensions/{dim_name}", "_dimension_update"),
    _route("DELETE", "/api/tasks/{task_id}", "_delete_task"),
]


def match_route(method: str, path: str) -> Optional[RouteMatch]:
    method = method.upper()
    path_parts = tuple(part for part in path.strip("/").split("/") if part)
    for route in API_ROUTES:
        if route.method != method:
            continue
        if len(route.pattern_parts) != len(path_parts):
            continue
        params = {}
        matched = True
        for pattern_part, path_part in zip(route.pattern_parts, path_parts, strict=False):
            if pattern_part.startswith("{") and pattern_part.endswith("}"):
                params[pattern_part[1:-1]] = path_part
            elif pattern_part != path_part:
                matched = False
                break
        if matched:
            return RouteMatch(route=route, params=params)
    return None
