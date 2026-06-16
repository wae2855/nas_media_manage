# User Prompt 纳入统一管理方案（修订版 v4）

## 一、背景

当前架构：AI 提示词分两层：

| 层 | 存储 | 可配置 |
|----|------|:---:|
| system_prompt | PromptDefaults + config → UI 可编辑 | ✅ |
| user_prompt | 硬编码在各调用点 | ❌ |

用户在前台 AI 配置提示词界面只能看到 system_prompt，看不到 user_prompt。不符合"所有提示词统一管理"的规范。

## 二、架构分析

### 2.1 user_prompt 的实际构成

以 `tier2_correct` 为例，user_prompt 包含三类内容：

| 类型 | 内容 | 性质 |
|------|------|------|
| 指令模板 | 判定规则、is_valid/certainty 定义、候选利用规则、网络搜索优先 | 用户可定制 |
| 输出格式契约 | JSON schema（字段名、类型、示例） | 不可配置（代码解析依赖） |
| 数据上下文 | original_filename, clean_title, candidates_text, tier1_hint 等 | 代码动态生成，不可被用户删除 |

### 2.2 风险

1. 用户误删 candidates_text → AI 看不到候选列表
2. 修改输出 JSON 字段名 → 代码解析崩溃
3. 删除 tier1_hint → 回到 bug：AI 不知道搜索已失败

### 2.3 推荐方案：指令模板 + 输出格式 + 数据上下文 三层分离

最终 user_content 由代码按以下顺序组装：

```
指令模板（可配置）+ 输出格式契约（不可配置）+ 数据上下文（不可配置）
```

例外：当系统处于 **legacy 兼容模式**（见 §4.0.2）时，user_content = 数据上下文（不含 instruction 和 output_format），因旧 system_prompt 已包含完整规则和格式。

**关键约束**：
- 数据上下文始终由代码拼装并追加到末尾，用户无法删除或修改
- 输出格式契约由代码追加在指令模板和数据上下文之间，用户无法修改字段名
- 指令模板只允许调整判定逻辑、风格、额外约束，不允许改变字段名和 JSON 结构

### 2.4 指令模板边界规则

| 允许用户调整 | 不允许用户调整 |
|------------|-------------|
| 判定规则的措辞和语气 | JSON 字段名（is_valid, selected_candidate_id 等） |
| 添加额外约束（如"reason 用中文"） | JSON 结构（嵌套层级、字段顺序） |
| 调整步骤顺序 | 输出格式说明（由代码追加） |

## 三、涉及的 6 个场景

| # | 场景 | system_prompt | user_prompt 现状 |
|---|------|:---:|------|
| 1 | tier2_correct 匹配辅助 | ✅ PromptDefaults.MATCH_ASSIST | ❌ _llm_match_assist.py:105-183 硬编码 |
| 2 | scrape 维度补全 | ✅ PromptDefaults.DIMENSION_SUPPLEMENT | ❌ llm_scraper.py:149-162 硬编码 |
| 3 | scrape_with_context 维度映射 | ✅ PromptDefaults.DIMENSION_MAPPING | ❌ llm_scraper.py:180-196 硬编码 |
| 4 | scrape_series 剧集补全 | ✅ PromptDefaults.DIMENSION_SUPPLEMENT | ❌ llm_scraper.py:212 硬编码 |
| 5 | scrape_series_with_context 剧集映射 | ✅ PromptDefaults.DIMENSION_MAPPING | ❌ llm_scraper.py:222-227 硬编码 |
| 6 | source_clean 源目录清理 | ✅ PromptDefaults.SOURCE_CLEAN | ❌ cleaner.py:312-314 硬编码 |

**不纳入**：
- extract_title：user_prompt 由调用方 filename_cleaner.py 动态构建（传文件名列表），无固定模板。UI 上该场景的提示词 tab 只显示 system_prompt 编辑区，标注"此场景无指令模板"。
- prompt_builder.py：已清理死代码，只剩维度数据容器功能。

## 四、设计方案

### 4.0 迁移策略：两类 system_prompt 的不同处理

PromptDefaults 中的 system_prompt 分两类，三态兼容：

#### 4.0.1 场景分类

| 类型 | 场景 | 迁移方式 |
|------|------|---------|
| 短 system_prompt | TITLE_CLEAN, MATCH_ASSIST | 不变。instruction 单独承载规则 |
| 长 system_prompt | DIMENSION_MAPPING, DIMENSION_SUPPLEMENT, SOURCE_CLEAN | 缩短为角色描述。规则抽到 instruction，格式抽到代码追加层 |

#### 4.0.2 三态兼容策略

给用户区分三种配置状态：

| 状态 | system_prompt 值 | instruction 值 | 行为 |
|------|:---:|:---:|------|
| ① 未自定义 | 默认（短） | 默认 instruction | **标准模式**：user_content = instruction + output_format + data_context |
| ② 自定义过 system_prompt | 用户值（≠ 旧默认） | 默认（同上） | **legacy 模式**：user_content = data_context（不追加 instruction 和 output_format） |
| ③ 设了 instruction | 任意 | 用户显式值 | **标准模式**：用用户 instruction |

**判断逻辑**（长 system_prompt 场景）：不依赖"非空判断"（`config.yaml` 默认就有旧值），改为**值对比**：

```
def is_legacy(self) -> bool:
    return user_value != "" and user_value != old_default_value
```

实现方式：PromptDefaults 同时保留新旧两版默认值，新默认值用于标准模式，旧默认值用于 legacy 检测。

```
class PromptDefaults:
    DIMENSION_MAPPING = "你是影视维度映射助手。（新短版）"
    _LEGACY_DIMENSION_MAPPING = "你是影视维度映射助手。请根据 Provider ...（旧长版）"
```

#### 4.0.3 PromptAssemblyPlan 简化控制

调用点改为统一入口，由 `_assemble_prompt()` 根据 legacy 状态决定是否追加 instruction 和 output_format：

```
def _assemble_prompt(instruction: str, data_context: str,
                     output_format: str, is_legacy: bool) -> str:
    if is_legacy:
        return data_context
    return "\n\n".join([instruction, output_format, data_context])
```

### 4.1 PromptDefaults 变更

#### 4.1.1 长 system_prompt 缩短 + 保留旧值

DIMENSION_SUPPLEMENT / DIMENSION_MAPPING / SOURCE_CLEAN 3 个常量缩短为纯角色描述（1 句）。旧值保留为 `_LEGACY_*` 私有常量，供 `PromptResolver` 做值对比。

#### 4.1.2 新增指令模板常量

4 个 `*_INSTRUCTION` 常量，**逐字从源码中提取**，提取规则：
- `MATCH_ASSIST_INSTRUCTION`：从 `_llm_match_assist.py:131-168` 提取（判定规则三步骤 + 网络搜索优先 + 关键要求），去掉 `## 输出要求` 段
- `DIMENSION_SUPPLEMENT_INSTRUCTION`：从 `llm_scraper.py:149-162` 中提取指令语义
- `DIMENSION_MAPPING_INSTRUCTION`：从 `llm_scraper.py:180-196` 中提取指令语义
- `SOURCE_CLEAN_INSTRUCTION`：从当前 `SOURCE_CLEAN` 常量中提取【分析原则】和【判断标准】段，去掉【输出格式】段

迁移验收：单元测试中对比 `*_INSTRUCTION` 常量与源码原文，断言关键短语存在（如 `is_valid=false`、`corrected_title`、`网络搜索`、`保守原则`）。

#### 4.1.3 get_all() 扩展

返回值新增 `instructions` 字段，前端通过 `/api/config/prompt-defaults` 获取。

DESCRIPTIONS 新增 4 条 instruction 描述，注明"不含输出 JSON 格式（由系统固定追加）"。

### 4.2 PromptResolver 扩展

4 个 instruction 字段 + 4 个 getter。长 system_prompt 场景的 getter 采用值对比机制：

```
def get_dimension_supplement_instruction(self) -> str:
    if self.prompt_dimension_supplement_instruction:
        return self.prompt_dimension_supplement_instruction       # ③显式设了
    val = self.prompt_dimension_supplement
    if val and val != PromptDefaults._LEGACY_DIMENSION_SUPPLEMENT:
        return ""                                                 # ②legacy 模式
    return PromptDefaults.DIMENSION_SUPPLEMENT_INSTRUCTION        # ①新配置
```

from_config() 同步新增 4 行读取配置路径。

### 4.3 代码调用点改造

统一调用模式：

```
instruction = self.prompt_resolver.get_xxx_instruction()
is_legacy = (instruction == "")
data_context = _build_xxx_context(...)
output_format = _build_xxx_output_format(...) if not is_legacy else ""
user_content = _assemble_prompt(instruction, data_context, output_format, is_legacy)
```

#### 4.3.1 tier2_correct（匹配辅助）

- `_build_match_assist_context()`（不可配置）：待匹配文件信息 + 目录上下文 + Provider 候选 + Step 1 搜索结果
- `_build_match_assist_output_format()`（不可配置）：is_valid/certainty JSON schema

#### 4.3.2 scrape / scrape_series（维度补全）

- `_build_dimension_data_context()`（不可配置）：视频文件名 + 字幕文件名 + 动态维度列表
- `_build_dimension_output_format()`（不可配置）：title_cn/title_en/dimensions JSON schema

#### 4.3.3 scrape_with_context / scrape_series_with_context（维度映射）

同 4.3.2 模式，data_context 额外包含 Provider 上下文 JSON。

#### 4.3.4 source_clean（源目录清理）—— 修复 pre-existing bug

问题：当前 cleaner.py 将 SOURCE_CLEAN 同时用作 system_prompt 和 user_prompt 前缀，导致内容重复发送。
改造后：短 system_prompt + instruction + output_format + data_context。legacy 用户跳过 instruction 和 output_format。

### 4.4 配置项映射

| 配置路径 | 说明 | 类型 |
|---------|------|------|
| ai_assist.prompt_match_assist | Tier 2 system_prompt | 已有 |
| ai_assist.prompt_match_assist_instruction | Tier 2 指令模板 | 新增 |
| ai_search.prompt_dimension_supplement | 维度补全 system_prompt | 已有 |
| ai_search.prompt_dimension_supplement_instruction | 维度补全指令模板 | 新增 |
| ai_assist.prompt_dimension_mapping | 维度映射 system_prompt | 已有 |
| ai_assist.prompt_dimension_mapping_instruction | 维度映射指令模板 | 新增 |
| ai_assist.prompt_source_clean | 源目录清理 system_prompt | 已有 |
| ai_assist.prompt_source_clean_instruction | 源目录清理指令模板 | 新增 |

向后兼容性：所有新增字段默认空字符串。长 system_prompt 场景通过值对比（与 `_LEGACY_*` 常量比较，而非空值判断）区分标准模式和 legacy 模式。

### 4.5 前端

| 文件 | 改动 |
|------|------|
| webui/index.html | 4 个 *_instruction tab 编辑区 + extract_title tab 标注 |
| webui/js/cinema-config-payloads.js | 4 个 instruction 字段读写 |
| webui/js/cinema-config.js | 独立的重置指令模板按钮 |
| webui/js/cinema-config-ai.js | resetActivePrompt() 支持 `defaults.instructions` 新来源 |
| webui/js/cinema-directory-loader.js | 4 个 instruction 字段配置回填 |
| webui/js/cinema-reel.js | 提示词状态汇总覆盖 instruction 字段 |

## 五、改动范围

### 5.1 后端（8 个文件）

| 文件 | 改动 |
|------|------|
| features/prompts/defaults.py | 新增+修改：4 个 *_INSTRUCTION 常量；3 个 _LEGACY_* 旧值常量；3 个长 system_prompt 缩短；get_all() 返回加 instructions |
| features/scraping/prompt_resolver.py | 新增：4 个字段 + 4 个值对比 getter + from_config() 加行 |
| core/config_view.py | 新增：ai_assist/ai_search 各加 instruction 字段 |
| scraper/_llm_match_assist.py | 重构：拆出 _build_context() + _build_output_format() 纯函数 + _assemble_prompt() |
| scraper/llm_scraper.py | 重构：scrape/scrape_with_context/scrape_series/scrape_series_with_context 改用新模式 |
| features/source_cleaning/cleaner.py | 重构+修复：修复 system/user 重复；短 system_prompt + instruction + output_format |
| scraper/_llm_client_impl.py | 无需修改（仅读取 self.prompt_builder.dimensions） |
| config/config.yaml | 将 3 个长 system_prompt 注释掉或改为短值 |

### 5.2 文档

ai-prompt-design.md + INDEX.md 同步更新为四层架构（system + instruction + output_format + data_context）。

## 六、测试清单

### 6.1 单元测试（test_user_prompt_management.py 或拆入已有测试文件）

| # | 测试名 | 断言 |
|---|--------|------|
| UT-1 | test_long_system_prompts_are_short | `DIMENSION_SUPPLEMENT` / `DIMENSION_MAPPING` / `SOURCE_CLEAN` 只含角色描述，不含 JSON 格式关键字、不含多维规则 |
| UT-2 | test_short_system_prompts_unchanged | `TITLE_CLEAN` / `MATCH_ASSIST` 常量值与改造前一致 |
| UT-3 | test_legacy_constants_preserved | `_LEGACY_DIMENSION_SUPPLEMENT` / `_LEGACY_DIMENSION_MAPPING` / `_LEGACY_SOURCE_CLEAN` 等于改造前的旧默认值 |
| UT-4 | test_instruction_constants_non_empty | `MATCH_ASSIST_INSTRUCTION` / `DIMENSION_SUPPLEMENT_INSTRUCTION` / `DIMENSION_MAPPING_INSTRUCTION` / `SOURCE_CLEAN_INSTRUCTION` 非空 |
| UT-5 | test_instruction_key_phrases | 每个 `*_INSTRUCTION` 常量包含关键短语（见附录 A） |
| UT-6 | test_get_all_has_instructions_field | `PromptDefaults.get_all()` 返回 dict 包含 `"instructions"` 键，含 4 个 key |
| UT-7 | test_get_all_has_descriptions_field | `DESCRIPTIONS` 包含方案涉及的 5 个 system prompt + 4 个 instruction |
| UT-8 | test_resolver_new_config_returns_instruction | PromptResolver 无任何自定义值时，`get_dimension_mapping_instruction()` 返回 `PromptDefaults.DIMENSION_MAPPING_INSTRUCTION` |
| UT-9 | test_resolver_legacy_returns_empty | `prompt_dimension_mapping = _LEGACY_DIMENSION_MAPPING`，`prompt_dimension_mapping_instruction = ""` → 返回 `""` |
| UT-10 | test_resolver_custom_system_returns_empty | `prompt_dimension_mapping = "用户自定义的长规则"` (≠ _LEGACY_*) → 返回 `""` |
| UT-11 | test_resolver_explicit_instruction_wins | `prompt_dimension_mapping_instruction = "用户自定义指令"` → 返回 `"用户自定义指令"`（无论 system_prompt 值） |
| UT-12 | test_assemble_prompt_standard_mode | `_assemble_prompt("指令", "数据", "格式", False)` → `"指令\n\n格式\n\n数据"` |
| UT-13 | test_assemble_prompt_legacy_mode | `_assemble_prompt("指令", "数据", "格式", True)` → `"数据"`（不含 instruction 和 output_format） |

### 6.2 集成测试（test_user_prompt_integration.py）

| # | 场景 | 配置状态 | 断言 |
|---|------|---------|------|
| IT-1 | tier2_correct | 新配置 | system_prompt 为短 MATCH_ASSIST；user_content 含 instruction + JSON schema + data_context；JSON schema 含 `is_valid` / `selected_candidate_id` |
| IT-2 | tier2_correct | legacy | system_prompt 为旧长值；user_content 仅含 data_context（文件信息、候选列表、tier1 结果）；不含重复 JSON schema |
| IT-3 | scrape | 新配置 | user_content 含维度列表（名称、可选值）；含 JSON schema（`title_cn`/`dimensions`） |
| IT-4 | scrape | legacy | user_content 仅含视频文件名和字幕列表；不含 instruction 和 output_format |
| IT-5 | scrape_with_context | 新配置 | data_context 含 Provider 上下文 JSON + 维度列表 |
| IT-6 | source_clean | 新配置 | system_prompt 为短 SOURCE_CLEAN（纯角色描述）；user_prompt 的 `【分析原则】` 仅出现一次 |
| IT-7 | source_clean | 修复验证 | `system_prompt` 和 `user_prompt` 不重复包含 `【分析原则】` / `【判断标准】` / JSON 格式 |
| IT-8 | scrape_series | 新配置 | 与 scrape 一致断言，但 media_type 固定为 tv |
| IT-9 | 自定义 instruction | match_assist | user_content 含用户修改的短语；JSON schema 仍由代码固定追加 |

### 6.3 有效提示词包一致性测试

所有 6 个场景在三种配置状态下，通过以下共享断言：

- **去重断言**：`(system_prompt + user_prompt).count("关键规则短语") == 1`
- **完整性断言**：有效提示词包含 `"只返回 JSON"` 或 `"解释文字"` 且仅一次（legacy 模式：由 system_prompt 承载；标准模式：由 output_format 承载）
- **数据完整性**：data_context 包含文件名、候选列表、维度列表（如适用）

### 6.4 UI 测试

| # | 测试 |
|---|------|
| UI-1 | AI 配置提示词页面出现 4 个 `*_instruction` 编辑区（对应 4 个纳入场景） |
| UI-2 | extract_title tab 只显示 system_prompt 编辑区，不显示 instruction 编辑区，标注"此场景无指令模板" |
| UI-3 | instruction 编辑区清空后保存，再加载，`/api/config/prompt-defaults` 返回默认 instruction 用于回填 |
| UI-4 | 重置指令模板按钮独立于 system_prompt 的重置按钮，分别从 `defaults.prompts` 和 `defaults.instructions` 读取默认值 |
| UI-5 | 提示词状态汇总（cinema-reel.js）正确反映 instruction 自定义状态 |

### 6.5 回归测试

- `python -m pytest tests/ --ignore=tests/test_frontend_ui.py --ignore=tests/test_scrape_ui.py --ignore=tests/test_ai_config_ui.py` 全部通过（当前 635 passed）
- `python -m pytest tests/test_architecture_guards.py` 全部通过

### 6.6 附录 A：指令模板关键短语清单

| 常量 | 必须包含的关键短语 |
|------|-------------------|
| `MATCH_ASSIST_INSTRUCTION` | `is_valid`、`certainty`、`selected_candidate_id`、`corrected_title`、`网络搜索`、`clean_title` |
| `DIMENSION_SUPPLEMENT_INSTRUCTION` | `联网搜索`、`返回空字符串`、`人工补全` |
| `DIMENSION_MAPPING_INSTRUCTION` | `Provider`、`映射`、`标准值`、`编造` |
| `SOURCE_CLEAN_INSTRUCTION` | `分析原则`、`保守原则`、`判断标准`、`保留`、`删除` |

## 七、风险与缓解

| 风险 | 缓解 |
|------|------|
| 值对比误判（旧默认 vs 用户自定义） | 旧值逐字存入 PromptDefaults._LEGACY_* 私有常量；单元测试覆盖全等比较 |
| legacy 模式下 output_format 跳过不彻底 | 集成测试断言有效提示词包不包含重复 JSON schema |
| 指令模板逐字迁移遗漏关键短语 | 迁移时用 pytest 对比 *_INSTRUCTION 常量与源码原文，断言关键短语存在 |
| 老 config.yaml 默认值时智能回退不生效 | 值对比判断而非空值判断；3 个长 system_prompt 在 config.yaml 中注释掉 |

## 八、与当前重构计划的关系

- docs/plans/2026-06-15-ai-config-restructure-plan.md：已将 system_prompt 纳入 PromptResolver。本方案是其延续。
- prompt_builder.py 死代码已清理完成（635 测试通过）。
- source_clean system/user 重复 bug 随本方案一同修复。
