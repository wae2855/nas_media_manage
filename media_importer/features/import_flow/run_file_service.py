import os
import threading
from dataclasses import dataclass
from datetime import datetime
from typing import Callable, Optional

from media_importer.features.configuration import inspect_processing_support_readiness
from media_importer.infrastructure.filesystem import (
    make_fingerprint,
    validate_file_ext,
    validate_path_safety,
)


@dataclass
class RunFileResult:
    code: int
    message: str = ""
    data: Optional[dict] = None


def run_batch_for_api(
    pipeline,
    thread_factory: Callable = threading.Thread,
) -> RunFileResult:
    if pipeline is None:
        return RunFileResult(code=500, message="Pipeline not initialized")
    readiness = inspect_processing_support_readiness(
        getattr(pipeline, "config", {}) or {},
    )
    if readiness["state"] != "READY":
        return RunFileResult(code=409, message="配置尚未就绪，请先处理存储检查中的阻塞项")

    def run_background():
        pipeline.run_all()

    thread = thread_factory(target=run_background, daemon=True)
    thread.start()
    return RunFileResult(code=202, message="已启动批量扫描，新任务稍后会出现在工作台")


def run_file_for_api(
    config: dict,
    task_manager,
    pipeline,
    file_path: str,
    thread_factory: Callable = threading.Thread,
) -> RunFileResult:
    if pipeline is None:
        return RunFileResult(code=500, message="Pipeline not initialized")
    if not file_path:
        return RunFileResult(code=400, message="Missing 'path' field")

    source_dir = config.get("source_dir", "") if config else ""
    allowed_dirs = [source_dir] if source_dir else []
    ok, message = validate_path_safety(file_path, allowed_base_dirs=allowed_dirs)
    if not ok:
        return RunFileResult(code=400, message=f"路径校验失败: {message}")

    ok, message = validate_file_ext(file_path, _media_extensions(config or {}))
    if not ok:
        return RunFileResult(code=400, message=f"文件类型校验失败: {message}")

    if not os.path.isfile(file_path):
        return RunFileResult(code=404, message=f"File not found: {file_path}")

    readiness = inspect_processing_support_readiness(config or {})
    if readiness["state"] != "READY":
        return RunFileResult(code=409, message="配置尚未就绪，请先处理存储检查中的阻塞项")

    stat = os.stat(file_path)
    source_unit_id = ""
    if (config.get("source_policy", {}) or {}).get("mode") == "recycle_source_unit":
        from media_importer.features.source_files import register_source_unit

        source_unit_id = register_source_unit(
            task_manager.conn, source_dir, file_path, config=config
        ).unit_id
    result = task_manager.create_or_reuse_source_task(
        video_path=file_path,
        video_file=os.path.basename(file_path),
        subtitle_files=[],
        file_size_mb=stat.st_size / (1024 * 1024),
        source_unit_id=source_unit_id,
        source_fingerprint=make_fingerprint(file_path),
        source_file_size=stat.st_size,
        source_mtime=datetime.fromtimestamp(stat.st_mtime).isoformat(),
    )
    if not result["created"]:
        task = result.get("task") or {}
        return RunFileResult(
            code=409,
            message=result.get("reason", "同一来源已有任务"),
            data={
                "task_id": task.get("task_id") or result.get("task_id"),
                "status": task.get("status") or result.get("old_status"),
                "stage": task.get("stage", ""),
                "action": result.get("action", "SKIP"),
            },
        )

    task = result["task"]

    def run_one():
        pipeline.process_one(task)

    thread = thread_factory(target=run_one, daemon=True)
    thread.start()
    return RunFileResult(
        code=202,
        message=f"已启动处理: {file_path}",
        data={"task_id": task["task_id"]},
    )


def _media_extensions(config: dict) -> set:
    video_exts = config.get("video_extensions", [])
    sub_exts = config.get("subtitle_extensions", [])
    return {
        ext.lower() if ext.startswith(".") else f".{ext.lower()}"
        for ext in video_exts + sub_exts
    }
