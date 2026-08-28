---
title: documentation-standards
type: standard
date: 2026-08-22
status: accepted
---

# Documentation Standards

## Directory Types

| 目录 | 职责 | 进入条件 |
|------|------|----------|
| `brainstorms/` | 探索期发散记录，问题空间分析 | 提案前的思考，允许粗糙 |
| `proposals/` | 待评审方案：问题、目标、方案概述、影响面 | 有明确要解决的问题 |
| `decisions/` | ADR 架构决策记录 | 架构级决策定案时 |
| `plans/` | 已批准且执行中的计划 | 需求已注册，方案已定（小任务可跳过 proposal） |
| `architecture/` | 当前技术事实（只写已实施的） | 实施完成时 |
| `features/` | 业务功能事实源：代码入口、扩展点、测试 | feature 落地时 |
| `standards/` | 长期规则 | 规则被确认后 |
| `testing/` | 测试策略与矩阵 | — |
| `workflows/` | 从想法到交付的闭环流程 | — |
| `product/` | 产品目标、术语、前端规划 | — |
| `tracking/` | 需求看板、验收台账、重估清单 | — |
| `_drafts/` | 未定稿草稿，不进索引 | 临时 |
| `_archive/` | 唯一归档地（含代码快照、旧测试） | 完成/废弃时 |

禁止：`docs/plans/_archive/` 等二级归档目录；归档内容一律进 `docs/_archive/<日期-主题>/`。

## Front-matter 规范

plans/proposals/brainstorms 必须以 YAML front-matter 开头：

```yaml
---
title: "短标题"
type: plan | proposal | brainstorm
date: YYYY-MM-DD
status: draft | approved | in-progress | complete | superseded
confidence: high | medium | low
requirement: REQ-YYYYMMDD-XXXXXX   # 可选，关联需求看板
---
```

ADR 使用自身模板（Context/Decision/Consequences/Alternatives/Links），状态：`Proposed | Accepted | Superseded | Deprecated`。

状态枚举全库统一为英文；历史 emoji 状态（📋🔄✅🗄️）已废弃，不再新增。

## Status Flow

```text
draft → approved → in-progress → complete（→ 归档 _archive/）
                ↘ superseded（→ 归档 _archive/，注明被谁替代）
```

## Size Rule

- 文档 ≤500 行；plans 建议 ≤300 行（任务分解型可放宽，但超 500 必须拆分）。
- proposal 一页纸 ≤150 行。

## Templates

### proposal 模板

```markdown
---
title: "xxx"
type: proposal
date: YYYY-MM-DD
status: draft
---
# 提案标题

## 问题（现状与痛点）
## 目标（可验证）
## 方案概述（推荐方案 + 关键取舍）
## 影响面（代码/配置/API/测试/文档）
## 备选方案（为何不选）
```

### plan 模板

```markdown
---
title: "xxx"
type: plan
date: YYYY-MM-DD
status: draft
requirement: REQ-xxx（可选）
---
# 计划标题

一行摘要。

## 任务分解
- [ ] 任务1（影响范围）
- [ ] 任务2

## 测试计划（必备，无此章节不得 approved）
- 单元/集成/UI 测试范围与验收命令

## 验收标准
- 可度量的完成条件

## 风险
```

## Required Sections for Feature Docs

- Code Entrypoints（代码入口表）
- Responsibility（职责）
- Extension Points（扩展点）
- Related Docs（关联文档）
- Tests（测试清单）

## 归档规则

- plan/proposal 完成或废弃后必须归档进 `docs/_archive/<日期-主题>/`，并在 `tracking/completed-items.md`（完成）或 `tracking/discarded-items.md`（废弃）留一行摘要。
- 归档时在归档目录写 README 说明归档原因与依据（git commit / tracking 记录），不信 plan 自身状态头。
- 当前文档不得引用归档内容作为事实；追溯历史链接必须注明「已归档」。
- 每次文档变更跑 `python scripts/check_docs.py`（断链/行数/front-matter 校验）。

## Documentation Lifecycle Rules

1. 新事实先落在 `architecture/` 或 `features/`，索引（`ai-map.md`）只做映射不复制事实。
2. 文档不包含可机械生成的全量清单（文件列表、测试列表），只写规则和例外。
3. 每类知识只在一处维护：安全规则细节只在 `standards/safety.md`；变更影响矩阵只在 `ai-map.md`；AGENTS.md 只留红线摘要。
