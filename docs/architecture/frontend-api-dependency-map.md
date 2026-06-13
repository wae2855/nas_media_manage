# Frontend API Dependency Map

## Purpose

本文件把当前前端页面、API、后端 feature、关键状态和测试入口连接起来，供前端重做时按页面拆分。

## View Map

| View | Current UI Source | Primary APIs | Backend Features | Key State | Current Tests |
|------|-------------------|--------------|------------------|-----------|---------------|
| Dashboard | `webui/index.html` overview, `js/app.js` | `GET /health`, `GET /metrics`, `GET /watcher/status`, `POST /watcher/control`, `POST /run`, `POST /queue/pause`, `POST /queue/retry-all`, `POST /restart` | `features.tasks`, `features.import_flow`, watcher/monitoring wiring | system health, queue counters, watcher enabled, run action loading | API smoke, future dashboard UI smoke |
| Task List | tasks panel, `js/tasks.js` | `GET /tasks`, `GET /tasks/stats`, `GET /dimensions/enabled` | `features.tasks`, `features.import_flow`, `features.scraping` | current page, status filter, dimension label cache | `tests/test_task_operations.py`, `tests/test_feature_import_flow.py` |
| Task Detail & Actions | tasks modal/actions, `js/tasks.js` | `GET /tasks/{id}`, `POST /tasks/{id}/retry`, `POST /tasks/{id}/confirm`, `POST /tasks/{id}/reclassify`, `POST /tasks/{id}/ignore`, `POST /tasks/{id}/rename`, `POST /tasks/{id}/delete`, `GET /tasks/{id}/subtitles`, `GET /logs` | `features.tasks`, `features.import_flow`, `features.scraping`, `features.recycle` | selected task, action loading, match path modal, rename/reclassify draft | `tests/test_feature_task_delete.py`, `tests/test_task_operations.py` |
| Config Shell | config cards, breadcrumb, `js/config.js`, `js/app.js` | `GET /config`, `POST /config`, `POST /config/section`, `POST /config/reload`, `POST /config/check-permission`, `POST /path/test` | `features.configuration` | current config snapshot, dirty values, breadcrumb stack, section visibility | `tests/test_config_view.py`, `tests/test_config_consumers.py` |
| Import Rules | config source/temp/recycle/path-rules/import-options | `GET /config`, `POST /config/section`, `POST /path/test` | `features.configuration`, `features.import_flow` | directory paths, path rules, filename template inputs, manual review toggle | config tests, future rules UI tests |
| Providers & LLM | config metadata.providers / llm | `GET /providers`, `POST /providers/{type}/test`, `POST /providers/{type}/search`, `POST /providers/{type}/details`, `POST /config/test-llm`, `POST /config/test-hermes` | `features.providers`, `features.scraping`, `features.configuration` | provider cards, preview modal, llm credential state | provider mock tests, connectivity tests |
| Prompt Workspace | `js/prompts.js`, prompt area in config | `GET /config/prompts`, `POST /config/prompts`, `POST /config/prompts/reset`, `GET /providers/{type}/prompts`, `POST /providers/{type}/prompts`, `POST /providers/{type}/prompts/reset`, `POST /scrape/preview`, `GET /dimensions/enabled` | `features.prompts`, `features.scraping`, `features.providers` | selected prompt tab, dimension cache, preview result | scrape/provider tests, future prompt UI tests |
| Dimensions Workspace | `js/dimensions.js`, `js/path-rules.js` | `GET /dimensions`, `GET /dimensions/enabled`, `PUT /dimensions/{name}`, `POST /dimensions/{name}/enable`, `POST /dimensions/{name}/disable`, `POST /dimensions/{name}/reset`, `GET /providers/{type}/genres` | `features.scraping`, dimensions repository layer | dimension list, expanded card, provider genre cache | `tests/test_feature_entrypoints.py`, future dimensions UI tests |
| Matching & Scrape Preview | match section in config, `js/config.js` | `GET /dimensions`, `GET /providers`, `POST /scrape/preview`, `POST /config/section` | `features.scraping`, `features.configuration` | match form state, scrape preview three-tier path | match engine tests |
| Source Cleaner | source cleaner config section | `GET /source-cleaner/preview`, `GET /source-cleaner/records`, `GET /source-cleaner/status`, `GET /source-cleaner/ai-preview`, `POST /source-cleaner/execute`, `POST /config/section` | `features.source_cleaning`, `features.recycle`, `features.configuration` | preview list, record list, ai preview, execute loading | `tests/test_feature_source_cleaning.py` |
| Recycle | recycle panel in config JS | `GET /recycle/list`, `POST /recycle/restore`, `POST /recycle/delete` | `features.recycle` | recycle filters, selected rows, restore conflict mode, stats | `tests/test_feature_recycle.py`, `tests/test_recycle_safety.py` |

## Frontend File Ownership

当前前端 JS 可按未来 ownership 粗分为：

- `js/app.js`
Dashboard 和全局壳层。

- `js/tasks.js`
Task List + Task Detail + task actions。

- `js/config.js`
Config shell + Import Rules + Providers & LLM + Matching + Source Cleaner + Recycle。

- `js/dimensions.js`
Dimensions workspace。

- `js/prompts.js`
Prompt workspace。

- `js/path-rules.js`
Path rules editor helper。

## Recommended Future Split

建议重做时按下列前端模块拆：

- `pages/dashboard/*`
- `pages/tasks/*`
- `pages/import-rules/*`
- `pages/metadata/*`
- `pages/prompts/*`
- `pages/dimensions/*`
- `pages/source-cleaner/*`
- `pages/recycle/*`
- `shared/api/*`
- `shared/state/*`

## Test Strategy For New Frontend

至少建立 4 类测试：

1. 页面 smoke
Dashboard、Tasks、Config、Recycle 能正常加载。

2. 核心流程
保存配置、启动批处理、任务删除、回收站恢复、源目录清理预览。

3. 错误态
权限失败、Provider 连接失败、LLM 测试失败、回收冲突。

4. 响应式
桌面和移动端下任务列表、配置表单、回收站工具栏不溢出。
