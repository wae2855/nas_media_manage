# Legacy webui 归档

本目录收纳已从运行时入口移除、但仍保留作历史对照的 webui 资源。

## legacy-config.html

状态：已从 `media_importer/webui/` 移出，运行期不再可访问（静态服务无法提供）。

历史背景：
- 旧版配置页面，包含已废弃的 confidence 公式配置面板（threshold / R 公式 /
  维度来源信任 / 置信度咨询 prompt）。
- 旧置信度公式体系（`final_confidence = T × R × data_gate`）的全部 UI 入口。

当前事实（ADR-0005）：
- 三级匹配策略（Provider 精确匹配 → AI 上下文辅助 → 用户确认）替代旧公式后，
  本页所有交互面板已被高级配置页面与三级匹配模拟页面取代。
- 仍需阅读历史公式细节时，仅供 ADR 追溯与方案对比参考，禁止作为现行功能入口。

若需重新启用，须先把页面内容整体迁移至新事实（match_level / match_concerns /
match_trace / confirm_reason / dim_sources），禁止再展示旧 T × R / data_gate /
置信度计算详情。