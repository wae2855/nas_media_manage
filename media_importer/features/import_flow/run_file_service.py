import os
import threading
from dataclasses import dataclass
from typing import Callable, Optional

from media_importer.infrastructure.filesystem import validate_file_ext, validate_path_safety


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

    def run_background():
        pipeline.run_all()

    thread = thread_factory(target=run_background, daemon=True)
    thread.start()
    return RunFileResult(code=202, message="Batch processing started in background")


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

    def run_one():
        video_file = os.path.basename(file_path)
        task = task_manager.create_task(
            video_path=file_path,
            video_file=video_file,
            subtitle_files=[],
            file_size_mb=os.path.getsize(file_path) / (1024 * 1024),
        )
        pipeline.process_one(task)

    thread = thread_factory(target=run_one, daemon=True)
    thread.start()
    return RunFileResult(code=202, message=f"Processing started: {file_path}")


def _media_extensions(config: dict) -> set:
    video_exts = config.get("video_extensions", [])
    sub_exts = config.get("subtitle_extensions", [])
    return {
        ext.lower() if ext.startswith(".") else f".{ext.lower()}"
        for ext in video_exts + sub_exts
    }
