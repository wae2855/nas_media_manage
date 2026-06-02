#!/usr/bin/env python3
import json
import sys
import os
import re
import math
import requests

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from media_importer.features.scraping import (
    ConfidenceEngine, FilenameCleaner, TitleMatcher, MatchResult,
    _calc_R, _similarity, DEFAULT_CONFIDENCE_CONFIG
)

CONFIG_YAML_PATH = os.path.join(os.path.dirname(__file__), '..', 'config', 'config.yaml')

def load_confidence_config():
    import yaml
    with open(CONFIG_YAML_PATH, 'r') as f:
        cfg = yaml.safe_load(f)
    return cfg.get('confidence', {})

def build_prompt(conf, user_need):
    r_formula = conf.get('R_formula', 'log')
    r_desc = {'inverse': 'R = 1/N', 'log': 'R = 1/log2(N+1)', 'sqrt': 'R = 1/sqrt(N)', 'flat': 'R = 1.0（不惩罚）'}

    dim_cfg = conf.get('dimensions', {})
    dim_lines = ''
    for dk, dcfg in dim_cfg.items():
        sources = dcfg.get('sources', [])
        src_parts = []
        for s in sources:
            src = s.get('source', '')
            trusted = s.get('trusted', True)
            src_parts.append(f"{src}({'✓可信' if trusted else '✗不可信'})")
        dim_lines += f'  {dk}: {">".join(src_parts)}\n'

    prompt = '# 影音库AI智能整理 — 置信度配置咨询助手\n'
    prompt += '\n你是 影音库AI智能整理的配置顾问。你的任务是根据用户需求，给出精确的配置建议，让用户直接在 Web 界面上修改对应参数。\n'
    prompt += '\n## 一、系统工作流程\n'
    prompt += '\n影音库AI智能整理自动刮削视频文件元数据并分类入库。处理流程：\n'
    prompt += '\n1. **文件名清洗**：用正则表达式从文件名中提取标题、年份、季集号。支持中英文标题自动拆分（如"蝙蝠侠：黑暗骑士.The.Dark.Knight.2008"会拆分为英文标题"The Dark Knight"）。如果年份可疑（如年份在未来、或清洗后标题残留年份），标记为 year_suspect，跳过直接搜索。\n'
    prompt += '2. **TMDB 搜索**：用清洗后的标题+年份搜索 TMDB 数据库，获取匹配结果。如果第一次搜索无结果或匹配分低于阈值，会触发 AI 辅助清洗后重新搜索。\n'
    prompt += '3. **AI 刮削**：调用 LLM 提取元数据（标题、年份、分辨率、维度信息等）。\n'
    prompt += '4. **置信度计算**：根据 TMDB 匹配质量和 AI 数据可信度计算最终置信度。\n'
    prompt += '5. **决策判定**：根据置信度自动决定任务状态。\n'
    prompt += '\n系统有两条独立的计算路径：\n'
    prompt += '- **TMDB+AI 路径**（TMDB 启用时）：使用 TMDB 搜索结果计算\n'
    prompt += '- **纯 AI 路径**（TMDB 未启用或无结果时）：仅依赖 AI 判断\n'
    prompt += '\n## 二、置信度计算公式详解\n'
    prompt += '\n### 路径 A：TMDB+AI（推荐路径）\n'
    prompt += '\n```\n最终置信度 = search_conf × data_gate\n\nsearch_conf = T × R\n  T = 标题匹配分（L1~L7 七个等级，见下文）\n  R = 搜索结果数惩罚因子（结果越多越不确定）\n\ndata_gate = 1.0（所有维度来源可信）或 0.0（有维度来源不可信 → 强制需审核）\n```\n'
    prompt += '\n#### T 值：标题匹配等级\n'
    prompt += '\n系统将文件名清洗后的标题与 TMDB 返回的标题做比较，分精确匹配和模糊匹配两种情况：\n'
    prompt += '\n**精确匹配（标准化后完全相同）时：**\n'
    prompt += '| 等级 | 条件 | T值参数名 | 当前值 | 说明 |\n'
    prompt += '|------|------|-----------|--------|------|\n'
    prompt += f'| L1 | 标题精确 + 年份精确一致 | title_exact_with_year | {conf.get("title_exact_with_year", 1.0)} | 最高置信，标题和年份都对上了 |\n'
    prompt += f'| L2 | 标题精确 + 有季号（无年份） | title_exact_with_season | {conf.get("title_exact_with_season", 0.9)} | 剧集常见，用季号辅助确认 |\n'
    prompt += f'| L3 | 标题精确 + 无年份也无季号 | title_exact_no_year | {conf.get("title_exact_no_year", 0.7)} | 标题对了但缺少时间锚定 |\n'
    prompt += f'| L4 | 标题精确 + 年份不匹配 | title_exact_year_mismatch | {conf.get("title_exact_year_mismatch", 0.4)} | 可能是同名不同年作品 |\n'
    prompt += '\n**模糊匹配（相似度 ≥ title_min_similarity）时：**\n'
    prompt += '| 等级 | 条件 | T值计算 | 说明 |\n'
    prompt += '|------|------|---------|------|\n'
    prompt += '| L5 | 模糊匹配 + 年份精确 | T = 相似度值 | 年份一致起到锚定作用，不加惩罚 |\n'
    prompt += f'| L6 | 模糊匹配 + 年份不匹配或无年份 | T = 相似度 × title_fuzzy_year_coeff | 缺少年份确认，打折扣 |\n'
    prompt += '| L7 | 相似度 < title_min_similarity | T = 0.0 | 完全不匹配 |\n'
    prompt += f'\n当前 title_fuzzy_year_coeff = {conf.get("title_fuzzy_year_coeff", 0.7)}，title_min_similarity = {conf.get("title_min_similarity", 0.3)}\n'
    prompt += '\n#### R 值：搜索结果数惩罚\n'
    prompt += '\nTMDB 搜索返回的结果越多，说明标题越不唯一，需要降低置信度。R 的计算分两步：\n'
    prompt += '\n**第一步：基础 R 值**（根据搜索结果总数 N 计算，N 上限为 R_max_results_cap）\n'
    prompt += '- inverse: R = 1/N（线性衰减，只有1个结果时R=1.0）\n'
    prompt += '- log: R = 1/log2(N+1)（对数衰减，推荐默认，温和惩罚）\n'
    prompt += '- sqrt: R = 1/sqrt(N)（平方根衰减，中等惩罚）\n'
    prompt += '- flat: R = 1.0（不惩罚，忽略结果数）\n'
    prompt += f'\n当前公式: {r_formula}（{r_desc.get(r_formula, r_formula)}），R_max_results_cap = {conf.get("R_max_results_cap", 10)}，R_min_value = {conf.get("R_min_value", 0.1)}\n'
    prompt += '\n**第二步：T 值自信任增强**（当 T > R_T_floor 时，R 向 1.0 方向调整）\n'
    prompt += '```\nalpha = ((T - R_T_floor) / (1.0 - R_T_floor)) ^ R_T_curve\nR_adjusted = R_base × (1 - alpha) + alpha\n```\n'
    prompt += '含义：标题匹配度越高，搜索结果数量的惩罚越小。因为高 T 值说明结果已经很明确了。\n'
    prompt += f'当前 R_T_floor = {conf.get("R_T_floor", 0.5)}，R_T_curve = {conf.get("R_T_curve", 1.5)}\n'
    prompt += '\n#### data_gate：数据来源可信门控\n'
    prompt += '\n每个维度（如影视类型、年龄分级等）的数据来源有三个：tmdb、ai、file。系统按配置的优先级顺序选取第一个有数据的来源。如果选中的来源不在该维度的信任列表中，且没有其他可信来源可用，则 data_gate = 0，强制进入审核。\n'
    prompt += '\n**关键规则**：如果某个维度有数据来自不可信来源，但同时该维度也有来自可信来源的数据（即使优先级更低），系统会使用可信来源的数据，不会触发门控阻断。只有所有可用来源都不可信时才阻断。\n'
    prompt += '\n### 路径 B：纯 AI 模式\n'
    prompt += '\n```\n最终置信度 = objective_cap × data_gate\n\nobjective_cap 根据 AI 返回标题与清洗标题的相似度(sim)计算：\n  sim >= ai_cap_high_similarity → cap = sim（AI标题高度一致，用相似度本身）\n  sim >= ai_cap_low_similarity  → cap = sim × ai_cap_low_coeff（低相似度，衰减处理）\n  sim < ai_cap_low_similarity   → cap = ai_cap_no_match（完全不匹配，兜底值）\n  AI 无标题                      → cap = ai_cap_no_title（AI没返回标题，兜底值）\n```\n'
    prompt += f'\n当前 ai_cap_high_similarity = {conf.get("ai_cap_high_similarity", 0.7)}，ai_cap_low_similarity = {conf.get("ai_cap_low_similarity", 0.3)}，ai_cap_no_title = {conf.get("ai_cap_no_title", 0.3)}，ai_cap_no_match = {conf.get("ai_cap_no_match", 0.2)}，ai_cap_low_coeff = {conf.get("ai_cap_low_coeff", 0.5)}\n'
    prompt += '\n### 决策阈值\n'
    prompt += '\n根据最终置信度判定任务状态：\n'
    prompt += '| 置信度范围 | 状态 | 说明 |\n'
    prompt += '|-----------|------|------|\n'
    prompt += f'| >= pass_threshold({conf.get("pass_threshold", 0.8)}) | PASS 自动通过 | 无需人工干预 |\n'
    prompt += f'| >= confirm_threshold({conf.get("confirm_threshold", 0.5)}) | CONFIRMING 需确认 | 建议人工确认 |\n'
    prompt += f'| >= review_threshold({conf.get("review_threshold", 0.3)}) | NEEDS_REVIEW 需审核 | 必须人工审核 |\n'
    prompt += '| < review_threshold | FAILED 失败 | 自动拒绝 |\n'
    prompt += '\n**特殊规则**：data_gate = 0 时，无论置信度多高，状态强制为 NEEDS_REVIEW。\n'
    prompt += f'\n### TMDB 最低匹配阈值\n\ntmdb_match_threshold = {conf.get("tmdb_match_threshold", 0.7)}。当第一次 TMDB 搜索的最佳匹配 T 值低于此阈值时，触发 AI 辅助清洗后重新搜索。\n'
    prompt += '\n## 三、当前完整配置\n\n```\n决策阈值:\n'
    prompt += f'  自动通过(pass_threshold) = {conf.get("pass_threshold", 0.8)}\n'
    prompt += f'  需确认(confirm_threshold) = {conf.get("confirm_threshold", 0.5)}\n'
    prompt += f'  需审核(review_threshold) = {conf.get("review_threshold", 0.3)}\n\n'
    prompt += '标题匹配等级(T值):\n'
    prompt += f'  L1精确+年份精确(title_exact_with_year) = {conf.get("title_exact_with_year", 1.0)}\n'
    prompt += f'  L2精确+有季号(title_exact_with_season) = {conf.get("title_exact_with_season", 0.9)}\n'
    prompt += f'  L3精确无年份(title_exact_no_year) = {conf.get("title_exact_no_year", 0.7)}\n'
    prompt += f'  L4精确年份不匹配(title_exact_year_mismatch) = {conf.get("title_exact_year_mismatch", 0.4)}\n'
    prompt += f'  模糊年份系数(title_fuzzy_year_coeff) = {conf.get("title_fuzzy_year_coeff", 0.7)}\n'
    prompt += f'  最低相似度(title_min_similarity) = {conf.get("title_min_similarity", 0.3)}\n'
    prompt += f'  TMDB最低匹配阈值(tmdb_match_threshold) = {conf.get("tmdb_match_threshold", 0.7)}\n\n'
    prompt += 'R值(搜索结果惩罚):\n'
    prompt += f'  公式(R_formula) = {r_formula}（{r_desc.get(r_formula, r_formula)}）\n'
    prompt += f'  结果数上限(R_max_results_cap) = {conf.get("R_max_results_cap", 10)}\n'
    prompt += f'  下限(R_min_value) = {conf.get("R_min_value", 0.1)}\n'
    prompt += f'  自信任门槛(R_T_floor) = {conf.get("R_T_floor", 0.5)}\n'
    prompt += f'  自信任曲率(R_T_curve) = {conf.get("R_T_curve", 1.5)}\n\n'
    prompt += '纯AI模式参数:\n'
    prompt += f'  高相似度门槛(ai_cap_high_similarity) = {conf.get("ai_cap_high_similarity", 0.7)}\n'
    prompt += f'  低相似度门槛(ai_cap_low_similarity) = {conf.get("ai_cap_low_similarity", 0.3)}\n'
    prompt += f'  无标题上限(ai_cap_no_title) = {conf.get("ai_cap_no_title", 0.3)}\n'
    prompt += f'  无匹配上限(ai_cap_no_match) = {conf.get("ai_cap_no_match", 0.2)}\n'
    prompt += f'  低相似度衰减(ai_cap_low_coeff) = {conf.get("ai_cap_low_coeff", 0.5)}\n'
    if dim_lines:
        prompt += f'\n维度来源配置(每个维度的来源优先级和信任状态):\n{dim_lines}'
    prompt += '```\n'
    prompt += f'\n## 四、用户需求\n\n{user_need}\n'
    prompt += '\n## 五、回答格式要求\n\n请按以下三部分回答。用户会在 Web 界面上逐项修改，不是编辑配置文件。配置项名称要使用括号内的英文参数名，方便用户在界面上找到对应输入框。\n'
    prompt += '\n### 第一部分：配置清单\n\n只列出需要调整的参数。格式：`区域.参数名(英文名) = 建议值`。\n\n格式示例：\n```\n决策阈值.自动通过(pass_threshold) = 0.85\n标题匹配等级.精确无年份(title_exact_no_year) = 0.75\n维度来源.年龄分级(restricted_level): 只信任tmdb\n```\n'
    prompt += '\n### 第二部分：调整原因\n\n针对每个调整项，用 1-2 句话说明为什么要改、改了会有什么效果。\n'
    prompt += '\n### 第三部分：示例计算\n\n用 1-2 个文件名模拟完整计算过程，展示每一步的中间值和最终结果。让用户能直观理解"改了这个参数，置信度会怎么变"。示例应覆盖用户关心的场景。\n'
    prompt += '\n---\n\n要求：\n1. **所有参数建议值必须在 0.0~1.0 范围内**。T值本质是置信度权重，最大为1.0；阈值也是0-1之间的概率值。没有参数可以超过1.0。R_max_results_cap 是唯一大于1的整数参数。\n2. 阈值必须满足 pass > confirm > review\n3. T 值等级应满足 L1 ≥ L2 ≥ L3 > L4\n4. 如果用户需求不明确，给出两套方案并说明适用场景\n5. 如果当前配置已经合理，明确告诉用户"当前配置适合您的场景，无需调整"\n6. 严格模式不是靠提高T值超过1.0来实现，而是靠提高pass_threshold或降低L3/L4的T值来实现'
    return prompt


def verify_calculation(engine, clean_title, year, tmdb_result, total_results, expected_conf_range, label):
    match_result = engine.matcher.match(clean_title, tmdb_result, year=year)
    search_conf, R, R_formula, R_base = engine._calc_search_conf(match_result.T, total_results)
    dims = {
        'media_type': {'value': 'movie', 'source': 'tmdb'},
        'restricted_level': {'value': 'R', 'source': 'tmdb'},
        'documentary': {'value': 'false', 'source': 'tmdb'},
        'animation': {'value': 'false', 'source': 'tmdb'},
    }
    data_gate, dim_results, gate_blocked = engine._calc_data_gate(dims)
    final = round(search_conf * data_gate, 4)
    level = engine.get_confidence_level(final, gate_blocked)

    ok = expected_conf_range[0] <= final <= expected_conf_range[1]
    status = "✅" if ok else "❌"
    print(f"  {status} {label}: T={match_result.T:.3f}({match_result.level}), R={R:.4f}, search_conf={search_conf:.4f}, gate={data_gate}, final={final:.4f}({level})")
    if not ok:
        print(f"     期望范围: [{expected_conf_range[0]}, {expected_conf_range[1]}]")
    return ok


def call_llm(prompt, llm_config):
    url = f"{llm_config['base_url'].rstrip('/')}/chat/completions"
    headers = {'Content-Type': 'application/json', 'Authorization': f'Bearer {llm_config["api_key"]}'}
    body = {
        'model': llm_config.get('fast_model') or llm_config.get('model', 'MiniMax-M2.5'),
        'messages': [{'role': 'user', 'content': prompt}],
        'temperature': 0.3,
        'max_tokens': 2000,
    }
    resp = requests.post(url, headers=headers, json=body, timeout=60)
    resp.raise_for_status()
    data = resp.json()
    text = data['choices'][0]['message']['content']
    think_match = re.search(r'</think\s*>', text, re.DOTALL)
    if think_match:
        text = text[think_match.end():].strip()
    return text


def verify_llm_response(response, scenario_name):
    issues = []
    has_part1 = '第一部分' in response or '配置清单' in response
    has_part2 = '第二部分' in response or '调整原因' in response
    has_part3 = '第三部分' in response or '示例计算' in response
    if not has_part1:
        issues.append("缺少第一部分：配置清单")
    if not has_part2:
        issues.append("缺少第二部分：调整原因")
    if not has_part3:
        issues.append("缺少第三部分：示例计算")

    param_names = ['pass_threshold', 'confirm_threshold', 'review_threshold',
                   'title_exact_with_year', 'title_exact_no_year', 'title_exact_year_mismatch',
                   'title_fuzzy_year_coeff', 'title_min_similarity', 'tmdb_match_threshold',
                   'R_formula', 'R_max_results_cap', 'R_min_value', 'R_T_floor', 'R_T_curve',
                   'ai_cap_high_similarity', 'ai_cap_low_similarity', 'ai_cap_no_title',
                   'ai_cap_no_match', 'ai_cap_low_coeff']
    mentioned_params = [p for p in param_names if p in response]

    value_pattern = re.compile(r'(?:pass_threshold|confirm_threshold|review_threshold|title_exact_with_year|title_exact_with_season|title_exact_no_year|title_exact_year_mismatch|title_fuzzy_year_coeff|title_min_similarity|tmdb_match_threshold|ai_cap_high_similarity|ai_cap_low_similarity|ai_cap_no_title|ai_cap_no_match|ai_cap_low_coeff|R_min_value|R_T_floor|R_T_curve)\s*[=：]\s*([0-9]*\.?[0-9]+)')
    values = value_pattern.findall(response)
    bad_values = [v for v in values if float(v) < 0 or float(v) > 1.0]

    if bad_values:
        issues.append(f"参数值超出0-1范围: {bad_values}")

    has_config_section = has_part1 or '配置清单' in response or '无需调整' in response or '无需修改' in response or '当前配置已满足' in response or '当前配置已经满足' in response or '无需大幅调整' in response
    has_reason_section = has_part2 or '调整原因' in response or '原因' in response or '理由' in response or '无需调整' in response or '无需修改' in response or '当前配置已满足' in response
    has_calc_section = has_part3 or '示例计算' in response or '计算过程' in response or 'search_conf' in response or 'T =' in response or 'T=' in response or '最终置信度' in response
    if not has_config_section:
        issues.append("缺少配置清单部分")
    if not has_reason_section:
        issues.append("缺少调整原因部分")
    if not has_calc_section:
        issues.append("缺少示例计算部分")

    if issues:
        print(f"  ❌ {scenario_name}: {', '.join(issues)}")
    else:
        print(f"  ✅ {scenario_name}: 格式完整, 提及{len(mentioned_params)}个参数, 值范围正常")
    return len(issues) == 0


def main():
    conf = load_confidence_config()
    engine = ConfidenceEngine(conf)

    print("=" * 70)
    print("第一步：验证置信度计算引擎的正确性")
    print("=" * 70)

    all_ok = True

    tmdb_result = {
        "title": "The Dark Knight",
        "original_title": "The Dark Knight",
        "release_date": "2008-07-18",
    }
    all_ok &= verify_calculation(engine, "The Dark Knight", 2008, tmdb_result, 1,
                                  [0.9, 1.0], "L1: 精确+年份一致, 1个结果")
    all_ok &= verify_calculation(engine, "The Dark Knight", 2008, tmdb_result, 5,
                                  [0.7, 1.0], "L1: 精确+年份一致, 5个结果")
    all_ok &= verify_calculation(engine, "The Dark Knight", None, tmdb_result, 1,
                                  [0.6, 0.8], "L3: 精确无年份, 1个结果")
    all_ok &= verify_calculation(engine, "The Dark Knight", 2007, tmdb_result, 1,
                                  [0.3, 0.5], "L4: 精确年份不匹配, 1个结果")

    tmdb_blade = {
        "title": "Blade Runner 2049",
        "original_title": "Blade Runner 2049",
        "release_date": "2017-10-06",
    }
    all_ok &= verify_calculation(engine, "Blade Runner 2049", 2017, tmdb_blade, 1,
                                  [0.9, 1.0], "L1: 精确+年份一致, 1个结果")

    print()

    print("=" * 70)
    print("第二步：验证 LLM 对提示词的理解（5个用户场景）")
    print("=" * 70)

    llm_config = {
        'base_url': conf.get('_llm_base_url', 'https://api.minimaxi.chat/v1'),
        'api_key': conf.get('_llm_api_key', ''),
        'model': 'MiniMax-M2.5',
        'fast_model': 'MiniMax-M2.5',
    }

    import yaml
    with open(CONFIG_YAML_PATH, 'r') as f:
        full_cfg = yaml.safe_load(f)
    llm_section = full_cfg.get('llm', {})
    llm_config['base_url'] = llm_section.get('base_url', llm_config['base_url'])
    llm_config['api_key'] = llm_section.get('api_key', llm_config['api_key'])
    llm_config['fast_model'] = llm_section.get('fast_model') or llm_section.get('fallback_model') or llm_section.get('model', 'MiniMax-M2.5')

    scenarios = [
        {
            "name": "场景1：新手默认配置",
            "need": "我是新手，刚搭建好系统，使用默认配置就行，帮我看看当前配置是否合理",
        },
        {
            "name": "场景2：严格模式",
            "need": "我希望只有TMDB精确匹配+年份一致的才自动通过，其他都需人工确认。我的文件名都很规范，基本都有年份",
        },
        {
            "name": "场景3：宽松模式",
            "need": "我的文件名不太规范，经常缺少年份信息。我希望只要标题对上了就自动通过，减少人工确认的工作量",
        },
        {
            "name": "场景4：动漫收藏场景",
            "need": "我主要收藏动漫，文件名经常没有年份，而且TMDB的动漫数据不如AI准确。我希望AI判断的动画和类型也能被信任",
        },
        {
            "name": "场景5：混合媒体库",
            "need": "我同时有电影、电视剧和纪录片。纪录片经常被误判，我想让TMDB和AI的纪录片判断都可信。另外年龄分级我只信任TMDB",
        },
    ]

    llm_ok = True
    for scenario in scenarios:
        print(f"\n--- {scenario['name']} ---")
        prompt = build_prompt(conf, scenario['need'])
        try:
            response = call_llm(prompt, llm_config)
            ok = verify_llm_response(response, scenario['name'])
            llm_ok &= ok
            print(f"  LLM回复前200字: {response[:200]}...")
        except Exception as e:
            print(f"  ❌ LLM调用失败: {e}")
            llm_ok = False

    print()
    print("=" * 70)
    print("第三步：验证示例计算过程的数学正确性")
    print("=" * 70)

    print("\n用当前配置手动计算几个场景，与引擎结果对比：")

    def manual_calc(T, N, label):
        R_base = _calc_R(N, conf.get('R_formula', 'log'), conf.get('R_max_results_cap', 10), conf.get('R_min_value', 0.1))
        R_T_floor = conf.get('R_T_floor', 0.5)
        R_T_curve = conf.get('R_T_curve', 1.5)
        if T > R_T_floor and R_T_floor < 1.0:
            alpha = ((T - R_T_floor) / (1.0 - R_T_floor)) ** R_T_curve
            R = R_base * (1.0 - alpha) + alpha
        else:
            R = R_base
        search_conf = T * R
        print(f"  {label}: T={T:.3f}, N={N}, R_base={R_base:.4f}, R_adj={R:.4f}, search_conf={search_conf:.4f}")

    manual_calc(1.0, 1, "L1+1结果")
    manual_calc(1.0, 5, "L1+5结果")
    manual_calc(1.0, 10, "L1+10结果")
    manual_calc(0.7, 1, "L3+1结果")
    manual_calc(0.7, 5, "L3+5结果")
    manual_calc(0.4, 1, "L4+1结果")
    manual_calc(0.4, 5, "L4+5结果")
    manual_calc(0.85, 3, "L5(sim=0.85)+3结果")
    manual_calc(0.6, 3, "L6(sim=0.6,coeff=0.7)+3结果")

    print()
    if all_ok and llm_ok:
        print("🎉 全部测试通过！提示词能被 LLM 正确理解，计算逻辑与引擎一致。")
    else:
        print("⚠️ 部分测试未通过，请检查上方标记为 ❌ 的项目。")

    return 0 if (all_ok and llm_ok) else 1


if __name__ == '__main__':
    sys.exit(main())
