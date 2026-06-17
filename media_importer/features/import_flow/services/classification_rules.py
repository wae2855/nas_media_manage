#!/usr/bin/env python3
import re
from typing import Dict, Any, Optional


BOOL_TRUE_STRINGS = {'true', 'yes', 'on'}
BOOL_FALSE_STRINGS = {'false', 'no', 'off'}


def _to_comparable(value):
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        if value.lower() in BOOL_TRUE_STRINGS:
            return True
        if value.lower() in BOOL_FALSE_STRINGS:
            return False
    return value


def match_conditions(dimensions: Dict[str, Any], conditions: Dict[str, Any],
                     enabled_dims: Optional[set] = None) -> bool:
    if enabled_dims is not None:
        conditions = {k: v for k, v in conditions.items() if k in enabled_dims}
    if not conditions:
        return True
    for key, expected_value in conditions.items():
        actual_value = dimensions.get(key)
        if actual_value is None and expected_value is None:
            continue
        if actual_value is None or expected_value is None:
            return False
        # restricted_level 支持 contains 语法（多个值用 | 分隔）
        if key == 'restricted_level':
            expected_str = str(expected_value)
            actual_str = str(actual_value)
            expected_values = [v.strip() for v in expected_str.split('|')]
            if actual_str not in expected_values:
                return False
        else:
            cmp_actual = _to_comparable(actual_value)
            cmp_expected = _to_comparable(expected_value)
            if cmp_actual != cmp_expected:
                return False
    return True


def render_template(template: str, scraped_info: Dict[str, Any], extra_vars: Optional[Dict[str, Any]] = None) -> str:
    result = template

    title_cn = scraped_info.get('title_cn')
    title_en = scraped_info.get('title_en', '')
    title = scraped_info.get('title', '')
    # 多层兜底：cn 空 → en → title，避免标题全空时命名模板退化为只剩年份
    if not title_cn and title_en:
        title_cn = title_en
    if not title_cn and title:
        title_cn = title
    if title_cn and title_cn != scraped_info.get('title_cn'):
        scraped_info = dict(scraped_info)
        scraped_info['title_cn'] = title_cn

    lookup = dict(scraped_info)
    if extra_vars:
        lookup.update(extra_vars)

    pattern = r'\{([^:}]+)(?::([^}]+))?\}'

    def replace_placeholder(match):
        key = match.group(1)
        fmt = match.group(2)

        if key.startswith('dimension.'):
            dim_name = key[len('dimension.'):]
            value = scraped_info.get('dimensions', {}).get(dim_name, '')
        else:
            value = lookup.get(key)

        if value is None:
            return ''

        try:
            if fmt:
                if key in ['season', 'episode']:
                    try:
                        value = int(value)
                    except (ValueError, TypeError):
                        pass
                return f"{{:{fmt}}}".format(value)
            else:
                if key == 'season':
                    try:
                        return f"{int(value):02d}"
                    except (ValueError, TypeError):
                        return str(value)
                elif key == 'episode':
                    try:
                        return f"{int(value):02d}"
                    except (ValueError, TypeError):
                        return str(value)
                else:
                    return str(value)
        except (ValueError, TypeError):
            return str(value) if value is not None else ''

    result = re.sub(pattern, replace_placeholder, result)

    result = re.sub(r'\s+\(\s*\)', '', result)
    result = re.sub(r'^\s*\(\s*\)', '', result)
    result = re.sub(r'/{2,}', '/', result)
    result = re.sub(r'\.{2,}', '.', result)
    result = re.sub(r'^\.+', '', result)
    return result.rstrip('/') + '/'


def classify(scraped_info: dict, path_rules: list, enabled_dims: Optional[set] = None) -> str:
    dimensions = scraped_info.get('dimensions', {})

    for rule in path_rules:
        conditions = rule.get('conditions', {})
        if match_conditions(dimensions, conditions, enabled_dims):
            template = rule.get('template', '')
            return render_template(template, scraped_info)

    for rule in path_rules:
        conditions = rule.get('conditions', {})
        if conditions == {}:
            template = rule.get('template', '')
            return render_template(template, scraped_info)

    return ''
