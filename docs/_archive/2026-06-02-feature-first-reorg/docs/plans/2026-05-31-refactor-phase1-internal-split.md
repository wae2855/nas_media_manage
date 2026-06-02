---
title: "refactor: Feature First 架构重构 — Phase 1 内部拆分"
type: plan
date: 2026-05-31
status: pending
brainstorm: docs/方案/代码解耦重构.md
confidence: high
---

# Feature First 架构重构 — Phase 1 内部拆分

> **一句话**：在不改变目录结构的前提下，将超 500 行的文件按职责拆分为多个子文件，同步拆分文档和更新测试，为后续 Feature First 重组打基础。

---

## Problem Statement

当前项目已按技术层完成子包拆分（api/core/scraper/storage/pipeline/notify/monitor），但存在三个核心问题：

1. **文件过大**：8 个 Python 文件超过 500 行（最大 1070 行），3 个 JS 文件超过 500 行，6 个 CSS 文件超过 500 行
2. **职责混杂**：同一文件包含多个不相关职责（如 safety.py 混合路径校验+回收站管理，config_handlers.py 混合配置+TMDB+监控+健康检查）
3. **AI 导航困难**：AI 修改"回收站逻辑"时需要阅读 637 行的 safety.py，其中 70% 是回收站代码，30% 才是路径校验

## Target End State

Phase 1 完成后：

- 所有 Python 文件 ≤ 500 行
- 每个文件职责单一，文件名即职责
- 回收站逻辑从 safety.py 独立为 recycle/ 子包
- config_handlers.py 按业务拆为 3 个 handler 文件
- confidence_engine.py 按类拆为 4 个文件
- steps.py 按步骤类型拆为 2 个文件
- llm_scraper.py 按职责拆为 2 个文件
- 文档同步拆分，与代码结构一致
- 所有测试通过，功能无回归

## Scope and Non-Goals

### In Scope

- 8 个超限 Python 文件的内部拆分
- core/safety.py → safety.py + core/recycle/ 子包
- api/config_handlers.py → 3 个 handler 文件
- scraper/confidence_engine.py → 4 个文件
- pipeline/steps.py → 2 个步骤文件
- scraper/llm_scraper.py → 2 个文件
- core/db/dimension_repo.py → repo + migrations
- core/config_loader.py → loader + migrations
- 文档拆分（架构/文件操作.md → 文件操作.md + 回收站.md）
- 测试 import 路径更新
- __init__.py 导出兼容

### Non-Goals

- 不改变子包目录结构（pipeline/ 仍叫 pipeline/，不改为 features/import_flow/）
- 不改变 API 端点路径
- 不改变数据库 schema
- 不改变前端 JS/CSS 拆分（留到 Phase 2）
- 不做 Feature First 目录重组（留到 Phase 3）
- 不重构 Mixin 组合模式

---

## Proposed Solution

### 总体策略

**"内拆外不动"**：只在子包内部拆分文件，不改变子包间的目录关系。通过 `__init__.py` 保持外部 import 路径不变，确保零破坏。

### 拆分原则

1. **每个文件 ≤ 500 行**
2. **文件名即职责**：看到文件名就知道里面是什么
3. **__init__.py 重导出**：拆分后外部 import 路径不变
4. **先拆后测**：每拆一个文件，立即运行相关测试
5. **文档同步**：代码拆分后，对应文档章节同步拆分

---

## Implementation Tasks

### Task Group A: safety.py 拆分（637行 → 3个文件）

> **风险**：中。safety.py 被 6+ 个模块引用，但通过 __init__.py 重导出可保持兼容。

- [ ] A1: 创建 `core/recycle/` 子包目录及 `__init__.py`
- [ ] A2: 从 safety.py 抽出回收站核心操作到 `core/recycle/manager.py`
  - 移动函数：`_recycle_subpath` (L142-160), `_determine_source_zone` (L163-172), `move_dir_to_recycle` (L175-248), `move_to_recycle` (L251-316), `move_to_recycle_with_companions` (L319-363)
  - 预计 ~250 行
- [ ] A3: 从 safety.py 抽出回收站管理到 `core/recycle/browser.py`
  - 移动函数：`recycle_cleanup` (L366-423), `list_recycle_dir` (L426-530), `restore_from_recycle` (L533-604), `delete_from_recycle` (L607-637)
  - 预计 ~280 行
- [ ] A4: 移动 `make_fingerprint` 到 `storage/file_analyzer.py`（它属于文件分析职责）
  - 从 safety.py L133-139 移出
  - 在 file_analyzer.py 中追加
- [ ] A5: 精简 safety.py，仅保留路径校验和安全操作
  - 保留函数：`validate_path_safety` (L9-18), `validate_file_ext` (L21-27), `safe_delete` (L30-58), `safe_move` (L61-92), `check_write_permission` (L95-113), `check_read_permission` (L116-130)
  - 预计 ~130 行
- [ ] A6: 在 `core/recycle/__init__.py` 中重导出所有公共函数
  - `from .manager import move_to_recycle, move_to_recycle_with_companions, move_dir_to_recycle`
  - `from .browser import list_recycle_dir, restore_from_recycle, delete_from_recycle, recycle_cleanup`
- [ ] A7: 在 `core/__init__.py` 中添加 recycle 子包的重导出
  - 保持 `from media_importer.core.safety import move_to_recycle` 仍然可用（通过在 safety.py 中 `from .recycle import *`）
- [ ] A8: 更新所有引用回收站函数的 import 路径
  - `pipeline/steps.py`: `from media_importer.core.safety import move_to_recycle` → `from media_importer.core.recycle import move_to_recycle`（或保持原路径通过重导出兼容）
  - `api/recycle_handlers.py`: 更新 import
  - `api/task_handlers.py`: 更新 import
  - `api/source_cleaner_handlers.py`: 更新 import
  - `storage/source_cleaner.py`: 更新 import
  - `monitor/file_watcher.py`: 更新 `recycle_cleanup` import
- [ ] A9: 运行测试验证
  - `pytest tests/test_recycle_and_safety.py -v`
  - `pytest tests/test_integration_recycle.py -v`
  - `pytest tests/test_deep_e2e.py -v`

**A 组验收标准**：
- safety.py ≤ 150 行
- core/recycle/manager.py ≤ 280 行
- core/recycle/browser.py ≤ 300 行
- `from media_importer.core.safety import move_to_recycle` 仍可用（向后兼容）
- `from media_importer.core.recycle import move_to_recycle` 也可用（新路径）
- 所有回收站相关测试通过

---

### Task Group B: config_handlers.py 拆分（1070行 → 3个文件）

> **风险**：低。仅在 api/ 子包内部重组，不影响外部。

- [ ] B1: 创建 `api/connectivity_handlers.py`
  - 移动方法：`_config_test_llm`, `_config_test_hermes`, `_config_test_tmdb`, `_health`, `_metrics`, `_logs`
  - 定义 `ConnectivityHandlersMixin` 类
  - 预计 ~200 行
- [ ] B2: 创建 `api/tmdb_handlers.py`
  - 移动方法：`_tmdb_genres_list`, `_tmdb_preview`, `_tmdb_search`, `_tmdb_details`, `_scrape_preview`
  - 定义 `TMDbHandlersMixin` 类
  - 预计 ~300 行
- [ ] B3: 精简 config_handlers.py，仅保留配置读写+监控控制+权限检查
  - 保留方法：`_config`, `_config_save`, `_config_save_section`, `_config_reload`, `_config_validate`, `_config_check_permission`, `_path_test`, `_watcher_status`, `_watcher_control`, `_list_tasks`
  - 保留内部工具方法：`_is_masked_value`, `_get_nested_value`, `_delete_nested_path`, `_filter_sensitive_fields`, `_get_real_config_value`, `_update_config_safely`, `_merge_provider_sensitive_fields`, `_reload_watcher`
  - 预计 ~450 行
- [ ] B4: 更新 handler.py 的 Mixin 继承
  - `APIHandler` 新增继承 `ConnectivityHandlersMixin`, `TMDbHandlersMixin`
  - 更新 import 语句
- [ ] B5: 更新 handler.py 的路由映射
  - 确认所有路由仍指向正确的方法名（方法名不变，只是移到了新的 Mixin）
- [ ] B6: 运行测试验证
  - `pytest tests/test_config_page_full.py -v`
  - `pytest tests/test_config_save_load_e2e.py -v`
  - `pytest tests/test_config_consumers.py -v`
  - `pytest tests/test_tmdb_config.py -v`

**B 组验收标准**：
- config_handlers.py ≤ 500 行
- connectivity_handlers.py ≤ 250 行
- tmdb_handlers.py ≤ 350 行
- 所有配置页 API 测试通过
- API 端点路径不变

---

### Task Group C: confidence_engine.py 拆分（860行 → 5个文件）

> **风险**：低。confidence_engine.py 内部类之间依赖清晰，拆分后通过 import 重组。

- [ ] C1: 创建 `scraper/filename_cleaner.py`
  - 移动类：`FilenameCleaner` (L98-230)
  - 移动依赖：正则表达式模式（如果定义在文件顶部）
  - 预计 ~135 行
- [ ] C2: 创建 `scraper/title_matcher.py`
  - 移动类：`TitleMatcher` (L242-409)
  - 移动依赖：`_normalize_title` (L232-235), `_similarity` (L236-239)
  - 预计 ~180 行
- [ ] C3: 创建 `scraper/trace_builder.py`
  - 移动类：`ScrapeTraceBuilder` (L412-480)
  - 预计 ~70 行
- [ ] C4: 创建 `scraper/confidence_models.py`
  - 移动数据类：`CleanResult` (L36-46), `MatchResult` (L48-55), `ConfidenceResult` (L57-95)
  - 移动配置：`DEFAULT_CONFIDENCE_CONFIG` (L9-32)
  - 移动工具函数：`_calc_R` (L483-497), `_aggregate` (L500-517)
  - 预计 ~120 行
- [ ] C5: 精简 confidence_engine.py，仅保留 ConfidenceEngine 类
  - 保留类：`ConfidenceEngine` (L520-860)
  - 更新 import：从新文件导入 `FilenameCleaner`, `TitleMatcher`, `ScrapeTraceBuilder`, 数据类和工具函数
  - 预计 ~340 行
- [ ] C6: 更新 `scraper/__init__.py` 重导出
  - 保持 `from media_importer.scraper.confidence_engine import ConfidenceEngine, FilenameCleaner, TitleMatcher` 仍可用
  - 通过在 confidence_engine.py 中 `from .filename_cleaner import FilenameCleaner` 等实现
- [ ] C7: 运行测试验证
  - `pytest tests/test_confidence_engine.py -v`
  - `pytest tests/test_consult_prompt.py -v`
  - `pytest tests/test_confidence_config_ui.py -v`
  - `pytest tests/test_confidence_ui.py -v`
  - `pytest tests/test_confidence_v2_ui.py -v`

**C 组验收标准**：
- confidence_engine.py ≤ 350 行
- filename_cleaner.py ≤ 150 行
- title_matcher.py ≤ 200 行
- trace_builder.py ≤ 80 行
- confidence_models.py ≤ 130 行
- `from media_importer.scraper.confidence_engine import ConfidenceEngine` 仍可用
- 所有置信度相关测试通过

---

### Task Group D: steps.py 拆分（637行 → 2个文件）

> **风险**：中。steps.py 是流水线核心，但拆分后通过 Mixin 组合保持一致。

- [ ] D1: 创建 `pipeline/steps_scrape.py`
  - 移动方法：`_step_scrape` (L55-158), `_step_validate` (L160-254)
  - 定义 `ScrapeStepsMixin` 类
  - 预计 ~200 行
  - import 依赖：`from media_importer.scraper.llm_scraper import LLMScrapeError`, `from media_importer.scraper.dimension_manager import get_dimensions_for_file`, `from media_importer.storage.file_analyzer import analyze_file`
- [ ] D2: 精简 steps.py 为 `pipeline/steps_file.py`（重命名）
  - 保留方法：`_step_copy` (L17-53), `_step_classify` (L256-299), `_step_dedup` (L379-450), `_step_rename` (L452-467), `_step_import` (L486-552), `_step_import_from_confirm` (L554-630), `_step_notify` (L632-637), `_step_record` (L635-637)
  - 定义 `FileStepsMixin` 类
  - 预计 ~400 行
  - **注意**：不重命名文件，保持 steps.py 文件名但内容改为组合入口
- [ ] D3: 重构 steps.py 为组合入口
  - `steps.py` 内容改为：
    ```python
    from .steps_scrape import ScrapeStepsMixin
    from .steps_file import FileStepsMixin

    class StepsMixin(ScrapeStepsMixin, FileStepsMixin):
        pass
    ```
  - 预计 ~10 行
- [ ] D4: 更新 runner.py 的 import
  - `from .steps import StepsMixin` 保持不变（因为 steps.py 仍导出 StepsMixin）
- [ ] D5: 运行测试验证
  - `pytest tests/test_full_flow.py -v`
  - `pytest tests/test_deep_e2e.py -v`
  - `pytest tests/test_e2e_file_processing.py -v`
  - `pytest tests/test_task_operations.py -v`

**D 组验收标准**：
- steps.py ≤ 20 行（纯组合入口）
- steps_scrape.py ≤ 250 行
- steps_file.py ≤ 450 行
- `from media_importer.pipeline.steps import StepsMixin` 仍可用
- 所有流水线相关测试通过

---

### Task Group E: llm_scraper.py 拆分（678行 → 2个文件）

> **风险**：低。提示词构建和 API 调用是两个清晰的职责边界。

- [ ] E1: 创建 `scraper/llm_prompts.py`
  - 移动方法：`_build_system_prompt` (L233-264), `_build_system_prompt_with_provider` (L266-314), `_build_system_prompt_with_context` (L317-318), `_build_series_prompt` (L568-612), `_build_series_prompt_with_provider` (L614-674)
  - 移动依赖：`_build_json_schema` 方法（如果存在），provider_prompts 相关常量
  - 定义 `LLMPromptBuilder` 类或独立函数
  - 预计 ~300 行
- [ ] E2: 精简 llm_scraper.py
  - 保留：`LLMScrapeError` (L11-13), `LLMScraper` 类骨架 + API 调用方法
  - 保留方法：`__init__`, `scrape`, `scrape_with_context`, `scrape_series`, `scrape_series_with_context`, `extract_title`, `_call_api`, `_call_fast_api`, `_do_call`, `_retry_with_fallback`, `_parse_response`
  - 更新：提示词构建改为调用 `llm_prompts.py` 中的函数
  - 预计 ~380 行
- [ ] E3: 更新 `scraper/__init__.py` 确保导出不变
- [ ] E4: 运行测试验证
  - `pytest tests/test_consult_prompt.py -v`
  - `pytest tests/test_scrape_results.py -v`
  - `pytest tests/test_scrape_ui.py -v`

**E 组验收标准**：
- llm_scraper.py ≤ 400 行
- llm_prompts.py ≤ 320 行
- `from media_importer.scraper.llm_scraper import LLMScraper` 仍可用
- 所有刮削相关测试通过

---

### Task Group F: 迁移逻辑抽出（dimension_repo + config_loader）

> **风险**：低。迁移逻辑仅在初始化时调用，抽出后不影响运行时。

- [ ] F1: 从 `core/db/dimension_repo.py` 抽出迁移逻辑到 `core/db/migrations.py`
  - 移动函数：`_seed_dimensions` (L8-26), `_migrate_dimensions` (L28-36), `_migrate_region` (L37-67), `_migrate_broad_genre` (L68-117), `_cleanup_invalid_genre_ids` (L118-165), `_migrate_restricted_level` (L118-165), `_migrate_source_type` (L165-180), `_migrate_tmdb_field` (L181-219), `_migrate_provider_mappings` (L220-324), `_build_provider_mappings` (L246-324)
  - 预计 ~280 行
- [ ] F2: 精简 dimension_repo.py，仅保留 CRUD
  - 保留函数：`get_all_dimensions`, `get_enabled_dimensions`, `get_dimension`, `update_dimension`, `enable_dimension`, `disable_dimension`, `reset_dimension`
  - 预计 ~150 行
- [ ] F3: 从 `core/config_loader.py` 抽出迁移逻辑到 `core/config_migrations.py`
  - 移动函数：`_migrate_confidence_v1_to_v2` (L253-309), `_migrate_source_policy` (L310-346), `_normalize_bool_strings` (L347-362), `_normalize_bool_strings_in_list` (L363-369)
  - 预计 ~120 行
- [ ] F4: 精简 config_loader.py
  - 保留函数：`copy_config_template`, `validate_config`, `mask_sensitive`, `validate_dimension_values`, `_value_in_list`, `load_config`
  - 预计 ~250 行
- [ ] F5: 更新 `core/db/__init__.py` 和 `core/__init__.py` 的重导出
- [ ] F6: 运行测试验证
  - `pytest tests/test_sqlite_refactor.py -v`
  - `pytest tests/test_config_consumers.py -v`

**F 组验收标准**：
- dimension_repo.py ≤ 180 行
- db/migrations.py ≤ 300 行
- config_loader.py ≤ 280 行
- config_migrations.py ≤ 130 行
- 数据库初始化和配置加载功能正常

---

### Task Group G: 文档拆分

> **风险**：极低。纯文档变更，不影响代码。

- [ ] G1: 拆分 `docs/架构/文件操作.md`（760行）
  - 抽出回收站相关章节 → `docs/架构/回收站管理.md`
  - 抽出源目录清理器章节 → 已有独立文档，确认一致性
  - 精简文件操作.md，仅保留扫描/复制/搬运/分析/去重/分类
  - 预计：文件操作.md ~400行，回收站管理.md ~300行
- [ ] G2: 拆分 `docs/架构/刮削引擎.md`（720行）
  - 抽出置信度引擎章节 → `docs/架构/置信度引擎.md`（如与现有 confidence-engine.md 合并）
  - 抽出文件名清洗/标题匹配章节 → 合并到置信度引擎文档
  - 精简刮削引擎.md，仅保留 Provider/元数据刮削/维度映射
  - 预计：刮削引擎.md ~400行，置信度引擎.md ~300行
- [ ] G3: 拆分 `docs/架构/配置系统.md`（749行）
  - 抽出配置迁移章节 → `docs/架构/配置迁移.md`
  - 精简配置系统.md
  - 预计：配置系统.md ~500行，配置迁移.md ~200行
- [ ] G4: 更新 `docs/系统架构总览.md`
  - 更新目录结构图（新增 recycle/ 子包、新文件名）
  - 更新模块依赖关系图
  - 更新跨模块交互矩阵
  - 更新功能模块文档链接
- [ ] G5: 更新 `AGENTS.md`
  - 更新目录结构说明
  - 更新关键架构决策表
  - 更新安全规则中的文件路径引用

**G 组验收标准**：
- 每个架构文档 ≤ 500 行
- 新文档与代码结构一致
- 系统架构总览中的目录结构图与实际代码一致
- AGENTS.md 中的路径引用正确

---

### Task Group H: 测试全面验证

> **风险**：无。纯验证，不修改代码。

- [ ] H1: 更新测试文件中的 import 路径
  - `test_recycle_and_safety.py`: 更新 `from media_importer.core.safety import ...` → 同时测试新旧路径
  - `test_deep_e2e.py`: 更新 safety 相关 import
  - `test_confidence_engine.py`: 确认 `from media_importer.scraper.confidence_engine import ...` 仍可用
  - `test_consult_prompt.py`: 同上
  - `test_full_flow.py`: 确认 pipeline import 正常
  - `test_sqlite_refactor.py`: 确认 db import 正常
  - `test_config_consumers.py`: 确认 config import 正常
- [ ] H2: 运行全部非 UI 单元测试
  - `pytest tests/ --ignore=tests/test_*_ui.py --ignore=tests/test_frontend_*.py --ignore=tests/test_scrape_ui.py -v`
- [ ] H3: 运行全部测试（需要服务运行）
  - `pytest tests/ -v`
- [ ] H4: 验证 import 兼容性
  - 编写脚本验证所有旧 import 路径仍可用
  - 验证所有新 import 路径也可用
- [ ] H5: 同步 deploy/ 目录
  - 将变更同步到 `deploy/nas-media-importer/app/server/media_importer/`

**H 组验收标准**：
- 所有测试通过（已知失败测试除外）
- 旧 import 路径全部兼容
- 新 import 路径全部可用
- deploy/ 目录与源码一致

---

## Decision Rationale

### 为什么 Phase 1 只做内部拆分，不做 Feature First 重组？

1. **风险控制**：内部拆分不改变子包间关系，影响面最小
2. **渐进式**：先让每个文件职责单一，再移动到 feature 目录，每步可验证
3. **兼容性**：通过 __init__.py 重导出，旧代码零修改
4. **AI 友好**：拆分后文件名即职责，AI 已可精准定位

### 为什么 safety.py 的回收站逻辑抽到 core/recycle/ 而不是 features/recycle/？

1. Phase 1 不创建 features/ 目录，保持现有结构
2. 回收站被 core/safety、pipeline、api、storage、monitor 多处引用，放在 core/ 层最合理
3. 后续 Phase 3 做 Feature First 重组时，再决定是否移到 features/recycle/

### 为什么 config_handlers.py 拆为 3 个而不是更多？

1. 配置读写（config_handlers）和提示词管理（prompt_handlers）已有独立文件
2. 连通性测试（LLM/Hermes/TMDB/健康检查）是独立职责，值得独立
3. TMDB 操作（genres/preview/search/details/scrape_preview）是独立职责，值得独立
4. 拆为 3 个后每个 ≤ 350 行，满足 500 行限制

### 为什么 steps.py 用 Mixin 组合而不是直接拆为两个独立文件？

1. runner.py 通过 `class PipelineRunner(StepsMixin, ConfirmMixin)` 组合
2. 拆为 ScrapeStepsMixin + FileStepsMixin 后，steps.py 作为组合入口保持 StepsMixin 导出
3. 外部 import 路径不变：`from media_importer.pipeline.steps import StepsMixin`

---

## Constraints and Boundaries

1. **不改变 API 端点路径**：前端已依赖现有路径
2. **不改变数据库 schema**：稳定运行中
3. **不改变子包间目录关系**：Phase 1 只做子包内部拆分
4. **保持旧 import 路径兼容**：通过 __init__.py 重导出
5. **每个文件 ≤ 500 行**：硬性约束
6. **deploy/ 目录必须同步**：手动同步，不自动执行

---

## Assumptions

| Assumption | Status | Evidence |
|------------|--------|----------|
| __init__.py 重导出可保持旧 import 兼容 | Verified | Python 包机制标准行为，项目已有先例（core/db/__init__.py） |
| Mixin 组合模式可继续用于拆分后的 steps | Verified | 项目已有 StepsMixin + ConfirmMixin 组合先例 |
| 测试文件中 import 路径可通过重导出保持兼容 | Verified | test_confidence_engine.py 通过 `from media_importer.scraper.confidence_engine import ...` 导入，重导出后仍可用 |
| deploy/ 目录可手动同步 | Verified | AGENTS.md 已说明 deploy 是手动同步 |
| 回收站函数的调用者都通过 core.safety 或 core.db 导入 | Verified | grep 分析确认所有调用者路径 |

---

## Risk Analysis

| Risk | Probability | Impact | Mitigation |
|------|------------|--------|------------|
| 拆分后 import 循环依赖 | Low | High | 先画依赖图再拆；recycle/ 不依赖 safety.py，safety.py 可选依赖 recycle/ |
| __init__.py 重导出遗漏 | Medium | Medium | 拆分后立即运行测试验证 |
| Mixin 方法名冲突 | Low | High | 新 Mixin 方法名保持原有前缀（_step_, _config_ 等），不会冲突 |
| 测试文件 import 路径不一致 | Medium | Low | H4 任务专门验证兼容性 |
| deploy/ 同步遗漏 | Medium | Medium | H5 任务专门同步 |
| 回收站函数移动后 safety.py 中仍有引用 | Low | Medium | safety.py 通过 `from .recycle import *` 重导出，保持兼容 |

---

## Phased Implementation

### Phase 1A: safety.py 拆分（Task Group A）
- **Exit Criteria**: safety.py ≤ 150 行，recycle/ 子包可用，回收站测试全部通过
- **Estimated Effort**: 2-3 小时

### Phase 1B: config_handlers.py 拆分（Task Group B）
- **Exit Criteria**: config_handlers.py ≤ 500 行，配置 API 测试全部通过
- **Estimated Effort**: 1-2 小时
- **Depends On**: None（可与 1A 并行）

### Phase 1C: confidence_engine.py 拆分（Task Group C）
- **Exit Criteria**: confidence_engine.py ≤ 350 行，置信度测试全部通过
- **Estimated Effort**: 1-2 小时
- **Depends On**: None（可与 1A/1B 并行）

### Phase 1D: steps.py + llm_scraper.py 拆分（Task Group D + E）
- **Exit Criteria**: steps.py ≤ 20 行，llm_scraper.py ≤ 400 行，流水线测试全部通过
- **Estimated Effort**: 2-3 小时
- **Depends On**: 1A（steps.py 引用 safety.py 的函数）

### Phase 1E: 迁移逻辑抽出（Task Group F）
- **Exit Criteria**: dimension_repo.py ≤ 180 行，config_loader.py ≤ 280 行
- **Estimated Effort**: 1 小时
- **Depends On**: None（可与其他并行）

### Phase 1F: 文档拆分（Task Group G）
- **Exit Criteria**: 每个架构文档 ≤ 500 行
- **Estimated Effort**: 1-2 小时
- **Depends On**: 1A-1E 全部完成（文档需反映最终代码结构）

### Phase 1G: 全面验证（Task Group H）
- **Exit Criteria**: 所有测试通过，deploy 同步完成
- **Estimated Effort**: 1 小时
- **Depends On**: 1A-1F 全部完成

---

## References

- [代码解耦重构方案](../docs/方案/代码解耦重构.md) — 上一次重构的决策记录
- [系统架构总览](../docs/系统架构总览.md) — 当前架构文档
- [文件操作架构](../docs/架构/文件操作.md) — safety.py 相关文档
- [刮削引擎架构](../docs/架构/刮削引擎.md) — confidence_engine.py 相关文档
- [配置系统架构](../docs/架构/配置系统.md) — config_handlers.py 相关文档
- [流水线处理架构](../docs/架构/流水线处理.md) — steps.py 相关文档
