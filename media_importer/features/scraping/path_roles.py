"""Classify media path segments for identity and inheritance decisions."""

from __future__ import annotations

import re
import unicodedata

_SUPPLEMENTARY_NAMES = {
    "extra",
    "extras",
    "trailer",
    "trailers",
    "featurette",
    "featurettes",
    "sample",
    "samples",
    "behind the scenes",
    "deleted scenes",
    "interview",
    "interviews",
    "short",
    "shorts",
    "other",
    "bonus",
    "bonuses",
    "special features",
}

_GENERIC_NAMES = {
    "download",
    "downloads",
    "completed",
    "incoming",
    "movie",
    "movies",
    "film",
    "films",
    "video",
    "videos",
    "tv",
    "series",
    "media",
    "temp",
    "tmp",
    "cache",
    "下载",
    "下载完成",
    "已完成",
    "完成",
    "电影",
    "影片",
    "视频",
    "电视剧",
    "剧集",
    "媒体",
    "临时",
    "缓存",
    "网盘",
}

_STRUCTURAL_DIRECTORY = re.compile(
    r"^(?:bdmv|stream|video ts|specials|season\s*\d{1,2}|"
    r"第\s*[零〇一二两三四五六七八九十百\d]+\s*季|s\d{1,2}|"
    r"disc(?:\s*\d+)?|disk(?:\s*\d+)?|cd(?:\s*\d+)?)$",
    re.IGNORECASE,
)

_TECHNICAL_NAMES = {
    "4k",
    "uhd",
    "bluray",
    "blu ray",
    "remux",
    "web dl",
    "webrip",
    "hdtv",
    "complete",
}
_TECHNICAL_DIRECTORY = re.compile(
    r"^(?:\d{3,4}[pi]|(?:bd|web|hdtv|uhd|hdr|sdr|dv|hevc|avc|x26[45])(?:\s*\d{3,4}[pi])?)$",
    re.IGNORECASE,
)
_DATE_OR_NUMBER_DIRECTORY = re.compile(r"^(?:\d{1,4}|\d{4}[-_.]\d{1,2}(?:[-_.]\d{1,2})?|\d{8,14})$")
_HASH_DIRECTORY = re.compile(r"^[a-f0-9]{12,64}$", re.IGNORECASE)


def _normalized_segment(value: str) -> str:
    text = unicodedata.normalize("NFKC", str(value or "")).casefold().strip()
    text = re.sub(r"[._-]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def is_supplementary_directory(name: str) -> bool:
    return _normalized_segment(name) in _SUPPLEMENTARY_NAMES


def is_structural_directory(name: str) -> bool:
    return bool(_STRUCTURAL_DIRECTORY.fullmatch(_normalized_segment(name)))


def _parse_chinese_number(value: str) -> int:
    if value.isdigit():
        return int(value)
    digits = {
        "零": 0, "〇": 0, "一": 1, "二": 2, "两": 2, "三": 3,
        "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9,
    }
    if "百" in value:
        left, right = value.split("百", 1)
        return digits.get(left, 1) * 100 + (_parse_chinese_number(right) if right else 0)
    if "十" in value:
        left, right = value.split("十", 1)
        return digits.get(left, 1) * 10 + (digits.get(right, 0) if right else 0)
    result = 0
    for char in value:
        result = result * 10 + digits[char]
    return result


def structural_season(name: str) -> int | None:
    """Return season encoded by a structural directory, including Specials."""
    normalized = _normalized_segment(name)
    if normalized == "specials":
        return 0
    match = re.fullmatch(r"(?:season\s*|s)(\d{1,2})", normalized, re.IGNORECASE)
    if match:
        return int(match.group(1))
    match = re.fullmatch(
        r"第\s*([零〇一二两三四五六七八九十百\d]+)\s*季",
        normalized,
    )
    return _parse_chinese_number(match.group(1)) if match else None


def is_technical_directory(name: str) -> bool:
    normalized = _normalized_segment(name)
    return normalized in _TECHNICAL_NAMES or bool(_TECHNICAL_DIRECTORY.fullmatch(normalized))


def is_generic_directory(name: str) -> bool:
    normalized = _normalized_segment(name)
    compact = normalized.replace(" ", "")
    return (
        not compact
        or normalized in _GENERIC_NAMES
        or compact in _GENERIC_NAMES
        or bool(_DATE_OR_NUMBER_DIRECTORY.fullmatch(compact))
        or bool(_HASH_DIRECTORY.fullmatch(compact))
    )
