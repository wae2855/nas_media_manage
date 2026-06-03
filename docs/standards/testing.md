# Testing Standards

## Test Layers

1. 单元测试：验证模块和服务。
2. 集成测试：验证 API、DB、文件处理流程。
3. UI 测试：Playwright 验证前端工作流。

## Commands

```bash
pytest tests/
pytest tests/test_feature_import_flow.py
pytest tests/test_architecture_guards.py
pytest tests/ --ignore=tests/test_*_ui.py --ignore=tests/test_frontend_*.py --ignore=tests/test_scrape_ui.py
PYTHONPYCACHEPREFIX=/private/tmp/nas_media_manage_pycache python3 -m compileall -q media_importer tests
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

## Architecture Guardrails

- 结构或文档重构后，优先运行 `tests/test_feature_entrypoints.py` 和 `tests/test_architecture_guards.py`。
- `tests/test_architecture_guards.py` 用于防止当前事实文档重新引用 archive 作为事实来源，并限制关键入口回退到旧 `storage/` 业务路径。
- 在未确定 lint/typecheck 工具链前，暂不新增 `pyproject.toml`；当前仍以 `pytest.ini` 维持 pytest 配置。
