# Pending Acceptance

记录已完成但尚未由用户确认验收的事项。AI 在后续对话开始时应检查本文件；超过 24 小时或跨阶段未验收的事项需要主动提醒。

| Item | Completed at | Commit | Scope | Verification | User confirmation needed |
|------|--------------|--------|-------|--------------|--------------------------|
| Feature-first architecture and documentation restructure | 2026-06-02 | `42c88b9`, `cb1d876`, `2f199b9` + latest cleanup commits | Code structure, docs structure, archive policy, lifecycle workflow, test archive, feature public APIs, product/API ownership docs, old pipeline/modules/config archive cleanup, configuration/tasks/scraping consumer entrypoints | Engineering delivery verified by tests, compileall, and diff check. | Engineering acceptance can be treated as complete; product full-flow acceptance is deferred until frontend redesign and UI/E2E regression are complete. |
| AI-efficient architecture completion Phase 1-4 slices | 2026-06-03 | latest refactor commits through filesystem/source-files slice | Plan status/index cleanup, architecture standards, dependency direction map, scraping/provider/prompt/storage/config/source-cleaning/dimension/prompt/task-detail/task-list/task-queue/task-review/task-file-lifecycle/import-flow-run-file/filesystem-infrastructure/source-files feature services | `python3 -m pytest tests/` -> 244 passed; compileall; `git diff --check`. | Engineering acceptance can be treated as complete; product full-flow acceptance is deferred until frontend redesign and UI/E2E regression are complete. |
| Status+Stage 双层任务状态模型重构 | 2026-06-09 | `6b1a6d0`, `5ad8511`, `3d5f665` + api.js hotfix | 后端核心 21 文件（DB 迁移/task_lifecycle/task_manager/api/task_repo/review_service/file_lifecycle_service/classification_service/handler/routes）；前端 4 文件（cinema-app.js/cinema-tasks.js/cinema-pages.css/index.html）+ api.js GET 请求修复；测试适配 10 个失败用例修复 + 3 个新测试文件（32 用例）；文档同步 | `python3 -m pytest tests/` -> 273 passed, 3 pre-existing; compileall clean; Playwright 筛选按钮点击验证通过 | 需重启服务验证 DB 迁移和前端筛选全流程 |

## Rules

- 新完成事项先进入本文件，不直接写入 completed。
- 用户验收后，将摘要移动到 `completed-items.md` 并从本文件删除。
- 如果用户要求延后验收，在本文件记录新的提醒时间或阶段。
