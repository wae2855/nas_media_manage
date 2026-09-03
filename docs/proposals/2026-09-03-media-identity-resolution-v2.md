---
title: "媒体身份解析 v2：显式 ID、NFO 与多证据决策"
type: proposal
date: 2026-09-03
status: approved
confidence: high
requirement: REQ-20260903-193839
---

# 媒体身份解析 v2：显式 ID、NFO 与多证据决策

## 问题

当前识别已经能把复杂发布名拆成标题、年份和季集，但仍把最终身份主要建立在标题搜索上：GuessIt 已识别出的 TMDB/IMDb/TVDB ID 被丢弃；本地 NFO 身份未读取；目录向上寻找遇到通用目录就提前停止；候选排序过度依赖精确标题和热度，缺少第一名与第二名差距保护。这会让已有确定性身份退化成模糊搜索，也会让相近作品被过早自动确认。

## 目标

- 显式 Provider ID 和 NFO ID 走确定性查找，查到后仍校验作品类型与明确年份。
- 文件、目录、NFO、Provider 别名分别保留来源，不把原始字符串拼接成新的噪声查询。
- 目录遍历跳过结构、通用和技术目录后继续向上，直到来源根或深度上限。
- 统一严格/宽松标题归一化，评分以身份与语义证据为主，热度只作最终并列排序。
- 第一候选与第二候选过近且无强证据时进入人工确认，并在轨迹中解释原因。
- 保持 TitleMatcher 对外接口、两级审核状态和“确认身份前不复制大文件”的安全边界。

## 推荐方案

在 `features/scraping` 内新增独立的 NFO 身份读取器和标题归一化器。`ReleaseIdentity` 保留 GuessIt 4.4.0 的 `tmdb_id`、`imdb_id`、`tvdb_id`；`alternative_title` 已被 GuessIt 稳定输出并同时保留为结构字段和标题候选，`date` 归一化为 `release_date`，`part`、`episode_title` 直接保留，`disc` 在 GuessIt 实际输出为 `cd` 时统一写入，避免另外发明解析规则。`identity_evidence` 只编排文件、目录与 NFO 证据。Provider 基类提供最小的 `get_by_provider_id` 与 `lookup_external_id` 扩展点，TMDB 适配器负责 `/movie|tv/{id}` 和 `/find/{external_id}`，通用匹配引擎不认识 TMDB URL 或响应字段。

匹配按“显式文件名 ID → NFO ID → 历史绑定（存在时）→ 文件标题/年份/季集 → 目录标题/年份 → Provider 别名 → 模糊候选”处理。确定性 ID 未命中或接口异常时允许继续标题流程，但必须留下轨迹；ID 查到却与明确年份或媒体类型严重冲突时直接进入人工确认。文本候选用多特征评分排序；候选差距保护比较双方证据形态，并由现有标题模糊边界推导所需差距，强别名或文件/目录收敛证据可以解除弱候选造成的机械拦截。

## 范围与非目标

包含发布名字段保留、NFO ID、目录祖先遍历、标题归一化、Provider ID 接口、证据评分、轨迹和真实语料测试。不新增 LLM 刮削，不做音译/NLP，不复制大型第三方解析器，不改变文件删除、覆盖、入库和来源处置安全合同，也不迁移未发布的旧任务。

## 影响面

- `features/scraping`：ReleaseIdentity、NFO、证据、匹配、归一化、轨迹。
- `features/providers`：通用 ID 查找接口及 TMDB 实现。
- `tests`：显式 ID、NFO、目录、相近候选、API 异常、真实语料。
- `docs`：刮削行为、架构、测试覆盖与需求台账。

## 验收摘要

- `[tmdbid-872585]` 直接查详情，IMDb/TVDB 通过 Provider 外部 ID 能力查找。
- `movie.nfo`、`tvshow.nfo`、同名 NFO 的 ID 可被使用；标题/年份只作校验辅助。
- `权力的游戏/downloads/Season 01/S01E01.mkv` 和 `Inception.2010/BDMV/STREAM/00001.m2ts` 找到正确意义目录。
- ID 类型/年份冲突、相近候选或 API 异常不会误自动通过。
- 800+ 组合测试继续保留，并增加按真实命名语法组织的 fixture。
