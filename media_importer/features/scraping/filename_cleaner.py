import re
from media_importer.features.scraping.confidence_models import (
    CleanResult,
    _RESOLUTION_PATTERNS,
    _SOURCE_CODEC_PATTERNS,
    _RELEASE_GROUP_START,
    _RELEASE_GROUP_TAIL,
    _SEASON_EPISODE,
    _SEASON_ONLY,
    _CN_SEASON_EPISODE,
    _CN_SEASON,
    _CN_EPISODE,
    _BARE_EPISODE,
    _YEAR_PATTERN,
    _YEAR_PAREN,
    _AD_PATTERN,
    _AD_FULL_PATTERN,
    _EDITION_PATTERN,
    _BRACKET_CONTENT,
    _EXTENSION_PATTERN,
    _MULTI_EP,
    _CODEC_PREFIX_RE,
    _SUBTITLE_LANG_PATTERN,
    _CJK_DESCRIPTOR_PATTERN,
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

        if season is None:
            cn_se_match = _CN_SEASON_EPISODE.search(_EXTENSION_PATTERN.sub('', filename))
            if cn_se_match:
                season = int(cn_se_match.group(1))
                episode = int(cn_se_match.group(2))
                removed.append(f"季集=S{season:02d}E{episode:02d}")

        if season is None:
            cn_s_match = _CN_SEASON.search(_EXTENSION_PATTERN.sub('', filename))
            if cn_s_match:
                season = int(cn_s_match.group(1))
                removed.append(f"季=S{season:02d}")

        if episode is None:
            cn_e_match = _CN_EPISODE.search(_EXTENSION_PATTERN.sub('', filename))
            if cn_e_match:
                episode = int(cn_e_match.group(1))
                removed.append(f"集=E{episode:02d}")

        if season is None and episode is None:
            bare_match = _BARE_EPISODE.search(name)
            if bare_match:
                num = int(bare_match.group(1))
                if not (1900 <= num <= 2099) and num not in (720, 1080, 2160):
                    episode = num
                    season = 1
                    name = name[:bare_match.start(1)] + name[bare_match.end(1):]
                    removed.append(f"集=E{episode:02d}")

        year = None
        year_suspect = False
        yp_match = _YEAR_PAREN.search(name)
        if yp_match:
            year = int(yp_match.group(1))
            name = _YEAR_PAREN.sub('', name)
            removed.append(f"年份={year}")

        if year is None:
            all_year_matches = list(_YEAR_PATTERN.finditer(name))
            if all_year_matches:
                import datetime
                _current_year = datetime.datetime.now().year
                best_match = None
                for ym in all_year_matches:
                    y = int(ym.group(1))
                    if y <= _current_year + 1:
                        best_match = ym
                        break
                if best_match is None:
                    best_match = all_year_matches[-1]
                    year_suspect = True
                year = int(best_match.group(1))
                name = name[:best_match.start()] + name[best_match.end():]
                removed.append(f"年份={year}")
                if len(all_year_matches) > 1:
                    year_suspect = True

        name = _RESOLUTION_PATTERNS.sub('', name)
        name = _SOURCE_CODEC_PATTERNS.sub('', name)
        name = _EDITION_PATTERN.sub('', name)
        name = _SUBTITLE_LANG_PATTERN.sub('', name)
        name = _CJK_DESCRIPTOR_PATTERN.sub('', name)
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

        year_suspect_final = year_suspect
        if year is not None and not year_suspect_final:
            import datetime
            _current_year = datetime.datetime.now().year
            if year > _current_year + 1:
                year_suspect_final = True
            if not year_suspect_final and re.search(r'(?:^|\s)(19\d{2}|20\d{2})(?:\s|$)', name):
                year_suspect_final = True

        return CleanResult(
            clean_title=name,
            year=year,
            season=season,
            episode=episode,
            removed_items=removed,
            method="regex",
            year_suspect=year_suspect_final,
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
