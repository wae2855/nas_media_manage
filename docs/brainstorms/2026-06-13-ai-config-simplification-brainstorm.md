---
title: "AI 配置简化与服务商预设模型"
type: brainstorm
date: 2026-06-13
status: superseded
participants: [用户, AI]
related:
  - docs/_archive/2026-06-17-plans-cleanup/2026-06-12-refactor-three-tier-matching-plan.md
  - docs/decisions/0005-three-tier-matching.md
---

# AI 配置简化与服务商预设模型

## 问题陈述

当前 AI 配置界面存在以下问题：

1. **刮削模式选择已无意义** — 三级匹配策略后，系统固定 Provider 优先，`provider_first` / `ai_only` 下拉框和配套说明文字是冗余的
2. **AI 配置字段过多** — 两个区块（AI 辅助 + AI 搜索增强）共 12+ 个字段，用户不知道填什么
3. **模型选择是自由文本** — 用户需要自己知道模型 ID（如 `glm-4-flash`），容易填错
4. **搜索模式区分用户不懂** — 智谱的 Search_std / Search_pro 等概念对普通用户不友好
5. **接口地址需要手动填写** — 用户需要记住各厂商的 API 地址
6. **没有总开关** — 用户觉得花钱多时无法一键关闭 AI

## 上下文

### 当前配置结构

**刮削配置区**（`data-config-panel="scrape"`）：
- 刮削模式下拉框（`provider_first` / `ai_only`）+ 大段说明文字
- Provider 配置卡片（TMDB 等）

**AI 配置区**（`data-config-panel="ai"`）：
- 区块一：AI 辅助 — 辅助模型ID、清理模型ID、接口地址、API Key（4 字段）
- 区块二：AI 搜索增强 — API Key、接口地址、刮削模型ID、备选模型ID、超时/重试/置信度阈值/SSL（8+ 字段）

### 当前 YAML 配置

```yaml
llm:
  api_key: ""
  base_url: "https://api.openai.com/v1"
  model: "gpt-3.5-turbo"
  fallback_model: "gpt-3.5-turbo"
  fast_model: ""
  fast_base_url: ""
  fast_api_key: ""
  source_cleaner_model: ""
  confidence_threshold: 0.8
  timeout: 30
  max_retries: 2
  retry_delay: 3
  verify_ssl: true
  web_search:
    enabled: false
    provider: "none"
```

### 相关代码

- `web_search_config.py` — 根据 base_url 自动检测服务商（zhipu/qwen/moonshot）
- `llm_scraper.py` — LLM 调用核心
- `metadata_scrape_flow.py` — 刮削流程分发
- `cinema-config.js` — 前端配置构建和保存
- `config_loader.py` — 配置加载
- `config_migrations.py` — 配置迁移

## 选择方案

### 方案概览

将刮削配置区和 AI 配置区合并简化为一个清晰的「AI 配置」面板：

1. **移除刮削模式选择** — 固定 Provider 优先，加一句提示
2. **服务商预设** — 下拉选择服务商 → 自动填充接口地址和模型列表
3. **模型下拉** — 根据服务商动态展示可选模型
4. **搜索模式下拉** — 所有厂商都显示，无区分的默认选「标准」
5. **总开关** — 一键关闭 AI，只走 Provider 刮削
6. **辅助模型默认复用** — 大多数用户用同一个模型

### 为什么选择这个方案

- **用户认知负担最低**：从 12+ 字段减少到 4-5 个核心字段
- **防错**：下拉选择不会填错模型 ID 和接口地址
- **成本可控**：总开关让用户随时关闭 AI
- **行业惯例**：Plex/Jellyfin 的 AI 配置都是服务商选择 + 模型下拉，没有自由文本

## 关键设计决策

### Q1: 刮削模式 — RESOLVED
**决策**：移除刮削模式下拉框和配套说明
**理由**：三级匹配策略后，系统固定 Provider 优先，用户不需要选择
**替代方案**：保留但禁用 → 增加困惑，不如直接移除

### Q2: 配置区块名 — RESOLVED
**决策**：新建 `ai:` 区块替代 `llm:`，历史数据直接清空
**理由**：`ai:` 更直观，`llm:` 是技术术语；用户明确表示不用考虑历史数据
**替代方案**：沿用 `llm:` 区块名只改内部字段 → 语义不匹配

### Q3: 高级参数 — RESOLVED
**决策**：全部移除（超时/重试/备选模型/置信度阈值），用合理默认值
**理由**：三级匹配后置信度阈值不再有意义；超时/重试参数 99% 用户不会改
**替代方案**：折叠到高级设置区 → 增加复杂度，后续有需求再加

### Q4: 搜索模式展示 — RESOLVED
**决策**：所有厂商都显示搜索模式下拉
**理由**：统一体验，没有区分的厂商默认选「标准」即可
**替代方案**：仅智谱显示 → 不一致，用户会困惑为什么有时有有时没有

### Q5: 辅助模型配置 — RESOLVED
**决策**：默认复用搜索增强模型，取消勾选后展开独立配置
**理由**：大多数用户用同一个模型就够了，减少配置项
**替代方案**：始终分开配置 → 字段多，用户困惑

## 新配置结构

### YAML 配置

```yaml
ai:
  enabled: true                      # 总开关：关闭后只使用 Provider 刮削
  provider: "zhipu"                  # 服务商标识
  search_mode: "std"                 # 搜索模式：std(标准) / pro(增强)
  api_key: ""                        # API Key
  base_url: ""                       # 自动填充，自定义时可改
  model: "glm-4-flash"              # 模型ID（下拉选择或手动输入）
  fast_model_same: true              # 辅助模型是否与搜索增强共用
  fast_provider: ""                  # 辅助模型服务商（仅 fast_model_same=false 时）
  fast_model: ""                     # 辅助模型ID（仅 fast_model_same=false 时）
  fast_api_key: ""                   # 辅助模型 API Key（仅 fast_model_same=false 时）
  verify_ssl: true                   # SSL 验证
```

### 服务商预设表

| 服务商 | provider 值 | base_url | 模型列表 | 搜索模式 |
|--------|------------|----------|----------|----------|
| 智谱 GLM | `zhipu` | `https://open.bigmodel.cn/api/paas/v4` | glm-4-flash, glm-4-air, glm-4-plus | std / pro |
| 通义千问 | `qwen` | `https://dashscope.aliyuncs.com/compatible-mode/v1` | qwen-turbo, qwen-plus, qwen-max | std(默认) |
| Kimi / Moonshot | `moonshot` | `https://api.moonshot.cn/v1` | moonshot-v1-8k, moonshot-v1-32k | std(默认) |
| DeepSeek | `deepseek` | `https://api.deepseek.com/v1` | deepseek-chat, deepseek-reasoner | std(默认) |
| OpenAI | `openai` | `https://api.openai.com/v1` | gpt-4o-mini, gpt-4o | std(默认) |
| 自定义 | `custom` | （手动输入） | （手动输入） | std(默认) |

### 前端布局

```
┌─ AI 配置 ──────────────────────────────────────────────────┐
│                                                             │
│  [总开关] 启用 AI 辅助刮削                                   │
│  关闭后系统仅使用 Provider 刮削，不调用任何 AI 模型            │
│                                                             │
│  ── 搜索增强模型 ──────────────────────────────              │
│  用于刮削匹配、维度补缺、联网搜索                             │
│                                                             │
│  服务商：[智谱 GLM ▼]                                       │
│  模型：  [glm-4-flash ▼]                                    │
│  搜索模式：[标准搜索 ▼]                                      │
│  API Key：[••••••••]                                        │
│  接口地址：https://open.bigmodel.cn/api/paas/v4（自动填充）   │
│                                                             │
│  ── 辅助模型 ─────────────────────────────────              │
│  用于标题清洗、数据整理、源目录清理等轻量任务                   │
│                                                             │
│  [✓] 与搜索增强使用同一模型                                  │
│  取消勾选后展开：                                            │
│    服务商：[通义千问 ▼]                                      │
│    模型：  [qwen-turbo ▼]                                   │
│    API Key：[••••••••]（留空则用搜索增强的）                  │
│                                                             │
│  [测试连通性]  [AI 搜索增强测试]                              │
│                                                             │
│  ── 使用场景说明 ──                                         │
│  ① 第二级匹配：Provider 未精确匹配时，AI 辅助判断             │
│  ② 维度补缺：Provider 数据不完整时，AI 补充缺失维度           │
│  ③ 标题清洗：从文件名提取影视标题                             │
│  ④ 源目录清理：AI 辅助判断垃圾文件                            │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### 刮削配置区简化

移除刮削模式下拉框和大段说明，只保留：
- Provider 配置卡片（TMDB 等）
- 一句提示：「系统默认 Provider 优先：精确匹配自动入库，模糊匹配 AI 辅助，无法确定时人工确认。」

## 假设审计

| 假设 | 分类 | 证据 |
|------|------|------|
| 服务商预设的 base_url 和模型列表足够覆盖用户需求 | 未验证 | 需确认各厂商 API 地址和模型名称的稳定性 |
| 移除高级参数后不会影响功能 | 基岩 | 超时/重试用合理默认值不影响核心功能；置信度阈值在三级匹配后不再使用 |
| 用户不需要同时配置两个不同厂商的模型 | 弱 | 大多数用户只用一个厂商，但高级用户可能用不同厂商的辅助模型 |
| 搜索模式对所有厂商都有意义 | 未验证 | 通义/DeepSeek 等是否有搜索模式区分需要确认 |

## 开放问题

1. **通义千问/DeepSeek 等是否有搜索模式区分？** — 如果没有，搜索模式下拉对它们是冗余的，但统一展示也不会造成困惑
2. **`source_cleaner_model` 是否保留？** — 当前有独立的源目录清理模型配置，新方案中默认复用辅助模型，是否需要单独配置？
3. **服务商预设表是否需要后端 API 动态获取？** — 还是硬编码在前端？硬编码更简单但需要随厂商更新

## 范围外

- 不改变 Provider 抽象和 TMDB 客户端
- 不改变三级匹配引擎逻辑
- 不改变文件操作/入库流程
- 不重新设计前端整体布局
- 不处理旧 `llm:` 配置的自动迁移（用户明确表示历史数据直接清空）

## 下一步

- `/plan` 创建实施计划
