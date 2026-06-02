# Domain Directory Migration Feasibility Review

Date: 2026-06-01
Status: completed
Related roadmap phase: Phase 6

## Purpose

评估是否应该把当前 `media_importer/{api,core,pipeline,scraper,storage,...}` 大范围移动为 `domains/` + `infrastructure/` 结构。

本评审只做迁移决策和兼容策略，不直接移动代码。原因：目录迁移会影响 import 路径、测试 patch 路径、部署副本和文档入口，风险高于前几阶段的边界内重构。

## Evidence

### Current Package Shape

当前源码包内 Python 文件数量：

| Area | Files |
|------|-------|
| `core` | 21 |
| `pipeline` | 15 |
| `api` | 15 |
| `scraper` | 14 |
| `storage` | 9 |
| `notify` | 3 |
| `monitor` | 3 |

当前最大文件仍集中在 API、scraper、source cleaner、CLI、pipeline、core DB 等位置。目录移动本身不会减少复杂度，只有在业务边界稳定且兼容策略明确后才有价值。

### Import Coupling

在 `media_importer`、`tests`、`docs`、`AGENTS.md` 中，显式历史包路径引用大致为：

| Imported Area | References |
|---------------|------------|
| `core` | 73 |
| `scraper` | 50 |
| `storage` | 18 |
| `api` | 12 |
| `pipeline` | 6 |
| `monitor` | 5 |
| `notify` | 4 |

测试中与 `pipeline/storage/scraper/api/core.db` 相关的 import 或 patch 路径约 138 处。直接移动目录会让大量 mock patch 路径失效，即使业务代码没有变。

### Deployment Coupling

`deploy/nas-media-importer/app/server/media_importer/` 里存在已跟踪 package workspace 副本。根目录代码迁移后，必须明确它不是开发源，否则会出现“开发包结构”和“fnOS 包结构”分叉。

### Current Stabilized Boundaries

前 5 个阶段已经形成了更有价值的业务边界：

- `TaskContext`
- `TaskLifecycle`
- `pipeline/services/`
- `ConfigView`
- `api/routes.py`

这些边界已经降低了 AI 搜索成本。目录名还没有变，但修改入口已经更稳定。

## Decision

不执行一次性大规模目录迁移。

采用三步策略：

1. **Keep Stable Public Imports**
   保留现有 `media_importer.core`、`media_importer.pipeline`、`media_importer.storage`、`media_importer.scraper`、`media_importer.api` 作为公共兼容入口。

2. **Introduce Domains Only As Proof Slices**
   只有当某个业务域已经有稳定 service/facade，才允许增加新的 `domains/<domain>/` 入口，并让旧路径 re-export 新实现。

3. **Move One Domain At A Time**
   每次只迁移一个低风险域，先迁移纯策略或低 I/O 代码，再迁移文件操作、DB、API 启动层。

## Recommended Migration Order

### Phase 6A: Compatibility Layer Only

目标：验证新目录不会破坏旧 import。

Status: completed

- 新增 `media_importer/domains/` 包。
- 选择一个低风险域做 proof slice，例如：
  - `domains/import_flow/` re-export `pipeline.context`、`core.task_lifecycle`、`pipeline.services.review`。
- 旧路径保持可用，不改调用方。
- 增加 import compatibility tests。

执行记录：

- 新增 `media_importer/domains/import_flow/`。
- `import_flow` 初始仅 re-export `TaskContext`、`TaskLifecycle` 和 `ReviewDecisionService`；Phase 6D services 后已承载 services 实现。
- 新增 `tests/test_domain_import_flow_compatibility.py` 保护新旧 import 与旧 patch 路径兼容。

退出标准：

- 新旧 import 都可用。
- 不需要修改现有业务代码调用方。
- 测试 patch 路径仍然可用。

### Phase 6B: Source Cleaning Domain

目标：迁移边界相对清楚的源目录清理域。

Status: completed

候选：

- `storage/source_cleaner.py`
- `api/source_cleaner_handlers.py`
- `core/db/cleaner_repo.py`

策略：

- 先创建 `domains/source_cleaning/`。
- 新模块持有实现。
- 旧模块只 re-export 或薄包装。
- API route 不变。

退出标准：

- 源目录清理相关单元/集成测试通过。
- API 路径不变。
- 文档入口改为 domain-first，但兼容旧模块链接。

执行记录：

- 新增 `media_importer/domains/source_cleaning/`。
- `SourceCleaner` 实现迁移到 `domains/source_cleaning/cleaner.py`。
- `storage/source_cleaner.py` 改为兼容别名，旧 import 和旧 patch 路径继续可用。
- API handler 改为从 domain 入口导入 `SourceCleaner` 和清理记录函数，API 路径不变。
- 新增 `tests/test_domain_source_cleaning_compatibility.py`。

### Phase 6C: Recycle Domain

目标：迁移安全规则明确且已模块化的回收站域。

Status: completed

候选：

- `core/recycle/`
- `api/recycle_handlers.py`
- `core/safety.py` 中回收站桥接函数

策略：

- `domains/recycle/` 作为业务入口。
- `core/safety.py` 暂时保留兼容函数，因为删除/覆盖安全规则依赖它。

退出标准：

- `tests/test_recycle_and_safety.py` 通过或只剩已记录旧失败。
- 所有直接删除规则仍受回收站门控。

执行记录：

- 新增 `media_importer/domains/recycle/`。
- `core/recycle/manager.py` 和 `core/recycle/browser.py` 实现迁移到 domain。
- 旧 `core/recycle/*` 改为兼容别名，历史私有 helper 和 patch 路径继续可用。
- `core/safety.py` 保留文件安全 facade，回收站函数从 domain 入口导入。
- API handler 改为从 domain 入口导入回收站浏览、恢复和永久删除函数，API 路径不变。
- 新增 `tests/test_domain_recycle_compatibility.py`。

### Phase 6D: Import Flow Domain

目标：在前面 proof slice 稳定后迁移主流程。

Status: steps_completed

候选：

- `pipeline/context.py`
- `pipeline/services/`
- `pipeline/runner.py`
- `pipeline/confirm.py`

策略：

- 先迁移 services，再迁移 runner/confirm。
- 保留 `media_importer.pipeline` 公共入口至少一个版本周期。
- 更新测试 patch 路径，优先 patch 新 domain；旧 patch 增加兼容测试。

退出标准：

- `tests/test_pipeline_services.py`
- `tests/test_task_context_lifecycle.py`
- `tests/test_full_flow.py` 关键切片
- API 和 CLI 启动 smoke test

执行记录：

- 已先迁移 services，不迁移 runner/confirm 实现。
- 新增 `media_importer/domains/import_flow/services/`。
- `pipeline/services/*` 改为兼容别名，旧 import 和旧 patch 路径继续可用。
- `pipeline/runner.py`、`steps_file.py`、`steps_scrape.py`、`confirm.py` 已改为从 domain services 导入。
- `TaskContext` 实现迁移到 `domains/import_flow/context.py`。
- `pipeline/context.py` 改为兼容别名，旧 import 继续可用。
- `ConfirmMixin` 实现迁移到 `domains/import_flow/confirm.py`。
- `pipeline/confirm.py` 改为兼容别名，旧 import 继续可用。
- `PipelineRunner` 实现迁移到 `domains/import_flow/runner.py`。
- `pipeline/runner.py` 改为兼容别名，`media_importer.pipeline.PipelineRunner` 继续可用。
- `StepsMixin`、`FileStepsMixin`、`ScrapeStepsMixin` 实现迁移到 `domains/import_flow/steps/`。
- `pipeline/steps.py`、`pipeline/steps_file.py`、`pipeline/steps_scrape.py` 改为兼容别名。
- `domains/import_flow/runner.py` 从 domain steps 导入 `StepsMixin`。
- `domains/import_flow/__init__.py` 导出 services、steps、`TaskContext` 和 `TaskLifecycle`。
- `tests/test_domain_import_flow_compatibility.py` 增加 context/confirm/runner/steps/services 兼容与旧 patch 路径保护。

## Explicit Non-Goals

- 不在一个提交里移动所有目录。
- 不把 `api`、`core/db`、`media_importer.py` 入口层作为第一批迁移对象。
- 不删除旧 import 路径。
- 不把 `deploy/nas-media-importer/` 当作应用源码入口；fnOS package 由 `deploy/build_fpk.sh` 从根源码生成。

## Compatibility Rules

- 旧路径必须继续工作：
  - `media_importer.pipeline`
  - `media_importer.core`
  - `media_importer.storage`
  - `media_importer.scraper`
  - `media_importer.api`
- 新路径只作为新开发入口逐步引入。
- 旧路径 re-export 时必须有测试保护。
- deploy package workspace 不作为 import 或架构证据；发布时从根源码重建。
- 每个迁移提交必须包含：
  - import compatibility test；
  - module docs update；
  - architecture map update；
  - deploy impact note。

## Rollback Strategy

每个 domain 迁移必须是独立提交。出现问题时：

1. 回退该 domain 迁移提交。
2. 保留前置阶段的 `TaskContext`、`TaskLifecycle`、services、`ConfigView`、route table。
3. 不回退已稳定的业务边界重构。

## Recommendation

下一步不要做完整目录移动。

建议执行 **Phase 6A: Compatibility Layer Only**：新增 `domains/` 包和一个只 re-export 的 proof slice，验证新域入口、旧路径兼容和文档导航是否成立。

如果 Phase 6A 通过，再迁移 `source_cleaning` 或 `recycle`，不要先迁移主 pipeline。

## Validation For This Review

本评审基于以下代码事实：

- 评审开始时工作区干净。
- 已存在稳定边界：`TaskContext`、`TaskLifecycle`、pipeline services、`ConfigView`、API route table。
- `deploy/nas-media-importer/app/server/media_importer/` 存在已跟踪 package workspace 副本，但不作为开发源。
- 历史 import 和测试 patch 路径引用数量较高。

本评审没有修改应用代码。提交前验证：

- `git diff --check`
- `python3 -m pytest tests/test_api_routes.py tests/test_config_view.py tests/test_pipeline_services.py tests/test_task_context_lifecycle.py tests/test_task_operations.py tests/test_full_flow.py::TestANormalFlow tests/test_full_flow.py::TestCSkipFlow tests/test_full_flow.py::TestFConfirmFlow tests/test_full_flow.py::TestGReclassifyFlow`
