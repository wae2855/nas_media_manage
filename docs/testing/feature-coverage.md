# Feature Coverage & Regression Test Map

> 目的：以**前台节点 → 功能点 → 后端入口 → 测试脚本**为主轴地毯式列清产品所有功能点，
> 作为后续回归测试选择、补齐和重命名的统一事实源。
>
> 视角区别：
>
> - 本文档 = "按产品功能点列"（产品视角，从外往里看）
> - [regression-matrix.md](regression-matrix.md) = "按修改范围列"（开发者视角，改了 X 跑哪些）
> - [test-inventory.md](test-inventory.md) = "按测试状态列"（维护者视角，哪些 current/gated/archive）

## 1. 节点划分基线

前台节点采用 [frontend-information-architecture.md](../product/frontend-information-architecture.md) 推荐的 **7 个工作区** 作为长期目标 IA。

| # | 工作区 | 当前一级空间 | 后端 Feature 域 | 主要 API 路径前缀 |
|---|--------|--------------|-----------------|-------------------|
| 1 | 仪表盘 Dashboard | `overview` | `core/runtime` | `/api/health`, `/api/metrics`, `/api/watcher/*`, `/api/queue/*`, `/api/logs`, `/api/skill*` |
| 2 | 任务工作台 Tasks | `tasks` | `features/tasks`, `features/import_flow` | `/api/tasks/*`, `/api/run*`, `/api/queue/*` |
| 3 | 入库规则 Import Rules | `config` | `features/configuration`, `features/source_files` | `/api/config`, `/api/path/test`, `/api/watcher/*` |
| 4 | 元数据与 AI Metadata & AI | `config` | `features/scraping`, `features/providers`, `features/prompts`, `features/dimensions` | `/api/providers/*`, `/api/dimensions/*`, `/api/scrape/*`, `/api/config/test-llm`, `/api/config/prompt-defaults` |
| 5 | 源目录清理 Source Cleaner | `config` | `features/source_cleaning` | `/api/source-cleaner/*` |
| 6 | 回收站 Recycle | `recycle` | `features/recycle`, `infrastructure/filesystem` | `/api/recycle/*`, `/api/thumbnails/*` |
| 7 | 系统与通知 System & Notify | `overview` + 散点 | `core/runtime`, `monitor/`, `notify/`, `features/configuration` | `/api/config/check-permission`, `/api/config/test-hermes`, `/api/skill*` |

注意：第 1、7 区在当前实现中共享 `overview` 顶栏和少量散点入口，正式重做后拆分。

## 2. 测试脚本命名规范

为了让按功能点检索和按范围选择测试都可读，测试脚本按以下前缀组织：

| 前缀 | 含义 | 当前示例 | 适用类型 |
|------|------|----------|----------|
| `test_feature_<feature>_*` | feature-first 业务域 smoke / 服务级单测 | `test_feature_task_cancel.py` | 单元/服务 |
| `test_<feature>_service.py` | feature 内部 services（如 dedup/review/cleanup） | `test_import_flow_services.py` | 单元/服务 |
| `test_match_engine*` | 三级匹配引擎（feature=scraping 子模块） | `test_match_engine.py` | 单元 |
| `test_tier<n>_*` | 匹配引擎 Tier 1/2/3 专项 | `test_tier2_match_engine.py` | 单元 |
| `test_dimensions_*` / `test_dimension_*` | 维度定义与解析 | `test_dimension_resolution.py` | 单元 |
| `test_prompt_*` | 提示词加载、解析、运行 | `test_prompt_runtime.py` | 单元/集成 |
| `test_provider_*` / `test_feature_providers_*` | Provider 注册与调用 | `test_feature_providers.py` | 单元 |
| `test_scrape_*` | 刮削预览/契约/UI | `test_scrape_preview_api.py` | 集成/UI |
| `test_recycle_*` / `test_feature_recycle_*` | 回收站移动/恢复/删除 | `test_recycle_safety.py` | 单元/集成 |
| `test_source_cleaner*` / `test_feature_source_cleaning*` | 源目录清理 | `test_source_cleaner_comprehensive.py` | 单元/集成 |
| `test_task_*` / `test_feature_task_*` | 任务领域 | `test_task_operations.py` | 单元/集成 |
| `test_config_*` / `test_feature_configuration_*` | 配置加载/校验/脱敏 | `test_config_view.py` | 单元 |
| `test_fnos_packaging` / `test_release_ledger` | fnOS 首次配置、生命周期合同、FPK 内容与版本单调门禁 | `test_fnos_packaging.py`, `test_release_ledger.py` | 单元/产物 |
| `test_api_*` | API 路由表与契约 | `test_api_routes.py` | 集成 |
| `test_architecture_guards` | 架构护栏（防回退） | `test_architecture_guards.py` | 静态/单测 |
| `test_no_legacy_*` | 历史兼容面清理验证 | `test_no_legacy_compat_surface.py` | 静态/单测 |
| `test_cleanup_orphaned_*` | 跨模块边界清理行为 | `test_cleanup_orphaned_state.py` | 集成 |
| `test_filename_cleaner` | 文件名清洗工具 | `test_filename_cleaner.py` | 单元 |
| `test_title_matcher` | 标题匹配器（匹配引擎依赖） | `test_title_matcher.py` | 单元 |
| `test_confidence_*` | 旧置信度（应转为 gated/archive） | `test_confidence_engine.py` | 历史 |

新增测试脚本必须按上面前缀组织；不符合前缀的需在评审时调整。

## 3. 工作区 1 · 仪表盘 Dashboard

| 功能点 | 前台节点 | 后端 API | 后端实现入口 | 已覆盖测试 | 缺口 |
|--------|----------|----------|--------------|------------|------|
| 健康检查与运行版本 | 顶栏状态指示、胶囊下版本 | `GET /api/health` | `api/connectivity_handlers.py:_health`, `app_version.py` | `test_api_routes.py`, `test_runtime_version.py`, `test_dashboard_responsive_ui.py`, `test_fnos_packaging.py` | fnOS 安装后版本视觉复核 |
| 运行指标 | 顶栏运行中/暂停/异常 | `GET /api/metrics` | `api/handler.py:_metrics` | `test_api_routes.py` | 指标字段契约单测 |
| 首页业务摘要 | 状态提示/今日入库/最近活动/最近影片 | `GET /api/dashboard/summary` | `features/tasks/dashboard_service.py` | `test_dashboard_summary.py`, `test_dashboard_responsive_ui.py`, `test_api_routes.py` | 真实 fnOS 设备视觉验收 |
| Watcher 状态/启停 | 自动运行阶段即时开关与状态卡 | `GET /api/watcher/status`, `POST /api/config`, `POST /api/watcher/control` | `api/config_save.py`, `features/configuration/runtime_service.py` | `test_feature_configuration_runtime.py`, `test_feature_configuration_application.py`, `test_config_atomic_save.py`, `test_configuration_refinement_ui.py`, `test_location_health.py`, `test_stable_source_gate.py`, `test_fnos_packaging.py`（含空闲只触达来源、候选恢复重试、回收每日节流、状态查询零探针） | 真实 fnOS rclone 来源、关闭桌面窗口后的持续运行与目标硬盘休眠验收 |
| 队列状态（暂停/恢复/重试全部） | 顶栏/批处理入口 | `GET /api/queue/status`, `POST /api/queue/pause|resume|retry-all` | `api/handler.py`, `features/tasks` | `test_feature_task_queue.py`（暂停/恢复/retry_all） | 队列状态 payload 字段单测 |
| 立即扫描（批处理入口） | 仪表盘 CTA | `POST /api/run` | `features/import_flow/services` | `test_feature_import_flow_run_file.py`（run_batch 间接） | run_batch 端到端 |
| 重启服务 | 仪表盘高级菜单 | `POST /api/restart` | `api/handler.py` | — | 缺回归脚本（建议 `test_dashboard_service_lifecycle.py`） |
| 首次配置引导 | 仪表盘空态 | `/api/config/validate` 等 | `features/configuration` | `test_config_view.py`, `test_api_routes.py` | 空态 UI 引导（待重做） |
| 开始页四步流程海报 | 配置开始页上半区 | 静态 UI | `webui/index.html`, `webui/css/cinema-config.css` | `test_configuration_refinement_ui.py:test_start_page_explains_the_four_step_media_journey` | 真实设备视觉验收 |
| 开始页开发者支持卡 | 配置开始页末尾 | 静态 UI | `webui/index.html`, `webui/css/cinema-config.css` | `test_configuration_refinement_ui.py:test_start_page_support_card_is_optional_and_has_stable_qr_asset_path` | 等待替换真实收款码并人工确认 |
| 日志查看 | 仪表盘抽屉 | `GET /api/logs` | `api/handler.py:_logs` | — | 缺回归脚本 |
| Skills 自检 | 仪表盘/系统页 | `GET /api/skill`, `GET /api/skills` | `api/handler.py` | — | 缺回归脚本 |

## 4. 工作区 2 · 任务工作台 Tasks

| 功能点 | 前台节点 | 后端 API | 后端实现入口 | 已覆盖测试 | 缺口 |
|--------|----------|----------|--------------|------------|------|
| 任务列表分页/筛选 | 任务工作台主表 | `GET /api/tasks` | `features/tasks` | `test_feature_task_list.py` | — |
| 任务状态统计 | 顶部状态卡 | `GET /api/tasks/stats` | `features/tasks` | `test_feature_task_detail.py:test_get_task_stats_*` | — |
| 任务详情 | 详情弹窗 | `GET /api/tasks/{id}` | `features/tasks` | `test_feature_task_detail.py:test_get_task_*`, `test_dashboard_responsive_ui.py` | 320/390px 真实浏览器视觉验收 |
| 字幕查询 | 详情内字幕 Tab | `GET /api/tasks/{id}/subtitles` | `features/tasks` | `test_feature_task_detail.py:test_get_task_subtitles_*` | — |
| 缩略图（详情/卡片/最近影片） | 卡片/详情/首页轮播 | `GET /api/thumbnails`, `GET /api/thumbnails/{file}` | `api/thumbnail_handlers.py`, `features/scraping/thumbnail_cache.py` | `test_dashboard_summary.py`（路径边界、去重、双阈值治理） | 缩略图 HTTP 响应端到端 |
| 启动单文件 | 任务空态/文件拖拽 | `POST /api/run/file` | `features/import_flow` | `test_feature_import_flow_run_file.py`（run_file 全部分支） | — |
| 重试任务 | 卡片操作 | `POST /api/tasks/{id}/retry` | `features/tasks` | `test_feature_task_queue.py:test_retry_task_*` | — |
| 重试所有失败 | 批处理菜单 | `POST /api/queue/retry-all` | `features/tasks` | `test_feature_task_queue.py:test_retry_all_failed_*` | — |
| 确认/批量确认 | 卡片操作 | `POST /api/tasks/{id}/confirm`, `POST /api/tasks/confirm-all` | `features/import_flow/services:review` | `test_feature_task_review.py`, `test_task_confirm_reason.py` | — |
| 重命名（源/临时） | 详情操作 | `POST /api/tasks/{id}/rename` | `features/tasks/services:file_lifecycle` | `test_feature_task_file_lifecycle.py:test_rename_*` | 已入库文件固定拒绝，避免修改片库 |
| 重分类 | 详情操作 | `POST /api/tasks/{id}/classify-preview` + 详情保存 | `features/import_flow/services:classification` | `test_classify_preview.py`, `test_feature_task_review.py:test_reclassify_task_*` | — |
| 忽略任务 | 详情操作 | `POST /api/tasks/{id}/ignore` | `features/tasks/services:file_lifecycle` | `test_feature_task_file_lifecycle.py:test_ignore_*` | — |
| 取消任务（队列/处理中） | 卡片操作 | `POST /api/tasks/{id}/cancel` | `features/tasks` | `test_feature_task_cancel.py` | — |
| 删除任务 | 卡片操作 | `POST /api/tasks/{id}/delete` / `DELETE /api/tasks/{id}` | `features/tasks` | `test_feature_task_delete.py` | 已入库任务只删记录；文件动作固定拒绝 |
| 清空任务（按状态） | 列表顶栏 | `POST /api/tasks/clear` | `features/tasks` | `test_feature_task_queue.py:test_clear_tasks_*` | — |
| 任务上下文/状态机迁移 | 引擎内部 | 内部方法 | `features/tasks`, `features/import_flow/context` | `test_task_context_lifecycle.py`, `test_stage_lifecycle.py` | — |
| 孤儿 RUNNING 收敛 | 启动/扫描时 | 内部 cron | `features/tasks` | `test_cleanup_orphaned_state.py` | — |

## 5. 工作区 3 · 入库规则 Import Rules

| 功能点 | 前台节点 | 后端 API | 后端实现入口 | 已覆盖测试 | 缺口 |
|--------|----------|----------|--------------|------------|------|
| 读取完整配置 | 配置导航壳加载 | `GET /api/config` | `features/configuration/application_service` | `test_api_routes.py`, `test_feature_configuration_application.py`, `test_config_view.py` | — |
| 校验配置 | 配置页保存前 | `GET /api/config/validate` | `features/configuration` | `test_api_routes.py`, `test_configuration_validate.py` | — |
| 保存整段配置 | 配置页 | `POST /api/config` | `api/config_save.py` | `test_config_view.py`, `test_config_api_no_legacy_prompts.py` | — |
| 保存分区配置 | 各分区卡片 | `POST /api/config/section` | `api/config_handlers.py`, `api/config_save.py` | `test_feature_configuration_application.py` | — |
| 路径测试（模板渲染） | 路径规则页 | `POST /api/path/test` | `api/config_handlers.py` | `test_feature_configuration_application.py:test_build_path_test_payload_*`, `test_path_rules.py` | — |
| 配置检查 | 配置完成页 | `GET /api/config/startup-readiness` | `features/configuration/startup_readiness.py` | `test_startup_readiness.py`, `test_configuration_realistic_scenarios.py`, `test_api_routes.py`, `test_configuration_refinement_ui.py` | fnOS watcher 真实运行态复核 |
| SQLite 并发保护 | 多线程 HTTP repository 访问 | 共享连接 + `_sqlite_conn_lock` | `core/db/connection.py`, `core/db/cleaner_repo.py` | `test_db_concurrency.py` | — |
| 来源单元整组回收 | 文件来源 | 内部协调器 | `features/source_files/source_units.py` | `test_source_unit_lifecycle.py`, `test_configuration_realistic_scenarios.py`, `test_naming_dedup_watcher.py` | fnOS rclone 永久删除真机验收 |
| 权限检查（读写路径） | 路径规则 | `POST /api/config/check-permission` | `api/config_handlers.py` | `test_config_consumers.py:test_permission_checker*` | — |
| Watcher 配置/状态/启停 | 监控/路径区 | `/api/watcher/status`, `/api/watcher/control` | `features/configuration/runtime` | `test_config_consumers.py:test_file_watcher_config`, `test_feature_configuration_runtime.py` | — |
| Hermes 通知配置/测试 | 系统通知区 | `POST /api/config/test-hermes` | `features/configuration` | `test_config_consumers.py:test_hermes_config` | — |
| 加载/迁移/默认值 | 内部 | 内部 | `features/configuration/application_service` | `test_config_consumers.py`, `test_config_view.py`, `test_no_legacy_compat_surface.py` | — |
| 敏感字段脱敏 | API payload | 内部 | `features/configuration/application_service` | `test_feature_configuration_application.py:test_build_config_ui_payload_masks_*` | — |
| 文件名清洗规则 | 路径规则 | 内部 `services/filename_cleaner` | `features/import_flow` 旁路 | `test_filename_cleaner.py` | — |

## 6. 工作区 4 · 元数据与 AI Metadata & AI

| 功能点 | 前台节点 | 后端 API | 后端实现入口 | 已覆盖测试 | 缺口 |
|--------|----------|----------|--------------|------------|------|
| Provider 列表 | 元数据/AI 页 | `GET /api/providers` | `features/providers` | `test_api_routes.py`, `test_feature_providers.py` | — |
| Provider 测试连接 | Provider 卡片 | `POST /api/providers/{type}/test` | `features/providers` | — | 缺回归脚本（建议 `test_provider_connectivity.py`） |
| Provider 预览 | Provider 卡片 | `POST /api/providers/{type}/preview` | `features/providers` | — | 缺回归脚本 |
| Provider 搜索 | Provider 卡片 | `POST /api/providers/{type}/search` | `features/providers` | `test_feature_providers.py`（tmdb search） | 多 Provider 覆盖 |
| Provider 详情 | Provider 卡片 | `POST /api/providers/{type}/details` | `features/providers` | `test_feature_providers.py` | — |
| Provider 类型 Genre 字典 | Provider 卡片 | `GET /api/providers/{type}/genres` | `features/providers` | — | 缺回归脚本 |
| Provider 维度能力 | 维度工作区 | `GET /api/providers/{type}/dimension-capabilities` | `features/providers` | `test_dimension_mapping_v2.py`, `test_api_routes.py` | 新 Provider 扩展验收 |
| LLM 连接测试 | LLM 配置 | `POST /api/config/test-llm` | `features/configuration` | `test_config_consumers.py`（间接） | LLM 集成端到端（gated） |
| LLM 演示 | AI 辅助 | `POST /api/config/ai-demo` | `features/configuration` | `test_ai_config_runtime.py`（ai_assist/ai_search 分离） | — |
| 提示词默认/模板 | Prompt 工作区 | `GET /api/config/prompt-defaults` | `features/prompts` | `test_api_routes.py`, `test_prompt_resolver_integration.py` | — |
| 提示词解析/注入运行 | Prompt 工作区 | 内部 | `features/prompts/prompt_builder` | `test_prompt_runtime.py`, `test_prompt_resolver_integration.py` | — |
| 维度列表 | 维度工作区 | `GET /api/dimensions` | `features/scraping` | `test_api_routes.py`, `test_dimensions_aggregation.py` | — |
| 维度启用集合 | 维度工作区 | `GET /api/dimensions/enabled` | `features/scraping` | `test_api_routes.py` | — |
| 维度详情 | 维度工作区 | `GET /api/dimensions/{name}` | `features/scraping` | `test_api_routes.py`, `test_feature_dimensions_service.py:test_get_dimension_detail_*` | — |
| 维度更新 | 维度工作区 | `PUT /api/dimensions/{name}` | `features/scraping` | `test_feature_dimensions_service.py` | — |
| 维度启用/禁用/重置 | 维度工作区 | `POST /api/dimensions/{name}/{enable,disable,reset}` | `features/scraping` | `test_feature_dimensions_service.py` | — |
| Provider 维度映射读写/试算 | 维度工作区 | `GET/PUT/POST /api/dimensions/{name}/mappings/{provider}[/preview]` | `features/scraping` | `test_dimension_mapping_v2.py`, `test_dimension_mapping_ui.py`, `test_api_routes.py` | fnOS 移动端弹层 |
| 维度 enabled 过滤匹配 | 引擎内部 | 内部 | `features/scraping` | `test_dimension_enabled_filter.py` | — |
| 维度解析/信任校验 | 引擎内部 | 内部 | `features/scraping` | `test_dimension_resolution.py` | — |
| 维度数据追溯 | 引擎内部 | 内部 | `features/scraping` | `test_dimension_trace_data_link.py` | — |
| 三级匹配 Tier1（精确） | 引擎内部 | 内部 | `features/scraping` | `test_match_engine.py`, `test_tier2_match_engine.py` | Tier1 独立可补 `test_tier1_match_engine.py` |
| 三级匹配 Tier2（关键词回搜） | 引擎内部 | 内部 | `features/scraping` | `test_match_engine.py`, `test_match_engine_keyword_loop.py`, `test_tier2_correct.py` | — |
| 三级匹配 Tier3（用户确认） | 引擎内部 | 内部 | `features/scraping` | `test_match_engine.py` | — |
| 匹配 → 审核 集成 | 引擎内部 | 内部 | `features/scraping` + `features/import_flow/services:review` | `test_match_pipeline_integration.py` | — |
| 审核决策 v2 | 引擎内部 | 内部 | `features/import_flow/services:review` | `test_review_decision_v2.py`, `test_no_legacy_confidence_behavior.py` | — |
| 标题匹配器 | 引擎内部 | 内部 | `features/scraping` | `test_title_matcher.py` | — |
| 刮削预览（启动/状态） | 匹配 & 刮削预览页 | `POST /api/scrape/preview/start`, `GET /api/scrape/preview/status/{job}` | `api/handler.py` | `test_scrape_preview_api.py`, `test_scrape_preview_job.py` | — |
| 刮削预览 UI | 刮削预览页 | UI | `webui/js/*` | `test_scrape_preview_ui.py`, `test_scrape_ui.py`（gated） | — |
| Provider 优先 E2E | 引擎内部 | 内部 | `features/scraping` | `test_scrape_provider_first_e2e.py`（gated） | — |
| 刮削结果契约 | 引擎内部 | 内部 | `features/scraping` | `test_scrape_result_contract.py` | — |
| LLM Web 搜索（search_type 注入） | AI 辅助 | 内部 | `features/scraping` | `test_llm_web_search.py`, `test_ai_config_runtime.py` | — |

## 7. 工作区 5 · 源目录清理 Source Cleaner

| 功能点 | 前台节点 | 后端 API | 后端实现入口 | 已覆盖测试 | 缺口 |
|--------|----------|----------|--------------|------------|------|
| 清理策略预览 | 源目录清理页 | `GET /api/source-cleaner/preview` | `features/source_cleaning` | `test_feature_source_cleaning.py`（间接）, `test_source_cleaner_comprehensive.py` | preview payload 字段单测 |
| 执行清理 | 源目录清理页 | `POST /api/source-cleaner/execute` | `features/source_cleaning` | `test_feature_source_cleaning.py`, `test_configuration_realistic_scenarios.py`, `test_architecture_guards.py:test_source_cleaner_api_handler_uses_*` | — |
| 执行记录 | 源目录清理页 | `GET /api/source-cleaner/records` | `features/source_cleaning` | `test_api_routes.py` | records 字段单测 |
| 服务状态 | 源目录清理页 | `GET /api/source-cleaner/status` | `features/source_cleaning` | `test_api_routes.py` | — |
| AI 辅助清理预览 | 源目录清理页 | `GET /api/source-cleaner/ai-preview` | `features/source_cleaning` | — | 缺回归脚本（建议 `test_source_cleaner_ai_preview.py`） |
| 入库后源文件清理策略 | 入库规则 | 内部 | `features/source_files` | `test_import_flow_services.py:SourceCleanupService`, `test_recycle_safety.py` | — |
| 黑名单目录/伴生文件规则 | 源目录清理策略 | 内部 | `features/source_cleaning` | `test_source_cleaner_comprehensive.py`（含 blacklist） | 拆分至 `test_source_cleaner_rules.py` |
| 媒体候选过滤 | 文件来源 | 扫描前内部合同 | `features/source_files/media_candidates.py` | `test_media_candidate_policy.py`, `test_source_unit_lifecycle.py`, `test_configuration_realistic_scenarios.py` | fnOS 真实广告文件夹 |

## 8. 工作区 6 · 回收站 Recycle

| 功能点 | 前台节点 | 后端 API | 后端实现入口 | 已覆盖测试 | 缺口 |
|--------|----------|----------|--------------|------------|------|
| 回收站列表 | 回收站页 | `GET /api/recycle/list` | `features/recycle` | `test_api_routes.py`, `test_recycle_list_payload.py`, `test_integration_recycle.py`（gated）, `test_frontend_recycle.py`（gated） | — |
| 恢复 | 回收站行 | `POST /api/recycle/restore` | `features/recycle` | `test_recycle_safety.py`（move/companion）, `test_integration_recycle.py`（gated） | — |
| 永久删除 | 回收站行 | `POST /api/recycle/delete` | `features/recycle` | `test_recycle_safety.py:test_safe_delete_*`, `test_integration_recycle.py`（gated） | — |
| 分区统计 | 回收站顶栏 | 内部 | `features/recycle` | `test_recycle_safety.py:test_move_to_recycle_records_metadata_and_source_zone` | — |
| 路径/删除安全检查 | 内部 | 内部 | `infrastructure/filesystem`, `features/recycle` | `test_recycle_safety.py:test_safe_delete_rejects_paths_*, test_validate_path_safety_rejects_traversal` | — |
| 文件指纹稳定性 | 内部 | 内部 | `infrastructure/filesystem` | `test_recycle_safety.py:test_fingerprint_*` | — |
| 入库文件被替换后入回收站 | 内部 | 内部 | `features/import_flow/services:file_operations` | `test_import_flow_services.py:ImportService` | — |
| Legacy 兼容导出 | 内部 | 内部 | `core/safety` facade | `test_recycle_safety.py:test_core_safety_keeps_compatibility_exports` | — |

## 9. 工作区 7 · 系统与通知 System & Notify

| 功能点 | 前台节点 | 后端 API | 后端实现入口 | 已覆盖测试 | 缺口 |
|--------|----------|----------|--------------|------------|------|
| 文件监控权限 | 系统页 | 内部 | `monitor/`, `infrastructure/filesystem` | `test_config_consumers.py:test_permission_checker*` | 显式 monitor smoke |
| 通知配置 Hermes | 系统页 | `POST /api/config/test-hermes` | `notify/`, `features/configuration` | `test_config_consumers.py:test_hermes_config`, `test_feature_configuration_runtime.py:test_build_notifier_*` | — |
| Watcher 启停 | 监控面板 | `/api/watcher/control` | `features/configuration/runtime` | `test_feature_configuration_runtime.py:test_restart_watcher_*` | — |
| 日志查看 | 系统页 | `GET /api/logs` | `api/handler.py` | — | 缺回归脚本 |
| Skills 自检 | 系统页 | `GET /api/skill`, `GET /api/skills` | `api/handler.py` | — | 缺回归脚本 |
| 服务端日志级别/诊断 | 系统页 | 内部 | `core/log` | — | 缺回归脚本 |
| 历史兼容面清理验证 | 内部 | 内部 | `features/*` | `test_no_legacy_compat_surface.py`, `test_no_legacy_confidence_surface.py`, `test_no_legacy_confidence_behavior.py`, `test_config_api_no_legacy_prompts.py` | — |
| 架构护栏（防回退） | 内部 | 内部 | — | `test_architecture_guards.py` | — |
| 入口直接调用 feature 公共 API | 内部 | 内部 | — | `test_feature_entrypoints.py` | — |

## 10. 缺口汇总与建议脚本

多片库与 fnOS 首次启动专项覆盖：`test_library_root_boundary.py`（规则显式选根、未知/停用引用、越界、未使用片库合法和规则解析不触达未选片库）、`test_multiple_library_roots.py`（0/2/10 根、分类、资源目录和 readiness）、`test_multiple_library_roots_ui.py`（统一目录台账、唯一目录入口、无默认规则归属）、`test_storage_directory_buttons_ui.py`（来源/回收/日志/资源/片库五类按钮的真实点击、fnOS 选择器路由与角色载荷；页面不存在中心中转入口；未授权的既有外部目录显示“重新授权”，应用私有目录显示“系统托管”；已有目录授权延迟可见后的自动刷新；模板变量光标插入、选区替换、分辨率变量、开头 `/` 即时移除和手机无溢出；片库目录独立保存、逐条人工关联、失效引用提示、失败原位反馈和成功跳转片库整理）、`test_fnos_directory_access.py`（Unix socket/token、外部目录授权根 containment、应用私有目录窄边界与失败关闭）、`test_location_health.py`（ACL、本地回收、远程来源/片库、分作用域 readiness、重启设备号重排不误报、真实挂载变化阻断）、`test_config_atomic_save.py`（片库根可先保存、规则保存必须显式绑定、废弃 `temp_dir` 请求拒绝和原子门禁）、`test_fnos_packaging.py`（首次启动空目录、应用私有日志/资源目录、跨卷重装托管路径迁移、用户外部路径保留、授权入口与离线 wheelhouse）。`test_bundle_restart_recovery.py` 覆盖目标侧暂存提交前回退、完整提交复核成功、歧义现场保留和重新整理恢复。`test_p0_confirm_workflow_fixes.py` 额外验证 `{resolution}` 能从 ffprobe 生成的 `dimensions.resolution_tier` 渲染。真实 fnOS 原生弹窗、安装时长和硬盘实际休眠仍属于 FNOS_UAT，不由本地测试替代。

按上面表格累计，主要缺口（按优先级）。**已补齐** 标记 ✅：

| 优先级 | 缺口 | 建议新脚本名 | 目标工作区 | 状态 |
|--------|------|--------------|-----------|------|
| P0 | 缩略图 API 端到端 | `test_thumbnails_api.py` | 2 任务 | 待补 |
| P0 | LLM 连接测试 | `test_feature_llm_connectivity.py` | 4 元数据 AI | 待补 |
| P0 | Provider 测试/预览/搜索/详情全分支 | `test_feature_providers_connectivity.py` | 4 元数据 AI | 待补 |
| P0 | 日志 API | `test_logs_api.py` | 1 仪表盘 + 7 系统 | 待补 |
| P0 | 重启服务 | `test_dashboard_service_lifecycle.py` | 1 仪表盘 | 待补 |
| P1 | 刮削启动 → 状态轮询 E2E | `test_scrape_preview_e2e.py` | 4 元数据 AI | 待补 |
| P1 | AI 辅助清理预览 | `test_source_cleaner_ai_preview.py` | 5 源清理 | 待补 |
| P1 | Source Cleaner 策略规则单测 | `test_source_cleaner_rules.py`（拆自 comprehensive） | 5 源清理 | 待补 |
| P1 | 路径规则/路径测试 payload | `test_path_rules.py` | 3 入库规则 | ✅ 已补（覆盖 `build_path_test_payload`） |
| P1 | 配置校验规则 | `test_configuration_validate.py` | 3 入库规则 | ✅ 已补（33 个用例覆盖 `validate_config` 全分支） |
| P1 | 队列状态 payload 字段 | `test_queue_status_payload.py` | 1 仪表盘 | 待补 |
| P1 | Skills 自检 | `test_skills_api.py` | 7 系统 | 待补 |
| P1 | Watcher 显式 smoke | `test_watcher_lifecycle.py` | 1 仪表盘 + 7 系统 | 待补 |
| P2 | Tier1 独立测试 | `test_tier1_match_engine.py` | 4 元数据 AI | 待补 |
| P2 | Source Cleaner preview/records 字段 | `test_source_cleaner_payload.py` | 5 源清理 | 待补 |
| P2 | Recycle list 字段 | `test_recycle_list_payload.py` | 6 回收站 | ✅ 已补（21 个用例覆盖 `list_recycle_dir` 字段/分页/过滤/restorable） |
| P2 | 维度分类聚合 | `test_dimensions_aggregation.py` | 4 元数据 AI | ✅ 已补（36 个用例覆盖 `dimension_manager` 7 个纯函数） |

## 11. 历史/待重构脚本（不作为当前回归主路径）

参考 [test-inventory.md](test-inventory.md)；新增功能点请用上面前缀命名，避免出现无归属脚本。

历史脚本在原仓库根目录和 `scripts/` 中已清理至归档目录；新增调试脚本请直接放入 `tmp/`（已被 `.gitignore` 忽略）并在合并前删除。

## 12. 变更影响与维护

- 新增功能点 → 同时新增/更新对应工作区章节、API 列表和测试脚本名。
- 修改 API → 更新 [architecture/api.md](../architecture/api.md) + 本文档"后端 API"列 + 关联测试。
- 新增业务域 feature → 同步 [docs/features/](../features/) + [ai-map.md](../ai-map.md) + 本文档相关工作区。
- 删除/重命名测试 → 同步 [test-inventory.md](test-inventory.md) + 本文档"已覆盖测试"列。
- 旧前端重做完成前，前台节点列以"目标 IA"为主，"当前一级空间"用于追溯。
