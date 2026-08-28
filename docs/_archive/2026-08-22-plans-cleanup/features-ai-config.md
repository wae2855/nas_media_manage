# AI 配置（ai-config）

## 概述

AI 配置界面划分为三个手风琴区域，每个区域独立折叠/展开，分别对应 API Key 配置、提示词配置和场景策略配置。

## 1. 三区域结构

### 区域 1：API Key 配置

- 两个 tab：**AI 辅助**（ai_assist）和 **AI 联网搜索增强**（ai_search）
- 每个 tab 独立的 API Key、Base URL、Model 等连接信息
- 每个 tab 独立【保存】按钮，各自 PUT `/api/config/section` ai_assist / ai_search
- 每个 tab 有独立的【测试连通性】按钮

### 区域 2：AI 提示词配置

- 5 个提示词 tab，对应 5 个 AI 场景
- 每个 tab 有：
  - 提示词编辑框
  - 功能说明折叠区（默认展开）
  - 【恢复默认】按钮（仅作用在当前 tab）
- 留空时使用 `PromptDefaults` 的内置真默认值

### 区域 3：AI 场景设置

- 5 行 × 2 列下拉框（primary / fallback）
- primary 必填（空时前端拦截保存）
- fallback 可选（空时只尝试 primary）
- 每个场景的默认值由 `config_loader.setdefault` 注入

## 2. 5 个场景

| # | 场景 key | 场景名 | primary 默认值 | 触发位置 |
|---|---------|--------|---------------|---------|
| 1 | `dimension_supplement` | 刮削缺失补充 | `ai_search` | Provider 命中但维度不全，且场景 2 失败后的兜底 |
| 2 | `dimension_mapping` | 刮削结果归类 | `ai_assist` | Provider 数据映射到本地维度体系 |
| 3 | `title_clean` | 文件标题清洗 | `ai_assist` | 从脏文件名提取干净标题，触发频率高 |
| 4 | `match_assist` | 影视名 AI 推测 | `ai_search` | Tier1 精确匹配失败后进入 Tier2 推测 |
| 5 | `source_clean` | 源目录清理分析 | `ai_assist` | 独立于刮削流程，由清理 API 触发 |

## 3. 多模型 Fallback

每个场景通过 `model_sequence` 解析为 `[primary]` 或 `[primary, fallback]`：
- primary 空时返回 `[]` → `_run_with_strategy_impl` 兜底到 `["ai_search"]` 并记录 `ai.scene.strategy_missing` 日志
- primary=fallback 时自动去重
- 未知场景抛 `ValueError`

共享实现在 `_run_with_strategy_impl`，负责：
- 多模型重试（先 primary 重试 `max_retries` 次，失败后切 fallback）
- 结构化日志（`ai.scene.*` 前缀）
- 提示词日志控制（`log_prompt` 字段）

## 4. 提示词默认值

事实源：`media_importer/features/prompts/defaults.py` 的 `PromptDefaults` 类

- 5 个默认提示词全部非空
- `PromptResolver` 的 `get_*_prompt()` 方法：用户配置为空时回退到 `PromptDefaults`
- 各使用点无内联兜底字符串

## 5. 配置默认值注入

`config_loader.load_config()` 中通过 `setdefault` 注入所有默认值，确保用户新配置不会遗漏任何字段：

- `ai_assist`：默认 `base_url=""`, `model=""`, `api_key=""`, `timeout=30`, `max_retries=2`, `retry_delay=3`
- `ai_search`：默认 `enabled=true`, `provider=""`, `model=""`, `api_key=""`
- `ai_scene_strategy`：5 场景的 primary/fallback 默认值见上表

## 6. 关键代码位置

| 组件 | 路径 |
|------|------|
| PromptDefaults | `media_importer/features/prompts/defaults.py` |
| PromptResolver | `media_importer/features/scraping/prompt_resolver.py` |
| SceneStrategyResolver | `media_importer/features/scraping/scene_strategy.py` |
| 共享 fallback 实现 | `media_importer/features/scraping/llm_client.py` |
| 配置加载 | `media_importer/core/config_loader.py` |
| ConfigView | `media_importer/core/config_view.py` |
| 前端 HTML | `media_importer/webui/index.html`（3 手风琴区域） |
| 前端 JS | `media_importer/webui/js/cinema-config-*.js`, `cinema-app-events.js` |
