"""首页业务摘要：把任务事实转换为普通用户能理解的状态。"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta

from media_importer.features.scraping.thumbnail_cache import (
    prune_thumbnail_cache,
    recent_movie_items,
)

from .repository import get_dashboard_task_snapshot


@dataclass
class DashboardSummaryResult:
    code: int
    data: dict = field(default_factory=dict)
    message: str = ""


def _task_title(task: dict) -> str:
    return str(
        task.get("scrape_title_cn")
        or task.get("scrape_title_en")
        or task.get("source_filename")
        or "未命名影片"
    )


def _activity(task: dict) -> dict:
    status = str(task.get("status") or "").upper()
    stage = str(task.get("stage") or "").upper()
    title = _task_title(task)
    occurred_at = task.get("completed_at") or task.get("started_at") or task.get("created_at")
    if status == "SUCCESS":
        event_title, copy, tone = "入库完成", f"《{title}》已经写入片库", "success"
    elif status == "PENDING" and stage == "AWAIT_REVIEW":
        event_title, copy, tone = "等待确认", f"《{title}》需要你核对识别或分类结果", "warning"
    elif status == "PENDING" and stage == "RUNNING":
        percent = max(0, min(100, int(task.get("percentage") or 0)))
        event_title, copy, tone = "正在整理", f"《{title}》当前完成 {percent}%", "running"
    elif status == "PENDING" and stage == "QUEUED":
        event_title, copy, tone = "等待处理", f"《{title}》已经进入整理队列", "queued"
    elif status == "FAILED":
        reason = str(task.get("error_message") or "请查看任务详情后重试")
        event_title, copy, tone = "处理失败", f"《{title}》：{reason}", "error"
    elif status == "SKIPPED":
        reason = str(task.get("skip_reason") or "已按用户选择跳过")
        event_title, copy, tone = "已跳过", f"《{title}》：{reason}", "muted"
    elif status == "CANCELLED":
        event_title, copy, tone = "已取消", f"《{title}》未继续处理", "muted"
    else:
        event_title, copy, tone = "任务已更新", f"《{title}》状态已经变化", "muted"
    return {
        "task_id": str(task.get("task_id") or ""),
        "title": event_title,
        "copy": copy,
        "tone": tone,
        "timestamp": occurred_at,
    }


def get_dashboard_summary_for_api(
    task_manager,
    *,
    paused: bool,
    thumbnail_dir: str,
    protected_roots: list[str] | None = None,
) -> DashboardSummaryResult:
    if not task_manager:
        return DashboardSummaryResult(code=503, message="任务服务尚未就绪")
    day_start_dt = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    day_end_dt = day_start_dt + timedelta(days=1)
    snapshot = get_dashboard_task_snapshot(
        task_manager.conn,
        day_start=day_start_dt.isoformat(),
        day_end=day_end_dt.isoformat(),
    )
    counts = {"queued": 0, "running": 0, "await_review": 0, "failed": 0}
    running_progress = 0
    for row in snapshot["grouped"]:
        status = str(row.get("status") or "").upper()
        stage = str(row.get("stage") or "").upper()
        count = int(row.get("cnt") or 0)
        if status == "PENDING" and stage == "QUEUED":
            counts["queued"] += count
        elif status == "PENDING" and stage == "RUNNING":
            counts["running"] += count
            running_progress = round(float(row.get("avg_progress") or 0))
        elif status == "PENDING" and stage == "AWAIT_REVIEW":
            counts["await_review"] += count
        elif status == "FAILED":
            counts["failed"] += count

    movies = recent_movie_items(snapshot["movies"], thumbnail_dir, limit=12)
    protected = set(snapshot["protected_thumbnail_paths"])
    protected.update(item["_path"] for item in movies)
    cache = prune_thumbnail_cache(
        thumbnail_dir,
        protected,
        protected_roots=protected_roots,
    )
    for item in movies:
        item.pop("_path", None)

    return DashboardSummaryResult(
        code=200,
        data={
            "paused": bool(paused),
            "counts": counts,
            "running_progress": max(0, min(100, running_progress)),
            "today_success": snapshot["today_success"],
            "activities": [_activity(task) for task in snapshot["events"][:5]],
            "recent_movies": movies,
            "thumbnail_cache": cache,
        },
    )
