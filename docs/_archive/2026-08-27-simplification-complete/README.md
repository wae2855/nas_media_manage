# 2026-08-27 简洁化完成批次归档

功能简洁化路线图（Phase 0-4）及全部关联方案已执行完毕，本批次归档防止 AI 读取到过时执行状态。事实已固化到 standards/（scrape-matching、ai-prompt-design、新增 frontend/backend 规范）与 ADR（0010）。

| 文件 | 类型 | 结果摘要 |
|------|------|----------|
| `2026-08-22-simplification-roadmap.md` | plan | Phase 0（死代码/兼容层/工具链）、Phase 1（Hermes+AI 刮削移除+维度兜底）、Phase 2（状态机重构）、Phase 3（配置面）、Phase 4（CSS/README/Ruff/fpk 0.2.0）全部完成；含 Phase 1 评审轮 9 项修复记录 |
| `2026-08-22-simplification-assessment.md` | proposal | 全项目评估：实测盘点+业务拍板（B1 只做减法/B2 功能取舍/B3 公开发布 fpk） |
| `2026-08-22-ai-surface-assessment.md` | proposal | AI 面 7 场景逐项评估（A1-D2 全部移除，仅留清理器 LLM）；维度兜底 A+B 方案设计 |
| `2026-08-23-state-machine-redesign.md` | proposal | 状态机三层收敛方案（S1 转换表/S2 断点续跑/S3 CAS/S4 矩阵），含 6 问题诊断 |
| `2026-08-27-frontend-copy-and-behavior-alignment.md` | proposal | 前端文案与行为同步（批 A-D）：品牌改「影音库智能整理」、两级匹配叙述、批量重试收敛 |
| `2026-06-03-frontend-cinema-theme-proposal.md` | proposal | cinema 主题提案（B1 决策 superseded：现状够用只做减法） |

对应需求：REQ-20260822-000003（路线图执行）、REQ-20260822-000004（状态机）均已关闭，见 tracking/completed-items.md。
