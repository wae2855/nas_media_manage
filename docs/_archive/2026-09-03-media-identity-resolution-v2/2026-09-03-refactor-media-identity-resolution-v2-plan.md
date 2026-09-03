---
title: "重构：媒体身份解析 v2"
type: plan
date: 2026-09-03
status: complete
confidence: high
requirement: REQ-20260903-193839
---

# 媒体身份解析 v2 实施计划

## Problem Statement

系统已经能拆解复杂发布名，但丢弃显式 Provider ID、忽略 NFO 身份、目录祖先遍历提前停止，且文本候选缺少多证据评分和差距保护。结果是确定性线索被降级为标题搜索，相近作品存在不必要确认或误匹配风险。

## Target End State

文件名与 NFO 中的 Provider ID 优先被确定性解析；文件、目录和 Provider 证据来源可追踪；标题归一化和候选评分一致；任何 ID 冲突或近似候选歧义都在复制前进入用户确认。现有两级任务状态、手动确认、维度映射和文件安全边界不变。

## Scope and Non-Goals

本计划修改 scraping/providers 及其文档测试。不会新增 LLM、片库扫描或历史任务迁移，不改变目标片库、来源删除、字幕和文件传输逻辑。

## Implementation Tasks

- [x] T1 扩展 `ReleaseIdentity` 与 `CleanResult.release_identity`，保留 GuessIt Provider ID 和少量稳定辅助字段。（scraping）
- [x] T2 新增边界受控的 NFO 身份读取器；支持 `movie.nfo`、`tvshow.nfo`、视频同名及合理同名 NFO。（scraping）
- [x] T3 修正目录祖先遍历，连续跳过结构/通用/技术目录直到来源根或深度上限。（scraping）
- [x] T4 新增 `TitleNormalizer`，让 TitleMatcher 和候选融合共用严格/宽松归一化。（scraping）
- [x] T5 扩展 Provider 最小 ID 接口；TMDB 实现原生 ID 详情和 IMDb/TVDB `/find`。（providers）
- [x] T6 在 MatchEngine 前置确定性身份解析，补齐类型/年份冲突、API 降级和可解释轨迹。（scraping）
- [x] T7 将文本候选升级为多特征排序与第一/第二差距保护，热度仅作平局裁决。（scraping）
- [x] T8 增加真实发布名 fixture、NFO/目录/ID/冲突/相近候选/异常测试，并保留 800+ 组合回归。（tests）
- [x] T9 同步 scraping/provider/测试文档、需求台账和 ADR 链接。（docs）
- [x] T10 执行专项、非 UI、架构、全量、lint、编译和文档检查；计划归档并记录真实结果。（verification）

## Test Plan

- 单元：GuessIt 三类 ID、NFO XML 变体、NFO 大小/损坏/越界、目录连续跳过、Unicode/重音/标点归一化。
- Provider：TMDB 原生 ID、IMDb/TVDB find、电影/剧集结果转换、无结果与网络异常。
- 匹配：ID 自动通过、年份/类型冲突、文件 ID 高于 NFO、NFO 高于标题、相近候选差距不足、热度不得覆盖业务证据。
- 语料：按电影/剧集/BDMV/中文发布名/多语言/显式 ID/NFO/冲突族组织 YAML fixture。
- 集成：正式 scrape 仍获取同一 selected candidate，身份轨迹可序列化且审核状态不变。

## Acceptance Criteria

- 三类显式 ID 和 NFO ID 均有自动化证据；确定性查找结果通过类型/年份校验。
- `权力的游戏/downloads/Season 01/S01E01.mkv` 与 BDMV 示例均选到正确目录证据。
- 严格/宽松标题归一化行为有固定契约，TitleMatcher 公共方法保持兼容。
- 相近候选没有强证据时明确显示第一、第二名及差距并进入 `NEEDS_CONFIRM`。
- Provider API 异常不会中断任务；轨迹说明降级原因。
- 指定专项、非 UI、架构、全量、Ruff、compileall 和文档检查全部通过。

## Risks and Controls

- NFO 不可信或损坏：限制路径、候选名与文件大小；只读取身份字段；解析失败保守忽略并留痕。
- TVDB 对电影不支持：Provider 根据官方能力只接纳可返回的媒体类型，无结果进入标题流程。
- ID 与文件名冲突：不让 ID 无条件覆盖明确年份/类型，冲突必须确认。
- 评分复杂化：特征保持少量、可解释、可单测，不开放用户配置魔法阈值。
- 回归范围大：先写小切片测试，再运行全部匹配与正式流程，最后全量。

## Required Verification Commands

```bash
python -m pytest tests/test_release_identity.py tests/test_identity_evidence.py tests/test_title_matcher.py tests/test_match_engine.py tests/test_feature_providers.py tests/test_scrape_provider_first_e2e.py
python -m pytest tests/ --ignore=tests/test_*_ui.py --ignore=tests/test_frontend_*.py --ignore=tests/test_scrape_ui.py
python -m pytest tests/test_architecture_guards.py
python -m pytest tests/
PYTHONPYCACHEPREFIX=/private/tmp/nas_media_manage_pycache python -m compileall -q media_importer tests
.venv/bin/ruff check <本次改动 Python 文件>
python scripts/check_docs.py
```

## References

- [方案](../../proposals/2026-09-03-media-identity-resolution-v2.md)
- [ADR-0025](../../decisions/0025-deterministic-media-identity-resolution.md)
- [ADR-0024](../../decisions/0024-layered-release-name-recognition.md)

## Completion Evidence

- 专项识别、Provider、正式刮削流程与解释性 UI 合同：103 passed。
- 非 UI 回归：981 passed、46 skipped（项目显式门禁）；全量回归（含真实 Chromium）：1072 passed。
- 架构护栏：18 passed；Ruff、compileall、文档断链检查均通过。
- 真实 TMDB 凭据调用与 fnOS 真机验收未在本地执行，保留为交付后验收边界。
