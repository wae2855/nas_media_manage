# 互联网媒体路径与文件名覆盖验收

本页记录 `REQ-20260903-234230` 的可复现测试口径。它验证“能否安全自动识别并取得正确 TMDB 详情”，不下载电影或电视剧文件，也不把明确歧义输入计为应自动通过。

## 语料与来源

事实数据位于 `tests/fixtures/internet_media_name_cases.yaml`，测试只在临时目录创建零字节媒体占位和最小 NFO。Scene/P2P 形式采用匿名发布组和合成技术标签，不访问下载站。

公开语法来源：

- [Plex 电影命名](https://support.plex.tv/articles/naming-and-organizing-your-movie-media-files/)：作品目录、年份、Provider ID、版本与多段文件。
- [Plex 剧集命名](https://support.plex.tv/articles/naming-and-organizing-your-tv-show-files/)：`SxxEyy`、日期集、Specials、多集与分段。
- [Jellyfin 电影](https://jellyfin.org/docs/general/server/media/movies/) 与 [Jellyfin 剧集](https://jellyfin.org/docs/general/server/media/shows/)：方括号 ID、多版本、BDMV/VIDEO_TS 和季度目录。
- [Sonarr](https://wiki.servarr.com/sonarr/settings)、[Radarr](https://wiki.servarr.com/radarr/settings)、[TRaSH Sonarr](https://trash-guides.info/Sonarr/Sonarr-recommended-naming-scheme/) 与 [TRaSH Radarr](https://trash-guides.info/Radarr/Radarr-recommended-naming-scheme/)：发布组、画质/来源/编码、动漫绝对集和标准化路径。
- [Kodi 电影命名](https://kodi.wiki/view/Naming_video_files/Movies)：作品目录、光盘结构和堆叠文件。
- 项目 ADR-0024/0025：中文季集、多语言发布名、显式 ID、NFO 和目录证据安全边界。

当前正向集包含 43 个场景族、129 个展开样本；电影和电视剧场景族均超过 35%。安全集包含 21 个错年、错类型、冲突 ID、同名同年、无年份同名剧、附加视频和弱标题样本。

## 成功定义

正向样本必须同时满足：

1. `MatchEngine` 返回 `AUTO_PASS`。
2. Provider ID、媒体类型和年份与预期作品一致。
3. fixture 声明季/集时，解析证据和最终 scrape result 均一致。
4. 实时层成功读取该候选的 TMDB details；不能用搜索命中冒充完整刮削。

门槛同时按两个口径计算：场景族中全部样本正确才算该族通过，且场景族通过率与样本通过率均须至少 90%。安全负例不进入正向分母，但必须 100% 不得 `AUTO_PASS`。

## 2026-09-04 开发环境结果

测试基于已与 `origin/main` 对齐的 `1ea11d3` 工作树执行。开发配置中的 TMDB 凭据只做存在性与连通性检查，报告不包含密钥或完整响应。

| 层级 | 结果 | 说明 |
|------|------|------|
| 冻结 Provider 回归 | PASS | 43 个场景族、129 个正向样本满足双 90% 门槛；21/21 安全负例未误放 |
| 真实 TMDB 匹配 + details + scrape result | PASS | 124/129 样本（96.12%）；40/43 场景族（93.02%）；21/21 安全负例；连接 PASS |
| 文件副作用 | PASS | 仅创建并自动清理临时零字节文件/NFO；未扫描真实媒体、未复制、未入库、未删除 |

实时脱敏明细由以下命令生成；报告路径可自行指定：

```bash
PYTHONPATH="${PWD}" .venv/bin/python scripts/validate_internet_media_names.py \
  --output /private/tmp/nas-media-name-live-report.json \
  --minimum-rate 0.90
```

## 保留缺口

以下 5 个实时样本保持人工确认，未通过降低门禁强行提升：

- `VIDEO_TS/*.VOB` 三个样本：当前扫描/任务模型没有把 DVD 分段聚合为一部影片；直接接纳 `.vob` 会把多个 VTS 段误建为多部电影任务。
- 单一繁中标题 `寄生蟲.2019`：当前 TMDB 官方标题/translation 未给出同一严格别名，候选差距不足；带英文标题的同族另外两个样本可自动通过。
- `地球脉动 第二季/第1季/第1集`：目录中的“第二季”既可能是作品标题的一部分，也可能是季度标记，与下层“第1季”存在语义歧义。

同名同年 CODA/Oppenheimer、无年份 One Piece/Band of Brothers/Frieren 已显式放入安全负例；用户补充 Provider ID 或作品年份后可进入正向自动流程。

## 回归规则

- 默认 CI 跑 `tests/test_internet_media_name_corpus.py`，使用冻结 Provider，避免网络和 TMDB 数据漂移。
- 实时脚本是发布前或匹配行为变更后的开发环境验收，不进入默认 CI。
- 新增大量后缀排列不能替代新场景族；每个新增族至少给一个正向样本或一个预期人工确认的安全样本。
- 不得通过具体片名白名单、热度直接选片、放宽 ID/年份/类型冲突来提高成功率。
