"""媒体候选判定。

自动扫描、来源单元快照和智能清理必须共用这里的判定，避免同一个文件在
不同阶段得到互相矛盾的结论。无法可靠读取或无法确定时一律接受，宁可进入
人工确认，也不静默丢弃真实影片。
"""

from __future__ import annotations

import fnmatch
import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

ACCEPT = "accept"
IGNORE_PROMOTION = "ignore_promotion"
IGNORE_SMALL_COMPANION = "ignore_small_companion"
CANDIDATE_POLICY_VERSION = 1

_DEFAULT_VIDEO_EXTENSIONS = (
    ".mkv", ".mp4", ".avi", ".mov", ".wmv", ".flv", ".ts", ".m2ts", ".webm",
)

_PATTERN_ASSET = Path(__file__).with_name("data") / "media_candidate_patterns.v1.json"


def _load_name_preset() -> dict:
    try:
        preset = json.loads(_PATTERN_ASSET.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        preset = {}
    if preset.get("schema_version") != CANDIDATE_POLICY_VERSION:
        preset = {}
    return {
        "action_terms": preset.get("action_terms") or ["更多", "访问", "扫码", "下载"],
        "content_terms": preset.get("content_terms") or ["电影", "影片", "资源", "高清"],
        "domain_tlds": preset.get("domain_tlds") or ["com", "cn", "net", "org"],
    }


_NAME_PRESET = _load_name_preset()
# 只匹配同时具备“引导语 + 网址/域名”的明确推广文件。单独出现“广告”、
# “高清”或电影站点名称均不足以忽略，避免误伤真实片名。
_PROMOTION_ACTION_RE = re.compile(
    r"(?:"
    + "|".join(re.escape(term) for term in _NAME_PRESET["action_terms"])
    + r").{0,16}(?:"
    + "|".join(re.escape(term) for term in _NAME_PRESET["content_terms"])
    + r")",
    re.IGNORECASE,
)
_PROMOTION_DOMAIN_RE = re.compile(
    r"(?:https?://|www\.|[a-z0-9-]{2,}\.(?:"
    + "|".join(re.escape(tld) for tld in _NAME_PRESET["domain_tlds"])
    + r"))",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class CandidateDecision:
    disposition: str
    reason: str
    evidence: dict

    @property
    def accepted(self) -> bool:
        return self.disposition == ACCEPT


class MediaCandidatePolicy:
    """根据文件名和同一来源单元内的体积关系筛选媒体候选。"""

    def __init__(self, config: dict | None = None):
        config = config or {}
        section = config.get("media_candidate_filter", {}) or {}
        legacy = config.get("source_cleaner", {}) or {}
        self.enabled = section.get("enabled", True) is not False
        self.small_video_max_mb = _non_negative_number(
            section.get("small_video_max_mb", legacy.get("junk_video_max_size_mb", 50)),
            50,
        )
        self.main_video_min_mb = _non_negative_number(
            section.get("main_video_min_mb", 500), 500
        )
        self.max_size_ratio = _ratio(section.get("max_size_ratio", 0.02), 0.02)
        patterns = section.get("extra_name_patterns", [])
        self.extra_name_patterns = tuple(
            str(pattern).strip() for pattern in patterns if str(pattern).strip()
        ) if isinstance(patterns, list) else ()
        configured_exts = config.get("video_extensions") or _DEFAULT_VIDEO_EXTENSIONS
        self.video_extensions = {
            str(ext).lower() if str(ext).startswith(".") else f".{str(ext).lower()}"
            for ext in configured_exts
        }

    def classify_tree(
        self,
        source_root: str,
        paths: Iterable[str],
    ) -> dict[str, CandidateDecision]:
        """一次判定一棵来源目录树，体积比较限制在同一来源单元内。"""
        candidates = [
            os.path.realpath(str(path))
            for path in paths
            if Path(str(path)).suffix.lower() in self.video_extensions
        ]
        grouped: dict[str, list[str]] = {}
        for path in candidates:
            grouped.setdefault(self._unit_key(source_root, path), []).append(path)

        decisions: dict[str, CandidateDecision] = {}
        for unit_paths in grouped.values():
            decisions.update(self._classify_unit(unit_paths))
        return decisions

    def _classify_unit(self, paths: list[str]) -> dict[str, CandidateDecision]:
        sizes: dict[str, int | None] = {}
        for path in paths:
            try:
                sizes[path] = os.path.getsize(path)
            except OSError:
                sizes[path] = None
        readable_sizes = [size for size in sizes.values() if size is not None]
        largest = max(readable_sizes, default=0)

        return {
            path: self._classify_one(path, sizes[path], largest)
            for path in paths
        }

    def _classify_one(
        self,
        path: str,
        size_bytes: int | None,
        largest_bytes: int,
    ) -> CandidateDecision:
        base_evidence = {
            "policy_version": CANDIDATE_POLICY_VERSION,
            "size_bytes": size_bytes,
            "largest_sibling_bytes": largest_bytes,
        }
        if not self.enabled:
            return CandidateDecision(ACCEPT, "媒体候选过滤已关闭", base_evidence)

        filename = os.path.basename(path)
        normalized = filename.casefold()
        extra_pattern = next(
            (
                pattern for pattern in self.extra_name_patterns
                if fnmatch.fnmatch(normalized, pattern.casefold())
            ),
            "",
        )
        built_in_promotion = bool(
            _PROMOTION_ACTION_RE.search(filename) and _PROMOTION_DOMAIN_RE.search(filename)
        )
        if built_in_promotion or extra_pattern:
            evidence = dict(base_evidence)
            evidence.update({
                "matched_builtin_promotion": built_in_promotion,
                "matched_extra_pattern": extra_pattern,
            })
            return CandidateDecision(
                IGNORE_PROMOTION,
                "文件名具有明确推广特征",
                evidence,
            )

        if size_bytes is None:
            return CandidateDecision(ACCEPT, "无法读取文件大小，保守保留", base_evidence)

        megabyte = 1024 * 1024
        ratio = size_bytes / largest_bytes if largest_bytes > 0 else 1.0
        evidence = dict(base_evidence)
        evidence["size_ratio"] = ratio
        is_small_companion = (
            self.small_video_max_mb > 0
            and size_bytes < self.small_video_max_mb * megabyte
            and largest_bytes >= self.main_video_min_mb * megabyte
            and ratio <= self.max_size_ratio
            and size_bytes < largest_bytes
        )
        if is_small_companion:
            return CandidateDecision(
                IGNORE_SMALL_COMPANION,
                "同一来源单元内存在明显更大的主视频，此文件为小体积附带视频",
                evidence,
            )
        return CandidateDecision(ACCEPT, "保留为媒体候选", evidence)

    @staticmethod
    def _unit_key(source_root: str, path: str) -> str:
        root = os.path.realpath(os.path.abspath(source_root))
        candidate = os.path.realpath(os.path.abspath(path))
        try:
            relative = os.path.relpath(candidate, root)
        except ValueError:
            return candidate
        if relative == os.pardir or relative.startswith(os.pardir + os.sep):
            return candidate
        parts = relative.split(os.sep)
        # 根目录直属文件共享 loose_root 单元；子目录中的文件按首层下载目录分组。
        return "." if len(parts) == 1 else parts[0]


def _non_negative_number(value, default: float) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return default
    return result if result >= 0 else default


def _ratio(value, default: float) -> float:
    result = _non_negative_number(value, default)
    return result if result <= 1 else default
