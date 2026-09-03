"""Build explainable title evidence from a media file and its directory.

The file basename is always the primary signal.  A directory basename is only
admitted as optional corroboration after structural and safety gates; an
irrelevant directory must never weaken a strong filename match.
"""

from __future__ import annotations

import os
from typing import Any

from .nfo_identity import read_adjacent_nfo_identities
from .path_roles import (
    is_generic_directory,
    is_structural_directory,
    is_supplementary_directory,
    is_technical_directory,
)
from .title_normalizer import TitleNormalizer

_WEAK_FILE_TITLES = {
    "video", "movie", "film", "sample", "trailer", "preview", "feature",
    "main", "index", "playlist", "00000", "00001",
}


def _normalized_name(value: str) -> str:
    return TitleNormalizer.strict(str(value or ""))


def _titles_from_clean(clean_result) -> list[str]:
    ordered = []
    cjk_title = str(getattr(clean_result, "cjk_title", "") or "").strip()
    clean_title = str(getattr(clean_result, "clean_title", "") or "").strip()
    for title in [cjk_title, clean_title, *(getattr(clean_result, "title_candidates", []) or [])]:
        title = str(title or "").strip(" ._-[]{}()")
        key = _normalized_name(title)
        if title and key and key not in {_normalized_name(item) for item in ordered}:
            ordered.append(title)
    return ordered


def _is_weak_file_identity(clean_result) -> bool:
    titles = _titles_from_clean(clean_result)
    if not titles:
        return True
    normalized = [_normalized_name(title).replace(" ", "") for title in titles]
    return all(
        title in _WEAK_FILE_TITLES
        or title.isdigit()
        or len(title) <= 1
        for title in normalized
    )


def _same_path(left: str, right: str) -> bool:
    if not left or not right:
        return False
    try:
        return os.path.realpath(left) == os.path.realpath(right)
    except OSError:
        return os.path.abspath(left) == os.path.abspath(right)


def _within_root(path: str, root: str) -> bool:
    if not root:
        return True
    try:
        return os.path.commonpath((os.path.realpath(path), os.path.realpath(root))) == os.path.realpath(root)
    except (OSError, ValueError):
        return False


def _signal(source: str, raw_name: str, clean_result, *, depth: int = 0) -> dict[str, Any]:
    return {
        "source": source,
        "raw_name": raw_name,
        "titles": _titles_from_clean(clean_result),
        "year": getattr(clean_result, "year", None),
        "season": getattr(clean_result, "season", None),
        "episode": getattr(clean_result, "episode", None),
        "episodes": list((getattr(clean_result, "release_identity", {}) or {}).get("episodes") or []),
        "year_suspect": bool(getattr(clean_result, "year_suspect", False)),
        "depth": depth,
    }


def build_identity_evidence(
    filename: str,
    *,
    video_path: str = "",
    source_dir: str = "",
    cleaner,
    path_context: dict | None = None,
) -> dict[str, Any]:
    """Return primary file evidence plus at most one gated directory signal."""
    file_clean = cleaner.clean(filename)
    file_signal = _signal("file", os.path.basename(filename), file_clean)
    file_signal["weak"] = _is_weak_file_identity(file_clean)
    evidence: dict[str, Any] = {
        "signals": [file_signal],
        "ignored_directories": [],
        "nfo_identities": [],
        "ignored_nfo": [],
        "file_clean_result": file_clean,
    }

    release_identity = getattr(file_clean, "release_identity", {}) or {}
    evidence["provider_ids"] = [
        {"source": "filename", "id_type": id_type, "value": str(release_identity.get(key) or "")}
        for id_type, key in (("tmdb", "tmdb_id"), ("imdb", "imdb_id"), ("tvdb", "tvdb_id"))
        if release_identity.get(key)
    ]

    nfo_identities, ignored_nfo = read_adjacent_nfo_identities(video_path, source_dir)
    evidence["ignored_nfo"] = ignored_nfo
    for identity in nfo_identities:
        item = {
            "path": identity.path,
            "title": identity.title,
            "year": identity.year,
            "media_type_hint": identity.media_type_hint,
            "identity_scope": identity.identity_scope,
            "provider_ids": [
                {"id_type": id_type, "value": value}
                for id_type, value in identity.provider_ids
            ],
        }
        evidence["nfo_identities"].append(item)
        if identity.identity_scope == "episode":
            evidence["ignored_nfo"].append({
                "path": identity.path,
                "reason": "episode NFO 身份编号不能作为 series ID，保留证据并回退标题识别",
            })
        evidence["provider_ids"].extend(
            {
                "source": "nfo",
                "path": identity.path,
                "id_type": id_type,
                "value": value,
                "media_type_hint": identity.media_type_hint,
                "identity_scope": identity.identity_scope,
                "year": identity.year,
            }
            for id_type, value in identity.provider_ids
        )

    historical = (path_context or {}).get("historical_binding") or {}
    if historical.get("provider_type") and historical.get("provider_id"):
        evidence["provider_ids"].append({
            "source": "history",
            "id_type": str(historical["provider_type"]),
            "value": str(historical["provider_id"]),
            "media_type_hint": str(historical.get("media_type") or ""),
            "year": historical.get("year"),
        })

    if not video_path or not os.path.dirname(video_path):
        evidence["ignored_directories"].append({"name": "", "reason": "没有可用的父目录"})
        return evidence

    current = os.path.dirname(os.path.abspath(video_path))
    root = os.path.abspath(source_dir) if source_dir else ""
    if root and (not _within_root(current, root) or _same_path(current, root)):
        reason = "视频直接位于来源根目录" if _same_path(current, root) else "父目录不在来源根内"
        evidence["ignored_directories"].append({"name": os.path.basename(current), "reason": reason})
        return evidence

    chosen_name = ""
    chosen_depth = 0
    for depth in range(0, 6):
        if root and _same_path(current, root):
            break
        name = os.path.basename(current)
        if not name:
            break
        if is_supplementary_directory(name):
            evidence["ignored_directories"].append({
                "name": name,
                "reason": "附加内容目录是作品身份继承边界",
            })
            break
        if is_structural_directory(name):
            evidence["ignored_directories"].append({"name": name, "reason": "结构目录不作为片名"})
            current = os.path.dirname(current)
            continue
        if is_generic_directory(name):
            evidence["ignored_directories"].append({"name": name, "reason": "通用目录名不作为片名"})
            current = os.path.dirname(current)
            continue
        if is_technical_directory(name):
            evidence["ignored_directories"].append({"name": name, "reason": "技术规格目录不作为片名"})
            current = os.path.dirname(current)
            continue
        clean_result = cleaner.clean(name)
        titles = _titles_from_clean(clean_result)
        if not titles or all(is_generic_directory(title) for title in titles):
            evidence["ignored_directories"].append({"name": name, "reason": "未提取到可信片名"})
            current = os.path.dirname(current)
            continue
        chosen_name = name
        chosen_depth = depth
        chosen_clean = clean_result
        break

    if not chosen_name:
        return evidence
    context = path_context or {}
    siblings = context.get("sibling_files") or []
    is_episode = file_signal.get("season") is not None or file_signal.get("episode") is not None
    if siblings and not is_episode and chosen_depth == 0:
        evidence["ignored_directories"].append({
            "name": chosen_name,
            "reason": "目录内存在多个视频，避免把容器名套用到每部影片",
        })
        return evidence

    folder_signal = _signal("folder", chosen_name, chosen_clean, depth=chosen_depth)
    if folder_signal["season"] is None:
        folder_signal["season"] = file_signal.get("season")
    folder_episodes = folder_signal.get("episodes") or []
    file_episode = file_signal.get("episode")
    if file_episode is not None and len(folder_episodes) > 1:
        # A range-bearing folder describes the source unit, not the concrete
        # episode.  The individual file remains the authoritative episode.
        folder_signal["episode"] = file_episode
    elif folder_signal["episode"] is None:
        folder_signal["episode"] = file_signal.get("episode")
    evidence["signals"].append(folder_signal)
    return evidence


def evidence_to_dict(evidence: dict[str, Any]) -> dict[str, Any]:
    """Drop internal CleanResult objects before serializing a task trace."""
    result = {
        "signals": [dict(signal) for signal in evidence.get("signals", [])],
        "ignored_directories": [dict(item) for item in evidence.get("ignored_directories", [])],
        "provider_ids": [dict(item) for item in evidence.get("provider_ids", [])],
        "nfo_identities": [dict(item) for item in evidence.get("nfo_identities", [])],
        "ignored_nfo": [dict(item) for item in evidence.get("ignored_nfo", [])],
    }
    if evidence.get("identity_resolution"):
        result["identity_resolution"] = dict(evidence["identity_resolution"])
    return result
