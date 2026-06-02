# Regression Matrix

| 修改范围 | 推荐测试 |
|----------|----------|
| DB/repo | `tests/test_task_operations.py` |
| 回收站/安全 | `tests/test_feature_recycle.py`, `tests/test_recycle_safety.py` |
| import flow | `tests/test_feature_import_flow.py`, `tests/test_import_flow_services.py`, `tests/test_task_operations.py` |
| scraper/confidence | `tests/test_confidence_engine.py`, scrape/confidence UI tests |
| config | config save/load/page tests |
| webui | `tests/test_frontend_recycle.py` for recycle UI; external-service Playwright suites only after starting port 9855 |
| API | integration/API or related UI tests |
