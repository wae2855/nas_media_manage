#!/usr/bin/env python3
import os
import re
from typing import Dict, Optional, List


RESOLUTION_PRIORITY = {
    '4320p': 6,
    '2160p': 5,
    '1440p': 4,
    '1080p': 3,
    '720p': 2,
    '480p': 1,
    '360p': 0
}


def normalize_title(title: str) -> str:
    if not title:
        return ''
    title = title.lower()
    title = re.sub(r'[.\-_，。、\s]', '', title)
    return title


def is_title_match(title_a: str, title_b: str) -> bool:
    norm_a = normalize_title(title_a)
    norm_b = normalize_title(title_b)
    return norm_a == norm_b and norm_a != ''


def parse_filename_info(filename: str) -> Dict[str, Optional[str]]:
    name_without_ext = os.path.splitext(filename)[0]
    result: Dict[str, Optional[str]] = {
        'title_cn': None,
        'title_en': None,
        'year': None,
        'season': None,
        'episode': None,
        'resolution': None,
        'quality': None
    }

    year_match = re.search(r'[(（]?(\d{4})[)）]?', name_without_ext)
    if year_match:
        result['year'] = year_match.group(1)

    season_match = re.search(r'[Ss](\d{1,2})', name_without_ext)
    if season_match:
        result['season'] = season_match.group(1)

    episode_match = re.search(r'[Ee](\d{1,2})', name_without_ext)
    if episode_match:
        result['episode'] = episode_match.group(1)

    res_match = re.search(r'(\d{3,4}p)', name_without_ext, re.IGNORECASE)
    if res_match:
        result['resolution'] = res_match.group(1).lower()

    quality_patterns = ['BluRay', 'WEB-DL', 'WEB', 'HDTV', 'DVDRip', 'BDRip']
    for quality in quality_patterns:
        if quality.lower() in name_without_ext.lower():
            result['quality'] = quality
            break

    year_part = year_match.group(0) if year_match else ''
    season_part = season_match.group(0) if season_match else ''
    episode_part = episode_match.group(0) if episode_match else ''
    res_part = res_match.group(0) if res_match else ''

    title_part = name_without_ext
    for part in [year_part, season_part, episode_part, res_part]:
        title_part = title_part.replace(part, '')

    title_candidates = re.split(r'[.\-_，。、\s]', title_part.strip())
    title_candidates = [t for t in title_candidates if t]

    if title_candidates:
        has_chinese = any(re.search(r'[\u4e00-\u9fff]', t) for t in title_candidates)
        if has_chinese:
            cn_parts = [t for t in title_candidates if re.search(r'[\u4e00-\u9fff]', t)]
            en_parts = [t for t in title_candidates if not re.search(r'[\u4e00-\u9fff]', t)]
            result['title_cn'] = ''.join(cn_parts) if cn_parts else None
            result['title_en'] = ' '.join(en_parts) if en_parts else None
        else:
            result['title_en'] = ' '.join(title_candidates)

    return result


VIDEO_EXTENSIONS = {'.mkv', '.mp4', '.avi', '.ts', '.mov', '.wmv', '.m2ts', '.flv'}


def find_existing_file(search_dir: str, scraped_info: dict) -> List[str]:
    if not os.path.exists(search_dir):
        return []

    target_info = {
        'title_cn': scraped_info.get('title_cn'),
        'title_en': scraped_info.get('title_en'),
        'year': str(scraped_info.get('year')) if scraped_info.get('year') else None,
        'season': str(scraped_info.get('season')) if scraped_info.get('season') else None,
        'episode': str(scraped_info.get('episode')) if scraped_info.get('episode') else None
    }

    matching_files = []

    for root, dirs, files in os.walk(search_dir):
        for filename in files:
            ext = os.path.splitext(filename)[1].lower()
            if ext not in VIDEO_EXTENSIONS:
                continue
            file_info = parse_filename_info(filename)

            year_match = target_info['year'] and file_info['year'] and target_info['year'] == file_info['year']

            title_match = False
            if target_info['title_cn'] and file_info['title_cn']:
                title_match = title_match or is_title_match(target_info['title_cn'], file_info['title_cn'])
            if target_info['title_en'] and file_info['title_en']:
                title_match = title_match or is_title_match(target_info['title_en'], file_info['title_en'])

            season_match = True
            if target_info['season'] and target_info['season'] is not None:
                season_match = file_info['season'] and str(int(target_info['season'])) == str(int(file_info['season']))

            episode_match = True
            if target_info['episode'] and target_info['episode'] is not None:
                episode_match = file_info['episode'] and str(int(target_info['episode'])) == str(int(file_info['episode']))

            if year_match and title_match and season_match and episode_match:
                matching_files.append(os.path.join(root, filename))

    return matching_files


def get_resolution_score(resolution: Optional[str]) -> int:
    """获取分辨率优先级分数"""
    if not resolution:
        return -1
    return RESOLUTION_PRIORITY.get(resolution.lower(), -1)


def compare_quality(new_file_path: str, existing_file_path: str, new_file_info: dict) -> str:
    new_resolution = new_file_info.get('resolution')
    new_size = os.path.getsize(new_file_path) if os.path.exists(new_file_path) else 0

    existing_info = parse_filename_info(os.path.basename(existing_file_path))
    existing_resolution = existing_info.get('resolution')
    existing_size = os.path.getsize(existing_file_path) if os.path.exists(existing_file_path) else 0

    new_res_score = get_resolution_score(new_resolution)
    existing_res_score = get_resolution_score(existing_resolution)

    if new_res_score > existing_res_score:
        return 'replace'
    elif new_res_score < existing_res_score:
        return 'keep_existing'
    else:
        if new_size > existing_size:
            return 'replace'
        else:
            return 'keep_existing'


def check_duplicate(import_path: str, scraped_info: dict, strategy: str, new_file_path: Optional[str] = None) -> dict:
    existing_files = find_existing_file(import_path, scraped_info)

    result = {
        'is_duplicate': False,
        'existing_file': None,
        'existing_path': None,
        'skip_message': None,
        'action': strategy,
        'suggested_filename': None,
        'quality_decision': None,
        'quality_reason': None
    }

    if existing_files:
        result['is_duplicate'] = True
        result['existing_file'] = os.path.basename(existing_files[0])
        result['existing_path'] = existing_files[0]
        
        title_info = []
        if scraped_info.get('title_cn'):
            title_info.append(scraped_info['title_cn'])
        if scraped_info.get('title_en'):
            title_info.append(scraped_info['title_en'])
        title = ' / '.join(title_info) if title_info else '视频'
        
        media_type = scraped_info.get('media_type', 'video')
        if media_type == 'tv' and scraped_info.get('season') and scraped_info.get('episode'):
            title += f" S{scraped_info['season']:02d}E{scraped_info['episode']:02d}"
        elif scraped_info.get('year'):
            title += f" ({scraped_info['year']})"

        if strategy == 'skip':
            result['skip_message'] = f"同名文件已存在: {result['existing_file']} (路径: {result['existing_path']})"

        elif strategy == 'replace':
            result['skip_message'] = f"替换已存在文件: {result['existing_file']} (路径: {result['existing_path']})"

        elif strategy == 'rename':
            ext = os.path.splitext(scraped_info.get('video_file', ''))[1] or '.mkv'
            base_name = f"{scraped_info.get('title_cn', 'video')}_{scraped_info.get('year', '')}"

            counter = 1
            while True:
                suggested_name = f"{base_name}_copy{counter}{ext}"
                suggested_path = os.path.join(import_path, suggested_name)
                if not os.path.exists(suggested_path):
                    result['suggested_filename'] = suggested_path
                    break
                counter += 1
            result['skip_message'] = f"同名文件已存在，将重命名为: {os.path.basename(result['suggested_filename'])}"

        elif strategy == 'quality':
            if new_file_path and os.path.exists(new_file_path):
                quality_decision = compare_quality(new_file_path, existing_files[0], scraped_info)
                result['quality_decision'] = quality_decision

                new_res = scraped_info.get('resolution', '未知') or '未知'
                existing_res = parse_filename_info(os.path.basename(existing_files[0])).get('resolution', '未知') or '未知'
                new_size_mb = round(os.path.getsize(new_file_path) / (1024 * 1024), 1) if os.path.exists(new_file_path) else 0
                existing_size_mb = round(os.path.getsize(existing_files[0]) / (1024 * 1024), 1) if os.path.exists(existing_files[0]) else 0

                if quality_decision == 'replace':
                    result['skip_message'] = f"质量优先: 新文件更优，将替换已存在文件 (新: {new_res}/{new_size_mb}MB, 已有: {existing_res}/{existing_size_mb}MB)"
                    result['quality_reason'] = f"新文件分辨率更高或同分辨率下文件更大"
                else:
                    result['skip_message'] = f"质量优先: 保留已存在文件 (已有: {existing_res}/{existing_size_mb}MB, 新: {new_res}/{new_size_mb}MB)"
                    result['quality_reason'] = f"已存在文件质量更高或相当"
            else:
                result['quality_decision'] = 'keep_existing'
                result['skip_message'] = f"同名文件已存在: {result['existing_file']} (无法比较质量，保留已存在文件)"
                result['quality_reason'] = "源文件暂不可访问，默认保留已存在文件"

    return result
