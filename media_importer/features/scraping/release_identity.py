"""影视发布名结构化解析。

解析器只把强边界后的技术字段视为噪声；边界前的未知词继续作为标题候选，
避免把片名中的 4K、Korean、Extended 等字样误删。
"""

from __future__ import annotations

import datetime
import os
import re
from dataclasses import dataclass

from guessit import guessit

_VIDEO_EXTENSIONS = re.compile(
    r"\.(?:mkv|mp4|avi|wmv|flv|mov|m2ts|ts|m4v|rmvb|rm)$",
    re.IGNORECASE,
)
_YEAR = re.compile(r"(?<![A-Za-z0-9])(19\d{2}|20\d{2})(?![A-Za-z0-9])")
_SEASON_EPISODE = re.compile(
    r"(?<![A-Za-z0-9])S(\d{1,2})[ ._-]*E(\d{1,3})(?:[ ._-]*E\d{1,3})?",
    re.IGNORECASE,
)
_ONE_X_EPISODE = re.compile(r"(?<!\d)(\d{1,2})x(\d{1,3})(?!\d)", re.IGNORECASE)
_CN_NUMBER = r"[零〇一二两三四五六七八九十百\d]+"
_CN_SEASON_EPISODE = re.compile(rf"第\s*({_CN_NUMBER})\s*季\s*第\s*({_CN_NUMBER})\s*集")
_CN_SEASON = re.compile(rf"第\s*({_CN_NUMBER})\s*季")
_CN_EPISODE = re.compile(rf"第\s*({_CN_NUMBER})\s*集")
_EPISODE = re.compile(r"(?<![A-Za-z0-9])(?:EP?|Episode)[ ._-]*(\d{1,3})(?!\d)", re.I)
_ANIME_EPISODE = re.compile(r"\s-\s(\d{1,3})(?=\s*(?:\[|$))")
_TRAILING_GROUP = re.compile(
    r"(?<=\w)\s*-\s*([A-Za-z][A-Za-z0-9@&]{2,31})\s*$"
)
_LEADING_BRACKET = re.compile(r"^\s*\[([^\]]+)]\s*")
_BRACKET = re.compile(r"\[([^\]]+)]")
_ANY_BRACKET = re.compile(r"\(([^()]*)\)|（([^（）]*)）|\[([^\[\]]*)]|【([^【】]*)】")

_EDITION_PHRASES = (
    "导演剪辑版", "导演剪辑", "加长版", "未删减版", "未删减", "修复版",
    "剧场版", "特别版", "终极版", "收藏版", "完整版", "重制版",
    "director's cut", "directors cut", "extended edition", "extended",
    "uncut", "uncensored", "remastered", "theatrical", "special edition",
    "collector's edition", "ultimate edition", "festival cut", "open matte",
)
_SUBTITLE_PHRASES = (
    "中英特效字幕", "简繁英字幕", "简繁中字", "简繁字幕", "双语特效字幕",
    "中英字幕", "中文字幕", "特效字幕", "内嵌字幕", "内封字幕", "外挂字幕",
    "简英", "繁英", "简繁", "中字", "英字", "双语字幕",
)
_LANGUAGE_PHRASES = (
    "国粤双语", "国英双语", "国语", "粤语", "台配", "日语", "韩语",
    "英语", "法语", "德语", "多国语言",
)

_RESOLUTION = re.compile(
    r"^(?:(?:BD|HD)-?)?(?:4320P|2160P|1440P|1080[PI]|720P|576P|480P)$|^(?:4K|8K|UHD|FHD)$",
    re.IGNORECASE,
)
_SOURCE = re.compile(
    r"^(?:BLU-?RAY|BD(?:RIP)?|BRRIP|WEB(?:-?DL|RIP)?|HDTV|HDRIP|REMUX|"
    r"DVD(?:RIP|SCR)?|HDTC|HDTS|CAM|TS|NF|NETFLIX|AMZN|DSNP|HMAX|ATVP)$",
    re.IGNORECASE,
)
_CODEC = re.compile(
    r"^(?:X26[45]|H[ .]?26[45]|HEVC|AVC|AV1|XVID|DIVX|10BIT|12BIT|"
    r"HDR10\+?|HDR|DV|DOLBYVISION|AAC|AC3|EAC3|DDP?\d*(?:\.\d+)?|"
    r"DTS(?:-HD)?|DTSX|TRUEHD|ATMOS|FLAC|MA\d*(?:\.\d+)?|\d+CH)$",
    re.IGNORECASE,
)
_REVISION = re.compile(
    r"^(?:PROPER|REPACK|RERIP|INTERNAL|RETAIL|COMPLETE|MULTI|DUAL|SUBBED|DUBBED)$",
    re.IGNORECASE,
)
_LANGUAGE_TOKEN = re.compile(
    r"^(?:KOREAN|JAPANESE|CHINESE|MANDARIN|CANTONESE|ENGLISH|FRENCH|GERMAN|"
    r"MULTI|CHS|CHT|CHI|ENG|JPN|KOR|ZH(?:-CN|-TW)?|JA|KO)$",
    re.IGNORECASE,
)
_CHECKSUM = re.compile(r"^(?:[A-F0-9]{8}|[A-F0-9]{32,64})$", re.IGNORECASE)
_AD_TOKEN = re.compile(
    r"^(?:https?://|www\.)[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.(?:com|net|org|cn|tv|me|cc)$",
    re.IGNORECASE,
)
_AD_DOMAIN = re.compile(
    r"(?:https?://|www\.)[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.(?:com|net|org|cn|tv|me|cc)",
    re.IGNORECASE,
)
_FULL_WIDTH_AD_BLOCK = re.compile(
    r"^\s*【[^】]*(?:www\.|\.(?:com|net|org|cn|tv|me|cc)|发布|影视之家)[^】]*】\s*",
    re.IGNORECASE,
)
_PROVIDER_ID_TAG = re.compile(
    r"^(?:tmdb(?:id)?|imdb(?:id)?|tvdb(?:id)?)[ .:_-]*(?:tt)?\d+$",
    re.IGNORECASE,
)
_LEADING_AD_PHRASE = re.compile(
    r"^\s*(?:电影天堂|高清影视之家(?:发布)?|阳光电影|飘花电影|人人影视(?:字幕组)?)\s*",
    re.IGNORECASE,
)
_BOUNDARY_MARKER = "NMMSTRONGBOUNDARY"


@dataclass(frozen=True)
class ReleaseIdentity:
    title_candidates: tuple[str, ...]
    year: int | None = None
    season: int | None = None
    episode: int | None = None
    episodes: tuple[int, ...] = ()
    media_type_hint: str = ""
    editions: tuple[str, ...] = ()
    languages: tuple[str, ...] = ()
    subtitle_tags: tuple[str, ...] = ()
    resolution: str = ""
    source: str = ""
    codecs: tuple[str, ...] = ()
    release_group: str = ""
    unknown_tags: tuple[str, ...] = ()
    evidence: tuple[str, ...] = ()
    year_suspect: bool = False
    tmdb_id: str = ""
    imdb_id: str = ""
    tvdb_id: str = ""
    release_date: str = ""
    part: int | None = None
    disc: int | None = None
    episode_title: str = ""
    alternative_title: str = ""

    @property
    def primary_title(self) -> str:
        latin = next(
            (title for title in self.title_candidates if re.search(r"[A-Za-z]", title)),
            "",
        )
        return latin or (self.title_candidates[0] if self.title_candidates else "")

    @property
    def cjk_title(self) -> str | None:
        return next(
            (title for title in self.title_candidates if re.search(r"[\u3400-\u9fff]", title)),
            None,
        )


def _prepare_for_guessit(filename: str) -> tuple[str, list[str], list[str], list[str], list[str]]:
    """Remove only locally understood Chinese noise before general parsing."""
    evidence: list[str] = []
    editions: list[str] = []
    languages: list[str] = []
    subtitles: list[str] = []
    result = _strip_advertising(filename, evidence)

    def replace_bracket(match: re.Match[str]) -> str:
        value = next((group for group in match.groups() if group is not None), "").strip()
        if _PROVIDER_ID_TAG.fullmatch(value):
            evidence.append(f"身份编号={value}")
            # GuessIt must see the tag so it can emit tmdb_id/imdb_id/tvdb_id.
            # The legacy supplement independently classifies it as technical.
            return match.group(0)
        if value and _bracket_is_technical(value):
            evidence.append(f"技术括号={value}")
            if "字幕" in value:
                subtitles.append(value)
            for phrase in _SUBTITLE_PHRASES:
                if phrase.casefold() in value.casefold():
                    subtitles.append(phrase)
            for phrase in _LANGUAGE_PHRASES:
                if phrase.casefold() in value.casefold():
                    languages.append(phrase)
            for phrase in _EDITION_PHRASES:
                if phrase.casefold() in value.casefold():
                    editions.append(phrase)
            return " "
        return match.group(0)

    result = _ANY_BRACKET.sub(replace_bracket, result)
    for phrase in sorted(_EDITION_PHRASES, key=len, reverse=True):
        if re.search(r"[\u3400-\u9fff]", phrase) and re.search(re.escape(phrase), result, re.I):
            result = re.sub(re.escape(phrase), " ", result, flags=re.I)
            editions.append(phrase)
            evidence.append(f"版本={phrase}")
    for phrase in sorted(_SUBTITLE_PHRASES, key=len, reverse=True):
        if re.search(re.escape(phrase), result, re.I):
            result = re.sub(re.escape(phrase), " ", result, flags=re.I)
            subtitles.append(phrase)
            evidence.append(f"字幕={phrase}")
    for phrase in sorted(_LANGUAGE_PHRASES, key=len, reverse=True):
        if re.search(re.escape(phrase), result, re.I):
            result = re.sub(re.escape(phrase), " ", result, flags=re.I)
            languages.append(phrase)
            evidence.append(f"语言={phrase}")
    result = re.sub(r"\(\s*\)|（\s*）|\[\s*]|【\s*】", " ", result)
    result = re.sub(r"\.{2,}", ".", result)
    result = re.sub(r"\s{2,}", " ", result).lstrip(" ._-—")
    return result, evidence, editions, languages, subtitles


def _guessit_title_candidates(guessed: dict) -> tuple[str, ...]:
    values: list[str] = []
    for key in ("title", "alternative_title"):
        for value in _string_values(guessed.get(key)):
            values.extend(_split_title_candidates(value))
    return tuple(_dedupe(values))


def _merge_title_candidates(*groups: tuple[str, ...]) -> tuple[str, ...]:
    values = _dedupe([
        value.strip(" ._-[]{}()")
        for group in groups
        for value in group
        if value and value.strip(" ._-[]{}()")
    ])
    # Prefer the most informative candidate in each writing system.  Shorter
    # parser fallbacks remain available for manual search but do not become the
    # primary title (for example GuessIt's "The" vs legacy "The 4K Movie").
    values.sort(key=lambda value: (
        0 if re.search(r"[\u3400-\u9fff]", value) else 1,
        -len(value),
    ))
    return tuple(values)


def _string_values(value) -> list[str]:
    if value is None:
        return []
    if isinstance(value, (list, tuple, set)):
        return [str(item) for item in value if str(item)]
    return [str(value)] if str(value) else []


def _as_int(value) -> int | None:
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _first_int(value) -> int | None:
    if isinstance(value, (list, tuple)):
        value = value[0] if value else None
    return _as_int(value)


def _provider_id(guessed: dict, key: str) -> str:
    value = guessed.get(key)
    if isinstance(value, (list, tuple)):
        value = value[0] if value else ""
    return str(value or "").strip()


def _normalize_screen_size(value) -> str:
    return str(value or "").upper().replace(" ", "")


def _guessit_evidence(guessed: dict, episodes: tuple[int, ...]) -> list[str]:
    evidence = ["通用发布名解析=GuessIt"]
    labels = {
        "year": "年份",
        "season": "季",
        "screen_size": "resolution",
        "source": "source",
        "video_codec": "codec",
        "audio_codec": "codec",
        "release_group": "发布组",
    }
    for key, label in labels.items():
        for value in _string_values(guessed.get(key)):
            evidence.append(f"{label}={value}")
    if episodes:
        if len(episodes) == 1:
            evidence.append(f"集=E{episodes[0]:02d}")
        else:
            evidence.append(f"集范围=E{episodes[0]:02d}-E{episodes[-1]:02d}")
    return evidence


def _parse_number(value: str) -> int:
    if str(value).isdigit():
        return int(value)
    digits = {"零": 0, "〇": 0, "一": 1, "二": 2, "两": 2, "三": 3, "四": 4,
              "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}
    text = str(value)
    if "百" in text:
        left, right = text.split("百", 1)
        return digits.get(left, 1) * 100 + (_parse_number(right) if right else 0)
    if "十" in text:
        left, right = text.split("十", 1)
        return digits.get(left, 1) * 10 + (digits.get(right, 0) if right else 0)
    result = 0
    for char in text:
        result = result * 10 + digits[char]
    return result


def parse_release_identity(filename: str) -> ReleaseIdentity:
    """Parse a release name through a mature grammar with a Chinese compatibility layer.

    GuessIt extracts general Scene/PT structure.  The existing parser remains a
    conservative supplement for Chinese-only and deliberately ambiguous titles;
    neither parser is allowed to decide the Provider identity on its own.
    """
    prepared, pre_evidence, pre_editions, pre_languages, pre_subtitles = _prepare_for_guessit(filename)
    guessed = dict(guessit(prepared))
    legacy = _parse_legacy_release_identity(prepared)

    guessed_candidates = _guessit_title_candidates(guessed)
    if legacy.episode is not None and str(guessed.get("type") or "") != "episode":
        guessed_candidates = tuple(
            candidate for candidate in guessed_candidates
            if not any(
                candidate == f"{legacy_title}{legacy.episode:02d}"
                or candidate == f"{legacy_title}{legacy.episode}"
                for legacy_title in legacy.title_candidates
            )
        )
    title_candidates = _merge_title_candidates(guessed_candidates, legacy.title_candidates)

    guessed_episodes = guessed.get("episode")
    if isinstance(guessed_episodes, list):
        episodes = tuple(int(value) for value in guessed_episodes)
    elif guessed_episodes is not None:
        episodes = (int(guessed_episodes),)
    elif legacy.episodes:
        episodes = legacy.episodes
    elif legacy.episode is not None:
        episodes = (legacy.episode,)
    else:
        episodes = ()

    guessed_year = _as_int(guessed.get("year"))
    guessed_season = _first_int(guessed.get("season"))
    guessed_episode = episodes[0] if episodes else None
    evidence = list(pre_evidence)
    evidence.extend(legacy.evidence)
    evidence.extend(_guessit_evidence(guessed, episodes))

    resolution = legacy.resolution or _normalize_screen_size(guessed.get("screen_size"))
    source = legacy.source or str(guessed.get("source") or "")
    codecs = list(legacy.codecs)
    for key in ("video_codec", "audio_codec"):
        codecs.extend(_string_values(guessed.get(key)))
    languages = [*pre_languages, *legacy.languages]
    languages.extend(_string_values(guessed.get("language")))
    editions = [*pre_editions, *legacy.editions]
    editions.extend(_string_values(guessed.get("edition")))
    subtitle_tags = [*pre_subtitles, *legacy.subtitle_tags]

    return ReleaseIdentity(
        title_candidates=title_candidates,
        year=guessed_year if guessed_year is not None else legacy.year,
        season=guessed_season if guessed_season is not None else legacy.season,
        episode=guessed_episode if guessed_episode is not None else legacy.episode,
        episodes=episodes,
        media_type_hint=(
            "tv" if str(guessed.get("type") or "") == "episode"
            or guessed_season is not None or guessed_episode is not None
            else legacy.media_type_hint
        ),
        editions=tuple(_dedupe(editions)),
        languages=tuple(_dedupe(languages)),
        subtitle_tags=tuple(_dedupe(subtitle_tags)),
        resolution=resolution,
        source=source,
        codecs=tuple(_dedupe(codecs)),
        release_group=str(guessed.get("release_group") or legacy.release_group or ""),
        unknown_tags=legacy.unknown_tags,
        evidence=tuple(_dedupe(evidence)),
        year_suspect=legacy.year_suspect or (
            guessed_year is not None and legacy.year is not None and guessed_year != legacy.year
        ),
        tmdb_id=_provider_id(guessed, "tmdb_id"),
        imdb_id=_provider_id(guessed, "imdb_id"),
        tvdb_id=_provider_id(guessed, "tvdb_id"),
        release_date=(
            guessed.get("date").isoformat()
            if isinstance(guessed.get("date"), datetime.date) else ""
        ),
        part=_first_int(guessed.get("part")),
        disc=_first_int(guessed.get("disc") if guessed.get("disc") is not None else guessed.get("cd")),
        episode_title=str(guessed.get("episode_title") or ""),
        alternative_title=str(guessed.get("alternative_title") or ""),
    )


def _parse_legacy_release_identity(filename: str) -> ReleaseIdentity:
    raw = _VIDEO_EXTENSIONS.sub("", os.path.basename(filename)).strip()
    working = raw
    evidence: list[str] = []
    release_group = ""

    working = _strip_advertising(working, evidence)

    leading = _LEADING_BRACKET.match(working)
    if leading:
        bracket_value = leading.group(1).strip()
        remainder = working[leading.end():]
        if _leading_bracket_is_title(bracket_value, remainder):
            evidence.append(f"括号片名={bracket_value}")
            working = f"{bracket_value} {remainder}"
        else:
            release_group = bracket_value
            evidence.append(f"发布组前缀={release_group}")
            working = remainder

    trailing = _TRAILING_GROUP.search(working)
    if trailing and not _is_technical_token(trailing.group(1)):
        release_group = release_group or trailing.group(1)
        evidence.append(f"发布组后缀={trailing.group(1)}")
        working = working[:trailing.start()]

    boundary_source = working
    season, episode, episode_spans = _extract_episode(working, evidence)

    year_matches = list(_YEAR.finditer(working))
    year, year_span, year_suspect = _select_year(year_matches)
    if year is not None:
        evidence.append(f"年份={year}")

    boundary_candidates = [span[0] for span in episode_spans]
    if year_span:
        boundary_candidates.append(year_span[0])
    boundary = min(boundary_candidates) if boundary_candidates else None

    # 用内部标记保留强边界，避免移除年份/季集/描述词后技术字段错位。
    structural_spans = list(episode_spans)
    if year_span:
        structural_spans.append(year_span)
    for start, end in sorted(structural_spans, reverse=True):
        replacement = f" {_BOUNDARY_MARKER} " if start == boundary else " "
        working = working[:start] + replacement + working[end:]

    editions, working = _remove_phrases(
        working,
        _EDITION_PHRASES,
        "版本",
        evidence,
        boundary=boundary,
        source_value=boundary_source,
    )
    subtitle_tags, working = _remove_phrases(
        working,
        _SUBTITLE_PHRASES,
        "字幕",
        evidence,
        boundary=boundary,
        source_value=boundary_source,
    )
    languages, working = _remove_phrases(
        working,
        _LANGUAGE_PHRASES,
        "语言",
        evidence,
        boundary=boundary,
        source_value=boundary_source,
    )

    bracket_values = _BRACKET.findall(working)
    for value in bracket_values:
        if _bracket_is_technical(value):
            evidence.append(f"技术括号={value}")
            working = working.replace(f"[{value}]", " ")

    normalized = re.sub(r"[._]+", " ", working)
    normalized = re.sub(r"\s+", " ", normalized).strip(" -_.,")
    tokens = normalized.split()
    title_tokens: list[str] = []
    unknown_tags: list[str] = []
    codecs: list[str] = []
    resolution = ""
    source = ""

    # 如果没有年份/季集，连续两个技术字段也可形成强边界。
    normalized_boundary = None
    if _BOUNDARY_MARKER in tokens:
        normalized_boundary = tokens.index(_BOUNDARY_MARKER)
        tokens.remove(_BOUNDARY_MARKER)
    tech_run_start = _technical_run_start(tokens)
    if normalized_boundary is None and tech_run_start is not None:
        normalized_boundary = tech_run_start

    for index, token in enumerate(tokens):
        clean_token = token.strip("()[]{}.,")
        if not clean_token:
            continue
        after_boundary = normalized_boundary is not None and index >= normalized_boundary
        category = _technical_category(clean_token)
        if after_boundary and category:
            if category == "resolution" and not resolution:
                resolution = clean_token.upper()
            elif category == "source" and not source:
                source = clean_token
            elif category == "codec":
                codecs.append(clean_token)
            elif category == "language":
                languages.append(clean_token)
            evidence.append(f"{category}={clean_token}")
            continue
        if after_boundary and (_CHECKSUM.match(clean_token) or _AD_TOKEN.match(clean_token)):
            evidence.append(f"发布标记={clean_token}")
            continue
        if after_boundary and clean_token not in ("-",):
            unknown_tags.append(clean_token)
            continue
        title_tokens.append(clean_token)

    title_text = " ".join(title_tokens).strip(" -_.,")
    title_candidates = _split_title_candidates(title_text)
    if not title_candidates and title_text:
        title_candidates = (title_text,)

    return ReleaseIdentity(
        title_candidates=title_candidates,
        year=year,
        season=season,
        episode=episode,
        episodes=(episode,) if episode is not None else (),
        media_type_hint="tv" if season is not None or episode is not None else "movie",
        editions=tuple(_dedupe(editions)),
        languages=tuple(_dedupe(languages)),
        subtitle_tags=tuple(_dedupe(subtitle_tags)),
        resolution=resolution,
        source=source,
        codecs=tuple(_dedupe(codecs)),
        release_group=release_group,
        unknown_tags=tuple(_dedupe(unknown_tags)),
        evidence=tuple(evidence),
        year_suspect=year_suspect,
    )


def _extract_episode(value: str, evidence: list[str]) -> tuple[int | None, int | None, list[tuple[int, int]]]:
    patterns = (_SEASON_EPISODE, _ONE_X_EPISODE, _CN_SEASON_EPISODE)
    for pattern in patterns:
        match = pattern.search(value)
        if match:
            season, episode = _parse_number(match.group(1)), _parse_number(match.group(2))
            evidence.append(f"季集=S{season:02d}E{episode:02d}")
            return season, episode, [match.span()]
    cn_season = _CN_SEASON.search(value)
    cn_episode = _CN_EPISODE.search(value)
    if cn_season or cn_episode:
        season = _parse_number(cn_season.group(1)) if cn_season else 1
        episode = _parse_number(cn_episode.group(1)) if cn_episode else None
        spans = [m.span() for m in (cn_season, cn_episode) if m]
        evidence.append(f"季集=S{season:02d}" + (f"E{episode:02d}" if episode else ""))
        return season, episode, spans
    episode_match = _EPISODE.search(value) or _ANIME_EPISODE.search(value)
    if episode_match:
        episode = int(episode_match.group(1))
        evidence.append(f"季集=S01E{episode:02d}")
        return 1, episode, [episode_match.span()]
    cjk_bare = re.search(r"[\u3400-\u9fff](\d{2,3})$", value)
    if cjk_bare:
        episode = int(cjk_bare.group(1))
        if episode not in (720, 1080, 2160):
            evidence.append(f"季集=S01E{episode:02d}")
            return 1, episode, [cjk_bare.span(1)]
    return None, None, []


def _strip_advertising(value: str, evidence: list[str]) -> str:
    result = value
    block = _FULL_WIDTH_AD_BLOCK.match(result)
    if block:
        evidence.append(f"广告前缀={block.group(0).strip()}")
        result = result[block.end():]
    phrase = _LEADING_AD_PHRASE.match(result)
    if phrase:
        evidence.append(f"广告前缀={phrase.group(0).strip()}")
        result = result[phrase.end():]
    domains = _AD_DOMAIN.findall(result)
    if domains:
        evidence.extend(f"广告域名={domain}" for domain in domains)
        result = _AD_DOMAIN.sub(" ", result)
    return result.lstrip(" ._-—")


def _leading_bracket_is_title(value: str, remainder: str) -> bool:
    normalized_remainder = remainder.lstrip(" ._-—")
    return bool(
        value
        and len(value) <= 12
        and _YEAR.match(normalized_remainder)
        and not _is_technical_token(value)
    )


def _select_year(matches: list[re.Match[str]]) -> tuple[int | None, tuple[int, int] | None, bool]:
    if not matches:
        return None, None, False
    current_year = datetime.datetime.now().year
    plausible = [match for match in matches if int(match.group(1)) <= current_year + 1]
    selected = plausible[-1] if plausible else matches[-1]
    return int(selected.group(1)), selected.span(), len(matches) > 1 or not plausible


def _remove_phrases(
    value: str,
    phrases: tuple[str, ...],
    label: str,
    evidence: list[str],
    *,
    boundary: int | None,
    source_value: str,
) -> tuple[list[str], str]:
    found: list[str] = []
    result = value
    for phrase in sorted(phrases, key=len, reverse=True):
        pattern = re.compile(re.escape(phrase), re.IGNORECASE)
        matches = list(pattern.finditer(result))
        source_matches = list(pattern.finditer(source_value))
        is_cjk_phrase = bool(re.search(r"[\u3400-\u9fff]", phrase))
        occurs_after_boundary = bool(
            boundary is not None
            and any(match.start() >= boundary for match in source_matches)
        )
        removable = matches if is_cjk_phrase or occurs_after_boundary else []
        if removable:
            found.append(phrase)
            evidence.append(f"{label}={phrase}")
            for match in reversed(removable):
                result = result[:match.start()] + " " + result[match.end():]
    return found, result


def _technical_run_start(tokens: list[str]) -> int | None:
    for index in range(len(tokens) - 1):
        if _is_technical_token(tokens[index]) and _is_technical_token(tokens[index + 1]):
            return index
    return None


def _technical_category(token: str) -> str:
    if _RESOLUTION.match(token):
        return "resolution"
    if _SOURCE.match(token):
        return "source"
    if _CODEC.match(token):
        return "codec"
    if _REVISION.match(token):
        return "revision"
    if _LANGUAGE_TOKEN.match(token):
        return "language"
    return ""


def _is_technical_token(token: str) -> bool:
    return bool(_technical_category(token.strip("()[]{}.,")))


def _bracket_is_technical(value: str) -> bool:
    if _PROVIDER_ID_TAG.fullmatch(str(value or "").strip()):
        return True
    normalized = re.sub(r"[._+&/|-]+", " ", value).strip()
    tokens = normalized.split()
    if any(_is_technical_token(token) for token in tokens):
        return True
    # 发布目录常把音轨和字幕合写在一个括号中，例如
    # [国粤英多音轨+简繁字幕]。这类括号整体是技术描述，不能污染片名。
    technical_phrases = (
        "字幕", "音轨", "配音", "国语", "粤语", "台配", "简繁",
        "简体", "繁体", "中字", "双语", "内封", "内嵌", "外挂",
    )
    return any(phrase in normalized for phrase in technical_phrases)


def _split_title_candidates(value: str) -> tuple[str, ...]:
    value = re.sub(r"\s+", " ", value).strip()
    if not value:
        return ()
    cjk_parts = re.findall(
        r"[\u3400-\u9fff][\u3400-\u9fff0-9\u3000-\u303f：:·\s]*",
        value,
    )
    cjk = " ".join(part.strip() for part in cjk_parts if part.strip()).strip()
    latin = re.sub(
        r"[\u3400-\u9fff][\u3400-\u9fff0-9\u3000-\u303f：:·\s]*",
        " ",
        value,
    )
    latin = re.sub(r"\s+", " ", latin).strip(" -_.,")
    candidates = []
    if cjk:
        candidates.append(cjk)
    if latin and re.search(r"[A-Za-z]", latin):
        candidates.append(latin)
    if not candidates:
        candidates.append(value)
    return tuple(_dedupe(candidates))


def _dedupe(values: list[str]) -> list[str]:
    result = []
    seen = set()
    for value in values:
        key = value.casefold()
        if value and key not in seen:
            result.append(value)
            seen.add(key)
    return result
