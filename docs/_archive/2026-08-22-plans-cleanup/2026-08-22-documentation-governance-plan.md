---
title: "documentation governance and AI navigation convergence"
type: plan
date: 2026-08-22
status: complete
confidence: high
---

# 文档治理与 AI 导航收敛方案

- **Status**: complete（批 1-5 已完成，check_docs.py 通过，待用户验收）
- **Date**: 2026-08-22
- **Scope**: `docs/`、`AGENTS.md`、`README.md`、`scripts/`（仅新增文档检查脚本）
- **Non-goals**: 不改任何 `media_importer/` 业务代码；不重做前端；不引入新依赖
- **后续路线**: 本方案完成后，依次执行「待办重估」（见 §5）→「全项目功能简洁化方案与可行性评估」（已注册为 REQ-20260822-000001）

## 0. 背景约束：项目停摆一个月 + 功能简洁化新方向

- 项目自 2026-06-20 后停摆一个月，2026-08-22 恢复。
- 用户已明确新方向：**功能简洁化**。历史遗留待办需重新评估合理性，未来规划需重新制定。
- 本方案是恢复工作的第一步：先把文档治理干净，为全项目评估提供可信的事实基础。
- **文档状态与实际进度脱节的实锤**：`tracking/pending-acceptance.md` 记录清理迁移主计划 Phase 1-5 已完成（最新 commit `b8f6ccc` 为 Phase 6 收尾），但对应两个主计划（2026-06-18 两个 plan）状态仍停在 `pending-review`。归档时必须以 git 历史和 tracking 记录为准，不能信 plan 文件自身状态头。

---

## 1. 现状诊断

### 1.1 问题清单

| # | 问题 | 证据 | 严重度 |
|---|------|------|--------|
| P1 | **73 处断链**（活跃文档内） | `AGENTS.md` 指向 2 个已归档 plan；根 `README.md` 指向不存在的 `docs/07-hermes-integration-guide.md`；`INDEX.md` 引用 6 个已归档 plan | P0 |
| P2 | **索引漂移**：test-inventory.md 只列 26 个测试，实际 76 个 | `ls tests/` vs 文档 | P0 |
| P3 | **ADR 编号混乱**：缺 0006；两个 0007（information-responsibility-split 与 confirm-workflow-preview-vs-import-split） | `docs/decisions/` | P0 |
| P4 | **plans 目录膨胀**：26 个文件，大部分已完成未归档；6 个 handoff-prompt（会话产物）混入；状态标记格式 6 种以上（`status: in_progress`/`pending`/`approved`/`ready-for-execution`/`✅ 已实施`/无标记） | `docs/plans/` | P1 |
| P5 | **导航四入口重叠**：AGENTS.md / docs/README.md / INDEX.md / ai-map.md 职责交叉，Change Impact 表在 AGENTS.md 与 INDEX.md 双份维护 | 对比四个文件 | P1 |
| P6 | **目录职责不清**：`design/`(1文件956行)、`brainstorms/`(1)、`_drafts/`(3) 与 `proposals/` 边界模糊；`documentation.md` 的 Document Types 列表缺 6 个实际存在目录 | `docs/standards/documentation.md` | P1 |
| P7 | **归档位置分裂**：`docs/plans/_archive/` 与 `docs/_archive/` 两套并存，archive-policy.md 未提 plans 子归档 | 目录结构 | P1 |
| P8 | **工具链规范缺失**：无 pyproject.toml；lint/format/typecheck 命令未文档化（pyrightconfig.json 已存在但无人知晓）；用户全局规范要求 Ruff/Prettier，项目未落地 | 根目录 + AGENTS.md 自述 | P2 |
| P9 | **文档无机器可读元数据**：状态靠正文 grep，格式不统一，无法自动校验 | P4 证据 | P2 |
| P10 | **无防漂移机制**：断链、行数超限、索引失配只能靠人工发现 | 73 断链即证据 | P2 |

### 1.2 现有优点（保留）

- feature-first 文档分区方向正确（features/ 连接代码-配置-API-测试）。
- ai-map「任务 → 先读 → 代码 → 测试 → 同步」表格设计合理，是 AI 导航核心资产。
- 归档纪律好：历史内容基本已进 `_archive/`，只是收尾不干净。

---

## 2. 目标架构

### 2.1 渐进式披露四层模型

```text
L0  AGENTS.md            AI 会话入口：命令 + 安全红线 + 路由表（≤150行，不含细节）
L1  docs/README.md       人类入口：目录导航 + 阅读规则（一屏内）
L2  docs/ai-map.md       唯一任务导航：任务→代码→测试→文档映射 + 变更影响矩阵
                        （合并现 INDEX.md，模块视角与任务视角合一）
L3  具体事实文档          architecture/ features/ standards/ workflows/ testing/ decisions/
                        plans/ product/ tracking/ proposals/ brainstorms/
```

**核心原则**：
1. **单一事实源**：每类知识只在一处维护。Change Impact 矩阵只在 L2；安全规则细节只在 `standards/safety.md`；测试清单只在 testing/。AGENTS.md 只摘要红线并链接。
2. **文档不复制可机械生成的事实**：全量文件清单（测试、代码）不进文档，文档只写分类规则和例外清单，全量靠命令获取（`ls tests/`、`rg`）。
3. **每个文档有 front-matter 状态头**：机器可 grep，脚本可校验。
4. **导航入口唯一**：AI 读 AGENTS.md → ai-map.md 两跳即达事实文档。

### 2.2 目录职责定义（收敛后）

| 目录 | 职责 | 变化 |
|------|------|------|
| `docs/brainstorms/` | 探索期发散记录（pre-proposal） | 保留 |
| `docs/proposals/` | 待评审方案（含原 design/ 内容） | **合并 design/ → proposals/** |
| `docs/decisions/` | ADR 定案 | 修复编号 |
| `docs/plans/` | 已批准且执行中的计划（≤10个，front-matter 必填） | 大规模归档 |
| `docs/architecture/` | 当前技术事实 | 保留，收编 module-map 与 repository-structure 重叠部分 |
| `docs/features/` | 业务功能事实源 | 保留 |
| `docs/standards/` | 长期规则 | testing.md 明确只写规则 |
| `docs/testing/` | 测试现状与矩阵 | test-inventory 改为规则+例外制 |
| `docs/workflows/` | 生命周期流程 | 保留 |
| `docs/product/` | 产品与前端规划 | 保留 |
| `docs/tracking/` | 需求/验收台账 | 保留 |
| `docs/_drafts/` | 未定稿草稿（明确不进索引） | 清空（见 3.3） |
| `docs/_archive/` | 唯一归档地 | **合并 plans/_archive/ 进来** |

---

## 3. 执行方案（四批，可独立验收）

### 批 1：止血——断链与索引修复（P0）

| 动作 | 详情 |
|------|------|
| 1.1 修 AGENTS.md 断链 | 两个已归档 plan 链接改为 `decisions/0004` + 当前活跃计划 |
| 1.2 修根 README.md 断链 | `docs/07-hermes-integration-guide.md` → `docs/architecture/notification-monitoring.md` |
| 1.3 INDEX.md Current Plans 清理 | 已完成的 plan（three-tier-matching、ai-config 系列、scrape-info-split、confirm-workflow 等）移入归档，索引只留活跃项 |
| 1.4 ADR 重号修复 | `0007-confirm-workflow-preview-vs-import-split.md` → 改号为 `0009`（编号只增不重排，0006 留空并在 README 注明历史缺口）；全库引用同步更新 |
| 1.5 其他散断链 | `standards/info-architecture.md`、`features/scraping.md`、`architecture/overview.md` 等指向已归档 plan 的链接改为指向 ADR 或删除 |

### 批 2：结构收敛——plans 治理与目录合并（P1）

plans 治理不按文件自身状态头判断，**以 git log + tracking/pending-acceptance.md 交叉验证实际完成度**，每个 plan 归入三类：

- **A 类·已完成**：归档，摘要进 completed-items.md（约 18+ 个，含状态漂移的 2026-06-18 两个主计划）
- **B 类·未完成但方向存疑**：不归档、不执行，进入批 5 重估清单（如前端 cinema 重做系列——与"功能简洁化"方向可能冲突）
- **C 类·未完成且大概率仍有效**：保留在 plans/，front-matter 补齐后留待批 5 重估确认

| 动作 | 详情 |
|------|------|
| 2.1 定义 plan front-matter 模板 | `status: draft\|approved\|in-progress\|complete\|superseded` + `date` + `type: plan\|prompt`；写入 standards/documentation.md |
| 2.2 三分类处置 plans | 按上述 A/B/C 分类；A 类约 18+ 个 → `docs/_archive/2026-08-22-plans-cleanup/` |
| 2.3 归档 handoff-prompt 类 | 6 个 `*handoff*prompt*.md` 是会话产物，整体移入同上归档目录 |
| 2.4 合并 plans/_archive/ | 3 个文件移入 `docs/_archive/`，删除二级归档目录，archive-policy.md 补充说明 |
| 2.5 合并 design/ → proposals/ | `2026-06-13-ai-config-redesign.md` 改名进 proposals/，引用同步 |
| 2.6 处置 _drafts/ | scraper-migration-inventory（使命已完成）→ 归档；file-flow-cartesian-product、spec-code-mismatch-review → 进入批 5 重估清单（其结论影响简洁化评估，暂不处置） |
| 2.7 documentation.md 重写 | 补全全部目录类型定义、front-matter 规范、状态枚举、模板链接 |

### 批 3：导航重构——四入口收敛为两跳（P1）

| 动作 | 详情 |
|------|------|
| 3.1 合并 INDEX.md → ai-map.md | ai-map 增补 Module Map（模块→文档→测试）与 Change Impact 矩阵；INDEX.md 变为指向 ai-map 的 3 行占位或直接删除（**需用户选一**） |
| 3.2 重写 AGENTS.md | 只保留：环境命令、安全红线（≤8条）、L2 路由表（任务类型→读哪个文档）、测试入口；删除与 ai-map 重复的 Change Impact 表；目标 ≤150 行 |
| 3.3 重设计 test-inventory.md | 不再列全量 76 个文件；只写：测试分类规则、gated/UI 测试例外清单、与 known-failures 的关系；全量清单交给 `ls tests/` |
| 3.4 product/ 过期检查 | frontend-redesign-todo.md 若与现状冲突，标记 superseded 或归档 |
| 3.5 ai-map 内容核对 | 逐行核对「任务→代码路径」映射与实际文件存在性（防止文档指向已迁移代码） |

### 批 4：规范补全与防漂移机制（P2）

| 动作 | 详情 |
|------|------|
| 4.1 新增 `scripts/check_docs.py` | 断链检查（md 相对链接）+ 文档行数检查（>500 行告警）+ plan front-matter 校验 + ADR 编号连续性检查；零依赖纯 stdlib |
| 4.2 接入工作流 | AGENTS.md 命令区新增 `python scripts/check_docs.py`；写入 documentation-maintenance.md 作为文档变更必跑项 |
| 4.3 coding.md 补工具链章节 | 目标状态：Ruff（format+lint）、Prettier（css/js）、pyright（已有配置）；标注"引入 pyproject.toml 与依赖安装待用户批准，本方案不实施" |
| 4.4 状态标签统一 | 全库统一为英文枚举（draft/approved/in-progress/complete/superseded/archived），废弃 emoji 状态 |
| 4.5 workflows 更新 | documentation-maintenance.md、ai-agent-workflow.md 按新导航结构改写；feature-development.md 补"文档同步 checklist 引用 ai-map 变更影响矩阵" |

### 批 5：待办重估——停摆一个月后的存量清理（P1，新增）

文档治理的收尾动作，衔接后续「全项目简洁化评估」。

| 动作 | 详情 |
|------|------|
| 5.1 输出重估清单 | 新建 `docs/tracking/backlog-reevaluation.md`：汇总批 2 的 B/C 类 plans + requirements-board 存量需求 + pending-acceptance 5 项待验收 + product/frontend-redesign-todo + _drafts 2 项，逐项标注「与新方向关系 / 初步判断 / 处置建议」 |
| 5.2 重估 dimensions | 每项按三个问题判断：①功能简洁化目标下是否还需要？②若需要，实现方式是否要变？③依赖它的其他待办是什么？ |
| 5.3 requirements-board 清理 | 重估后：仍有效的需求更新状态保留；失效需求移入 discarded-items.md；新增依赖关系指向 REQ-20260822-000001 |
| 5.4 pending-acceptance 处置 | 5 项待验收事项逐项请用户验收或批量豁免（停摆一个月，多数已无验收意义）；验收后移入 completed-items.md 或随重估废弃 |
| 5.5 product/ 前端规划冻结标记 | frontend-redesign-todo.md、frontend-information-architecture.md 头部加 `status: frozen-pending-reevaluation`，避免 AI 在重估前引用其为目标 |

### 执行顺序与依赖

```text
批1（止血） → 批2（结构） → 批3（导航） → 批4（机制） → 批5（待办重估）
   │              │             │             │              │
   └──────────────┴─────────────┴── 每批结束跑 check_docs.py ──┴─ 重估清单交用户拍板
```

---

## 4. 验收标准

| 标准 | 度量 |
|------|------|
| 零断链 | `python scripts/check_docs.py` exit 0 |
| 导航两跳可达 | AGENTS.md → ai-map.md → 任一事实文档；AGENTS.md ≤150 行 |
| 活跃 plans 精简 | `docs/plans/*.md` ≤10 个且全部有合法 front-matter |
| 状态可机读 | 所有 plans/decisions 有统一 status 头 |
| 无重复维护点 | Change Impact 矩阵、安全规则摘要全库唯一 |
| 归档单一位置 | 不存在 `docs/plans/_archive/` |
| 索引不漂移 | 文档不再包含可机械生成的全量清单 |
| 状态与事实一致 | plan 状态头与 git log / tracking 记录交叉验证无矛盾 |
| 存量待办可追溯 | backlog-reevaluation.md 覆盖全部 B/C 类 plans + 看板存量 + 待验收 5 项 |

---

## 5. 文档治理之后的整体路线（本方案外，仅锚定顺序）

```text
阶段 A  文档治理（本方案，批 1-5）
阶段 B  全项目方案与可行性评估（REQ-20260822-000001，独立待办，已注册）
        ├─ 输入：治理后的干净文档 + 批 5 重估清单
        ├─ 内容：现状功能盘点 → 简洁化候选项（删/简/留）→ 可行性与风险评估 → 分期路线图
        └─ 产出：评估报告 + 新的项目整体规划（替代所有历史规划）
阶段 C  按新规划执行（功能删减/简化、前端重做决策、遗留技术债清理）
```

阶段 B 的要求：
- 以「功能简洁化」为第一目标重新审视产品边界，不受历史 plans/proposals 约束。
- 评估范围必须覆盖：后端 features 全集、前端 webui、API 面、配置面、测试面、deploy。
- 产出物是一份可执行的分期规划，经用户确认后成为唯一活跃规划，历史规划全部归档。

## 6. 风险与决策点（已拍板，2026-08-22 用户确认）

| # | 决策 | 结论 |
|---|------|------|
| D1 | INDEX.md 去留 | ✅ 合并进 ai-map.md 后删除 |
| D2 | ADR 0007 重号处理 | ✅ confirm-workflow 改号为 0009，全库更新引用 |
| D3 | handoff-prompt 归档 | ✅ 全部归档（会话产物，一次性） |
| D4 | 工具链引入 | ✅ 本轮只写规范与目标态，pyproject/ruff 安装下一轮单独做 |
| D5 | 前端系列计划处置 | ✅ 全部进入批 5 重估清单，暂不归档不执行 |

用户追加要求：
1. **后续开发需求必须有规范流程**：不过度复杂，但至少包含方案、需求、测试、计划文档（详见 §7 轻量开发流程规范）。
2. **已开发完成的文档必须归档**（批 2 A 类执行原则）。

---

## 7. 轻量开发流程规范（落地到 workflows/feature-development.md 等文档）

### 7.1 分级文档要求

| 变更级别 | 需求注册 | 方案 | ADR | 计划 | 测试计划 |
|----------|---------|------|-----|------|----------|
| 小改（bugfix、参数调整、文案） | ✅ 看板一行 | ❌ 可省 | ❌ | ❌ 可省（看板 Links 记录即可） | 必跑既有回归 |
| 中改（新功能点、行为变更） | ✅ | ✅ proposals/ 一页 | 仅涉架构时 | ✅ plans/ 含 front-matter | ✅ plan 内必备章节 |
| 大改（跨 feature、架构级） | ✅ | ✅ | ✅ | ✅ | ✅ 独立测试计划章节或文档 |

### 7.2 文档模板（批 2.7 写入 standards/documentation.md）

- **proposal**：问题 → 目标 → 方案概述 → 影响面 → 备选方案。一页纸，≤150 行。
- **plan**：front-matter（title/type/date/status/confidence）→ 一行摘要 → 任务分解（可勾选）→ 测试计划 → 验收标准。
- **需求看板行**：REQ-ID / 标题 / 类型 / 优先级 / Links（指向 proposal+plan）。

### 7.3 生命周期与归档

```text
注册（requirements-board）→ 方案（proposals/，可跳过）→ [ADR（架构级）]
  → 计划（plans/）→ 实施+测试 → 验收（pending-acceptance）
  → 归档（plan 移入 _archive，摘要进 completed-items；proposal 同步归档）
```

硬规则：
- plan 状态只有 5 个枚举：`draft | approved | in-progress | complete | superseded`。
- plan 完成后必须归档，不得长期滞留 plans/ 目录（check_docs.py 校验）。
- 每个 plan 必须有「测试计划」章节，无测试计划的 plan 不得标记 approved。

---

## 8. 涉及文件清单（预估）

- 修改：`AGENTS.md`、`README.md`、`docs/README.md`、`docs/ai-map.md`、`docs/INDEX.md`、`docs/standards/documentation.md`、`docs/standards/coding.md`、`docs/testing/test-inventory.md`、`docs/decisions/README.md` + ADR 改号、`docs/workflows/*` 3 个、约 10 个含断链的事实文档
- 移动归档：约 27 个文件（plans 24 + design 1 + drafts 2+）
- 新增：`scripts/check_docs.py`、`docs/tracking/backlog-reevaluation.md`、本方案对应的标准模板章节

## 9. 批后动作

方案确认后按批执行；批间可暂停回看。全部完成后：
1. 本文件标记 complete 并移入 tracking/pending-acceptance.md。
2. 批 5 重估清单交用户逐项拍板。
3. 启动 REQ-20260822-000001（全项目方案与可行性评估）。
