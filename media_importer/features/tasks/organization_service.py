"""兜底入库结果与关联重新整理任务。"""

from __future__ import annotations

import os
from dataclasses import dataclass, field

from media_importer.features.configuration import configured_library_roots, path_within
from media_importer.features.configuration.library_paths import (
    canonicalize_library_config,
    resolve_rule_template,
)
from media_importer.features.organization_state import (
    ORGANIZATION_FALLBACK_PENDING,
    ORGANIZATION_ORGANIZED,
    TASK_KIND_REORGANIZE,
)
from media_importer.infrastructure.db import (
    find_active_reorganization,
    get_subtitles_by_task,
    get_task,
    list_all_tasks,
    update_task,
)


@dataclass
class OrganizationActionResult:
    code: int
    data: dict = field(default_factory=dict)
    message: str = ""


def fallback_target_for_task(config: dict, task: dict) -> str:
    """Return the stable configured parent of the fallback template."""
    canonical = canonicalize_library_config(config or {})
    fallback = str(canonical.get("fallback_dir", "") or "").strip()
    if not fallback:
        return ""
    # Backfill only needs the invariant fallback parent. Using the static prefix
    # also recognizes old successful tasks when a fallback template contained
    # variables whose historical values were not persisted completely.
    stable_parent = fallback.split("{", 1)[0].rstrip("/")
    if not stable_parent:
        return ""
    return resolve_rule_template(
        canonical,
        None,
        stable_parent,
        {},
        fallback=True,
    )


def task_used_fallback(config: dict, task: dict) -> bool:
    if str(task.get("organization_status", "")) == ORGANIZATION_ORGANIZED:
        return False
    if bool(task.get("used_fallback")):
        return True
    if str(task.get("organization_status", "")) == ORGANIZATION_FALLBACK_PENDING:
        return True
    target = fallback_target_for_task(config, task)
    if not target:
        return False
    result_path = (
        task.get("import_video_path")
        or task.get("video_path")
        or task.get("import_path")
        or ""
    )
    return bool(result_path) and path_within(str(result_path), target)


def backfill_fallback_outcomes(conn, config: dict) -> int:
    """为旧版本已经落入当前兜底目录的成功任务补结果标记。"""
    changed = 0
    for row in list_all_tasks(conn, limit=10000):
        if (
            row.get("status") != "SUCCESS"
            or not row.get("import_success")
            or row.get("organization_status")
        ):
            continue
        task = get_task(conn, row["task_id"]) or row
        if not task_used_fallback(config, task):
            continue
        update_task(
            conn,
            row["task_id"],
            used_fallback=1,
            organization_status=ORGANIZATION_FALLBACK_PENDING,
        )
        changed += 1
    return changed


def create_reorganization_task_for_api(
    task_manager,
    config: dict,
    parent_task_id: str,
) -> OrganizationActionResult:
    if task_manager is None:
        return OrganizationActionResult(code=500, message="TaskManager not initialized")
    parent = task_manager.get_task(parent_task_id)
    if not parent:
        return OrganizationActionResult(code=404, message="原入库任务不存在")
    if parent.get("status") != "SUCCESS" or not parent.get("import_success"):
        return OrganizationActionResult(code=400, message="只有已经成功入库的任务可以重新整理")
    organization_status = str(parent.get("organization_status") or "")
    if organization_status == ORGANIZATION_ORGANIZED:
        return OrganizationActionResult(code=400, message="该影片已经按正式规则整理完成")
    if organization_status != ORGANIZATION_FALLBACK_PENDING and task_used_fallback(config, parent):
        parent = update_task(
            task_manager.conn,
            parent_task_id,
            used_fallback=1,
            organization_status=ORGANIZATION_FALLBACK_PENDING,
        ) or parent
        organization_status = ORGANIZATION_FALLBACK_PENDING
    if organization_status != ORGANIZATION_FALLBACK_PENDING:
        return OrganizationActionResult(code=400, message="该影片不在待整理区，无需创建重新整理任务")

    active = find_active_reorganization(task_manager.conn, parent_task_id)
    if active:
        return OrganizationActionResult(
            code=200,
            data={"task": get_task(task_manager.conn, active["task_id"]), "created": False},
            message="已经有一条重新整理任务，请继续处理现有任务",
        )

    video_path = str(parent.get("import_video_path") or parent.get("video_path") or "")
    roots = configured_library_roots(config or {})
    if (
        not video_path
        or os.path.islink(video_path)
        or not os.path.isfile(video_path)
        or not any(path_within(video_path, root, allow_root=False) for root in roots)
    ):
        return OrganizationActionResult(
            code=409,
            message="待整理区中的影片不存在或不在已授权片库内，请先运行配置检查",
        )

    parent_subtitles = get_subtitles_by_task(task_manager.conn, parent_task_id)
    subtitle_paths = []
    for subtitle in parent_subtitles:
        path = str(subtitle.get("import_path") or subtitle.get("target_path") or "")
        if path and os.path.isfile(path) and not os.path.islink(path):
            subtitle_paths.append(path)

    created = task_manager.create_task(
        video_path=video_path,
        video_file=os.path.basename(video_path),
        subtitle_files=subtitle_paths,
        file_size_mb=os.path.getsize(video_path) / (1024 * 1024),
        stage="AWAIT_REVIEW",
        task_kind=TASK_KIND_REORGANIZE,
        parent_task_id=parent_task_id,
    )
    task_id = created["task_id"]
    copied_fields = {
        key: parent.get(key)
        for key in (
            "scrape_result", "scrape_title_cn", "scrape_title_en", "scrape_year",
            "scrape_media_type", "scrape_season", "scrape_episode",
            "scrape_dimensions", "scrape_trace", "dim_sources", "provider_type",
            "provider_id", "thumbnail_path",
        )
    }
    copied_fields.update({
        "video_path": video_path,
        "file_location": "import",
        "confirm_status": "PENDING",
        "match_level": "NEEDS_CONFIRM",
        "match_concerns": [{
            "code": "FALLBACK_REORGANIZATION",
            "message": "影片已在待整理区，请重新刮削或调整维度以匹配正式入库规则",
        }],
        "match_trace": {},
        "import_path": str(parent.get("import_path") or os.path.dirname(video_path)),
        "classify_result": str(parent.get("classify_result") or os.path.dirname(video_path)),
        "final_filename": os.path.basename(video_path),
        "used_fallback": 1,
        "organization_status": "",
        "source_cleanup_status": "SKIPPED",
        "error_message": "",
        "skip_reason": "",
    })
    child = update_task(task_manager.conn, task_id, **copied_fields)
    return OrganizationActionResult(
        code=201,
        data={"task": child, "created": True},
        message="已创建重新整理任务，原入库任务保持已完成",
    )
