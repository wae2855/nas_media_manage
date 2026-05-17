#!/usr/bin/env python3
import os
import re
from typing import Dict, Optional, List


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
    result = {
        'title_cn': None,
        'title_en': None,
        'year': None,
        'season': None,
        'episode': None
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

    year_part = year_match.group(0) if year_match else ''
    season_part = season_match.group(0) if season_match else ''
    episode_part = episode_match.group(0) if episode_match else ''

    title_part = name_without_ext
    for part in [year_part, season_part, episode_part]:
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


def check_duplicate(import_path: str, scraped_info: dict, strategy: str) -> dict:
    existing_files = find_existing_file(import_path, scraped_info)

    result = {
        'is_duplicate': False,
        'existing_file': None,
        'action': strategy,
        'suggested_filename': None
    }

    if existing_files:
        result['is_duplicate'] = True
        result['existing_file'] = existing_files[0]

        if strategy == 'rename':
            ext = os.path.splitext(scraped_info.get('filename', ''))[1] or '.mkv'
            base_name = f"{scraped_info.get('title_cn', 'video')}_{scraped_info.get('year', '')}"

            counter = 1
            while True:
                suggested_name = f"{base_name}_copy{counter}{ext}"
                suggested_path = os.path.join(import_path, suggested_name)
                if not os.path.exists(suggested_path):
                    result['suggested_filename'] = suggested_path
                    break
                counter += 1

    return result
