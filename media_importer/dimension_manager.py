#!/usr/bin/env python3
import json
import logging

logger = logging.getLogger(__name__)


def check_tier_access(required_tier: str) -> bool:
    return True


def get_dimensions_for_scrape(conn) -> list:
    from media_importer.db import get_enabled_dimensions
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
    from media_importer.db import get_enabled_dimensions
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
    from media_importer.db import get_enabled_dimensions
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


def map_tmdb_to_dimension(dim_config: dict, tmdb_data: dict) -> dict:
    name = dim_config['name']
    tmdb_field = dim_config.get('tmdb_field', '')
    value_list = dim_config.get('value_list', [])

    if tmdb_field == 'origin_country':
        return _map_region(name, value_list, tmdb_data)

    if tmdb_field == 'original_language':
        return _map_origin_lang(name, value_list, tmdb_data)

    if tmdb_field == 'genres':
        return _map_broad_genre(name, value_list, tmdb_data)

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
