---
title: "test: legacy cleanup acceptance and regression"
type: test-plan
date: 2026-06-13
status: ready-for-execution
confidence: high
related:
  - docs/plans/2026-06-13-refactor-remove-legacy-compatibility-plan.md
  - docs/decisions/0005-three-tier-matching.md
---

# 去历史兼容化验收与回归测试计划

一行摘要：通过自动化回归、API 集成、Playwright 前端模拟和组合场景测试，确认去历史兼容化后系统主流程稳定，再决定是否进入 `scraper/` 整包迁移。

## 测试目标

- 前端能加载配置页、AI 配置页、Provider 配置页、任务页和模拟测试页。
- AI 配置是唯一用户可见提示词入口。
- Provider 配置和 Provider 搜索可用。
- 异步模拟刮削有阶段进度，不再长时间空白等待。
- 三级匹配结果正确展示。
- `NEEDS_CONFIRM` 时能展示候选第一名和确认原因。
- 运行时不再暴露旧 `llm`、旧 prompt、旧置信度、旧同步 preview、旧 storage wrapper 和旧 route flags。
- 自动化回归、集成测试和关键 Playwright 前端验收通过。

## 测试边界

### In Scope

- Python 编译检查。
- pytest 非 UI 回归。
- legacy guard。
- API 集成测试。
- Playwright 真实前端操作。
- 模拟测试页面异步 preview job。
- 典型文件名组合场景。
- 任务流程 smoke。

### Out Of Scope

- 不做 `scraper/` 整包迁移。
- 不修改代码。
- 不修改配置文件，除非测试环境已明确允许使用临时配置。
- 不测试 `deploy/` 生成副本。

## 前置条件

- 仓库处于去历史兼容化清理完成后的工作区。
- Python 环境已初始化。
- 如需真实 Provider 测试，`config/config.yaml` 中有有效 TMDB API Key。
- 如需真实 AI 测试，`ai_assist` / `ai_search` 已配置有效模型和 API Key。
- 如果没有真实外部服务，必须在报告中标注“使用 mock / 未配置真实 TMDB / 未配置真实 AI”。

## A. 基础自动化回归

### A1. 编译检查

```bash
PYTHONPYCACHEPREFIX=/private/tmp/nas_media_manage_pycache python -m compileall -q media_importer tests
```

期望：无输出，退出码 0。

### A2. 核心测试

```bash
python -m pytest tests/test_no_legacy_compat_surface.py -q
python -m pytest tests/test_config_api_no_legacy_prompts.py -q
python -m pytest tests/test_ai_config_runtime.py tests/test_config_view.py tests/test_llm_web_search.py -q
python -m pytest tests/test_scrape_preview_job.py tests/test_scrape_provider_first_e2e.py -q
python -m pytest tests/test_match_engine.py tests/test_match_engine_keyword_loop.py tests/test_match_pipeline_integration.py -q
```

期望：全部通过。

### A3. 全量非 UI 测试

```bash
python -m pytest tests/ --ignore=tests/test_scrape_ui.py --ignore=tests/test_frontend_config.py -q
```

期望：全部通过。

### A4. 旧兼容面 grep

```bash
rg "get\([\"']llm[\"']|_get_real_config_value\([\"']llm[\"']|\[[\"']llm[\"']\]|LLMConfig|fallback_model|source_cleaner_model|confidence_threshold|media_importer\.storage|from media_importer.storage|body_before_params|pass_self|ConfidenceEngine|ConfidenceResult|scrape_confidence|scraper_prompts|tmdb_prompts|prompt-config|prompt-tmdb|_load_prompts_for_ui|_tmdb_preview|_tmdb_search|_tmdb_details" media_importer tests
```

期望：

- `media_importer` 无命中。
- `tests` 只允许 guard 测试或断言旧字段不存在的测试中出现。

## B. 服务启动与 API 集成测试

### B0. 启动服务

```bash
PYTHONPATH="${PWD}" python -m media_importer.media_importer -c config/config.yaml serve -p 9855 --host 127.0.0.1
```

如果端口占用，换端口并记录。

### B1. 健康检查

请求：

```text
GET http://127.0.0.1:9855/api/health
```

期望：

- HTTP 200。
- 返回 JSON。
- 不引用旧 `llm` 字段作为唯一 AI 状态来源。

### B2. 配置接口

请求：

```text
GET /api/config
```

期望：

- HTTP 200。
- `data.config` 存在。
- `data.prompts` 不存在。
- 不报 `_load_prompts_for_ui` 错误。

### B3. Prompt Defaults

请求：

```text
GET /api/config/prompt-defaults
```

期望返回 5 类：

- `prompt_title_clean`
- `prompt_match_assist`
- `prompt_dimension_mapping`
- `prompt_source_clean`
- `prompt_dimension_supplement`

### B4. 旧 Prompt API 不存在

请求：

```text
GET /api/config/prompts
POST /api/config/prompts
POST /api/config/prompts/reset
GET /api/providers/tmdb/prompts
POST /api/providers/tmdb/prompts
POST /api/providers/tmdb/prompts/reset
```

期望：

- 404 或明确不可用。
- 不能返回旧 prompt 编辑数据。

### B5. 旧同步 Preview 不存在

请求：

```text
POST /api/scrape/preview
```

期望：

- 404 或明确不可用。
- 不能执行完整刮削。
- 不返回旧 `confidence_detail` / `best_confidence`。

### B6. 异步 Preview Job

请求：

```text
POST /api/scrape/preview/start
body: {"filename":"进击的巨人.S01E02.1080p.BluRay.mp4"}
```

期望：

- HTTP 200。
- 返回 `job_id`。

轮询：

```text
GET /api/scrape/preview/status/{job_id}
```

期望：

- `status` 为 `running` 或 `done`。
- `steps` 数组存在。
- 至少包含文件名清洗、Provider 搜索、匹配相关步骤。
- 最终 `result.match_result.match_level` 存在。
- 如果 `NEEDS_CONFIRM`，必须有 `confirm_reason` 或 `match_concerns`。
- 不返回旧 `confidence_detail`、`best_confidence`、`confidence_search`、`confidence_data_gate`。

## C. Playwright 前端验收测试

### C0. 打开页面

URL：

```text
http://127.0.0.1:9855/
```

期望：

- 页面正常加载。
- Console 无红色错误。
- Network 无 `/api/config` 500。
- 记录页面截图、console errors、network failed requests。

### C1. 配置页加载

步骤：

1. 打开首页。
2. 进入配置入口或高级配置入口。
3. 等待配置页内容加载。

期望不出现：

- `AI刮削提示词`
- `LLM+TMDB 刮削提示词`
- `LLM 直接刮削提示词`
- `置信度计算详情`
- `最终置信度`
- `T × R`
- `search_conf`
- `data_gate`

### C2. AI 配置页

步骤：

1. 进入 AI 配置页。
2. 检查 `ai_assist` 区域。
3. 检查 `ai_search` 区域。
4. 检查 5 个提示词 textarea 或编辑入口。
5. 如有“恢复默认”，点击并确认默认内容可回填。
6. 保存配置。
7. 刷新页面后再次进入。

期望：

- 5 个提示词集中在 AI 配置中。
- 保存后刷新仍保留。
- 不需要进入“AI刮削提示词”页面。
- 不出现旧 `llm` 字段文案。

需要检查的字段：

| 字段 | 期望 |
|---|---|
| AI辅助模型 URL | 可保存 |
| AI辅助模型 ID | 可保存 |
| AI辅助 API Key | 脱敏显示 |
| AI搜索模型 URL | 可保存 |
| AI搜索模型 ID | 可保存 |
| AI搜索 API Key | 脱敏显示 |
| `prompt_title_clean` | 可编辑/恢复默认 |
| `prompt_match_assist` | 可编辑/恢复默认 |
| `prompt_dimension_mapping` | 可编辑/恢复默认 |
| `prompt_source_clean` | 可编辑/恢复默认 |
| `prompt_dimension_supplement` | 可编辑/恢复默认 |

### C3. Provider 配置页

步骤：

1. 进入 Provider / 元数据源配置。
2. 启用 TMDB。
3. 填写或保留 API Key。
4. 保存。
5. 搜索测试一个标题。

测试标题：

```text
进击的巨人
Attack on Titan
Inception
```

期望：

- Provider 配置保存成功。
- API Key 脱敏。
- 搜索结果返回列表或合理错误。
- 不出现旧 `metadata.tmdb` 单 key 配置说明。

### C4. 异步模拟刮削进度

核心测试输入：

```text
进击的巨人.S01E02.1080p.BluRay.mp4
```

步骤：

1. 进入模拟测试页面。
2. 输入文件名。
3. 点击“刮削开始”或模拟测试按钮。
4. 观察页面 1 秒内是否出现第一步进度。
5. 持续观察步骤变化。
6. 等待完成。

期望：

- 1 秒内出现阶段进度。
- 不再 5 分钟空白等待。
- 至少显示类似步骤：文件名清洗、Provider 搜索、三级匹配、候选确认/获取详情、完成。
- 完成时展示结果。
- 如果 `NEEDS_CONFIRM`，展示“待人工确认”、确认原因、候选第一名预览结果，并标注实际入库前仍需人工确认。
- 不展示 `T=0.90`、`最终置信度`、`置信度计算详情`、`search_conf`、`data_gate`。

## D. 组合测试矩阵

采用“核心笛卡尔积 + pairwise”覆盖，不做全量爆炸。

### D1. 文件名 × Provider × AI 状态

| Case | 文件名 | Provider | AI辅助 | AI搜索 | 期望 |
|---|---|---|---|---|---|
| D1-1 | `Inception.2010.1080p.mp4` | 唯一结果 | 开 | 关 | `AUTO_PASS` 或 `CONTEXT_PASS` |
| D1-2 | `进击的巨人.S01E02.1080p.BluRay.mp4` | 多候选 | 开 | 开 | `NEEDS_CONFIRM`，有候选第一名 |
| D1-3 | `UnknownMovie.2099.mkv` | 无结果 | 开 | 开 | `NEEDS_CONFIRM`，无假 AI 作品 |
| D1-4 | `Attack.on.Titan.S01E02.mkv` | 多候选 | 关 | 关 | `NEEDS_CONFIRM`，说明 AI 不可用 |
| D1-5 | `Some.Movie.1080p.mkv` | 详情失败 | 开 | 关 | `NEEDS_CONFIRM` 或 minimal result，不纯 AI 兜底 |

### D2. 维度来源 × 信任开关

| dim source | trust 设置 | 期望 |
|---|---|---|
| `provider:tmdb` | 任意 | 可直接使用 |
| `file` | 任意 | 可直接使用 |
| `ai_assist` | trust=true | 可使用 |
| `ai_assist` | trust=false | 进入人工确认 |
| `ai_search` | trust=true | 可使用 |
| `ai_search` | trust=false | 进入人工确认 |
| `unknown` | 任意 | 进入人工确认或标记缺失 |

检查点：

- 任务详情显示每个维度来源。
- 不出现旧置信度。
- `confirm_reason` 说明“不信任 AI 来源”或“来源未知”。

### D3. 页面 × API

| 页面 | 必测 API | 期望 |
|---|---|---|
| 首页 / 任务页 | `/api/tasks` | 200 |
| 配置页 | `/api/config` | 200，无 prompts |
| AI 配置 | `/api/config/prompt-defaults` | 200 |
| Provider 配置 | `/api/providers` | 200 |
| Provider 搜索 | `/api/providers/tmdb/search` | 200 或合理错误 |
| 模拟测试 | `/api/scrape/preview/start` | 返回 job_id |
| 模拟测试轮询 | `/api/scrape/preview/status/{job_id}` | 返回 steps |
| 回收站 | `/api/recycle/list` | 200 |
| 源目录清理 | `/api/source-cleaner/status` | 200 |

## E. 任务流程回归

如果测试环境允许准备临时源目录，跑一次导入任务。

### E1. 单文件导入

文件：

```text
进击的巨人.S01E02.1080p.BluRay.mp4
```

步骤：

1. 放入源目录。
2. 触发扫描/导入。
3. 等待任务进入刮削阶段。
4. 查看任务卡片。
5. 如果需要确认，点击详情。

期望：

- 任务不崩溃。
- 任务状态正确。
- `NEEDS_CONFIRM` 时显示确认原因。
- 有候选结果。
- 显示 `dim_sources`。
- 不显示旧置信度。

### E2. Provider 无结果

文件：

```text
不存在的电影.2099.1080p.mp4
```

期望：

- 不使用 AI 伪造作品。
- 进入人工确认。
- 原因说明 Provider 无结果或无法唯一匹配。

## F. Playwright 执行建议

建议顺序：

1. `browser_navigate("http://127.0.0.1:9855/")`
2. `browser_console_messages(level="error")`
3. 检查页面文本是否包含旧词。
4. 点击配置页。
5. 等待 `/api/config`。
6. 点击 AI 配置。
7. 检查 prompt 字段。
8. 点击模拟测试。
9. 输入 `进击的巨人.S01E02.1080p.BluRay.mp4`。
10. 点击开始。
11. 每 2 秒 snapshot 一次，最多等 2 分钟。
12. 记录步骤文本。
13. 检查最终状态。

Playwright 失败时必须返回：

- 当前页面 snapshot。
- console errors。
- network failed requests。
- 最后一张截图。
- 测试停在哪一步。

## G. 结果报告模板

```markdown
# 测试结果报告

## 环境
- 分支/commit:
- 启动命令:
- 服务地址:
- 配置文件:
- 是否配置真实 TMDB:
- 是否配置真实 AI:

## A. 自动化回归
- compileall: PASS/FAIL
- legacy guard: PASS/FAIL
- key tests: PASS/FAIL
- full non-UI pytest: PASS/FAIL

## B. API 集成
| Case | 结果 | 备注 |
|---|---|---|
| /api/health | PASS/FAIL | |
| /api/config | PASS/FAIL | |
| /api/config/prompt-defaults | PASS/FAIL | |
| old prompt APIs | PASS/FAIL | |
| old /api/scrape/preview | PASS/FAIL | |
| preview start/status | PASS/FAIL | |

## C. Playwright 前端
| Case | 结果 | 备注 |
|---|---|---|
| 页面加载 | PASS/FAIL | |
| 配置页加载 | PASS/FAIL | |
| AI 配置页 | PASS/FAIL | |
| Provider 配置页 | PASS/FAIL | |
| 模拟测试进度 | PASS/FAIL | |
| NEEDS_CONFIRM 展示 | PASS/FAIL | |
| 无旧置信度文案 | PASS/FAIL | |

## D. 组合测试
| Case | 输入 | 期望 | 实际 | 结果 |
|---|---|---|---|---|

## 错误详情
- Console errors:
- Network errors:
- 后端日志:
- 截图路径:
- 复现步骤:

## 结论
- 是否可进入 scraper/ 整包迁移:
- 阻塞问题:
- 建议:
```

## H. 进入 `scraper/` 整包迁移的门槛

只有满足下面条件才建议进入：

- 自动化测试全绿。
- `/api/config`、AI 配置、Provider 配置、Preview job 全部通过。
- Playwright 模拟测试能看到阶段进度。
- `进击的巨人.S01E02.1080p.BluRay.mp4` 不再空等。
- `NEEDS_CONFIRM` 能显示候选第一名和确认原因。
- 前端不出现旧置信度/旧 prompt/旧 llm 文案。
- 至少一次真实或 mock 导入任务完成到 `DONE` 或 `NEEDS_CONFIRM`。

如果这些没过，不建议开始 `scraper/` 迁移。
