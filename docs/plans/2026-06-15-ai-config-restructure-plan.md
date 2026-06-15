# 2026-06-15 AI 配置界面三区域改造方案 — 详细执行手册

> **文档用途**：本方案已敲定细节，拆分为可在 Phase 1/2/3 独立交付的任务单元（T1.x / T2.x / T3.x）。每个任务给出文件路径、改动锚点、改动前后对比和验收标准。低能力模型可按任务编号顺序执行，每个任务完成后跑对应测试命令验证。

---

## 0. 已决策项汇总

| # | 决策项 | 结论 |
|---|--------|------|
| 1 | 场景命名 | 用用户拍板的命名（见 §1） |
| 2 | 默认配置策略 | 代码不做硬编码 fallback；全走 `config_loader.setdefault` |
| 3 | 大多数场景只配 primary，不配 fallback | 无 fallback 时调用失败按现状抛错，由调用方 try/except 处理 |
| 4 | `DIMENSION_MAPPING` / `DIMENSION_SUPPLEMENT` 默认值 | 用运行时详细版（已被生产验证） |
| 5 | `tier2_judge` 死代码 | 删除 |
| 6 | `dimension_supplement` 双归属 | 归一到 `ai_search` |
| 7 | `config-build.js:5-22` 老 `updateAiConfigStatus` | 删除 |
| 8 | 两条调用链 Provider 重复搜索 | **降为低优先级 follow-up**（见 §6） |
| 9 | 提示词"恢复默认"作用范围 | 当前 tab |
| 10 | API Key 区保存按钮 | 区域统一一个（非 tab 级） |
| 11 | AI 调用日志 | 统一结构化日志（`ai.scene.*` 前缀），不写数据库；默认 INFO 记录提示词摘要（前 200 字符），DEBUG 记录完整提示词；可通过 `ai_assist.log_prompt=false` 关闭 |
| 12 | 多模型 fallback 共享实现 | 抽出 `_run_with_strategy_impl` 作为唯一共享入口，`_retry_with_fallback_impl`（返回 dict）和 `_call_with_retry_impl`（返回 raw）都走它，区别只在 `on_success` 回调。所有日志埋点、多模型 fallback、错误分类都在共享方法里（Phase 1 已实施） |
| 13 | 场景 3/4 走 raw 入口 | `_extract_title_impl` / `_tier2_correct_impl` 改用 `_call_with_retry_impl`（而非 `_retry_with_fallback_impl`），因为它们需要 raw 文本自行解析（前者返回纯标题字符串，后者自己解析 JSON），不能走强制 JSON 解析的 `_parse_response_impl`（Phase 1 已实施） |
| 14 | `SceneStrategyResolver` 兜底 | 当 `model_sequence` 返回空列表时，`_run_with_strategy_impl` 兜底到 `["ai_search"]` 并输出 `ai.scene.strategy_missing` warning 日志，便于排查"配置未生效"。生产路径（`load_config.setdefault` 已覆盖）不会触发，主要为测试和绕过 `load_config` 的路径提供防御性兜底（Phase 1 已实施） |
| 15 | `tier2_judge` 测试清理 | 删除 `_tier2_judge_impl` 时需同步删除 3 个调用它的测试（执行模型已确认并清理） |

---

## 1. 5 个场景命名与说明（前端展示文案）

> **使用位置**：前端场景策略区的标签 + tooltip + 提示词区的功能说明折叠区。所有文案从此处单一事实源复制，禁止散落。

### 1.1 场景命名表

| # | 场景 key | 场景名（中文） | 场景名（英文/代码用） |
|---|---------|---------------|---------------------|
| 1 | `dimension_supplement` | 刮削缺失补充 | dimension_supplement |
| 2 | `dimension_mapping` | 刮削结果归类 | dimension_mapping |
| 3 | `title_clean` | 文件标题清洗 | title_clean |
| 4 | `match_assist` | 影视名AI推测 | match_assist |
| 5 | `source_clean` | 源目录清理分析 | source_clean |

### 1.2 场景说明文案（前端展示用）

| 场景 | 说明文案 |
|------|---------|
| 刮削缺失补充 | Provider 刮削结果缺失的维度，由 AI 联网搜索补充。建议优先使用【AI 联网搜索增强】准确度更高。触发位置：Provider 命中但维度不全，且场景 2（刮削结果归类）失败后的兜底路径。 |
| 刮削结果归类 | Provider 刮削到的原始字段，由 AI 归类映射到本地维度体系，便于后续入库处理。触发位置：Provider 命中但维度不全时的主路径。 |
| 文件标题清洗 | 结合 AI 从脏文件名中清洗出干净标题，然后传递给 Provider 重新刮削。**触发频率较高**（单文件可能多次触发）。建议优先使用【AI 辅助】控制成本。触发条件：①正则清洗时发现年份可疑（文件名有多个 4 位数字、年份是未来值等）；②Provider 有结果但命中等级为 L4（标题对但年份不符）/L6（模糊匹配多候选）/L7（完全不匹配）；③Provider 完全无结果。 |
| 影视名AI推测 | 通过文件名 + 文件夹路径 + 同级文件名，由 AI 综合推测最可能的影视名。建议优先使用【AI 联网搜索增强】准确度更高。触发位置：Tier1 Provider 精确匹配失败时进入 Tier2 推测。 |
| 源目录清理分析 | 由 AI 分析源目录下每个子目录的文件构成，推测哪些目录是可以清理的。与刮削流程无关，由独立的源目录清理 API 触发。 |

### 1.3 场景在刮削流程中的位置图

```
入库任务启动
    │
    ├─ 调用链 A：scraper.scrape() ─────────────────────────┐
    │     ├─ [可选] 场景 3 文件标题清洗                     │
    │     ├─ Provider 搜索                                  │ 这些都会触发 AI
    │     ├─ [可选] 场景 2 刮削结果归类（维度不全时）       │
    │     └─ [兜底] 场景 1 刮削缺失补充（场景 2 失败时）    │
    │                                                       │
    ├─ 调用链 B：match_engine.match() ────────────────────┤
    │     ├─ Tier1：正则清洗 + Provider 精确匹配（无 AI）  │
    │     ├─ Tier2：场景 4 影视名AI推测（Tier1 失败时）    │
    │     └─ Tier3：用户手动确认（Tier2 失败时，无 AI）    │
    │                                                       │
    └─ 独立 API：source-cleaner/* ─────────────────────────┘
          └─ 场景 5 源目录清理分析（与刮削零耦合）
```

---

## 2. 默认配置值

### 2.1 `ai_scene_strategy` 默认值（由 `config_loader.setdefault` 写入）

```yaml
ai_scene_strategy:
  dimension_supplement:        # 场景 1：刮削缺失补充
    primary: ai_search         # 必填
    fallback: ""               # 空 = 不 fallback
  dimension_mapping:           # 场景 2：刮削结果归类
    primary: ai_assist
    fallback: ""
  title_clean:                 # 场景 3：文件标题清洗
    primary: ai_assist         # 触发频率高，用便宜的模型控制成本
    fallback: ""
  match_assist:                # 场景 4：影视名AI推测
    primary: ai_search
    fallback: ""
  source_clean:                # 场景 5：源目录清理分析
    primary: ai_assist
    fallback: ""
```

### 2.2 fallback 空值处理规则

- `fallback: ""` 或未填 → `SceneStrategyResolver.model_sequence(scene)` 返回 `[primary]` 单元素列表
- 调用失败后没有下一个模型可切换 → 抛出最后一个错误
- 各场景调用方的现有 try/except（见 §3.4 兜底表）原样保留，负责把错误转化为降级行为

---

## 3. 详细任务清单

### Phase 1：后端基础设施（共 15 个任务）

---

#### T1.1 迁移 `PromptDefaults` 真默认值

**文件**：`media_importer/features/prompts/defaults.py`

**改动**：把分散在 4 处的真默认值全部迁到本文件，让 `PromptDefaults` 成为唯一事实源。

**改动前**（当前 `features/prompts/defaults.py` 内容是精简版，与运行时不一致）

**改动后**：

```python
class PromptDefaults:
    # 来源：scraper/_llm_match_assist.py:11-12 内联字面量
    TITLE_CLEAN = """...（复制 _llm_match_assist.py:11-12 的真值）..."""

    # 来源：scraper/_llm_match_assist.py:40-41 内联字面量
    MATCH_ASSIST = """...（复制 _llm_match_assist.py:40-41 的真值）..."""

    # 来源：features/prompts/prompt_builder.py:6-68 DEFAULT_SYSTEM_PROMPT
    DIMENSION_MAPPING = """...（复制 prompt_builder.DEFAULT_SYSTEM_PROMPT）..."""

    # 来源：features/prompts/prompt_builder.py:6-68 DEFAULT_SYSTEM_PROMPT（与上同源）
    DIMENSION_SUPPLEMENT = """...（同 DIMENSION_MAPPING）..."""

    # 来源：features/source_cleaning/cleaner.py:15-40 AI_SYSTEM_PROMPT
    SOURCE_CLEAN = """...（复制 cleaner.AI_SYSTEM_PROMPT 25 行版）..."""

    # 新增：功能说明文案（供前端展示）
    DESCRIPTIONS = {
        "prompt_title_clean": "文件标题清洗：从脏文件名中清洗出干净标题...",
        "prompt_match_assist": "影视名AI推测：综合文件名+路径+同级文件推测影视名...",
        "prompt_dimension_mapping": "刮削结果归类：把 Provider 字段映射到本地维度...",
        "prompt_dimension_supplement": "刮削缺失补充：联网搜索补充缺失维度...",
        "prompt_source_clean": "源目录清理分析：分析目录文件构成给出清理建议...",
    }

    @classmethod
    def get_all(cls):
        return {
            "prompts": {
                "prompt_title_clean": cls.TITLE_CLEAN,
                "prompt_match_assist": cls.MATCH_ASSIST,
                "prompt_dimension_mapping": cls.DIMENSION_MAPPING,
                "prompt_dimension_supplement": cls.DIMENSION_SUPPLEMENT,
                "prompt_source_clean": cls.SOURCE_CLEAN,
            },
            "descriptions": cls.DESCRIPTIONS,
        }
```

**验收**：
- `python -c "from media_importer.features.prompts import PromptDefaults; print(PromptDefaults.get_all())"` 输出含 `prompts` 和 `descriptions` 两层
- 5 个 prompt 值与代码使用处的真兜底字面量**完全一致**

---

#### T1.2 改造 `PromptResolver`（留空返回默认值）

**文件**：`media_importer/features/scraping/prompt_resolver.py:52-70`

**改动前**：

```python
def get_title_clean_prompt(self) -> str | None:
    return self.prompt_title_clean or None
```

**改动后**：

```python
def get_title_clean_prompt(self) -> str:
    return self.prompt_title_clean or PromptDefaults.TITLE_CLEAN

def get_match_assist_prompt(self) -> str:
    return self.prompt_match_assist or PromptDefaults.MATCH_ASSIST

def get_dimension_mapping_prompt(self) -> str:
    return self.prompt_dimension_mapping or PromptDefaults.DIMENSION_MAPPING

def get_dimension_supplement_prompt(self) -> str:
    return self.prompt_dimension_supplement or PromptDefaults.DIMENSION_SUPPLEMENT

def get_source_clean_prompt(self) -> str:
    return self.prompt_source_clean or PromptDefaults.SOURCE_CLEAN
```

**验收**：
- 所有 `get_*_prompt()` 返回类型从 `str | None` 变为 `str`
- 单测：留空时返回对应 `PromptDefaults.XXX`

---

#### T1.3 改造 5 个 prompt 使用点（删除内联兜底）

**文件清单与改动**：

| 文件 | 行号 | 改动前 | 改动后 |
|------|------|--------|--------|
| `scraper/_llm_match_assist.py:10-12` | `system_prompt = self.prompt_resolver.get_title_clean_prompt() or ("你是一个影视标题提取助手...")` | `system_prompt = self.prompt_resolver.get_title_clean_prompt()` |
| `scraper/_llm_match_assist.py:39-41` | `system_prompt = self.prompt_resolver.get_match_assist_prompt() or ("你是一个影视标题纠正助手...")` | `system_prompt = self.prompt_resolver.get_match_assist_prompt()` |
| `scraper/_llm_match_assist.py:101-150` | `_tier2_judge_impl` 整段（死代码） | **整段删除** |
| `scraper/llm_scraper.py:145-146` | `custom_prompt = ...; system_prompt = custom_prompt if custom_prompt else self.prompt_builder._build_system_prompt()` | `system_prompt = self.prompt_resolver.get_dimension_supplement_prompt()` |
| `scraper/llm_scraper.py:179-181` | `custom_prompt = ...; system_prompt = custom_prompt if custom_prompt else self.prompt_builder._build_system_prompt_with_provider(...)` | `system_prompt = self.prompt_resolver.get_dimension_mapping_prompt()` |
| `scraper/llm_scraper.py:196-197` | 同 145-146（series 版） | 同上 |
| `scraper/llm_scraper.py:211-213` | 同 179-181（series 版） | 同上 |
| `features/source_cleaning/cleaner.py:59` | `self.ai_prompt = self.view.ai_assist.prompt_source_clean or AI_SYSTEM_PROMPT` | `self.ai_prompt = self.prompt_resolver.get_source_clean_prompt()`（同时确保 `__init__` 中已实例化 `self.prompt_resolver`） |

**额外清理**：
- 删除 `features/source_cleaning/cleaner.py:15-40` 的 `AI_SYSTEM_PROMPT` 常量（已迁到 `PromptDefaults`）
- 删除 `features/prompts/prompt_builder.py:70-115` 的 `TIER2_CORRECT_PROMPT`（0 引用）

**验收**：
- `python -m compileall -q media_importer` 编译通过
- `grep -r "你是一个影视标题" media_importer/` 无结果（所有内联字面量已迁走）
- `grep -r "AI_SYSTEM_PROMPT" media_importer/` 仅在 `__init__.py` 有兼容导出，否则无结果

---

#### T1.4 新增 `ai_scene_strategy` 配置 schema

**文件**：`media_importer/core/config_view.py`

**改动**：新增 `AiSceneStrategyConfig` dataclass 和 `SceneModelConfig` 子结构。

```python
@dataclass
class SceneModelConfig:
    primary: str = ""
    fallback: str = ""

@dataclass
class AiSceneStrategyConfig:
    dimension_supplement: SceneModelConfig = field(default_factory=SceneModelConfig)
    dimension_mapping: SceneModelConfig = field(default_factory=SceneModelConfig)
    title_clean: SceneModelConfig = field(default_factory=SceneModelConfig)
    match_assist: SceneModelConfig = field(default_factory=SceneModelConfig)
    source_clean: SceneModelConfig = field(default_factory=SceneModelConfig)

    @classmethod
    def from_dict(cls, data: dict) -> "AiSceneStrategyConfig":
        result = cls()
        for key in ("dimension_supplement", "dimension_mapping",
                    "title_clean", "match_assist", "source_clean"):
            section = data.get(key, {}) or {}
            setattr(result, key, SceneModelConfig(
                primary=str(section.get("primary", "")),
                fallback=str(section.get("fallback", "")),
            ))
        return result
```

在 `ConfigView` 类中新增字段：

```python
class ConfigView:
    def __init__(self, config: dict):
        ...
        self.ai_scene_strategy = AiSceneStrategyConfig.from_dict(
            config.get("ai_scene_strategy", {})
        )
```

**验收**：
- 单测：`ConfigView.from_dict({})` 不抛错，5 个场景字段都有默认空值
- 单测：完整 yaml 解析后 `view.ai_scene_strategy.match_assist.primary == "ai_search"`

---

#### T1.5 `config_loader.setdefault` 注入默认值

**文件**：`media_importer/core/config_loader.py:124-209`（`load_config` 函数内）

**改动**：在现有 `setdefault` 块附近新增：

```python
# AI 场景策略默认值
ai_strategy = config.setdefault("ai_scene_strategy", {})
DEFAULT_SCENE_STRATEGY = {
    "dimension_supplement": {"primary": "ai_search", "fallback": ""},
    "dimension_mapping": {"primary": "ai_assist", "fallback": ""},
    "title_clean": {"primary": "ai_assist", "fallback": ""},
    "match_assist": {"primary": "ai_search", "fallback": ""},
    "source_clean": {"primary": "ai_assist", "fallback": ""},
}
for scene, defaults in DEFAULT_SCENE_STRATEGY.items():
    section = ai_strategy.setdefault(scene, {})
    section.setdefault("primary", defaults["primary"])
    section.setdefault("fallback", defaults["fallback"])
```

**验收**：
- 单测：`load_config({})` 后 `config["ai_scene_strategy"]["match_assist"]["primary"] == "ai_search"`
- 单测：用户配置 `{ai_scene_strategy: {match_assist: {primary: "ai_assist"}}}` 时不被覆盖

---

#### T1.6 `config_validator` 校验

**文件**：`media_importer/core/config_validator.py:152-407`（`validate_config` 函数内）

**改动**：新增场景策略校验：

```python
# 校验 ai_scene_strategy
VALID_MODELS = {"ai_assist", "ai_search"}
REQUIRED_SCENES = {"dimension_supplement", "dimension_mapping",
                   "title_clean", "match_assist", "source_clean"}
ai_strategy = config.get("ai_scene_strategy", {})
for scene in REQUIRED_SCENES:
    section = ai_strategy.get(scene, {})
    primary = section.get("primary", "")
    fallback = section.get("fallback", "")
    if not primary:
        errors.append(f"ai_scene_strategy.{scene}.primary 不能为空")
    elif primary not in VALID_MODELS:
        errors.append(f"ai_scene_strategy.{scene}.primary 必须是 {VALID_MODELS} 之一")
    if fallback and fallback not in VALID_MODELS:
        errors.append(f"ai_scene_strategy.{scene}.fallback 必须是 {VALID_MODELS} 之一或留空")
```

**验收**：
- 单测：`primary=""` 报错
- 单测：`primary="invalid"` 报错
- 单测：`fallback=""` 通过
- 单测：`fallback="ai_assist"` 通过

---

#### T1.7 新增 `SceneStrategyResolver`

**文件（新建）**：`media_importer/features/scraping/scene_strategy.py`

```python
from media_importer.core.config_view import ConfigView

class SceneStrategyResolver:
    SCENE_KEYS = (
        "dimension_supplement",
        "dimension_mapping",
        "title_clean",
        "match_assist",
        "source_clean",
    )

    def __init__(self, view: ConfigView):
        self.view = view

    def model_sequence(self, scene: str) -> list[str]:
        """返回 [primary] 或 [primary, fallback]，过滤空值和重复。"""
        if scene not in self.SCENE_KEYS:
            raise ValueError(f"未知场景: {scene}")
        section = getattr(self.view.ai_scene_strategy, scene)
        result = [section.primary] if section.primary else []
        if section.fallback and section.fallback not in result:
            result.append(section.fallback)
        return result
```

**验收**：
- 单测：`primary=ai_search, fallback=""` → `["ai_search"]`
- 单测：`primary=ai_assist, fallback=ai_search` → `["ai_assist", "ai_search"]`
- 单测：`primary=ai_search, fallback=ai_search` → `["ai_search"]`（去重）
- 单测：未知 scene 抛 `ValueError`

---

#### T1.8 抽出 `_run_with_strategy_impl` 共享实现（多模型 fallback + 日志）

**状态**：✅ Phase 1 已完成，实际实现比原 plan 更优雅（见决策 12）

**文件**：`media_importer/scraper/_llm_client_impl.py`

**实际实现要点**（执行模型重构后）：

1. **抽出 `_run_with_strategy_impl(self, system_prompt, user_content, scene, scenario, on_success)`** 作为共享入口，参数 `on_success(raw, cfg_key, model, attempt)` 是单次成功回调，决定返回 dict 还是 raw。
2. **`_retry_with_fallback_impl`** 改为薄包装，`on_success` 调 `_parse_response_impl` 转 dict。
3. **`_call_with_retry_impl`** 是新增的薄包装，`on_success` 直接返回 raw 字符串。
4. **`_resolve_connection(cfg_key)`** 模块级函数：`ai_assist` → fast_model 配置 + `default_use_search=False`；`ai_search` → 主模型配置 + `default_use_search=True`。
5. **兜底**（决策 14）：`model_sequence` 返回空时兜底到 `["ai_search"]`，并输出 `ai.scene.strategy_missing` warning 日志。
6. **日志埋点**（决策 11）：全部 8 种事件都在 `_run_with_strategy_impl` 内，不在 `_do_call_impl` 重复埋点。
7. **`use_fast` 兼容**：`_retry_with_fallback_impl` 保留 `use_fast` 参数用于老入口，`True → scene="dimension_mapping"`，`False → scene="dimension_supplement"`。

**配套改动**：`LLMScraper.__init__`（`scraper/llm_scraper.py:29-54`）已注入：

```python
from media_importer.features.scraping.scene_strategy import SceneStrategyResolver
self.scene_strategy = SceneStrategyResolver(cfg_view)
```

**验收**：
- ✅ 单测：mock `_do_call` 第一次抛 `LLMApiError`、第二次返回成功，断言重试了 `max_retries` 次后成功
- ✅ 单测：`scene` 配置 `primary=ai_assist, fallback=ai_search`，primary 全部重试失败后切到 fallback
- ✅ 单测：`scene` 配置 `primary=ai_assist, fallback=""`，primary 全部失败后抛最后一个错误
- ✅ 单测：兜底场景输出 `ai.scene.strategy_missing` warning
- ✅ 单测：日志事件齐全（见 `tests/test_ai_call_logging.py` 10 个用例）

---

#### T1.9 `LLMScraper` 新增 `call_with_prompt`（供 SourceCleaner 使用）

**文件**：`media_importer/scraper/llm_scraper.py`

```python
def call_with_prompt(self, system_prompt: str, user_prompt: str, scene: str) -> str:
    """通用 LLM 调用入口（供 SourceCleaner 等非刮削场景使用）。

    复用 _retry_with_fallback_impl 的重试、错误分类、多模型 fallback 能力。
    """
    return self._retry_with_fallback(
        system_prompt=system_prompt,
        user_content=user_prompt,
        scene=scene,
        scenario=None,
    )
```

**验收**：
- 单测：mock `_do_call` 返回固定字符串，`call_with_prompt` 返回相同字符串

---

#### T1.10 改造 5 个 scrape 调用点（传入 scene，移除 use_fast）

**状态**：✅ Phase 1 已完成

**文件**：`media_importer/scraper/llm_scraper.py` + `media_importer/scraper/_llm_match_assist.py`

**实际改动清单**（决策 12 + 决策 13）：

| 方法 | 改动后调用入口 | scene |
|------|---------------|-------|
| `LLMScraper.scrape()` | `_retry_with_fallback_impl` | `dimension_supplement` |
| `LLMScraper.scrape_with_context()` | `_retry_with_fallback_impl` | `dimension_mapping` |
| `LLMScraper.scrape_series()` | `_retry_with_fallback_impl` | `dimension_supplement` |
| `LLMScraper.scrape_series_with_context()` | `_retry_with_fallback_impl` | `dimension_mapping` |
| `_extract_title_impl`（场景 3） | **`_call_with_retry_impl`**（决策 13） | `title_clean` |
| `_tier2_correct_impl`（场景 4） | **`_call_with_retry_impl`**（决策 13） | `match_assist` |

**关键设计（决策 13）**：场景 3/4 必须走 `_call_with_retry_impl`（返回 raw），不能走 `_retry_with_fallback_impl`（返回 dict）。原因：
- 场景 3 `_extract_title_impl` 返回纯标题字符串，不是 JSON
- 场景 4 `_tier2_correct_impl` 自己解析 JSON（兼容 think 标签/markdown 代码块/字段补全）
- `_retry_with_fallback_impl` 内部调 `_parse_response_impl` 会强制 JSON 解析，破坏这两个场景

两个入口共享 `_run_with_strategy_impl`，所以多模型 fallback、重试、错误分类、日志埋点完全一致。

**验收**：
- ✅ 编译通过
- ✅ 单测：每个调用点都按场景策略选模型
- ✅ 单测：场景 3/4 的多模型 fallback 完整可用（共享 `_run_with_strategy_impl`）

---

#### T1.11 改造 `SourceCleaner` 走 `LLMScraper`

**文件**：`media_importer/features/source_cleaning/cleaner.py`

**改动 1：`__init__` 增加 LLMScraper 实例**

```python
def __init__(self, config):
    self.view = ConfigView.from_dict(config)
    self.config = config
    # 新增
    from media_importer.scraper.llm_scraper import LLMScraper
    from media_importer.features.scraping.prompt_resolver import PromptResolver
    self.llm = LLMScraper(config)
    self.prompt_resolver = PromptResolver.from_config(config)
    self.ai_prompt = self.prompt_resolver.get_source_clean_prompt()
    # 删除原有 urllib 相关字段（如 self.timeout = 60）
```

**改动 2：删除 `_call_llm` 旧实现（`cleaner.py:336-356`），改为薄包装**

```python
def _call_llm(self, prompt: str) -> str:
    return self.llm.call_with_prompt(
        system_prompt=self.ai_prompt,
        user_prompt=prompt,
        scene="source_clean",
    )
```

**改动 3：`_ai_analyze_directory`（`cleaner.py:315-330`）简化**

```python
def _ai_analyze_directory(self, dir_path, file_items):
    if not self.view.ai_assist.api_key and not self.view.ai_search.api_key:
        return {}
    try:
        prompt = self._build_cleaner_prompt(dir_path, file_items)
        raw = self._call_llm(prompt)
        return self._parse_ai_response(raw)
    except Exception as e:
        logger.warning(f"AI 分析目录失败 {dir_path}: {e}")
        return {}
```

> 注意：原来 `_call_llm` 接收 `(api_base, api_key, model, prompt)` 4 个参数，新版只接收 `prompt` 1 个参数，连接信息由 `LLMScraper` 内部按场景策略解析。

**验收**：
- 编译通过
- 单测：mock `LLMScraper.call_with_prompt` 返回固定 JSON 字符串，`SourceCleaner._call_llm` 返回相同字符串
- 单测：`source_clean` 场景策略配 `primary=ai_assist, fallback=ai_search`，primary 失败后切到 fallback

---

#### T1.12 `/api/config/prompt-defaults` 返回升级

**文件**：`media_importer/api/prompt_handlers.py:7-9`

**改动前**：

```python
def _prompt_defaults(self, ...):
    return json_response(200, "ok", PromptDefaults.get_all())
```

**改动后**：返回结构不变，但 `get_all()` 的内容已升级（见 T1.1）。

**验收**：
- API 测：`GET /api/config/prompt-defaults` 返回 `{code: 200, data: {prompts: {...}, descriptions: {...}}}`

---

#### T1.13 `/api/config/section` 支持新 section

**文件**：`media_importer/api/config_handlers.py`（处理 `/config/section` 的 handler）

**改动**：新增三个 section 的处理分支：

| section 名 | 数据结构 | 持久化到 yaml 路径 |
|-----------|---------|------------------|
| `ai_apikey` | `{ai_assist: {...}, ai_search: {...}}` | 合并写入 `ai_assist` 和 `ai_search` |
| `ai_prompts` | `{ai_assist: {prompt_*}, ai_search: {prompt_*}}` | 仅写入 prompt 字段，保留其他字段 |
| `ai_scene_strategy` | `{dimension_supplement: {primary, fallback}, ...}` | 写入 `ai_scene_strategy` |

**注意**：`ai_apikey` 和 `ai_prompts` 是为前端三区域手风琴拆分新增的逻辑 section，物理 yaml 仍写入 `ai_assist` / `ai_search`。

**API Key 脱敏**：必须保留 `preserveApiKey` 逻辑（参考 `webui/js/cinema-config-payloads.js:207-211`），输入框留空时回填已保存值或 `***`。

**验收**：
- API 测：POST `{section: "ai_scene_strategy", data: {...}}` 后 GET `/config` 能读到新值
- API 测：POST `{section: "ai_apikey", data: {ai_assist: {api_key: ""}}}` 时 api_key 不会被覆盖为空

---

#### T1.14 修复 `connectivity_handlers` 场景归属歧义

**文件**：`media_importer/api/connectivity_handlers.py:9-21`

**改动**：把 `dimension_supplement` 从 `AI_ASSIST_SCENARIOS` 中删除，只保留在 `AI_SEARCH_SCENARIOS`。

**验收**：
- 单测：`dimension_supplement` 只归属 `AI_SEARCH_SCENARIOS`

---

#### T1.15 AI 调用统一日志（结构化、便于排查）

**目标**：每次 AI 调用都记录**调用逻辑、场景、模型、耗时、提示词**到日志文件（不写数据库），便于后续排查。触发频率高的场景（如场景 3）日志可读性要强。

**文件**：
- `media_importer/scraper/_llm_client_impl.py`（核心埋点位置）
- `media_importer/scraper/_llm_match_assist.py`（场景 3/4 入口补充日志）
- `media_importer/features/source_cleaning/cleaner.py`（场景 5 入口补充日志）
- `media_importer/core/logger.py`（如不存在则用 stdlib `logging.getLogger("media_importer.ai")`）

**日志规范**：

统一使用 `logging.getLogger("media_importer.ai")`，所有 AI 相关日志带前缀 `ai.scene.xxx`，结构化为 key=value 格式便于 grep。

| 事件 | 级别 | 日志内容 | 触发位置 |
|------|------|---------|---------|
| 场景开始 | INFO | `ai.scene.start scene=<scene> model=<cfg_key> attempt=1/<max_retries> prompt_len=<len>` | `_run_with_strategy_impl` 进入每个模型循环时 |
| 单次尝试开始 | DEBUG | `ai.scene.attempt scene=<scene> model=<cfg_key> attempt=<n>` | `_do_call_impl` 入口 |
| 单次尝试成功 | INFO | `ai.scene.success scene=<scene> model=<cfg_key> attempt=<n> elapsed_ms=<ms>` | `_run_with_strategy_impl` try 块成功后 |
| 单次尝试失败将重试 | WARNING | `ai.scene.retry scene=<scene> model=<cfg_key> attempt=<n> error=<type> reason=<msg> next_attempt_in=<s>` | try 块 except 后，且非最后一次重试 |
| 切换 fallback 模型 | WARNING | `ai.scene.fallback scene=<scene> from=<cfg_key> to=<next_cfg_key> reason=all_retries_failed` | 模型循环切换到下一个时 |
| 场景彻底失败 | ERROR | `ai.scene.failure scene=<scene> last_model=<cfg_key> last_error=<type> reason=<msg> total_elapsed_ms=<ms>` | 全部重试 + fallback 都失败后 |
| 提示词完整记录 | DEBUG | `ai.scene.prompt scene=<scene> system_prompt=<full_text> user_prompt=<full_text>` | `_run_with_strategy_impl` 内（仅 DEBUG 级别） |
| 提示词摘要（默认开） | INFO | `ai.scene.prompt_summary scene=<scene> system_prompt_len=<n> system_prompt_preview=<前200字符> user_prompt_len=<n> user_prompt_preview=<前200字符>` | `_run_with_strategy_impl` 内（受 `ai_assist.log_prompt` 控制） |
| 配置缺失兜底 | WARNING | `ai.scene.strategy_missing scene=<scene> fallback_to=ai_search reason=ai_scene_strategy_not_configured` | `model_sequence` 返回空时（决策 14） |
| 业务上下文 | INFO | `ai.scene.business scene=<scene> trigger=<触发条件> ...` | 场景 3/4/5 入口处 |

**状态**：✅ Phase 1 已完成

**关键实现**（埋点位置见决策 11 + 12）：

所有 8 种日志事件统一埋在 `_run_with_strategy_impl`（`media_importer/scraper/_llm_client_impl.py:214-304`），**不在 `_do_call_impl` 重复埋点**。这样：
- `_retry_with_fallback_impl`（场景 1/2）和 `_call_with_retry_impl`（场景 3/4/5）共享同一段日志代码
- 每次调用只产生一条 `prompt_summary` 和一条 `prompt` 日志（避免重复）
- 日志带 attempt 维度（`attempt=1/2`），便于追踪每次重试

**埋点结构**：

```python
def _run_with_strategy_impl(self, system_prompt, user_content, scene, scenario, on_success):
    strategy = self.scene_strategy.model_sequence(scene)
    if not strategy:
        logger.warning(f"ai.scene.strategy_missing scene={scene} fallback_to=ai_search ...")
        strategy = ["ai_search"]

    for idx, cfg_key in enumerate(strategy):
        for attempt in range(self.max_retries):
            logger.info(f"ai.scene.start scene={scene} model={cfg_key} attempt={attempt+1}/{self.max_retries} ...")
            if log_prompt_enabled:
                logger.info(f"ai.scene.prompt_summary scene={scene} ... preview={system_prompt[:200]!r} ...")
            logger.debug(f"ai.scene.prompt scene={scene} ... system_prompt={system_prompt!r} ...")
            try:
                raw = self._do_call(...)
                logger.info(f"ai.scene.success scene={scene} model={cfg_key} attempt={attempt+1} elapsed_ms=...")
                return on_success(raw, cfg_key, model, attempt + 1)
            except (LLMScrapeError, LLMApiError, LLMWebSearchError) as e:
                if attempt < self.max_retries - 1:
                    logger.warning(f"ai.scene.retry scene={scene} ... error=... next_attempt_in=...")
                    time.sleep(self.retry_delay)
                else:
                    logger.warning(f"ai.scene.model_exhausted scene={scene} ... last_error=...")
        if idx < len(strategy) - 1:
            logger.warning(f"ai.scene.fallback scene={scene} from={cfg_key} to={strategy[idx+1]} ...")
    logger.error(f"ai.scene.failure scene={scene} last_model=... total_elapsed_ms=...")
    raise last_error
```

**配置开关**（已实施）：

```yaml
ai_assist:
  log_prompt: true   # 默认 true，记录 prompt_summary（INFO）；prompt（DEBUG）由 logging 配置控制
```

`config_view.AiAssistConfig` 已新增 `log_prompt: bool = True` 字段。`_run_with_strategy_impl` 根据此字段决定是否记录提示词。

**业务入口日志**（场景 3/4/5 入口处）：

```python
# _extract_title_impl 入口（场景 3）
logger.info(f"ai.scene.business scene=title_clean trigger=year_suspect_or_low_match prompt_len=...")

# _tier2_correct_impl 入口（场景 4）
logger.info(f"ai.scene.business scene=match_assist trigger=tier1_no_match filename=... clean_title=...")

# _ai_analyze_directory 入口（场景 5）
ai_logger.info(f"ai.scene.business scene=source_clean trigger=manual dir=... file_count=...")
```

> 注：场景 3 的 trigger 当前是合并标签 `year_suspect_or_low_match`，未区分 3 种细分条件（year_suspect / L4/L6/L7 / no_provider_result）。如需细分，可在 `_do_ai_clean` 调用方传入具体 trigger（列为 Phase 3 优化项）。

**日志示例（一次成功的场景 4 调用）**：

```
2026-06-15 10:23:15 INFO  media_importer.ai - ai.scene.start scene=match_assist model=ai_search attempt=1/2 system_prompt_len=1234 user_prompt_len=567
2026-06-15 10:23:15 INFO  media_importer.ai - ai.scene.prompt_summary scene=match_assist model=glm-4-flash system_prompt_len=1234 system_prompt_preview='你是一个影视标题纠正助手...' user_prompt_len=567 user_prompt_preview='原始文件名：某某某.mkv\n路径上下文：...'
2026-06-15 10:23:18 INFO  media_importer.ai - ai.scene.success scene=match_assist model=ai_search attempt=1 elapsed_ms=3142
```

**日志示例（primary 失败 fallback 成功）**：

```
2026-06-15 10:23:20 WARNING media_importer.ai - ai.scene.retry scene=match_assist model=ai_assist attempt=1 elapsed_ms=1200 error=LLMApiError reason=HTTP 429 rate limited next_attempt_in=2s
2026-06-15 10:23:23 WARNING media_importer.ai - ai.scene.retry scene=match_assist model=ai_assist attempt=2 elapsed_ms=1100 error=LLMApiError reason=HTTP 429 rate limited next_attempt_in=2s
2026-06-15 10:23:25 WARNING media_importer.ai - ai.scene.model_exhausted scene=match_assist model=ai_assist attempts=2 last_error=LLMApiError
2026-06-15 10:23:25 WARNING media_importer.ai - ai.scene.fallback scene=match_assist from=ai_assist to=ai_search reason=all_retries_failed
2026-06-15 10:23:25 INFO  media_importer.ai - ai.scene.start scene=match_assist model=ai_search attempt=1/2 system_prompt_len=1234 user_prompt_len=567
2026-06-15 10:23:28 INFO  media_importer.ai - ai.scene.success scene=match_assist model=ai_search attempt=1 elapsed_ms=3142
```

**额外日志（场景 3/4/5 入口）**：

在 `_extract_title_impl` / `_tier2_correct_impl` / `_ai_analyze_directory` 入口处增加业务上下文日志，便于关联：

```python
# _extract_title_impl 入口
logger.info(f"ai.scene.business scene=title_clean trigger=year_suspect filename={filename!r}")

# _tier2_correct_impl 入口
logger.info(f"ai.scene.business scene=match_assist trigger=tier1_no_match filename={original_filename!r} path={video_path!r}")

# _ai_analyze_directory 入口
logger.info(f"ai.scene.business scene=source_clean trigger=manual dir={dir_path!r} file_count={len(file_items)}")
```

**验收**：
- 单测：mock `_do_call` 立即成功，断言 logger 输出 `ai.scene.start` + `ai.scene.success`
- 单测：mock `_do_call` 抛 `LLMApiError` 两次，断言 logger 输出 `ai.scene.retry` × N + `ai.scene.failure`
- 单测：primary 失败 + fallback 成功，断言 logger 输出 `ai.scene.fallback` + `ai.scene.success`
- 单测：`log_prompt=false` 时不输出 `prompt_summary` 日志
- 集成测：跑一个完整入库任务，日志中能 grep 到至少 5 个场景的 `ai.scene.start` 记录
- 手工验证：日志能通过 `grep "ai.scene"` 提取所有 AI 调用记录

---

### Phase 2：前端 UI（共 6 个任务）

---

#### T2.1 补全 AI demo 模态 HTML（修复 broken）

**文件**：`media_importer/webui/index.html:842`

**改动**：把空容器替换为完整的两个模态 DOM：

```html
<div id="ai-demo-modals-container">
  <!-- AI 辅助测试模态 -->
  <div id="ai-assist-demo-modal" class="demo-modal" style="display:none;">
    <div class="demo-modal-content">
      <div class="demo-modal-header">
        <h3>AI 辅助模拟测试</h3>
        <button id="btn-ai-assist-demo-close" class="demo-modal-close">×</button>
      </div>
      <div class="demo-modal-body">
        <div class="demo-scenario-list">
          <!-- 场景卡片，data-demo-scenario 属性 -->
          <div class="demo-scenario-card" data-demo-scenario="title_clean">...</div>
          <div class="demo-scenario-card" data-demo-scenario="match_assist">...</div>
          <div class="demo-scenario-card" data-demo-scenario="dimension_mapping">...</div>
        </div>
        <div id="ai-assist-demo-result" class="demo-result-area" style="display:none;">
          <div class="demo-result-header">
            <span id="ai-assist-demo-result-title"></span>
            <span id="ai-assist-demo-result-elapsed"></span>
          </div>
          <div id="ai-assist-demo-result-body"></div>
        </div>
        <div id="ai-assist-demo-loading" class="demo-loading" style="display:none;">
          <div class="spinner"></div>
        </div>
      </div>
    </div>
  </div>

  <!-- AI 联网搜索增强测试模态（结构同上） -->
  <div id="ai-scrape-demo-modal" class="demo-modal" style="display:none;">
    ...（同上，id 改为 ai-scrape-demo-*）...
  </div>
</div>
```

**CSS 已就绪**（`cinema-pages-7.css:430-484`），无需改动。

**验收**：
- UI 测：点击【AI 辅助测试】按钮，模态正常弹出（不抛 `Cannot read properties of null`）
- UI 测：点击【AI 联网搜索增强测试】按钮，模态正常弹出
- UI 测：点击关闭按钮，模态隐藏

---

#### T2.2 重排为 3 个手风琴区域

**文件**：`media_importer/webui/index.html:539-693`

**改动**：删除现有 AI 辅助卡片 + AI 联网搜索增强卡片两段，替换为三个 `.config-collapse-card`：

```html
<section class="config-stage-panel" data-config-panel="ai">

  <!-- 区域 1：AI 的 API Key 配置 -->
  <article class="form-card form-card-full config-collapse-card" id="ai-apikey-card">
    <!-- 见 T2.3 -->
  </article>

  <!-- 区域 2：AI 提示词配置 -->
  <article class="form-card form-card-full config-collapse-card" id="ai-prompts-card">
    <!-- 见 T2.4 -->
  </article>

  <!-- 区域 3：AI 场景设置 -->
  <article class="form-card form-card-full config-collapse-card" id="ai-scene-strategy-card">
    <!-- 见 T2.5 -->
  </article>

</section>
```

**默认折叠**：3 个 card 默认都不加 `.open` 类。

**验收**：
- UI 测：进入 AI 配置 stage，3 个 card 默认全部折叠
- UI 测：点击每个 card 的 header，独立展开/折叠（不互相影响）

---

#### T2.3 区域 1：API Key 配置（页签化）

**位置**：`#ai-apikey-card` 内部

**结构**：

```html
<div class="config-collapse-header" data-collapse-toggle="ai-apikey-body">
  <div class="config-collapse-header-left">
    <span class="config-collapse-chevron">▸</span>
    <div>
      <b>AI 的 API Key 配置</b>
      <span class="config-collapse-status" id="ai-apikey-status">未配置</span>
    </div>
  </div>
  <div class="config-collapse-header-right">
    <button class="btn-primary" data-config-save="ai-apikey">保存</button>
  </div>
</div>
<div class="config-collapse-body" id="ai-apikey-body">
  <!-- 页签 -->
  <div class="prompt-tabs" data-apikey-tabs="ai">
    <div class="prompt-tab active" data-apikey-tab="ai_assist">AI 辅助</div>
    <div class="prompt-tab" data-apikey-tab="ai_search">AI 联网搜索增强</div>
  </div>

  <!-- AI 辅助 tab 内容 -->
  <div class="apikey-tab-content active" data-apikey-content="ai_assist">
    <!-- 复用现有字段：cfg-ai_assist-base_url / model / api_key -->
    <!-- 高级选项 details -->
    <!-- 操作行：【测试连通性】data-llm-test="inline" + 【模拟测试】#btn-ai-assist-demo -->
  </div>

  <!-- AI 联网搜索增强 tab 内容 -->
  <div class="apikey-tab-content" data-apikey-content="ai_search">
    <!-- 复用现有字段：cfg-ai_search-enabled / provider / model / search_type / api_key -->
    <!-- 高级选项 details -->
    <!-- 操作行：【测试连通性】data-llm-test="inline" + 【模拟测试】#btn-ai-scrape-demo -->
  </div>
</div>
```

**注意**：所有字段 id 保留（如 `cfg-ai_assist-base_url`），与 `cinema-directory-loader.js:88-162` 的回填逻辑一致。

**验收**：
- UI 测：点击【AI 辅助】tab，显示 AI 辅助字段；点击【AI 联网搜索增强】tab，切换显示
- UI 测：两个 tab 都有【测试连通性】+【模拟测试】按钮
- UI 测：点击【测试连通性】弹出 toast（成功/失败）
- UI 测：点击【模拟测试】弹出对应模态（T2.1）
- UI 测：点击【保存】，POST `/api/config/section` body 含 `section: "ai_apikey"`

---

#### T2.4 区域 2：提示词配置（5 tab + 功能说明折叠）

**位置**：`#ai-prompts-card` 内部

**结构**：

```html
<div class="config-collapse-header" data-collapse-toggle="ai-prompts-body">
  ...<button data-config-save="ai-prompts">保存</button>...
</div>
<div class="config-collapse-body" id="ai-prompts-body">
  <div class="prompt-tabs" data-prompt-tabs="ai-all">
    <div class="prompt-tab active" data-prompt-tab="prompt_title_clean">文件标题清洗</div>
    <div class="prompt-tab" data-prompt-tab="prompt_match_assist">影视名AI推测</div>
    <div class="prompt-tab" data-prompt-tab="prompt_dimension_mapping">刮削结果归类</div>
    <div class="prompt-tab" data-prompt-tab="prompt_dimension_supplement">刮削缺失补充</div>
    <div class="prompt-tab" data-prompt-tab="prompt_source_clean">源目录清理分析</div>
  </div>

  <!-- 每个 tab 内容（以 prompt_title_clean 为例） -->
  <div class="prompt-tab-content active" data-prompt-content="prompt_title_clean">
    <div class="prompt-edit-grid">
      <div class="prompt-edit-main">
        <textarea id="cfg-ai_assist-prompt_title_clean" rows="15"></textarea>
      </div>
      <div class="prompt-edit-side">
        <details class="prompt-help-disclosure">
          <summary>功能说明</summary>
          <div class="prompt-help-body">
            <!-- 从 /api/config/prompt-defaults 的 descriptions 中取 -->
          </div>
        </details>
      </div>
    </div>
    <div class="prompt-edit-actions">
      <button data-prompt-reset="ai-assist">恢复默认</button>
    </div>
  </div>
</div>
```

**注意**：
- 提示词 textarea 的 id 与现状保持一致（`cfg-ai_assist-prompt_*` 或 `cfg-ai_search-prompt_*`），便于 `cinema-directory-loader.js` 回填
- 每个提示词所属 section（`ai_assist` 还是 `ai_search`）由现状决定，见 §1.1 配置 key 表
- 功能说明文案从 `/api/config/prompt-defaults` 的 `descriptions` 字段读取，前端首次加载时缓存

**新增 CSS**（`media_importer/webui/css/cinema-pages-8.css` 末尾）：

```css
.prompt-edit-grid {
  display: grid;
  grid-template-columns: 1fr 280px;
  gap: 16px;
}
.prompt-help-disclosure summary {
  cursor: pointer;
  font-weight: 600;
}
.prompt-help-disclosure[open] summary {
  margin-bottom: 8px;
}
```

**验收**：
- UI 测：5 个 tab 切换正常
- UI 测：每个 tab 的功能说明默认折叠，点击展开
- UI 测：点击【恢复默认】，仅当前 tab 的 textarea 被覆盖为默认值
- UI 测：点击【保存】，POST `/api/config/section` body 含 `section: "ai_prompts"`

---

#### T2.5 区域 3：场景设置

**位置**：`#ai-scene-strategy-card` 内部

**结构**：

```html
<div class="config-collapse-header" data-collapse-toggle="ai-scene-strategy-body">
  ...<button data-config-save="ai-scene-strategy">保存</button>...
</div>
<div class="config-collapse-body" id="ai-scene-strategy-body">
  <div class="info-callout">
    为每个 AI 场景配置【优先模型】（必填）和【次选模型】（可空）。
    优先模型调用失败（含重试）后自动切换到次选模型；两者都失败时按各场景的容错策略降级。
    大多数场景默认只配置优先模型即可。
  </div>

  <!-- 5 行场景配置（以 dimension_supplement 为例） -->
  <div class="scene-strategy-row" data-scene="dimension_supplement">
    <div class="scene-strategy-label">
      <b>刮削缺失补充</b>
      <small>Provider 刮削结果缺失的维度，由 AI 联网搜索补充</small>
    </div>
    <div class="scene-strategy-selects">
      <label>
        优先模型
        <select id="cfg-ai_scene_strategy-dimension_supplement-primary">
          <option value="ai_assist">AI 辅助</option>
          <option value="ai_search">AI 联网搜索增强</option>
        </select>
      </label>
      <label>
        次选模型
        <select id="cfg-ai_scene_strategy-dimension_supplement-fallback">
          <option value="">（不配置）</option>
          <option value="ai_assist">AI 辅助</option>
          <option value="ai_search">AI 联网搜索增强</option>
        </select>
      </label>
    </div>
  </div>

  <!-- 其余 4 行结构相同，scene 名和文案见 §1.1 和 §1.2 -->
</div>
```

**新增 CSS**（`cinema-pages-8.css` 末尾）：

```css
.scene-strategy-row {
  display: grid;
  grid-template-columns: 1fr auto;
  gap: 16px;
  padding: 16px;
  border-bottom: 1px solid var(--border-color);
}
.scene-strategy-selects {
  display: flex;
  gap: 12px;
}
```

**验收**：
- UI 测：5 行场景配置完整显示，每行有 2 个下拉
- UI 测：primary 下拉没有"空"选项，fallback 下拉有"空"选项且是默认
- UI 测：保存时前端校验 primary 非空，否则 toast 提示
- UI 测：点击【保存】，POST `/api/config/section` body 含 `section: "ai_scene_strategy"`

---

#### T2.6 JS 模块改造

**文件清单**：

| 文件 | 改动 |
|------|------|
| `webui/js/cinema-config-payloads.js` | 新增 `buildAiApikeyPayload()` / `buildAiPromptsPayload()` / `buildAiSceneStrategyPayload()`；保留 `preserveApiKey` 逻辑 |
| `webui/js/cinema-config-save.js` | 新增 `saveAiApikeyConfig()` / `saveAiPromptsConfig()` / `saveAiSceneStrategyConfig()`，分别 POST section `ai_apikey` / `ai_prompts` / `ai_scene_strategy` |
| `webui/js/cinema-config-ai.js` | 扩展 `bindAiConfigInteractions`：①API Key 区页签切换（`data-apikey-tab`）②提示词区 5 tab 切换③每个提示词右侧 help details 折叠（用原生 `<details>`）④场景策略下拉事件 |
| `webui/js/cinema-directory-loader.js:88-162` | 新增 `ai_scene_strategy` 字段回填（5 场景 × 2 下拉）；提示词区从单一 ai_assist/ai_search 分离出来集中渲染 |
| `webui/js/cinema-reel.js:227-280` | `updateAiConfigStatus` 改为按 3 个 card 分别更新状态徽章：①API Key 区根据 ai_assist/ai_search 是否有 api_key 判定②提示词区根据是否启用非默认值判定③场景区根据是否有效配置判定 |
| `webui/js/cinema-app-events.js:113-205` | 新增委托：`data-config-save="ai-apikey"` / `"ai-prompts"` / `"ai-scene-strategy"`；`data-apikey-tab` 页签切换；保留 `data-llm-test` / `data-prompt-reset` / `data-prompt-tab` |
| `webui/js/cinema-config.js:3-34` | 保留 `SEARCH_TYPE_MAP` / `PROVIDER_BASE_URL_MAP` / `PROVIDER_MODEL_MAP` 不变 |
| `webui/js/config-build.js:5-22` | **删除老版 `updateAiConfigStatus`（死代码）** |

**验收**：
- UI 测：每个保存按钮触发的 section 正确
- UI 测：加载 `/config` 后所有字段正确回填
- UI 测：3 个状态徽章正确显示"已配置"/"未配置"

---

### Phase 3：测试与文档（共 5 个任务）

---

#### T3.1 单元测试（新增）

**文件（新建）**：`tests/test_ai_scene_strategy.py`

**用例清单**：

| 用例 | 验证点 |
|------|--------|
| `test_scene_strategy_default_values` | `load_config({})` 后 5 个场景的 primary/fallback 都按 §2.1 默认值填充 |
| `test_scene_strategy_user_override_not_overwritten` | 用户自定义值不被 setdefault 覆盖 |
| `test_scene_strategy_validator_empty_primary` | primary 为空时报错 |
| `test_scene_strategy_validator_invalid_primary` | primary 非 ai_assist/ai_search 时报错 |
| `test_scene_strategy_validator_empty_fallback_ok` | fallback 为空时通过 |
| `test_scene_resolver_model_sequence_no_fallback` | fallback="" → `[primary]` |
| `test_scene_resolver_model_sequence_with_fallback` | fallback 非空 → `[primary, fallback]` |
| `test_scene_resolver_model_sequence_dedup` | primary=fallback 时去重 |
| `test_scene_resolver_unknown_scene_raises` | 未知 scene 抛 ValueError |

**文件（新建）**：`tests/test_prompt_defaults_unified.py`

| 用例 | 验证点 |
|------|--------|
| `test_prompt_defaults_get_all_structure` | `get_all()` 返回 `{prompts: {...}, descriptions: {...}}` |
| `test_prompt_resolver_returns_default_when_empty` | 5 个 `get_*_prompt()` 留空时返回 `PromptDefaults.XXX` |
| `test_prompt_resolver_returns_user_value` | 配置了自定义值时返回用户值 |
| `test_no_inline_fallback_in_usage_points` | grep 5 个使用点，确认无 `or "你是一个"` 之类的内联兜底 |

**文件（新建）**：`tests/test_retry_with_fallback.py`

| 用例 | 验证点 |
|------|--------|
| `test_retry_success_on_first_attempt` | 首次成功不重试 |
| `test_retry_switches_to_fallback_model` | primary 重试 `max_retries` 次失败后切到 fallback |
| `test_retry_no_fallback_raises_last_error` | fallback="" 时重试失败后抛最后一个错误 |
| `test_retry_unknown_scene_raises` | 未知 scene 抛 ValueError |

**文件（新建）**：`tests/test_source_cleaner_uses_llm_scraper.py`

| 用例 | 验证点 |
|------|--------|
| `test_source_cleaner_call_llm_uses_llm_scraper` | mock `LLMScraper.call_with_prompt`，断言被调用 |
| `test_source_cleaner_no_urllib_direct_call` | grep `cleaner.py` 无 `urllib.request.urlopen` |
| `test_source_cleaner_follows_scene_strategy` | 场景策略配 primary=ai_search 时，调用走 ai_search 模型 |

**文件（新建）**：`tests/test_ai_call_logging.py`

| 用例 | 验证点 |
|------|--------|
| `test_log_ai_scene_start_on_call` | 调用 AI 时输出 `ai.scene.start` 日志，含 scene/model/attempt |
| `test_log_ai_scene_success_with_elapsed` | 成功时输出 `ai.scene.success` 日志，含 elapsed_ms |
| `test_log_ai_scene_retry_on_failure` | 抛错重试时输出 `ai.scene.retry` 日志，含 error/reason |
| `test_log_ai_scene_fallback_on_model_switch` | 切换 fallback 模型时输出 `ai.scene.fallback` 日志，含 from/to |
| `test_log_ai_scene_failure_when_all_fail` | 全部失败时输出 `ai.scene.failure` 日志，含 last_error/total_elapsed_ms |
| `test_log_ai_scene_prompt_summary_info_level` | 默认 INFO 级别输出 `ai.scene.prompt_summary`，含 preview 前 200 字符 |
| `test_log_ai_scene_prompt_full_debug_level` | DEBUG 级别输出 `ai.scene.prompt`，含完整提示词 |
| `test_log_ai_scene_prompt_disabled_when_config_off` | `ai_assist.log_prompt=false` 时不输出 prompt 相关日志 |
| `test_log_ai_scene_business_context` | 场景 3/4/5 入口输出 `ai.scene.business` 日志，含 trigger/filename 等业务上下文 |

---

#### T3.2 集成测试（新增）

**文件（新建）**：`tests/test_ai_scenes_integration.py`

| 用例 | 验证点 |
|------|--------|
| `test_scene1_dimension_supplement_uses_configured_model` | 配置 primary=ai_assist，刮削缺失补充流程实际用 ai_assist |
| `test_scene2_dimension_mapping_falls_back_to_scene1_on_failure` | 场景 2 失败后降级到场景 1（保留现有容错） |
| `test_scene3_title_clean_fails_silently_to_regex` | 场景 3 全部失败后降级到正则清洗（保留现有容错） |
| `test_scene4_match_assist_fails_to_needs_confirm` | 场景 4 全部失败后降级到 NEEDS_CONFIRM（保留现有容错） |
| `test_scene5_source_clean_fails_to_rule_only` | 场景 5 全部失败后仅返回规则分类结果（保留现有容错） |
| `test_full_import_flow_with_ai_disabled` | AI 未配置时，整个入库流程仍能跑完（场景 1/2 失败由各调用方 try/except 兜底） |

---

#### T3.3 回归测试（必须通过）

**命令**：

```bash
# 全部测试
python -m pytest tests/

# 架构护栏
python -m pytest tests/test_architecture_guards.py

# 非 UI 测试（CI 友好）
python -m pytest tests/ --ignore=tests/test_*_ui.py --ignore=tests/test_frontend_*.py --ignore=tests/test_scrape_ui.py

# 编译检查
PYTHONPYCACHEPREFIX=/private/tmp/nas_media_manage_pycache python -m compileall -q media_importer tests
```

**回归红线**：本次改造**不得改变**以下行为：

| 行为 | 验证 |
|------|------|
| 场景 1 失败阻塞入库 | `test_import_flow_pipeline_error_on_dimension_supplement_failure` |
| 场景 2 失败降级到场景 1 | `test_scrape_with_context_fallback_to_scrape` |
| 场景 3 失败降级到正则 | `test_ai_clean_fallback_to_regex` |
| 场景 4 失败降级到 NEEDS_CONFIRM | `test_tier2_low_certainty_to_needs_confirm` |
| 场景 5 失败仅返回规则分类 | `test_source_cleaner_ai_failure_returns_rule_only` |
| API Key 脱敏 | `test_config_api_key_masked_in_response` |

> 如果上述任意回归测试不存在，先补齐再开始本次改造。

---

#### T3.4 UI 测试

**测试范围**：`tests/test_ai_config_ui.py`（如不存在则新建）

| 用例 | 验证点 |
|------|--------|
| `test_ai_config_three_accordion_default_collapsed` | 进入 AI 配置页，3 个区域默认折叠 |
| `test_ai_config_apikey_tab_switch` | API Key 区两个 tab 切换正常 |
| `test_ai_config_apikey_test_connection_button_per_tab` | 两个 tab 都有【测试连通性】按钮且可点击 |
| `test_ai_config_demo_modal_opens` | 点击【模拟测试】模态正常弹出（修复 T2.1 的 broken） |
| `test_ai_config_prompts_five_tabs` | 提示词区 5 个 tab 切换正常 |
| `test_ai_config_prompts_help_disclosure` | 每个提示词 tab 的功能说明默认折叠，点击展开 |
| `test_ai_config_prompts_reset_current_tab_only` | 恢复默认仅作用于当前 tab |
| `test_ai_config_scene_strategy_five_rows` | 场景区 5 行配置完整显示 |
| `test_ai_config_scene_strategy_primary_required` | primary 为空时保存被前端拦截 |
| `test_ai_config_scene_strategy_fallback_optional` | fallback 为空时保存通过 |
| `test_ai_config_save_apikey_section` | 保存触发 POST `ai_apikey` section |
| `test_ai_config_save_prompts_section` | 保存触发 POST `ai_prompts` section |
| `test_ai_config_save_scene_strategy_section` | 保存触发 POST `ai_scene_strategy` section |

---

#### T3.5 文档同步

**改动清单**：

| 文件 | 改动 |
|------|------|
| `docs/architecture/api.md` | 新增 `ai_apikey` / `ai_prompts` / `ai_scene_strategy` 三个 section；`/api/config/prompt-defaults` 返回结构升级 |
| `docs/standards/api.md` | 同步 API 协议 |
| `docs/features/ai-config.md`（新建） | 描述三区域 + 5 场景策略 + 默认值 |
| `docs/INDEX.md` | 加入新文档索引 |
| `docs/tracking/pending-acceptance.md` | 加入本次改造的待验收项 |
| `docs/standards/safety.md` | 如有改动 API Key 脱敏逻辑则同步 |

---

## 4. 执行顺序建议

### 阶段 A：后端基础设施（T1.1 - T1.15）— ✅ Phase 1 已完成

实际完成顺序（含偏离说明，见决策 12-15）：

```
T1.1 PromptDefaults 迁移 ✅
  └→ T1.2 PromptResolver 改造 ✅
       └→ T1.3 使用点改造（5 处）✅ + 决策 15：同步清理 tier2_judge 测试

T1.4 config_view 新增 dataclass ✅
  └→ T1.5 config_loader.setdefault ✅
       └→ T1.6 config_validator 校验 ✅
            └→ T1.7 SceneStrategyResolver ✅
                 └→ T1.8 抽出 _run_with_strategy_impl 共享实现 ✅（决策 12，比原 plan 更优雅）
                      ├→ T1.9 call_with_prompt 新增 ✅
                      │    └→ T1.11 SourceCleaner 改造 ✅
                      └→ T1.10 5 个调用点传入 scene ✅ + 决策 13：场景 3/4 走 _call_with_retry_impl

T1.12 /api/config/prompt-defaults 升级 ✅（依赖 T1.1）
T1.13 /api/config/section 新增 3 个 section ✅（依赖 T1.4-T1.6）
T1.14 connectivity_handlers 修复 ✅（独立）
T1.15 AI 调用统一日志 ✅（埋点统一在 _run_with_strategy_impl）
```

**Phase 1 实际产出**：
- 总改动文件数：20 个（12 修改 + 2 删除 + 4 新建 + 2 测试辅助修改）
- 净减少约 146 行（删除死代码 + 抽取共享实现）
- 新增 18 个单元测试，588 个回归测试全过
- 编译通过

### 阶段 B：前端 UI（T2.1 - T2.6）— 待开始

依赖顺序：

```
T2.1 补全 demo 模态 HTML（独立先行，修复 broken）
  └→ T2.2 重排 3 个手风琴
       ├→ T2.3 API Key 区
       ├→ T2.4 提示词区
       └→ T2.5 场景区
            └→ T2.6 JS 模块改造
```

### 阶段 C：测试与文档（T3.1 - T3.5）— 待开始

- T3.1 单测可与阶段 A 同步写（TDD）— Phase 1 已补齐 18 个
- T3.2 集成测试在阶段 A 完成后写
- T3.3 回归测试在阶段 A + B 完成后跑
- T3.4 UI 测试在阶段 B 完成后写
- T3.5 文档同步最后做

---

## 5. 验收标准（整体）

### 阶段 A 验收（Phase 1）— ✅ 已通过

1. **后端**：
   - ✅ 所有单元测试 + 集成测试通过（588 个）
   - ✅ `python -m compileall -q media_importer tests` 编译通过
   - ✅ `python -m pytest tests/test_architecture_guards.py` 通过
   - ✅ 5 个内联兜底字面量全部删除（grep 验证）
   - ✅ SourceCleaner 不再直接使用 urllib（grep 验证）
   - ✅ 日志埋点齐全（`tests/test_ai_call_logging.py` 10 个用例通过）
   - ⏳ 跑一个完整入库任务，日志中能 grep 到至少 5 个场景的 `ai.scene.start` 记录（待集成测/手工验证）

### 阶段 B 验收（Phase 2）— 待执行

2. **前端**：
   - AI 配置页 3 个手风琴区域默认全折叠
   - API Key 区两个 tab 切换 + 各自测试按钮可用（AI 辅助 tab 必须补【测试连通性】）
   - 提示词区 5 tab + 右侧 help + 每页签恢复默认
   - 场景区 5 行 × 2 下拉 + primary 必填校验
   - 3 个独立保存按钮各自 POST 对应 section
   - 模拟测试模态能正常弹出（修复 broken）

### 阶段 C 验收（Phase 3）— 待执行

3. **回归**：
   - 所有原有测试通过
   - 5 个场景的容错行为（失败降级）原样保留

4. **文档**：
   - `docs/architecture/api.md` / `docs/features/ai-config.md` / `docs/INDEX.md` 同步
   - `docs/tracking/pending-acceptance.md` 加入待验收项

---

## 6. 低优先级 follow-up

### F1. 两条调用链 Provider 重复搜索问题

**现状描述**（用户询问的位置）：

在 `media_importer/features/import_flow/steps/scrape.py:_step_scrape()` 中：

- **Line 33**：`self.scraper.scrape(...)` — 调用链 A，内部会调 Provider 搜索 + AI 维度映射/补充
- **Line 44**：`match_engine.match(...)` — 调用链 B，内部 Tier1 会再次用同样的 filename 调 Provider 搜索，Tier2 失败时还会用 AI 纠正后的标题搜第三次

两条链各自独立，**Provider 被重复搜索**，且场景 3（调用链 A）和场景 4（调用链 B）的 AI 结果互不感知。

**优先级**：低（功能正常，只是性能可优化）

**处理时机**：本次三区域改造全部完成并验收后，单独开 plan 处理

**预期方案**：让调用链 B 复用调用链 A 已经搜到的 Provider 候选，而不是重新搜索

---

## 7. 关联文档

- 前序 plan：[2026-06-13 AI 配置重设计实现计划](file:///Users/wangwei/Documents/code/nas_media_manage/docs/plans/2026-06-13-ai-config-redesign-implementation-plan.md)
- 相关 plan：[2026-06-14 Tier2 AI 上下文辅助匹配改造](file:///Users/wangwei/Documents/code/nas_media_manage/docs/plans/2026-06-14-tier2-ai-context-match-redesign.md)
- 架构决策：[ADR-0005 三级匹配](file:///Users/wangwei/Documents/code/nas_media_manage/docs/decisions/0005-three-tier-matching.md)
- 安全规范：[docs/standards/safety.md](file:///Users/wangwei/Documents/code/nas_media_manage/docs/standards/safety.md)
- 测试规范：[docs/standards/testing.md](file:///Users/wangwei/Documents/code/nas_media_manage/docs/standards/testing.md)
- 配置规范：[docs/standards/](file:///Users/wangwei/Documents/code/nas_media_manage/docs/standards/)
