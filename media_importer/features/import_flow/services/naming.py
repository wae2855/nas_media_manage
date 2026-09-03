import os

from media_importer.features.import_flow.services.classification_rules import render_template


def apply_filename_template(scraped_info: dict, template: str, video_ext: str) -> str:
    filename = render_template(template, scraped_info, extra_vars={"ext": video_ext})
    filename = filename.rstrip("/")
    if "{ext}" not in template and not filename.endswith(video_ext):
        filename = filename + video_ext
    return filename


def apply_subtitle_template(
    video_basename: str,
    lang: str,
    subtitle_ext: str,
    template: str = "{video_filename}.{lang}.{ext}",
    sequence: int = 1,
) -> str:
    video_name_without_ext = os.path.splitext(video_basename)[0]
    normalized_lang = lang if lang and lang != "unknown" else "und"
    rendered = render_template(
        template,
        {
            "video_filename": video_name_without_ext,
            "video_stem": video_name_without_ext,
            "lang": normalized_lang,
            "ext": subtitle_ext.lstrip("."),
        },
    ).rstrip("/")
    if not rendered.lower().endswith(subtitle_ext.lower()):
        rendered += subtitle_ext
    if sequence > 1:
        stem, extension = os.path.splitext(rendered)
        rendered = f"{stem}.{sequence}{extension}"
    return rendered


def plan_subtitle_filenames(
    subtitle_paths: list[str],
    video_basename: str,
    template: str = "{video_filename}.{lang}.{ext}",
) -> list[dict]:
    """按源文件名稳定排序，为同语言字幕生成确定性编号。"""
    counters: dict[tuple[str, str], int] = {}
    planned_by_path = {}
    for path in sorted(subtitle_paths, key=lambda item: os.path.basename(item).casefold()):
        lang = detect_subtitle_lang(path)
        normalized_lang = lang if lang != "unknown" else "und"
        extension = os.path.splitext(path)[1].lower()
        key = (normalized_lang, extension)
        counters[key] = counters.get(key, 0) + 1
        planned_by_path[path] = {
            "source_path": path,
            "lang": normalized_lang,
            "sequence": counters[key],
            "filename": apply_subtitle_template(
                video_basename,
                normalized_lang,
                extension,
                template,
                counters[key],
            ),
        }
    return [planned_by_path[path] for path in subtitle_paths]


def detect_subtitle_lang(filename: str) -> str:
    name_lower = filename.lower()
    if ".zh." in name_lower or ".chs." in name_lower or "chinese" in name_lower:
        return "zh"
    if ".en." in name_lower or ".eng." in name_lower or "english" in name_lower:
        return "en"
    if ".ja." in name_lower or ".jpn." in name_lower or "japanese" in name_lower:
        return "ja"
    if ".ko." in name_lower or ".kor." in name_lower or "korean" in name_lower:
        return "ko"
    # 纯语言码文件名（如 Subs/eng.srt、chs.srt，字幕单独放在子目录时常见）
    stem = os.path.splitext(os.path.basename(name_lower))[0]
    if stem in ("zh", "chs", "cht", "cn", "chinese", "sc", "tc"):
        return "zh"
    if stem in ("en", "eng", "english"):
        return "en"
    if stem in ("ja", "jpn", "japanese"):
        return "ja"
    if stem in ("ko", "kor", "korean"):
        return "ko"
    return "unknown"
