# 2026-06-14 第二级 AI 上下文辅助匹配改造方案（详细实施版）

## 0. 背景

当前第二级的 AI 输入是正则清洗后的 clean_title（可能被污染），且 AI 只能从已有 candidates 中选一个。改造后 AI 直接接收原始文件名 + 路径上下文，自己纠正标题，然后根据确定性（high/medium/low）分流。

## 1. 涉及文件清单

| 文件 | 改动 | 说明 |
|------|------|------|
| features/prompts/prompt_builder.py | 新增常量 | TIER2_CORRECT_PROMPT 类常量 |
| scraper/llm_scraper.py | 新增方法 | tier2_correct 方法 |
| features/scraping/match_engine.py | 重写+新增 | _tier2_context_match + 3个分流方法 + _collect_context增强 |
| api/tmdb_handlers.py | 适配 | _run_scrape_preview_job 适配新返回结构 |
| webui/index.html | 文案 | 匹配辅助卡片说明 |

## 2. 实施步骤

### 步骤 1：prompt_builder.py 新增默认提示词常量
文件: media_importer/features/prompts/prompt_builder.py
位置: LLMPromptBuilder 类中 DEFAULT_SYSTEM_PROMPT 之后
操作: 新增类常量 TIER2_CORRECT_PROMPT
内容: 见评审确认的提示词（含年份vs分辨率vs标题内数字区分规则 + 6个示例）

### 步骤 2：llm_scraper.py 新增 tier2_correct 方法
文件: media_importer/scraper/llm_scraper.py
位置: tier2_judge 方法结束后（约第517行）
逻辑:
1. 从 path_context 提取 path_segments/sibling_files/parent_folder/grandparent_folder
2. 构造 user_parts（原始文件名 + 路径上下文 + 正则参考）
3. system_prompt = self.prompt_resolver.get_match_assist_prompt() or LLMPromptBuilder.TIER2_CORRECT_PROMPT
4. 调 _do_call -> 解析 JSON（兼容 think标签/markdown代码块）
5. 异常兜底返回 certainty=low

### 步骤 3：match_engine.py 增强 _collect_context
文件: media_importer/features/scraping/match_engine.py
3.1 __init__ 中新增 self.source_dir = ""
3.2 替换 _collect_context（约第351行），新增从 source_dir 提取完整中间路径段

### 步骤 4：match_engine.py 重写 _tier2_context_match
文件: media_importer/features/scraping/match_engine.py
位置: 替换原方法（约第212-349行）
新逻辑: collect_context -> tier2_correct -> 按certainty分流到3个方法

### 步骤 5：match_engine.py 新增3个分流方法
文件: media_importer/features/scraping/match_engine.py
位置: _tier2_context_match 之后
- _tier2_high_certainty: 搜Provider -> CONTEXT_PASS
- _tier2_medium_certainty: 搜Provider -> NEEDS_CONFIRM
- _tier2_low_certainty: 不搜 -> NEEDS_CONFIRM

### 步骤 6：tmdb_handlers.py 适配模拟测试
文件: media_importer/api/tmdb_handlers.py
位置: 第160行附近
改动: tier2返回NEEDS_CONFIRM时跳过第三级，直接使用该结果

### 步骤 7：index.html 更新匹配辅助说明
文件: media_importer/webui/index.html
位置: 第551行
旧: Provider 精确搜索失败时，根据上下文建议新关键词
新: Provider 精确搜索失败时，AI 根据原始文件名和目录上下文纠正标题并重新搜索

## 3. 测试用例

### 3.1 新建: tests/test_tier2_correct.py（8个用例）

TC-01 2160P分辨率误识别: original_filename=美丽人生.2160P.mkv, path_segments=电影
  期望: corrected_title=美丽人生, corrected_year=null, certainty=medium, reason含分辨率

TC-02 标题内含数字: original_filename=银翼杀手2049.2017.BluRay.2160p.mkv
  期望: corrected_title=银翼杀手2049, corrected_year=2017, certainty=high

TC-03 标题就是数字2012: original_filename=2012.2009.1080p.BluRay.mkv
  期望: corrected_title=2012, corrected_year=2009, certainty=high

TC-04 标题就是数字2046: original_filename=2046.2004.720p.mkv
  期望: corrected_title=2046, corrected_year=2004, certainty=high

TC-05 无年份剧集: original_filename=jinji.S01E02.mp4
  期望: corrected_title=jinji, media_type_hint=tv, certainty=medium, suggestion非空

TC-06 标准命名: original_filename=xXx.Return.of.Xander.Cage.2017.1080p.BluRay.x264-CHDWEB.mkv
  期望: corrected_title=xXx: Return of Xander Cage, corrected_year=2017, certainty=high

TC-07 AI异常兜底: mock _do_call 返回非法JSON
  期望: certainty=low, reason含AI 解析失败

TC-08 自定义提示词生效: config中 ai_assist.prompt_match_assist 有自定义值
  期望: tier2_correct 使用自定义提示词而非默认值

### 3.2 新建: tests/test_tier2_match_engine.py（4个用例）

TC-09 high certainty: mock tier2_correct返回certainty=high
  期望: _tier2_context_match返回MatchResult(match_level=CONTEXT_PASS)

TC-10 medium certainty: mock tier2_correct返回certainty=medium
  期望: _tier2_context_match返回MatchResult(match_level=NEEDS_CONFIRM), confirm_reason非空

TC-11 low certainty: mock tier2_correct返回certainty=low
  期望: _tier2_context_match返回MatchResult(match_level=NEEDS_CONFIRM), 不搜Provider

TC-12 AI异常: mock tier2_correct抛异常
  期望: _tier2_context_match返回None（进入第三级）

### 3.3 回归测试

pytest tests/test_match_engine.py tests/test_scrape_preview_job.py tests/test_review_decision_v2.py tests/test_import_flow_services.py -x

## 4. 验收清单

1. python -m compileall -q media_importer
2. pytest tests/ --ignore=tests/test_*_ui.py --ignore=tests/test_frontend_*.py --ignore=tests/test_scrape_ui.py -x
3. 模拟测试输入 美丽人生.2160P.mkv -> 第二级 AI 纠正 -> medium -> NEEDS_CONFIRM
4. 模拟测试输入 银翼杀手2049.2017.BluRay.2160p.mkv -> 第二级 AI 纠正 -> high -> CONTEXT_PASS
5. 前端匹配辅助卡片说明已更新