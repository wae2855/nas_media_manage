#!/usr/bin/env python3
import json
import logging
import shutil
import subprocess

logger = logging.getLogger(__name__)

_ffprobe_available = None


def check_ffprobe_available() -> bool:
    global _ffprobe_available
    if _ffprobe_available is not None:
        return _ffprobe_available
    _ffprobe_available = shutil.which("ffprobe") is not None
    if not _ffprobe_available:
        logger.warning("ffprobe 未找到，分辨率检测不可用")
    return _ffprobe_available


def detect_resolution(video_path: str) -> dict:
    if not check_ffprobe_available():
        return {"width": 0, "height": 0}

    try:
        cmd = [
            "ffprobe",
            "-v", "quiet",
            "-print_format", "json",
            "-show_streams",
            "-select_streams", "v:0",
            video_path,
        ]
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=30
        )
        if result.returncode != 0:
            logger.warning("ffprobe 执行失败: %s", result.stderr[:200])
            return {"width": 0, "height": 0}

        probe_data = json.loads(result.stdout)
        streams = probe_data.get("streams", [])
        if not streams:
            return {"width": 0, "height": 0}

        stream = streams[0]
        width = int(stream.get("width", 0))
        height = int(stream.get("height", 0))
        return {"width": width, "height": height}

    except subprocess.TimeoutExpired:
        logger.warning("ffprobe 超时: %s", video_path)
        return {"width": 0, "height": 0}
    except Exception as e:
        logger.warning("ffprobe 异常: %s - %s", video_path, e)
        return {"width": 0, "height": 0}


def classify_resolution_tier(width: int, value_list: list) -> str:
    sorted_tiers = sorted(
        [v for v in value_list if v.get("value") != "sd" and v.get("min_width", 0) > 0],
        key=lambda x: x.get("min_width", 0),
        reverse=True,
    )
    for tier in sorted_tiers:
        if width >= tier.get("min_width", 0):
            return tier["value"]

    for v in value_list:
        if v.get("value") == "sd":
            return "sd"

    return "sd"


def analyze_file(video_path: str, enabled_file_dimensions: list) -> dict:
    result = {}
    if not enabled_file_dimensions:
        return result

    for dim in enabled_file_dimensions:
        name = dim["name"]
        value_list = dim.get("value_list", [])

        if name == "resolution_tier":
            res = detect_resolution(video_path)
            width = res.get("width", 0)
            if width > 0:
                tier = classify_resolution_tier(width, value_list)
                result[name] = {
                    "value": tier,
                    "source_reliability": 1.0,
                    "source": "file",
                    "detail": f"{res['width']}x{res['height']}",
                }
            else:
                result[name] = {
                    "value": None,
                    "source_reliability": 0,
                    "source": "file",
                    "detail": "ffprobe 未能获取分辨率",
                }

    return result
