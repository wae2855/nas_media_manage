---
title: "互联网媒体命名场景覆盖与真实刮削验收"
type: proposal
date: 2026-09-03
status: approved
confidence: medium
requirement: REQ-20260903-234230
---

# 互联网媒体命名场景覆盖与真实刮削验收

## 问题（现状与痛点）

发布名与确定性身份解析已经完成两轮实现，但现有真实语料集中于少量 fnOS 失败案例，800+ 组合测试又主要变化画质和发布组，不能证明不同路径语法、剧集编号体系和媒体服务器命名规范都能走到正确 Provider 身份。产品需要一个不依赖影视文件、可量化且不会因网络波动失真的覆盖基线。

## 目标（可验证）

- 覆盖至少 30 个正向场景族、100 个展开样本和 15 个安全负例。
- 正向场景族、正向样本的正确 `AUTO_PASS` 率均达到 90%。
- 安全负例零误自动通过；真实 TMDB 与冻结 Provider 结果分开报告。
- 测试数据只包含路径、文件名和最小作品身份，不包含媒体内容或凭据。

## 方案概述（推荐方案 + 关键取舍）

fixture 将作品身份、来源规范和路径变体分开定义，同一份数据驱动三层验证：发布名结构、目录证据和完整 `MatchEngine` 裁决。冻结 Provider 只返回最小 `SearchItem`，用于稳定回归；开发环境另以 `TMDbProvider` 跑全部正向与安全样本及 details 路径。

来源按行为而不是网站数量分类：

| 来源 | 场景族 |
|------|--------|
| Plex | 电影独立目录/单文件、花括号 Provider ID、Edition、多段；标准/日期/Specials/多集/分段剧集 |
| Jellyfin | 方括号 Provider ID、多版本、3D、BDMV/VIDEO_TS、多段、字幕伴随；标准剧集目录 |
| Sonarr / Radarr / TRaSH | Scene/P2P 技术标签、原始发布名、标准/日期/动漫绝对集、多集样式、作品与剧集目录格式 |
| Kodi | 作品目录、Provider ID、光盘结构、文件堆叠 |
| 项目中文生态 | 简繁中、双语、日文/韩文、中文数字季集、网盘技术/广告目录 |

自动成功率同时按“场景族”和“展开样本”计算，避免大量同类技术后缀掩盖一个完整场景族不支持。明确冲突或无可靠身份的输入不纳入自动成功率分母，因为正确产品行为是人工确认；它们单独要求 100% 不误放。

## 影响面（代码/配置/API/测试/文档）

- scraping/providers：只允许修复跨作品通用语法和证据编排，不改变接口与安全状态。
- tests/fixtures：新增互联网命名语料、冻结 Provider 和双口径指标。
- scripts：新增可选实时 TMDB 验收入口，读取现有开发配置但永不输出密钥。
- docs：同步匹配标准、架构、测试矩阵、需求与来源依据。
- 配置/API/前端/文件流：不变。

## 备选方案（为何不选）

- 只扩大技术标签排列：不能证明路径、日期、多集、光盘和动漫编号能力。
- 把实时 TMDB 测试放入默认 CI：外部网络、配额和数据变化会制造不稳定失败。
- 为未通过作品增加别名白名单：不可扩展，也违反 ADR-0024。
- 为达到 90% 放宽年份/类型/候选差距门禁：误入库成本高于人工确认，拒绝。

## 公开资料

- [Plex movie naming](https://support.plex.tv/articles/naming-and-organizing-your-movie-media-files/)
- [Plex TV naming](https://support.plex.tv/articles/naming-and-organizing-your-tv-show-files/)
- [Jellyfin movies](https://jellyfin.org/docs/general/server/media/movies/)
- [Jellyfin shows](https://jellyfin.org/docs/general/server/media/shows/)
- [Sonarr settings](https://wiki.servarr.com/sonarr/settings)
- [Radarr settings](https://wiki.servarr.com/radarr/settings)
- [TRaSH Radarr naming](https://trash-guides.info/Radarr/Radarr-recommended-naming-scheme/)
- [TRaSH Sonarr naming](https://trash-guides.info/Sonarr/Sonarr-recommended-naming-scheme/)
- [Kodi movie naming](https://kodi.wiki/view/Naming_video_files/Movies)
