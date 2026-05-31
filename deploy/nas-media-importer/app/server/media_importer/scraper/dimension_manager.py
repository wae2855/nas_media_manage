#!/usr/bin/env python3
import json
import logging

logger = logging.getLogger(__name__)

CERTIFICATION_TO_LEVEL = {
    'G': '0-6',
    'U': '0-6',
    'PG': '7-12',
    'TV-Y': '0-6',
    'TV-Y7': '7-12',
    'TV-G': '7-12',
    'TV-PG': '7-12',
    '12A': '13-16',
    '12': '13-16',
    'PG-13': '13-16',
    'TV-14': '13-16',
    'R': '17+',
    'NC-17': '17+',
    '15': '17+',
    '18': '17+',
    'TV-MA': '17+',
}


def check_tier_access(required_tier: str) -> bool:
    return True


def get_dimensions_for_scrape(conn) -> list:
    from media_importer.core.db import get_enabled_dimensions
    dims = get_enabled_dimensions(conn)
    result = []
    for dim in dims:
        source_type = dim.get('source_type', '')
        ai_prompt = dim.get('ai_prompt', '')
        if source_type == 'ai' or (source_type == 'ai+tmdb' and ai_prompt):
            result.append({
                'name': dim['name'],
                'label': dim['label'],
                'values': [v['value'] for v in dim.get('value_list', [])],
                'ai_prompt': ai_prompt,
                'source_type': source_type,
            })
    return result


def get_dimensions_for_tmdb(conn) -> list:
    from media_importer.core.db import get_enabled_dimensions
    dims = get_enabled_dimensions(conn)
    result = []
    for dim in dims:
        if dim.get('source_type') == 'ai+tmdb' and dim.get('tmdb_field'):
            result.append({
                'name': dim['name'],
                'label': dim['label'],
                'source_type': dim['source_type'],
                'tmdb_field': dim.get('tmdb_field', ''),
                'value_list': dim.get('value_list', []),
            })
    return result


def get_dimensions_for_file(conn) -> list:
    from media_importer.core.db import get_enabled_dimensions
    dims = get_enabled_dimensions(conn)
    result = []
    for dim in dims:
        if dim.get('source_type') == 'file':
            result.append({
                'name': dim['name'],
                'label': dim['label'],
                'value_list': dim.get('value_list', []),
            })
    return result


def map_tmdb_to_dimension(dim_config: dict, tmdb_data: dict, release_dates: list = None) -> dict:
    name = dim_config['name']
    tmdb_field = dim_config.get('tmdb_field', '')
    value_list = dim_config.get('value_list', [])

    if tmdb_field == 'origin_country':
        return _map_region(name, value_list, tmdb_data)

    if tmdb_field == 'original_language':
        return _map_origin_lang(name, value_list, tmdb_data)

    if tmdb_field == 'genres':
        if name == 'documentary':
            return _map_documentary(name, value_list, tmdb_data)
        elif name == 'animation':
            return _map_animation(name, value_list, tmdb_data)
        else:
            return _map_broad_genre(name, value_list, tmdb_data)

    if tmdb_field == 'release_dates':
        return _map_restricted_level(name, value_list, release_dates or [])

    return {'name': name, 'value': None, 'confidence': 0}


def _map_region(name: str, value_list: list, tmdb_data: dict) -> dict:
    origin_countries = tmdb_data.get('origin_country', [])
    if not origin_countries:
        return {'name': name, 'value': None, 'confidence': 0}

    first_country = origin_countries[0] if isinstance(origin_countries, list) else origin_countries

    for vl in value_list:
        tmdb_codes = vl.get('tmdb_codes', [])
        if first_country in tmdb_codes:
            return {'name': name, 'value': vl['value'], 'confidence': 1.0}

    for vl in value_list:
        if vl.get('value') == 'other':
            return {'name': name, 'value': 'other', 'confidence': 1.0}

    return {'name': name, 'value': None, 'confidence': 0}


def _map_origin_lang(name: str, value_list: list, tmdb_data: dict) -> dict:
    original_language = tmdb_data.get('original_language', '')
    if not original_language:
        return {'name': name, 'value': None, 'confidence': 0}

    for vl in value_list:
        if vl.get('value') == original_language:
            return {'name': name, 'value': original_language, 'confidence': 1.0}

    for vl in value_list:
        if vl.get('value') == 'other':
            return {'name': name, 'value': 'other', 'confidence': 1.0}

    return {'name': name, 'value': 'other', 'confidence': 1.0}


def _map_broad_genre(name: str, value_list: list, tmdb_data: dict) -> dict:
    genres = tmdb_data.get('genres', [])
    if not genres:
        return {'name': name, 'value': None, 'confidence': 0}

    genre_ids = []
    for g in genres:
        if isinstance(g, dict) and 'id' in g:
            genre_ids.append(g['id'])
        elif isinstance(g, int):
            genre_ids.append(g)

    if not genre_ids:
        return {'name': name, 'value': None, 'confidence': 0}

    sorted_values = sorted(value_list, key=lambda x: x.get('priority', 99))

    for vl in sorted_values:
        tmdb_genre_ids = vl.get('tmdb_genre_ids', [])
        for gid in genre_ids:
            if gid in tmdb_genre_ids:
                return {'name': name, 'value': vl['value'], 'confidence': 0.9}

    for vl in sorted_values:
        if vl.get('value') == 'other':
            return {'name': name, 'value': 'other', 'confidence': 0.9}

    return {'name': name, 'value': 'other', 'confidence': 0.9}


def _map_documentary(name: str, value_list: list, tmdb_data: dict) -> dict:
    genres = tmdb_data.get('genres', [])
    if not genres:
        return {'name': name, 'value': None, 'confidence': 0}

    genre_ids = []
    for g in genres:
        if isinstance(g, dict) and 'id' in g:
            genre_ids.append(g['id'])
        elif isinstance(g, int):
            genre_ids.append(g)

    if 99 in genre_ids:
        return {'name': name, 'value': 'true', 'confidence': 1.0}
    elif genre_ids:
        return {'name': name, 'value': 'false', 'confidence': 0.9}
    else:
        return {'name': name, 'value': None, 'confidence': 0}


def _map_animation(name: str, value_list: list, tmdb_data: dict) -> dict:
    genres = tmdb_data.get('genres', [])
    if not genres:
        return {'name': name, 'value': None, 'confidence': 0}

    genre_ids = []
    for g in genres:
        if isinstance(g, dict) and 'id' in g:
            genre_ids.append(g['id'])
        elif isinstance(g, int):
            genre_ids.append(g)

    if 16 in genre_ids:
        return {'name': name, 'value': 'true', 'confidence': 1.0}
    elif genre_ids:
        return {'name': name, 'value': 'false', 'confidence': 0.9}
    else:
        return {'name': name, 'value': None, 'confidence': 0}


def _map_restricted_level(name: str, value_list: list, release_dates: list) -> dict:
    if not release_dates:
        return {'name': name, 'value': None, 'confidence': 0}

    country_priority = ['US', 'GB', 'DE', 'FR', 'CN', 'JP', 'KR', 'AU', 'CA']

    sorted_dates = []
    for rd in release_dates:
        iso = rd.get('iso_3166_1', '')
        if iso in country_priority:
            priority = country_priority.index(iso)
        else:
            priority = len(country_priority)
        sorted_dates.append((priority, rd))

    sorted_dates.sort(key=lambda x: x[0])

    for _, result in sorted_dates:
        iso = result.get('iso_3166_1', '')
        if iso not in country_priority[:2]:
            continue

        tv_rating = result.get('rating', '').strip().upper()
        if tv_rating and tv_rating in CERTIFICATION_TO_LEVEL:
            level = CERTIFICATION_TO_LEVEL[tv_rating]
            confidence = 1.0 if iso == 'US' else 0.95
            return {'name': name, 'value': level, 'confidence': confidence}

        dates = result.get('release_dates', [])
        if not dates:
            continue

        for rd in dates:
            cert = rd.get('certification', '').strip().upper()
            if cert in CERTIFICATION_TO_LEVEL:
                level = CERTIFICATION_TO_LEVEL[cert]
                confidence = 1.0 if iso == 'US' else 0.95
                return {'name': name, 'value': level, 'confidence': confidence}

    return {'name': name, 'value': None, 'confidence': 0}
