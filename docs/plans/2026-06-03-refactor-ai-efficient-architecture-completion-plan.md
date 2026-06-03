---
title: "refactor: AI-efficient architecture completion"
type: plan
date: 2026-06-03
status: in_progress
confidence: medium
---

# AI-efficient Architecture Completion Plan

一句话：当前项目已经有清晰的 feature-first 入口和文档导航，但真实实现仍分散在旧技术目录中；下一阶段目标是把实现、文档和测试继续收拢到更少、更稳定、更容易被 AI 检索的业务边界里。

## Review Findings

### F1: Feature 入口已建立，但实现仍是混合态

证据：

- `features/import_flow` 已是入库流程入口，但仍直接依赖 `storage`、`core.db`、`notify` 等旧技术目录。
- `features/scraping` 已导出 scraping public API，但 `scraper/` 仍承载主要实现。
- `features/configuration` 和 `features/tasks` 已提供 public API，但底层实现仍在 `core/`。

影响：

- AI 能从 `features/` 开始，但深入后仍要在旧技术目录里追依赖。
- 新功能容易产生“放 feature 还是放 core/storage/scraper”的决策成本。

### F2: `storage/` 同时承担基础设施和业务规则

证据：

- `storage/file_mover.py`、`storage/classifier.py`、`storage/dedup_checker.py` 既处理文件系统，也包含分类、命名、去重和源文件处理策略。
- `features/import_flow/services/` 调用这些实现，但业务边界还没有完全反转。

影响：

- 文件安全、分类策略、导入策略的变更容易跨目录扩散。
- 后续如果新增“预览导入”“批量重命名”“源目录策略”等功能，容易继续堆到 `storage/`。

### F3: `scraper/` 仍是事实实现中心

证据：

- `scraper/metadata_scraper.py`、`llm_scraper.py`、`confidence_engine.py`、`dimension_manager.py`、`providers/` 仍是主要实现位置。
- `features/scraping` 和 `features/providers` 当前更多是 public API facade。

影响：

- 新增 Provider、提示词、置信度规则时，文档说先看 feature，但代码事实仍在旧目录。
- scraping/provider/prompt 的边界容易互相穿透。

### F4: API handler 仍偏重

证据：

- `api/handler.py` 仍是全局组装和若干动作入口。
- 多个 `*_handlers.py` 直接调用 DB、monitor、notify、安全、scraper 或 storage 实现。

影响：

- API 层可能重新吸收业务策略。
- 新增 API 时，容易绕过 feature service。

### F5: 文档状态存在轻微不一致

证据：

- `docs/INDEX.md` 仍把已 `complete` 的上一轮计划列为 Active Plans。
- 部分 standards 仍以 `scraper/storage/core` 作为当前层规则，而不是明确标注为待迁移实现目录。

影响：

- AI 会把已完成计划误认为当前执行计划。
- 文档对“当前事实”和“目标方向”的边界还可以更锐利。

### F6: 前端仍是最大 AI 成本区

证据：

- `webui/index.html`、`webui/js/config.js`、`webui/js/tasks.js` 和多份 CSS 超过 500 行。
- 前端尚未按业务功能、页面状态和 API 依赖重新拆分。

影响：

- 后续前端改动会继续让 AI 读取大文件。
- 深层 UI/E2E 测试暂时难以稳定重建。

### F7: 工程化护栏还不完整

证据：

- 当前没有统一 `pyproject.toml`、formatter、lint、typecheck 配置。
- 依赖方向主要靠文档和少量 entrypoint 测试约束。

影响：

- 后续重构质量依赖人工纪律。
- 目录边界可能在新增功能时悄悄回退。

## Target End State

- AI 从 `AGENTS.md`、`docs/INDEX.md` 和 `docs/ai-map.md` 能在 1 到 2 跳内找到业务实现、文档和测试。
- `features/` 不只是 facade，而是稳定业务事实源。
- `core/`、`storage/`、`scraper/`、`monitor/`、`notify/` 要么降级为 infrastructure/adapters，要么被 feature 吸收。
- API/CLI/watcher 只做入口组装、请求解析、响应包装和 feature 调用。
- 前端重做前，后端 feature/API 文档足够稳定。
- 当前计划、已完成计划和归档计划状态清晰，AI 不会扫到过期计划当作当前任务。

## Scope

本计划包含：

- 收口文档状态和 active plan 索引。
- 迁移 scraping/provider/prompt 的实现边界。
- 拆分 storage 中的业务策略和文件系统基础设施。
- 薄化 API handler 对旧技术目录的直接调用。
- 加强依赖方向测试和结构扫描。
- 为前端重做准备 API/业务依赖地图。

## Non-Goals

- 不在本阶段重做前端 UI。
- 不改变 HTTP API 路径和响应格式。
- 不处理真实 TMDB/LLM 网络 E2E。
- 不一次性重写所有旧技术目录；每次只迁移一个业务切片。
- 不删除 archive 内容；只保证当前事实文档不依赖 archive。

## Proposed Solution

采用“先文档状态收口，再后端实现迁移，最后前端准备”的顺序。

核心策略：

- 每个迁移先做 feature public API 和结构测试，再移动实现。
- 不再新增旧技术目录 public import；旧目录只能是 implementation detail。
- 迁移时优先保留行为，结构变化和行为变化分开。
- 每个阶段同步 `docs/features/`、`docs/architecture/`、`docs/INDEX.md` 和测试矩阵。

## Implementation Tasks

### Phase 1: 文档状态和计划索引收口

- [x] 将上一轮 complete 计划从 `docs/INDEX.md` Active Plans 移出或标注为 completed/pending acceptance。
- [x] 新增本计划为当前执行中计划。
- [x] 更新 `docs/standards/architecture.md`，把 `core/storage/scraper/monitor/notify` 标注为当前实现目录和迁移目标，而不是长期业务层。
- [x] 更新 `docs/architecture/module-map.md`，明确 feature 到 infrastructure 的允许依赖和禁止依赖。
- [x] 更新 `docs/tracking/pending-acceptance.md`，把上一轮等待验收和本轮阶段收口区分开。

### Phase 2: Scraping / Providers / Prompts 实现收口

- [x] 把 `scraper/metadata_scraper.py` 迁到 `features/scraping/` 或拆出 feature-owned service。
- [x] 把 `confidence_engine.py` 迁到 `features/scraping/`，旧路径保留薄 wrapper。
- [x] 把 `confidence_models.py` 迁到 `features/scraping/`，旧路径保留薄 wrapper。
- [x] 把 `dimension_manager.py` 明确归入 `features/scraping/` 或 `infrastructure`。
- [x] 把 `scraper/providers/` 迁到 `features/providers/`，只保留外部 client adapter 时放入 infrastructure。
- [x] 把 prompt 相关实现迁到 `features/prompts/`，避免 prompt feature 只做 re-export。
- [x] 补充 scraping/provider/prompt import smoke tests 和 provider mock tests。
- [x] 更新 `docs/features/scraping.md`、`providers.md`、`prompts.md` 和 `architecture/scraping.md`。

### Phase 3: Storage / 文件系统边界收口

- [x] 将 `FileCopier` 复制基础能力归入 `infrastructure/filesystem`，旧 `storage/file_copier.py` 保留 wrapper。
- [ ] 继续评估路径校验、复制/移动、删除基础能力是否归入 `infrastructure/filesystem`。
- [x] 将分类规则和模板渲染迁到 `features/import_flow/services/classification_rules.py`，旧 `storage/classifier.py` 保留 wrapper。
- [x] 将去重策略迁到 `features/import_flow/services/dedup_rules.py`，旧 `storage/dedup_checker.py` 保留 wrapper。
- [x] 将命名模板与字幕命名规则迁到 `features/import_flow/services/naming.py`，旧 `storage/file_mover.py` 复用该 service。
- [x] 将入库移动、源文件删除、附属文件识别和空父目录清理迁到 `features/import_flow/services/file_operations.py`，旧 `storage/file_mover.py` 保留 wrapper。
- [ ] 继续评估源文件处理策略是否迁到 `features/import_flow/services/` 或独立 feature service。
- [x] 将 `storage/source_cleaner.py` 的剩余旧入口继续对齐 `features/source_cleaning/`。
- [x] 增加 storage boundary tests，防止 feature 继续直接依赖旧业务策略文件。
- [x] 更新 `docs/architecture/storage-filesystem.md` 和 import-flow/source-cleaning feature 文档。

### Phase 4: API / CLI / Watcher 薄化

- [x] 盘点 `api/*_handlers.py` 中直接访问 DB/storage/scraper/monitor/notify 的调用。
- [x] 为任务删除高频动作建立 `features/tasks/delete_service.py` proof slice。
- [x] `api/task_delete.py` 保留参数解析、错误包装、JSON 响应，不承载任务删除业务策略。
- [x] 将启动扫描逻辑通过 `features.import_flow.scan_source_dir` 暴露给 API/CLI/watcher proof slice。
- [x] 为 source cleaner API 建立 `features/source_cleaning/application_service.py` proof slice。
- [x] 为 config handler 建立 `features/configuration/application_service.py` proof slice，承接 UI payload、section save、permission/path payload 和 watcher status。
- [x] 为 config reload 建立 `features/configuration/runtime_service.py` proof slice，承接 pipeline/notifier/watcher 刷新。
- [x] 为 dimension handler 建立 `features/scraping/dimensions_service.py` proof slice，承接维度 CRUD 和 tier 校验。
- [x] 为 prompt/provider prompt handler 建立 `features/prompts/application_service.py` proof slice，承接全局和 Provider-specific prompt 文件读写。
- [x] 为 `/api/tasks` 列表建立 `features/tasks/list_service.py` proof slice，承接分页、状态校验和统计 payload。
- [x] 为任务队列 clear/retry/retry-all/pause/resume/status 建立 `features/tasks/queue_service.py` proof slice。
- [x] 为人工审核 confirm/reclassify/confirm-all 建立 `features/tasks/review_service.py` proof slice。
- [ ] 继续为其他高频 API 动作建立 feature service 或 application function。
- [ ] 继续薄化其他 API handler，保留参数解析、错误包装、JSON 响应。
- [x] CLI 和 watcher 的扫描入口改为通过 `features.import_flow.scan_source_dir`，不再直接调用 `storage.file_scanner`。
- [x] 扩展 `tests/test_feature_entrypoints.py`，覆盖任务删除 API proof slice 的依赖方向。
- [x] 扩展 `tests/test_feature_entrypoints.py`，覆盖 CLI/watcher 的依赖方向。

### Phase 5: 前端重做准备

- [x] 输出 `docs/product/frontend-information-architecture.md`。
- [x] 输出 `docs/architecture/frontend-api-dependency-map.md`。
- [x] 按页面列出 API、业务 feature、状态字段和测试入口。
- [x] 将当前超 500 行前端文件登记为重做输入，而不是继续局部修补。
- [x] 前端开工前先确定页面拆分、状态模型和 UI/E2E 验收方式。

### Phase 6: 工程化护栏

- [x] 评估是否新增 `pyproject.toml` 管理 pytest、ruff/formatter、可选 typecheck。当前结论：在 lint/typecheck 工具链未定前暂不新增，继续沿用 `pytest.ini`。
- [x] 增加结构扫描测试，确保当前事实文档不引用 archived 文件作为事实来源。
- [x] 增加 dependency direction test，限制 API/feature/infra 的依赖方向。
- [x] 将工程化命令写入 `AGENTS.md` 和 `docs/standards/testing.md`。

## Acceptance Criteria

- `docs/INDEX.md` 不再把 complete plan 当作 active plan。
- 新业务代码优先落在 `features/`，旧技术目录不再新增 public 入口。
- Scraping/provider/prompt 至少完成一个代表性 proof slice 的实现迁移。
- Storage 至少完成一个代表性 proof slice，将业务策略从基础文件系统操作中分离。
- API handler 至少完成一个代表性 proof slice，证明 handler 可以薄调用 feature service。
- `tests/test_feature_entrypoints.py` 覆盖 configuration/tasks/scraping/import-flow/API 的关键入口。
- 默认回归 `python3 -m pytest tests/` 通过。
- `PYTHONPYCACHEPREFIX=/private/tmp/nas_media_manage_pycache python3 -m compileall -q media_importer tests` 通过。
- `git diff --check` 通过。
- 文档同步覆盖 `docs/features/`、`docs/architecture/`、`docs/INDEX.md`、`docs/ai-map.md`。

## Decision Rationale

下一阶段不应该先重做前端。前端重做需要稳定 API 和业务文档，否则会把旧结构问题带进新界面。

也不应该继续只做 facade。Facade 已经降低检索成本，但如果真实实现长期留在旧目录，AI 仍会在深入时迷路。更好的方式是每次选一个 proof slice，把真实实现、文档、测试一起迁到新边界。

## Constraints and Boundaries

- 文件删除/覆盖逻辑仍必须遵守回收站安全规则。
- 发布包仍以根源码为事实来源，不手工补丁 deploy package workspace。
- 不为了迁移而改变用户可见行为。
- 每个阶段必须保持默认测试可运行。
- 完成阶段后写入 pending acceptance，用户验收后再进入 completed items。

## Risk Analysis

| Risk | Impact | Mitigation |
|------|--------|------------|
| 移动实现导致 import cycle | 中 | proof slice 先行，增加 import smoke tests |
| feature 目录膨胀成新“大杂烩” | 中 | 每个 feature 文档明确 application/domain/infrastructure 边界 |
| API 薄化时改变响应行为 | 高 | 每个 handler 迁移前后保留 API 回归或快照测试 |
| storage 拆分触碰文件安全 | 高 | 文件删除/覆盖相关迁移必须跑 recycle/safety tests |
| 前端继续推迟导致旧 UI 成为瓶颈 | 中 | Phase 5 输出前端 IA 和 API dependency map 后再进入 UI 重做 |
| 工程化工具引入过早造成噪音 | 中 | 先 dry-run/局部启用，再决定是否纳入默认门禁 |

## Suggested Execution Order

1. Phase 1：立即执行，成本低，能避免 AI 继续读取过期计划。
2. Phase 2：先迁 scraping/provider/prompt 的一个 proof slice。
3. Phase 3：再迁 storage/import-flow 的一个 proof slice。
4. Phase 4：用已迁出的 feature service 薄化 API。
5. Phase 5：准备前端重做资料。
6. Phase 6：补工程化护栏。
