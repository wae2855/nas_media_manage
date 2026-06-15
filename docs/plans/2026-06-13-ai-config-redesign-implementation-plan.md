---
title: "AI配置重设计 — 详细开发计划"
type: plan
date: 2026-06-13
status: active
design: docs/design/2026-06-13-ai-config-redesign.md
adr: docs/decisions/0005-three-tier-matching.md
---

# AI配置重设计 — 详细开发计划

**设计方案**：[2026-06-13-ai-config-redesign.md](file:///Users/wangwei/Documents/code/nas_media_manage/docs/design/2026-06-13-ai-config-redesign.md)
**架构决策**：[ADR-0005](file:///Users/wangwei/Documents/code/nas_media_manage/docs/decisions/0005-three-tier-matching.md)

## 总览

本计划将设计方案 v6 拆分为 3 个 Phase，每个 Phase 可独立交付和验证。Phase 内按任务编号顺序执行，带依赖关系的任务标注了前置条件。

**开发后评审状态（2026-06-13）**：
- Phase 1 ✅ 基础设施已完成（配置对象、迁移函数、DB 新列、提示词 API）
- Phase 2 ✅ UI 已完成（前端控件齐全），但后端数据源未完全连通
- Phase 3 ⚠️ 壳已搭，核心逻辑未完全切换

**紧急修复清单**（评审发现的 P0/P1 问题，需优先处理）：

| # | 优先级 | 问题 | 状态 |
|---|--------|------|------|
| #1 | P0 | `llm_scraper.py` 仍读旧 `llm` 字段，新配置不生效 | 🔴 待修复 |
| #2 | P0 | `confirm_reason` 仅存内存，未写入 DB | 🔴 待修复 |
| #3 | P1 | `dim_sources` 维度来源追踪——DB 有字段、前端有读取，中间未写入 | 🔴 待修复 |
| #4 | P1 | `validate_config` 仍强制要求旧 `llm.api_key` | 🟡 待修复 |
| #7 | P2 | `trust_ai_assist/trust_ai_search` 未影响刮削判断逻辑 | 🟡 待修复 |
| #5 | P3 | `ai_only` 残留代码未清理 | 🟢 待处理 |
| #8 | P3 | 迁移无幂等保护，无 schema_version | 🟢 待处理 |

---

## 🔥 紧急修复（Hot Fixes）

### HF-1 llm_scraper.py 配置源切换（P0）

**问题**：构造函數仍硬编码读 `ConfigView.from_dict(config).llm`，用户在 UI 配置的 `ai_assist`/`ai_search` 完全不生效。

**文件**：`media_importer/scraper/llm_scraper.py`

**操作**：修改 `__init__`，优先读 `ai_assist`/`ai_search`，fallback 到 `llm`：

```python
def __init__(self, config: dict):
    ai_assist = config.get("ai_assist", {})
    ai_search = config.get("ai_search", {})
    llm = config.get("llm", {})

    # AI辅助模型（fast_*）
    self.fast_model = ai_assist.get("model") or llm.get("fast_model") or llm.get("model", "")
    self.fast_base_url = ai_assist.get("base_url") or llm.get("fast_base_url") or llm.get("base_url", "")
    self.fast_api_key = ai_assist.get("api_key") or llm.get("fast_api_key") or llm.get("api_key", "")

    # AI联网搜索增强模型
    self.model = ai_search.get("model") or llm.get("model", "")
    self.base_url = ai_search.get("base_url") or llm.get("base_url", "")
    self.api_key = ai_search.get("api_key") or llm.get("api_key", "")

    # Web搜索配置
    from media_importer.features.scraping.web_search_config import build_web_search_config
    self.web_search_config = build_web_search_config(ai_search or llm.get("web_search", {}))

    # 其他参数
    self.timeout = ai_assist.get("timeout") or llm.get("timeout", 30)
    self.max_retries = ai_assist.get("max_retries") or llm.get("max_retries", 2)
    self.verify_ssl = ai_assist.get("verify_ssl", True) if ai_assist.get("verify_ssl") is not None else llm.get("verify_ssl", True)

    # legacy 字段保留给上层兼容
    self.fallback_model = llm.get("fallback_model", "")
    self.confidence_threshold = llm.get("confidence_threshold", 0)
```

**验证**：旧 `llm` 配置用户升级后刮削正常；新 `ai_assist`/`ai_search` 配置用户刮削生效。

---

### HF-2 confirm_reason 写入 DB（P0）

**问题**：`_step_validate` 只写 `task["_confirm_reason"]` 内存字段，`confirm_reason` 未写入 DB。

**文件**：`media_importer/features/import_flow/steps/scrape.py`

**操作**：在 `db_update_task` 调用中加入 `confirm_reason`：

```python
db_update_task(
    self.task_manager.conn, task.get("task_id", ""),
    ...
    confirm_reason=task.get("_confirm_reason", ""),
)
```

**验证**：待确认任务在 DB 中 `confirm_reason` 非空，重启后仍能展示确认原因。

---

### HF-3 dim_sources 维度来源写入 DB（P1）

**问题**：`dim_sources` DB 字段和前端展示逻辑已就绪，但 `scrape.py` 和 `metadata_scrape_flow.py` 均未构造和写入。

**文件**：`media_importer/features/import_flow/steps/scrape.py`

**操作**：

1. 在 `_step_scrape` 中，从 `scrape_result` 获取或构造 `dim_sources`：
```python
import json as _json
dim_sources = result.get("dim_sources", {})
if not dim_sources:
    # 临时兜底：根据 result 中是否有 ai_invoked 标记来源
    dim_sources = self._infer_dim_sources(result, file_dimensions, scrape_dimensions)
task["dim_sources"] = dim_sources
```

2. 在 `db_update_task` 调用中加入：
```python
db_update_task(
    ...
    dim_sources=dim_sources,
)
```

3. 新增 `_infer_dim_sources()` 辅助函数（临时方案，正式方案在 Phase 3 T3.4 中实现）：
```python
def _infer_dim_sources(self, result: dict, file_dimensions: dict, scrape_dimensions: dict) -> dict:
    """根据 result 推断各维度来源。临时方案，正式方案见 Phase 3 T3.4。"""
    sources = {}
    scrape_trace = result.get("scrape_trace", {})
    ai_invoked = scrape_trace.get("ai_invoked", False) if isinstance(scrape_trace, dict) else False

    for dim_name in scrape_dimensions:
        if dim_name in file_dimensions:
            sources[dim_name] = "file"
        elif ai_invoked:
            sources[dim_name] = "ai_assist"
        else:
            sources[dim_name] = "provider:tmdb"
    return sources
```

**验证**：任务卡片刮削过程展开区能看到维度来源图标，不再是空。

---

### HF-4 validate_config 改用新字段校验（P1）

**问题**：`validate_config` 强制要求旧 `llm.api_key`，但新用户 UI 上已无 `llm` 区块。

**文件**：`media_importer/core/config_loader.py`

**操作**：修改校验逻辑，支持 Provider-only 模式（不强制 AI 配置）：

```python
def validate_config(config: dict) -> list:
    errors = []
    llm = config.get("llm", {})
    ai_assist = config.get("ai_assist", {})
    ai_search = config.get("ai_search", {})

    # Provider-only 模式：至少有一个 Provider 配置即可，不强制 AI
    if not config.get("providers"):
        # 检查是否有 TMDB 等 Provider（通过 providers 区块）
        pass  # 保留原有 Provider 校验

    # AI 配置为可选项（NAS 用例可用 Provider-only）
    # 如果用户配置了 AI 但未填写完整，给出提示而非报错
    for section, name in (("ai_assist", "AI辅助"), ("ai_search", "AI联网搜索增强")):
        s = config.get(section, {})
        if s and s.get("api_key") and s["api_key"] != "your-api-key-here":
            # 检查必填字段
            if section == "ai_assist":
                if not s.get("base_url") or not s.get("model"):
                    errors.append(f"{name}已配置 API Key，但缺少 base_url 或 model")
            elif section == "ai_search":
                if not s.get("provider") or not s.get("model"):
                    errors.append(f"{name}已配置 API Key，但缺少 provider 或 model")

    return errors
```

**验证**：无 AI 配置时服务正常启动；配置 AI 但字段不完整时给出明确提示。

---

## Phase 1：配置结构 + DB 变更

**✅ 状态**：已完成（所有 T1.1-T1.8 任务均已实现）

**文件**：`media_importer/core/config_view.py`

**操作**：

1. 在 `LLMConfig` 之后新增两个 dataclass：

```python
@dataclass(frozen=True)
class AiAssistConfig:
    """AI辅助模型配置（轻量任务：标题清洗、匹配辅助、维度映射、源目录清理）。"""
    base_url: str = ""
    model: str = ""
    api_key: str = ""
    timeout: int = 30
    max_retries: int = 2
    retry_delay: int = 3
    verify_ssl: bool = True
    # 提示词（高级选项，留空使用默认值）
    prompt_title_clean: str = ""
    prompt_match_assist: str = ""
    prompt_dimension_mapping: str = ""
    prompt_source_clean: str = ""

    @property
    def is_configured(self) -> bool:
        return bool(self.api_key and self.base_url and self.model)


@dataclass(frozen=True)
class AiSearchConfig:
    """AI联网搜索增强配置（维度补全，需联网搜索能力）。"""
    enabled: bool = True
    provider: str = ""          # 厂商下拉：zhipu / qwen / moonshot
    model: str = ""
    search_type: str = ""       # 搜索类型：search_std / search_pro / enable_search 等
    api_key: str = ""
    base_url: str = ""          # 高级选项，自动填充
    timeout: int = 30
    max_retries: int = 2
    retry_delay: int = 3
    verify_ssl: bool = True
    # 提示词（高级选项，留空使用默认值）
    prompt_dimension_supplement: str = ""

    @property
    def is_configured(self) -> bool:
        return bool(self.api_key and self.model)

    @property
    def is_effective(self) -> bool:
        return self.enabled and self.is_configured
```

2. 在 `ConfigView` dataclass 中新增字段：

```python
ai_assist: AiAssistConfig
ai_search: AiSearchConfig
```

3. 在 `ConfigView.from_dict()` 方法中，从 `config.get("ai_assist", {})` 和 `config.get("ai_search", {})` 构建新 dataclass 实例。

4. `LLMConfig` 标记为 legacy，添加注释：`# legacy: 保留用于向后兼容，新代码使用 ai_assist / ai_search`。

**验证**：`python -c "from media_importer.core.config_view import ConfigView; print('OK')"` 编译通过。

---

### T1.2 SECTION_FIELD_MAP 注册新配置区块

**文件**：`media_importer/features/configuration/application_service.py`

**操作**：

在 `SECTION_FIELD_MAP` 中新增：

```python
SECTION_FIELD_MAP = {
    ...
    "ai_assist": ["ai_assist"],
    "ai_search": ["ai_search"],
    ...
}
```

**验证**：`build_section_config_update("ai_assist", {"ai_assist": {...}}, config)` 不抛异常。

---

### T1.3 配置迁移逻辑：llm → ai_assist + ai_search

**文件**：`media_importer/core/config_migrations.py`

**操作**：

1. 新增迁移函数：

```python
def _migrate_llm_to_ai_config(config: dict) -> None:
    """将旧 llm 配置迁移为 ai_assist + ai_search。

    迁移规则：
    - llm.fast_model/fast_base_url/fast_api_key → ai_assist.model/base_url/api_key
    - llm.model/base_url/api_key → ai_search.model/base_url/api_key
    - llm.web_search.provider → ai_search.provider
    - llm.source_cleaner_model → 忽略（统一用 ai_assist.model）
    - llm.fallback_model → 忽略
    - llm.confidence_threshold → 忽略
    - llm.enabled → 忽略
    - metadata.scrape_mode → 忽略（固定 provider_first）
    """
    if "ai_assist" in config and "ai_search" in config:
        return  # 已迁移过

    llm = config.get("llm", {})
    if not llm:
        return

    # 构建 ai_assist
    ai_assist = {}
    if llm.get("fast_base_url") or llm.get("base_url"):
        ai_assist["base_url"] = llm.get("fast_base_url") or llm.get("base_url", "")
    if llm.get("fast_model") or llm.get("model"):
        ai_assist["model"] = llm.get("fast_model") or llm.get("model", "")
    if llm.get("fast_api_key") or llm.get("api_key"):
        ai_assist["api_key"] = llm.get("fast_api_key") or llm.get("api_key", "")
    ai_assist.setdefault("timeout", llm.get("timeout", 30))
    ai_assist.setdefault("max_retries", llm.get("max_retries", 2))
    ai_assist.setdefault("retry_delay", llm.get("retry_delay", 3))
    ai_assist.setdefault("verify_ssl", llm.get("verify_ssl", True))

    # 构建 ai_search
    ai_search = {}
    web_search = llm.get("web_search", {})
    ai_search["enabled"] = web_search.get("enabled", True)
    ai_search["provider"] = web_search.get("provider", "")
    if llm.get("model"):
        ai_search["model"] = llm["model"]
    if llm.get("base_url"):
        ai_search["base_url"] = llm["base_url"]
    if llm.get("api_key"):
        ai_search["api_key"] = llm["api_key"]
    ai_search.setdefault("timeout", llm.get("timeout", 30))
    ai_search.setdefault("max_retries", llm.get("max_retries", 2))
    ai_search.setdefault("retry_delay", llm.get("retry_delay", 3))
    ai_search.setdefault("verify_ssl", llm.get("verify_ssl", True))

    config["ai_assist"] = ai_assist
    config["ai_search"] = ai_search

    # 删除旧字段
    for key in ["fallback_model", "confidence_threshold", "enabled", "source_cleaner_model"]:
        llm.pop(key, None)
    llm.pop("web_search", None)

    # 删除 scrape_mode
    config.get("metadata", {}).pop("scrape_mode", None)

    print("已自动迁移 llm 配置 → ai_assist + ai_search")
```

2. 在 `config_loader.py` 的 `load_config()` 中调用：

```python
# 在 _migrate_confidence_v2_to_v3(config) 之后
_migrate_llm_to_ai_config(config)
```

3. 在 `config_loader.py` 顶部 import 新函数。

**验证**：编写测试用例验证迁移逻辑（见 T1.8）。

---

### T1.4 web_search_config.py 新增 search_type + 新厂商

**文件**：`media_importer/features/scraping/web_search_config.py`

**操作**：

1. 扩展 `SUPPORTED_PROVIDERS`：

```python
SUPPORTED_PROVIDERS: Dict[str, str] = {
    "zhipu": "智谱 GLM",
    "qwen": "通义千问",
    "moonshot": "Kimi/Moonshot",
    # 以下为预留，暂不支持
    # "doubao": "豆包（开发中）",
    # "openai": "OpenAI（开发中）",
    # "self_hosted": "自部署搜索服务（开发中）",
}
```

2. 新增搜索类型映射：

```python
SEARCH_TYPE_MAP: Dict[str, list] = {
    "zhipu": [
        {"value": "search_std", "label": "标准搜索"},
        {"value": "search_pro", "label": "增强搜索"},
    ],
    "qwen": [
        {"value": "enable_search", "label": "标准搜索"},
        {"value": "forced_search", "label": "强制搜索"},
    ],
    "moonshot": [
        {"value": "web_search", "label": "联网搜索"},
    ],
}

DEFAULT_SEARCH_TYPE: Dict[str, str] = {
    "zhipu": "search_std",
    "qwen": "enable_search",
    "moonshot": "web_search",
}
```

3. 扩展 `WebSearchConfig`：

```python
@dataclass(frozen=True)
class WebSearchConfig:
    detected_provider: Optional[str] = None
    search_type: str = ""           # 新增：搜索类型
    enabled: bool = True            # 新增：开关

    def should_search(self, scenario: str) -> bool:
        if not self.enabled:
            return False
        if self.detected_provider is None:
            return False
        return scenario in ("scrape", "series_scrape")

    def effective_provider(self) -> Optional[str]:
        return self.detected_provider

    def supports_web_search(self) -> bool:
        return self.enabled and self.detected_provider is not None

    def effective_search_type(self) -> str:
        """返回有效的搜索类型，未配置时用默认值。"""
        if self.search_type:
            return self.search_type
        return DEFAULT_SEARCH_TYPE.get(self.detected_provider or "", "")
```

4. 新增工厂函数：

```python
def build_web_search_config(ai_search_config: dict) -> WebSearchConfig:
    """从 ai_search 配置构建 WebSearchConfig。"""
    provider = ai_search_config.get("provider", "")
    enabled = ai_search_config.get("enabled", True)
    search_type = ai_search_config.get("search_type", "")

    detected = provider if provider in SUPPORTED_PROVIDERS else None

    return WebSearchConfig(
        detected_provider=detected,
        search_type=search_type,
        enabled=enabled,
    )
```

**验证**：`python -c "from media_importer.features.scraping.web_search_config import build_web_search_config; print(build_web_search_config({'provider': 'zhipu', 'enabled': True, 'search_type': 'search_std'}))"` 正常输出。

---

### T1.5 DB 变更：dimensions 新增信任字段，tasks 新增来源追踪字段

**文件**：`media_importer/core/db/connection.py`

**操作**：

在 `_migrate_schema()` 函数的 dimensions 迁移区域新增：

```python
if "dimensions" in tables:
    dim_existing = {row[1] for row in conn.execute("PRAGMA table_info(dimensions)").fetchall()}
    # ... 现有 default_value_list 迁移 ...
    if "trust_ai_assist" not in dim_existing:
        conn.execute("ALTER TABLE dimensions ADD COLUMN trust_ai_assist INTEGER NOT NULL DEFAULT 1")
    if "trust_ai_search" not in dim_existing:
        conn.execute("ALTER TABLE dimensions ADD COLUMN trust_ai_search INTEGER NOT NULL DEFAULT 0")
```

在 tasks 迁移区域新增：

```python
if "confirm_reason" not in existing:
    conn.execute("ALTER TABLE tasks ADD COLUMN confirm_reason TEXT DEFAULT ''")
if "dim_sources" not in existing:
    conn.execute("ALTER TABLE tasks ADD COLUMN dim_sources TEXT DEFAULT NULL")
```

**文件**：`media_importer/core/db/constants.py`

**操作**：

在 `DEFAULT_DIMENSIONS` 的每个维度字典中新增：

```python
"trust_ai_assist": 1,   # 1=信任AI辅助映射，0=不信任
"trust_ai_search": 0,   # 1=信任AI联网搜索，0=不信任
```

特别注意 `media_type` 维度：`trust_ai_assist` 和 `trust_ai_search` 都设为 1（因为 media_type 由 Provider 搜索端点硬编码，不走 AI）。

**文件**：`media_importer/core/db/dimension_repo.py`

**操作**：

确保 `trust_ai_assist` 和 `trust_ai_search` 在维度读写操作中包含。

**文件**：`media_importer/core/db/task_repo.py`

**操作**：

确保 `confirm_reason` 和 `dim_sources` 在任务读写操作中包含。

**验证**：启动服务后检查 DB schema 包含新字段。

---

### T1.6 新增 PromptDefaults 默认提示词常量

**文件**：新建 `media_importer/features/prompts/defaults.py`

**操作**：

```python
"""所有场景的默认提示词，作为恢复默认的唯一来源。"""


class PromptDefaults:
    """默认提示词常量。

    优先级：
    1. 用户在高级选项中配置的自定义提示词（最高优先级）
    2. config/scraper_prompts.md 文件中的提示词（兼容旧方式，仅 dimension_mapping）
    3. PromptDefaults 代码常量（兜底，"恢复默认"的目标）
    """

    TITLE_CLEAN = """从以下视频文件名中提取影视作品的标题和上映年份。
注意：文件名可能包含制作组名、分辨率、编码信息等干扰项，年份可能是标题的一部分而非上映年份。
请按以下JSON格式返回，不要返回其他内容：
{"title": "标题", "year": 年份或null}"""

    MATCH_ASSIST = """你是一个影视元数据匹配助手。当前正在为一个视频文件匹配影视元数据，
但 Provider（TMDB等）搜索后未找到精确匹配结果。

请根据以下信息，分析该文件可能对应的影视作品，建议更准确的搜索关键词。

分析策略：
1. 优先从上级文件夹名推断影视标题（文件夹名通常比文件名更准确）
2. 从同级文件名中寻找关联信息（如季集编号、系列名）
3. 如果文件名含年份但搜索无结果，尝试去掉年份重新搜索
4. 如果文件名是英文缩写，尝试展开完整名称

输出要求：
返回 JSON:
{"suggested_query": "建议的搜索关键词", "confidence": 0.8, "reason": "判断理由"}

如果无法建议有效关键词，设置 confidence < 0.5 并说明原因。"""

    DIMENSION_MAPPING = """你是一个专业的影视信息分析助手。根据Provider返回的数据，将复杂数据映射为标准维度值。

重要原则：
1. 只根据提供的Provider数据进行分析，不要编造信息
2. 如果数据不足以判断，将该维度设为空字符串 ""
3. 严格按照维度值列表选择，不要创造新值

输出要求：
返回 JSON，只包含需要映射的维度:
{"维度名": "值或空字符串", ...}"""

    SOURCE_CLEAN = """你是"影音库AI智能整理"系统的源目录清理助手。
根据提供的文件列表和规则，判断哪些是垃圾文件需要清理。

判断原则：
1. 样本文件（Sample/sample）通常是垃圾
2. 预览/广告视频通常是垃圾
3. 小于阈值的视频文件可能是样本
4. NFO、字幕、封面图片等属于媒体相关文件，不应清理
5. 不确定时保守处理，标记为保留"""

    DIMENSION_SUPPLEMENT = """你是一个影视信息搜索助手。根据提供的影视作品信息，联网搜索补充缺失的维度值。

重要原则：
1. 只补充明确缺失的维度，不要修改已有值
2. 搜索结果应来自权威数据源（豆瓣、TMDB、IMDb、维基百科）
3. 如果搜索后仍无法确定，将该维度设为空字符串 ""
4. 不要猜测或编造信息

输出要求：
返回 JSON，只包含需要补充的维度:
{"维度名": "值或空字符串", ...}"""

    @classmethod
    def get_all(cls) -> dict:
        return {
            "title_clean": cls.TITLE_CLEAN,
            "match_assist": cls.MATCH_ASSIST,
            "dimension_mapping": cls.DIMENSION_MAPPING,
            "source_clean": cls.SOURCE_CLEAN,
            "dimension_supplement": cls.DIMENSION_SUPPLEMENT,
        }
```

**验证**：`python -c "from media_importer.features.prompts.defaults import PromptDefaults; print(list(PromptDefaults.get_all().keys()))"` 输出 `['title_clean', 'match_assist', 'dimension_mapping', 'source_clean', 'dimension_supplement']`。

---

### T1.7 新增 /api/config/prompt-defaults API

**文件**：`media_importer/api/config_handlers.py`

**操作**：

新增 API handler：

```python
def handle_get_prompt_defaults(handler) -> dict:
    """GET /api/config/prompt-defaults — 返回所有默认提示词。"""
    from media_importer.features.prompts.defaults import PromptDefaults
    return PromptDefaults.get_all()
```

在路由注册处新增路由。

**验证**：启动服务后 `curl http://localhost:9855/api/config/prompt-defaults` 返回 JSON。

---

### T1.8 Phase 1 验证

**操作**：

1. 编译检查：`PYTHONPYCACHEPREFIX=/private/tmp/nas_media_manage_pycache python -m compileall -q media_importer`
2. 启动服务验证：`PYTHONPATH="${PWD}" python -m media_importer.media_importer -c config/config.yaml serve -p 9855 --host 0.0.0.0`
3. 检查 DB schema 包含新字段
4. 检查旧配置迁移正常（llm → ai_assist + ai_search）
5. 检查 `/api/config/prompt-defaults` API 可用
6. 运行非 UI 测试：`python -m pytest tests/ --ignore=tests/test_*_ui.py --ignore=tests/test_frontend_*.py --ignore=tests/test_scrape_ui.py`

**退出标准**：
- 编译通过
- 服务可正常启动
- DB 新字段存在
- 旧配置自动迁移
- prompt-defaults API 可用
- 现有测试无回归

---

## Phase 2：UI 重写

**✅ 状态**：已完成（前端控件齐全，T2.1-T2.7 均已实现），**但后端数据源未完全连通（HFT-3）**。

**目标**：重写前端 AI 配置界面、维度信任配置、模拟刮削展示、任务卡片刮削过程。依赖 Phase 1 的 API 和 DB 变更。

### T2.1 替换刮削模式卡片为展示卡

**文件**：`media_importer/webui/index.html`

**操作**：

1. 找到 `scrape-mode-card` 或刮削模式相关的 HTML 区块
2. 替换为纯信息展示卡（无输入控件，默认折叠的手风琴）

参考设计方案第 2 章的展示卡布局，包含：
- 标题清洗说明
- 匹配路径三级说明
- 维度确认三级说明
- 维度完整性判定说明
- 人工复核说明

**文件**：`media_importer/webui/js/cinema-config.js`

**操作**：

1. 删除 `saveScrapeModeConfig()` 函数
2. 删除与刮削模式下拉相关的所有事件绑定

---

### T2.2 重写 AI 辅助配置区块

**文件**：`media_importer/webui/index.html`

**操作**：

替换当前 LLM 配置区块为 AI 辅助区块，包含：
- 使用说明手风琴（默认折叠）
- 模型URL输入框
- 模型ID输入框
- API Key输入框
- AI辅助测试按钮
- 高级选项折叠区（超时/重试/重试间隔/SSL验证 + 提示词分页签）

**文件**：`media_importer/webui/js/cinema-config.js`

**操作**：

1. 新增 `buildAiAssistPayload()` 函数，从表单收集 ai_assist 配置
2. 修改保存逻辑，调用 `build_section_config_update("ai_assist", ...)`
3. 新增高级选项折叠交互
4. 新增提示词分页签切换逻辑
5. 新增"恢复默认"按钮逻辑：从 `/api/config/prompt-defaults` 获取默认值填入

---

### T2.3 新增 AI联网搜索增强配置区块

**文件**：`media_importer/webui/index.html`

**操作**：

新增 AI联网搜索增强区块，包含：
- 启用开关
- 使用说明手风琴（默认折叠）
- 模型厂商下拉（zhipu/qwen/moonshot）
- 模型下拉（根据厂商联动）
- 搜索类型下拉（根据厂商联动，映射 SEARCH_TYPE_MAP）
- API Key输入框
- 测试连通性 + AI联网搜索增强测试按钮
- 高级选项折叠区（接口地址/超时/重试/重试间隔/SSL验证 + 缺失维度搜索提示词）

**文件**：`media_importer/webui/js/cinema-config.js`

**操作**：

1. 新增 `buildAiSearchPayload()` 函数
2. 新增 `onProviderChange()` 联动函数：厂商变化时更新模型列表和搜索类型列表
3. 新增搜索类型映射数据（前端硬编码 `SEARCH_TYPE_MAP`，与后端保持一致）
4. 修改保存逻辑，调用 `build_section_config_update("ai_search", ...)`
5. 开关关闭时，禁用下方所有输入控件

---

### T2.4 维度配置新增信任开关

**文件**：`media_importer/webui/js/cinema-dimensions.js`

**操作**：

1. 每个维度卡片新增两个开关：
   - "信任AI辅助映射" checkbox（`trust_ai_assist`，默认勾选）
   - "信任AI联网搜索" checkbox（`trust_ai_search`，默认不勾选）
2. 保存维度时包含 `trust_ai_assist` 和 `trust_ai_search` 字段
3. `media_type` 维度：两个开关都勾选且禁用（因为由 Provider 端点硬编码，不走 AI）

**文件**：`media_importer/webui/index.html`

**操作**：

在维度编辑弹窗/卡片中新增信任开关的 HTML。

---

### T2.5 模拟刮削重写

**文件**：`media_importer/webui/js/cinema-config.js`

**操作**：

1. 重写模拟刮削展示逻辑，改为展示每个维度的来源路径
2. 每个维度显示：值 + 来源图标（🗄️/📚/🤖/🔍/📄）+ 来源说明
3. 展示匹配路径（第一级/第二级/第三级）
4. 展示维度确认路径（Provider映射/AI辅助/AI联网搜索）

**文件**：`media_importer/api/tmdb_handlers.py`

**操作**：

1. 修改 `_scrape_preview` 返回结构，新增 `dim_sources` 字段
2. 每个维度返回 `{"value": "movie", "source": "provider", "source_label": "TMDB搜索端点"}`

---

### T2.6 任务卡片展示 confirm_reason + 刮削过程展开区

**文件**：`media_importer/webui/js/cinema-tasks.js`

**操作**：

1. 待确认任务展示 `confirm_reason`（如"维度缺失: 限制级分类；AI补充需确认: 地区(AI联网搜索)"）
2. 新增"刮削过程"展开按钮
3. 展开后显示每个维度的来源图标和说明
4. 使用 `dim_sources` JSON 数据渲染

---

### T2.7 CSS 样式

**文件**：`media_importer/webui/css/cinema-config.css`

**操作**：

1. 展示卡样式（纯信息展示，折叠/展开）
2. 手风琴样式（使用说明区域）
3. 高级选项折叠样式
4. 维度来源图标样式（不同来源不同颜色）
5. AI联网搜索增强开关样式
6. 提示词分页签样式
7. 刮削过程展开区样式

---

### T2.8 Phase 2 验证

**操作**：

1. 启动服务，打开前端页面
2. 验证刮削模式展示卡（无输入控件，可折叠）
3. 验证 AI 辅助配置：输入 URL/模型ID/API Key → 保存 → 刷新后值保留
4. 验证 AI联网搜索增强：开关、厂商下拉联动、搜索类型联动、保存
5. 验证维度信任开关：勾选/取消 → 保存 → 刷新后值保留
6. 验证模拟刮削：展示每个维度来源路径
7. 验证任务卡片：confirm_reason 展示、刮削过程展开
8. 验证提示词分页签切换和"恢复默认"
9. 运行编译检查

**退出标准**：
- 前端所有新控件功能正常
- 配置保存/读取正确
- 模拟刮削展示维度来源
- 任务卡片展示刮削过程
- 无 JS 控制台错误

---

## Phase 3：刮削逻辑切换

**⚠️ 状态**：部分完成。T3.1（配置源切换）、T3.2（search_type）**待通过 HF-1 实现**；T3.3-T3.8 未实现（正式维度三级来源逻辑未落地）。

**目标**：将刮削逻辑从旧 `llm` 配置切换到 `ai_assist` / `ai_search`，实现维度确认三级流程、confirm_reason 生成、第二级循环清洗。依赖 Phase 1 + 2。

### T3.1 llm_scraper.py 配置源切换

**文件**：`media_importer/scraper/llm_scraper.py`

**操作**：

1. 修改构造函数，优先读 `ai_search` / `ai_assist`，fallback 到 `llm`：

```python
def __init__(self, config: dict):
    # 优先使用新配置
    ai_assist = config.get("ai_assist", {})
    ai_search = config.get("ai_search", {})
    llm = config.get("llm", {})

    # AI辅助模型
    self.fast_model = ai_assist.get("model") or llm.get("fast_model") or llm.get("model", "")
    self.fast_base_url = ai_assist.get("base_url") or llm.get("fast_base_url") or llm.get("base_url", "")
    self.fast_api_key = ai_assist.get("api_key") or llm.get("fast_api_key") or llm.get("api_key", "")

    # AI联网搜索增强模型
    self.model = ai_search.get("model") or llm.get("model", "")
    self.base_url = ai_search.get("base_url") or llm.get("base_url", "")
    self.api_key = ai_search.get("api_key") or llm.get("api_key", "")

    # Web搜索配置
    from media_importer.features.scraping.web_search_config import build_web_search_config
    self.web_search_config = build_web_search_config(ai_search or llm.get("web_search", {}))

    # 其他参数
    self.timeout = ai_assist.get("timeout") or llm.get("timeout", 30)
    self.max_retries = ai_assist.get("max_retries") or llm.get("max_retries", 2)
    self.verify_ssl = ai_assist.get("verify_ssl", True) if ai_assist.get("verify_ssl") is not None else llm.get("verify_ssl", True)
```

2. 删除 `confidence_threshold` 相关代码

---

### T3.2 _inject_search() 新增 search_type 参数

**文件**：`media_importer/scraper/llm_scraper.py`

**操作**：

修改 `_inject_search()` 方法，根据 `web_search_config.search_type` 注入搜索参数：

```python
def _inject_search(self, messages: list, model: str = None) -> tuple:
    """注入联网搜索参数。返回 (messages, kwargs)。"""
    config = self.web_search_config
    if not config.should_search("scrape"):
        return messages, {}

    provider = config.detected_provider
    search_type = config.effective_search_type()
    kwargs = {}

    if provider == "zhipu":
        tools = [{"type": "web_search", "web_search": {"search_type": search_type or "search_std"}}]
        kwargs["tools"] = tools
    elif provider == "qwen":
        kwargs["enable_search"] = True
        if search_type == "forced_search":
            kwargs["search_options"] = {"forced_search": True}
    elif provider == "moonshot":
        tools = [{"type": "builtin_function", "function": {"name": "$web_search"}}]
        kwargs["tools"] = tools

    return messages, kwargs
```

---

### T3.3 第二级匹配改为AI建议关键词 + 循环回第一级

**文件**：`media_importer/features/scraping/match_engine.py`

**操作**：

1. 修改 `_tier2_context_match()` 方法：

```python
def _tier2_context_match(self, clean_result, providers, filename, max_loops=2):
    """第二级：上下文辅助匹配（循环清洗机制）。

    流程：
    1. 收集上下文（上级文件夹名、同级文件名）
    2. AI辅助模型分析上下文，建议新搜索关键词
    3. 用新关键词回到第一级重新搜索
    4. 如果精确匹配成功 → AUTO_PASS
    5. 如果仍无精确匹配 → 取排名第一 + 疑虑标记 → 第三级
    """
    for loop in range(max_loops):
        # 收集上下文
        context = self._collect_context(filename)

        # AI建议新关键词
        suggested = self._ai_suggest_keyword(clean_result, context, providers)
        if not suggested or suggested.get("confidence", 0) < 0.5:
            break

        new_query = suggested["suggested_query"]
        # 用新关键词重新搜索
        result = self._tier1_exact_match_with_query(new_query, clean_result, providers)
        if result and result.match_level == "AUTO_PASS":
            return result

        # 更新 clean_result 用于下一轮
        clean_result = clean_result._replace(clean_title=new_query)

    # 循环结束仍无精确匹配 → 取排名第一 + 疑虑标记
    return self._tier3_user_confirm(clean_result, providers)
```

2. 新增 `_ai_suggest_keyword()` 方法，使用 AI辅助模型 + 匹配辅助提示词

3. 新增 `_collect_context()` 方法（从旧计划迁移）

---

### T3.4 维度确认三级流程实现

**文件**：`media_importer/scraper/metadata_scrape_flow.py`

**操作**：

1. 删除 `ai_only` 分支
2. 在匹配成功后，实现维度确认三级流程：

```python
def _resolve_dimensions(self, provider_details, dim_configs, conn, provider_type):
    """维度确认三级流程。"""
    dim_sources = {}
    dim_values = {}

    for dim in dim_configs:
        if not dim.get("is_enabled"):
            continue
        dim_name = dim["name"]
        value = None
        source = "unknown"

        # 第一级：Provider 直接映射
        value = self._provider_map_dimension(dim, provider_details, provider_type)
        if value is not None:
            dim_values[dim_name] = value
            dim_sources[dim_name] = f"provider:{provider_type}"
            continue

        # 第二级：AI辅助模型分析
        value = self._ai_assist_map_dimension(dim, provider_details)
        if value is not None:
            dim_values[dim_name] = value
            dim_sources[dim_name] = "ai_assist"
            continue

        # 第三级：AI联网搜索增强
        if self.ai_search_enabled:
            value = self._ai_search_map_dimension(dim, provider_details)
            if value is not None:
                dim_values[dim_name] = value
                dim_sources[dim_name] = "ai_search"
                continue

        # 仍无法获取 → 维度值为空
        dim_values[dim_name] = None
        dim_sources[dim_name] = "unknown"

    return dim_values, dim_sources
```

3. `_provider_map_dimension()` 调用已有的 `map_provider_to_dimension()`
4. `_ai_assist_map_dimension()` 使用 AI辅助模型 + 维度映射提示词
5. `_ai_search_map_dimension()` 使用 AI联网搜索增强 + 缺失维度搜索提示词

---

### T3.5 维度值来源追踪（dim_sources）

**文件**：`media_importer/features/import_flow/steps/scrape.py`

**操作**：

1. 在 `_step_scrape()` 中保存 `dim_sources` 到 task 和 DB：

```python
task.dim_sources = json.dumps(dim_sources, ensure_ascii=False)
```

2. 确保 `task_repo.py` 的更新方法包含 `dim_sources` 字段

---

### T3.6 生成 confirm_reason

**文件**：`media_importer/features/scraping/match_engine.py` 或 `metadata_scrape_flow.py`

**操作**：

实现设计方案第 5.5 节的 `_determine_match_level()` 函数：

```python
def _determine_match_level(result: dict, enabled_dims: list, dim_sources: dict) -> tuple:
    """基于维度完整性和信任配置判定匹配级别。

    Returns:
        (match_level, confirm_reason)
    """
    reasons = []
    missing_dims = []
    untrusted_ai_dims = []

    for dim in enabled_dims:
        dim_name = dim["name"]
        dim_label = dim.get("label", dim_name)
        value = result.get(dim_name)
        source = dim_sources.get(dim_name, "unknown")
        trust_ai_assist = dim.get("trust_ai_assist", 1)
        trust_ai_search = dim.get("trust_ai_search", 0)

        if value is None or value == "" or value == "unknown":
            missing_dims.append(dim_label)
            continue

        if source == "ai_assist" and not trust_ai_assist:
            untrusted_ai_dims.append(f"{dim_label}(AI辅助)")
        elif source == "ai_search" and not trust_ai_search:
            untrusted_ai_dims.append(f"{dim_label}(AI联网搜索)")

    if missing_dims:
        reasons.append(f"维度缺失: {', '.join(missing_dims)}")
    if untrusted_ai_dims:
        reasons.append(f"AI补充需确认: {', '.join(untrusted_ai_dims)}")

    if not reasons:
        return "AUTO_PASS", ""
    return "NEEDS_CONFIRM", "；".join(reasons)
```

---

### T3.7 删除 _scrape_ai_only() 分支

**文件**：`media_importer/scraper/metadata_scrape_flow.py`

**操作**：

1. 删除 `ai_only` 模式分支代码
2. 删除 `scrape_mode` 参数判断
3. 统一为 `provider_first` 流程

---

### T3.8 review.py 改为基于 match_level + confirm_reason

**文件**：`media_importer/features/import_flow/services/review.py`

**操作**：

修改 `evaluate()` 方法：

```python
def evaluate(self, scraped: dict) -> ReviewDecision:
    match_level = scraped.get("match_level", "NEEDS_CONFIRM")
    confirm_reason = scraped.get("confirm_reason", "")

    if match_level == "AUTO_PASS":
        return ReviewDecision(action="continue")

    if match_level == "NEEDS_CONFIRM":
        reason = confirm_reason or "需要人工确认"
        return ReviewDecision(action="confirm", reason=reason)

    return ReviewDecision(action="failed", reason="匹配失败，无法识别")
```

---

### T3.9 Phase 3 验证

**操作**：

1. 编译检查
2. 启动服务，完整走一遍刮削流程：
   - 输入文件名 → 标题清洗 → 匹配 → 维度确认 → 入库
3. 验证维度确认三级流程：
   - Provider 直接映射的维度标记为 `provider:tmdb`
   - AI辅助映射的维度标记为 `ai_assist`
   - AI联网搜索的维度标记为 `ai_search`
4. 验证 confirm_reason 生成：
   - 维度缺失时生成"维度缺失: xxx"
   - 不信任AI来源时生成"AI补充需确认: xxx"
5. 验证第二级循环清洗：
   - AI建议关键词 → 重新搜索 → 精确匹配成功
   - AI建议关键词 → 重新搜索 → 仍无精确匹配 → 取排名第一
6. 验证 AI联网搜索增强开关：
   - 关闭后维度补全只走 Provider + AI辅助
7. 运行非 UI 测试
8. 运行架构护栏测试

**退出标准**：
- 完整刮削流程正常
- 维度来源追踪正确
- confirm_reason 生成正确
- 第二级循环清洗正常
- AI联网搜索增强开关生效
- 无测试回归

---

## 附录 A：文件变更清单

| 文件 | Phase | 变更类型 |
|------|-------|----------|
| `core/config_view.py` | 1 | 新增 AiAssistConfig/AiSearchConfig dataclass |
| `features/configuration/application_service.py` | 1 | SECTION_FIELD_MAP 新增 ai_assist/ai_search |
| `core/config_migrations.py` | 1 | 新增 _migrate_llm_to_ai_config() |
| `core/config_loader.py` | 1 | 调用迁移函数 |
| `features/scraping/web_search_config.py` | 1 | 新增 search_type + SEARCH_TYPE_MAP + build_web_search_config() |
| `core/db/connection.py` | 1 | DB schema 新增字段 |
| `core/db/constants.py` | 1 | DEFAULT_DIMENSIONS 新增 trust_ai_assist/trust_ai_search |
| `core/db/dimension_repo.py` | 1 | 读写新字段 |
| `core/db/task_repo.py` | 1 | 读写新字段 |
| `features/prompts/defaults.py` | 1 | **新建** 默认提示词常量 |
| `api/config_handlers.py` | 1 | 新增 prompt-defaults API |
| `webui/index.html` | 2 | 重写 AI 配置区块 |
| `webui/js/cinema-config.js` | 2 | 重写保存/联动逻辑 |
| `webui/js/cinema-dimensions.js` | 2 | 新增信任开关 |
| `webui/js/cinema-tasks.js` | 2 | confirm_reason + 刮削过程展开 |
| `webui/css/cinema-config.css` | 2 | 新增样式 |
| `api/tmdb_handlers.py` | 2 | _scrape_preview 返回 dim_sources |
| `scraper/llm_scraper.py` | 3 | 配置源切换 + search_type |
| `features/scraping/match_engine.py` | 3 | 第二级循环清洗 + confirm_reason |
| `scraper/metadata_scrape_flow.py` | 3 | 维度确认三级 + 删除 ai_only |
| `features/import_flow/steps/scrape.py` | 3 | 保存 dim_sources + confirm_reason |
| `features/import_flow/services/review.py` | 3 | 基于 match_level + confirm_reason |

## 附录 B：关键数据结构

### ai_assist 配置（YAML）

```yaml
ai_assist:
  base_url: ""
  model: ""
  api_key: ""
  timeout: 30
  max_retries: 2
  retry_delay: 3
  verify_ssl: true
  prompt_title_clean: ""
  prompt_match_assist: ""
  prompt_dimension_mapping: ""
  prompt_source_clean: ""
```

### ai_search 配置（YAML）

```yaml
ai_search:
  enabled: true
  provider: ""
  model: ""
  search_type: ""
  api_key: ""
  base_url: ""
  timeout: 30
  max_retries: 2
  retry_delay: 3
  verify_ssl: true
  prompt_dimension_supplement: ""
```

### dim_sources（JSON，存入 tasks 表）

```json
{
  "media_type": "provider:tmdb",
  "documentary": "provider:tmdb",
  "restricted_level": "ai_assist",
  "animation": "provider:tmdb",
  "region": "provider:tmdb",
  "origin_lang": "provider:tmdb",
  "resolution_tier": "file",
  "broad_genre": "provider:tmdb"
}
```

### confirm_reason 格式

```
维度缺失: 限制级分类, 题材类型；AI补充需确认: 地区(AI联网搜索)
```

### 搜索类型映射

| 厂商 | search_type 值 | API 参数 |
|------|---------------|----------|
| zhipu | search_std | `tools.web_search.search_type: "search_std"` |
| zhipu | search_pro | `tools.web_search.search_type: "search_pro"` |
| qwen | enable_search | `enable_search: true` |
| qwen | forced_search | `enable_search: true, search_options: {forced_search: true}` |
| moonshot | web_search | `tools: [{type: "builtin_function", function: {name: "$web_search"}}]` |

## 附录 C：维度来源图标映射

| source 值 | 图标 | CSS class | 颜色 |
|-----------|------|-----------|------|
| provider:tmdb | 🗄️ | `dim-source-provider-tmdb` | #3b82f6 |
| provider:douban | 📚 | `dim-source-provider-douban` | #10b981 |
| ai_assist | 🤖 | `dim-source-ai-assist` | #8b5cf6 |
| ai_search | 🔍 | `dim-source-ai-search` | #f59e0b |
| file | 📄 | `dim-source-file` | #6b7280 |
| unknown | — | `dim-source-unknown` | #ef4444 |
