---
title: "停摆恢复待办重估清单"
type: standard
date: 2026-08-22
status: accepted
---

# Backlog Reevaluation（停摆恢复待办重估）

项目停摆一个月（2026-06-20 → 2026-08-22）后恢复，新方向为**功能简洁化**。本清单汇总存量待办处置结果。

处置原则（用户 2026-08-22 授权）：技术合理性决策由 AI 判定；**业务取舍（产品方向/功能重要性）须用户拍板**。

## 1. 业务决策项（待用户拍板，唯一保留的开放项）

| 项目 | 问题 | 选项 |
|------|------|------|
| [前端 cinema 重做计划](../_archive/2026-08-22-plans-cleanup/2026-06-03-frontend-cinema-redesign-plan.md)（展示层约完成 80%，功能接线未完） | 前端走哪个方向？ | A. 现状够用，冻结重做，简洁化评估时只做减法；B. 继续完成 cinema 重做（含功能接线）；C. 以简洁化目标重新定前端范围（可能砍页面/交互） |
| 功能取舍（REQ-20260822-000001 核心输入） | 当前哪些功能是你实际使用的核心？哪些可砍？ | 候选清单见 §2 |

## 2. 功能清单（REQ-20260822-000001 评估范围）

当前产品功能面（供业务拍板时参考，✎=待用户标注 留/简/砍）：

| 功能 | 入口 | 标注 |
|------|------|------|
| 目录扫描建任务（手动/定时） | CLI scan + 文件监控 | ✎ |
| 文件监控自动处理（FileWatcher） | monitor/ | ✎ |
| 手动批量/单文件处理 | API run_all / process_one | ✎ |
| AI 刮削（LLM 多模型 fallback） | features/scraping | ✎ |
| TMDB Provider 检索 | features/providers | ✎ |
| 三级匹配 + 待确认人工审核流 | standards/scrape-matching | ✎ |
| 模拟刮削预览（simulator/scrape preview） | api/scrape_preview_job | ✎ |
| 分类规则/路径规则/命名模板 | features/import_flow/services | ✎ |
| 同名去重策略 | dedup_rules | ✎ |
| 源目录清理器 | features/source_cleaning | ✎ |
| 回收站（安全删除/恢复） | features/recycle | ✎ |
| AI 配置界面（三区域+场景策略+提示词管理） | webui cinema-config | ✎ |
| 维度管理界面 | webui dimensions | ✎ |
| Hermes 飞书通知 | notify/ | ✎ |
| 运行指标/日志查看 | core/metrics + api | ✎ |

## 3. 已决策（技术，2026-08-22）

| 项目 | 决策 | 依据 |
|------|------|------|
| 停摆前 5 项待验收 | 批量豁免工程验收，关闭 | 代码稳定运行至今；前端全流程验收并入 §1 前端决策 |
| REQ-20260616-000001 待确认流程整治 | 关闭（已实施） | ADR-0009 落地 + 测试存在 |
| 系统性测试计划（5 阶段） | superseded 归档 | 测试数据文件已删除、从未执行；测试策略由简洁化评估重新定义 |
| spec-code-mismatch-review 草稿 | 归档 | 全部结论已被 06-18 主计划消费执行完毕；前台流程测试优先级表转记 §4 |
| file-flow-cartesian-product 草稿 | 冻结保留 | 测试设计矩阵，价值取决于简洁化后的测试策略 |
| scraper/ compat 层、storage/ 等 legacy wrapper | 纳入简洁化执行清单（删除候选） | 迁移完成已一个周期 |
| pyproject.toml + Ruff/Prettier 落地 | 纳入简洁化第一阶段工程项 | coding.md 已定目标态 |

## 4. 转记：前台流程测试优先级（源自已归档复核文档，供评估参考）

P0：首页指标卡→任务筛选；任务详情→待确认编辑→预览→确认入库；FAILED/SKIPPED/CANCELLED→重试/重新投入。
P1：AI 配置三区域+提示词保存；Provider 测试/搜索；回收站恢复/删除。

## 4.5 业务拍板结果（2026-08-22）

- B1 前端：现状够用只做减法 → cinema 重做计划 superseded 归档。
- B2 功能：保留 watcher/源清理器/模拟器/维度界面/手动处理；移除 Hermes 整链路、AI 刮削（ADR-0010）；AI 配置收缩为 LLM 连接+清理器提示词；新增状态机重构需求（REQ-20260822-000004）。
- B3 场景：公开发布 fpk。
- 授权系统：未来 Draft（REQ-20260822-000005）。
- 全部结论已并入评估提案与路线图，本清单使命完成，保留作记录。

## 5. 处置状态

- [x] 技术项决策完毕（§3）
- [x] 用户拍板前端方向（§4.5）
- [x] 用户标注功能留/简/砍（§4.5）
- [x] 拍板结果并入评估提案（REQ-20260822-000001 已完成），路线图启动（REQ-20260822-000003）
