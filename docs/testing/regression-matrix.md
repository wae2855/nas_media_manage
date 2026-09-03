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
| 回收站/安全 | `tests/test_feature_recycle.py`, `tests/test_recycle_safety.py`, `tests/test_recycle_api_boundary.py`, `tests/test_integration_recycle.py` (gated) |
| import flow | `tests/test_feature_import_flow.py`, `tests/test_feature_import_flow_run_file.py`, `tests/test_import_flow_services.py`, `tests/test_task_operations.py`, `tests/test_filename_cleaner.py` |
| 目标片库冲突/覆盖安全 | `tests/test_target_library_conflict_safety.py`, `tests/test_filesystem_symlink_safety.py`, `tests/test_target_library_conflict_ui.py`, `tests/test_cleanup_orphaned_state.py`, `tests/test_feature_task_delete.py`, `tests/test_feature_task_file_lifecycle.py`, `tests/test_source_unit_lifecycle.py`, `tests/test_recycle_safety.py`, `tests/test_dashboard_summary.py`，并用真实临时目录验证检测前后指纹不变、并发目标不被覆盖、链接目标不被写入 |
| 兜底入库/重新整理 | `tests/test_task_organization.py`, `tests/test_task_organization_ui.py`, `tests/test_task_organization_browser_ui.py`, `tests/test_bundle_restart_recovery.py`, `tests/test_file_flow_matrix.py`, `tests/test_feature_task_review.py`；真实临时目录验证父任务不重开、字幕整包移动、目标冲突零覆盖和提交前后重启恢复，并由真实浏览器覆盖手动刮削、移动端详情、冲突决策及明确确认兜底的客户旅程 |
| 刮削/匹配（两级） | `tests/test_match_engine.py`, `tests/test_media_identity_resolution_v2.py`, `tests/test_tier2_match_engine.py`, `tests/test_tier2_correct.py`, `tests/test_match_engine_keyword_loop.py`, `tests/test_match_pipeline_integration.py`, `tests/test_review_decision_v2.py`, `tests/test_title_matcher.py`, `tests/test_identity_evidence.py`, `tests/test_full_frontend_flow_matrix_browser_ui.py`；覆盖显式/NFO ID、ID 冲突与异常降级、候选差距保护、目录连续跳过、广告伴随视频不阻断片名目录、多影片合集不套用目录、文件/目录冲突进入人工确认 |
| 发布名解析 | `tests/test_release_identity.py`, `tests/test_identity_evidence.py`, `tests/test_media_identity_resolution_v2.py` + `tests/fixtures/media_identity_resolution_v2.yaml`；覆盖中文数字季、多集范围、复合画质、强广告域名、正常 `.me` 英文片名、三类 Provider ID、NFO、目录结构、Provider 官方别名及年份冲突降级 |
| 刮削预览/Provider 契约 | `tests/test_scrape_preview_api.py`, `tests/test_scrape_preview_job.py`, `tests/test_scrape_provider_first_e2e.py` (gated), `tests/test_scrape_result_contract.py`, `tests/test_feature_providers.py` |
| LLM / AI 注入 | `tests/test_ai_config_runtime.py`, `tests/test_llm_web_search.py`, `tests/test_prompt_runtime.py`, `tests/test_prompt_resolver_integration.py` |
| 维度 | `tests/test_dimension_resolution.py`, `tests/test_dimension_enabled_filter.py`, `tests/test_dimension_trace_data_link.py`, `tests/test_feature_dimensions_service.py`, `tests/test_dimension_mapping_v2.py`, `tests/test_dimension_mapping_ui.py` |
| 配置 | `tests/test_config_view.py`, `tests/test_config_consumers.py`, `tests/test_feature_configuration_application.py`, `tests/test_feature_configuration_runtime.py`, `tests/test_config_api_no_legacy_prompts.py`, `tests/test_configuration_realistic_scenarios.py` |
| fnOS 安装/打包 | `tests/test_fnos_packaging.py`, `tests/test_release_ledger.py`, `python scripts/release_ledger.py status`, `scripts/validate_fpk.py <fpk> --version <version>`, `bash -n deploy/build_fpk.sh` |
| 源目录清理 | `tests/test_feature_source_cleaning.py`, `tests/test_source_cleaner_comprehensive.py`, `tests/test_configuration_realistic_scenarios.py`, `tests/test_media_candidate_policy.py`, `tests/test_source_unit_lifecycle.py`, `tests/test_filesystem_symlink_safety.py`, `tests/test_naming_dedup_watcher.py`, `tests/test_architecture_guards.py` |
| 任务域 | `tests/test_task_context_lifecycle.py`, `tests/test_stage_lifecycle.py`, `tests/test_feature_task_list.py`, `tests/test_feature_task_detail.py`, `tests/test_feature_task_queue.py`, `tests/test_feature_task_review.py`, `tests/test_feature_task_file_lifecycle.py` |
| 任务取消/CANCELLED | `tests/test_feature_task_cancel.py`, `tests/test_api_routes.py`, task workbench 手动验证 |
| 任务安全退出/来源处置/只删记录 | `tests/test_task_disposition.py`, `tests/test_task_disposition_ui.py`, `tests/test_feature_task_delete.py`, `tests/test_api_routes.py`；必须验证运行中协作停止、精确视频/字幕成员、永久删除门禁、片库哈希不变和移动端弹窗 |
| rclone/FUSE 来源永久删除 | `tests/test_source_permanent_delete.py`；必须验证 rename 后虚拟 inode 改变、旧账本、部分 unlink 后续做、挂载变化、本地 inode 门禁、未知成员和片库哨兵不变 |
| 最少大文件传输/直接目标暂存 | `tests/test_import_flow_services.py`, `tests/test_subtitle_bundle_publish.py`, `tests/test_bundle_restart_recovery.py`, `tests/test_verified_transfer.py`, `tests/test_file_flow_matrix.py`, `tests/test_full_frontend_flow_matrix_browser_ui.py`；确认前目标零写入，直接复制只读来源一次并取得摘要，停止/重启只清理任务目标副本；完整前端矩阵还需核对源/片库/回收树和 SHA-256 证据，并包含真实复制中途外部 SIGKILL、同配置重启和前端重试 |
| 任务工作台交互/详情编辑布局/孤儿任务 FAILED | `tests/test_cleanup_orphaned_state.py`, task workbench 手动验证（卡片点击、详情文件名/维度修改保存） |
| API 路由/契约 | `tests/test_api_routes.py` |
| webui | `tests/test_frontend_recycle.py` for recycle UI; external-service Playwright suites only after starting port 9855; in Codex Desktop macOS prefer the in-app Browser tool for quick checks and treat sandbox launch failures as environment blocked |
| 架构护栏/历史清理 | `tests/test_architecture_guards.py`, `tests/test_no_legacy_compat_surface.py`, `tests/test_no_legacy_confidence_surface.py`, `tests/test_no_legacy_confidence_behavior.py`, `tests/test_feature_entrypoints.py` |
| 历史置信度（已替换为 match_level） | `tests/test_confidence_engine.py` (gated → 计划 archive), `tests/test_review_decision_v2.py` |
