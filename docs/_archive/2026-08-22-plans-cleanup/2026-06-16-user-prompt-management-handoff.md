# Handoff：User Prompt 纳入统一管理

## 任务

把硬编码在各调用点的 user_prompt 纳入 PromptDefaults + PromptResolver 统一管理，使前台 UI 可配置完整 AI 提示词。

## 前置条件

- 仓库基线：所有测试通过（635 passed, 8 deselected）
- Python 3.12.13，`.venv/` 虚拟环境
- 项目根目录：`/Users/wangwei/Documents/code/nas_media_manage`
- 方案文档：`docs/plans/2026-06-16-user-prompt-management-plan.md`
- **每次改完 Python 文件后必须：清除 `__pycache__`，重启服务**

## LSP 状态

以下 LSP 错误已在本轮修复（类型注解补充 `Optional`）：`_llm_client_impl.py` 和 `classification_rules.py`。

以下 LSP 错误是遗留的，与本次任务无关：
- `_llm_client_impl.py:74`：`"choice" is possibly unbound`（linter 误判，for 循环第一行即赋值）
- `scrape.py`：mixin 属性未识别（需架构重构，不在范围）
- `test_ai_config_ui.py`：`sync_playwright` 可能未绑定（测试文件条件导入）

## 核心架构：三层分离 + 三态兼容

### 三层模型

最终 user_content = `instruction + output_format + data_context`

| 层 | 内容 | 可配置 |
|----|------|:---:|
| instruction | 判定规则、is_valid/certainty 定义 | ✅ 用户可编辑 |
| output_format | JSON schema 字段名/类型/示例 | ❌ 代码固定追加 |
| data_context | 文件名、候选列表、维度列表等 | ❌ 代码动态生成 |

**例外（legacy 模式）**：当用户自定义过旧长 system_prompt 时，user_content = data_context（不含 instruction 和 output_format）。

### 三态兼容

| 状态 | system_prompt | instruction | 行为 |
|------|:---:|:---:|------|
| ① 未自定义 | 短默认值 | 默认 instruction | user_content = instruction + output_format + data_context |
| ② 自定义过 system_prompt | 用户值（≠ 旧默认） | 默认 | user_content = data_context（跳过 instruction 和 output_format） |
| ③ 设了 instruction | 任意 | 用户显式值 | user_content = 用户 instruction + output_format + data_context |

**判断逻辑**：用**值对比**而非空值判断。`_LEGACY_*` 常量保存改造前的旧默认值，getter 比较当前配置值是否等于 `_LEGACY_*` 来决定是否处于 legacy 模式。

---

## 分步实施

### 第 1 步：PromptDefaults 变更

**文件**：`media_importer/features/prompts/defaults.py`

**1a. 保留旧值常量**

在类中新增 3 个私有常量，值为改造前的当前默认值（从当前源码中复制）：

```python
class PromptDefaults:
    # 复制当前 DIMENSION_SUPPLEMENT 的完整值作为旧值
    _LEGACY_DIMENSION_SUPPLEMENT = """你是影视维度补充助手。Provider 没有返回足够的维度信息...（当前完整值）"""
    
    # 复制当前 DIMENSION_MAPPING 的完整值作为旧值
    _LEGACY_DIMENSION_MAPPING = """你是影视维度映射助手。请根据 Provider 返回的结构化数据...（当前完整值）"""
    
    # 复制当前 SOURCE_CLEAN 的完整值作为旧值
    _LEGACY_SOURCE_CLEAN = """你是"影音库AI智能整理"系统的源目录清理助手...（当前完整值）"""
```

**1b. 缩短 3 个长 system_prompt**

把 `DIMENSION_SUPPLEMENT`、`DIMENSION_MAPPING`、`SOURCE_CLEAN` 改为纯角色描述（1-2 句）：

```python
DIMENSION_SUPPLEMENT = "你是影视维度补充助手。基于文件名和字幕文件名补全 Provider 缺失的维度值。"
DIMENSION_MAPPING = "你是影视维度映射助手。根据 Provider 上下文把复杂字段映射为系统要求的标准维度值。"
SOURCE_CLEAN = "你是影音库AI智能整理系统的源目录清理助手。判断源目录中哪些文件应清理、哪些应保留。"
```

**1c. 新增 4 个 instruction 常量**

逐字从源码中提取（详见方案 §4.1.2）：

- `MATCH_ASSIST_INSTRUCTION`：从 `_llm_match_assist.py:131-168` 提取，去掉 `## 输出要求` 段
- `DIMENSION_SUPPLEMENT_INSTRUCTION`：从 `llm_scraper.py:149-162` 提取指令语义
- `DIMENSION_MAPPING_INSTRUCTION`：从 `llm_scraper.py:180-196` 提取指令语义
- `SOURCE_CLEAN_INSTRUCTION`：从当前 `SOURCE_CLEAN` 常量中提取 `【分析原则】` 和 `【判断标准】`，去掉 `【输出格式】`

**1d. 扩展 get_all()**

新增 `"instructions"` 键，返回 4 个 `*_INSTRUCTION` 常量。
DESCRIPTIONS 新增 4 条 instruction 描述（注明"不含输出 JSON 格式（由系统固定追加）"）。

### 第 2 步：PromptResolver 扩展

**文件**：`media_importer/features/scraping/prompt_resolver.py`

**2a. 新增 4 个字段**

```python
prompt_match_assist_instruction: str = ""
prompt_dimension_supplement_instruction: str = ""
prompt_dimension_mapping_instruction: str = ""
prompt_source_clean_instruction: str = ""
```

**2b. 新增 4 个 getter（关键：值对比）**

`get_match_assist_instruction()` 简单回退（短 system_prompt 场景）：

```python
def get_match_assist_instruction(self) -> str:
    return self.prompt_match_assist_instruction or PromptDefaults.MATCH_ASSIST_INSTRUCTION
```

`get_dimension_supplement_instruction()` / `get_dimension_mapping_instruction()` / `get_source_clean_instruction()` 值对比逻辑：

```python
def get_dimension_supplement_instruction(self) -> str:
    if self.prompt_dimension_supplement_instruction:
        return self.prompt_dimension_supplement_instruction       # ③ 用户显式设了
    val = self.prompt_dimension_supplement
    if val and val != PromptDefaults._LEGACY_DIMENSION_SUPPLEMENT:
        return ""                                                  # ② legacy：用户改了 system_prompt
    return PromptDefaults.DIMENSION_SUPPLEMENT_INSTRUCTION         # ① 未自定义
```

**2c. from_config() 加行**

```python
prompt_match_assist_instruction=ai_assist.prompt_match_assist_instruction or "",
prompt_dimension_supplement_instruction=ai_search.prompt_dimension_supplement_instruction or "",
prompt_dimension_mapping_instruction=ai_assist.prompt_dimension_mapping_instruction or "",
prompt_source_clean_instruction=ai_assist.prompt_source_clean_instruction or "",
```

### 第 3 步：config_view.py 扩展

**文件**：`media_importer/core/config_view.py`

给 `AIConfig` / `AISearchConfig` dataclass 各加 2-3 个 `*_instruction` 字段，并在 `from_dict()` 中读取。

### 第 4 步：代码调用点改造

#### 4a. _llm_match_assist.py（tier2_correct）

拆出两个纯函数：

```python
def _build_match_assist_context(original_filename, clean_title, year, path_context) -> str:
    """输出：## 待匹配文件信息 + ## 目录上下文 + ## Provider 候选 + ## Step 1 搜索结果"""
    # 从当前 user_parts 中提取这些部分

def _build_match_assist_output_format() -> str:
    """输出：## 输出要求 + JSON schema（is_valid/certainty 字段名和示例）"""
```

改造 `_tier2_correct_impl`：
```python
instruction = self.prompt_resolver.get_match_assist_instruction()
is_legacy = (instruction == "")
data_context = _build_match_assist_context(original_filename, clean_title, year, path_context)
output_format = "" if is_legacy else _build_match_assist_output_format()
user_content = _assemble_prompt(instruction, data_context, output_format, is_legacy)
```

#### 4b. llm_scraper.py（scrape / scrape_with_context / scrape_series / scrape_series_with_context）

类似模式。额外：`_build_dimension_data_context()` 需要注入动态维度列表（从 `self.prompt_builder.dimensions`）。

维度列表格式：
```
当前需要判断的维度：
1. {label}（{name}）: [{values}] — {ai_hint}
2. ...
```

#### 4c. cleaner.py（source_clean）

**修复 pre-existing bug**：当前 `_call_llm()` 把 `self.ai_prompt` 同时用作 system_prompt 和 user_prompt 前缀。改造：

```python
def _build_cleaner_prompt(self, dir_path, files):
    instruction = self.prompt_resolver.get_source_clean_instruction()
    is_legacy = (instruction == "")
    files_desc = json.dumps(files, ensure_ascii=False, indent=2)
    data_context = f"【待分析目录】\n目录: {dir_path}\n文件列表:\n{files_desc}"
    output_format = "" if is_legacy else _build_source_clean_output_format()
    return _assemble_prompt(instruction, data_context, output_format, is_legacy)

def _call_llm(self, prompt):
    return self.llm.call_with_prompt(
        system_prompt=self.prompt_resolver.get_source_clean_prompt(),  # 短 SOURCE_CLEAN
        user_prompt=prompt,  # 由 _build_cleaner_prompt 组装
        scene="source_clean",
    )
```

`_build_source_clean_output_format()`：
```
## 输出要求
请严格按以下JSON格式返回，不要添加任何解释文字：
{"analysis": "...", "decisions": {"文件名": {"action": "keep或delete", "reason": "判断理由"}}}
```

#### 4d. 通用 _assemble_prompt() 函数

```python
def _assemble_prompt(instruction: str, data_context: str,
                     output_format: str = "", is_legacy: bool = False) -> str:
    if is_legacy:
        return data_context
    parts = [p for p in [instruction, output_format, data_context] if p]
    return "\n\n".join(parts)
```

### 第 5 步：前端

- `webui/index.html`：每个现有 prompt tab 增加 instruction textarea 编辑区；extract_title tab 标注"此场景无指令模板"
- `webui/js/cinema-config-payloads.js`：payload 增加 4 个 instruction 字段
- `webui/js/cinema-config-ai.js`：`resetActivePrompt()` 支持从 `defaults.instructions` 读取默认值
- `webui/js/cinema-directory-loader.js`：加载配置时回填 4 个 instruction textarea
- `webui/js/cinema-reel.js`：提示词状态汇总覆盖 instruction 字段
- `webui/js/cinema-config.js`：独立的重置指令模板按钮

### 第 6 步：config.yaml

将 3 个长 system_prompt 的值注释掉（或改为短值），使新架构生效。

### 第 7 步：测试

详见方案 §六 测试清单。重点：
- UT-9/10/11：值对比三态测试
- UT-12/13：_assemble_prompt 的 legacy/standard 行为
- IT-7：source_clean 不重复
- 有效提示词包去重测试：`(system_prompt + user_prompt).count("关键规则短语") == 1`

---

## 关键提醒

1. **值对比是核心**：不要用 `if self.prompt_dimension_mapping:` 判断 legacy 模式，因为 `config.yaml` 默认就有旧值。必须用 `!= PromptDefaults._LEGACY_DIMENSION_MAPPING`。
2. **legacy 模式跳过两次**：instruction 为空 AND output_format 为空。`_assemble_prompt(legacy=True)` 只返回 data_context。
3. **维度列表是动态的**：`_build_dimension_data_context()` 必须从 `self.prompt_builder.dimensions` 读取当前维度列表并格式化注入。
4. **output_format 不可配置**：每个场景的 JSON schema 始终由代码固定追加（legacy 模式除外），用户无法修改字段名。
5. **禁止修改 config/config.yaml 以外的配置文件**（`.config`、`.env`、`opencode.json` 等）。
