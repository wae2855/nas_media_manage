import re
from .confidence_models import (
    CleanResult,
    _RESOLUTION_PATTERNS,
    _SOURCE_CODEC_PATTERNS,
    _RELEASE_GROUP_START,
    _RELEASE_GROUP_TAIL,
    _SEASON_EPISODE,
    _SEASON_ONLY,
    _YEAR_PATTERN,
    _YEAR_PAREN,
    _AD_PATTERN,
    _AD_FULL_PATTERN,
    _EDITION_PATTERN,
    _BRACKET_CONTENT,
    _EXTENSION_PATTERN,
    _MULTI_EP,
    _CODEC_PREFIX_RE,
)


class FilenameCleaner:
    def clean(self, filename: str) -> CleanResult:
        original = filename
        name = _EXTENSION_PATTERN.sub('', filename)
        removed = []

        name = _RELEASE_GROUP_START.sub('', name)
        if name != _EXTENSION_PATTERN.sub('', filename):
            removed.append("制作组标签")

        rg_match = re.search(r'-\s*([A-Za-z0-9_.@&\u4e00-\u9fff\u3400-\u4dbf]+)$', name)
        if rg_match:
            group_name = rg_match.group(1)
            pre_dash = name[:rg_match.start()].rstrip()
            is_after_ad = bool(_AD_FULL_PATTERN.search(pre_dash)) if pre_dash else False
            if not _CODEC_PREFIX_RE.match(group_name) and not is_after_ad:
                name = name[:rg_match.start()] + name[rg_match.end():]
                removed.append(f"发布组={group_name}")

        name = _MULTI_EP.sub('', name)
        name = _SEASON_EPISODE.sub('', name)

        season = None
        episode = None
        se_match = _SEASON_EPISODE.search(_EXTENSION_PATTERN.sub('', filename))
        if se_match:
            season = int(se_match.group(1))
            episode = int(se_match.group(2))
            removed.append(f"季集=S{season:02d}E{episode:02d}")

        if season is None:
            so_match = _SEASON_ONLY.search(_EXTENSION_PATTERN.sub('', filename))
            if so_match:
                season = int(so_match.group(1))
                removed.append(f"季=S{season:02d}")
            name = _SEASON_ONLY.sub('', name)

        year = None
        yp_match = _YEAR_PAREN.search(name)
        if yp_match:
            year = int(yp_match.group(1))
            name = _YEAR_PAREN.sub('', name)
            removed.append(f"年份={year}")

        if year is None:
            year_match = _YEAR_PATTERN.search(name)
            if year_match:
                year = int(year_match.group(1))
                name = name[:year_match.start()] + name[year_match.end():]
                removed.append(f"年份={year}")

        name = _RESOLUTION_PATTERNS.sub('', name)
        name = _SOURCE_CODEC_PATTERNS.sub('', name)
        name = _EDITION_PATTERN.sub('', name)
        name = _AD_FULL_PATTERN.sub('', name)
        name = _AD_PATTERN.sub('', name)
        name = _BRACKET_CONTENT.sub('', name)

        result = _RELEASE_GROUP_TAIL.sub('', name)
        if result != name:
            removed.append("发布组标记")
            name = result

        name = re.sub(r'[.\s_-]+', ' ', name).strip()
        name = re.sub(r'^[\s._-]+|[\s._-]+$', '', name)

        cjk_title = None
        _CJK = r'\u4e00-\u9fff\u3400-\u4dbf\u3000-\u303f\uff00-\uffef'
        _CJK_COLON = r'\uff1a\uFE55\u003a'
        mixed_match = re.match(
            rf'([{_CJK}][{_CJK}{_CJK_COLON}\s：:]+?)\s+([A-Za-z][A-Za-z\s\':,&!?\-]+)$',
            name
        )
        if mixed_match:
            cjk_part = mixed_match.group(1).strip()
            eng_part = mixed_match.group(2).strip()
            if len(cjk_part) >= 2 and len(eng_part) >= 3:
                removed.append(f"中文标题={cjk_part}")
                cjk_title = cjk_part
                name = eng_part

        year_suspect = False
        if year is not None:
            import datetime
            _current_year = datetime.datetime.now().year
            if year > _current_year + 1:
                year_suspect = True
            if not year_suspect and re.search(r'(?:^|\s)(19\d{2}|20\d{2})(?:\s|$)', name):
                year_suspect = True

        return CleanResult(
            clean_title=name,
            year=year,
            season=season,
            episode=episode,
            removed_items=removed,
            method="regex",
            year_suspect=year_suspect,
            cjk_title=cjk_title,
        )

    def ai_clean(self, filename: str, llm_scraper) -> CleanResult:
        prompt = (
            "从以下视频文件名中提取影视作品的标题和上映年份。\n"
            "注意：文件名可能包含制作组名、分辨率、编码信息等干扰项，年份可能是标题的一部分而非上映年份。\n"
            "请按以下JSON格式返回，不要返回其他内容：\n"
            '{"title": "标题", "year": 年份或null}\n'
            f"文件名: {filename}"
        )
        try:
            ai_result = llm_scraper.extract_title(prompt)
            if ai_result and ai_result.strip():
                import json
                text = ai_result.strip()
                think_match = re.search(r'</think\s*>', text, re.DOTALL)
                if think_match:
                    text = text[think_match.end():].strip()
                json_match = re.search(r'\{[^}]+\}', text, re.DOTALL)
                if json_match:
                    data = json.loads(json_match.group())
                    title = data.get("title", "").strip()
                    year = data.get("year")
                    if title:
                        return CleanResult(
                            clean_title=title,
                            year=year if isinstance(year, int) else None,
                            method="ai"
                        )
                return CleanResult(clean_title=text, method="ai")
        except Exception:
            pass
        return self.clean(filename)
