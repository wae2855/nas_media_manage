# Regression Matrix

| 修改范围 | 推荐测试 |
|----------|----------|
| DB/repo | `tests/test_task_operations.py` |
| 回收站/安全 | `tests/test_feature_recycle.py`, `tests/test_recycle_safety.py` |
| import flow | `tests/test_feature_import_flow.py`, `tests/test_import_flow_services.py`, `tests/test_task_operations.py` |
| scraper/matching | `tests/test_match_engine.py`, `tests/test_match_pipeline_integration.py`, `tests/test_scrape_preview_api.py` |
| config | config save/load/page tests |
| webui | `tests/test_frontend_recycle.py` for recycle UI; external-service Playwright suites only after starting port 9855; in Codex Desktop macOS prefer the in-app Browser tool for quick checks and treat sandbox launch failures as environment blocked |
| API | integration/API or related UI tests |
| 任务取消/CANCELLED | `tests/test_feature_task_cancel.py`, `tests/test_api_routes.py`, task workbench 手动验证 |
| 任务工作台交互/详情编辑布局/孤儿任务 FAILED | `tests/test_cleanup_orphaned_state.py`, task workbench 手动验证（卡片点击、详情文件名/维度修改保存） |
