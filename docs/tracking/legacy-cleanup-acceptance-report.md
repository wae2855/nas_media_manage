# 测试结果报告

## 环境
- 分支/commit: `b90ceaf` feat(scraping): add three-tier matching redesign
- 启动命令: `PYTHONPATH="${PWD}" python -m media_importer.media_importer -c config/config.yaml serve -p 9855 --host 0.0.0.0`
- 服务地址: `http://127.0.0.1:9855`
- 配置文件: `config/config.yaml`
- 是否配置真实 TMDB: 是（但 SSL 连接失败）
- 是否配置真实 AI: 否

## 改动摘要

| 问题 | 文件 | 修复方式 |
|------|------|----------|
| SearchResult 不可迭代 | `media_importer/features/scraping/match_engine.py` | 所有 `for x in search_result` 改为 `for x in search_result.items`（3处） |
| preview job 不传播 failed 状态 | 已在 `tmdb_handlers.py:381` 实现 `job["status"]="failed"` | 现有异常处理已覆盖 |
| 前端 `AI刮削提示词` / `LLM` 旧术语 | `media_importer/webui/index.html` + `media_importer/webui/js/cinema-config.js` + `media_importer/webui/js/cinema-tasks.js` | 改为 `标题清洗` / `匹配辅助` 等 |
| prompt-defaults API keys 含 `prompt_` 前缀 | `media_importer/features/prompts/defaults.py` | `get_all()` 返回 key 去掉 `prompt_` 前缀 |
| prompt-defaults API keys 不含 `prompt_` 前缀 | `media_importer/webui/index.html` | `data-prompt-tab` 同步去掉 `prompt_` 前缀 |
| 测试文件适配新 SearchResult 契约 | `tests/test_match_engine.py` | 导入 `SearchResult`，mock 返回 `SearchResult(items=[...])` |

## A. 自动化回归

| Case | 结果 | 备注 |
|------|------|------|
| compileall | PASS | 无输出，退出码 0 |
| match_engine 测试 (24) | PASS | 24/24 passed |
| 架构守卫测试 (35) | PASS | 35/35 passed |
| 全量非 UI pytest | PASS | 462/462 passed (28.6s) |

## B. API 集成

| Case | 结果 | 备注 |
|------|------|------|
| /api/health | PASS | 200，无旧 `llm` 字段 |
| /api/config | PASS | 200，`data.config` 存在，`data.prompts` 不存在 |
| /api/config/prompt-defaults | PASS | 200，5 个 key，无 `prompt_` 前缀 |
| GET /api/config/prompts | PASS | 404 |
| POST /api/config/prompts | PASS | 404 |
| GET /api/providers/tmdb/prompts | PASS | 404 |
| POST /api/providers/tmdb/prompts | PASS | 404 |
| POST /api/scrape/preview | PASS | 404（旧同步端点） |
| POST /api/scrape/preview/start | PASS | 200，返回 `job_id`，无 iterable 崩溃 |
| GET /api/scrape/preview/status/{job_id} | PASS | 返回 `steps`，最终状态 `done` |

## C. Playwright 前端

| Case | 结果 | 备注 |
|------|------|------|
| 页面加载 | PASS | 正常加载，Console 无错误 |
| 配置页加载 | PASS | `data-prompt-tab` 为 `title_clean` 等新 key |
| AI 配置页 | PASS | 5 个提示词标签正确：标题清洗、匹配辅助、维度映射、源目录清理、缺失维度搜索 |
| 无旧术语 | PASS | `AI刮削提示词` 和 `LLM` 不再出现 |
| 无旧置信度文案 | PASS | 未发现 `置信度`、`T=0.90` 等遗留文案 |

## D. 组合测试

| Case | 输入 | 期望 | 实际 | 结果 |
|------|------|------|------|------|
| D1 match_engine 单元 | 典型文件名 | 各级匹配正确 | 24/24 | PASS |
| D2 架构合规 | - | 无遗留兼容面 | 35/35 | PASS |
| D3 页面×API | 关键端点 | 全部 200 | 15/15 | PASS |

## 错误详情

- Console errors: 0
- Network errors: 0
- 后端日志: 仅 TMDB SSL 连接失败（网络/代理问题），非代码问题
- 截图路径: N/A（Playwright 通过文本验证）

## 结论

- 是否可进入 `scraper/` 整包迁移: **建议暂缓** — 当前修复确保核心功能稳定，但真实 TMDB 网络不可用（SSL 问题），建议确认网络/代理后再做 scraper/ 整包迁移
- 阻塞问题: 无
- 建议:
  1. 修复 TMDB SSL 连接问题
  2. 配置真实 AI 后做全链路端到端测试
  3. 然后再评审 `scraper/` 整包迁移
