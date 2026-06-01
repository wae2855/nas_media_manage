---
title: "refactor: AI 友好架构整体调整路线图"
type: plan
date: 2026-05-31
status: pending
confidence: medium
---

# AI 友好架构整体调整路线图

> 一句话：这不是一次小修，而是一轮以“AI 易理解、业务边界清晰、新功能低成本扩展”为目标的分阶段大重构；每个阶段都保持项目可运行、可测试、可回滚。

## 目标

本轮架构调整服务三个目标：

1. **AI 最小成本理解项目**：AI 不需要全文搜索才能知道一个功能该改哪里、状态在哪里流转、配置在哪里生效。
2. **按业务角度解耦**：从“技术层目录”进一步走向“业务能力边界”，让刮削、入库、源目录清理、回收站、配置、任务状态各自有明确入口。
3. **新增或扩展功能最小成本**：新增 Provider、状态、清理策略、导入策略、API、配置项时，有固定扩展点和测试入口。

## 总体判断

项目当前已经完成了第一轮基础拆分：`api/core/scraper/storage/pipeline/notify/monitor` 的技术分层基本成立，部分大文件也已拆开。但真正影响 AI 和扩展成本的，不只是文件大小，而是：

- pipeline 的业务状态靠可变 `dict` 隐式传递；
- 状态和文件位置规则散落在 runner、confirm、API、DB migration；
- 配置 key 被各层直接读取；
- API 路由集中在长分支；
- 文档多，但还没有成为“AI 操作手册”。

因此本轮采用 **大目标、分阶段、每阶段可运行** 的方式推进。避免一次性 big bang，也避免无方向的小修小补。

## 架构目标图

```text
入口层
├── CLI / API / Watcher
│
应用编排层
├── ImportWorkflow / SourceCleanerWorkflow / ConfigWorkflow
│
业务服务层
├── ScrapeService
├── ClassificationService
├── DedupService
├── ImportService
├── SourceCleanupService
├── ReviewDecisionService
├── RecycleService
└── ConfigService
│
领域模型层
├── TaskContext
├── TaskLifecycle
├── FileLocation
├── ScrapeResult
├── ImportPlan
├── DedupDecision
└── ReviewDecision
│
基础设施层
├── SQLite repos
├── filesystem operations
├── metadata providers
├── LLM client
├── notifier
└── logger / metrics
```

## 阶段划分

### Phase 0: Baseline Commit and Reality Check

目标：把当前状态固定下来，后续任何重构都有明确基线。

- [x] 提交当前代码和文档为 baseline。
- [x] 记录当前分支、提交号、未提交内容数量。
- [x] 记录当前已知异常文件名或历史遗留文件。
- [x] 跑非 UI 测试基线，记录已知失败，不把旧失败算作重构回归。

执行记录：

- 基线提交：`1426c17 docs: establish ai-ready documentation framework`
- 当前分支：`main`
- 已知失败记录：`docs/testing/known-failures.md`

验收标准：

- 有一个 baseline commit。
- 后续重构基于 baseline commit 开始。
- 测试基线结果记录在重构阶段文档或提交说明中。

### Phase 1: AI 导航与文档入口重构

目标：先让 AI 和人知道“从哪里读、改哪里、怎么验证”。

- [x] 重写根目录 `AGENTS.md`，从项目说明升级为 AI 操作手册。
- [x] 建立文档入口、项目索引和 AI 导航：
  - `docs/README.md`
  - `docs/INDEX.md`
  - `docs/ai-map.md`
- [x] 建立新文档目录骨架：
  - `product/`
  - `architecture/`
  - `modules/`
  - `standards/`
  - `workflows/`
  - `decisions/`
  - `testing/`
  - `proposals/`
- [x] 备份旧文档和旧 `AGENTS.md` 到 `_archive/`。
- [x] 建立 `standards/`、`workflows/`、`decisions/`、`testing/` 的基础规则。
- [ ] 后续按代码重构结果补全 architecture/modules 详细事实。
- [ ] 原计划中的 `docs/架构/AI开发导航.md` 调整为 `docs/ai-map.md`：
  - 常见任务到代码入口映射；
  - 新增配置项清单；
  - 新增 API 清单；
  - 新增 pipeline step 清单；
  - 文件操作安全规则；
  - 测试选择指南。
- [ ] 在代码架构重构稳定后，更新旧 `docs/系统架构总览.md` 或迁移为新 `docs/architecture/overview.md`。
- [ ] 在代码架构重构稳定后，补全核心业务域详细事实：
  - 任务与状态；
  - 刮削与 Provider；
  - 入库流水线；
  - 源目录清理；
  - 回收站；
  - 配置系统；
  - API 服务。

验收标准：

- AI 修改一个常见功能时，能从文档 2-3 次跳转定位到代码。
- 文档明确“新增功能必须改哪些层”。
- 文档不再只是说明现状，而是能指导操作。
- 当前阶段遵循“框架先行，事实后补”，不在后续代码大重构前深写易漂移细节。

### Phase 2: 任务上下文与状态生命周期

目标：先解决最核心的隐式状态问题。

- [x] 新增 `pipeline/context.py`，定义 `TaskContext` 薄包装。
- [x] 新增 `core/task_lifecycle.py`，集中表达状态和 `file_location` 的转换。
- [x] 替换 `runner.py` 中重复的 `status/file_location/confirm_status` 直接更新。
- [x] 替换 `confirm.py` 和 `task_manager.py` 中 retry、confirm、ignore 的状态更新。
- [x] 增加状态转换测试。
- [x] 更新 `docs/architecture/task-lifecycle.md` 和 `docs/architecture/import-pipeline.md`。

验收标准：

- 新增状态时，主要修改点集中在 lifecycle 和文档。
- `file_location` 规则有单一权威说明。
- pipeline 主流程能通过 `TaskContext` 阅读。

### Phase 3: Pipeline 业务服务拆分

目标：让 pipeline runner 从“做所有事”变成“编排业务服务”。

- [x] 新增 `pipeline/services/`。
- [x] 抽出 `ClassificationService`。
- [x] 抽出 `DedupService`。
- [x] 抽出 `ImportService`。
- [x] 抽出 `SourceCleanupService`。
- [x] 抽出 `ReviewDecisionService`。
- [x] 普通入库和确认入库复用同一导入核心。
- [x] 每个服务配套单元测试。

执行记录：

- 新增 `tests/test_pipeline_services.py` 覆盖服务决策。
- `steps_file.py` 保留进度、日志和 DB task 更新，业务策略下沉到 services。
- `steps_scrape.py` 的审核决策下沉到 `ReviewDecisionService`。
- pipeline skip 后的源文件回收统一到 `SourceCleanupService`。

验收标准：

- `steps_file.py` 不再直接承载完整的去重、回收站、源文件清理、导入移动策略。
- 新增一种去重策略或清理策略，不需要改 runner 主流程。
- pipeline 文档以业务服务为单位描述。

### Phase 4: 配置系统 Facade 与变更链路

目标：降低新增配置项的扇出成本。

- [x] 新增 `core/config_view.py`，定义 typed facade。
- [x] 覆盖高扇出配置：
  - 路径；
  - 源文件策略；
  - 去重；
  - 文件名模板；
  - 人工审核；
  - Provider；
  - LLM。
- [x] pipeline services 改用 facade。
- [x] `FileScanner`、`SourceCleaner`、`MetadataScraper` 的高频配置逐步改为显式参数或 facade。
- [x] 更新配置迁移、校验、API、前端的新增配置流程文档。

执行记录：

- 新增 `ConfigView` 及 `PathConfig`、`SourcePolicyConfig`、`DedupConfig`、`FilenameTemplateConfig`、`ManualReviewConfig`、`MetadataProviderConfig`、`LLMConfig`、`ScannerConfig`、`SourceCleanerConfig`。
- pipeline services 已改用 `ConfigView`。
- `FileScanner`、`SourceCleaner`、`MetadataScraper`、`LLMScraper`、provider registry 的高频读取已接入 `ConfigView`。
- 新增 `tests/test_config_view.py` 覆盖默认值、扩展名归一化和消费者兼容。

验收标准：

- 新增配置项有固定 checklist。
- 业务层不再到处手写深层 `config.get(...)`。
- facade 默认值与 loader 默认值有测试保护。

### Phase 5: API 路由表与应用服务边界

目标：降低新增 API 和前端功能的成本。

- [x] 新增 `api/routes.py`。
- [x] 先迁移稳定 GET 路由。
- [x] 再迁移任务、配置、Provider、回收站、源目录清理路由。
- [x] API handler 只负责：
  - 解析请求；
  - 鉴权；
  - 路由匹配；
  - 调用 handler；
  - 统一响应；
  - 静态文件 fallback。
- [x] 将 handler 内直接业务逻辑逐步下沉到应用服务。
- [x] 更新 API 架构与规范文档。

执行记录：

- 新增 `media_importer/api/routes.py`，支持 exact route 与 `{param}` 动态路径。
- `handler.py` 的 API 长分支改为 route table dispatch。
- 保留静态文件 fallback、API key 鉴权和 `{code,status,message,data}` 响应格式。
- 新增 `tests/test_api_routes.py` 覆盖 route 匹配、动态参数和分发参数顺序。

验收标准：

- 新增端点只需要新增 route + handler，不需要扩展长分支。
- API 响应格式仍保持 `{code, status, message, data}`。
- 前端无需改路径。

### Phase 6: 业务域目录重组

目标：在业务边界稳定后，再考虑更大范围目录重组。

候选结构：

```text
media_importer/
├── app/                  # CLI/API/watcher 启动与组装
├── domains/
│   ├── import_flow/
│   ├── scraping/
│   ├── source_cleaning/
│   ├── recycle/
│   ├── configuration/
│   └── tasks/
├── infrastructure/
│   ├── db/
│   ├── filesystem/
│   ├── providers/
│   ├── llm/
│   └── notification/
└── webui/
```

本阶段不是必须立刻做。只有当 Phase 2-5 的业务边界稳定后，目录迁移才值得做。

验收标准：

- import 路径迁移有兼容层或一次性机械迁移脚本。
- 文档入口同步更新。
- 部署路径和 `deploy/` 同步策略明确。

### Phase 7: 测试体系与 AI 回归护栏

目标：让 AI 能安全大规模修改。

- [ ] 给每个业务服务补单元测试。
- [ ] 给状态生命周期补全转换表测试。
- [ ] 给 API route table 补路由匹配测试。
- [ ] 给配置 facade 补默认值和迁移兼容测试。
- [ ] 梳理 UI 测试依赖服务启动的要求。
- [ ] 新增 `docs/测试/AI回归测试指南.md`。

验收标准：

- AI 每次改动能按影响范围选择测试集合。
- 已知失败和新增失败能区分。
- 大重构不依赖手工点 UI 才能发现明显问题。

## 推荐执行顺序

1. **立刻做**：Phase 0 baseline commit。
2. **第一批重构**：Phase 1 + Phase 2。先让文档入口和状态模型稳定。
3. **第二批重构**：Phase 3 + Phase 4。抽业务服务和配置 facade。
4. **第三批重构**：Phase 5。迁移 API route table。
5. **评估后再做**：Phase 6。业务域目录重组。
6. **贯穿全程**：Phase 7。测试和 AI 护栏。

## 决策原则

- 每个阶段都要能单独提交。
- 每个阶段都要保持服务可启动。
- 不做“改了一半系统不可运行”的长时间迁移。
- 文档和代码同阶段更新。
- `deploy/` 不自动作为开发源，但 baseline 会保留当前状态；后续是否同步 deploy 需要单独决策。
- 任何删除/覆盖影视文件相关逻辑必须优先走回收站安全规则。

## 与现有计划关系

- `docs/plans/2026-05-31-refactor-phase1-internal-split.md`：已经完成或正在完成的文件级拆分基础。
- `docs/plans/2026-05-31-refactor-business-boundaries-plan.md`：本路线图中 Phase 2-5 的详细执行计划。
- 本文档：总路线图，负责阶段顺序和目标边界。

## 风险

| 风险 | 影响 | 处理方式 |
|------|------|----------|
| 一次性目录重组导致 import 大面积损坏 | 高 | 放到 Phase 6，等业务边界稳定后再做 |
| 已知失败测试掩盖重构回归 | 高 | Phase 0 记录基线，阶段内只追踪新增失败 |
| 文档继续漂移 | 中 | 每阶段验收包含文档更新 |
| deploy 目录与根源码漂移 | 中 | 后续单独制定 deploy 同步策略，不在业务重构中隐式处理 |
| 过度抽象导致代码更难读 | 中 | 只为真实业务变化点抽服务，不为了模式而抽象 |

## 完成标准

本轮整体重构完成时，应满足：

- AI 能从 `AGENTS.md` 和架构导航快速定位任务入口。
- pipeline 主流程只表达编排，不承载大量业务细节。
- 状态和文件位置转换有集中模块和测试。
- 配置读取有 facade，新增配置项有固定流程。
- API 路由注册表化，新增端点低成本。
- 文档结构与代码边界一致。
- 项目在每个阶段结束时可运行、可测试、可继续扩展。
