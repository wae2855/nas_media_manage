# 2026-08-22 Plans Cleanup Archive

项目停摆一个月（2026-06-20 → 2026-08-22）后恢复，用户确认新方向为功能简洁化。本目录归档 2026-06 至 2026-06-20 期间已完成或已失去时效的计划与草稿文档。

归档依据：git 历史（commit 记录）+ `docs/tracking/pending-acceptance.md` 交叉验证，不依赖 plan 文件自身状态头（存在状态漂移）。

## 归档清单

| 文件 | 归档原因 |
|------|----------|
| `2026-06-06-frontend-function-migration-handoff-prompt.md` | 会话 handoff 产物，功能迁移已完成 |
| `2026-06-08-frontend-bc-enhancement-plan.md` | 前端增强已完成（原 plans/_archive 移入） |
| `2026-06-09-task-status-stage-refactor.md` | Status+Stage 重构已完成验收（原 plans/_archive 移入） |
| `2026-06-06-frontend-function-migration-plan.md` | 前端功能迁移已完成（原 plans/_archive 移入） |
| `2026-06-10-dimension-enable-disable-fix.md` | 维度开关修复已完成，测试存在 |
| `2026-06-10-frontend-config-reading-simplification-plan.md` | 前端配置读取简化已完成 |
| `2026-06-13-ai-config-redesign-completion-plan.md` | AI 配置后端契约修复完成 |
| `2026-06-13-ai-config-redesign-implementation-plan.md` | AI 配置重设计已实施 |
| `2026-06-13-legacy-cleanup-acceptance-test-plan.md` | 验收已完成，报告见 tracking |
| `2026-06-13-refactor-remove-legacy-compatibility-plan.md` | 去兼容化已由 06-18 主计划完成 |
| `2026-06-14-refactor-file-split-plan.md` | 文件拆分已完成 |
| `2026-06-14-simulator-sourcecleaner-taskcard-scrape-fixes.md` | 五项修复已完成（对应 fix commits） |
| `2026-06-14-tier2-ai-context-match-redesign.md` | Tier2 AI 上下文匹配已实施 |
| `2026-06-15-ai-config-restructure-plan.md` | 三区域改造完成，627 tests pass |
| `2026-06-16-behavior-normalization-fix.md` | 行为规范化修复已完成 |
| `2026-06-16-complete-handoff-prompt.md` | 会话 handoff 产物 |
| `2026-06-16-confirm-workflow-overhaul-plan.md` | 待确认流程整治已实施（ADR-0009） |
| `2026-06-16-development-handoff-prompt.md` | 会话 handoff 产物 |
| `2026-06-16-fix-field-propagation-prompt.md` | 字段透传修复已完成 |
| `2026-06-16-multi-match-fix.md` | 多匹配规则已改 NEEDS_CONFIRM（dbf6e74） |
| `2026-06-16-optimization-items-plan.md` | 优化项已随后续修复完成 |
| `2026-06-16-p1-p2-handoff-prompt.md` | 会话 handoff 产物 |
| `2026-06-16-scrape-info-responsibility-split-plan.md` | 信息职责拆分完成，632 tests（ADR-0007） |
| `2026-06-16-user-prompt-management-handoff.md` | 会话 handoff 产物 |
| `2026-06-16-user-prompt-management-plan.md` | user_prompt 统一管理已实施（028a7c6） |
| `2026-06-18-refactor-cleanup-and-migration-sequencing-plan.md` | 清理迁移主计划 Phase 1-6 完成（b8f6ccc） |
| `2026-06-18-refactor-scraper-feature-first-migration-plan.md` | scraper 迁移 S-Phase 1-5 完成（ADR-0008 落地） |
| `2026-06-19-scraper-migration-inventory.md` | 迁移清单使命已完成（原 _drafts 移入） |
| `2026-06-18-spec-code-mismatch-review.md` | 复核结论已全部被 06-18 主计划消费执行完毕（原 _drafts 移入）；其 §4.2 前台流程测试优先级表转记入 backlog-reevaluation.md §5 |
| `2026-06-10-test-plan-systematic.md` | superseded：引用的测试数据文件已删除且从未执行；测试策略由 REQ-20260822-000001 重新定义 |
| `2026-08-22-documentation-governance-plan.md` | 文档治理方案批 1-5 执行完毕（2026-08-22），D1-D5 决策记录与轻量流程已固化到 standards/workflows；治理效果经新会话模拟自验 |

## 自验记录（2026-08-22）

新会话模拟导航自验 + 机械化路径校验发现并修复 **11 处文档-代码漂移**（文档描述的路径已随 2026-06 清理删除，文档未同步）：
`media_importer/storage/`（7 个文档引用）、`core/recycle/`（3 处）、`core/config_migrations.py`、`features/prompts/application_service.py`、`features/scraping/confidence_engine.py`、`scraper/match_engine|confidence_engine|confidence_models.py`、`storage/source_cleaner.py`、测试文件 3 个（`test_feature_recycle.py`/`test_config_migration_v3.py`/`test_match_pipeline_integration.py`/`test_stage_db_migration.py`）。
最终状态：88 个活跃 md 断链 0、代码路径漂移 0、AGENTS.md→ai-map.md 两跳可答全部典型任务问题。

## 未归档（保留待业务拍板）

- `docs/plans/2026-06-03-frontend-cinema-redesign-plan.md` — 前端重做方向属业务决策，待用户拍板（见 tracking/backlog-reevaluation.md §1）
- `docs/_drafts/2026-06-18-file-flow-cartesian-product.md` — 文件全流程测试设计矩阵，价值取决于简洁化后的测试策略，冻结待 REQ-20260822-000001 评估
