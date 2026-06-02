# Testing Standards

## Test Layers

1. 单元测试：验证模块和服务。
2. 集成测试：验证 API、DB、文件处理流程。
3. UI 测试：Playwright 验证前端工作流。

## Commands

```bash
pytest tests/
pytest tests/test_feature_import_flow.py
pytest tests/ --ignore=tests/test_*_ui.py --ignore=tests/test_frontend_*.py --ignore=tests/test_scrape_ui.py
```

## Before Refactor

- 先记录 baseline commit。
- 先检查 `.pytest_cache/v/cache/lastfailed`。
- 区分已知失败和新增失败。

## Test Reporting

每次最终回复或提交说明应包含：

- 跑了哪些测试；
- 是否通过；
- 未跑测试的原因；
- 已知失败是否与本次变更无关。
