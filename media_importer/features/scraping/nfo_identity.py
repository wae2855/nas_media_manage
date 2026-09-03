"""Read deterministic media identity from bounded, adjacent NFO files."""

from __future__ import annotations

import os
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass

MAX_NFO_BYTES = 1024 * 1024
MAX_ANCESTOR_DEPTH = 6
_IMDB_ID = re.compile(r"tt\d{5,12}", re.IGNORECASE)
_NUMERIC_ID = re.compile(r"\d{1,12}")


@dataclass(frozen=True)
class NfoIdentity:
    path: str
    tmdb_id: str = ""
    imdb_id: str = ""
    tvdb_id: str = ""
    title: str = ""
    year: int | None = None
    media_type_hint: str = ""

    @property
    def provider_ids(self) -> tuple[tuple[str, str], ...]:
        return tuple(
            (kind, value)
            for kind, value in (
                ("tmdb", self.tmdb_id),
                ("imdb", self.imdb_id),
                ("tvdb", self.tvdb_id),
            )
            if value
        )


def _within_root(path: str, root: str) -> bool:
    if not root:
        return True
    try:
        resolved_root = os.path.realpath(root)
        return os.path.commonpath((os.path.realpath(path), resolved_root)) == resolved_root
    except (OSError, ValueError):
        return False


def _candidate_paths(video_path: str, source_dir: str) -> list[str]:
    video_path = os.path.abspath(video_path)
    directory = os.path.dirname(video_path)
    stem = os.path.splitext(os.path.basename(video_path))[0]
    candidates: list[str] = []

    def add(path: str) -> None:
        if path not in candidates and _within_root(path, source_dir):
            candidates.append(path)

    add(os.path.join(directory, f"{stem}.nfo"))
    add(os.path.join(directory, "movie.nfo"))
    add(os.path.join(directory, "tvshow.nfo"))

    current = directory
    for _ in range(MAX_ANCESTOR_DEPTH if source_dir else 0):
        if source_dir and os.path.realpath(current) == os.path.realpath(source_dir):
            break
        name = os.path.basename(current)
        if name:
            add(os.path.join(current, f"{name}.nfo"))
            add(os.path.join(current, "movie.nfo"))
            add(os.path.join(current, "tvshow.nfo"))
        parent = os.path.dirname(current)
        if parent == current:
            break
        current = parent
    return candidates


def _text(element: ET.Element | None) -> str:
    return str(element.text or "").strip() if element is not None else ""


def _valid_id(kind: str, value: str) -> str:
    value = str(value or "").strip()
    if kind == "imdb":
        match = _IMDB_ID.fullmatch(value)
        return match.group(0).lower() if match else ""
    return value if _NUMERIC_ID.fullmatch(value) else ""


def parse_nfo_identity(path: str) -> NfoIdentity | None:
    try:
        if not os.path.isfile(path) or os.path.islink(path):
            return None
        if os.path.getsize(path) > MAX_NFO_BYTES:
            return None
        root = ET.parse(path).getroot()
    except (OSError, ET.ParseError):
        return None

    ids = {"tmdb": "", "imdb": "", "tvdb": ""}
    for element in root.findall(".//uniqueid"):
        kind = str(element.attrib.get("type") or "").strip().casefold()
        if kind in ids and not ids[kind]:
            ids[kind] = _valid_id(kind, _text(element))
    legacy_tags = {
        "tmdb": ("tmdbid", "tmdb_id"),
        "imdb": ("imdbid", "imdb_id"),
        "tvdb": ("tvdbid", "tvdb_id"),
    }
    for kind, tags in legacy_tags.items():
        if ids[kind]:
            continue
        for tag in tags:
            value = _valid_id(kind, _text(root.find(f".//{tag}")))
            if value:
                ids[kind] = value
                break

    if not any(ids.values()):
        return None
    title = _text(root.find(".//title")) or _text(root.find(".//originaltitle"))
    try:
        year = int(_text(root.find(".//year")))
    except (TypeError, ValueError):
        year = None
    root_tag = str(root.tag or "").casefold()
    media_type = "tv" if root_tag in {"tvshow", "episodedetails"} else "movie" if root_tag == "movie" else ""
    return NfoIdentity(
        path=path,
        tmdb_id=ids["tmdb"],
        imdb_id=ids["imdb"],
        tvdb_id=ids["tvdb"],
        title=title,
        year=year,
        media_type_hint=media_type,
    )


def read_adjacent_nfo_identities(video_path: str, source_dir: str = "") -> tuple[list[NfoIdentity], list[dict]]:
    identities: list[NfoIdentity] = []
    ignored: list[dict] = []
    if not video_path or not os.path.dirname(video_path):
        return identities, ignored
    for path in _candidate_paths(video_path, source_dir):
        if not os.path.exists(path):
            continue
        identity = parse_nfo_identity(path)
        if identity is None:
            ignored.append({"path": path, "reason": "NFO 无有效身份或无法安全解析"})
            continue
        identities.append(identity)
    return identities, ignored
