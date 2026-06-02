---
title: "refactor: feature-first code and documentation structure"
type: plan
date: 2026-06-02
status: in_progress
confidence: medium
---

# Feature-first Code and Documentation Structure Plan

一句话：暂停对旧 known failures 的深层修复，把当前工作重新聚焦到激进的 feature-first 新架构和新文档结构；项目仍处于未上线开发阶段，不以历史数据、旧 import、旧测试和并行兼容为主要约束。

## Problem Statement

当前项目已经完成 AI 友好重构的第一轮收口：文档导航、任务生命周期、pipeline services、ConfigView、API route table、`features/` 初始业务入口、测试 gating 都已落地。

但继续调查 known failures 时发现，失败混合了多种来源：

- 旧测试仍使用旧顶层 import 或旧业务术语。
- 旧 UI/E2E 测试依赖外部服务、Playwright、真实配置或网络。
- 部分测试反映旧业务契约，和新架构下的行为需要重新决策。
- 前端尚未按新架构重做，深层 UI/E2E 测试会放大环境和旧契约噪声。

更重要的是，本项目当前是未上线开发阶段的软件产品，不需要为历史生产数据、旧部署、旧 import 调用方或并行兼容承担过高成本。因此当前优先级应从“渐进兼容式迁移”调整为“按业务功能重组为 feature-first 架构”。测试工作保留最低限度稳定回归入口，不再把旧失败作为当前阶段的阻塞项。

## Target End State

完成本计划后，应满足：

- 代码主入口按 feature-first 业务能力定位，而不是按技术层目录定位。
- 每个业务 feature 内有自己的 API/application/domain/infrastructure/docs/tests 相关入口或明确映射。
- 新架构优先表达业务能力：入库流程、刮削、配置、任务、源目录清理、回收站、Provider、提示词、通知监控。
- 旧技术分层目录如果不再适合 AI 检索，可以整体迁移、合并、归档或降级为基础设施目录。
- 文档结构按新代码边界组织，而不是旧目录历史自然生长。
- 历史文档统一归档到一个 archive 入口，当前事实文档只保留在新结构中。
- 项目下所有目录和文件都完成定位：保留、兼容保留、待迁移、归档候选、生成物忽略。
- 新架构后形成一个干净的全新结构；旧的、废弃的、历史生成的、测试脚本式遗留文件统一移入归档目录，后续运行稳定后可删除。
- 当前文档不得引用已经归档的文件内容；如必须提及历史材料，只引用 archive 索引，不把旧内容作为当前事实依据。
- 需求、bug、重构、文档、前端等工作都有完整闭环生命周期：
  - 发现/头脑风暴；
  - 方案/决策；
  - 计划；
  - 实施；
  - 测试；
  - 文档更新；
  - 待用户验收；
  - 用户验收；
  - 完成摘要；
  - 规范回写；
  - 历史计划归档。
- 验收前事项有统一记录；超过约定时间仍未用户确认的事项，AI 在后续对话中需要主动提醒用户验收。
- 用户验收后，必须将摘要写入完成事项，并把已完成 plan/方案移出活跃文档区，避免后续 AI 扫描时被旧方案干扰。
- AI 能从 `AGENTS.md`、`docs/README.md`、`docs/INDEX.md`、`docs/ai-map.md` 直接定位新架构入口。
- 前端重做可以依赖稳定 feature 文档、API 文档、配置/数据库文档和产品工作流文档。
- 深层测试在前端完成后重新规划，不再混用旧测试契约作为当前架构迁移阻塞。

## Scope

本计划包含：

- 继续按 feature-first 迁移代码入口和稳定实现。
- 允许激进重组为 feature-first 目录，不以旧 import 兼容为硬性要求。
- 结合配置文件、SQLite 数据模型、API、前端页面和业务流程统一设计 feature 边界。
- 重建文档结构，使文档与新代码边界一致。
- 统一历史文档归档策略。
- 统一全仓库文件和目录定位策略。
- 归档不再属于新架构的历史文件、旧方案、旧测试脚本和生成物残留。
- 建立项目工作闭环生命周期文档和验收记录机制。
- 建立“待验收事项”和“完成事项”文档。
- 建立完成后规范回写规则。
- 更新 AI 导航、模块索引、架构总览和工作流文档。
- 可以删除或归档旧 import 路径和旧兼容层，前提是新架构入口、文档和测试同步更新。
- 标记 known failures 为“暂缓处理，待新前端和新架构文档完成后重评”。
- 将前端设计工作保留为待办事项，后续单独展开讨论和规划。

## Non-Goals

本阶段不做：

- 不修复所有 known failures。
- 不做完整 UI/E2E 深测。
- 不保留旧 `pipeline/`、`storage/`、`core/recycle/` 兼容入口作为硬性要求；如新架构更清晰，可以归档或删除。
- 不以历史 DB schema 兼容为约束；可以按新产品模型重新组织配置和数据库文档，必要时重建 schema/migration。
- 不重做前端页面。
- 不在本阶段细化前端设计方案，只登记为待办。
- 不改变 API 路径和响应格式。
- 不处理真实 TMDB/LLM 网络 E2E。

## Proposed Solution

采用三段式推进：

1. **Feature-first Code Architecture First**
   - 按业务 feature 重组代码。
   - 每个 feature 的边界覆盖配置、数据、API、业务服务、前端依赖和测试入口。
   - 旧路径不再默认保留兼容；不适合新架构的代码和测试统一归档。

2. **Documentation Structure Second**
   - 文档按 feature-first 新架构分层重组。
   - 明确“新事实入口”和“legacy 文档”边界。
   - 为前端重做准备产品、API、模块和工作流文档。

3. **Frontend Then Deep Testing**
   - 前端重做完成后，再重新设计深层测试。
   - 旧 known failures 到时按新业务契约重新判定：修测试、修实现或废弃。

## Implementation Tasks

### Phase 1: Feature-first Code Migration

- [x] 新增 ADR，替代或修订 `ADR-0002`：
  - 项目仍未上线；
  - 不考虑历史生产数据；
  - 不以旧 import/旧 patch/旧测试兼容为硬约束；
  - 采用激进 feature-first 重组；
  - 文档和代码同步迁移；
  - 旧内容统一归档，后续运行稳定后删除。
- [x] 盘点当前代码目录，重新定义 feature-first 目标结构。
- [x] 确认新顶层代码结构，例如：
  - `features/import_flow/`
  - `features/scraping/`
  - `features/configuration/`
  - `features/tasks/`
  - `features/source_cleaning/`
  - `features/recycle/`
  - `features/providers/`
  - `features/prompts/`
  - `shared/` 或 `infrastructure/`
  - `app/` 或 `entrypoints/`
- [x] 每个 feature 内明确：
  - `application`：用例编排；
  - `domain`：业务模型/规则；
  - `infrastructure`：DB、文件系统、外部 provider；
  - `api`：HTTP handler/route；
  - `config`：配置项和默认值；
  - `docs/tests` 映射。
- [x] 迁移或新增 `scraping` feature：
  - `MetadataScraper`
  - provider registry
  - confidence / trace / dimension mapping 相关入口
  - 旧 `scraper/` 路径可归档，不强制兼容。
- [x] 迁移或新增 `configuration` feature：
  - `ConfigView`
  - config loader / migration / validator 的业务入口
  - 配置保存 API 辅助逻辑
  - 结合 `config/config.yaml`、配置 API、前端配置页重新定义配置文档。
- [x] 迁移或新增 `tasks` feature：
  - `TaskLifecycle`
  - `TaskManager`
  - task repo public entry
  - 结合 SQLite task schema 重新组织任务状态/文件位置/确认状态文档。
- [x] 迁移或重组 `api/`：
  - route table 可保留；
  - handler 可以按 feature 分布；
  - 保留统一 HTTP 响应规范。
- [ ] 迁移或重组 `core/db`：
  - 不再按历史兼容优先；
  - 按 feature repo 或 shared infrastructure 重新定位。
- [x] 为已迁移 feature 增加新架构 smoke/import tests。
- [x] 更新已迁移入口 imports：应用入口优先从 feature 新结构导入；旧测试按需重写或归档。

### Phase 2: Documentation Structure Rebuild

- [x] 建立全仓库结构清点清单：
  - 每个顶层目录；
  - `media_importer/` 下每个子包；
  - `tests/` 下每个测试文件；
  - `docs/` 下每个文档目录和文件；
  - `deploy/`、配置样例、脚本、临时/生成物。
- [x] 为每个文件或目录标注归属：
  - `current`: 新架构当前事实来源；
  - `compatibility`: 为旧 import、旧 patch、旧部署路径保留的兼容入口；
  - `pending_migration`: 后续要迁移到新架构，但当前仍在用；
  - `archive_candidate`: 历史文档、旧方案、历史测试脚本、废弃实现或临时产物；
  - `generated_ignored`: 生成物或本地运行产物，不纳入源码事实。
- [x] 新增结构清点文档：
  - `docs/architecture/repository-structure.md`：当前仓库结构和归属说明；
  - `docs/architecture/archive-policy.md`：归档标准、命名、禁止引用规则；
  - `docs/testing/test-inventory.md`：测试文件分级、保留/归档/重写建议。
- [x] 建立统一归档目录：
  - `docs/_archive/` 保留历史文档；
  - 如需归档非文档文件，使用单一仓库级归档入口，例如 `_archive/` 或 `archive/`，并在 ADR 中确认；
  - 归档目录内按日期和来源分组；
  - 归档目录必须有 README，说明这些内容不是当前事实来源。
- [x] 归档历史测试脚本：
  - 测试文件若是一次性脚本、旧结构 import、外部服务脚本式测试，移动到归档；
  - 当前 `tests/` 只保留能作为新架构回归、明确 gated、或即将重写的测试；
  - 归档后更新 `pytest.ini`、`tests/conftest.py` 和测试文档，确保默认测试不扫描归档。
- [x] 清理当前文档引用：
  - 扫描 `docs/`、`AGENTS.md` 中对归档文件的引用；
  - 当前事实文档不得直接链接归档内容；
  - 如需保留历史说明，只链接 archive README 或在 `docs/legacy.md` 说明。
- [x] 建立统一归档策略：
  - 所有历史文档统一进入 `docs/_archive/`；
  - 旧中文目录、旧方案、旧架构、旧测试、旧规范都移入 archive；
  - 活跃文档区只保留当前事实入口；
  - archive 内必须保留索引，方便必要时追溯。
- [x] 重审 `docs/README.md`，让它成为新架构总入口。
- [x] 重审 `docs/INDEX.md`，用 feature-first 代码索引替换旧技术目录优先叙述。
- [x] 重审 `docs/ai-map.md`，按任务类型指向新 feature 入口。
- [x] 更新 `docs/architecture/overview.md`：
  - 新架构层次；
  - feature-first 结构；
  - legacy compatibility 规则。
- [x] 更新 `docs/architecture/module-map.md`，明确允许依赖方向。
- [x] 新增或重写 feature 模块文档：
  - `docs/features/import-flow.md`
  - `docs/features/scraping.md`
  - `docs/features/configuration.md`
  - `docs/features/tasks.md`
  - `docs/features/source-cleaning.md`
  - `docs/features/recycle.md`
  - `docs/features/providers.md`
  - `docs/features/prompts.md`
- [ ] 当前 `docs/modules/` 可作为旧模块文档归档候选；若保留，必须只作为 feature 文档的辅助索引。
- [x] 更新 `docs/testing/known-failures.md`，说明本阶段 known failures 暂缓处理的原因和重评条件。
- [x] 更新 `AGENTS.md` 当前重构方向，强调先架构和文档、再前端、再深测。

### Phase 3: Closed-loop Project Workflow Docs

- [x] 新增或重写项目生命周期流程文档：
  - `docs/workflows/project-lifecycle.md`
  - `docs/workflows/bugfix.md`
  - `docs/workflows/feature-development.md`
  - `docs/workflows/refactor-development.md`
  - `docs/workflows/documentation-maintenance.md`
- [x] 明确不同工作类型必须维护的文档：
  - bug：问题记录、根因、修复计划、测试记录、回归说明、完成摘要；
  - 新需求：头脑风暴、产品说明、方案、ADR、计划、测试、文档更新、验收记录；
  - 重构：目标/非目标、影响范围、迁移策略、兼容策略、测试矩阵、文档同步；
  - 前端：产品流程、信息架构、设计方案、API 依赖、验收截图/录屏、UI 测试计划。
- [x] 建立验收前记录：
  - 新增 `docs/tracking/pending-acceptance.md`；
  - 每个待验收项记录完成时间、提交号、影响范围、验证命令、待用户确认点。
- [x] 建立完成事项记录：
  - 新增 `docs/tracking/completed-items.md`；
  - 用户验收后写入摘要、关键提交、测试结果、后续事项。
- [x] 建立主动提醒规则：
  - 默认超过 24 小时或跨工作阶段仍未验收的事项，AI 在后续对话开始时提醒；
  - 如果用户明确延后，则记录新的提醒时间或阶段。
- [x] 建立规范回写规则：
  - 用户验收后，如果本次工作形成可复用约束，必须更新 `docs/standards/` 或 `AGENTS.md` 导航；
  - 如果只是一次性实施记录，归档到 completed，不污染规范。
- [x] 建立计划归档规则：
  - 活跃 `docs/plans/` 只保留当前待执行或正在执行计划；
  - 已完成、已废弃、已被新计划取代的 plan 移入 `docs/_archive/`；
  - `docs/plans/README.md` 或同类索引只列当前活跃计划，避免 AI 扫旧方案。

### Phase 4: Frontend Preparation Docs

- [ ] 更新产品文档：
  - `docs/product/overview.md`
  - `docs/product/workflows.md`
  - `docs/product/glossary.md`
- [x] 将前端设计工作登记为待办事项，后续单独展开讨论。
- [ ] 后续新增前端重做规划文档时，应明确：
  - 信息架构；
  - 页面模块；
  - API 依赖；
  - 状态展示；
  - 配置页面结构；
  - 任务列表和任务详情；
  - 源目录清理、回收站、Provider、提示词管理。
- [ ] 更新 API 文档，使前端开发能直接按接口和业务域理解。

### Phase 5: Testing Re-entry Plan

- [x] 暂不修复全部 known failures，只保留默认稳定回归 `pytest tests/`。
- [x] 为新 feature 迁移保留轻量测试：
  - feature smoke/import；
  - route table；
  - config view；
  - task lifecycle；
  - pipeline services。
- [ ] 前端完成后，重新规划 UI/E2E 测试结构。
- [x] 旧 known failures 到时按新业务契约重新分类：
  - delete obsolete test；
  - rewrite test；
  - fix implementation；
  - keep as environment-gated.

## Acceptance Criteria

- 新代码结构按 feature-first 组织，AI 能按业务功能定位代码。
- 新应用入口优先引用 feature 新结构，而不是旧技术目录。
- 每个新 feature 都有 smoke/import test 和文档入口。
- 配置文件、SQLite 数据模型、API、前端依赖在 feature 文档中有明确映射。
- 文档总入口、索引、AI map、architecture overview 都指向新架构。
- legacy 文档不会被误认为当前事实来源。
- 历史文档全部集中在 `docs/_archive/`，活跃文档区不混入旧事实来源。
- 仓库所有顶层目录和主要文件都有结构定位说明。
- 不属于新架构当前事实的旧文件已进入统一归档目录或被明确标注为兼容保留。
- `tests/` 目录只保留当前测试、明确 gated 测试或待重写测试；历史测试脚本已归档。
- 当前文档没有直接引用已归档文件内容。
- 有明确的待验收事项文档和完成事项文档。
- AI 后续对话能依据待验收文档提醒用户验收超时事项。
- 用户验收后，完成摘要进入 completed，相关规范完成回写。
- 已完成或被取代的 plan/方案不再留在活跃计划区。
- `pytest tests/` 仍作为默认稳定回归入口通过。
- known failures 不再阻塞架构和文档迁移，但有明确重评计划。
- 前端设计工作已登记为待办，但不在本计划中细化实施。

## Decision Rationale

继续深测的收益暂时低于成本。当前失败大多不是单纯实现 bug，而是旧契约、旧前端、环境依赖和架构迁移状态混杂。

先完成新架构和文档结构有三个好处：

- 前端重做有稳定依赖，不会边做边追旧接口认知。
- 后续测试可以围绕新业务契约重写，而不是修补旧测试。
- AI 后续进入项目时，默认读取的是新结构，不会在旧目录和旧文档中绕路。

## Constraints and Boundaries

- 不强制保留旧 public imports；是否保留只取决于新架构迁移成本和清晰度。
- 不改变 API 路径和响应格式。
- 不以历史数据兼容为约束；配置和数据库可以面向新产品重新设计，但必须同步文档和测试。
- 文件删除/覆盖仍必须走回收站安全规则。
- 文档和代码同阶段更新。
- deploy package workspace 仍是生成物，根源码为唯一事实来源。

## Risks

| 风险 | 影响 | 缓解 |
|------|------|------|
| feature 迁移产生循环 import | 中 | 每个 feature 增加 smoke/import tests |
| 文档过早声明尚未迁移的结构 | 中 | 文档标注 current / planned / compatibility |
| known failures 长期搁置 | 中 | 写入重评条件，前端完成后集中处理 |
| 旧 patch 路径失效 | 低 | 未上线产品不以旧 patch 路径为硬约束；旧测试可重写或归档 |
| 前端重做再次扩大范围 | 中 | 先写前端规划文档和 API 依赖清单 |
| 历史文档继续干扰 AI | 高 | 统一移入 `docs/_archive/`，活跃索引只指向当前事实 |
| 归档代码或测试导致可运行性下降 | 高 | 先做 inventory，再分批归档，每批跑默认回归 |
| 文档仍链接归档文件 | 中 | 归档后跑引用扫描，并更新当前事实文档 |
| 测试脚本归档后遗失有价值场景 | 中 | 先登记到 `docs/testing/test-inventory.md`，后续按新架构重写 |
| 用户验收事项遗漏 | 中 | 建立 pending acceptance 和主动提醒规则 |
| 完成经验没有沉淀为规范 | 中 | 验收后强制判断是否更新 standards 或 AGENTS 导航 |

## Assumptions

- 用户当前优先级是代码架构与文档结构，而不是短期清空 known failures。
- 前端将按新架构重做，旧 UI 测试不能作为最终验收基准。
- 旧 import 兼容层不是硬约束；如阻碍清晰架构，可以归档或删除。
- 当前默认稳定回归入口已经足够保护架构迁移的低层行为。
- 默认验收提醒阈值先按 24 小时处理；如用户后续指定其他周期，以用户指定为准。
- `docs/_archive/` 是唯一历史文档归档入口。
- 非文档文件可以使用仓库级 `_archive/` 作为统一归档入口；归档前先完成 inventory 和一次默认回归即可。
- 活跃 plan 区只用于当前待执行或正在执行工作。

## References

- `docs/_archive/2026-06-02-feature-first-reorg/README.md`
- `docs/decisions/0004-feature-first-architecture-restructure.md`
- `docs/testing/known-failures.md`
