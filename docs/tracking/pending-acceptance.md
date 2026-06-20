# Pending Acceptance

记录已完成但尚未由用户确认验收的事项。AI 在后续对话开始时应检查本文件；超过 24 小时或跨阶段未验收的事项需要主动提醒。

| Item | Completed at | Commit | Scope | Verification | User confirmation needed |
|------|--------------|--------|-------|--------------|--------------------------|
| Feature-first architecture and documentation restructure | 2026-06-02 | `42c88b9`, `cb1d876`, `2f199b9` + latest cleanup commits | Code structure, docs structure, archive policy, lifecycle workflow, test archive, feature public APIs, product/API ownership docs, old pipeline/modules/config archive cleanup, configuration/tasks/scraping consumer entrypoints | Engineering delivery verified by tests, compileall, and diff check. | Engineering acceptance can be treated as complete; product full-flow acceptance is deferred until frontend redesign and UI/E2E regression are complete. |
| AI-efficient architecture completion Phase 1-4 slices | 2026-06-03 | latest refactor commits through filesystem/source-files slice | Plan status/index cleanup, architecture standards, dependency direction map, scraping/provider/prompt/storage/config/source-cleaning/dimension/prompt/task-detail/task-list/task-queue/task-review/task-file-lifecycle/import-flow-run-file/filesystem-infrastructure/source-files feature services | `python3 -m pytest tests/` -> 244 passed; compileall; `git diff --check`. | Engineering acceptance can be treated as complete; product full-flow acceptance is deferred until frontend redesign and UI/E2E regression are complete. |
| Status+Stage 双层任务状态模型重构 | 2026-06-09 | `6b1a6d0`, `5ad8511`, `3d5f665` + api.js hotfix | 后端核心 21 文件（DB 迁移/task_lifecycle/task_manager/api/task_repo/review_service/file_lifecycle_service/classification_service/handler/routes）；前端 4 文件（cinema-app.js/cinema-tasks.js/cinema-pages.css/index.html）+ api.js GET 请求修复；测试适配 10 个失败用例修复 + 3 个新测试文件（32 用例）；文档同步 | `python3 -m pytest tests/` -> 273 passed, 3 pre-existing; compileall clean; Playwright 筛选按钮点击验证通过 | 需重启服务验证 DB 迁移和前端筛选全流程 |
| AI 配置界面三区域改造 Phase 1-3 | 2026-06-15 | `8a5e425`, `197d01d`, `cb59d55`, (Phase 3 commit) | Phase 1：后端基础设施（5 场景策略 + 多模型 fallback + 统一日志）；Phase 2：前端 3 手风琴区域 + 5 提示词 tab + 场景策略 5×2 下拉 + 用户验收修复；Phase 3：31 新测试 + 文档同步 | `python3 -m pytest tests/` -> 623+ passed（无 UI 测试）；compileall clean；架构护栏通过 | 待用户浏览器验证前端全部功能 |
| 清理与迁移主计划 Phase 1-5 | 2026-06-20 | `7fc7677`, `a59a2ac`, `ea2410b`, `1c8cd41`, `19f2b0b`, `745f65f`, `77fb424`, `955c0b5`, `bf93ee8`, `d401db3`, `4ea70b8`, `abf9be1`, `cb0db68`, `93a51f8` | Phase 1：前端 P0 修复（首页"需要确认"指标卡 + setTaskFilter 兜底）；Phase 2：旧任务前端 JS 归档到 `_archive/2026-06-18-legacy-task-ui/`；Phase 3：confirm_reason 万能胶字段退役（6 层职责模型）；Phase 4：scraper/ 整包迁移到 features/scraping + features/providers（S-Phase 1/2/3a/3b-1/3b-2/4a/5）；Phase 5：core.db → infrastructure.db facade 迁移 + 2 个 architecture guards | `python -m pytest tests/` 通过；compileall clean；`test_no_production_code_imports_scraper_package` + `test_no_production_code_imports_core_db_directly` 通过 | 需用户浏览器验证前端 P0 修复（指标卡跳转到 review chip） + 任务工作台主流程 |

## Rules

- 新完成事项先进入本文件，不直接写入 completed。
- 用户验收后，将摘要移动到 `completed-items.md` 并从本文件删除。
- 如果用户要求延后验收，在本文件记录新的提醒时间或阶段。
