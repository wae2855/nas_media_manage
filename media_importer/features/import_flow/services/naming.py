import os

from media_importer.features.import_flow.services.classification_rules import render_template


def apply_filename_template(scraped_info: dict, template: str, video_ext: str) -> str:
    filename = render_template(template, scraped_info, extra_vars={"ext": video_ext})
    filename = filename.rstrip("/")
    if "{ext}" not in template and not filename.endswith(video_ext):
        filename = filename + video_ext
    return filename


def apply_subtitle_template(video_basename: str, lang: str, subtitle_ext: str) -> str:
    video_name_without_ext = os.path.splitext(video_basename)[0]
    return f"{video_name_without_ext}.{lang}{subtitle_ext}"


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
