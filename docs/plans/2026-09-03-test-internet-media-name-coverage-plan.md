---
title: "测试：互联网媒体命名场景覆盖与真实刮削验收"
type: plan
date: 2026-09-03
status: complete
confidence: high
requirement: REQ-20260903-234230
---

# 互联网媒体命名场景覆盖与真实刮削验收计划

以公开媒体生态命名规范构建可复现语料，验证并加固当前 TMDB 主导刮削链路，使安全可自动化的电影、电视剧场景达到至少 90% 自动成功率。

## Problem Statement

现有发布名解析已覆盖 GuessIt、中文季集、显式 Provider ID、NFO 和目录证据，但当前真实语料主要来自少量 fnOS 案例及组合技术标签。它尚未系统证明 Plex、Jellyfin、Sonarr、Radarr、Scene/P2P、动漫绝对集、日期节目、多集文件、光盘结构、多版本和多语言路径等常见生态能在产品真实匹配链路中稳定工作。只验证解析字段也不能证明最终 Provider 身份和自动刮削状态正确。

## Target End State

- 一套可审计的互联网来源场景目录，记录来源规范、场景族、路径、文件名、预期作品身份和自动化资格。
- 测试仅创建零字节占位文件、小型 NFO 与内存 Provider 数据，不下载或保存影视内容。
- 正向自动化场景的场景族通过率和样本通过率均不低于 90%，且 Provider ID、媒体类型、年份、季集均正确。
- 冲突 ID、错年、错类型、附加视频、无可信标题等安全负例 100% 不得错误 `AUTO_PASS`。
- 开发环境在可用 TMDB 凭据下完成全部正向与安全样本的实时 Provider 验证；网络验证与确定性回归分别报告。

## Scope and Non-Goals

包含远端同步、公开规范调研、fixture/测试执行器、解析与匹配的必要小范围修复、实时 TMDB 代表样本验证、回归和文档闭环。不访问盗版站点，不下载媒体，不复制大文件，不改入库/删除/覆盖/回收合同，不用片名白名单提升通过率，不降低冲突门禁，不要求所有非标准或本质歧义输入自动通过，不执行 fnOS/UAT/生产部署。

## Proposed Solution

1. 将公开规范转成“场景族 DSL”：作品事实与命名模板分离，按电影、剧集、路径结构、确定性 ID/NFO、语言/字符集和安全负例组织。
2. 使用相同 fixture 运行三层验证：`ReleaseIdentity` 结构解析、`build_identity_evidence` 路径证据、`MatchEngine` 完整身份裁决；正向样本必须正确 `AUTO_PASS`，不是只要搜到候选。
3. 本地确定性测试使用最小冻结 Provider 记录，实时验证使用当前开发配置的 `TMDbProvider`，结果输出为脱敏汇总，不落 API Key 或完整响应。
4. 仅修复跨作品通用语法或目录角色；每个修复先有失败用例，并保持 ADR-0024/0025 的人工确认边界。

## Phased Implementation

### Phase 1：同步与基线

- [x] T1 核对干净工作区、成功 fetch，并以 fast-forward 同步 `origin/main`；记录精确基线提交。
- [x] T2 运行现有发布名、身份解析、匹配与 Provider 专项，区分历史失败和新增失败。

退出条件：远端状态可信，基线测试结果可复核。

### Phase 2：语料与指标

- [x] T3 注册需求并补一页方案；把 Plex、Jellyfin、Servarr/Sonarr/Radarr、TRaSH 与 Kodi 官方/项目文档映射为场景族。
- [x] T4 新增互联网命名 fixture，覆盖独立/同目录电影、年份/ID、版本/剪辑、多段、BDMV/VIDEO_TS、标准剧集、日期节目、Specials、跨集、多段剧集、动漫绝对集、Scene/P2P、中文/繁中/日文/韩文、双语、标点重音、通用/技术/结构目录和 NFO。
- [x] T5 新增场景执行器和分层断言；按场景族与样本双口径输出通过率和失败分类，防止用大量同类排列稀释缺口。

退出条件：至少 30 个正向场景族、100 个展开正向样本及 15 个安全负例可重复执行。

### Phase 3：缺口修复与真实 Provider

- [x] T6 先运行新语料建立缺口表，再对通用解析/路径证据问题做最小修复；不得针对具体作品写白名单或放宽安全冲突门禁。
- [x] T7 检查开发配置的 TMDB 凭据可用性，对全部 129 个正向样本和 21 个安全负例运行真实 `MatchEngine + TMDbProvider`；记录正确身份、自动状态、失败原因和网络状态。
- [x] T8 对全部实时自动命中样本执行正式 Provider 元数据详情路径，确认最终 scrape result 的 Provider ID、类型、年份和季集保持一致。

退出条件：确定性正向场景族与样本通过率均 ≥90%，安全负例零误放；实时结果独立可解释。

### Phase 4：回归与闭环

- [x] T9 更新刮削标准、架构/功能说明、测试矩阵、需求看板和外部来源说明；登记待验收，用户确认后再归档计划。
- [x] T10 运行新增专项、相邻刮削回归、非 UI 全量、架构护栏、完整测试、Ruff、compileall、文档检查和 `git diff --check`。

退出条件：无本次新增回归失败，文档与代码事实一致。

## Test Plan

- 结构解析：标题、年份、季/集/范围、日期、版本、多段、显式 ID、技术标签、发布组。
- 路径证据：作品目录、来源根、Season/Specials、BDMV/VIDEO_TS、技术/下载目录、附加内容边界、NFO 继承。
- 完整匹配：冻结 Provider 对每个正向样本返回目标作品和干扰候选，断言正确 `AUTO_PASS`；模糊/冲突样本断言 `NEEDS_CONFIRM`。
- 真实 Provider：从开发配置读取 TMDB Key 但不输出，限速运行代表集；区分联网失败、Provider 无数据、解析失败和安全门禁。
- 正式刮削：代表样本从匹配结果进入 Provider details，验证结果字段，不执行文件复制或入库。
- 回归命令遵循 `AGENTS.md` 与 `docs/standards/testing.md`。

## Acceptance Criteria

- 正向场景族数量 ≥30、展开正向样本 ≥100、安全负例 ≥15；电影与电视剧均至少占正向场景族的 35%。
- 正向场景族自动正确率 ≥90%，正向样本自动正确率 ≥90%；“正确”同时要求 `AUTO_PASS` 和预期 Provider 身份/类型/年份/季集一致。
- 安全负例误 `AUTO_PASS` 数为 0；任何为达标而降低年份、类型、ID 冲突或候选差距保护的修改均拒绝。
- 实时 TMDB 代表样本在凭据与网络可用时完成；若外部服务不可用，必须标为 `NOT_RUN`/`FAIL`，不得用冻结数据冒充实时通过。
- 新语料测试、相邻刮削回归、非 UI、架构、完整测试及质量检查无本次新增失败。
- 最终报告分别给出：本地确定性测试、真实 TMDB、完整本地回归、fnOS/UAT/生产状态。

## Decision Rationale

按场景族和样本双计分，可避免 800 个技术标签排列掩盖某一种目录或集号语法完全不支持。冻结 Provider 使回归稳定，实时 TMDB 又能证明开发环境真实集成；二者不可互相替代。安全负例不纳入“自动成功率”分母，因为它们的产品正确结果本来就是人工确认，但必须单独以零误放验收。

## Constraints and Boundaries

- GuessIt 仍只是结构解析器，Provider 身份才是自动成功事实。
- 不确定结果在任何大文件复制前进入人工确认；本计划不触发复制、删除、覆盖或来源清理。
- fixture 只保留路径、文件名及最小作品身份，不保存版权媒体、密钥、Cookie 或完整第三方响应。
- 外部资料采用公开文档及其示例语法，Scene/P2P 样式使用匿名发布组和合成技术标签。

## Assumptions

| Assumption | Status | Evidence / Action |
|------------|--------|-------------------|
| 当前 checkout 可安全 fast-forward 同步 | 已验证 | fetch 成功；`HEAD` 与 `origin/main` 同为 `1ea11d325dbdbb9d5dd414a3fa6bb01cb78e5890`，ahead/behind 为 `0/0` |
| 开发配置包含可用 TMDB 凭据 | 已验证 | 实时验收连接 PASS；输出仅保留脱敏统计与失败路径 |
| `MatchEngine` 是自动身份裁决事实入口 | 已验证 | `metadata_scrape_flow` 接收其 selected candidate，ADR-0024/0025 定义此边界 |
| 零字节占位文件足以验证文件名与路径证据 | 已验证 | 当前身份测试使用 `Path.touch()`，解析阶段不读取媒体内容 |
| 公开命名规范可代表主流生态但不等于所有下载站输入 | 已验证 | 来源覆盖 Plex/Jellyfin/Servarr/TRaSH/Kodi，计划明确不宣称百分百 |

## Risk Analysis

- 实时 TMDB 受网络、限流或大陆连通性影响：限速、缓存本轮最小结果，并与确定性回归分开报告。
- 为追求 90% 导致误匹配：安全负例零误放是更高优先级门禁，未达标时保留人工确认并报告缺口。
- fixture 偏向规范化媒体库而非原始发布名：同时纳入 Scene/P2P、双语和动漫发布组语法，但不采集侵权站点。
- 大量参数化用例难以定位：失败输出场景族、路径、解析值、搜索词和候选裁决原因。
- 远端同步改变实现：T1 后重新读取相关差异，必要时更新计划而不回滚远端代码。

## Execution Results

- 语料：43 个正向场景族、129 个正向样本、21 个安全负例；电影和电视剧场景族均超过 35%。
- 真实 TMDB：124/129 正向样本正确自动完成（96.12%），40/43 场景族全样本通过（93.02%），21/21 安全负例未误放；连接、details 与最终 scrape result 链路 PASS。
- 保留人工确认：3 个 `VIDEO_TS/*.VOB` 分段、单一繁中 `寄生蟲.2019`、存在上下层季度语义冲突的 `地球脉动 第二季/第1季/第1集`。
- 工程回归：新增与相邻专项 100/100、完整测试 1108/1108、架构护栏 18/18、Ruff、compileall、前端脚本语法均 PASS。
- 文件安全：测试只创建并清理临时零字节文件与最小 NFO；未读取真实媒体、未复制、未入库、未删除。
- 环境边界：真实 TMDB 集成已运行；远端 CI、fnOS UAT 与生产均未运行。

## References

- [Plex movie naming](https://support.plex.tv/articles/naming-and-organizing-your-movie-media-files/)
- [Plex TV naming](https://support.plex.tv/articles/naming-and-organizing-your-tv-show-files/)
- [Jellyfin movie naming](https://jellyfin.org/docs/general/server/media/movies/)
- [Jellyfin TV naming](https://jellyfin.org/docs/general/server/media/shows/)
- [Sonarr media naming](https://wiki.servarr.com/sonarr/settings)
- [Radarr media naming](https://wiki.servarr.com/radarr/settings)
- [TRaSH Radarr naming](https://trash-guides.info/Radarr/Radarr-recommended-naming-scheme/)
- [TRaSH Sonarr naming](https://trash-guides.info/Sonarr/Sonarr-recommended-naming-scheme/)
- [Kodi movie naming](https://kodi.wiki/view/Naming_video_files/Movies)
- [ADR-0024](../decisions/0024-layered-release-name-recognition.md)
- [ADR-0025](../decisions/0025-deterministic-media-identity-resolution.md)
- [刮削匹配标准](../standards/scrape-matching.md)
