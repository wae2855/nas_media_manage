# 刮削器 Provider 抽象：TMDB 解耦与多源支持方案（v2）

> **状态：✅ 已实施完成** | 实施日期：2026-05-28
>
> 本方案已完成全部三个阶段的实施：后端核心抽象 → API 层泛化 → 前端 UI 泛化。
> 新增 Provider 只需：1) 实现 MetadataProvider 子类 2) @register_provider 装饰 3) 配置启用。
> 详见 `media_importer/scraper/providers/` 目录。

## 问题陈述

当前系统中 TMDB 作为唯一的元数据外部来源，深度嵌入到从刮削、置信度计算、维度映射、API 服务到前端 UI 的全链路中（约 200+ 处耦合点，涉及 20+ 个文件）。如果未来要添加新的刮削 API（如 IMDB、豆瓣等），改动量极大且容易遗漏。

**目标**：抽象出 `MetadataProvider` 接口层，将 TMDB 从"硬编码的唯一选择"变为"第一个 Provider 实现"，使未来新增刮削源只需：
1. 实现一个 `MetadataProvider` 子类
2. 用 `@register_provider` 装饰器注册
3. 在配置中启用
4. 前端自动渲染对应配置面板

**新增 Provider 时不应修改的文件**：`metadata_scraper.py`、`confidence_engine.py`、`llm_scraper.py`、`dimension_manager.py`

---

## 当前耦合全景

### 按层级统计

| 层级 | 文件 | 耦合点数 | 耦合程度 |
|------|------|----------|----------|
| scraper | tmdb_client.py | 整个文件(170行) | 极高 - 100% TMDB 专属 |
| scraper | metadata_scraper.py | ~20处 | 极高 - 核心流程依赖 |
| scraper | dimension_manager.py | ~15处 | 高 - 字段名/genre ID硬编码 |
| scraper | confidence_engine.py | ~10处 | 高 - 配置键/字段访问 |
| scraper | llm_scraper.py | ~15处 | 高 - TMDB提示词常量 |
| pipeline | steps.py / runner.py | 0处 | 无 - 仅通过scraper间接 |
| api | handler.py | 10个路由 | 高 - TMDB专属API |
| api | config_handlers.py | ~20处 | 极高 - 直接实例化TMDbClient |
| api | dimension_handlers.py | 1处 | 低 |
| api | prompt_handlers.py | 6处 | 中 |
| db | constants.py | ~30处 | 极高 - DEFAULT_DIMENSIONS |
| db | dimension_repo.py | ~10处 | 中 |
| config | config_loader.py | 8处 | 中 |
| webui | index.html | 34处 | 高 |
| webui | tmdb-dict.js | 整个文件(85行) | 极高 - 100% TMDB专属 |
| webui | config.js | ~15处 | 高 |
| webui | dimensions.js | ~8处 | 高 |
| webui | tasks.js | 2处 | 低 |

### 核心耦合模式分类

**A. 直接实例化/导入**
- `metadata_scraper.py` 直接 `from .tmdb_client import TMDbClient, TMDbError`
- `config_handlers.py` 直接 `from media_importer.scraper.tmdb_client import TMDbClient`
- `prompt_handlers.py` 引用 `LLMScraper.TMDB_CONTEXT_PROMPT`

**B. 配置键硬编码**
- `metadata.tmdb` 配置路径
- `tmdb_match_threshold` 配置键
- `source_priority: ["tmdb", "ai", "file"]`
- `source_type: "ai+tmdb"` 维度类型

**C. 字段名硬编码**
- `tmdb_field`（数据库列、维度配置）
- `tmdb_genre_ids`、`tmdb_codes`（value_list 中的映射键）
- `title/name/original_title/original_name/release_date/first_air_date`（TitleMatcher 访问的字段名）

**D. API 路由硬编码**
- 10 个 `/api/tmdb/*` 和 `/api/config/test-tmdb` 路由
- 前端直接调用这些硬编码路由

**E. UI 硬编码**
- TMDB 配置面板（API Key、语言、测试、预览）
- 维度来源信任只列出 TMDB/AI/FILE 三行
- TMDB 提示词编辑器
- `tmdb-dict.js` 字段翻译字典
- CSS `.tmdb-*` 样式类（47处）

---

## 方案设计

### 核心思路：三层解耦 + 注册表模式

```
┌──────────────────────────────────────────────┐
│          配置层 (config.yaml)                  │
│  metadata.providers:                          │
│    - type: tmdb                               │
│      enabled: true                            │
│      api_key: xxx                             │
│    - type: imdb  (未来)                        │
│      enabled: false                           │
├──────────────────────────────────────────────┤
│          Provider 抽象层                       │
│  MetadataProvider (ABC)                       │
│  ├── @register_provider 自动注册到注册表       │
│  ├── TMDbProvider                             │
│  ├── IMDBProvider (未来)                       │
│  └── DoubanProvider (未来)                     │
├──────────────────────────────────────────────┤
│          消费层 (不变)                          │
│  MetadataScraper → 从注册表获取 Provider       │
│  DimensionManager → 通过 provider_mappings 映射│
│  ConfidenceEngine → 不感知 Provider 类型       │
│  LLMScraper → 接收标准 context，不感知来源     │
└──────────────────────────────────────────────┘
```

---

### 第一层：MetadataProvider 抽象接口 + 注册表

定义在 `scraper/providers/base.py`：

```python
from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Any
from dataclasses import dataclass


@dataclass
class Genre:
    id: str
    name: str


@dataclass
class SearchItem:
    provider_type: str
    item_id: str
    title: str
    original_title: str
    year: Optional[int]
    media_type: str
    poster_url: Optional[str]
    vote_average: Optional[float]
    raw_data: dict


@dataclass
class SearchResult:
    items: List[SearchItem]
    total_results: int


@dataclass
class MediaDetails:
    provider_type: str
    item_id: str
    media_type: str
    title: str
    original_title: str
    year: Optional[int]
    genres: List[Genre]
    overview: str
    vote_average: float
    origin_country: List[str]
    original_language: str
    adult: bool
    tagline: str
    poster_url: str
    raw_data: dict
    rating_info: Optional[dict] = None


@dataclass
class DimensionMapping:
    name: str
    value: Any
    confidence: float
    source: str


class MetadataProvider(ABC):

    @property
    @abstractmethod
    def provider_type(self) -> str:
        """Provider 类型标识，如 'tmdb', 'imdb'"""

    @property
    @abstractmethod
    def display_name(self) -> str:
        """显示名称，如 'TMDb', 'IMDb'"""

    @abstractmethod
    def search(self, query: str, year: Optional[int] = None,
               media_type: Optional[str] = None) -> SearchResult:
        """搜索影视，返回标准化结果"""

    @abstractmethod
    def get_details(self, item_id: str, media_type: str) -> MediaDetails:
        """获取详情，返回标准化结构"""

    @abstractmethod
    def get_genres(self, media_type: Optional[str] = None) -> list:
        """获取类型列表"""

    @abstractmethod
    def test_connection(self) -> bool:
        """测试连接"""

    @abstractmethod
    def map_dimensions(self, dim_configs: list, details: MediaDetails) -> List[DimensionMapping]:
        """根据维度配置，将 Provider 数据映射到维度值"""

    @classmethod
    def get_config_schema(cls) -> dict:
        """返回该 Provider 的配置字段定义，供前端动态渲染"""
        return {"fields": []}

    def get_context_template(self) -> str:
        """返回该 Provider 的 AI 上下文提示词模板"""
        return (
            "系统已通过 {provider_name} API 获取到该影视作品的元数据，"
            "请基于这些数据整理为系统所需的格式化信息。\n\n"
            "重要原则：\n"
            "1. {provider_name} 数据是优先参考来源，标题、年份、类型等基础信息优先采用。\n"
            "2. 若 {provider_name} 数据不完整或存疑，请结合你的知识进行补充判断。\n"
            "3. 如果 {provider_name} 数据与文件名信息有冲突，以 {provider_name} 数据为准，但季/集编号以文件名为准。\n"
        )

    def get_prompt_file_name(self) -> str:
        """返回该 Provider 的提示词文件名（不含路径）"""
        return f"{self.provider_type}_prompts.md"
```

**关键设计决策**：

1. `Genre.id` 类型为 `str`（解决 P1-6：不同 Provider 的 ID 格式不同，TMDB 是整数但 IMDB 可能是字符串）
2. `SearchItem` 标准化了 `title`/`original_title`/`year`，`TitleMatcher` 不再需要访问 Provider 原始字段名（解决 P1-5）
3. `raw_data` 字段保留 Provider 原始返回数据，供深度匹配和调试
4. `rating_info` 不强制格式，由各 Provider 的 `map_dimensions` 方法自行解析
5. `get_config_schema()` 类方法返回配置字段定义，供前端动态渲染（解决 P1-7）
6. `get_context_template()` 返回通用提示词模板，不再硬编码 TMDB（解决 P1-8）
7. `get_prompt_file_name()` 返回提示词文件名，支持每个 Provider 独立提示词文件（解决 P1-9）

**注册表模式**（解决 P0-1）：

定义在 `scraper/providers/__init__.py`：

```python
from typing import Dict, Type
from .base import MetadataProvider

_PROVIDER_REGISTRY: Dict[str, Type[MetadataProvider]] = {}


def register_provider(cls: Type[MetadataProvider]) -> Type[MetadataProvider]:
    _PROVIDER_REGISTRY[cls.provider_type] = cls
    return cls


def get_provider_class(provider_type: str) -> Optional[Type[MetadataProvider]]:
    return _PROVIDER_REGISTRY.get(provider_type)


def get_all_provider_types() -> list:
    return list(_PROVIDER_REGISTRY.keys())


def create_providers(config: dict) -> list:
    providers_config = config.get("metadata", {}).get("providers", [])
    providers = []
    for pconf in providers_config:
        if not pconf.get("enabled", False):
            continue
        cls = get_provider_class(pconf.get("type", ""))
        if cls:
            providers.append(cls(pconf))
    return providers
```

**新增 Provider 的流程**（零修改消费层）：

```python
# scraper/providers/imdb_provider.py（未来新增）
from .base import MetadataProvider, register_provider

@register_provider
class IMDBProvider(MetadataProvider):
    provider_type = "imdb"
    display_name = "IMDb"

    def __init__(self, config: dict):
        ...

    def search(self, query, year=None, media_type=None):
        ...

    # ... 实现其他抽象方法
```

只需在 `providers/__init__.py` 中 import 即可完成注册：

```python
from .tmdb_provider import TMDbProvider  # noqa: F401 — 触发 @register_provider
# 未来: from .imdb_provider import IMDBProvider  # noqa: F401
```

---

### 第二层：TMDbProvider 实现

将现有 `tmdb_client.py` 包装为 Provider（`scraper/providers/tmdb_provider.py`）：

```python
from .base import (
    MetadataProvider, register_provider, SearchResult, SearchItem,
    MediaDetails, Genre, DimensionMapping
)
from ..tmdb_client import TMDbClient, TMDbError


@register_provider
class TMDbProvider(MetadataProvider):
    provider_type = "tmdb"
    display_name = "TMDb"

    def __init__(self, config: dict):
        self._client = TMDbClient(
            api_key=config.get("api_key", ""),
            language=config.get("language", "zh-CN"),
            fallback_language=config.get("fallback_language", "en-US"),
            timeout=config.get("request_timeout", 10),
            max_retries=config.get("max_retries", 3),
        )

    def search(self, query, year=None, media_type=None):
        results = []
        if media_type == "tv" or media_type is None:
            tv_raw = self._client.search_tv_list(query, year=year)
            for item in tv_raw.get("results", []):
                results.append(self._to_search_item(item, "tv"))
        if media_type == "movie" or media_type is None:
            movie_raw = self._client.search_movie_list(query, year=year)
            for item in movie_raw.get("results", []):
                results.append(self._to_search_item(item, "movie"))
        return SearchResult(
            items=results,
            total_results=sum(r.get("total_results", 0) for r in [tv_raw, movie_raw] if r),
        )

    def _to_search_item(self, raw: dict, media_type: str) -> SearchItem:
        date_field = "release_date" if media_type == "movie" else "first_air_date"
        release_date = raw.get(date_field, "")
        year = int(release_date[:4]) if release_date and len(release_date) >= 4 else None
        return SearchItem(
            provider_type="tmdb",
            item_id=str(raw.get("id", "")),
            title=raw.get("title") or raw.get("name", ""),
            original_title=raw.get("original_title") or raw.get("original_name", ""),
            year=year,
            media_type=media_type,
            poster_url=raw.get("poster_path", ""),
            vote_average=raw.get("vote_average"),
            raw_data=raw,
        )

    def get_details(self, item_id, media_type):
        if media_type == "movie":
            raw = self._client.get_movie_details(int(item_id))
        else:
            raw = self._client.get_tv_details(int(item_id))
        return self._to_media_details(raw, media_type)

    def _to_media_details(self, raw: dict, media_type: str) -> MediaDetails:
        date_field = "release_date" if media_type == "movie" else "first_air_date"
        release_date = raw.get(date_field, "")
        year = int(release_date[:4]) if release_date and len(release_date) >= 4 else None
        genres = [Genre(id=str(g.get("id", "")), name=g.get("name", "")) for g in raw.get("genres", [])]
        poster_path = raw.get("poster_path", "")
        poster_url = f"https://image.tmdb.org/t/p/w500{poster_path}" if poster_path else ""
        return MediaDetails(
            provider_type="tmdb",
            item_id=str(raw.get("id", "")),
            media_type=media_type,
            title=raw.get("title") or raw.get("name", ""),
            original_title=raw.get("original_title") or raw.get("original_name", ""),
            year=year,
            genres=genres,
            overview=raw.get("overview", ""),
            vote_average=raw.get("vote_average", 0),
            origin_country=raw.get("origin_country", []),
            original_language=raw.get("original_language", ""),
            adult=raw.get("adult", False),
            tagline=raw.get("tagline", ""),
            poster_url=poster_url,
            raw_data=raw,
            rating_info=self._extract_rating_info(raw),
        )

    def _extract_rating_info(self, raw: dict) -> dict:
        return {"adult": raw.get("adult", False)}

    def get_genres(self, media_type=None):
        return self._client.get_genre_list()

    def test_connection(self):
        return self._client.test_connection()

    def map_dimensions(self, dim_configs, details):
        from ..dimension_manager import map_provider_to_dimension
        release_dates = self._get_release_dates(details.item_id, details.media_type)
        results = []
        for dim_config in dim_configs:
            mapping = map_provider_to_dimension(
                dim_config, details.raw_data, release_dates, provider_type="tmdb"
            )
            if mapping and mapping.get("value") is not None:
                results.append(DimensionMapping(
                    name=mapping["name"],
                    value=mapping["value"],
                    confidence=mapping.get("confidence", 1.0),
                    source="tmdb",
                ))
        return results

    def _get_release_dates(self, item_id, media_type):
        try:
            if media_type == "movie":
                return self._client.get_movie_release_dates(int(item_id))
            else:
                return self._client.get_tv_release_dates(int(item_id))
        except Exception:
            return []

    @classmethod
    def get_config_schema(cls) -> dict:
        return {
            "fields": [
                {"key": "api_key", "label": "API Key", "type": "password", "required": True},
                {"key": "language", "label": "优先语言", "type": "select",
                 "options": [
                     {"value": "zh-CN", "label": "中文"},
                     {"value": "en-US", "label": "英文"},
                     {"value": "ja-JP", "label": "日文"},
                     {"value": "ko-KR", "label": "韩文"},
                 ]},
                {"key": "fallback_language", "label": "回退语言", "type": "select",
                 "options": [
                     {"value": "en-US", "label": "英文"},
                     {"value": "zh-CN", "label": "中文"},
                 ]},
                {"key": "request_timeout", "label": "请求超时(秒)", "type": "number", "default": 10},
                {"key": "max_retries", "label": "最大重试次数", "type": "number", "default": 3},
            ],
        }

    def get_context_template(self) -> str:
        return (
            "系统已通过 TMDb API 获取到该影视作品的元数据，请基于这些数据整理为系统所需的格式化信息。\n\n"
            "重要原则：\n"
            "1. TMDb 数据是优先参考来源，标题、年份、类型等基础信息优先采用 TMDb 数据。\n"
            "2. 若 TMDb 数据不完整或存疑（如缺少某些维度信息、类型标签不够精确），请结合你的知识进行补充判断。例如：TMDb 可能未明确标注是否动漫，但你可以根据作品信息自行判断。\n"
            "3. 如果 TMDb 数据与文件名信息有冲突，以 TMDb 数据为准，但季/集编号以文件名为准。\n\n"
            "【维度判断规则 - 请严格遵循】\n"
            "以下维度的映射数据已自动提取为参考（如为 null 表示未提供），请对每个维度给出判断：\n"
        )
```

**注意**：`tmdb_client.py` 保留不动，TMDbProvider 只是包装层。未来如果需要替换底层 HTTP 客户端，只需修改 TMDbProvider。

---

### 第三层：维度映射泛化（解决 P0-3、P0-4）

**当前问题**：
- `tmdb_field` → 数据库列名硬编码
- `tmdb_genre_ids` → TMDB genre ID 硬编码
- `tmdb_codes` → TMDB 国家代码硬编码
- `get_dimensions_for_tmdb()` 按 `source_type=='ai+tmdb'` 过滤
- `map_tmdb_to_dimension()` 按 `tmdb_field` 值分派

**改造方案**：

#### 3.1 数据库 schema 变更

`dimensions` 表：
- `tmdb_field TEXT` → 保留（向后兼容），但新增 `provider_mappings TEXT`
- `source_type` 值从 `"ai+tmdb"` 改为 `"ai+provider"`

```sql
ALTER TABLE dimensions ADD COLUMN provider_mappings TEXT DEFAULT '';
```

`provider_mappings` 存储格式（JSON）：

```json
// documentary 维度
{
  "tmdb": {
    "field": "genres",
    "match_type": "genre_ids",
    "match_rules": {"true": [99]}
  }
}

// region 维度
{
  "tmdb": {
    "field": "origin_country",
    "match_type": "country_codes",
    "codes": {"us": ["US"], "cn": ["CN"], "hk": ["HK"], "tw": ["TW"], "jp": ["JP"], "kr": ["KR"], "gb": ["GB", "IE"], "fr": ["FR"], "de": ["DE"], "it": ["IT"], "es": ["ES"], "in": ["IN"]}
  }
}

// broad_genre 维度
{
  "tmdb": {
    "field": "genres",
    "match_type": "genre_ids",
    "match_rules": {
      "horror_mystery": {"ids": [27, 9648, 53, 10758], "priority": 1},
      "scifi_fantasy": {"ids": [878, 14, 10765], "priority": 2},
      "action_adventure": {"ids": [28, 12, 10759, 37], "priority": 4},
      "comedy": {"ids": [35], "priority": 5},
      "drama_romance": {"ids": [18, 10749, 80, 36, 10751, 10766, 10770], "priority": 6},
      "other": {"ids": [], "priority": 11}
    }
  }
}

// restricted_level 维度
{
  "tmdb": {
    "field": "release_dates",
    "match_type": "certification"
  }
}

// origin_lang 维度
{
  "tmdb": {
    "field": "original_language",
    "match_type": "direct_match"
  }
}

// 未来添加 IMDB 时
{
  "tmdb": {"field": "genres", "match_type": "genre_ids", "match_rules": {"true": [99]}},
  "imdb": {"field": "genres", "match_type": "genre_names", "match_rules": {"true": ["Documentary"]}}
}
```

#### 3.2 dimension_manager.py 改造

**`get_dimensions_for_tmdb` → `get_dimensions_for_provider`**（解决 P0-4）：

```python
def get_dimensions_for_provider(conn, provider_type: str) -> list:
    from media_importer.core.db import get_enabled_dimensions
    dims = get_enabled_dimensions(conn)
    result = []
    for dim in dims:
        if dim.get('source_type') != 'ai+provider':
            continue
        provider_mappings = dim.get('provider_mappings')
        if not provider_mappings:
            # 向后兼容：回退到 tmdb_field
            if provider_type == 'tmdb' and dim.get('tmdb_field'):
                provider_mappings = _legacy_tmdb_field_to_mapping(dim)
            else:
                continue
        if isinstance(provider_mappings, str):
            try:
                provider_mappings = json.loads(provider_mappings)
            except (json.JSONDecodeError, TypeError):
                continue
        if provider_type in provider_mappings:
            result.append({
                'name': dim['name'],
                'label': dim['label'],
                'source_type': dim['source_type'],
                'provider_mappings': provider_mappings,
                'value_list': dim.get('value_list', []),
            })
    return result


def _legacy_tmdb_field_to_mapping(dim: dict) -> dict:
    """将旧的 tmdb_field + value_list 中的 tmdb_genre_ids/tmdb_codes 转为 provider_mappings"""
    field = dim.get('tmdb_field', '')
    value_list = dim.get('value_list', [])
    if not field:
        return {}
    mapping = {"field": field}
    if field == 'genres':
        mapping["match_type"] = "genre_ids"
        match_rules = {}
        for vl in value_list:
            ids = vl.get('tmdb_genre_ids', [])
            match_rules[vl['value']] = {"ids": ids}
            if 'priority' in vl:
                match_rules[vl['value']]['priority'] = vl['priority']
        mapping["match_rules"] = match_rules
    elif field == 'origin_country':
        mapping["match_type"] = "country_codes"
        codes = {}
        for vl in value_list:
            tmdb_codes = vl.get('tmdb_codes', [])
            if tmdb_codes:
                codes[vl['value']] = tmdb_codes
        mapping["codes"] = codes
    elif field == 'original_language':
        mapping["match_type"] = "direct_match"
    elif field == 'release_dates':
        mapping["match_type"] = "certification"
    return {"tmdb": mapping}
```

**`map_tmdb_to_dimension` → `map_provider_to_dimension`**：

```python
def map_provider_to_dimension(dim_config: dict, provider_data: dict,
                               release_dates: list = None,
                               provider_type: str = "tmdb") -> dict:
    name = dim_config['name']
    provider_mappings = dim_config.get('provider_mappings', {})
    value_list = dim_config.get('value_list', [])

    if isinstance(provider_mappings, str):
        try:
            provider_mappings = json.loads(provider_mappings)
        except (json.JSONDecodeError, TypeError):
            provider_mappings = {}

    mapping = provider_mappings.get(provider_type, {})
    if not mapping:
        # 向后兼容：回退到 tmdb_field
        tmdb_field = dim_config.get('tmdb_field', '')
        if provider_type == 'tmdb' and tmdb_field:
            mapping = _legacy_tmdb_field_to_mapping(dim_config).get('tmdb', {})
        if not mapping:
            return {'name': name, 'value': None, 'confidence': 0}

    match_type = mapping.get('match_type', '')
    field = mapping.get('field', '')

    if match_type == 'genre_ids':
        if name in ('documentary', 'animation'):
            return _map_bool_genre(name, mapping, provider_data)
        else:
            return _map_genre_by_rules(name, mapping, value_list, provider_data)

    if match_type == 'country_codes':
        return _map_region_v2(name, mapping, provider_data)

    if match_type == 'direct_match':
        return _map_origin_lang(name, value_list, provider_data, field)

    if match_type == 'certification':
        return _map_restricted_level(name, value_list, release_dates or [])

    if match_type == 'genre_names':
        # 未来 IMDB 等使用名称匹配的 Provider
        return _map_genre_by_names(name, mapping, provider_data)

    return {'name': name, 'value': None, 'confidence': 0}


def _map_bool_genre(name: str, mapping: dict, provider_data: dict) -> dict:
    match_rules = mapping.get('match_rules', {})
    true_rule = match_rules.get('true', {})
    target_ids = set(true_rule.get('ids', [])) if isinstance(true_rule, dict) else set()

    genres = provider_data.get('genres', [])
    genre_ids = set()
    for g in genres:
        if isinstance(g, dict) and 'id' in g:
            genre_ids.add(str(g['id']))
        elif isinstance(g, int):
            genre_ids.add(str(g))

    if target_ids & genre_ids:
        return {'name': name, 'value': 'true', 'confidence': 1.0}
    elif genre_ids:
        return {'name': name, 'value': 'false', 'confidence': 0.9}
    return {'name': name, 'value': None, 'confidence': 0}


def _map_genre_by_rules(name: str, mapping: dict, value_list: list, provider_data: dict) -> dict:
    match_rules = mapping.get('match_rules', {})
    genres = provider_data.get('genres', [])
    genre_ids = set()
    for g in genres:
        if isinstance(g, dict) and 'id' in g:
            genre_ids.add(str(g['id']))
        elif isinstance(g, int):
            genre_ids.add(str(g))

    sorted_rules = sorted(
        [(val, rule) for val, rule in match_rules.items() if val != 'other'],
        key=lambda x: x[1].get('priority', 99) if isinstance(x[1], dict) else 99
    )

    for val, rule in sorted_rules:
        rule_ids = set(str(i) for i in rule.get('ids', []))
        if rule_ids & genre_ids:
            return {'name': name, 'value': val, 'confidence': 0.9}

    other_rule = match_rules.get('other', {})
    if other_rule:
        return {'name': name, 'value': 'other', 'confidence': 0.9}

    return {'name': name, 'value': 'other', 'confidence': 0.9}


def _map_region_v2(name: str, mapping: dict, provider_data: dict) -> dict:
    origin_countries = provider_data.get('origin_country', [])
    if not origin_countries:
        return {'name': name, 'value': None, 'confidence': 0}
    first_country = origin_countries[0] if isinstance(origin_countries, list) else origin_countries
    codes = mapping.get('codes', {})
    for value, country_codes in codes.items():
        if first_country in country_codes:
            return {'name': name, 'value': value, 'confidence': 1.0}
    return {'name': name, 'value': 'other', 'confidence': 1.0}
```

#### 3.3 数据库迁移（解决 P2-13）

在 `dimension_repo.py` 的 `_migrate_dimensions` 中新增：

```python
def _migrate_to_provider_mappings(conn):
    """将 tmdb_field + value_list 中的 tmdb_genre_ids/tmdb_codes 迁移为 provider_mappings"""
    rows = conn.execute(
        "SELECT name, tmdb_field, value_list, source_type FROM dimensions WHERE tmdb_field IS NOT NULL AND tmdb_field != ''"
    ).fetchall()
    if not rows:
        return

    for row in rows:
        name, tmdb_field, value_list_raw, source_type = row
        try:
            value_list = json.loads(value_list_raw) if value_list_raw else []
        except (json.JSONDecodeError, TypeError):
            value_list = []

        provider_mappings = _build_provider_mappings(tmdb_field, value_list)
        if provider_mappings:
            conn.execute(
                "UPDATE dimensions SET provider_mappings=?, source_type='ai+provider' WHERE name=?",
                (json.dumps(provider_mappings, ensure_ascii=False), name)
            )
            logger.info(f"已迁移维度 {name}: tmdb_field={tmdb_field} → provider_mappings")

    conn.commit()


def _build_provider_mappings(tmdb_field: str, value_list: list) -> dict:
    mapping = {"field": tmdb_field}
    if tmdb_field == 'genres':
        mapping["match_type"] = "genre_ids"
        match_rules = {}
        for vl in value_list:
            ids = vl.get('tmdb_genre_ids', [])
            rule = {"ids": ids}
            if 'priority' in vl:
                rule['priority'] = vl['priority']
            match_rules[vl.get('value', '')] = rule
        mapping["match_rules"] = match_rules
    elif tmdb_field == 'origin_country':
        mapping["match_type"] = "country_codes"
        codes = {}
        for vl in value_list:
            tmdb_codes = vl.get('tmdb_codes', [])
            if tmdb_codes:
                codes[vl['value']] = tmdb_codes
        mapping["codes"] = codes
    elif tmdb_field == 'original_language':
        mapping["match_type"] = "direct_match"
    elif tmdb_field == 'release_dates':
        mapping["match_type"] = "certification"
    else:
        return {}
    return {"tmdb": mapping}
```

---

### 第四层：MetadataScraper 解耦

**当前**：`MetadataScraper.__init__` 直接创建 `TMDbClient`
**改造后**：

```python
from .providers import create_providers

class MetadataScraper:
    def __init__(self, config: dict):
        self.config = config
        self.providers = create_providers(config)
        self.llm_scraper = LLMScraper(config)
        self.confidence_engine = ConfidenceEngine(config.get("confidence", {}))
        self._cleaner = FilenameCleaner()
        self._matcher = TitleMatcher(config.get("confidence", {}))

    def _search_with_match(self, provider, clean_title, year, season, min_threshold=None):
        """通用 Provider 搜索 + 标题匹配（替代 _search_tmdb_with_match）"""
        match_threshold = min_threshold or self.confidence_engine._config.get(
            "provider_match_threshold", 0.85
        )

        search_methods = []
        if season is not None:
            search_methods = [("tv", None), ("movie", None)]
        else:
            search_methods = [("movie", None), ("tv", None)]

        best_match = None
        best_T = 0.0
        best_search_item = None
        best_media_type = None
        best_search_info = None
        consecutive_errors = 0

        for media_type_hint, _ in search_methods:
            try:
                search_result = provider.search(clean_title, year=year, media_type=media_type_hint)
                consecutive_errors = 0
                for item in search_result.items:
                    match_result = self._matcher.match_standard(clean_title, item, year, season)
                    if match_result.T > best_T:
                        best_T = match_result.T
                        best_match = match_result
                        best_search_item = item
                        best_media_type = item.media_type
                        best_search_info = {
                            "query": clean_title,
                            "total_results": search_result.total_results,
                            "provider_type": provider.provider_type,
                            "selected_title": item.title,
                            "selected_original_title": item.original_title,
                            "selected_year": item.year,
                            "title_match_level": match_result.level,
                            "title_similarity": match_result.similarity,
                            "year_match": match_result.year_match,
                            "fallback_used": False,
                            "original_filename": "",
                        }
            except Exception as e:
                consecutive_errors += 1
                _log.warning(f"[provider_search] {provider.provider_type} {media_type_hint} failed: {e}")

            if consecutive_errors >= 2:
                break
            if best_T >= match_threshold:
                break

        # 年份回退搜索
        if best_T < match_threshold and year is not None and consecutive_errors < 2:
            for media_type_hint, _ in search_methods:
                try:
                    search_result = provider.search(clean_title, year=None, media_type=media_type_hint)
                    for item in search_result.items:
                        match_result = self._matcher.match_standard(clean_title, item, year, season)
                        if match_result.T > best_T:
                            best_T = match_result.T
                            best_match = match_result
                            best_search_item = item
                            best_media_type = item.media_type
                            best_search_info = {**best_search_info, "query": clean_title}
                except Exception:
                    pass
                if best_T >= match_threshold:
                    break

        if best_T >= match_threshold and best_search_item:
            return best_search_item, best_media_type, best_match, best_search_info
        return None
```

**`scrape()` 方法改造**（解决 P0-2 多 Provider 维度冲突）：

```python
def scrape(self, video_filename, subtitle_filenames=None, conn=None):
    if subtitle_filenames is None:
        subtitle_filenames = []

    t_start = time.time()
    clean_result = self._cleaner.clean(video_filename)

    match_threshold = self.confidence_engine._config.get("provider_match_threshold", 0.85)
    ai_research_threshold = self.confidence_engine._config.get("confirm_threshold", 0.5)

    # AI 清洗逻辑（与现有相同，略）
    ai_clean_result = None
    # ... year_suspect / cjk_title 逻辑保持不变，只是调用 _search_with_match(provider, ...) 替代 _search_tmdb_with_match

    # 遍历 Provider 搜索
    provider_result = None
    for provider in self.providers:
        search_result = self._search_with_match(provider, clean_result.clean_title, ...)
        if search_result:
            provider_result = (provider, search_result)
            break

    if not provider_result:
        # 所有 Provider 都无结果，降级到纯 AI
        return self._scrape_ai_only(video_filename, subtitle_filenames, clean_result, ...)

    provider, (search_item, media_type, match_result, search_info) = provider_result

    # 获取详情
    try:
        details = provider.get_details(search_item.item_id, media_type)
    except Exception:
        return self._scrape_ai_only(video_filename, subtitle_filenames, clean_result, ...)

    # 维度映射
    provider_dimensions = {'media_type': {'value': media_type, 'confidence': 1.0, 'source': provider.provider_type}}
    if conn:
        dim_configs = get_dimensions_for_provider(conn, provider.provider_type)
        dim_mappings = provider.map_dimensions(dim_configs, details)
        for dm in dim_mappings:
            provider_dimensions[dm.name] = {
                'value': dm.value,
                'confidence': dm.confidence,
                'source': dm.source,
            }

    # 构建 AI 上下文
    context = self._extract_context(details, clean_result)

    # AI 刮削（排除 Provider 已覆盖的维度）
    exclude_dims = set(provider_dimensions.keys())
    try:
        result = self.llm_scraper.scrape_with_context(
            video_filename, subtitle_filenames, context,
            provider_dimensions=provider_dimensions,
            exclude_dims=exclude_dims,
            provider_name=provider.display_name,
            conn=conn,
        )
    except LLMScrapeError:
        result = self.llm_scraper.scrape(video_filename, subtitle_filenames, conn=conn)

    # 合并结果：Provider 维度覆盖 AI 维度
    if provider_dimensions:
        ai_dims = result.get('dimensions', {})
        for dim_name, dim_info in provider_dimensions.items():
            ai_dims[dim_name] = dim_info
        result['dimensions'] = ai_dims

    # 置信度计算
    search_info["original_filename"] = video_filename
    confidence_result = self.confidence_engine.calculate(
        scrape_result=result,
        provider_search_info=search_info,
        clean_result=clean_result,
        ai_clean_result=ai_clean_result,
        match_result=match_result,
        llm_raw_confidence=result.get("confidence"),
        enabled_dims=enabled_dims_set,
    )
    result["confidence"] = confidence_result.final_confidence
    result["scrape_trace"] = confidence_result.scrape_trace
    return result
```

**多 Provider 维度冲突策略**（解决 P0-2）：

当前设计中 `scrape()` 遍历 providers，**第一个达到匹配阈值的 Provider 就进入详情获取 + 维度映射 + AI 刮削流程**。这意味着同一时间只有一个 Provider 参与维度映射，不存在多 Provider 维度冲突。

如果未来需要"多 Provider 并行搜索取最优"（开放问题 2），则需要处理冲突。当前方案选择**按优先级顺序搜索，第一个命中即停**，这是最简单且性能最优的策略。

---

### 第五层：置信度引擎解耦

**改造点**：

1. **`source_priority` 动态化**：从 `metadata.providers` 配置中读取已启用的 provider type 列表
   ```yaml
   confidence:
     provider_match_threshold: 0.85    # 原 tmdb_match_threshold
     source_priority: ["tmdb", "ai", "file"]   # 动态包含所有 provider type
   ```

2. **`TitleMatcher.match()` → `match_standard()`**（解决 P1-5）：新增方法接收标准 `SearchItem`

   ```python
   def match_standard(self, clean_title: str, search_item: SearchItem,
                      year: int = None, season: int = None) -> MatchResult:
       """接收标准化 SearchItem，不再访问 Provider 原始字段"""
       original_title = search_item.original_title
       title = search_item.title
       provider_year = search_item.year

       # 后续匹配逻辑与 match() 相同，只是数据来源从 dict 改为 SearchItem 属性
       clean_norm = _normalize_title(clean_title)
       orig_norm = _normalize_title(original_title)
       title_norm = _normalize_title(title)
       # ... 与现有 match() 逻辑一致
   ```

   保留原 `match()` 方法用于向后兼容（API 层的搜索预览等场景仍传入原始 dict）。

3. **`ScrapeTraceBuilder` 改造**（解决 P2-10）：

   ```python
   trace = {
       "mode": "provider_ai",  # 原 "tmdb_ai"
       "provider_type": tmdb_search_info.get("provider_type", "tmdb"),  # 新增
       "filename_clean": {...},
       "provider_search": tmdb_search_info,  # 原 "tmdb_search"
       # ...
   }
   ```

   前端渲染时同时检查 `tmdb_search` 和 `provider_search`（向后兼容旧数据）。

4. **`tmdb_match_threshold` → `provider_match_threshold`**（解决 P2-12）：

   `config_loader.py` 中：
   ```python
   # 兼容旧配置
   if "tmdb_match_threshold" in confidence and "provider_match_threshold" not in confidence:
       confidence["provider_match_threshold"] = confidence.pop("tmdb_match_threshold")
   confidence.setdefault("provider_match_threshold", 0.7)
   ```

5. **`calculate()` 方法参数重命名**：

   ```python
   def calculate(self, scrape_result, provider_search_info,  # 原 tmdb_search_info
                 clean_result, ai_clean_result=None, match_result=None,
                 llm_raw_confidence=None, enabled_dims=None):
   ```

---

### 第六层：LLMScraper 解耦（解决 P0-3、P1-8、P1-9）

**当前问题**：
- `TMDB_CONTEXT_PROMPT` 硬编码 TMDB 专属概念（id=99, id=16, release_dates）
- `scrape_with_context()` 的 `exclude_dims` 逻辑：`set(tmdb_dimensions.keys())`
- `_build_system_prompt_with_context()` 使用 `self.custom_tmdb_prompt`
- 提示词文件 `tmdb_prompts.md` 硬编码

**改造方案**：

#### 6.1 提示词模板泛化

删除 `TMDB_CONTEXT_PROMPT` 常量。改为由 Provider 提供 `get_context_template()` 方法。

```python
class LLMScraper:
    # 保留 DEFAULT_SYSTEM_PROMPT（纯 AI 模式）
    # 删除 TMDB_CONTEXT_PROMPT

    def __init__(self, config):
        # ... 现有初始化 ...
        self._provider_prompts = {}  # {provider_type: custom_prompt}
        self._load_provider_prompts_from_files()

    def _load_provider_prompts_from_files(self):
        """从 config/{provider_type}_prompts.md 加载各 Provider 的自定义提示词"""
        for provider_type in get_all_provider_types():
            self._provider_prompts[provider_type] = self._load_prompt_file(
                f"{provider_type}_prompts.md"
            )

    def _load_prompt_file(self, filename):
        """通用提示词文件加载"""
        possible_paths = [
            os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        'config', filename),
            os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        '..', 'config', filename),
            f'/vol3/@appdata/nas-media-importer/config/{filename}',
        ]
        SEP = "【维度判断】\n当前需要判断的维度："
        for path in possible_paths:
            if os.path.exists(path):
                try:
                    import yaml
                    with open(path, 'r', encoding='utf-8') as f:
                        data = yaml.safe_load(f)
                    if data and isinstance(data, dict):
                        sp = (data.get('system_prompt') or '').strip()
                        if SEP in sp:
                            sp = sp.split(SEP)[0].strip()
                        if sp:
                            return sp
                except Exception:
                    pass
        return ''

    def scrape_with_context(self, video_filename, subtitle_filenames,
                            provider_context, provider_dimensions=None,
                            exclude_dims=None, provider_name=None,
                            conn=None):
        """
        参数变更：
        - tmdb_context → provider_context
        - tmdb_dimensions → provider_dimensions
        - 新增 exclude_dims（由调用方决定排除哪些维度）
        - 新增 provider_name（用于选择提示词模板）
        """
        if conn:
            self.load_dimensions_from_db(conn)

        if exclude_dims is None:
            exclude_dims = set(provider_dimensions.keys()) if provider_dimensions else set()

        user_content_parts = [
            "视频文件名:",
            video_filename,
            ""
        ]
        if subtitle_filenames:
            user_content_parts.append("字幕文件名:")
            for sub_file in subtitle_filenames:
                user_content_parts.append(f"- {sub_file}")
        else:
            user_content_parts.append("字幕文件: 无")
        user_content_parts.append("")
        user_content_parts.append(provider_context)
        user_content = '\n'.join(user_content_parts)

        system_prompt = self._build_system_prompt_with_provider_context(
            exclude_dims=exclude_dims,
            provider_name=provider_name,
        )

        result = self._retry_with_fallback(system_prompt, user_content, use_fast=True)

        if provider_dimensions:
            ai_dims = result.get('dimensions', {})
            for dim_name, dim_info in provider_dimensions.items():
                ai_dims[dim_name] = dim_info
            result['dimensions'] = ai_dims

        return result

    def _build_system_prompt_with_provider_context(self, exclude_dims=None, provider_name=None):
        """根据 provider_name 选择提示词模板"""
        SEP = "【维度判断】\n当前需要判断的维度："

        # 优先使用用户自定义提示词
        provider_type = None
        if provider_name:
            # 从注册表查找 provider_type
            for pt, cls in _PROVIDER_REGISTRY.items():
                if cls.display_name == provider_name or cls.provider_type == provider_name:
                    provider_type = pt
                    break

        custom_prompt = ''
        if provider_type and provider_type in self._provider_prompts:
            custom_prompt = self._provider_prompts[provider_type]

        if custom_prompt:
            base = custom_prompt
        elif provider_type:
            # 使用 Provider 的默认模板
            cls = get_provider_class(provider_type)
            if cls:
                base = cls.get_context_template(cls)  # 类方法
            else:
                base = MetadataProvider.get_context_template(None)
        else:
            base = MetadataProvider.get_context_template(None)

        if base.endswith(SEP):
            base = base[:-len(SEP)]

        prompt_parts = [base, "", SEP, ""]

        dims = [d for d in self.dimensions if d.get('name') not in (exclude_dims or set())]
        for i, dim in enumerate(dims, 1):
            name = dim.get('name', '')
            label = dim.get('label', name)
            values = dim.get('values', [])
            values_str = ', '.join(str(v) for v in values) if values else ''
            ai_hint = dim.get('ai_prompt', '')
            if ai_hint:
                prompt_parts.append(f"{i}. {label}（{name}）: [{values_str}] — {ai_hint}")
            else:
                prompt_parts.append(f"{i}. {label}（{name}）: [{values_str}]")

        prompt_parts.append("")
        prompt_parts.append("请严格按以下JSON格式返回，不要添加任何解释文字：")
        json_schema = self._build_json_schema(exclude_dims)
        prompt_parts.append(json.dumps(json_schema, ensure_ascii=False, indent=2))
        return '\n'.join(prompt_parts)
```

#### 6.2 提示词文件管理（解决 P1-9）

- 保留现有 `config/tmdb_prompts.md`（重命名提示词内容中的 "TMDB" 为 "TMDb"，与 Provider display_name 一致）
- 未来新增 IMDB Provider 时，创建 `config/imdb_prompts.md`
- `prompt_handlers.py` 中的 `_load_tmdb_prompts_for_ui` / `_config_save_tmdb_prompts` / `_config_reset_tmdb_prompts` 泛化为按 provider_type 操作

#### 6.3 AI 提示词中 TMDB 专属引用的泛化（解决 P1-8）

当前 `TMDB_CONTEXT_PROMPT` 中的硬编码：
```
- 是否纪录片：TMDB genres 包含 Documentary (id=99) 则为 true
- 是否动漫：TMDB genres 包含 Animation (id=16) 则为 true
- 限制级分类：优先使用 TMDB release_dates 中的官方分级
```

改造后，这些规则不再出现在提示词中。Provider 的 `map_dimensions()` 已经自动提取了这些维度的值（documentary=true/false 等），这些值通过 `provider_dimensions` 传给 AI，AI 只需对 `exclude_dims` 以外的维度做判断。

提示词模板改为通用表述：
```
以下维度的映射数据已自动提取为参考（如为 null 表示未提供），请对每个维度给出判断
```

---

### 第七层：配置结构改造

**当前**：
```yaml
metadata:
  tmdb:
    enabled: true
    api_key: xxx
    language: zh-CN
```

**改造后**：
```yaml
metadata:
  providers:
    - type: tmdb
      enabled: true
      api_key: xxx
      language: zh-CN
      fallback_language: en-US
      request_timeout: 10
      max_retries: 3
```

**迁移**（`config_loader.py`）：

```python
# 兼容旧配置 metadata.tmdb → metadata.providers
if "tmdb" in config.get("metadata", {}) and "providers" not in config.get("metadata", {}):
    old_tmdb = config["metadata"].pop("tmdb")
    config["metadata"]["providers"] = [{"type": "tmdb", **old_tmdb}]
    print("已自动迁移配置: metadata.tmdb → metadata.providers")

if "metadata" not in config:
    config["metadata"] = {}
if "providers" not in config["metadata"]:
    config["metadata"]["providers"] = [{"type": "tmdb", "enabled": True, "language": "zh-CN", "fallback_language": "en-US"}]
```

**`mask_sensitive` 更新**：

```python
# 原: masked.get("metadata", {}).get("tmdb", {}).get("api_key")
# 改: 遍历 metadata.providers 列表，对每个 provider 的 api_key 脱敏
for provider in masked.get("metadata", {}).get("providers", []):
    if provider.get("api_key"):
        provider["api_key"] = "***"
```

---

### 第八层：API 路由泛化

**当前 10 个 TMDB 专属路由** → 改为通用 Provider 路由：

```
GET  /api/providers                           # 列出所有已注册 Provider 及其状态/配置Schema
GET  /api/providers/{type}                    # 单个 Provider 配置
POST /api/providers/{type}/test               # 测试连接
POST /api/providers/{type}/search             # 搜索
POST /api/providers/{type}/details            # 详情
GET  /api/providers/{type}/genres             # 类型列表
POST /api/providers/{type}/preview            # 预览
GET  /api/providers/{type}/prompts            # 获取提示词
POST /api/providers/{type}/prompts            # 保存提示词
POST /api/providers/{type}/prompts/reset      # 重置提示词
```

**兼容别名**（保留一个版本周期）：

```
POST /api/config/test-tmdb          → 301 → POST /api/providers/tmdb/test
POST /api/tmdb/preview              → 301 → POST /api/providers/tmdb/preview
POST /api/tmdb/search               → 301 → POST /api/providers/tmdb/search
POST /api/tmdb/details              → 301 → POST /api/providers/tmdb/details
GET  /api/tmdb/genres               → 301 → GET  /api/providers/tmdb/genres
GET  /api/config/prompts/tmdb       → 301 → GET  /api/providers/tmdb/prompts
POST /api/config/prompts/tmdb       → 301 → POST /api/providers/tmdb/prompts
POST /api/config/prompts/tmdb/reset → 301 → POST /api/providers/tmdb/prompts/reset
```

**`_scrape_preview` 改造**（解决 P2-11）：

```python
def _scrape_preview(self, body):
    filename = (body or {}).get("filename", "").strip()
    if not filename:
        json_response(self, 400, message="请输入视频文件名")
        return

    providers = create_providers(globals._config)
    # ... 并行运行纯 AI 和 Provider+AI ...
    # 返回格式改为：
    json_response(self, 200, data={
        "filename": filename,
        "clean_result": {...},
        "ai_only": ai_result,
        "ai_only_elapsed": ai_elapsed,
        "providers": [
            {"type": p.provider_type, "result": provider_result, "elapsed": provider_elapsed}
            for p, provider_result, provider_elapsed in provider_results
        ],
    })
```

---

### 第九层：前端 UI 改造

#### 9.1 元数据源配置面板动态化

当前硬编码 TMDB 配置表单 → 改为从 `/api/providers` 获取 Schema 后动态渲染：

```javascript
async function loadProviderConfigs() {
    var result = await apiRequest('GET', '/providers');
    var providers = result.data.providers || [];
    var container = document.getElementById('provider-configs-container');
    container.innerHTML = '';

    for (var p of providers) {
        var card = renderProviderCard(p);
        container.appendChild(card);
    }
}

function renderProviderCard(provider) {
    var card = document.createElement('div');
    card.className = 'provider-card';
    card.innerHTML = `
        <div class="provider-card-header">
            <span class="provider-name">${provider.display_name}</span>
            <label class="toggle-switch">
                <input type="checkbox" ${provider.enabled ? 'checked' : ''} onchange="toggleProvider('${provider.type}', this.checked)">
                <span class="toggle-slider"></span>
            </label>
        </div>
        <div class="provider-card-body">
            ${provider.config_schema.fields.map(f => renderConfigField(provider.type, f)).join('')}
            <div class="provider-actions">
                <button onclick="testProvider('${provider.type}')">测试连接</button>
                <button onclick="previewProvider('${provider.type}')">刮削预览</button>
            </div>
        </div>
    `;
    return card;
}

function renderConfigField(providerType, field) {
    switch (field.type) {
        case 'password':
            return `<div class="form-group">
                <label>${field.label}</label>
                <input type="password" id="cfg-provider-${providerType}-${field.key}" placeholder="${field.label}">
            </div>`;
        case 'select':
            return `<div class="form-group">
                <label>${field.label}</label>
                <select id="cfg-provider-${providerType}-${field.key}">
                    ${field.options.map(o => `<option value="${o.value}">${o.label}</option>`).join('')}
                </select>
            </div>`;
        case 'number':
            return `<div class="form-group">
                <label>${field.label}</label>
                <input type="number" id="cfg-provider-${providerType}-${field.key}" value="${field.default || ''}">
            </div>`;
        default:
            return `<div class="form-group">
                <label>${field.label}</label>
                <input type="text" id="cfg-provider-${providerType}-${field.key}">
            </div>`;
    }
}
```

#### 9.2 维度来源信任卡片动态化

```javascript
async function renderDimensionSourceTrustCards() {
    var providersResult = await apiRequest('GET', '/providers');
    var enabledProviders = (providersResult.data.providers || []).filter(p => p.enabled);
    var allSources = [
        ...enabledProviders.map(p => ({key: p.type, label: p.display_name, icon: '🌐'})),
        {key: 'ai', label: 'AI 刮削', icon: '🤖'},
        {key: 'file', label: '文件信息', icon: '📁'},
    ];
    // ... 后续渲染逻辑与现有相同，只是 allSources 从 API 动态获取
}
```

#### 9.3 提示词编辑器动态化

当前硬编码两个 Tab（LLM / LLM+TMDB）→ 改为动态 Tab：

```javascript
async function loadPromptTabs() {
    var providersResult = await apiRequest('GET', '/providers');
    var enabledProviders = (providersResult.data.providers || []).filter(p => p.enabled);

    var tabs = [{id: 'llm', label: 'LLM 纯 AI'}];
    for (var p of enabledProviders) {
        tabs.push({id: p.type, label: `LLM + ${p.display_name}`});
    }
    // 渲染 Tab 栏
    renderPromptTabs(tabs);
}
```

#### 9.4 tmdb-dict.js 处理（解决 P2-14）

**策略**：暂不改动。当前只有 TMDB 一个 Provider，`tmdb-dict.js` 保持原样。未来新增第二个 Provider 时，再为它新建对应的 dict 文件（如 `imdb-dict.js`），并在详情预览弹窗中按 provider_type 选择对应的字典。

#### 9.5 tasks.js trace 渲染（解决 P2-10）

```javascript
function renderScrapeTrace(trace) {
    // 兼容旧数据
    var searchInfo = trace.provider_search || trace.tmdb_search;
    var mode = trace.mode || 'unknown';
    var providerLabel = trace.provider_type
        ? getProviderDisplayName(trace.provider_type)
        : 'TMDb';  // 旧数据默认 TMDb
    // ... 后续渲染
}
```

---

## 改造策略：分阶段执行

### 阶段 1：后端核心抽象（不改 UI，不改 API 路由）

**目标**：Provider 接口 + 注册表 + TMDbProvider 实现 + MetadataScraper/DimensionManager/ConfidenceEngine/LLMScraper 内部解耦

**步骤**：

| # | 任务 | 涉及文件 | 验收标准 |
|---|------|---------|---------|
| 1.1 | 创建 `scraper/providers/` 子包 | 新增 `base.py`, `models.py`, `tmdb_provider.py`, `__init__.py` | `from .providers import create_providers` 可正常导入；`@register_provider` 装饰器工作正常 |
| 1.2 | 重构 `dimension_manager.py` | `dimension_manager.py` | `get_dimensions_for_provider(conn, "tmdb")` 返回与旧 `get_dimensions_for_tmdb(conn)` 相同结果；`map_provider_to_dimension()` 通过 `provider_mappings` 正确映射所有 7 个维度 |
| 1.3 | 重构 `confidence_engine.py` | `confidence_engine.py` | `TitleMatcher.match_standard()` 接收 `SearchItem` 返回与 `match()` 相同结果；`ScrapeTraceBuilder` 输出 `provider_search` 键；`tmdb_match_threshold` 兼容 `provider_match_threshold` |
| 1.4 | 重构 `llm_scraper.py` | `llm_scraper.py` | `scrape_with_context()` 接收 `provider_context`/`provider_dimensions`/`exclude_dims`/`provider_name`；`_build_system_prompt_with_provider_context()` 根据 provider_name 选择模板；`tmdb_prompts.md` 正常加载 |
| 1.5 | 重构 `metadata_scraper.py` | `metadata_scraper.py` | `MetadataScraper` 从 `create_providers(config)` 初始化；`scrape()` 遍历 providers；`_search_with_match()` 替代 `_search_tmdb_with_match()`；`_extract_context()` 替代 `_extract_tmdb_context()` |
| 1.6 | 配置迁移 | `config_loader.py` | `metadata.tmdb` 自动转为 `metadata.providers`；`tmdb_match_threshold` 自动转为 `provider_match_threshold`；`mask_sensitive` 正确脱敏 providers 列表 |
| 1.7 | 数据库迁移 | `dimension_repo.py`, `constants.py` | `dimensions` 表新增 `provider_mappings` 列；现有 `tmdb_field` + `value_list` 自动迁移为 `provider_mappings` JSON；`source_type "ai+tmdb"` 迁移为 `"ai+provider"` |
| 1.8 | 回归测试 | 所有测试文件 | 现有测试全部通过；新增 Provider 抽象层单元测试 |

**预计改动文件**：
- 新增：`scraper/providers/base.py`, `scraper/providers/models.py`, `scraper/providers/tmdb_provider.py`, `scraper/providers/__init__.py`（4个）
- 重构：`scraper/metadata_scraper.py`, `scraper/dimension_manager.py`, `scraper/confidence_engine.py`, `scraper/llm_scraper.py`（4个）
- 小改：`core/config_loader.py`, `core/db/constants.py`, `core/db/dimension_repo.py`（3个）
- 不变：pipeline 层、storage 层、notify 层、monitor 层

**关键约束**：
- 阶段 1 完成后，**外部行为不变**：API 路由不变、前端不变、配置文件格式自动兼容
- `tmdb_client.py` 保留不动，TMDbProvider 是包装层
- 旧的 `_search_tmdb_with_match`、`_extract_tmdb_context`、`_map_tmdb_dimensions` 方法标记为 deprecated 但保留一个版本周期

### 阶段 2：API 层泛化

| # | 任务 | 涉及文件 | 验收标准 |
|---|------|---------|---------|
| 2.1 | 新增 `/api/providers` 通用路由 | `api/handler.py`, `api/provider_handlers.py`(新增) | `GET /api/providers` 返回所有已注册 Provider 及其 Schema |
| 2.2 | 实现 Provider 通用 CRUD | `api/provider_handlers.py` | `GET/POST /api/providers/{type}/*` 全部工作 |
| 2.3 | 旧路由兼容别名 | `api/handler.py` | 旧 `/api/tmdb/*` 路由重定向到 `/api/providers/tmdb/*` |
| 2.4 | 重构 `config_handlers.py` | `api/config_handlers.py` | `_config_test_tmdb` → `_provider_test`；`_tmdb_preview` → `_provider_preview`；`_scrape_preview` 返回新格式 |
| 2.5 | 重构 `prompt_handlers.py` | `api/prompt_handlers.py` | `_load_tmdb_prompts_for_ui` → `_load_provider_prompts_for_ui(type)`；`_config_save_tmdb_prompts` → `_config_save_provider_prompts(type)` |

### 阶段 3：前端 UI 泛化

| # | 任务 | 涉及文件 | 验收标准 |
|---|------|---------|---------|
| 3.1 | 元数据源配置面板动态化 | `config.js`, `index.html` | 从 `/api/providers` 获取 Schema 动态渲染配置表单 |
| 3.2 | 维度来源信任卡片动态化 | `config.js` | `allSources` 从 API 动态获取，支持 N 行 |
| 3.3 | 提示词编辑器动态化 | `config.js`, `index.html` | Tab 从 API 动态生成 |
| 3.4 | tasks.js trace 兼容 | `tasks.js` | 同时支持 `tmdb_search` 和 `provider_search` |
| 3.5 | API 调用路径更新 | `config.js`, `dimensions.js`, `tasks.js` | 前端调用 `/api/providers/tmdb/*` 替代 `/api/tmdb/*` |

---

## 评审问题解决对照表

| # | 问题 | 等级 | 解决方案 | 所在层 |
|---|------|------|---------|--------|
| 1 | Provider 注册机制缺失 | P0 | `@register_provider` 装饰器 + `_PROVIDER_REGISTRY` 字典 | 第一层 |
| 2 | 多 Provider 维度冲突 | P0 | 按优先级顺序搜索，第一个命中即停，不存在同时多 Provider 映射 | 第四层 |
| 3 | exclude_dims 重设计 | P0 | `scrape_with_context()` 接收 `exclude_dims` 参数，由 MetadataScraper 计算所有 Provider 已覆盖维度的并集 | 第六层 |
| 4 | get_dimensions_for_tmdb 改造 | P0 | `get_dimensions_for_provider(conn, provider_type)` 按 `provider_mappings` 中是否有该 provider 的条目筛选 | 第三层 |
| 5 | TitleMatcher 解耦 | P1 | 新增 `match_standard()` 方法接收 `SearchItem`，保留原 `match()` 向后兼容 | 第五层 |
| 6 | Genre.id 类型 | P1 | `Genre.id: str`，TMDB 的整数 ID 转为字符串 | 第一层 |
| 7 | Provider 配置 Schema | P1 | `get_config_schema()` 类方法 + `/api/providers` API 暴露 | 第一层 + 第八层 |
| 8 | 提示词 TMDB 硬编码 | P1 | Provider 提供 `get_context_template()` 方法，LLMScraper 根据 provider_name 选择模板 | 第六层 |
| 9 | 提示词文件管理 | P1 | 每个 Provider 一个 `{type}_prompts.md` 文件，`_load_provider_prompts_from_files()` 统一加载 | 第六层 |
| 10 | Trace 向后兼容 | P2 | 前端同时检查 `tmdb_search` 和 `provider_search` | 第五层 + 第九层 |
| 11 | scrape_preview 硬编码 | P2 | `_scrape_preview` 改为遍历 `create_providers()`，返回 `providers` 数组 | 第八层 |
| 12 | 配置键重命名迁移 | P2 | `config_loader.py` 自动将 `tmdb_match_threshold` 转为 `provider_match_threshold` | 第七层 |
| 13 | DB 迁移复杂度 | P2 | `_migrate_to_provider_mappings()` 从 `tmdb_field` + `value_list` 自动构建 JSON | 第三层 |
| 14 | tmdb-dict.js 改造范围 | P2 | 暂不改动，未来按需新增 | 不变 |
| 15 | 多 Provider 搜索性能 | P2 | 默认顺序搜索（第一个命中即停），可配置 `search_strategy: "parallel"` | 第四层 |
| 16 | _extract_tmdb_context 格式化 | P2 | `_extract_context(details)` 接收标准 `MediaDetails`，格式化逻辑在 MetadataScraper 中 | 第四层 |

---

## 配置示例（改造后完整配置）

```yaml
metadata:
  providers:
    - type: tmdb
      enabled: true
      api_key: "xxx"
      language: "zh-CN"
      fallback_language: "en-US"
      request_timeout: 10
      max_retries: 3
    # 未来:
    # - type: imdb
    #   enabled: false
    #   api_key: "xxx"

confidence:
  provider_match_threshold: 0.85    # 原 tmdb_match_threshold（自动兼容）
  source_priority: ["tmdb", "ai", "file"]   # 动态包含所有 provider type
  # ... 其他参数不变

dimensions:
  # 维度配置中的 provider_mappings 替代 tmdb_field
  documentary:
    provider_mappings:
      tmdb:
        field: genres
        match_type: genre_ids
        match_rules:
          true:
            ids: [99]
```

---

## 开放问题

1. **`provider_mappings` 存储格式**：是用 JSON 存在数据库 TEXT 列中，还是新建关联表？
   - **决定**：TEXT 列存 JSON，与现有 `value_list` 模式一致，简单够用

2. **多 Provider 并行搜索 vs 顺序搜索**：
   - **决定**：默认按优先级顺序搜索，第一个达到阈值就停。未来可配置 `search_strategy: "parallel"` 并行搜索取最优

3. **旧配置兼容期**：保留多久旧路由和旧配置键？
   - **决定**：至少保留一个版本周期，在日志中打印 deprecation 警告

4. **是否现在就支持配置多个 Provider**：
   - **决定**：后端和配置完全支持多 Provider，UI 暂时只渲染 TMDB 配置，但维度来源信任卡片动态化

5. **`_extract_context` 中 TV 特有字段（number_of_seasons 等）如何泛化**：
   - **决定**：`MediaDetails` 不包含 TV 特有字段，`_extract_context` 从 `raw_data` 中按需提取。格式化逻辑留在 MetadataScraper 中（解决 P2-16）

---

## 新增 Provider 清单（未来参考）

添加一个新的刮削源（如 IMDB）只需：

1. **创建 `scraper/providers/imdb_provider.py`**：
   - 继承 `MetadataProvider`
   - 用 `@register_provider` 装饰
   - 实现所有抽象方法
   - 实现 `get_config_schema()` 返回配置字段定义
   - 实现 `map_dimensions()` 处理 IMDB 特有的维度映射
   - 可选覆盖 `get_context_template()` 提供 IMDB 专属提示词

2. **在 `scraper/providers/__init__.py` 中 import**：
   ```python
   from .imdb_provider import IMDBProvider  # noqa: F401
   ```

3. **在配置中启用**：
   ```yaml
   metadata:
     providers:
       - type: imdb
         enabled: true
         api_key: "xxx"
   ```

4. **（可选）创建 `config/imdb_prompts.md`**：IMDB 专属提示词

5. **（可选）在维度配置中添加 IMDB 映射**：
   ```json
   {
     "tmdb": {"field": "genres", "match_type": "genre_ids", "match_rules": {"true": {"ids": [99]}}},
     "imdb": {"field": "genres", "match_type": "genre_names", "match_rules": {"true": {"names": ["Documentary"]}}}
   }
   ```

**不需要修改的文件**：`metadata_scraper.py`、`confidence_engine.py`、`llm_scraper.py`、`dimension_manager.py`、`config_loader.py`、任何前端文件
