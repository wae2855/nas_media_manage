---
title: "重构：分层发布名识别与 fnOS 实例回归"
type: plan
date: 2026-09-03
status: complete
confidence: high
requirement: REQ-20260903-153000
---

# 分层发布名识别与 fnOS 实例回归计划

用成熟通用解析底座替换不断追加例外的识别方式，并用当前 fnOS 失败案例证明安全边界。

## Problem Statement

当前发布名解析会把正常英文片名片段识别成域名，也无法可靠处理中文数字季和多集范围。错误标题会造成无结果或不必要的人工确认；若将模糊候选过度自动化，还可能把大文件写入错误片库。

## Target End State

- 国际通用发布字段由固定版本 GuessIt 解析，中文层只做局部增强。
- 《极地重生》得到完整中英文候选，《北海鲸梦》五集使用纯剧名和正确季集。
- `.me` 正常片名不误删，真正广告域名仍可去除。
- TMDB 官方别名可作为可解释证据，但不能绕过年份和类型校验。
- 所有不确定结果在文件复制前进入人工确认。

## Scope and Non-Goals

本次包含解析、证据融合、TMDB 别名验证、依赖打包和自动化回归。不新增复杂的前端识别词配置，不修改维度映射、入库规则或目标片库安全边界，不处理已完成旧任务的数据迁移。

## Representative Proof Slice

先使以下两条通过，再扩展全部语料：

- `极地重生(蓝光特效中英双字幕).As.Far.As.My.Feet.Will.Carry.Me.2001.BD-1080p...`
- `北海鲸梦.第一季.2021.EP05.HD1080P...`，父目录为 `EP01-05`。

如果两者任一仍需要靠具体片名白名单，停止传播并重新调整解析层边界。

## Implementation Tasks

- [x] T1 固定 GuessIt 及传递依赖，验证 Python 3.12 与 fnOS 离线 wheelhouse。（依赖/打包）
- [x] T2 重构发布名解析为“中文规范化 + GuessIt + 保守归一化”，支持中文数字季、多集范围和组合技术标签。（scraping）
- [x] T3 调整目录证据：范围目录只提供剧名/季信息，单文件集号保持主证据。（scraping）
- [x] T4 增加 Provider 官方别名能力与受限自动通过规则，轨迹记录命中的别名。（providers/scraping）
- [x] T5 修正未匹配用户文案和 Provider 状态，不再显示“AI 不可用”。（scraping/tasks）
- [x] T6 扩展真实发布名、证据融合、匹配门禁和 fnOS 现有案例测试。（tests）
- [x] T7 同步架构、功能、匹配标准、测试矩阵和第三方依赖说明。（docs/deploy）
- [x] T8 运行专项、非 UI、架构、文档、lint 和编译检查；读取 fnOS 当前案例进行对照复核。（verification）

## Test Plan

- 单元：中文数字季、范围、`.me` 片名、强广告域名、圆括号技术说明、复合画质标签。
- Provider：官方别名命中、年份/类型冲突、别名接口失败保守降级、请求次数门禁。
- 集成：文件/目录证据收敛、剧集组目录、识别失败不进入复制。
- 回归：既有 `test_release_identity.py`、`test_identity_evidence.py`、匹配与正式刮削流程测试。
- 质量：非 UI 测试、架构护栏、Ruff、compileall、文档检查和 fnOS 打包依赖校验。

## Acceptance Criteria

- 《极地重生》候选包含完整 `极地重生` 与 `As Far As My Feet Will Carry Me`，年份 2001，技术说明不污染标题。
- 《北海鲸梦》EP01–EP05 均以 `北海鲸梦` 搜索，season=1，各自 episode 正确。
- `Stand.By.Me`、`Let.Me.In`、`Call.Me.By.Your.Name` 不被域名规则截断。
- `www.example.com` 等强广告证据仍被删除。
- 官方别名仅在同类型、同年、精确归一化命中时支持自动通过；接口失败或冲突进入确认。
- 回归测试无本次新增失败；fnOS 依赖可离线安装。

## Constraints and Rejection Criteria

- 禁止具体影片白名单和“唯一候选即自动通过”。
- 禁止在确认身份前复制、删除或覆盖文件。
- 禁止让目录名否决文件名的强精确证据。
- GuessIt 版本必须固定，许可证必须随发布物说明。
- 如果引入后现有正确样本大面积退化，保留现有解析器作为受控回退并停止切换默认路径。

## Assumptions

| Assumption | Status | Evidence |
|------------|--------|----------|
| GuessIt 支持 Python 3.12 且为纯 Python 依赖 | 已验证 | 4.4.0 及传递依赖均成功下载 Python 3.12 `none-any` wheel |
| TMDB 为电影和剧集提供官方别名接口 | 已验证 | TMDB v3 alternative_titles 端点及现有 Provider 客户端扩展点 |
| 当前 fnOS 问题主要来自解析而非网络 | 已验证 | 0.3.26 健康检查正常；中英文纯标题手动搜索命中正确 ID |
| 旧任务无需迁移 | 已确认 | 产品未正式发布，按新任务模型执行 |

## Risk Analysis

- 第三方解析结果改变：固定版本并建立金丝雀语料，升级必须显式评审。
- 中文语料覆盖不足：中文层保持独立，采用语法规则而非影片白名单。
- 别名导致误放行：同时要求类型、年份和标准化精确命中；失败关闭。
- Provider 请求增加：仅唯一模糊候选触发，单次匹配缓存。
- 脏工作区重叠：只修改本计划列出的文件，不回滚或整理用户已有变更。

## References

- [ADR-0024](../decisions/0024-layered-release-name-recognition.md)
- [刮削匹配规范](../standards/scrape-matching.md)
- GuessIt、Sonarr、Jellyfin/Emby Naming、MoviePilot 的公开实现与行为说明。
