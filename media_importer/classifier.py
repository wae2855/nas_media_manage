#!/usr/bin/env python3
import re
from typing import Dict, Any


def match_conditions(dimensions: Dict[str, Any], conditions: Dict[str, Any]) -> bool:
    for key, expected_value in conditions.items():
        actual_value = dimensions.get(key)
        if actual_value != expected_value:
            return False
    return True


def render_template(template: str, scraped_info: Dict[str, Any]) -> str:
    result = template

    for key in ['title_cn', 'title_en', 'year', 'season', 'episode', 'resolution', 'quality']:
        value = scraped_info.get(key)
        placeholder = "{" + key + "}"
        if placeholder in result:
            if value is not None:
                result = result.replace(placeholder, str(value))
            else:
                result = result.replace(placeholder, '')

    dimension_pattern = r'\{dimension\.([^}]+)\}'
    matches = re.findall(dimension_pattern, template)
    for dim_name in matches:
        placeholder = "{dimension." + dim_name + "}"
        value = scraped_info.get('dimensions', {}).get(dim_name, '')
        if placeholder in result:
            result = result.replace(placeholder, str(value) if value is not None else '')

    result = re.sub(r'\(\s*\)', '', result)
    result = re.sub(r'/{2,}', '/', result)
    result = re.sub(r'\.\.', '.', result)
    return result.rstrip('/') + '/'


def classify(scraped_info: dict, path_rules: list) -> str:
    dimensions = scraped_info.get('dimensions', {})

    for rule in path_rules:
        conditions = rule.get('conditions', {})
        if match_conditions(dimensions, conditions):
            template = rule.get('template', '')
            return render_template(template, scraped_info)

    for rule in path_rules:
        conditions = rule.get('conditions', {})
        if conditions == {}:
            template = rule.get('template', '')
            return render_template(template, scraped_info)

    return ''
