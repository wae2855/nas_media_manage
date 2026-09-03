---
title: "修复：媒体身份解析 v2 收尾加固"
type: plan
date: 2026-09-03
status: completed
confidence: high
requirement: REQ-20260903-193839
---

# 媒体身份解析 v2 收尾加固计划

对已落地的确定性身份管线补齐 NFO 继承范围、episode scope、目录连续上溯、多标题完整裁决与 Latin-only 重音折叠。

## Problem Statement

当前作品级 NFO 可能越过 Extras 等附加内容边界；episode NFO ID 可能被误当作 series ID；技术目录与无法形成可信标题的未知目录会中断祖先查找；多标题文件可能在第一个精确查询后提前通过；宽松归一化会删除所有文字体系的 combining mark。这些问题会造成强身份证据误用或候选未完整收集。

## Target End State

- 附加内容只读取明确属于当前文件的同名 NFO，不继承作品级 NFO。
- Season、BDMV 等正常结构仍可继承 movie/tvshow NFO。
- NFO 显式区分 movie、series、episode、unknown；episode ID 只留痕，不作为 series ID 查询。
- structural、generic、technical 目录连续跳过；未知目录清洗不可信时继续上溯。
- 同一文件的全部标题候选完成强匹配收集后，才判断唯一或冲突。
- 重音折叠只作用于 Latin 基字符，日文浊音/半浊音保持不同。

## Scope and Non-Goals

只修改 scraping 身份识别、测试与现有文档。不实现 episode→series Provider 查询，不改变 GuessIt、Provider 接口、任务状态、文件传输/删除/覆盖/回收，不发版、不改版本号、不执行真实 TMDB 或 fnOS 验收。

## Proposed Solution

1. 在 NFO 模块定义目录角色与 `identity_scope`，候选生成时执行 supplementary inheritance boundary。
2. 身份证据保留 NFO scope；确定性解析过滤 episode-scope ID 并记录忽略原因。
3. 目录证据使用四类 helper，并在清洗后无可信标题时继续循环。
4. Tier 1 先聚合同一 file identity 的全部精确候选，再按唯一/同一作品收敛/冲突裁决；现有 fuzzy scoring 保持不变。
5. TitleNormalizer 按 Unicode Latin script 基字符有选择地移除 combining mark。

## Implementation Tasks

- [x] T1 写入七类失败回归，固定 NFO 边界、scope、目录、多标题和 Unicode 契约。
- [x] T2 实现 supplementary/structural/generic/technical 分类与 NFO 继承边界。
- [x] T3 增加 NFO identity scope，并禁止 episode ID 进入 series 确定性查询。
- [x] T4 修正目录清洗失败后的连续上溯。
- [x] T5 移除多标题第一次 exact 即返回，完整收集后统一裁决。
- [x] T6 将 loose accent folding 限制为 Latin 字符。
- [x] T7 更新 ADR-0025、scraping 架构/规范、测试矩阵和需求验收记录。
- [x] T8 执行专项、非 UI、架构、全量、Ruff、compileall、docs、diff check，并归档计划。

## Acceptance Criteria

- 用户给出的七类回归全部通过，且原 Media Identity Resolution v2 测试无退化。
- 附加内容和 episode NFO 不会触发错误确定性 AUTO_PASS。
- 正常 Season/BDMV 继承、技术目录上溯与多标题同作品收敛仍可 AUTO_PASS。
- 全量测试和项目质量门禁全部通过。

## Decision Rationale

NFO 边界在候选生成阶段阻断最安全，因为下游不会接触到越界强 ID；scope 作为独立字段比从 `media_type_hint=tv` 猜 episode 更可解释。多标题裁决继续复用现有 candidate aggregation，避免重写 scoring。目录分类用小型集合/规则 helper，避免扩大单一正则。

## Assumptions

| Assumption | Status | Evidence |
|------------|--------|----------|
| episode NFO 当前没有安全的 episode→series Provider 能力 | Verified | Provider 仅提供原生作品 ID 与外部 ID 查询 |
| Season/BDMV 属于可继承作品身份的结构路径 | Verified | 现有身份测试和 ADR-0025 行为 |
| supplementary 目录内同名 NFO 明确属于当前文件 | Verified | 用户冻结的本轮边界 |
| 无需新增第三方 Unicode 依赖 | Verified | `unicodedata` 可识别 combining mark 与 Latin 基字符 |

## Risks and Controls

- 附加目录别名漏识别：仅补常见 Jellyfin/Kodi/Plex 名称，保持独立集合并用测试扩展。
- 目录“可信标题”判断过严或过松：复用现有 cleaner 和弱身份门禁，不引入新语义猜测。
- 多标题改造改变旧自动通过：保留单候选和同作品收敛路径，专项后必须跑完整回归。
- episode ID 被静默丢失：保留在 `nfo_identities` 与 `ignored_nfo` 解释信息中。

## References

- [ADR-0025](../../decisions/0025-deterministic-media-identity-resolution.md)
- [Scraping feature](../../features/scraping.md)
- [Scraping architecture](../../architecture/scraping.md)
- [原实施记录](../2026-09-03-media-identity-resolution-v2/2026-09-03-refactor-media-identity-resolution-v2-plan.md)

## Execution Record

- 专项身份与匹配回归：71 passed。
- 非 UI 清单：989 passed, 46 skipped（需显式开关的集成/E2E）。
- 架构护栏：18 passed。
- 完整本地测试（含 Chromium UI）：1084 passed。
- Ruff、compileall、文档断链/行数/front-matter、`git diff --check` 均通过。
