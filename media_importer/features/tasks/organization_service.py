"""兜底入库结果与关联重新整理任务。"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import datetime

from media_importer.features.configuration import configured_library_roots, path_within
from media_importer.features.configuration.library_paths import (
    canonicalize_library_config,
    library_root_by_id,
    resolve_library_template,
    resolve_rule_template,
)
from media_importer.features.organization_state import (
    ORGANIZATION_FALLBACK_PENDING,
    ORGANIZATION_ORGANIZED,
    TASK_KIND_REORGANIZE,
)
from media_importer.infrastructure.db import (
    find_active_reorganization,
    get_enabled_dimensions,
    get_subtitles_by_task,
    get_task,
    list_all_tasks,
    update_subtitle,
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
    *,
    mode: str = "rules",
    library_root_id: str = "",
    relative_dir: str = "",
) -> OrganizationActionResult:
    if task_manager is None:
        return OrganizationActionResult(code=500, message="TaskManager not initialized")
    parent = task_manager.get_task(parent_task_id)
    if not parent:
        return OrganizationActionResult(code=404, message="原入库任务不存在")
    if parent.get("status") != "SUCCESS" or not parent.get("import_success"):
        return OrganizationActionResult(code=400, message="只有已经成功入库的任务可以重新整理")
    mode = str(mode or "rules").strip().lower()
    if mode not in {"rules", "custom"}:
        return OrganizationActionResult(code=400, message="调整方式无效")
    organization_status = str(parent.get("organization_status") or "")
    if organization_status != ORGANIZATION_FALLBACK_PENDING and task_used_fallback(config, parent):
        parent = update_task(
            task_manager.conn,
            parent_task_id,
            used_fallback=1,
            organization_status=ORGANIZATION_FALLBACK_PENDING,
        ) or parent
        organization_status = ORGANIZATION_FALLBACK_PENDING
    is_fallback = organization_status == ORGANIZATION_FALLBACK_PENDING

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

    target_dir = str(parent.get("import_path") or os.path.dirname(video_path))
    classify_result_text = str(
        parent.get("classify_result") or os.path.dirname(video_path)
    )
    target_used_fallback = is_fallback
    target_root_id = ""
    target_relative_dir = ""
    if mode == "custom":
        try:
            root = library_root_by_id(config or {}, str(library_root_id or "").strip())
            target_root_id = str(root["id"])
            target_relative_dir = str(relative_dir or "").strip()
            if not target_relative_dir or target_relative_dir in {".", os.curdir}:
                raise ValueError("请选择目标片库内的具体子目录")
            target_dir = resolve_library_template(
                str(root["path"]),
                target_relative_dir,
                {},
            )
        except (KeyError, ValueError) as exc:
            return OrganizationActionResult(code=400, message=str(exc))
        final_path = os.path.join(target_dir, os.path.basename(video_path))
        if os.path.realpath(final_path) == os.path.realpath(video_path):
            return OrganizationActionResult(code=400, message="目标位置与当前位置相同，无需调整")
        classify_result_text = f"人工指定目录: {target_dir}"
        target_used_fallback = False
    elif not is_fallback:
        try:
            from media_importer.features.import_flow.services import ClassificationService

            enabled_names = {
                item["name"] for item in get_enabled_dimensions(task_manager.conn)
            }
            classified = ClassificationService(config or {}).classify_task(
                dict(parent),
                enabled_names,
            )
            if classified.import_path:
                target_dir = classified.import_path
                classify_result_text = classified.classify_result
                target_used_fallback = bool(classified.used_fallback)
        except (KeyError, ValueError):
            # 仍创建显式待确认任务，让用户在详情中修正维度或改用指定目录。
            target_used_fallback = True

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
            "code": (
                "FALLBACK_REORGANIZATION"
                if is_fallback and mode == "rules"
                else "USER_REQUESTED_REORGANIZATION"
            ),
            "message": (
                "影片已在待整理区，请重新刮削或调整维度以匹配正式入库规则"
                if is_fallback and mode == "rules"
                else "用户主动调整已入库影片位置，请核对原位置和目标位置后确认"
            ),
        }],
        "match_trace": {},
        "import_path": target_dir,
        "classify_result": classify_result_text,
        "final_filename": os.path.basename(video_path),
        "used_fallback": 1 if target_used_fallback else 0,
        "organization_status": "",
        "reorganization_intent": {
            "reason": "user_requested" if not (is_fallback and mode == "rules") else "fallback",
            "mode": mode,
            "source_path": os.path.realpath(video_path),
            "target_library_root_id": target_root_id,
            "target_relative_dir": target_relative_dir,
            "target_dir": os.path.realpath(target_dir),
            "target_path": os.path.realpath(
                os.path.join(target_dir, os.path.basename(video_path))
            ),
            "requested_at": datetime.now().isoformat(),
        },
        "source_cleanup_status": "SKIPPED",
        "error_message": "",
        "skip_reason": "",
    })
    child = update_task(task_manager.conn, task_id, **copied_fields)
    if mode == "custom":
        from media_importer.features.import_flow.services.naming import (
            plan_subtitle_filenames,
        )

        child_subtitles = get_subtitles_by_task(task_manager.conn, task_id)
        subtitle_plan = plan_subtitle_filenames(
            [str(item.get("source_path") or "") for item in child_subtitles],
            os.path.basename(video_path),
            (config.get("filename_templates", {}) or {}).get(
                "subtitle", "{video_filename}.{lang}.{ext}"
            ),
        )
        for subtitle, planned in zip(child_subtitles, subtitle_plan, strict=True):
            update_subtitle(
                task_manager.conn,
                subtitle["id"],
                planned_filename=planned["filename"],
                lang=planned["lang"],
            )
        child = get_task(task_manager.conn, task_id)
    return OrganizationActionResult(
        code=201,
        data={"task": child, "created": True},
        message=(
            "已创建人工调整任务，原入库任务保持已完成"
            if not (is_fallback and mode == "rules")
            else "已创建重新整理任务，原入库任务保持已完成"
        ),
    )
