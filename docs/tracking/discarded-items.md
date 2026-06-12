# Discarded Items

废弃需求记录。AI 默认不扫描本文件，仅在用户要求查阅时读取。

| ID | Title | Type | Reason | Code Action | Discarded at | Links |
|----|-------|------|--------|-------------|-------------|-------|
| DISCARD-2026-06-10-E2E | Live E2E Playwright 全量回归套件 | plan + test-suite | 前端进入重做阶段，旧 v1/v2 全量 Playwright 回归（70+ 用例，覆盖配置/扫描/任务操作/回收/导航/批量/视觉）需要在新前端和稳定 service-integration 基线上重新规划；继续维护会与新 UI 不同步 | plan-deleted + branch-deleted | 2026-06-10 | [docs/plans/2026-06-09-e2e-playwright-test-plan.md]（已删）, tests/test_e2e_01_config.py ~ tests/test_e2e_07_visual.py（已删）, tests/conftest.py 中 LIVE_E2E_FILES / e2e_server / e2e_browser_context / e2e_page / e2e_test_files fixtures 与 `--run-live-e2e` option 已移除, pytest.ini 中 live_e2e marker 已移除, docs/testing/ui-playwright.md 中 `--run-live-e2e` 文档已移除 |

## Rules

- 只有用户确认废弃的需求才写入本文件。
- Code Action 记录处理方式：`branch-deleted` / `reverted` / `partial-revert` / `kept`。
- 废弃原因和替代方案（如有）写在 Reason 列。
