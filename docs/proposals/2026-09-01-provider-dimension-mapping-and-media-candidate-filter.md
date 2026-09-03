---
title: "Provider 维度映射与媒体候选过滤"
type: proposal
date: 2026-09-01
status: approved
confidence: high
requirement: REQ-20260901-233114
---

# Provider 维度映射与媒体候选过滤提案

## 问题

扫描器只凭视频扩展名创建任务，fnOS 真实目录中的推广小视频也会被当作电影。现有垃圾视频阈值位于任务创建后的源清理器，无法阻止广告任务；若只改扫描器，来源单元又会把被忽略视频当作“缺少任务”而永久等待。

维度侧已有 `provider_mappings` 数据字段，但限制级、类型、地区和语言仍包含不可编辑的 Python/前端硬编码。TMDB `adult=false`、美国 `R` 的《通天塔》被当前 `R → 17+ → 成人内容` 语义错误归类；维度页还因 `trustHtml` 未定义而整体无法渲染。

## 目标

- 明显广告视频在任务创建前被高可信忽略，模糊短片保守保留。
- 扫描、来源单元和源清理共用同一判定及冻结快照。
- Provider 原始结果通过用户可编辑映射落到本地维度值，出厂预置可恢复但不锁死。
- “观看分级”和“成人电影标记”分开，R 不再自动等于成人内容。
- 主配置页保持摘要化，复杂映射只在专用双端弹层中编辑和预览。

## 推荐方案

1. 增加无副作用 `MediaCandidatePolicy`，输出接受、推广忽略、小伴生视频忽略及证据；扫描和来源处理保存同一版本化判定。
2. 定义 Provider 能力描述与有限映射数据形状（scalar/set/country_value/media_type），业务原始值映射移入版本化预置数据。
3. `provider_mappings` 继续作为 DB 唯一事实源，API 提供校验、内容哈希并发保存、预览和恢复预置。
4. 映射引擎返回原始值、规则 ID、目标值和版本证据，自动/手动/重新整理入口共用。
5. 维度卡默认只显示摘要；点击“编辑映射”打开国家/数据项分组编辑弹层。手机改为全屏纵向卡片，不展示横向表格。
6. 保留 `restricted_level` 内部键并改称“观看分级”；新增可选 `content_sensitivity`。旧 17+ 片库规则提示人工复核，不自动修改片库。

## 影响面

- 后端：scraping/providers/source_files/source_cleaning/import_flow/configuration。
- 数据/API：维度映射 v2 合同、预置迁移、扫描摘要、配置检查。
- 前端：维度卡、映射弹层、文件来源高级折叠项、移动端。
- 安全：来源快照和处置门禁不放宽；目标片库只新增边界不变。
- 测试：映射 golden、迁移/API/UI、广告/短片反例、来源单元、fnOS 真实目录。

## 备选方案

- 只加大小阈值：误伤短片且破坏来源单元覆盖，否决。
- 只加广告正则：站点变化快、误伤风险高，否决。
- 前端直接编辑 JSON：复杂且不可在移动端可靠使用，否决。
- 每个维度单独写映射逻辑：继续制造保存和语义漂移，否决。

## Links

- [实施计划](../plans/2026-09-01-feat-provider-dimension-mapping-and-media-candidate-filter-plan.md)
- [ADR-0020](../decisions/0020-provider-capabilities-and-editable-dimension-mappings.md)
- [需求看板](../tracking/requirements-board.md)
