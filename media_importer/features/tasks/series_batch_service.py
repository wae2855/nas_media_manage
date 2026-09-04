"""Safe discovery of pending TV episodes that can share a manual Provider choice."""

from __future__ import annotations

import os
import re
import unicodedata
from collections import Counter
from datetime import datetime

from media_importer.features.scraping import FilenameCleaner

_PENDING_REVIEW = ("PENDING", "AWAIT_REVIEW")


def _normalize_title(value: object) -> str:
    text = unicodedata.normalize("NFKC", str(value or "")).casefold()
    return re.sub(r"[^0-9a-z\u3400-\u9fff]+", "", text)


def _task_titles(task: dict) -> set[str]:
    source_name = os.path.basename(
        str(task.get("source_path") or task.get("source_filename") or "")
    )
    try:
        clean = FilenameCleaner().clean(source_name)
    except (TypeError, ValueError):
        return set()
    values = list(getattr(clean, "title_candidates", []) or [])
    values.extend(
        [
            getattr(clean, "clean_title", ""),
            getattr(clean, "cjk_title", ""),
        ]
    )
    return {key for value in values if (key := _normalize_title(value))}


def _task_episode(task: dict) -> tuple[int, int] | None:
    result = task.get("scrape_result") or {}
    dimensions = task.get("scrape_dimensions") or {}
    if not isinstance(result, dict):
        result = {}
    if not isinstance(dimensions, dict):
        dimensions = {}
    source_name = os.path.basename(
        str(task.get("source_path") or task.get("source_filename") or "")
    )
    try:
        clean = FilenameCleaner().clean(source_name)
    except (TypeError, ValueError):
        return None
    season = (
        result.get("season")
        if result.get("season") not in (None, "")
        else dimensions.get("season", task.get("scrape_season"))
    )
    episode = (
        result.get("episode")
        if result.get("episode") not in (None, "")
        else dimensions.get("episode", task.get("scrape_episode"))
    )
    if season in (None, ""):
        season = clean.season
    if episode in (None, ""):
        episode = clean.episode
    try:
        parsed = (int(season), int(episode))
    except (TypeError, ValueError):
        return None
    if parsed[0] < 0 or parsed[1] < 0:
        return None
    return parsed


def _source_parent(task: dict) -> str:
    source_path = str(task.get("source_path") or "")
    if not source_path:
        return ""
    return os.path.normcase(os.path.realpath(os.path.dirname(source_path)))


def _task_media_type(task: dict) -> str:
    result = task.get("scrape_result") or {}
    result_media_type = result.get("media_type") if isinstance(result, dict) else ""
    return str(task.get("scrape_media_type") or result_media_type or "")


def _manual_provider_conflicts(task: dict, selection: dict) -> bool:
    binding = task.get("manual_provider_binding") or {}
    if isinstance(binding, dict) and binding.get("provider_type") and binding.get("item_id"):
        return (
            str(binding.get("provider_type")),
            str(binding.get("item_id")),
        ) != (
            str(selection.get("provider_type") or ""),
            str(selection.get("item_id") or ""),
        )
    trace = task.get("scrape_trace") or {}
    if not isinstance(trace, dict) or not trace.get("manual_selected"):
        return False
    current = (
        str(task.get("provider_type") or trace.get("provider_type") or ""),
        str(task.get("provider_id") or trace.get("provider_id") or ""),
    )
    selected = (
        str(selection.get("provider_type") or ""),
        str(selection.get("item_id") or ""),
    )
    return bool(all(current) and current != selected)


def _has_unresolved_conflict(task: dict) -> bool:
    dedup = task.get("dedup_result") or {}
    return bool(
        isinstance(dedup, dict)
        and dedup.get("is_duplicate")
        and dedup.get("status") == "awaiting_user"
    )


def discover_series_batch(task_manager, task_id: str, selection: dict) -> dict:
    """Return a conservative, user-previewable batch including the anchor task."""

    if task_manager is None:
        raise ValueError("TaskManager not initialized")
    anchor = task_manager.get_task(task_id)
    if not anchor:
        raise ValueError(f"Task not found: {task_id}")
    if str(selection.get("media_type") or "") != "tv":
        return {"anchor_task_id": task_id, "tasks": [], "excluded": []}
    if (anchor.get("status"), anchor.get("stage")) != _PENDING_REVIEW:
        raise ValueError("只有等待人工确认的电视剧任务可以查找同剧分集")

    anchor_titles = _task_titles(anchor)
    anchor_parent = _source_parent(anchor)
    anchor_episode = _task_episode(anchor)
    if not anchor_titles or not anchor_parent or anchor_episode is None:
        return {"anchor_task_id": task_id, "tasks": [], "excluded": []}

    rows = task_manager.list_tasks(status="PENDING", limit=1000)
    candidates: list[tuple[dict, tuple[int, int]]] = []
    excluded: list[dict] = []
    for summary in rows:
        candidate_id = str(summary.get("task_id") or "")
        task = anchor if candidate_id == task_id else task_manager.get_task(candidate_id)
        if not task:
            continue
        reason = ""
        media_type = _task_media_type(task)
        episode = None
        state = (task.get("status"), task.get("stage"))
        if task.get("status") != "PENDING" or task.get("stage") not in {
            "AWAIT_REVIEW", "QUEUED", "RUNNING",
        }:
            reason = "state_changed"
        elif task.get("task_kind") == "REORGANIZE":
            reason = "reorganization"
        elif media_type and media_type != "tv":
            reason = "not_tv"
        elif _source_parent(task) != anchor_parent:
            reason = "different_directory"
        elif not (_task_titles(task) & anchor_titles):
            reason = "different_title"
        else:
            episode = _task_episode(task)
            if episode is None:
                reason = "missing_episode"
            elif (
                state == _PENDING_REVIEW
                and candidate_id != task_id
                and _has_unresolved_conflict(task)
            ):
                reason = "library_conflict"
            elif candidate_id != task_id and _manual_provider_conflicts(task, selection):
                reason = "different_manual_provider"
        if reason:
            excluded.append({"task_id": candidate_id, "reason": reason})
        elif episode is not None:
            candidates.append((task, episode))

    duplicate_episodes = {
        episode for episode, count in Counter(ep for _, ep in candidates).items() if count > 1
    }
    tasks = []
    for task, episode in candidates:
        candidate_id = str(task.get("task_id") or "")
        if episode in duplicate_episodes and candidate_id != task_id:
            excluded.append({"task_id": candidate_id, "reason": "duplicate_episode"})
            continue
        tasks.append(
            {
                "task_id": candidate_id,
                "source_filename": task.get("source_filename")
                or os.path.basename(str(task.get("source_path") or "")),
                "season": episode[0],
                "episode": episode[1],
                "is_anchor": candidate_id == task_id,
                "stage": task.get("stage"),
                "handling": {
                    "AWAIT_REVIEW": "queue_with_binding",
                    "QUEUED": "bind_queued",
                    "RUNNING": "processing_unchanged",
                }.get(str(task.get("stage")), "excluded"),
                "selectable": task.get("stage") in {"AWAIT_REVIEW", "QUEUED"},
            }
        )
    tasks.sort(key=lambda item: (item["season"], item["episode"], item["task_id"]))
    return {"anchor_task_id": task_id, "tasks": tasks, "excluded": excluded}


def build_manual_provider_binding(
    selection: dict,
    *,
    season: int | None,
    episode: int | None,
) -> dict:
    """Build the minimum durable intent needed to reuse a manual TV identity."""

    return {
        "provider_type": str(selection.get("provider_type") or ""),
        "item_id": str(selection.get("item_id") or ""),
        "media_type": str(selection.get("media_type") or ""),
        "language": str(selection.get("language") or ""),
        "season": int(season) if season is not None else None,
        "episode": int(episode) if episode is not None else None,
        "requested_at": datetime.now().isoformat(),
    }


def queue_manual_provider_binding(
    task_manager,
    task_id: str,
    selection: dict,
    *,
    season: int | None,
    episode: int | None,
) -> tuple[dict | None, str]:
    """Persist a manual identity and make an awaiting task honestly queued."""

    from media_importer.features.tasks.transitions import apply
    from media_importer.infrastructure.db import compare_and_update_task

    task = task_manager.get_task(task_id)
    if not task or task.get("status") != "PENDING":
        return None, "state_changed"
    binding = build_manual_provider_binding(
        selection,
        season=season,
        episode=episode,
    )
    stage = str(task.get("stage") or "")
    if stage == "AWAIT_REVIEW":
        fields = apply(task, "manual_bind_queue", manual_provider_binding=binding)
        updated = compare_and_update_task(
            task_manager.conn,
            task_id,
            expect_status="PENDING",
            expect_stage="AWAIT_REVIEW",
            **fields,
        )
        return updated, "queued_with_binding" if updated else "state_changed"
    if stage == "QUEUED":
        updated = compare_and_update_task(
            task_manager.conn,
            task_id,
            expect_status="PENDING",
            expect_stage="QUEUED",
            manual_provider_binding=binding,
        )
        return updated, "bound_queued" if updated else "state_changed"
    if stage == "RUNNING":
        return None, "processing_unchanged"
    return None, "state_changed"
