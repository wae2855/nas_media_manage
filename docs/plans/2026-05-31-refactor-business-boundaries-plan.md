---
title: "refactor: 业务边界显式化重构"
type: plan
date: 2026-05-31
status: in_progress
brainstorm: docs/方案/任务状态模型与文件流转重构.md
confidence: medium
---

# 业务边界显式化重构

> 一句话：在不改变现有功能和 API 行为的前提下，把任务上下文、状态流转、配置访问和 pipeline 业务服务边界显式化，让 AI 和人都能用更少搜索成本理解、扩展和验证系统。

## Problem Statement

当前项目已经完成了从平铺模块到 `api/core/scraper/storage/pipeline` 等子包的拆分，也已经有 Provider 抽象、DB repo 拆分、pipeline step 拆分等基础成果。但按“AI 最小成本理解、按业务解耦、扩展最小成本”衡量，仍有四个结构性问题：

1. `PipelineRunner.process_one()` 是事实上的业务内核，任务状态、文件位置、人工确认、失败/跳过等规则都通过可变 `dict` 和字符串字段隐式传递。
2. `pipeline/steps_file.py` 同时处理分类、路径解析、去重、回收站、源文件清理、DB 写入，业务策略和基础设施调用混在一起。
3. 配置仍是全局 `dict` 合约，`config.get(...)` 散落在 API、pipeline、scraper、storage、monitor 中，新增配置项会产生较大扇出。
4. API 已拆 Mixin，但路由仍在 `api/handler.py` 的长 `if/elif` 中，新增端点的搜索和回归成本偏高。

这些问题不会立刻阻塞功能，但会让后续新增状态、清理策略、导入策略、Provider 能力、确认流程时越来越容易牵动核心流程。

## Target End State

完成后应满足：

- 任务处理主流程能通过 3-5 个业务概念读懂：`TaskContext`、`TaskLifecycle`、`ScrapeService`、`ImportService`、`ReviewDecision`。
- 状态和 `file_location` 的合法流转集中在一个地方表达，而不是散落在 runner、confirm、task_handlers、DB migration 中。
- pipeline runner 只负责任务编排、错误边界和通知钩子，不直接承载去重、清理、路径策略细节。
- 主要业务配置通过 typed facade 读取，低层模块不再到处依赖裸配置 key。
- API 路由逐步表驱动化，新增端点只需要注册 route + handler，不需要改长分支。
- 外部行为保持兼容：API 路径、DB schema、配置文件格式、前端交互不因本次重构改变。

## Scope and Non-Goals

### In Scope

- 新增任务处理上下文对象，先作为 `dict` 的薄包装，再逐步承接 pipeline 内部字段访问。
- 新增任务生命周期/状态转换模块，集中管理状态、确认子状态、文件位置更新规则。
- 抽出 pipeline 业务服务边界：分类、去重、入库、源文件清理、确认决策。
- 新增配置 facade，优先覆盖 pipeline 高扇出配置：路径、源文件策略、去重、文件名模板、人工审核。
- 将 API 路由从长 `if/elif` 逐步迁移为表驱动注册，优先覆盖新增或高频端点。
- 同步更新 `docs/架构/流水线处理.md`、`docs/架构/任务管理.md`、`docs/规范/接口规范.md` 中受影响部分。
- 补充单元测试和低成本集成测试，优先覆盖状态转换、上下文兼容、配置 facade、关键 pipeline 分支。

### Non-Goals

- 不重写整个 pipeline。
- 不引入 FastAPI、Pydantic、SQLAlchemy、Celery 等新框架。
- 不改变现有 API 路径和响应格式。
- 不改变 SQLite schema，除非后续阶段明确需要迁移。
- 不改变前端页面结构和交互。
- 不处理 deploy 目录的手动同步。
- 不追求一次性消灭所有 `dict` 和所有 `config.get(...)`。

## Proposed Solution

采用“包一层、收一处、再替换”的低风险路径：

1. **包一层**：先引入 `TaskContext`，兼容现有 `dict`，允许旧代码继续通过 `task.get(...)` 工作。
2. **收一处**：把状态转换、文件位置、确认决策集中到 `TaskLifecycle`，让 runner/confirm/API 调用同一套规则。
3. **再替换**：按业务片段把 step 内的策略抽成服务，runner 逐步从“做细节”变成“调服务”。
4. **控制半径**：每个阶段保持可运行、可回滚、可测试，不做跨层大迁移。

建议新增模块：

```text
media_importer/
├── core/
│   ├── config_view.py          # typed config facade
│   └── task_lifecycle.py       # 状态、文件位置、转换规则
└── pipeline/
    ├── context.py              # TaskContext / processing result
    └── services/
        ├── classification.py   # 分类与导入路径解析
        ├── dedup.py            # 去重策略执行
        ├── import_service.py   # 入库移动、字幕落库、临时文件清理
        ├── source_cleanup.py   # 源文件清理与回收站
        └── review.py           # 置信度结果到人工确认/失败/继续的决策
```

## Phased Implementation

### Phase 0: Baseline and Safety Net

目标：确认当前坏测试边界，避免把既有失败误判成重构回归。

- [x] 记录当前 git 状态和相关文件变更范围。
- [x] 阅读 `.pytest_cache/v/cache/lastfailed`，确认已知失败。
- [x] 跑非 UI 单元测试基线：
  - `pytest tests/ --ignore=tests/test_*_ui.py --ignore=tests/test_frontend_*.py --ignore=tests/test_scrape_ui.py`
- [x] 若全量非 UI 测试过大，至少跑：
  - `pytest tests/test_task_operations.py tests/test_full_flow.py tests/test_e2e_file_processing.py tests/test_recycle_and_safety.py`

执行记录：

- `pytest` 命令不存在，改用 `python3 -m pytest`。
- `python3 -m pytest tests/test_task_context_lifecycle.py tests/test_task_operations.py tests/test_sqlite_refactor.py` 中 `tests/test_sqlite_refactor.py` 的 13 个失败与 `.pytest_cache/v/cache/lastfailed` 一致。
- `python3 -m pytest tests/test_task_context_lifecycle.py tests/test_task_operations.py` 通过：54 passed。
- 已知失败清单记录在 `docs/testing/known-failures.md`。

退出标准：记录可接受的基线失败；后续阶段只对新增失败负责。

### Phase 1: TaskContext 薄包装

目标：降低 pipeline 内部任务字段的搜索成本，但不要求一次性替换所有 `dict`。

- [x] 新建 `pipeline/context.py`。
- [x] 定义 `TaskContext`，内部持有原始 `dict`，提供：
  - `task_id`
  - `source_path`
  - `current_video_path`
  - `subtitle_files`
  - `scrape_result`
  - `scrape_dimensions`
  - `file_location`
  - `mark_temp(video_path, subtitles)`
  - `mark_scraped(result)`
  - `to_update_fields(...)`
  - `raw` 兼容入口
- [x] 在 `PipelineRunner.process_one()` 入口创建 context，但保留旧 step 接收 `dict`。
- [x] 先在 runner 的状态判断和清理路径中使用 context，避免大范围改 step。
- [x] 为 context 添加单元测试，验证对现有任务 dict 字段的读写兼容。

退出标准：`PipelineRunner` 能通过 context 表达主路径关键字段；旧 step 不需要大改；现有测试不新增失败。

### Phase 2: TaskLifecycle 状态集中化

目标：把 `status`、`confirm_status`、`file_location`、完成时间、错误字段的组合规则收敛。

- [x] 新建 `core/task_lifecycle.py`。
- [x] 定义状态和文件位置常量，复用现有 DB 合法状态，不改变 schema。
- [x] 定义状态转换函数：
  - `start_processing(ctx)`
  - `mark_temp_ready(ctx)`
  - `mark_confirming(ctx, reason)`
  - `mark_needs_review(ctx, reason)`
  - `mark_failed(ctx, error)`
  - `mark_skipped(ctx, reason)`
  - `mark_imported(ctx, import_path)`
  - `reset_for_retry(task)`
- [x] 在 `runner.py` 替换直接 `db_update_task(... status=..., file_location=...)` 的高风险重复片段。
- [x] 在 `confirm.py` 替换确认、忽略、重分类后的状态更新片段。
- [x] 在 `task_manager.retry_task()` / `retry_all_failed()` 使用 lifecycle 的 retry 字段规则。
- [x] 添加状态转换单元测试，覆盖 PENDING、PROCESSING、CONFIRMING、FAILED、SKIPPED、SUCCESS 与 `file_location` 组合。

退出标准：新增状态或调整文件位置规则时，主要修改点集中在 `task_lifecycle.py` 和测试。

### Phase 3: Pipeline 业务服务抽取

目标：让 runner 和 step mixin 变薄，业务策略以服务形式存在。

- [x] 新建 `pipeline/services/` 子包。
- [x] 抽出 `ClassificationService`：
  - 输入：scrape result、path rules、fallback_dir、config root
  - 输出：import_path、classify_result 或业务错误
  - 替换 `_step_classify()` 内路径策略。
- [x] 抽出 `DedupService`：
  - 输入：import_roots、scrape result、strategy、video_path
  - 输出：skip/rename/replace/quality 决策
  - 回收站移动交给 `SourceCleanupService` 或明确注入。
- [x] 抽出 `ImportService`：
  - 封装 `move_to_import()`、字幕 DB 更新、临时文件清理。
  - `_step_import()` 和 `_step_import_from_confirm()` 复用同一服务。
- [x] 抽出 `SourceCleanupService`：
  - 封装 `cleanup_source_after_done`、回收站目录、伴随文件、空目录清理。
- [x] 抽出 `ReviewDecisionService`：
  - 把 `_step_validate()` 的置信度等级到 `_force_fail/_needs_review/_needs_confirm` 的隐式 flag 改成显式 decision。
- [x] 每抽一个服务先写或迁移对应单元测试，再替换 step 内实现。

执行记录：

- `ClassificationService` 替换 `_step_classify()` 内路径策略。
- `DedupService` 替换 `_step_dedup()` 内同名检测和 skip/rename/replace/quality 决策。
- `ImportService` 统一 `_step_import()` 和 `_step_import_from_confirm()` 的文件移动、临时文件清理、字幕落库。
- `SourceCleanupService` 统一源文件清理、回收站、skip 后源文件回收。
- `ReviewDecisionService` 替换 `_step_validate()` 中置信度等级到审核动作的判断。
- 服务测试：`tests/test_pipeline_services.py`。

退出标准：`steps_file.py` 中不再直接承载去重替换、源文件清理、导入移动的完整业务策略；确认入库和普通入库复用同一导入服务。

### Phase 4: Config Facade

目标：减少全局配置 dict 扇出，尤其保护 pipeline 和 storage。

- [x] 新建 `core/config_view.py`。
- [x] 定义轻量 facade：
  - `PathConfig`
  - `SourcePolicyConfig`
  - `DedupConfig`
  - `FilenameTemplateConfig`
  - `ManualReviewConfig`
  - `MetadataProviderConfig`
- [x] 提供 `ConfigView.from_dict(config)`，保留原始 dict 访问能力。
- [x] 先在 pipeline services 中使用 facade。
- [x] 再把 `FileScanner`、`MetadataScraper`、`SourceCleaner` 中高频路径/扩展名配置替换为 facade 或显式构造参数。
- [x] 添加 facade 默认值和旧配置兼容测试。

执行记录：

- `ConfigView` 保留 `raw`，支持后续渐进迁移。
- `pipeline/services/` 不再直接读取高频深层配置 key。
- `LLMScraper` 和 provider registry 也接入 `ConfigView`，覆盖 LLM 与 Provider 配置入口。
- `SourceCleaner` 保留历史默认模型 `gpt-4o-mini`。

退出标准：pipeline services 不直接依赖裸 `config.get("source_policy", {})`、`config.get("path_rules", [])` 等关键 key。

### Phase 5: API Route Table

目标：降低新增端点成本，保持原生 HTTP 和 Mixin 模式。

- [x] 新建 `api/routes.py`。
- [x] 定义最小 route 结构：method、path/matcher、auth_required、handler_name、body_required。
- [x] 先迁移无路径参数的 GET 路由，如 `/api/health`、`/api/metrics`、`/api/config`。
- [x] 再迁移任务和 provider 这类带路径参数的路由。
- [x] `APIHandler.do_GET/do_POST/do_DELETE` 变成：
  - 解析 path/query/body
  - 鉴权
  - route 匹配
  - 调用 handler
  - 静态文件 fallback
- [x] 添加 route 匹配单元测试，覆盖当前端点路径。

执行记录：

- API route table 覆盖 GET、POST、PUT、DELETE 现有端点。
- `APIHandler` 保留原生 HTTP、鉴权、JSON 响应、静态文件 fallback。
- `tests/test_api_routes.py` 覆盖 exact route 优先级、动态参数、provider body-first 旧签名、delete_files body 提取。

退出标准：新增 API 端点不需要继续扩展长 `if/elif`；现有接口路径和响应格式不变。

### Phase 6: Documentation and Handoff

目标：让未来 AI 和人按新边界接手。

- [x] 更新迁移评审文档，明确大目录重组的兼容策略和执行顺序。
- [ ] 更新 `docs/系统架构总览.md` 的模块依赖和核心数据流。
- [x] 更新 `docs/architecture/import-pipeline.md` 和 `docs/architecture/task-lifecycle.md`，补充 `TaskContext`、`TaskLifecycle`、services 边界。
- [ ] 更新 `docs/架构/任务管理.md`，集中描述状态转换和 `file_location` 规则。
- [ ] 若 API route table 落地，更新 `docs/规范/接口规范.md` 的新增端点维护规则。
- [ ] 回写本计划的完成状态和实施偏差。

执行记录：

- 新增 `docs/plans/2026-06-01-domain-directory-migration-feasibility.md`。
- 新增 `docs/decisions/0002-domain-directory-migration-strategy.md`。
- 决策：暂不做一次性目录大迁移；先做 `domains/` 兼容 proof slice。
- Phase 6A 已新增 `media_importer/domains/import_flow/`，仅 re-export 已稳定实现。
- 新增 `tests/test_domain_import_flow_compatibility.py` 保护新旧 import 与旧 patch 路径兼容。
- Phase 6B 已新增 `media_importer/domains/source_cleaning/`，迁移 `SourceCleaner` 实现并保留旧 `storage/source_cleaner.py` 兼容别名。
- Phase 6C 已新增 `media_importer/domains/recycle/`，迁移回收站实现并保留旧 `core/recycle/*` 和 `core/safety.py` 兼容入口。
- Phase 6D services 已迁移 `media_importer/domains/import_flow/services/`，旧 `pipeline/services/*` 保留兼容别名。

退出标准：文档能作为 AI 后续修改 pipeline/API 的入口，而不需要先全文搜索。

## Decision Rationale

### 为什么先做上下文和状态机

当前最大认知成本来自“任务字典字段在不同步骤被隐式改变”。只拆文件不能解决这个问题。`TaskContext` 和 `TaskLifecycle` 可以把最容易出错的业务合约先显式化，收益最大，风险相对可控。

### 为什么不直接 Feature First 大重组

项目运行在 NAS 环境，现有测试也存在已知失败。大规模移动目录会放大 import、部署、文档、测试路径的风险。当前更适合先在现有目录内建立业务边界，再决定是否做目录级迁移。

### 为什么不用新框架

本项目的核心约束是轻量、可部署、低依赖。FastAPI/Pydantic 能提供结构化能力，但会增加运行和部署复杂度。本计划先用 dataclass、普通函数和小服务对象达成 80% 的结构收益。

### 为什么 API 路由放后面

API 路由可读性问题真实存在，但它不是业务状态错误的根源。先稳定 pipeline 领域模型，再迁移路由，可以避免 route table 只是“换一种写法的胶水”。

## Assumptions

| Assumption | Status | Evidence |
|------------|--------|----------|
| 现有 API 路径必须保持兼容 | Verified | AGENTS.md 要求新增端点同步文档，前端原生 JS 已直接依赖路径 |
| 不引入新框架更符合 NAS 部署约束 | Verified | 项目文档明确原生 HTTP API + 原生 JS，无构建依赖 |
| `TaskContext` 可先包装 dict，不必一次性迁移 DB row 类型 | Verified | 现有 pipeline 和 repo 都以 dict 传递任务 |
| 状态流转规则可以集中而不改 DB schema | Mostly verified | 当前合法状态已集中在 `core/db/constants.py`，但 `file_location` 规则散落，需要迁移时验证 |
| 现有测试能覆盖主要 pipeline 分支 | Unverified | 测试文件存在，但 `.pytest_cache` 显示有已知失败，Phase 0 必须先跑基线 |

## Risk Analysis

| Risk | Impact | Mitigation |
|------|--------|------------|
| context 与原 dict 双写不一致 | 高 | Phase 1 只包装原 dict，不复制状态；所有 mutator 直接写 raw |
| 状态机引入后漏掉某个旧更新字段 | 高 | 为每个旧分支建立对照测试；逐段替换，不一次性删除旧逻辑 |
| services 抽取导致步骤间副作用丢失 | 中 | 每个 service 输出显式 result，由 step 统一落库；先抽纯策略，再抽文件操作 |
| 配置 facade 默认值与 loader 默认值不一致 | 中 | facade 测试使用 `config.yaml.example` 和最小配置 dict |
| route table 迁移破坏静态文件 fallback | 中 | API route table 最后做，保留静态文件 fallback 作为显式测试项 |
| 已知失败测试干扰判断 | 中 | Phase 0 记录基线，只追踪新增失败 |

## Acceptance Criteria

- `PipelineRunner.process_one()` 中直接拼装 `status/file_location/confirm_status` 的重复更新明显减少，关键状态更新通过 `TaskLifecycle`。
- pipeline 主路径至少使用 `TaskContext` 表达任务输入、临时文件、刮削结果、入库结果。
- 普通入库和确认入库复用同一个入库服务或共享核心函数。
- 源文件清理和回收站移动从 `_step_import()` 中抽离。
- pipeline services 单元测试覆盖分类、去重决策、入库结果、源文件清理决策。
- 配置 facade 覆盖 pipeline 高扇出配置，并有默认值兼容测试。
- API route table 至少覆盖健康检查、配置、任务列表等基础端点；未迁移路由仍正常工作。
- 文档更新完成，后续 AI 能从架构文档定位状态流转和业务服务边界。

## Suggested Execution Order

1. Phase 0：基线测试和已知失败记录。
2. Phase 1：`TaskContext` 薄包装。
3. Phase 2：`TaskLifecycle`，优先替换 runner 主路径。
4. Phase 3：按 `ClassificationService` → `DedupService` → `SourceCleanupService` → `ImportService` → `ReviewDecisionService` 的顺序抽取。
5. Phase 4：配置 facade 接入 services。
6. Phase 5：API route table。
7. Phase 6：文档回写。

## References

- `docs/方案/任务状态模型与文件流转重构.md`
- `docs/plans/2026-05-31-refactor-phase1-internal-split.md`
- `docs/架构/流水线处理.md`
- `media_importer/pipeline/runner.py`
- `media_importer/pipeline/steps_file.py`
- `media_importer/pipeline/confirm.py`
- `media_importer/core/task_manager.py`
- `media_importer/api/handler.py`
