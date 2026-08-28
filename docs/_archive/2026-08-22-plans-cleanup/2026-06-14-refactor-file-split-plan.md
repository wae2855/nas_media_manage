# 文件拆分方案 — 500 行合规（2026-06-14）

> **执行顺序**：Python → JS → CSS → HTML。每个阶段结束后运行回归测试，通过后再进入下一阶段。
>
> **核心原则**：拆分时**不改变公共 API 签名**；原文件通过 `import ... from ...` 重新导出，保持外部引用路径不变。
>
> **可中断**：每个阶段是独立可停的检查点。本文件按"章节→小节→编号步骤"组织，回到项目后从上次未完成的编号步骤继续。

---

## 0. 基线与前置检查

### 0.1 超标文件清单（2026-06-14 快照）

**Python**（3 个文件）：

| # | 文件 | 行数 | 问题 |
|---|------|------|------|
| 1 | `media_importer/scraper/llm_scraper.py` | 603 | LLM 请求 + 刮削入口 + AI 辅助混合在一个类中 |
| 2 | `media_importer/api/tmdb_handlers.py` | 538 | 刮削模拟任务实现 + HTTP handler 混合 |
| 3 | `media_importer/features/scraping/match_engine.py` | 522 | 三级匹配策略 + 主编排流程混合 |

**JS**（4 个文件，全部被 `index.html` 引用为活动文件）：

| # | 文件 | 行数 | 问题 |
|---|------|------|------|
| 4 | `media_importer/webui/js/cinema-config.js` | 2240 | 配置 payload 构建 + 保存 + Provider 预览 + AI 配置 + 规则编辑 + 模拟器 + 维度操作 混合 |
| 5 | `media_importer/webui/js/cinema-tasks.js` | 1608 | 任务卡片/列表 + 详情 + 操作 + 批量混合 |
| 6 | `media_importer/webui/js/dimensions.js` | 1544 | 维度列表/卡片 + Genre picker + 拖拽 + 编辑混合 |
| 7 | `media_importer/webui/js/cinema-app.js` | 1477 | 全局状态 + Dashboard + 事件绑定 + Reel wheel 混合 |

**CSS**（5 个文件，全部被 `index.html` 引用为活动文件）：

| # | 文件 | 行数 | 问题 |
|---|------|------|------|
| 8 | `media_importer/webui/css/cinema-pages.css` | ~3985 | 多页面样式混合 |
| 9 | `media_importer/webui/css/dimensions.css` | ~814 | 维度相关 UI 样式 |
| 10 | `media_importer/webui/css/cinema-advanced.css` | ~705 | 高级配置/Hermes/安全配置样式 |
| 11 | `media_importer/webui/css/components.css` | ~600 | 通用组件样式（按钮/表单/卡片/模态等） |

**HTML**（1 个主文件，超标但需按 partial 拆分）：

| # | 文件 | 行数 | 问题 |
|---|------|------|------|
| 12 | `media_importer/webui/index.html` | 883 | 含 config 视图 ~570 行，适合拆成 partial |

### 0.2 运行基线测试

在启动拆分前，运行一次全部测试以确认基线绿色：

```bash
# 全部测试（含需要本地服务的 UI 测试）
python -m pytest tests/
# 或仅非 UI 测试（作为最低要求）
python -m pytest tests/ --ignore=tests/test_*_ui.py --ignore=tests/test_frontend_*.py --ignore=tests/test_scrape_ui.py
```

记录最后一条输出的 "passed/failed" 总数，作为回归检查点。

### 0.3 编译检查

```bash
python -m compileall -q media_importer
```

所有 Python 文件需通过编译，无 SyntaxError。

---

## Phase 1：Python 拆分（预计 1-2 小时）

**原则**：**保持公共符号路径不变**。新模块是"实现细节"，原文件仅做 `from .xxx import yyy` 再导出，外部调用者完全无感。

---

### Step 1.1：`tmdb_handlers.py`（538 行）→ 2 文件

**内部结构（行号）**：

```
L1-9     import / 全局
L12      _SCRAPE_PREVIEW_JOBS = {}
L16-18   _preview_step_delay
L21-38   _preview_add_step
L41-58   _confirm_reason_from_match
L61-65   _find_provider
L68-401  _run_scrape_preview_job（主体 333 行）
L403-538 TMDbHandlersMixin 类（135 行）
          L408-493  _tmdb_genres_list
          L494-520  _scrape_preview_start
          L523-538  _scrape_preview_status
```

**拆分目标**：

- `api/scrape_preview_job.py`（~345 行，合规边界）
  - `_SCRAPE_PREVIEW_JOBS`
  - `_PREVIEW_STEP_DELAY`
  - `_preview_step_delay()`
  - `_preview_add_step()`
  - `_confirm_reason_from_match()`
  - `_find_provider()`
  - `_run_scrape_preview_job()`
- `api/tmdb_handlers.py`（瘦身到 ~155 行）
  - 保留 `TMDbHandlersMixin` 类
  - 顶部：`from .scrape_preview_job import ( _SCRAPE_PREVIEW_JOBS, _run_scrape_preview_job, _confirm_reason_from_match, _find_provider, _preview_add_step, _preview_step_delay, _PREVIEW_STEP_DELAY, )`

**引用影响分析**（外部引用此文件的位置）：

| 引用方 | 引用内容 | 拆分后是否受影响 |
|--------|----------|------------------|
| `api/handler.py:24` | `from .tmdb_handlers import TMDbHandlersMixin` | ✅ 不变（仍在 `tmdb_handlers.py`） |
| `tests/test_scrape_preview_job.py` | `from media_importer.api.tmdb_handlers import (_run_scrape_preview_job, _SCRAPE_PREVIEW_JOBS, ...)` | ✅ 不变（原文件 re-export） |
| `tests/test_feature_entrypoints.py:72` | 检查文件存在性 | ✅ 不影响 |
| `tests/test_config_api_no_legacy_prompts.py:16` | `from media_importer.api import tmdb_handlers` | ✅ 不变（访问属性 `_SCRAPE_PREVIEW_JOBS` 时通过 re-export） |

**实现步骤**：

1. 新建 `media_importer/api/scrape_preview_job.py`，内容为：
   - L1 开头的 `import time, logging, os, sqlite3, threading, uuid` 及 `from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeout`
   - `from media_importer.api import globals`
   - `from .utils import json_response`
   - `_SCRAPE_PREVIEW_JOBS = {}`
   - `_PREVIEW_STEP_DELAY = 0.8`
   - 原文件 L16-65 的函数（`_preview_step_delay`, `_preview_add_step`, `_confirm_reason_from_match`, `_find_provider`）
   - 原文件 L68-401 的 `_run_scrape_preview_job`
2. 在 `scrape_preview_job.py` 顶部保留同样的 import（与原文件一致）。
3. **在原文件 `tmdb_handlers.py` 顶部**添加 re-export：
   ```python
   from .scrape_preview_job import (
       _SCRAPE_PREVIEW_JOBS,
       _PREVIEW_STEP_DELAY,
       _preview_step_delay,
       _preview_add_step,
       _confirm_reason_from_match,
       _find_provider,
       _run_scrape_preview_job,
   )
   ```
4. 从原文件删除已迁移到 `scrape_preview_job.py` 的函数定义（L12-401 的 `_SCRAPE_PREVIEW_JOBS`、常量、5 个函数）。
5. 保留 `TMDbHandlersMixin` 类（L403-538）在原文件不变。
6. **编译检查**：`python -c "from media_importer.api.tmdb_handlers import TMDbHandlersMixin, _run_scrape_preview_job, _SCRAPE_PREVIEW_JOBS"`
7. **运行相关测试**：`python -m pytest tests/test_scrape_preview_job.py tests/test_scrape_preview_api.py tests/test_config_api_no_legacy_prompts.py tests/test_feature_entrypoints.py -v`

**验收标准**：
- `scrape_preview_job.py` ≤ 345 行
- `tmdb_handlers.py` ≤ 155 行
- 相关测试全部通过

---

### Step 1.2：`llm_scraper.py`（603 行）→ 3 文件

**内部结构（行号）**：

```
L13-14   LLMApiError
L17-18   LLMWebSearchError
L21-22   LLMScrapeError
L25-99   __init__ + _get_default_* + _build_payload
L100-171 _send_request
L173-185 _inject_search
L187-201 _classify_error
L203-228 _do_call
L229-269 _parse_response
L273-298 _retry_with_fallback
L300-312 extract_title
L314-342 scrape
L344-410 scrape_with_context + scrape_series + scrape_series_with_context
L412-494 tier2_correct
L496-601 tier2_judge
```

**拆分目标**（类保持不变，内部方法体委托到独立函数）：

- `scraper/_llm_client_impl.py`（~180 行）
  - `_do_request_send(config, headers, payload, timeout)` — 从 `_send_request` 提取
  - `_do_request_retry(config, headers, payload, fn_send, max_retries, retry_delay, scenario)` — 从 `_retry_with_fallback` 提取
  - `_do_inject_web_search(config, payload, scenario)` — 从 `_inject_search` 提取
  - `_do_classify_error(status_code, body_text, scenario)` — 从 `_classify_error` 提取
  - `_do_parse_response(raw_response, scenario)` — 从 `_parse_response` 提取
  - `_build_payload_int(config, system_prompt, user_content)` — 从 `_build_payload` 提取
- `scraper/_llm_match_assist.py`（~195 行）
  - `_extract_title_impl(llm, filename)` — `extract_title` 实现
  - `_tier2_correct_impl(llm, context)` — `tier2_correct` 实现（保留原方法作为 thin wrapper）
  - `_tier2_judge_impl(llm, context)` — `tier2_judge` 实现
- `scraper/llm_scraper.py`（瘦身到 ~220 行）
  - 保留 3 个异常类
  - 保留 `LLMScraper` 类骨架，方法体改为调用上面两个新模块的函数

**引用影响分析**（外部引用此文件的位置，关键）：

| 引用方 | 引用内容 | 拆分后是否受影响 |
|--------|----------|------------------|
| `media_importer/scraper/metadata_scrape_flow.py:8` | `from .llm_scraper import LLMScrapeError` | ✅ 不变 |
| `media_importer/api/connectivity_handlers.py:111,155` | `from media_importer.scraper.llm_scraper import LLMScraper` | ✅ 不变 |
| `media_importer/features/scraping/metadata_scraper.py:12` | `from media_importer.scraper.llm_scraper import LLMScraper` | ✅ 不变 |
| `media_importer/features/scraping/__init__.py:20` | `from media_importer.scraper.llm_scraper import LLMScrapeError, LLMScraper` | ✅ 不变 |
| `media_importer/scraper/__init__.py:1` | `from .llm_scraper import LLMScraper, LLMScrapeError` | ✅ 不变 |
| `media_importer/features/prompts/__init__.py:13` | `from media_importer.scraper.llm_scraper import LLMScraper` | ✅ 不变 |
| `tests/test_match_engine.py:173,194,217,246` | `patch('media_importer.scraper.llm_scraper.LLMScraper.tier2_correct')` + patch 类 | ⚠️ 需确保方法**仍为类的方法**（thin wrapper 可满足） |
| `tests/test_tier2_match_engine.py:40,68,94,123,142` | 同上 tier2_correct patch | ⚠️ 同上 |
| `tests/test_match_pipeline_integration.py:87,113` | `from media_importer.scraper.llm_scraper import LLMScraper` | ✅ 不变 |
| `tests/test_llm_web_search.py:128-207,237,252,276,314` | `import LLMScraper / LLMApiError / LLMWebSearchError` | ✅ 不变 |
| `tests/test_ai_config_runtime.py`（多次） | `from media_importer.scraper.llm_scraper import LLMScraper` | ✅ 不变 |
| `tests/test_prompt_runtime.py`（多次） | `from media_importer.scraper.llm_scraper import LLMScraper` | ✅ 不变 |
| `tests/test_feature_entrypoints.py:130` | 文件存在性检查 | ✅ 不影响 |

**关键风险点**：`patch('media_importer.scraper.llm_scraper.LLMScraper.tier2_correct')` 生效条件是 `tier2_correct` 必须是 `LLMScraper` 的**真实方法**。方案是保留方法定义，方法体委托到 `_llm_match_assist._tier2_correct_impl(self, ...)`。patch 会拦截方法调用，内部是否调用另一个模块的函数不影响 patch 行为（patch 在方法入口点替换）。

**实现步骤**：

1. 新建 `media_importer/scraper/_llm_client_impl.py`：
   - `from typing import Dict, Any, Optional, List`
   - `import json, re, time, ssl, urllib.request`
   - 将 `_send_request`、`_do_call`、`_inject_search`、`_classify_error`、`_parse_response`、`_retry_with_fallback`、`_build_payload` 的主体**提取为模块级函数**
   - 这些函数接收 `self` 中需要的字段作为显式参数（例如 `_do_inject_web_search` 仅需要 `web_search_config`），或者直接接收 `self` 作为第一个参数——后者更简单，推荐
   - 简单做法：在函数内部通过 `self.xxx` 访问实例属性，签名改为 `_send_request_impl(self, ...)`
2. 新建 `media_importer/scraper/_llm_match_assist.py`：
   - 同样地，将 `extract_title`、`tier2_correct`、`tier2_judge` 的主体提取为接收 `self` 作为第一参数的函数
   - 例如 `def _extract_title_impl(self, prompt): ...`
3. 修改原文件 `llm_scraper.py`：
   - 保留 3 个异常类
   - 保留 `LLMScraper` 类的 `__init__`、`_get_default_*`
   - `_send_request` → 体改为 `return _cli._send_request_impl(self, ...)`
   - `_do_call` → `return _cli._do_call_impl(self, ...)`
   - 其他低层方法同理
   - `tier2_correct` → `return _ma._tier2_correct_impl(self, ...)`
   - `tier2_judge` → `return _ma._tier2_judge_impl(self, ...)`
   - 顶部添加：`from . import _llm_client_impl as _cli` + `from . import _llm_match_assist as _ma`
4. **编译检查**：`python -c "from media_importer.scraper.llm_scraper import LLMScraper, LLMScrapeError, LLMApiError, LLMWebSearchError"`
5. **运行相关测试**（关键路径）：
   ```bash
   python -m pytest tests/test_match_engine.py tests/test_tier2_match_engine.py tests/test_match_pipeline_integration.py tests/test_llm_web_search.py tests/test_ai_config_runtime.py tests/test_prompt_runtime.py tests/test_feature_entrypoints.py tests/test_tier2_correct.py -v
   ```

**验收标准**：
- `_llm_client_impl.py` ≤ 180 行
- `_llm_match_assist.py` ≤ 195 行
- `llm_scraper.py` ≤ 220 行
- 以上测试**全部通过**（重点关注使用 patch 的测试）

---

### Step 1.3：`match_engine.py`（522 行）→ 2 文件

**内部结构（行号）**：

```
L18-26   MatchEngine 类定义 + __init__
L27-32   __init__ 体
L34-90   match()（主入口）
L92-211  _tier1_exact_match（~120 行）
L213-290 _tier2_context_match（~78 行）
L292-329 _tier2_high_certainty（~38 行）
L331-363 _tier2_medium_certainty（~33 行）
L365-393 _tier2_low_certainty（~29 行）
L395-416 _search_providers（~22 行）
L418-455 _collect_context（~38 行）
L457-522 _tier3_user_confirm（~66 行）
```

**拆分目标**：

- `features/scraping/_match_tiers_impl.py`（~370 行）
  - `_tier1_exact_match_impl(engine, filename)`
  - `_tier2_context_match_impl(engine, filename, context)`
  - `_tier2_high_certainty_impl(engine, match, context)`
  - `_tier2_medium_certainty_impl(engine, match, context)`
  - `_tier2_low_certainty_impl(engine, match, context)`
  - `_search_providers_impl(engine, provider_type)`
  - `_collect_context_impl(engine, context_type)`
  - `_tier3_user_confirm_impl(engine, context)`
- `features/scraping/match_engine.py`（瘦身到 ~150 行）
  - 保留 `MatchEngine` 类 + `match()` 方法
  - 所有 `_tier*_*` 方法变成 thin wrapper → 调用 `_tiers.xxx_impl(self, ...)`

**引用影响分析**：

| 引用方 | 引用内容 | 拆分后是否受影响 |
|--------|----------|------------------|
| `features/import_flow/steps/scrape.py:8` | `from media_importer.features.scraping.match_engine import MatchEngine` | ✅ 不变 |
| `api/tmdb_handlers.py:76` | `from media_importer.features.scraping.match_engine import MatchEngine` | ✅ 不变 |
| `tests/test_match_engine.py:5` | `from media_importer.features.scraping.match_engine import MatchEngine` | ✅ 不变 |
| `tests/test_tier2_match_engine.py:7` | `from media_importer.features.scraping.match_engine import MatchEngine` | ✅ 不变 |
| `tests/test_match_engine_keyword_loop.py:55` | `from media_importer.features.scraping.match_engine import MatchEngine` | ✅ 不变 |
| `tests/test_match_pipeline_integration.py:9` | `from media_importer.features.scraping.match_engine import MatchEngine` | ✅ 不变 |
| `tests/test_scrape_preview_job.py:152` | `patch("...match_engine.MatchEngine._tier1_exact_match")` 等 3 个 tier 方法 | ⚠️ 方法仍是类的真实方法（thin wrapper），patch 路径不变 |
| `tests/test_feature_entrypoints.py:72` | 文件存在性检查 | ✅ 不影响 |

**实现步骤**：

1. 新建 `media_importer/features/scraping/_match_tiers_impl.py`：
   - 将每个 `_tier*`、`_search_providers`、`_collect_context` 的**方法体**复制为接收 `engine`（即 self）作为第一个参数的函数
   - 保持 `from media_importer.scraper.llm_scraper import LLMScraper` 动态 import 行为不变（在原方法内部或在 impl 函数内部同样做延迟 import）
2. 修改 `match_engine.py`：
   - 保留 `__init__`
   - 保留 `match()` 不变
   - `_tier1_exact_match(self, filename)` → `return _tiers._tier1_exact_match_impl(self, filename)`
   - 同理处理其他 `_tier*`、`_search_providers`、`_collect_context`、`_tier3_user_confirm`
   - 顶部：`from . import _match_tiers_impl as _tiers`
3. **编译检查**：`python -c "from media_importer.features.scraping.match_engine import MatchEngine"`
4. **运行相关测试**：
   ```bash
   python -m pytest tests/test_match_engine.py tests/test_tier2_match_engine.py tests/test_match_engine_keyword_loop.py tests/test_match_pipeline_integration.py tests/test_scrape_preview_job.py -v
   ```

**验收标准**：
- `_match_tiers_impl.py` ≤ 370 行
- `match_engine.py` ≤ 150 行
- 以上测试全部通过（重点关注 `test_scrape_preview_job.py` 中对 `_tier1_exact_match` 等方法的 patch）

---

### Step 1.4：Phase 1 回归测试

运行完整非 UI 测试套件：

```bash
python -m pytest tests/ --ignore=tests/test_*_ui.py --ignore=tests/test_frontend_*.py --ignore=tests/test_scrape_ui.py
python -m compileall -q media_importer
```

同时手动检查：
```bash
# 检查当前超标文件的行数（仅 Python）
wc -l media_importer/scraper/llm_scraper.py media_importer/api/tmdb_handlers.py media_importer/features/scraping/match_engine.py
```

**Phase 1 验收**：
- ✅ 所有原 Python 文件 ≤ 500 行
- ✅ 非 UI 测试全部通过
- ✅ compileall 无错误

**若以上任一未满足**：
- 回到对应 Step 解决（例如 `_match_tiers_impl.py` 超 500 行 → 进一步拆 `_match_tiers_tier1.py`、`_match_tiers_tier2.py`）
- 不进入 Phase 2

---

## Phase 2：JS 拆分（预计 2-3 小时）

**原则**：所有 `function Xxx()` 声明**仍在全局作用域**（浏览器天然共享）。拆分只是"把函数定义挪到不同的 .js 文件"。`index.html` 中 `<script src="...">` 的**加载顺序需按依赖重新排序**。

**当前 index.html script 顺序**（需要更新）：

```html
<script src="js/api.js?v=1"></script>
<script src="js/tmdb-dict.js?v=1"></script>
<script src="js/cinema-modals.js?v=1"></script>
<script src="js/dimensions.js?v=38"></script>     ← 1544 行，会拆成多个文件
<script src="js/cinema-tasks.js?v=3"></script>     ← 1608 行，会拆成多个文件
<script src="js/cinema-recycle.js?v=1"></script>
<script src="js/cinema-field.js?v=1"></script>
<script src="js/cinema-section.js?v=1"></script>
<script src="js/cinema-config.js?v=11"></script>    ← 2240 行，会拆成多个文件
<script src="js/cinema-app.js?v=7"></script>        ← 1477 行，会拆成多个文件
```

### Phase 2 拆分前的公共函数核对表

**`dimensions.js` 定义的函数**（全局，被其他文件可能调用）：
- `loadDimensions`, `renderDimensions`, `_renderDimCard`, `_renderDimBody`, `_renderRegionMapping`, `_renderLangMapping`
- `toggleDimCard`, `enableDimension`, `disableDimension`, `resetDimension`
- `_renderGenreRows`, `_renderGenreEditable`, `_renderGenrePickerTrigger`, `_buildGenrePickerContent`, `toggleGenrePicker`, `toggleGenreHelp`
- `genreDragStart`, `genreDragEnd`, `genreDragOver`, `genreDragLeave`, `genreDrop`
- `_updateGenreRowsFromData`, `startAddGenre`, `confirmAddGenre`, `cancelAddGenre`, `_resetAddRowButton`, `removeGenreValue`
- `_generateGenrePrompt`, `_collectGenreMappingData`, `_collectMappingData`
- `_escapeHtml`, `_parseValueList`, `_genreIdToLabel`, `_getGenreNameById`
- `_startBackgroundGenreLoad`, `_refreshGenreDisplay`
- `loadProviderGenres`, `getSourceLabel`
- 全局状态：`_dimensionsData`, `_expandedDim`, `_openGenrePicker`, `_genreAdding`, `_cachedProviderGenres`, `_FALLBACK_GENRE_MAP`

**`cinema-tasks.js` 定义的函数**（全局）：
- `getTaskStatusText`, `getTaskTone`, `taskFileName`, `taskDisplayTitle`, `taskDescription`
- `taskMeta`, `taskPrimaryAction`, `taskSecondaryAction`, `formatFileSizeMb`
- `renderTaskSummary`, `renderTaskScrapeProcess`, `renderTaskCard`, `renderTaskList`, `renderStaticLists`
- `setTaskFilter`, `listTasksByStatuses`, `loadTaskList`, `renderErrorState`
- `findTaskRecord`, `extractDimValue`, `buildTaskDimensionsForm`, `formatMultiValue`, `getTaskEditPermission`
- `buildScrapeTraceSection`, `taskToMatchPathData`, `showMatchPathModalFromData`
- `buildSubtitleTable`, `classifyErrorMessage`, `buildScrapeResultSection`, `buildFailureSection`
- `buildRenamePreview`, `updateRenamePreview`, `openTaskDetail`, `openTaskDetailImpl`
- `performTaskAction`, `taskStatusOf`, `taskStageOf`, `isBatchableStatus`
- `getSelectedTaskRecords`, `updateBatchToolbar`, `toggleTaskSelect`, `selectAllVisibleTasks`, `clearTaskSelection`
- `setBatchToolbarVisibility`, `performBatchTaskAction`, `showMatchTraceModal`

**`cinema-config.js` 定义的函数**（全局）：
- `buildSourceConfigPayload`, `buildTempConfigPayload`, `buildRecycleConfigPayload`, `buildRulesConfigPayload`
- `buildImportOptionsPayload`, `getProviderDefinition`, `inferProviderFieldValue`
- `buildSingleProviderConfig`, `buildAllProvidersPayload`, `buildProvidersPayloadFor`, `preserveApiKey`
- `buildAiAssistPayload`, `buildAiSearchPayload`, `buildServerConfigPayload`, `buildHermesConfigPayload`
- `buildAdvancedSystemPayload`, `saveConfigPayload`, `saveSourceConfig`, `saveTempConfig`
- `saveRecycleConfig`, `saveRulesConfig`, `saveProvidersConfig`, `saveLlmConfig`
- `saveAiAssistConfig`, `saveAiScrapeConfig`, `saveImportOptionsConfig`, `saveSecurityConfig`
- `saveHermesConfig`, `saveAdvancedSystemConfig`, `testConfigPath`
- `testAllRulePermissions`, `testProviderConnection`
- `_currentPreviewProviderType` 等（Provider 预览相关）
- `previewProvider`, `doProviderPreviewSearch`, `selectProviderPreviewResult`
- `renderProviderDetailsStructured`, `renderProviderFieldValue`
- `syncAiSearchOptions`, `syncAiSearchEnabledState`
- `loadPromptDefaults`, `resetActivePrompt`, `bindAiConfigInteractions`, `testLlmConnection`
- `openAiScrapeDemoModal`, `closeAiScrapeDemoModal`, `openAiAssistDemoModal`, `closeAiAssistDemoModal`
- `runAiScrapeDemo`, `runAiAssistDemo`, `testHermesConnection`
- `buildProviderField`, `renderInlineProviderConfigs`, `bindProviderCardToggles`, `loadInlineProviderConfigs`
- `renderRuleList`, `renderDimensionVarList`, `loadDimensionVars`, `toggleVarGroup`
- `getEditablePathRules`, `parseRuleConditionValue`, `_dimValueToLabel`
- `openRuleEditor`, `deleteInlineRule`
- `explainSimulatedQueue`, `renderMatchPathPreview`, `renderSimulatorPreview`
- `_simDecisionLabel2`, `_simFormatNumber`, `_renderSimDims`
- `runConfigSimulator`, `pollScrapePreviewJob`, `renderSimulatorProgress`
- `updateConfigStageStatus`, `loadDimensionsList`
- `toggleDimensionEnabled`, `renderEnabledDimensionBadges`
- `collectDimensionOrder`, `saveDimensionOrder`, `performDimensionAction`
- `loadCinemaConfidenceConfig`
- 常量：`SEARCH_TYPE_MAP`, `PROVIDER_BASE_URL_MAP`, `PROVIDER_MODEL_MAP`

**`cinema-app.js` 定义的函数 + 状态**（全局，被大量引用）：
- 状态：`currentTaskFilter`, `currentConfigSnapshot`, `currentTaskRecords`, `currentTaskTotal`, `currentTaskPage`, `currentTaskPageSize`, `currentTaskHasMore`, `currentTaskLoading`, `currentRecycleRecords`, `currentProviderDefinitions`, `currentEnabledDimensions`, `selectedTaskIds`, `selectedRecycleIds`
- 常量：`DASHBOARD_REFRESH_MS`, `TASK_FILTER_META`, `TASK_FILTER_PARAMS`, `STICKY_HERO_VIEWS`
- `setView`, `showToast`, `escapeHtml`, `requestApi`
- `normalizePathValue`, `parseMultilineValue`, `showPathTestFeedback`, `currentPathSnapshot`
- `validateDirectoryConflicts`, `statusCount`, `formatActivityTime`, `activityIcon`, `activityTone`
- `renderActivityRows`, `setDashboardQueueStrip`, `loadHtmlPartial`, `runAction`, `fetchQueueSnapshot`
- `setConfigStage`, `setCleanerTab`, `toggleAdvancedDisclosure`
- `toggleHermesInlineFields`, `toggleSourceCleanerUi`, `toggleSourceDepthField`
- `toggleFileWatcherPollGroup`, `updateStickyHeroState`, `setFieldValue`
- `loadDashboardMetrics`, `loadDashboardQueueStatus`, `loadDashboardActivity`, `loadDashboardOverview`
- `startDashboardAutoRefresh`, `collectHelpItemsForGrid`, `buildHelpAccordion`, `initHelpAccordions`
- `loadDirectoryConfig`（263 行，大函数）
- `bindEvents`（277 行，大函数）
- `initReelWheel`, `buildReelWheel`, `loadReelWheelFromTasks`
- `updateScrapeModeHint`, `updateWebSearchSupport`, `updateAiConfigStatus`

**跨文件依赖图（谁调用谁）**：

| 调用方 | 调用内容 | 目标文件 | 关系 |
|--------|----------|----------|------|
| `cinema-app.js` bindEvents | `setTaskFilter`, `loadTaskList`, `performTaskAction`, `performBatchTaskAction`, `toggleTaskSelect`, `selectAllVisibleTasks`, `clearTaskSelection`, `openTaskDetail`, `showMatchTraceModal`, `renderTaskList`, `setBatchToolbarVisibility`, `updateBatchToolbar`, `performRecycleAction`, `toggleRecycleSelect`, `performBatchRecycleAction`, `saveSourceConfig`, `saveTempConfig`, `saveRecycleConfig`, `saveRulesConfig`, `saveProvidersConfig`, `saveLlmConfig`, `saveAiAssistConfig`, `saveAiScrapeConfig`, `saveImportOptionsConfig`, `saveSecurityConfig`, `saveHermesConfig`, `saveAdvancedSystemConfig`, `testConfigPath`, `testAllRulePermissions`, `testProviderConnection`, `testLlmConnection`, `testHermesConnection`, `runAiScrapeDemo`, `runAiAssistDemo`, `runConfigSimulator` | `cinema-tasks.js` + `cinema-config.js` | 被依赖方**须先加载** |
| `cinema-app.js` loadDirectoryConfig | `loadInlineProviderConfigs`, `loadDimensions`, `loadDimensionVars`, `renderRuleList`, `loadCinemaConfidenceConfig`, `toggleSourceCleanerUi`, `toggleSourceDepthField`, `toggleHermesInlineFields`, `toggleFileWatcherPollGroup` | `cinema-config.js` + `dimensions.js` | 同上 |
| `cinema-app.js` 其他 | `renderStaticLists`, `loadReelWheelFromTasks`, `loadDirectoryConfig`, `bindEvents`, `bindAiConfigInteractions`, `checkApiKeyRequired` | 多个文件 | 同上 |
| `cinema-config.js` | `requestApi`, `showToast`, `setFieldValue`, `setConfigStage`, `updateStickyHeroState`, `setCleanerTab`, `toggleAdvancedDisclosure` | `cinema-app.js` | 循环依赖但浏览器全局作用域下**可行**（函数是声明，运行时才查找） |
| `cinema-tasks.js` | `requestApi`, `showToast`, `escapeHtml` | `cinema-app.js` | 需 cinema-app 先加载 |
| `dimensions.js` | `apiRequest`（来自 `api.js`） | `api.js` | 已先加载 |

**关键结论**：函数声明是"惰性解析"——只要在 `<body>` 加载完成前全部函数已定义到 window，调用时都能找到。因此**加载顺序的核心要求是 "state 变量（如 `currentTaskRecords`、`currentProviderDefinitions`）在第一次被读取前必须已定义"**。

**新的加载顺序**（拆分后）：
```html
<!-- 1. 基础工具 & API（无状态依赖） -->
<script src="js/api.js?v=1"></script>
<script src="js/tmdb-dict.js?v=1"></script>
<script src="js/cinema-modals.js?v=1"></script>

<!-- 2. 全局状态（必须最先加载，各子文件会读写这些变量） -->
<script src="js/cinema-app-state.js?v=1"></script>

<!-- 3. 任务相关：utils → list → detail → actions → 入口 -->
<script src="js/cinema-task-utils.js?v=1"></script>
<script src="js/cinema-task-list.js?v=1"></script>
<script src="js/cinema-task-detail.js?v=1"></script>
<script src="js/cinema-task-actions.js?v=1"></script>
<script src="js/cinema-tasks.js?v=4"></script>   <!-- 现为入口，仅常量或空文件 -->

<!-- 4. 维度相关：genre 核心 → 列表 → 编辑 → 入口 -->
<script src="js/dimension-genre.js?v=1"></script>
<script src="js/dimension-list.js?v=1"></script>
<script src="js/dimension-edit.js?v=1"></script>
<script src="js/dimensions.js?v=39"></script>   <!-- 状态容器，也保留 _FALLBACK_GENRE_MAP -->

<!-- 5. 回收/字段/section（小文件，保持原样） -->
<script src="js/cinema-recycle.js?v=1"></script>
<script src="js/cinema-field.js?v=1"></script>
<script src="js/cinema-section.js?v=1"></script>

<!-- 6. Config 相关：payloads → save → provider → AI → rules → simulator → dim ops → 入口 -->
<script src="js/cinema-config-payloads.js?v=1"></script>
<script src="js/cinema-config-save.js?v=1"></script>
<script src="js/cinema-config-provider.js?v=1"></script>
<script src="js/cinema-config-ai.js?v=1"></script>
<script src="js/cinema-config-rules.js?v=1"></script>
<script src="js/cinema-config-simulator.js?v=1"></script>
<script src="js/cinema-config-dim-ops.js?v=1"></script>
<script src="js/cinema-config.js?v=12"></script>    <!-- 保留常量 SEARCH_TYPE_MAP 等 -->

<!-- 7. Dashboard / loader / events / reel（这些函数依赖上面全部模块先加载） -->
<script src="js/cinema-dashboard.js?v=1"></script>
<script src="js/cinema-directory-loader.js?v=1"></script>
<script src="js/cinema-app-events.js?v=1"></script>
<script src="js/cinema-reel.js?v=1"></script>
<script src="js/cinema-app.js?v=8"></script>        <!-- 现仅 DOMContentLoaded init 块 -->
```

---

### Step 2.1：`cinema-config.js`（2240 行）→ 7+1 文件

**按功能域精确拆分**（函数按功能聚类，行号来自 grep 结果）：

#### 2.1.1 `js/cinema-config-payloads.js`（~430 行）

**提取的函数**（payload 构建）：
- `buildSourceConfigPayload()`
- `buildTempConfigPayload()`
- `buildRecycleConfigPayload()`
- `buildRulesConfigPayload()`
- `buildImportOptionsPayload()`
- `getProviderDefinition()`
- `inferProviderFieldValue()`
- `buildSingleProviderConfig(provider, providerDefinitions)`
- `buildAllProvidersPayload(config)`
- `buildProvidersPayloadFor(provider_type, config)`
- `preserveApiKey(config)`
- `buildAiAssistPayload()`
- `buildAiSearchPayload()`
- `buildServerConfigPayload()`
- `buildHermesConfigPayload()`
- `buildAdvancedSystemPayload()`

**步骤**：
1. 创建 `js/cinema-config-payloads.js`，顶部放 `// cinema-config-payloads.js` 注释
2. 把上述函数**整段**复制到新文件
3. 保留 `SEARCH_TYPE_MAP`、`PROVIDER_BASE_URL_MAP`、`PROVIDER_MODEL_MAP`**在原文件**（它们是跨功能域的常量）
4. 从原文件删除已搬迁的函数定义
5. 在 `index.html` 中 `<script src="js/cinema-config-payloads.js?v=1"></script>` 加在 `cinema-config.js` 之前

#### 2.1.2 `js/cinema-config-save.js`（~150 行）

**提取的函数**（保存）：
- `saveConfigPayload(payload, successText)`
- `saveSourceConfig()`
- `saveTempConfig()`
- `saveRecycleConfig()`
- `saveRulesConfig()`
- `saveProvidersConfig(providerType)`
- `saveLlmConfig()`
- `saveAiAssistConfig()`
- `saveAiScrapeConfig()`
- `saveImportOptionsConfig()`
- `saveSecurityConfig()`
- `saveHermesConfig()`
- `saveAdvancedSystemConfig()`
- `testConfigPath(path)`
- `testAllRulePermissions()`
- `testProviderConnection(providerType)`

#### 2.1.3 `js/cinema-config-provider.js`（~380 行）

**提取的函数**（Provider 配置 + 预览）：
- `_currentPreviewProviderType` / `_tmdbSelectedResultId` / `_tmdbSelectedResultType` 状态变量
- `previewProvider(providerType)`
- `doProviderPreviewSearch()`
- `selectProviderPreviewResult(providerId, providerName)`
- `renderProviderDetailsStructured(providerDetails, raw)`
- `renderProviderFieldValue(field, value, raw)`
- `buildProviderField(providerType, field, rawValue)`
- `renderInlineProviderConfigs(providerDefs, savedProviders)`
- `bindProviderCardToggles()`
- `loadInlineProviderConfigs(config)`

**注意**：`_currentPreviewProviderType` 等状态变量定义在这个文件中，它们在 preview 操作时被读写。

#### 2.1.4 `js/cinema-config-ai.js`（~240 行）

**提取的函数**（AI 配置交互）：
- `syncAiSearchOptions(forceBaseUrl)`
- `syncAiSearchEnabledState()`
- `loadPromptDefaults()`
- `resetActivePrompt(group)`
- `bindAiConfigInteractions()`
- `testLlmConnection()`
- `openAiScrapeDemoModal()`
- `closeAiScrapeDemoModal()`
- `openAiAssistDemoModal()`
- `closeAiAssistDemoModal()`
- `runAiScrapeDemo(scenario, demoFile)`
- `runAiAssistDemo(scenario, demoFile)`
- `testHermesConnection()`

#### 2.1.5 `js/cinema-config-rules.js`（~180 行）

**提取的函数**（路径规则编辑/渲染）：
- `renderRuleList(pathRules)`
- `renderDimensionVarList(dimensions)`
- `loadDimensionVars()`
- `toggleVarGroup(name)`
- `getEditablePathRules()`
- `parseRuleConditionValue(rule, dimName)`
- `_dimValueToLabel(dim, value)`
- `openRuleEditor(ruleIndex = -1)`
- `deleteInlineRule(index)`

#### 2.1.6 `js/cinema-config-simulator.js`（~310 行）

**提取的函数**（模拟器/刮削预览）：
- `explainSimulatedQueue(result)`
- `renderMatchPathPreview(matchPath)`
- `renderSimulatorPreview(filename, result)`
- `_simDecisionLabel2(step)`
- `_simFormatNumber(n)`
- `_renderSimDims(dims)`
- `runConfigSimulator(filename)`
- `pollScrapePreviewJob(jobId, filename)`
- `renderSimulatorProgress(steps, jobStatus, extraHtml)`

#### 2.1.7 `js/cinema-config-dim-ops.js`（~180 行）

**提取的函数**（维度操作/状态同步）：
- `updateConfigStageStatus(config, paths, pathRules)`
- `loadDimensionsList()`
- `toggleDimensionEnabled(dimName)`
- `renderEnabledDimensionBadges(enabledDims, availableDims)`
- `collectDimensionOrder()`
- `saveDimensionOrder()`
- `performDimensionAction(action, dimName)`
- `loadCinemaConfidenceConfig(rawConfig)`

**注意**：`renderEnabledDimensionBadges`、`loadDimensionsList`、`toggleDimensionEnabled`、`collectDimensionOrder`、`saveDimensionOrder`、`performDimensionAction` 与 `dimensions.js` 中的维度管理不是同一套——它们是"配置页内的维度小工具"。`dimensions.js` 是独立的"高级配置/维度管理"页。二者命名不冲突，互不干扰。

#### 2.1.8 原文件瘦身

**保留在 `cinema-config.js` 的内容**：
- 顶部 `// cinema-config.js — 配置模块入口，实现分布在 cinema-config-*.js` 注释
- 常量 `SEARCH_TYPE_MAP`、`PROVIDER_BASE_URL_MAP`、`PROVIDER_MODEL_MAP`
- 空文件也可（所有函数已被迁出）——但为了 `index.html` 中的 `<script src="js/cinema-config.js?v=12">` 保留兼容，保留一个最小版本

#### 2.1.9 拆分后检查

检查每个新文件行数：
```bash
wc -l media_importer/webui/js/cinema-config-*.js
```

**验收**：每个新文件 ≤ 500 行，总和 ~1870 行 + 入口 ~50 行 ≈ 1920 行。
（如某子文件超 500 → 进一步拆）

#### 2.1.10 手工浏览器检查

1. 启动服务：`PYTHONPATH="${PWD}" python -m media_importer.media_importer -c config/config.yaml serve -p 9855`
2. 访问 `http://localhost:9855/webui/`
3. 检查：
   - 控制台无 `Uncaught ReferenceError`
   - 视图切换正常（Dashboard → Tasks → Recycle → Config）
   - Config 视图中：保存按钮触发 `saveSourceConfig` → 有 toast 反馈
   - Provider 预览弹窗可打开、可关闭
   - AI 配置测试按钮可点击
   - 运行配置模拟器（需要 provider 配置正确）

---

### Step 2.2：`cinema-tasks.js`（1608 行）→ 4+1 文件

#### 2.2.1 `js/cinema-task-utils.js`（~120 行）

**提取**：
- `getTaskStatusText(status, stage)`
- `getTaskTone(task)`
- `taskFileName(task)`
- `taskDisplayTitle(task)`
- `taskDescription(task)`
- `taskMeta(task)`
- `taskPrimaryAction(task)`
- `taskSecondaryAction(task)`
- `formatFileSizeMb(sizeMb)`
- `renderTaskSummary(task)`
- `renderTaskScrapeProcess(task)`

#### 2.2.2 `js/cinema-task-list.js`（~170 行）

**提取**：
- `renderTaskCard(item, index)`
- `renderTaskList()`
- `renderStaticLists()`
- `setTaskFilter(filter)`
- `listTasksByStatuses(params, page, pageSize)`
- `loadTaskList(append)`
- `renderErrorState(message)`
- `findTaskRecord(taskId)`
- `extractDimValue(raw)`

#### 2.2.3 `js/cinema-task-detail.js`（~430 行）

**提取**（大函数集中区）：
- `buildTaskDimensionsForm(task, editable, enabled)`
- `formatMultiValue(value, options)`
- `getTaskEditPermission(task)`
- `buildScrapeTraceSection(task)`
- `taskToMatchPathData(task)`
- `showMatchPathModalFromData(dataJson, filename)`
- `buildSubtitleTable(subtitles)`
- `classifyErrorMessage(message)`
- `buildScrapeResultSection(task)`
- `buildFailureSection(task)`
- `buildRenamePreview(originalFilename)`
- `updateRenamePreview(inputEl)`
- `openTaskDetail(taskId)`
- `openTaskDetailImpl(task, htmlId)`

**⚠️ 此文件约 430 行，接近 500 上限**。若实际超 500，进一步把 `buildScrapeTraceSection` + `showMatchPathModalFromData` + `buildSubtitleTable` 三个"trace 相关"函数拆到 `js/cinema-task-trace.js`（~150 行），这样 detail 变 ~280 行。

#### 2.2.4 `js/cinema-task-actions.js`（~290 行）

**提取**：
- `performTaskAction(action, taskId)`
- `taskStatusOf(task)`
- `taskStageOf(task)`
- `isBatchableStatus(status)`
- `getSelectedTaskRecords()`
- `updateBatchToolbar()`
- `toggleTaskSelect(taskId)`
- `selectAllVisibleTasks()`
- `clearTaskSelection()`
- `setBatchToolbarVisibility()`
- `performBatchTaskAction(action)`
- `showMatchTraceModal(trace, filename)`

#### 2.2.5 原文件瘦身

`cinema-tasks.js` 保留常量 `MULTI_SELECT_DIMS = new Set(...)`（如果文件里有这个定义——经查，此文件中定义了 `MULTI_SELECT_DIMS`，否则为空）。若为空，保留一行 `// cinema-tasks.js — 任务模块入口，实现分布在 cinema-task-*.js`。

#### 2.2.6 验收

```bash
wc -l media_importer/webui/js/cinema-task-*.js media_importer/webui/js/cinema-tasks.js
```

每个 ≤ 500 行。手工测试：任务列表可加载、点击任务打开详情、勾选任务 → 批量按钮可见、批量操作功能正常。

---

### Step 2.3：`dimensions.js`（1544 行）→ 3+1 文件

#### 2.3.1 `js/dimension-genre.js`（~480 行）

**提取**（Genre 映射 + Picker + 拖拽 + 映射数据收集）：
- `_FALLBACK_GENRE_MAP` ← 这个在 dimensions.js 顶部，保留在 dimensions.js 作为状态中心
- `_escapeHtml(str)` — **建议保留在 dimensions.js**（工具函数，被多个子模块调用，放在最底层）
- `_parseValueList(raw)` — 同上，工具函数，保留在 dimensions.js
- `_genreIdToLabel(ids)` — 提取
- `_getGenreNameById(id)` — 提取
- `loadProviderGenres(providerType)` — 提取
- `_startBackgroundGenreLoad()` — 提取
- `_refreshGenreDisplay()` — 提取
- `_renderGenreRowHTML(dimName, item, origIdx, displayOrderNum)` — 提取
- `_renderGenreRows(dimName, valueList)` — 提取
- `_renderGenreEditable(dimName, valueList)` — 提取
- `_renderGenrePickerTrigger(dimName, idx, selectedIds)` — 提取
- `_buildGenrePickerContent(idx, selectedIds)` — 提取
- `toggleGenrePicker(dimName, idx)` — 提取
- `toggleGenreHelp()` — 提取
- `genreDragStart(e, dimName, idx)` — 提取
- `genreDragEnd(e)` — 提取
- `genreDragOver(e)` — 提取
- `genreDragLeave(e)` — 提取
- `genreDrop(e, dimName, targetIdx)` — 提取
- `_updateGenreRowsFromData(dimName, valueList)` — 提取
- `startAddGenre(dimName)` — 提取
- `confirmAddGenre(dimName, label, value)` — 提取
- `cancelAddGenre(dimName)` — 提取
- `_resetAddRowButton(dimName)` — 提取
- `removeGenreValue(dimName, idx)` — 提取
- `_generateGenrePrompt()` — 提取
- `_collectGenreMappingData(dimName)` — 提取
- `_collectMappingData()` — 提取

#### 2.3.2 `js/dimension-list.js`（~220 行）

**提取**（维度列表/卡片渲染）：
- `getSourceLabel(sourceType)`
- `loadDimensions()`
- `renderDimensions()`
- `_renderDimCard(dim, isEnabled)`
- `_renderDimBody(dim)`
- `_renderRegionMapping(valueList)`
- `_renderLangMapping(valueList)`

#### 2.3.3 `js/dimension-edit.js`（~70 行）

**提取**（启用/禁用/重置）：
- `toggleDimCard(name)`
- `enableDimension(name)`
- `disableDimension(name)`
- `resetDimension(name)`

#### 2.3.4 原文件瘦身

`dimensions.js` 保留：
- 全局状态：`_dimensionsData = []`, `_expandedDim = null`, `_openGenrePicker = null`, `_genreAdding = null`, `_cachedProviderGenres = null`
- `_FALLBACK_GENRE_MAP`（大常量）
- `_escapeHtml(str)`（小工具函数，被多个子文件引用——因为共享全局作用域，子文件不需要 import 也能调用）
- `_parseValueList(raw)`（同理）
- 顶部注释：`// dimensions.js — 维度模块入口 + 共享状态，实现分布在 dimension-*.js`

**⚠️ 关键**：`_cachedProviderGenres` 必须在 `dimensions.js` 中定义——因为 `dimension-genre.js` 的 `loadProviderGenres` 会读写它。由于浏览器全局，函数定义在 `dimension-genre.js` 时通过 `window._cachedProviderGenres` 或全局名直接访问即可（后者更自然——JS 默认读写全局变量）。

#### 2.3.5 验收

```bash
wc -l media_importer/webui/js/dimension-*.js media_importer/webui/js/dimensions.js
```

每个 ≤ 500 行。手工测试：在 Advanced → Dimensions 视图，维度列表加载、展开、拖动 Genre、添加/删除 Genre 正常。

---

### Step 2.4：`cinema-app.js`（1477 行）→ 4+1 文件

#### 2.4.1 `js/cinema-app-state.js`（~230 行）

**提取**（全局状态 + 常量 + 小工具函数）：
- `DASHBOARD_REFRESH_MS`
- `TASK_FILTER_META`
- `TASK_FILTER_PARAMS`
- `STICKY_HERO_VIEWS`
- `currentTaskFilter`
- `currentConfigSnapshot`
- `currentCleanerTab`
- `currentTaskRecords`
- `currentTaskTotal`
- `currentTaskPage`
- `currentTaskPageSize`
- `currentTaskHasMore`
- `currentTaskLoading`
- `currentRecycleRecords`
- `currentProviderDefinitions`
- `currentEnabledDimensions`
- `selectedTaskIds`
- `selectedRecycleIds`
- 小工具函数：
  - `setView(view, navKey)`
  - `showToast(message)`
  - `maskValue(value)`
  - `escapeHtml(value)`
  - `requestApi(method, endpoint, body, options)`
  - `normalizePathValue(value)`
  - `parseMultilineValue(id)`
  - `showPathTestFeedback(result, label)`
  - `currentPathSnapshot()`
  - `validateDirectoryConflicts(paths)`
  - `statusCount(source, ...keys)`
  - `formatActivityTime(value)`
  - `activityIcon(level)`
  - `activityTone(level)`
  - `setFieldValue(id, value)`
  - `updateStickyHeroState()`
  - `setConfigStage(stage)`
  - `setCleanerTab(tab)`
  - `toggleAdvancedDisclosure(name)`
  - `toggleHermesInlineFields()`
  - `toggleSourceCleanerUi()`
  - `toggleSourceDepthField()`
  - `toggleFileWatcherPollGroup()`

**⚠️ `cinema-app-state.js` 必须**最先被加载（在 `cinema-config-*`、`cinema-task-*`、`dimension-*` 之前），因为那些模块会读写上面的状态变量与小工具函数。

#### 2.4.2 `js/cinema-dashboard.js`（~320 行）

**提取**（Dashboard 加载/渲染 + 队列操作）：
- `renderActivityRows(items)`
- `setDashboardQueueStrip(text, ratio)`
- `loadHtmlPartial(targetId, url)` — **⚠️ 需放在这里或单独 util，原文件中 bindEvents 也调用它**
- `runAction(action, trigger)`
- `fetchQueueSnapshot()`
- `loadDashboardMetrics()`
- `loadDashboardQueueStatus()`
- `loadDashboardActivity()`
- `loadDashboardOverview()`
- `startDashboardAutoRefresh()`
- `collectHelpItemsForGrid(grid)`
- `buildHelpAccordion(items)`
- `initHelpAccordions()`

#### 2.4.3 `js/cinema-directory-loader.js`（~265 行）

**提取**（大函数：loadDirectoryConfig — 263 行）：
- `loadDirectoryConfig()`

这个函数内部调用：
- `setFieldValue(id, value)`（来自 state.js）
- `toggleSourceCleanerUi()`（来自 state.js）
- `toggleSourceDepthField()`（来自 state.js）
- `toggleHermesInlineFields()`（来自 state.js）
- `toggleFileWatcherPollGroup()`（来自 state.js）
- `updateConfigStageStatus()`（来自 `cinema-config-dim-ops.js`）
- `loadCinemaConfidenceConfig()`（来自 `cinema-config-dim-ops.js`）
- `loadInlineProviderConfigs()`（来自 `cinema-config-provider.js`）
- `loadDimensions()`（来自 `dimensions.js` 或 `dimension-list.js`）
- `loadDimensionVars()`（来自 `cinema-config-rules.js`）
- `renderRuleList()`（来自 `cinema-config-rules.js`）

只要上述**所有模块**都在 `cinema-directory-loader.js` 之前加载，就没问题。按我们的顺序：
1. `cinema-app-state.js` → 提供 setFieldValue 等
2. `cinema-config-*.js`（已加载全部）→ 提供 updateConfigStageStatus、loadCinemaConfidenceConfig、loadInlineProviderConfigs、loadDimensionVars、renderRuleList
3. `dimensions.js`（已加载）→ 提供 loadDimensions
4. 最后才是 `cinema-directory-loader.js`

✓ 依赖全部满足。

#### 2.4.4 `js/cinema-app-events.js`（~280 行）

**提取**（大函数：bindEvents — 277 行）：
- `bindEvents()`

这个函数做两件事：
1. 在 `<body>` 上监听大量 `data-xxx` 属性驱动的事件，派发到对应的处理函数（`setView`, `setTaskFilter`, `setConfigStage`, `setCleanerTab`, `toggleVarGroup`, `toggleAdvancedDisclosure`, `performTaskAction`, `toggleTaskSelect`, `openTaskDetail`, `performBatchTaskAction`, `performRecycleAction`, `toggleRecycleSelect`, `performBatchRecycleAction`, `saveSourceConfig`, `saveTempConfig`, ..., `runConfigSimulator`, `runAction`, 等等）
2. 监听一些表单元素的 change/input 事件

**⚠️ 关键**：`bindEvents` 调用的**全部**函数必须在本文件**之前**定义。按我们的顺序：
- 任务相关函数（已在 `cinema-task-*.js` 定义）✓
- Config 相关函数（已在 `cinema-config-*.js` 定义）✓
- State 小工具函数（已在 `cinema-app-state.js` 定义）✓
- Dashboard 中的 `loadHtmlPartial`、`runAction`（已在 `cinema-dashboard.js` 定义）✓

✓ 依赖全部满足，只要 `bindEvents` 在最后。

#### 2.4.5 `js/cinema-reel.js`（~170 行）

**提取**（Reel wheel + 刮削模式提示 / 联网搜索支持 / AI 配置状态）：
- `initReelWheel()`
- `buildReelWheel(items)` — 注意：此函数挂载在 `window.buildReelWheel`，被 `loadReelWheelFromTasks` 调用
- `loadReelWheelFromTasks()`
- `updateScrapeModeHint()`
- `updateWebSearchSupport()`
- `updateAiConfigStatus()`

#### 2.4.6 原文件瘦身

`cinema-app.js` 仅剩：
- `DOMContentLoaded` 事件监听器（原文件末尾，~20 行）
- 这个初始化块内部调用：`loadHtmlPartial('advanced-pages-slot', ...)`, `bindEvents()`, `renderStaticLists()`, `initReelWheel()`, `setTaskFilter("all")`, `loadTaskList()`, `loadRecycleData()`, `setConfigStage("start")`, `setCleanerTab("delete")`, `updateStickyHeroState()`, `loadDashboardOverview()`, `loadReelWheelFromTasks()`, `startDashboardAutoRefresh()`, `initHelpAccordions()`, `bindAiConfigInteractions()`, `loadDirectoryConfig()`, `checkApiKeyRequired()`
- 顶部注释

#### 2.4.7 验收

```bash
wc -l media_importer/webui/js/cinema-app-state.js media_importer/webui/js/cinema-dashboard.js media_importer/webui/js/cinema-directory-loader.js media_importer/webui/js/cinema-app-events.js media_importer/webui/js/cinema-reel.js media_importer/webui/js/cinema-app.js
```

每个 ≤ 500 行。手工测试：页面首页加载 → Dashboard 显示 metrics → 任务列表 → 回到配置 → 所有视图切换无错误。

---

### Step 2.5：Phase 2 回归测试

**自动化**（若已存在 Playwright 测试）：
```bash
python -m pytest tests/test_frontend_*.py tests/test_*_ui.py tests/test_scrape_ui.py -v
```

**手工检查清单**（必须逐项确认）：

- [ ] 打开首页无控制台错误
- [ ] 路由切换（Dashboard → Tasks → Recycle → Config → Advanced）无错误
- [ ] Config 视图中：保存路径配置、保存 provider、测试 LLM 连接、测试 Hermes
- [ ] Config 视图中：运行配置模拟器
- [ ] Config 视图中：打开 Provider 预览 → 搜索 → 选中 → 关闭
- [ ] Config 视图中：AI 配置交互（prompt 默认值加载、重置）
- [ ] Tasks 视图中：列表加载、筛选、详情、批量勾选、批量操作
- [ ] Dimensions 视图中：列表加载、展开/折叠、Genre 拖动、启用/禁用维度
- [ ] Recycle 视图：列表加载、条目操作
- [ ] Dashboard：指标显示、自动刷新（如果触发）、reel wheel
- [ ] 切换窗口大小/滚动：sticky hero 行为正常

**JavaScript 语法检查**（可选，但推荐）：
```bash
# 用 node 做语法检查
node --check media_importer/webui/js/cinema-app-state.js
node --check media_importer/webui/js/cinema-dashboard.js
node --check media_importer/webui/js/cinema-directory-loader.js
node --check media_importer/webui/js/cinema-app-events.js
node --check media_importer/webui/js/cinema-reel.js
node --check media_importer/webui/js/cinema-config-payloads.js
# ... 对每个新 JS 文件重复
```
（注意：node --check 会报告 `document is not defined` 之类的 ReferenceError——那只是 node 无 DOM，不是语法错误。应该看 "SyntaxError"。）

---

## Phase 3：CSS 拆分（预计 1-2 小时）

**原则**：CSS 选择器在浏览器中天然全局——拆分只是"把同一 CSS 文件的不同区域代码挪到不同文件"，选择器名称不变。最终通过 `<link>` 并行加载或 `@import` 组合。

### Step 3.1：`cinema-pages.css`（~3985 行）→ 按页面拆 6 文件

由于选择器在 CSS 里是无结构的，需要**按 grep 手工分组**：

**前期分析步骤**（在开始前执行，输出填入下表）：

```bash
# 列出所有顶层选择器前缀，统计每组大致行数
grep -n '^\..*\s*{' media_importer/webui/css/cinema-pages.css | head -50
# 或更粗：按 top-level 类名首段分组
grep -nE '^\.(hero|metric|dashboard|task|recycle|config|dim|provider|match|sim|rule|modal|help|form|stage|ai|naming|clean|batch|step|section|page|panel|reel|queue)' \
  media_importer/webui/css/cinema-pages.css
```

**预期拆分**（根据代码结构推断，需实际核对）：

| 新文件 | 内容（选择器） | 预估行数 |
|--------|----------------|----------|
| `css/cinema-dashboard.css` | `.hero`, `.hero-*`, `.metric*`, `.dashboard-*`, `.module-card*`, `.module-grid*`, `.activity-*`, `.now-strip*`, `.queue-status-*` | ~650 |
| `css/cinema-task-list.css` | `.task-list*`, `.task-card*`, `.task-summary*`, `.task-filter*`, `.task-empty-state*`, `.task-load-more*`, `.batch-toolbar*` | ~550 |
| `css/cinema-task-detail.css` | `.task-detail*`, `.scrape-trace-section*`, `.match-path-modal*`, `.match-trace-modal*`, `.subtitle-table*`, `.scrape-result-section*`, `.failure-section*`, `.rename-preview*` | ~480 |
| `css/cinema-recycle.css` | `.recycle-*`（含 recycle stats / cards / actions） | ~350 |
| `css/cinema-config-stage.css` | `.config-stage-panel*`, `.config-stage-status*`, `.stage-*`, `.sim-step*`, `.simulator-*`, `.rule-inline-*`, `.path-preview-*` | ~580 |
| `css/cinema-config-modals.css` | `.provider-preview-modal*`, `.tmdb-preview-modal*`, `.ai-demo-modal*`, `.modal-*`（非通用） | ~300 |
| `css/cinema-config-help.css` | `.help-accordion*`, `.info-intro*`, `.info-rows*`, `.info-callout*` | ~180 |
| `css/cinema-enhancements.css` | `.is-condensed`, `.glow`, `.animate-pulse`, `.is-enabled`, `.is-disabled`, `.status-configured`, `.is-disabled-status`, `.scrape-mode-hint*` 等通用状态样式 | ~180 |
| `cinema-pages.css`（瘦身） | 顶部注释 + 剩余未分类兜底（若 <300 行） | ~200 |

> **若 `cinema-dashboard.css` 预估 650 行或 `cinema-config-stage.css` 预估 580 行超 500**：进一步拆。例如 `cinema-dashboard.css` 拆成 `cinema-dashboard-hero.css` + `cinema-dashboard-metric.css` + `cinema-dashboard-main.css`。同理 `cinema-config-stage.css` 拆成 `cinema-config-stage-main.css` + `cinema-config-stage-sim.css`。

---

#### Step 3.1.1 实际拆分步骤（`cinema-pages.css`）

1. **先做选择器清单**（记录在下面表中，作为拆分时的切割依据）：

```bash
grep -nE '^\.' media_importer/webui/css/cinema-pages.css | head -100
```

2. **按上表 8 个新文件分类创建**：
   - 新建 `css/cinema-dashboard.css`，把 `.hero*` / `.metric*` / `.dashboard*` / `.module-card*` / `.module-grid*` / `.activity*` / `.now-strip*` / `.queue-status*` 区块整体剪切过来
   - 新建 `css/cinema-task-list.css`，把 `.task-list*` / `.task-card*` / `.task-summary*` / `.task-filter*` / `.task-empty-state*` / `.task-load-more*` / `.batch-toolbar*` 区块整体剪切过来
   - 新建 `css/cinema-task-detail.css`，把 `.task-detail*` / `.scrape-trace-section*` / `.match-path-modal*` / `.match-trace-modal*` / `.subtitle-table*` / `.scrape-result-section*` / `.failure-section*` / `.rename-preview*` 区块整体剪切过来
   - 新建 `css/cinema-recycle.css`，把 `.recycle-*` 区块整体剪切过来
   - 新建 `css/cinema-config-stage.css`，把 `.config-stage-panel*` / `.config-stage-status*` / `.stage-*` / `.sim-step*` / `.simulator-*` / `.rule-inline-*` / `.path-preview-*` 区块整体剪切过来
   - 新建 `css/cinema-config-modals.css`，把 `.provider-preview-modal*` / `.tmdb-preview-modal*` / `.ai-demo-modal*` / 非通用 `.modal-*` 区块整体剪切过来
   - 新建 `css/cinema-config-help.css`，把 `.help-accordion*` / `.info-intro*` / `.info-rows*` / `.info-callout*` 区块整体剪切过来
   - 新建 `css/cinema-enhancements.css`，把 `.is-condensed` / `.glow` / `.animate-pulse` / `.is-enabled` / `.is-disabled` / `.status-configured` / `.is-disabled-status` / `.scrape-mode-hint*` 等通用状态样式剪切过来

3. **原文件 `cinema-pages.css` 保留**：
   - 顶部加注释：`/* cinema-pages.css — 页面样式入口，实现分布在 cinema-dashboard.css / cinema-task-*.css / cinema-recycle.css / cinema-config-*.css / cinema-enhancements.css */`
   - 保留未归入任何特定类别的选择器（若剩余 <300 行则 OK；若仍 >500 行则继续分类）

4. **更新 `index.html` 中的 `<link>` 顺序**：

```html
<!-- 基础样式（保持不变） -->
<link rel="stylesheet" href="css/style.css?v=1">
<link rel="stylesheet" href="css/modals.css?v=1">
<link rel="stylesheet" href="css/toast.css?v=1">

<!-- 页面模块样式（按页面/功能加载） -->
<link rel="stylesheet" href="css/cinema-enhancements.css?v=1">
<link rel="stylesheet" href="css/cinema-dashboard.css?v=1">
<link rel="stylesheet" href="css/cinema-task-list.css?v=1">
<link rel="stylesheet" href="css/cinema-task-detail.css?v=1">
<link rel="stylesheet" href="css/cinema-recycle.css?v=1">
<link rel="stylesheet" href="css/cinema-config-stage.css?v=1">
<link rel="stylesheet" href="css/cinema-config-modals.css?v=1">
<link rel="stylesheet" href="css/cinema-config-help.css?v=1">

<!-- 原页面样式入口（瘦身） -->
<link rel="stylesheet" href="css/cinema-pages.css?v=2">

<!-- 其他模块（保持不变） -->
<link rel="stylesheet" href="css/dimensions.css?v=1">
<link rel="stylesheet" href="css/cinema-advanced.css?v=1">
<link rel="stylesheet" href="css/components.css?v=1">
```

5. **检查行数**：

```bash
wc -l media_importer/webui/css/cinema-*.css
```

**验收**：全部 ≤ 500 行。

---

#### Step 3.1.2 其他 CSS 文件检查（`dimensions.css` / `cinema-advanced.css` / `components.css`）

同样做行数检查，若超 500 行做类似拆分：

```bash
wc -l media_importer/webui/css/dimensions.css media_importer/webui/css/cinema-advanced.css media_importer/webui/css/components.css
```

| 文件 | 预估行数 | 是否需要拆 | 策略 |
|------|----------|------------|------|
| `dimensions.css` | ~814 | 是 | 按「维度卡片」「Genre picker」「拖拽样式」拆 2-3 文件 |
| `cinema-advanced.css` | ~705 | 是 | 按「Hermes」「安全配置」「通用高级样式」拆 2-3 文件 |
| `components.css` | ~600 | 是 | 按「按钮」「表单」「卡片」拆分 2-3 文件 |

**若任一字文件超 500 行**：复用 cinema-pages.css 的模式继续拆，不超过 3 层。

---

#### Step 3.1.3 CSS 手工验收

1. 启动服务：`PYTHONPATH="${PWD}" python -m media_importer.media_importer -c config/config.yaml serve -p 9855`
2. 访问 `http://localhost:9855/webui/`
3. 逐项检查：
   - [ ] Dashboard：hero 条显示正常、metrics 卡片布局正常、activity 列表正常
   - [ ] Task 列表：卡片布局正常、筛选按钮正常、批量工具栏正常
   - [ ] Task 详情：弹窗尺寸正常、trace 样式正常、subtitle 表格正常
   - [ ] Recycle：卡片与操作按钮样式正常
   - [ ] Config 视图：各 stage 切换正常、provider 卡片折叠正常、modal 样式正常
   - [ ] Dimensions 视图：卡片展开/折叠正常、Genre picker 样式正常
   - [ ] Advanced 视图：Hermes 表单、安全配置表单样式正常
4. 检查浏览器 DevTools → Elements → Styles：无 `unknown property` 警告

---

### Step 3.2：Phase 3 回归测试

```bash
# 检查 CSS 文件全部存在且无明显语法错误（浏览器手工打开检查）
ls -la media_importer/webui/css/*.css
wc -l media_importer/webui/css/*.css
```

---

## Phase 4：HTML partial 拆分（预计 1-2 小时）

**原则**：`index.html` 的配置相关 DOM 块可以作为独立的 partial HTML 文件，通过 JS 的 `loadHtmlPartial` 动态加载。这样 `index.html` 主体保持精简，partial 文件独立维护。

### Step 4.1：`index.html`（883 行）→ 主文件 + 1-2 partial

**先做结构分析**（确定哪些区块可独立）：

```bash
# 列出主要 section / div 边界
grep -nE '^[[:space:]]*(<section|<div id|<div class="page)' media_importer/webui/index.html | head -30
```

**预期可拆的区块**：

| partial 文件 | 内容 | 预估行数 |
|-------------|------|----------|
| `webui/partials/config-pages.html` | Config stage 的所有 DOM（各 stage panel、provider preview modal、ai demo modal、simulator 输出 slot 等） | ~500 |
| `webui/partials/advanced-pages.html` | Advanced 视图的所有 DOM（Dimensions 列表、Hermes 配置、安全配置、Prompt 编辑等） | ~300 |

**若拆 partial 后 index.html 仍 >500 行**：进一步把「recycle section」「task detail modal」等也拆为 partial。

---

#### Step 4.1.1 实际拆分步骤

1. **创建 `webui/partials/` 目录**（若不存在）

2. **创建 `partials/config-pages.html`**：
   - 从 index.html 中找到 Config 视图的外层容器（如 `<section id="view-config">` 或对应 div）
   - 把整个 Config 区块（含所有 stage panel、provider modal、ai modal）剪切到 `config-pages.html`
   - 在 index.html 原位置替换为占位：`<div id="config-pages-slot" class="config-pages-slot"></div>`

3. **创建 `partials/advanced-pages.html`**：
   - 把 Advanced 视图的整个区块剪切到 `advanced-pages.html`
   - 在 index.html 原位置替换为占位：`<div id="advanced-pages-slot" class="advanced-pages-slot"></div>`

4. **修改 `cinema-app.js` 的 `DOMContentLoaded` 初始化块**：
   - 在 `bindEvents()` 之前，先调用 `loadHtmlPartial('config-pages-slot', 'partials/config-pages.html')`
   - 同样加载 `advanced-pages-slot`
   - **⚠️ 关键**：`loadHtmlPartial` 是异步的（fetch + innerHTML）。后续 `loadInlineProviderConfigs`、`loadDimensions`、`bindEvents` 等必须在 partial 加载完成后再执行。

5. **修改 `loadHtmlPartial` 函数**（若在 `cinema-dashboard.js` 中）：
   - 返回 Promise，在 fetch 完成后 resolve
   - 这样 `DOMContentLoaded` 中可以写：

```javascript
Promise.all([
  loadHtmlPartial('config-pages-slot', 'partials/config-pages.html'),
  loadHtmlPartial('advanced-pages-slot', 'partials/advanced-pages.html'),
]).then(() => {
  loadHtmlPartial('advanced-pages-slot', 'partials/advanced-pages.html');
  bindEvents();
  renderStaticLists();
  initReelWheel();
  // ... 其他初始化
});
```

6. **更新 `index.html` 的 `<script>` 加载顺序不变**（因为 partial 是 JS 动态加载，不影响 script 顺序）

7. **检查行数**：

```bash
wc -l media_importer/webui/index.html media_importer/webui/partials/*.html
```

**验收**：`index.html` ≤ 500 行，每个 partial ≤ 500 行。

---

#### Step 4.1.2 partial 手工验收

1. 启动服务 → 访问首页
2. 检查：
   - [ ] 页面首次加载时 Config 视图与 Advanced 视图内容能正确显示（无空白）
   - [ ] 视图切换（Dashboard → Tasks → Recycle → Config → Advanced）无错误
   - [ ] Config 视图中：stage 切换正常、provider 弹窗 DOM 存在
   - [ ] Advanced 视图中：Dimensions 列表 DOM 存在、Hermes 表单 DOM 存在
3. 检查 DevTools → Network：确认 `partials/config-pages.html` 和 `partials/advanced-pages.html` 被请求且状态 200

---

### Step 4.2：Phase 4 回归测试

同 Phase 3 的手工检查清单 + 额外确认 partial 文件被正确加载。

---

## 完整测试策略（跨 Phase）

### 1. 单元测试（Python）

覆盖 Phase 1 中修改的文件：

```bash
# 每个 Step 后都应运行以下测试
python -m pytest tests/test_match_engine.py -v
python -m pytest tests/test_tier2_match_engine.py -v
python -m pytest tests/test_match_engine_keyword_loop.py -v
python -m pytest tests/test_match_pipeline_integration.py -v
python -m pytest tests/test_scrape_preview_job.py -v
python -m pytest tests/test_scrape_preview_api.py -v
python -m pytest tests/test_config_api_no_legacy_prompts.py -v
python -m pytest tests/test_feature_entrypoints.py -v
python -m pytest tests/test_llm_web_search.py -v
python -m pytest tests/test_ai_config_runtime.py -v
python -m pytest tests/test_prompt_runtime.py -v
python -m pytest tests/test_tier2_correct.py -v
```

**关键断言**：
- `MatchEngine` 实例化成功
- `match()` 方法返回预期结构的结果
- tier1/tier2/tier3 方法的 patch 路径仍然有效（测试中 `patch("...MatchEngine._tier1_exact_match")`）
- `LLMScraper.tier2_correct`、`tier2_judge` 仍然是类方法，可被 patch
- `_run_scrape_preview_job`、`_SCRAPE_PREVIEW_JOBS` 等符号仍可从原文件导入

### 2. 集成测试（Python）

验证跨模块协作：

```bash
python -m pytest tests/test_match_pipeline_integration.py -v
python -m pytest tests/test_feature_entrypoints.py -v
```

**关键断言**：
- provider scraper → match engine → LLMScraper 的调用链完整
- import flow 各阶段可通过 feature entrypoints 触发

### 3. 前端自动化测试（Playwright）

若项目已有 Playwright 测试：

```bash
python -m pytest tests/test_frontend_*.py tests/test_*_ui.py tests/test_scrape_ui.py -v
```

**关键断言**：
- 各视图可加载（无 404 / 白屏）
- 按钮点击触发预期行为（保存配置 → toast、打开任务详情 → 弹窗）
- API 调用返回预期数据

### 4. 回归测试（手工清单）

**Python 端**：

```bash
# 全部非 UI 测试套件
python -m pytest tests/ --ignore=tests/test_*_ui.py --ignore=tests/test_frontend_*.py --ignore=tests/test_scrape_ui.py -v

# 编译检查
python -m compileall -q media_importer
```

**前端端**（手工逐项）：

- [ ] 首页加载 → 控制台无 `ReferenceError` / `TypeError`
- [ ] Dashboard：metrics 显示、activity 列表、reel wheel、queue status
- [ ] Tasks：列表加载、筛选、详情弹窗、批量勾选、批量操作
- [ ] Recycle：列表加载、条目操作
- [ ] Config：保存路径配置、保存 provider、测试 LLM/Hermes、运行模拟器
- [ ] Config：Provider preview 弹窗 → 搜索 → 选中 → 关闭
- [ ] Config：AI prompt 默认值加载、重置
- [ ] Advanced：Dimensions 列表加载、展开/折叠、Genre 拖动、启用/禁用
- [ ] Advanced：Hermes 表单、安全配置表单
- [ ] 视图切换：Dashboard ↔ Tasks ↔ Recycle ↔ Config ↔ Advanced 全循环
- [ ] 滚动/窗口大小变化：sticky hero 行为正常

### 5. 特殊测试点

**patch 路径有效性测试**（Phase 1 重点）：
- `tests/test_match_engine.py` 中 `patch("media_importer.features.scraping.match_engine.MatchEngine._tier1_exact_match")` → 必须仍生效
- `tests/test_scrape_preview_job.py` 中 `patch("...match_engine.MatchEngine._tier2_context_match")` → 必须仍生效
- `tests/test_tier2_match_engine.py` 中 `patch("...llm_scraper.LLMScraper.tier2_correct")` → 必须仍生效

**验证方法**：跑完上述测试后，检查 pytest 输出无 `ModuleNotFoundError` 或 patch 失败相关错误。

**JS 全局函数可达性测试**（Phase 2 重点）：
- 在浏览器控制台输入 `typeof buildSourceConfigPayload` → `function`
- `typeof loadTaskList` → `function`
- `typeof renderDimensions` → `function`
- `typeof loadDashboardOverview` → `function`
- `typeof bindEvents` → `function`
- `typeof _run_scrape_preview_job` → 不适用（这是 Python 的，不在 JS 侧）
- 检查 `window.currentTaskRecords` → `[]` 或实际数据（状态变量已定义）

**CSS 选择器覆盖测试**（Phase 3 重点）：
- DevTools → Elements → 搜索 `cinema-` 开头的类名 → 确认各元素的 Styles 面板中有 CSS 规则匹配
- 确认无元素仅有类名但无匹配样式（这意味着某个 CSS 区块被遗漏了）

---

## 回滚方案（任一 Phase 出问题时）

### 方案 A：git 回滚（推荐，最彻底）

```bash
# 记录当前 HEAD
git log --oneline -1

# 若发现 breakage
git stash        # 保存当前工作
# 或
git reset --hard HEAD  # 丢弃所有未提交改动
```

### 方案 B：逐文件回滚（仅某文件出问题时）

```bash
# 例如：发现 cinema-app.js 拆分后有问题
git checkout HEAD -- media_importer/webui/js/cinema-app.js
git checkout HEAD -- media_importer/webui/js/cinema-app-state.js
# ... 恢复相关文件
```

### 方案 C：CSS/JS 快速回退（前端问题最常用）

```bash
# 恢复 index.html 的 script/link 引用为拆分前版本
git checkout HEAD -- media_importer/webui/index.html

# 删除新创建的子文件（它们不再被引用）
rm media_importer/webui/js/cinema-app-state.js
rm media_importer/webui/js/cinema-dashboard.js
# ... 等等
```

---

## 执行顺序索引（中断后从这里继续）

> 此索引按执行顺序排列。每次中断/恢复后，找到最后完成的 Step，从下一个继续。

### Phase 0：基线（必须最先执行）

| # | 步骤 | 检查点 |
|---|------|--------|
| 0.1 | 运行基线测试（完整非 UI 测试套件） | 记录 pass/fail 总数 |
| 0.2 | 运行 compileall | 无 SyntaxError |
| 0.3 | 记录当前超标文件行数快照 | 保存下表实际值 |

### Phase 1：Python 拆分

| # | 步骤 | 检查点 | 关键风险 |
|---|------|--------|----------|
| 1.1 | 拆分 `tmdb_handlers.py` → `scrape_preview_job.py` + 原文件 | `wc -l` 均 ≤ 500；`from media_importer.api.tmdb_handlers import _run_scrape_preview_job` 仍可导入 | test_scrape_preview_job |
| 1.2 | 拆分 `llm_scraper.py` → `_llm_client_impl.py` + `_llm_match_assist.py` + 原文件 | `LLMScraper.tier2_correct` 仍是方法；patch 路径不变 | test_match_engine, test_tier2_match_engine |
| 1.3 | 拆分 `match_engine.py` → `_match_tiers_impl.py` + 原文件 | `MatchEngine._tier1_exact_match` 仍是方法；patch 路径不变 | test_scrape_preview_job, test_match_engine |
| 1.4 | Phase 1 回归测试 | 全部非 UI 测试通过；compileall 通过 | 如有失败 → 回滚对应 Step 重做 |

### Phase 2：JS 拆分

| # | 步骤 | 检查点 | 关键风险 |
|---|------|--------|----------|
| 2.1 | 拆分 `cinema-config.js` → 7 个子文件 + 入口 | 每个 `wc -l` ≤ 500；`index.html` 脚本顺序更新 | JS 函数命名冲突；跨文件循环依赖 |
| 2.2 | 拆分 `cinema-tasks.js` → 4 个子文件 + 入口 | 每个 `wc -l` ≤ 500 | task detail 若超 500 → 继续拆 trace 子文件 |
| 2.3 | 拆分 `dimensions.js` → 3 个子文件 + 入口 | 每个 `wc -l` ≤ 500；`_dimensionsData` 等状态变量仍在 dimensions.js | genre 操作函数与状态不在同一文件但通过全局作用域连接 |
| 2.4 | 拆分 `cinema-app.js` → 4 个子文件 + 入口 | 每个 `wc -l` ≤ 500；`cinema-app-state.js` 最先加载 | state 变量在子文件被读写前必须已定义 |
| 2.5 | Phase 2 回归测试（手工清单 + Playwright） | 控制台无 ReferenceError；各视图功能正常 | 如有函数缺失错误 → grep 函数名查找遗漏文件 |

### Phase 3：CSS 拆分

| # | 步骤 | 检查点 | 关键风险 |
|---|------|--------|----------|
| 3.1 | 拆分 `cinema-pages.css` → 8 个页面/功能文件 + 入口 | 每个 `wc -l` ≤ 500；`index.html` link 顺序更新 | 选择器在拆分后无元素匹配（样式丢失） |
| 3.2 | 检查 `dimensions.css` / `cinema-advanced.css` / `components.css` | 若 >500 → 按相同模式继续拆 | 同上 |
| 3.3 | Phase 3 手工回归测试 | 各页面样式正常；DevTools 无样式警告 |

### Phase 4：HTML partial

| # | 步骤 | 检查点 | 关键风险 |
|---|------|--------|----------|
| 4.1 | 拆分 `index.html` → `partials/config-pages.html` + `partials/advanced-pages.html` | index.html ≤ 500 行；partial ≤ 500 行 | loadHtmlPartial 异步顺序；bindEvents 必须在 partial 后 |
| 4.2 | Phase 4 回归测试 | partial 文件被请求且内容正确渲染 | 如有白屏 → 检查 fetch 路径和 Promise 顺序 |

### Phase 5：最终验收

| # | 步骤 | 检查点 |
|---|------|--------|
| 5.1 | 统计所有源文件行数 | 全部 ≤ 500 行 |
| 5.2 | 完整测试套件 | 全部通过 |
| 5.3 | compileall + node --check | 无语法错误 |
| 5.4 | 手工走一遍完整用户流程 | 无视觉/功能回归 |

---

## 风险与缓解表

| 风险 | 影响 | 概率 | 缓解 |
|------|------|------|------|
| Python patch 路径在拆分后失效 | 测试全失败 | 中 | 保留原方法作为 thin wrapper，实现体在新文件；方法签名不变 |
| JS 全局函数挪文件后未被加载 | 页面功能 broken，ReferenceError | 高 | `index.html` 脚本顺序严格按依赖排序；拆分后在浏览器控制台 `typeof` 检查关键函数 |
| JS 状态变量读写顺序错误 | 变量 undefined，功能 broken | 中 | `cinema-app-state.js` 必须最先加载；所有子文件读取状态时已定义 |
| CSS 选择器拆分时遗漏区块 | 页面部分元素无样式 | 中 | 先做选择器清单再分类剪切；每次拆分后 DevTools 检查匹配 |
| HTML partial 异步加载顺序错误 | DOM 元素未就绪时 bindEvents 绑定失败 | 中 | `loadHtmlPartial` 返回 Promise；`bindEvents` 在 `Promise.all().then()` 中调用 |
| 某次拆分后原文件仍超 500 行 | 不满足规范 | 低 | 继续递归拆分；拆分前先估算行数，规划过度而非不足 |
