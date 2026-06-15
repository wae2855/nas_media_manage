# Regression Matrix

> 视角：**改了 X 范围 → 推荐跑哪些测试**。
>
> 配套文档：
>
> - 产品视角（按前台节点）→ [feature-coverage.md](feature-coverage.md)
> - 测试状态分类 → [test-inventory.md](test-inventory.md)

| 修改范围 | 推荐测试 |
|----------|----------|
| DB/repo | `tests/test_task_operations.py`, `tests/test_feature_entrypoints.py` |
| 回收站/安全 | `tests/test_feature_recycle.py`, `tests/test_recycle_safety.py`, `tests/test_integration_recycle.py` (gated) |
| import flow | `tests/test_feature_import_flow.py`, `tests/test_feature_import_flow_run_file.py`, `tests/test_import_flow_services.py`, `tests/test_task_operations.py`, `tests/test_filename_cleaner.py` |
| 刮削/匹配（三级） | `tests/test_match_engine.py`, `tests/test_tier2_match_engine.py`, `tests/test_tier2_correct.py`, `tests/test_match_engine_keyword_loop.py`, `tests/test_match_pipeline_integration.py`, `tests/test_review_decision_v2.py`, `tests/test_title_matcher.py` |
| 刮削预览/Provider 契约 | `tests/test_scrape_preview_api.py`, `tests/test_scrape_preview_job.py`, `tests/test_scrape_provider_first_e2e.py` (gated), `tests/test_scrape_result_contract.py`, `tests/test_feature_providers.py` |
| LLM / AI 注入 | `tests/test_ai_config_runtime.py`, `tests/test_llm_web_search.py`, `tests/test_prompt_runtime.py`, `tests/test_prompt_resolver_integration.py` |
| 维度 | `tests/test_dimension_resolution.py`, `tests/test_dimension_enabled_filter.py`, `tests/test_dimension_trace_data_link.py`, `tests/test_feature_dimensions_service.py` |
| 配置 | `tests/test_config_view.py`, `tests/test_config_consumers.py`, `tests/test_feature_configuration_application.py`, `tests/test_feature_configuration_runtime.py`, `tests/test_config_api_no_legacy_prompts.py` |
| 源目录清理 | `tests/test_feature_source_cleaning.py`, `tests/test_source_cleaner_comprehensive.py` (legacy), `tests/test_architecture_guards.py` |
| 任务域 | `tests/test_task_context_lifecycle.py`, `tests/test_stage_lifecycle.py`, `tests/test_feature_task_list.py`, `tests/test_feature_task_detail.py`, `tests/test_feature_task_queue.py`, `tests/test_feature_task_review.py`, `tests/test_feature_task_file_lifecycle.py` |
| 任务取消/CANCELLED | `tests/test_feature_task_cancel.py`, `tests/test_api_routes.py`, task workbench 手动验证 |
| 任务工作台交互/详情编辑布局/孤儿任务 FAILED | `tests/test_cleanup_orphaned_state.py`, task workbench 手动验证（卡片点击、详情文件名/维度修改保存） |
| API 路由/契约 | `tests/test_api_routes.py` |
| webui | `tests/test_frontend_recycle.py` for recycle UI; external-service Playwright suites only after starting port 9855; in Codex Desktop macOS prefer the in-app Browser tool for quick checks and treat sandbox launch failures as environment blocked |
| 架构护栏/历史清理 | `tests/test_architecture_guards.py`, `tests/test_no_legacy_compat_surface.py`, `tests/test_no_legacy_confidence_surface.py`, `tests/test_no_legacy_confidence_behavior.py`, `tests/test_feature_entrypoints.py` |
| 历史置信度（已替换为 match_level） | `tests/test_confidence_engine.py` (gated → 计划 archive), `tests/test_review_decision_v2.py` |
