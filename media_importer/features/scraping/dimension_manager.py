#!/usr/bin/env python3
import json
import logging
from typing import Optional

logger = logging.getLogger(__name__)

CERTIFICATION_TO_LEVEL = {
    # 美国（MPAA/TV）
    'G': '0-6', 'TV-Y': '0-6',
    'PG': '7-12', 'TV-Y7': '7-12', 'TV-G': '7-12', 'TV-PG': '7-12',
    'PG-13': '13-16', 'TV-14': '13-16',
    'R': '17+', 'NC-17': '17+', 'TV-MA': '17+',
    # 英国（BBFC）：15岁级别仍属于青少年段，18岁才是成人段
    'U': '0-6',
    '12A': '13-16', '12': '13-16',
    '15': '13-16', '18': '17+',
    # 德国（FSK，TMDB 上为数字形式）
    'FSK 0': '0-6', 'FSK 6': '7-12', '6': '7-12',
    'FSK 12': '13-16',
    'FSK 16': '13-16', '16': '13-16',
    # 法国（CN）
    '-10': '7-12',
    '-12': '13-16',
    '-16': '13-16', '-18': '17+',
    # 日本（映倫）
    'PG12': '13-16',
    'R-15+': '13-16', 'R15+': '13-16',
    'R-18+': '17+', 'R18+': '17+',
    # 韩国（영등급위）
    'ALL': '0-6', '전체관람가': '0-6',
    '12세이상관람가': '13-16',
    '15세이상관람가': '13-16',
    '19': '17+', '청소년관람불가': '17+',
    # 加拿大/澳大利亚常见
    '14A': '13-16', '18A': '17+',
    'MA15+': '13-16',
}


def check_tier_access(required_tier: str) -> bool:
    return True


def get_dimensions_for_tmdb(conn) -> list:
    from media_importer.infrastructure.db import get_all_dimensions
    dims = get_all_dimensions(conn)
    result = []
    for dim in dims:
        if dim.get('source_type') == 'ai+tmdb' and dim.get('tmdb_field'):
            result.append({
                'name': dim['name'],
                'label': dim['label'],
                'source_type': dim['source_type'],
                'tmdb_field': dim.get('tmdb_field', ''),
                'value_list': dim.get('value_list', []),
                'is_enabled': dim.get('is_enabled', 1),
            })
    return result


def get_dimensions_for_provider(conn, provider_type: str) -> list:
    from media_importer.infrastructure.db import get_all_dimensions
    dims = get_all_dimensions(conn)
    result = []
    for dim in dims:
        if dim.get('source_type') not in ('provider', 'ai+provider'):
            continue
        provider_mappings_raw = dim.get('provider_mappings', '')
        if not provider_mappings_raw:
            continue
        if isinstance(provider_mappings_raw, str):
            try:
                provider_mappings = json.loads(provider_mappings_raw)
            except (json.JSONDecodeError, TypeError):
                continue
        elif isinstance(provider_mappings_raw, dict):
            provider_mappings = provider_mappings_raw
        else:
            continue
        if provider_type not in provider_mappings:
            continue
        result.append({
            'name': dim['name'],
            'label': dim['label'],
            'source_type': dim['source_type'],
            'provider_mappings': provider_mappings,
            'value_list': dim.get('value_list', []),
            'is_enabled': dim.get('is_enabled', 1),
        })
    return result


def get_dimensions_for_file(conn) -> list:
    from media_importer.infrastructure.db import get_all_dimensions
    dims = get_all_dimensions(conn)
    result = []
    for dim in dims:
        if dim.get('source_type') == 'file':
            result.append({
                'name': dim['name'],
                'label': dim['label'],
                'value_list': dim.get('value_list', []),
                'is_enabled': dim.get('is_enabled', 1),
            })
    return result


def map_tmdb_to_dimension(dim_config: dict, tmdb_data: dict, release_dates: Optional[list] = None) -> dict:
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

    return {'name': name, 'value': None, 'source_reliability': 0}


def _extract_genre_ids(provider_data: dict) -> set:
    genres = provider_data.get('genres', [])
    if not genres:
        return set()
    result = set()
    for g in genres:
        if isinstance(g, dict) and 'id' in g:
            result.add(str(g['id']))
        elif isinstance(g, (int, str)):
            result.add(str(g))
    return result


def _map_region_v2(name: str, mapping: dict, provider_data: dict) -> dict:
    field = mapping.get('field', 'origin_country')
    origin_countries = provider_data.get(field, [])
    if not origin_countries:
        return {'name': name, 'value': None, 'source_reliability': 0}

    first_country = origin_countries[0] if isinstance(origin_countries, list) else origin_countries

    match_rules = mapping.get('match_rules', {})
    if not match_rules:
        flat_codes = mapping.get('codes', {})
        if flat_codes:
            match_rules = {k: {'codes': v} for k, v in flat_codes.items()}
    for rule_value, rule_config in match_rules.items():
        codes = rule_config.get('codes', [])
        if first_country in codes:
            return {'name': name, 'value': rule_value, 'source_reliability': 1.0}

    return {'name': name, 'value': 'other', 'source_reliability': 1.0}


def _map_origin_lang_v2(name: str, mapping: dict, provider_data: dict, value_list: Optional[list] = None) -> dict:
    field = mapping.get('field', 'original_language')
    original_language = provider_data.get(field, '')
    if not original_language:
        return {'name': name, 'value': None, 'source_reliability': 0}

    match_rules = mapping.get('match_rules', {})
    if match_rules:
        for rule_value, rule_config in match_rules.items():
            langs = rule_config.get('languages', [])
            if original_language in langs:
                return {'name': name, 'value': rule_value, 'source_reliability': 1.0}
        return {'name': name, 'value': 'other', 'source_reliability': 1.0}

    if value_list:
        for vl in value_list:
            if vl.get('value') == original_language:
                return {'name': name, 'value': original_language, 'source_reliability': 1.0}
        for vl in value_list:
            if vl.get('value') == 'other':
                return {'name': name, 'value': 'other', 'source_reliability': 1.0}

    return {'name': name, 'value': 'other', 'source_reliability': 1.0}


def _map_genre_by_rules(name: str, mapping: dict, value_list: list, provider_data: dict) -> dict:
    genres = provider_data.get('genres', [])
    ordered_ids = []
    for g in genres:
        if isinstance(g, dict) and 'id' in g:
            ordered_ids.append(str(g['id']))
        elif isinstance(g, (int, str)):
            ordered_ids.append(str(g))
    if not ordered_ids:
        return {'name': name, 'value': None, 'source_reliability': 0}

    match_rules = mapping.get('match_rules', {})
    id_to_category = {}
    for category, rule_config in match_rules.items():
        for gid in rule_config.get('ids', []):
            id_to_category[str(gid)] = category

    for gid in ordered_ids:
        category = id_to_category.get(gid)
        if category:
            for vl in value_list:
                if vl.get('value') == category:
                    return {'name': name, 'value': category, 'source_reliability': 0.9}

    return {'name': name, 'value': 'other', 'source_reliability': 0.9}


def _map_bool_genre(name: str, mapping: dict, provider_data: dict) -> dict:
    genre_ids = _extract_genre_ids(provider_data)
    if not genre_ids:
        return {'name': name, 'value': None, 'source_reliability': 0}

    match_rules = mapping.get('match_rules', {})
    true_config = match_rules.get('true', {})
    true_ids = set(str(i) for i in true_config.get('ids', []))

    if genre_ids & true_ids:
        return {'name': name, 'value': 'true', 'source_reliability': 1.0}
    elif genre_ids:
        return {'name': name, 'value': 'false', 'source_reliability': 0.9}
    else:
        return {'name': name, 'value': None, 'source_reliability': 0}


def _map_genre_by_names(name: str, mapping: dict, provider_data: dict) -> dict:
    return {'name': name, 'value': None, 'source_reliability': 0}


def map_provider_to_dimension(dim_config: dict, provider_data: dict, release_dates: Optional[list] = None, provider_type: str = "tmdb") -> dict:
    name = dim_config['name']
    value_list = dim_config.get('value_list', [])

    provider_mappings = dim_config.get('provider_mappings', {})
    if not isinstance(provider_mappings, dict):
        return {'name': name, 'value': None, 'source_reliability': 0}

    mapping = provider_mappings.get(provider_type, {})
    if not mapping:
        return {'name': name, 'value': None, 'source_reliability': 0}

    match_type = mapping.get('match_type', '')

    if match_type == 'genre_ids':
        if name in ('documentary', 'animation'):
            return _map_bool_genre(name, mapping, provider_data)
        else:
            return _map_genre_by_rules(name, mapping, value_list, provider_data)

    if match_type == 'country_codes':
        return _map_region_v2(name, mapping, provider_data)

    if match_type == 'direct_match':
        return _map_origin_lang_v2(name, mapping, provider_data, value_list)

    if match_type == 'certification':
        return _map_restricted_level(name, value_list, release_dates or [])

    if match_type == 'genre_names':
        return _map_genre_by_names(name, mapping, provider_data)

    return {'name': name, 'value': None, 'source_reliability': 0}




def _map_region(name: str, value_list: list, tmdb_data: dict) -> dict:
    origin_countries = tmdb_data.get('origin_country', [])
    if not origin_countries:
        return {'name': name, 'value': None, 'source_reliability': 0}

    first_country = origin_countries[0] if isinstance(origin_countries, list) else origin_countries

    for vl in value_list:
        tmdb_codes = vl.get('tmdb_codes', [])
        if first_country in tmdb_codes:
            return {'name': name, 'value': vl['value'], 'source_reliability': 1.0}

    for vl in value_list:
        if vl.get('value') == 'other':
            return {'name': name, 'value': 'other', 'source_reliability': 1.0}

    return {'name': name, 'value': None, 'source_reliability': 0}


def _map_origin_lang(name: str, value_list: list, tmdb_data: dict) -> dict:
    original_language = tmdb_data.get('original_language', '')
    if not original_language:
        return {'name': name, 'value': None, 'source_reliability': 0}

    for vl in value_list:
        if vl.get('value') == original_language:
            return {'name': name, 'value': original_language, 'source_reliability': 1.0}

    for vl in value_list:
        if vl.get('value') == 'other':
            return {'name': name, 'value': 'other', 'source_reliability': 1.0}

    return {'name': name, 'value': 'other', 'source_reliability': 1.0}


def _map_broad_genre(name: str, value_list: list, tmdb_data: dict) -> dict:
    genres = tmdb_data.get('genres', [])
    if not genres:
        return {'name': name, 'value': None, 'source_reliability': 0}

    genre_ids = []
    for g in genres:
        if isinstance(g, dict) and 'id' in g:
            genre_ids.append(g['id'])
        elif isinstance(g, int):
            genre_ids.append(g)

    if not genre_ids:
        return {'name': name, 'value': None, 'source_reliability': 0}

    sorted_values = sorted(value_list, key=lambda x: x.get('priority', 99))

    for vl in sorted_values:
        tmdb_genre_ids = vl.get('tmdb_genre_ids', [])
        for gid in genre_ids:
            if gid in tmdb_genre_ids:
                return {'name': name, 'value': vl['value'], 'source_reliability': 0.9}

    for vl in sorted_values:
        if vl.get('value') == 'other':
            return {'name': name, 'value': 'other', 'source_reliability': 0.9}

    return {'name': name, 'value': 'other', 'source_reliability': 0.9}


def _map_documentary(name: str, value_list: list, tmdb_data: dict) -> dict:
    genres = tmdb_data.get('genres', [])
    if not genres:
        return {'name': name, 'value': None, 'source_reliability': 0}

    genre_ids = []
    for g in genres:
        if isinstance(g, dict) and 'id' in g:
            genre_ids.append(g['id'])
        elif isinstance(g, int):
            genre_ids.append(g)

    if 99 in genre_ids:
        return {'name': name, 'value': 'true', 'source_reliability': 1.0}
    elif genre_ids:
        return {'name': name, 'value': 'false', 'source_reliability': 0.9}
    else:
        return {'name': name, 'value': None, 'source_reliability': 0}


def _map_animation(name: str, value_list: list, tmdb_data: dict) -> dict:
    genres = tmdb_data.get('genres', [])
    if not genres:
        return {'name': name, 'value': None, 'source_reliability': 0}

    genre_ids = []
    for g in genres:
        if isinstance(g, dict) and 'id' in g:
            genre_ids.append(g['id'])
        elif isinstance(g, int):
            genre_ids.append(g)

    if 16 in genre_ids:
        return {'name': name, 'value': 'true', 'source_reliability': 1.0}
    elif genre_ids:
        return {'name': name, 'value': 'false', 'source_reliability': 0.9}
    else:
        return {'name': name, 'value': None, 'source_reliability': 0}


def _map_restricted_level(name: str, value_list: list, release_dates: list) -> dict:
    """TMDB release_dates 多国分级 → 年龄段（ADR-0010：9 国优先级规则增强）。

    优先级：US > GB > DE > FR > CN > JP > KR > AU > CA > 其他（数据可信度递减）。
    旧实现只消费 US/GB 两国数据，2026-08-22 起全 9 国参与映射。
    """
    if not release_dates:
        return {'name': name, 'value': None, 'source_reliability': 0}

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

        tv_rating = result.get('rating', '').strip().upper()
        if tv_rating and tv_rating in CERTIFICATION_TO_LEVEL:
            level = CERTIFICATION_TO_LEVEL[tv_rating]
            source_reliability = 1.0 if iso == 'US' else 0.95
            return {'name': name, 'value': level, 'source_reliability': source_reliability}

        dates = result.get('release_dates', [])
        if not dates:
            continue

        for rd in dates:
            cert = rd.get('certification', '').strip().upper()
            if cert in CERTIFICATION_TO_LEVEL:
                level = CERTIFICATION_TO_LEVEL[cert]
                source_reliability = 1.0 if iso == 'US' else 0.95
                return {'name': name, 'value': level, 'source_reliability': source_reliability}

    return {'name': name, 'value': None, 'source_reliability': 0}
