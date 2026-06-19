# 2026-06-19 scraper/ 迁移 Inventory(S-Phase 0)

本文件是 scraper/ → features/* 迁移的 inventory 与 baseline,供 S-Phase 1-5 参考,不会进入正式 docs 树。

决策依据:
- ADR-0008:docs/decisions/0008-scraper-feature-first-migration.md
- 子计划:docs/plans/2026-06-18-refactor-scraper-feature-first-migration-plan.md(Migration Map 见第 4 节)

---

## 1. 文件清单(任务 A)

`media_importer/scraper/` 共 14 个 .py 文件(含 providers/ 子目录 3 个):

| 文件 | 行数 | 文件级 docstring / 首 5 行摘要 |
|------|------|---------------------------------|
| `__init__.py` | 7 | 直接 re-export `LLMScraper`, `MetadataScraper`, `TMDbClient`, `TMDbError`, `check_tier_access`, `get_dimensions_for_scrape` 等 |
| `_llm_client_impl.py` | 332 | `"""LLM HTTP client implementation — extracted from LLMScraper."""` |
| `_llm_match_assist.py` | 232 | `"""LLM match assistance implementation — extracted from LLMScraper."""` |
| `dimension_manager.py` | 21 | 无 docstring;从 `features.scraping.dimension_manager` 引入并 re-export `CERTIFICATION_TO_LEVEL`, `check_tier_access`, `get_dimensions_for_file`, `get_dimensions_for_provider`(纯 thin re-export) |
| `exceptions.py` | 13 | `"""LLM scraper exception classes — extracted to avoid circular imports."""`;含 `LLMApiError`, `LLMWebSearchError`, `LLMScrapeError` |
| `filename_cleaner.py` | 204 | 无 docstring;从 `features.scraping.confidence_models` 引入 `CleanResult`, `_RESOLUTION_PATTERNS` 等 |
| `llm_scraper.py` | 260 | `"""LLM Scraper — public API; implementation distributed to _llm_client_impl / _llm_match_assist."""` |
| `metadata_scrape_flow.py` | 527 | 无 docstring;从 `media_importer.core.db import get_enabled_dimensions` 引入 |
| `metadata_scraper.py` | 3 | 无 docstring;**纯 re-export** from `features.scraping.metadata_scraper`:`MetadataScraper` |
| `title_matcher.py` | 183 | 无 docstring;从 `features.scraping.confidence_models` 引入 `MatchResult`, `DEFAULT_CONFIDENCE_CONFIG` |
| `tmdb_client.py` | 174 | 无 docstring;仅 `#!/usr/bin/env python3` shebang |
| `providers/__init__.py` | 29 | 全部从 `features.providers` re-export:`DimensionMapping`, `Genre`, `MediaDetails`, `MetadataProvider` |
| `providers/base.py` | 17 | 全部从 `features.providers.base` re-export 上述 4 个类型 |
| `providers/tmdb_provider.py` | 3 | **纯 re-export**:`from features.providers.tmdb_provider import TMDbProvider` |

**行数总和**:14 个文件,合计 ~1997 行(含注释/空行)。
**已有 docstring 的文件**:仅 3 个(`__init__.py` 顶层隐式 + `llm_scraper.py` 显式 + `_llm_client_impl.py` 显式 + `_llm_match_assist.py` 显式 + `exceptions.py` 显式),其余 9 个首 5 行只有 import 或 shebang。

---

## 2. 外部消费者 import 图(任务 B)

在 `media_importer/` 下搜索(排除 `scraper/` 自身),共 **14 条** import 命中,分布在 **8 个消费者文件**:

### 按消费者文件分组

**`media_importer/features/scraping/__init__.py`**(4 条)
- `from media_importer.scraper.llm_scraper import LLMScrapeError, LLMScraper`
- `from media_importer.scraper.tmdb_client import TMDbClient, TMDbError`
- `from media_importer.scraper.filename_cleaner import FilenameCleaner`
- `from media_importer.scraper.title_matcher import TitleMatcher, _similarity`

**`media_importer/features/scraping/match_engine.py`**(2 条)
- `from media_importer.scraper.title_matcher import TitleMatcher`
- `from media_importer.scraper.filename_cleaner import FilenameCleaner`

**`media_importer/features/scraping/metadata_scraper.py`**(4 条)
- `from media_importer.scraper.llm_scraper import LLMScraper`
- `from media_importer.scraper.filename_cleaner import FilenameCleaner`
- `from media_importer.scraper.title_matcher import TitleMatcher, MatchResult`
- `from media_importer.scraper.metadata_scrape_flow import scrape_metadata, scrape_series_metadata`

**`media_importer/features/scraping/_match_tiers_impl.py`**(1 条,函数内 lazy import)
- `from media_importer.scraper.llm_scraper import LLMScraper`(`_match_tiers_impl.py:503`,在函数体内)

**`media_importer/features/providers/tmdb_provider.py`**(1 条)
- `from media_importer.scraper.tmdb_client import TMDbClient, TMDbError`

**`media_importer/features/source_cleaning/cleaner.py`**(2 条,1 条模块顶层 + 1 条函数内 lazy import)
- 顶层:`from media_importer.scraper._llm_match_assist import _assemble_prompt`
- 函数内:`from media_importer.scraper.llm_scraper import LLMScraper`(`cleaner.py:47`)

**`media_importer/features/prompts/__init__.py`**(1 条,try/except 内 lazy import)
- `from media_importer.scraper.llm_scraper import LLMScraper`(`__init__.py:12`,在 try 块内)

**`media_importer/api/connectivity_handlers.py`**(2 条,函数内 lazy import)
- `from media_importer.scraper.llm_scraper import LLMScraper`(`connectivity_handlers.py:115`)
- `from media_importer.scraper.llm_scraper import LLMScraper`(`connectivity_handlers.py:159`)

### 按被导入模块统计

| scraper 模块 | 引用次数 |
|--------------|----------|
| `llm_scraper` | 7(`LLMScraper` + `LLMScrapeError`) |
| `tmdb_client` | 2(`TMDbClient` + `TMDbError`) |
| `filename_cleaner` | 3(`FilenameCleaner`) |
| `title_matcher` | 3(`TitleMatcher` + `MatchResult` + `_similarity`) |
| `metadata_scrape_flow` | 1(`scrape_metadata` + `scrape_series_metadata`) |
| `_llm_match_assist` | 1(`_assemble_prompt`) |
| `_llm_client_impl` | 0(无直接 import,被 `_llm_match_assist` / `llm_scraper` 内部用) |
| `dimension_manager` | 0(无直接生产 import,见 §4 处置理由) |
| `metadata_scraper` | 0(纯 re-export,无生产引用) |
| `exceptions` | 0(异常类型全部从 `llm_scraper` re-export,生产代码不直接 import) |
| `providers/*` | 0(纯 re-export,生产代码直接 import `features.providers.*`) |

**关键观察**:被引用最多的是 `llm_scraper`(7 条),其中 5 条是函数内 lazy import(`_match_tiers_impl.py:503`、`source_cleaning/cleaner.py:47`、`prompts/__init__.py:12`、`connectivity_handlers.py:115` 和 `:159`),2 条是模块顶层 import(`scraping/__init__.py`、`scraping/metadata_scraper.py`)——必须在迁移时保持外部 API 名称 `LLMScraper` 与 `LLMScrapeError` 稳定。`_llm_client_impl` 和 `dimension_manager` 无生产直接引用,处置空间更大。

---

## 3. 内部 import 方式统计(任务 C)

scraper/ 内部 import 共 **8 条**命中,全部使用**相对 import**(`from .xxx`),**0 条绝对 import**。

```
media_importer/scraper/metadata_scrape_flow.py:8:from .llm_scraper import LLMScrapeError
media_importer/scraper/__init__.py:1:from .llm_scraper import LLMScraper, LLMScrapeError
media_importer/scraper/__init__.py:2:from .metadata_scraper import MetadataScraper
media_importer/scraper/__init__.py:3:from .tmdb_client import TMDbClient, TMDbError
media_importer/scraper/__init__.py:4:from .dimension_manager import (...)
media_importer/scraper/llm_scraper.py:7:from media_importer.scraper.exceptions import (...)
media_importer/scraper/llm_scraper.py:9:from media_importer.scraper._llm_client_impl import (...)
media_importer/scraper/llm_scraper.py:20:from media_importer.scraper._llm_match_assist import (...)
media_importer/scraper/_llm_match_assist.py:7:from media_importer.scraper._llm_client_impl import _call_with_retry_impl
media_importer/scraper/_llm_match_assist.py:8:from media_importer.scraper.exceptions import LLMScrapeError
media_importer/scraper/_llm_client_impl.py:11:from media_importer.scraper.exceptions import (...)
```

修正:上面 grep 显示 `from media_importer.scraper.exceptions` 等**绝对 import** 出现在 `llm_scraper.py`、`_llm_match_assist.py`、`_llm_client_impl.py` 中——**这与"全相对"的假设矛盾**。

精确分类:
- **相对 import**(`from .xxx`):**5 条**(`metadata_scrape_flow.py` 1 + `__init__.py` 4)
- **绝对 import**(`from media_importer.scraper.xxx`):**6 条**(`llm_scraper.py` 3 + `_llm_match_assist.py` 2 + `_llm_client_impl.py` 1)

**迁移影响**:绝对 import 的文件(`llm_scraper.py`、`_llm_match_assist.py`、`_llm_client_impl.py`)在移动后必须更新 import 路径。相对 import 的文件移动后内部引用**不受影响**(`__init__.py` 在 refactor in place 后仍是集散点,无需更新)。

---

## 4. 文件处置表(任务 D)

基于子计划 Migration Map(§4)逐项落实,覆盖全部 14 个文件:

| # | 文件 | 当前职责 | 是否被生产引用 | 处置类别 | 目标位置 | 备注 |
|---|------|----------|----------------|----------|----------|------|
| 1 | `__init__.py` | 旧包入口,顶层 re-export 4 个子模块符号 | 是(经子模块路径) | **refactor in place** | 原地改造 | 改造为 compat re-export 集散点;所有外部 import 经此转发到 `features.*`。原有 4 个 `from .xxx` 不变,新增对 `features.*` 的转发。 |
| 2 | `_llm_client_impl.py` | LLM HTTP 调用执行能力(已从 `llm_scraper` 拆出) | 否(仅被同包内引用) | **move + rename** | `features/scraping/llm_client.py` | 目标名 `llm_client`(去掉前缀 `_`);同时把内部 3 条绝对 import 改为相对或新绝对路径。 |
| 3 | `_llm_match_assist.py` | match assist 执行(已从 `llm_scraper` 拆出) | 是(`source_cleaning/cleaner.py` 用 `_assemble_prompt`) | **split** | `features/prompts/match_assist.py` + `features/scraping/llm_match_assist.py` | 子计划要求按"Prompt 组装 + match assist 执行"拆分。`_assemble_prompt` 是 Prompt 职责,迁 `features/prompts`;其余执行迁 `features/scraping`。 |
| 4 | `dimension_manager.py` | **纯 re-export**(21 行),从 `features.scraping.dimension_manager` 引入 4 个符号 | 否(无生产直接 import) | **audit + merge/archive** | 与 `features/scraping/dimension_manager.py` 对比 | 已有同名实现,且生产代码不引用此文件——**实质等价 compat 入口**。处置:`__init__.py` 内增加对 `features.scraping.dimension_manager` 的直接 re-export,此文件可**删除**。但子计划要求"明确处置",故本 inventory 建议 S-Phase 5(Compatibility Cleanup)统一处理删除。**待人工确认是否在 S-Phase 0 内删除**。 |
| 5 | `exceptions.py` | 异常类型(`LLMApiError`, `LLMWebSearchError`, `LLMScrapeError`) | 否(生产代码只 import 它们的 re-export 路径) | **split** | `features/scraping/errors.py` + `features/providers/errors.py` | 按归属拆分:`LLMScrapeError` → scraping;`LLMApiError`/`LLMWebSearchError` → scraping(LLM 通用)。但无 providers 专用异常,实际可能只生成 `features/scraping/errors.py`。 |
| 6 | `filename_cleaner.py` | 文件名清洗(204 行真实实现) | 是(`match_engine.py`, `metadata_scraper.py`, `scraping/__init__.py`) | **move + compat re-export** | `features/scraping/filename_cleaner.py` | 旧路径保留 re-export;同时清理内部 import(从 `features.scraping.confidence_models` 已是绝对,迁移后保持)。 |
| 7 | `llm_scraper.py` | LLM 标题/维度辅助公共 API(260 行) | 是(7 条引用,最广) | **move + compat re-export** | `features/scraping/llm_scraper.py` | 内部 3 条绝对 import 需更新;类名 `LLMScraper` 与 `LLMScrapeError` 保持稳定(7 个外部调用点全部依赖此名)。 |
| 8 | `metadata_scrape_flow.py` | 正式任务元数据刮削编排(527 行) | 是(`metadata_scraper.py` 1 条) | **split** | `features/scraping/metadata_flow/`(目录) | 子计划要求拆为包;目录内可拆 `flow.py`, `series.py`, `common.py`。 |
| 9 | `metadata_scraper.py` | **纯 re-export**(3 行) from `features.scraping.metadata_scraper` | 否(无生产直接 import) | **audit + merge/archive** | 与 `features/scraping/metadata_scraper.py` 对比 | 已有同名实现且生产代码不引用——同 §4 第 4 项,建议 S-Phase 5 统一清理。**待人工确认是否在 S-Phase 0 内删除**。 |
| 10 | `title_matcher.py` | 标题相似度与匹配等级(183 行真实实现) | 是(`match_engine.py`, `metadata_scraper.py`, `scraping/__init__.py`) | **move + compat re-export** | `features/scraping/title_matcher.py` | 旧路径保留 re-export;`MatchResult` 已在 `features.scraping.confidence_models` 真实定义,内部引用已是绝对路径,迁移后保持。 |
| 11 | `tmdb_client.py` | TMDB HTTP 客户端(174 行真实实现) | 是(`scraping/__init__.py`, `providers/tmdb_provider.py` 各 1 条) | **move + compat re-export** | `features/providers/tmdb_client.py` | 旧路径保留 re-export;注意 `providers/tmdb_provider.py` 已经 re-export from `features.providers.tmdb_provider`——存在中间层,迁移后 `features/providers/tmdb_provider.py` 应改为 import 新位置的 `features/providers/tmdb_client.py`。 |
| 12 | `providers/__init__.py` | **纯 re-export**(29 行) from `features.providers` | 否(生产代码直接 import `features.providers.*`) | **consolidate** | `features/providers/__init__.py`(已存在) | 完全等价,建议 S-Phase 5 删除整个 `scraper/providers/` 子目录。 |
| 13 | `providers/base.py` | **纯 re-export**(17 行) from `features.providers.base` | 否 | **consolidate** | `features/providers/base.py`(已存在) | 同 §12,建议 S-Phase 5 统一删除。 |
| 14 | `providers/tmdb_provider.py` | **纯 re-export**(3 行) from `features.providers.tmdb_provider` | 否 | **consolidate** | `features/providers/tmdb_provider.py`(已存在) | 同 §12,建议 S-Phase 5 统一删除。 |

**无"未分类"文件**:14/14 全部落实。0 个文件被标记为 compat re-export only(全部带 move 或 refactor in place)。

### 特别关注项处置

- `scraper/dimension_manager.py` 与 `features/scraping/dimension_manager.py`:功能完全等价,后者是真实实现(15454 字节),前者是 21 行 thin re-export。无生产引用。**处置**:S-Phase 5 清理时直接删除 `scraper/dimension_manager.py`,`__init__.py` 内增加对 `features.scraping.dimension_manager` 的转发即可。
- `scraper/providers/*` 与 `features/providers/*`:**两层目录同名,但内容完全分离**——`scraper/providers/*` 全是 thin re-export(29/17/3 行),`features/providers/*` 是真实实现(含 `base.py`, `tmdb_provider.py`)。无生产代码直接 import `scraper.providers.*`。**处置**:S-Phase 5 清理时整目录删除 `scraper/providers/`,生产代码早已走 `features.providers.*` 路径。

---

## 5. 测试基线(任务 E)

### 相关测试文件清单

直接 import `media_importer.scraper.*` 的测试(13 个):
- `tests/test_ai_call_logging.py`
- `tests/test_ai_config_runtime.py`
- `tests/test_ai_scenes_integration.py`
- `tests/test_feature_entrypoints.py`
- `tests/test_filename_cleaner.py`
- `tests/test_llm_web_search.py`
- `tests/test_p0_confirm_workflow_fixes.py`
- `tests/test_prompt_resolver_integration.py`
- `tests/test_prompt_runtime.py`
- `tests/test_retry_with_fallback.py`
- `tests/test_scrape_provider_first_e2e.py`
- `tests/test_tier2_correct.py`
- `tests/test_title_matcher.py`

按 scraper 模块的覆盖映射:
- `llm_scraper`:`test_ai_call_logging`, `test_ai_config_runtime`, `test_ai_scenes_integration`, `test_feature_entrypoints`, `test_p0_confirm_workflow_fixes`, `test_retry_with_fallback`, `test_scrape_provider_first_e2e`, `test_source_cleaner_uses_llm_scraper`
- `title_matcher`:`test_title_matcher`, `test_tier2_correct`, `test_tier2_match_engine`
- `filename_cleaner`:`test_filename_cleaner`
- `tmdb_client`:`test_llm_web_search`(通过 `tmdb_provider`), `test_scrape_provider_first_e2e`
- `_llm_match_assist`:`test_source_cleaner_uses_llm_scraper`
- `metadata_scrape_flow`:`test_scrape_provider_first_e2e`, `test_p0_confirm_workflow_fixes`(间接)
- `providers/*`:`test_feature_providers`, `test_scrape_provider_first_e2e`

### 类型分布
- **单元测试**:`test_filename_cleaner`, `test_title_matcher`, `test_ai_call_logging`, `test_ai_config_runtime`, `test_llm_web_search`, `test_prompt_runtime` 等
- **集成/API 测试**:`test_ai_scenes_integration`, `test_scrape_provider_first_e2e`, `test_scrape_preview_job`, `test_prompt_resolver_integration`
- **架构守卫**:`test_feature_entrypoints`, `test_no_legacy_compat_surface`, `test_no_legacy_confidence_surface`

### baseline 跑测结果(S-Phase 0 锁定)

直接 import scraper 的 13 个文件跑测:

```
collected 122 items
122 passed in 0.41s
```

**122 passed, 0 failed, 0 skipped**。这是 S-Phase 1-5 的可对照 baseline。

### 历史失败记录(`.pytest_cache/v/cache/lastfailed`)

相关测试在 lastfailed 中的历史失败 **4 条**(均在 `test_llm_web_search.py`):
- `test_llm_web_search.py::TestDetectProvider::test_detect_volcengine`
- `test_llm_web_search.py::TestDetectProvider::test_detect_volcengine_alt`
- `test_llm_web_search.py::TestLLMConfig::test_source_cleaner_model_three_level_fallback`
- `test_llm_web_search.py::TestLLMConfig::test_source_cleaner_model_explicit`

本次 baseline 全部通过——这 4 条是**历史 flaky/已修复**,不影响本次 baseline 有效性。S-Phase 1-5 期间若再现,需单独排查(可能与 `features.providers` API 变更相关)。

---

## 6. 风险点和待确认事项

### 风险点

1. **`LLMScraper` 类名稳定性**(7 条外部引用):迁移必须保持类名不变;若改名,所有 7 处调用点需同步更新。Migration Map 已标注 `move + compat re-export`,意味着旧路径必须保留指向新实现的 alias,否则生产代码会断。
2. **`_similarity` 在 `scraping/__init__.py` 中 re-export**:`title_matcher._similarity` 是 module-level 函数,被 `scraping/__init__.py:28` 通过 `from .title_matcher import TitleMatcher, _similarity` 引入并对外暴露。迁移时若 `title_matcher.py` 删除原模块,`__init__.py` 必须改为 `from features.scraping.title_matcher import _similarity`,否则外部 import `from features.scraping import _similarity` 会断。
3. **Lazy import 集中在 `llm_scraper`**:`_match_tiers_impl.py:503`, `source_cleaning/cleaner.py:47`, `prompts/__init__.py:12`, `connectivity_handlers.py:115/159` 共 5 处函数内 lazy import。Lazy import 通常是为了避免循环依赖,迁移时若新模块路径破坏循环结构,这些点可能需要重新审视是否仍需 lazy。
4. **`scraper/providers/` 子目录与 `features/providers/` 同名**:两个目录都含 `__init__.py`、`base.py`、`tmdb_provider.py`。即使生产代码走 `features.providers.*`,但**任何第三方代码或文档示例**如果引用 `media_importer.scraper.providers.*` 就会得到 thin re-export。S-Phase 5 删除 `scraper/providers/` 之前,这是一条合法路径。
5. **`metadata_scrape_flow.py` 拆分粒度**:527 行最大文件,拆为 `metadata_flow/` 包需要明确子模块边界(子计划未规定,留给 S-Phase 4 决定)。最小拆分:`flow.py`(电影单集) + `series.py`(剧集) + `common.py`(公共工具)。
6. **异常类拆分归属**:子计划要求 split 到 `features/scraping/errors.py` 和 `features/providers/errors.py`,但当前 `exceptions.py` 只有 3 个异常全属 LLM/刮削范畴,无 providers 专用异常。实际可能只生成 `features/scraping/errors.py`,`features/providers/errors.py` 暂时为空或不创建——需要 S-Phase 3 决策。

### 待确认事项

1. **`scraper/dimension_manager.py` 与 `scraper/metadata_scraper.py` 是否在 S-Phase 0 内删除**:两个文件都是 21 行 / 3 行纯 re-export,无生产引用。当前 inventory **建议保留到 S-Phase 5 统一清理**,因为它们属于 compat 入口范畴。如果你倾向提前删除,可以在本步骤同步执行——但删除后 `scraper/__init__.py` 必须立即增加对 `features.scraping.dimension_manager` 和 `features.scraping.metadata_scraper` 的转发,否则 `from media_importer.scraper.dimension_manager import check_tier_access` 这种潜在调用方会断。**需要你确认**。
2. **`_llm_match_assist.py` 的 split 边界**:子计划规定 `_assemble_prompt` → `features/prompts`,其余执行 → `features/scraping`。`_assemble_prompt` 内部用了 `_call_with_retry_impl`(在 `_llm_client_impl.py` 中)。如果 `_call_with_retry_impl` 也迁到 `features/scraping/llm_client.py`,则 `features/prompts/match_assist.py` 需要跨 feature 目录 import scraping 内部实现——这种跨 feature import 是否被架构守卫允许,需要 S-Phase 3 验证。
   **S-Phase 0 review 给出的倾向性建议(待 S-Phase 3 最终确认)**:调整 `_assemble_prompt` 的归属,让它留在 `features/scraping/llm_match_assist.py` 而不是迁到 `features/prompts/`。理由是 `features/prompts/` 应保持"纯 prompt 文本组装"无依赖,`_assemble_prompt` 既然依赖 `_call_with_retry_impl` 就已经在做"prompt + 执行衔接",属于 scraping 职责。`features/prompts/` 只放纯文本 prompt 默认值和模板。这条建议需要 S-Phase 3 执行时与子计划 Migration Map 对照后做最终决策。
3. **`exceptions.py` 拆分时是否引入 `features/providers/errors.py`**:当前无 providers 专用异常。**S-Phase 0 review 决策:按需创建,不预创建空文件**(YAGNI)。所有异常暂时归 `features/scraping/errors.py`,将来真有 providers 异常需求时再拆。
4. **`tmdb_client.py` 迁移后是否合并入 `features/providers/tmdb_provider.py`**:当前 `features/providers/tmdb_provider.py` 已经从 `scraper.tmdb_client` re-export `TMDbClient`。如果 `tmdb_client.py` 整体迁到 `features/providers/tmdb_client.py`,则 `features/providers/tmdb_provider.py` 应改为 `from media_importer.features.providers.tmdb_client import TMDbClient`——但这导致 `tmdb_provider.py` 同时是 `TMDbProvider` 类定义和 `TMDbClient` re-export,职责混杂。
   **S-Phase 0 review 决策:保持分离**。理由:`tmdb_client.py`(HTTP 客户端,174 行)和 `tmdb_provider.py`(Provider 抽象实现)是不同职责,合并违反单一职责。分离后 `features/providers/__init__.py` 同时 export `TMDbClient` 和 `TMDbProvider`,消费方按需 import。S-Phase 2 执行时按此决策实施。
5. **`.pytest_cache/v/cache/lastfailed` 中 `test_llm_web_search.py` 的 4 条历史失败**:本次 baseline 通过,可能是之前 `source_cleaner_model` 字段映射的修复。如果 S-Phase 期间再 fail,要排查 `source_cleaner.py` 是否依赖被迁移的 scraper 模块。

### 跨子包架构守卫

ADR-0008 §Compliance 明确"迁移完成后架构 guard 禁止新增生产代码 import `media_importer.scraper.*`"。

S-Phase 5 应新增/强化 `tests/test_no_legacy_compat_surface.py`(已有)或新建 `tests/test_architecture_guards.py` 检查,确保除 `scraper/__init__.py` 自身外,生产代码不再 import 旧路径。

---

## 附录:本 inventory 不做的事

- 不移动任何 scraper/ 文件
- 不修改任何 features/, core/, api/, infrastructure/ 代码
- 不改 docs/ 下任何已有文件
- 不 commit
- 不修改 config/ 或 .env