---
title: "refactor: 移除 llm.enabled 开关，以字段完整度判定 AI 可用性"
type: plan
date: 2026-06-11
status: complete
confidence: high
related: docs/plans/2026-06-11-scrape-mode-provider-first-plan.md
---

# 移除 `llm.enabled` 开关

## 一句话摘要

移除前端 AI 刮削卡片中的"启用 AI 刮削"toggle 开关，AI 是否可用改为由三个必要字段（API Key、接口地址、模型ID）是否完整来判定。`ai_only` 和 `hybrid` 模式下 AI 未配置时自动降级为 `provider_first` 行为，而非返回空结果。

## 问题陈述

当前 `llm.enabled` 开关和 `scrape_mode` 形成**双重控制**：

| 用户意图 | 需要的操作 | 当前步骤 |
|---------|-----------|---------|
| 想用 AI 刮削 | 选 `ai_only` 或 `hybrid` | 1. 选模式 2. 开 AI 开关 3. 填 API Key/模型 |
| 不想用 AI | 选 `provider_first` | 1. 选模式 2. 关 AI 开关（多此一举） |

两个控制点互不知情，容易出现"选了 AI 模式但忘开开关"的困惑。且当前 `ai_only` 模式下 AI 不可用时直接返回空结果（confidence=0），用户体验差。

## 目标终态

1. **前端**：AI 刮削卡片不再有 toggle 开关，状态显示改为"已配置 / 未配置"（基于字段完整度）
2. **后端**：`LLMScraper.enabled` 只看 `is_configured()`（API Key + 接口地址 + 模型ID 都填了），忽略 `llm.enabled` 配置项
3. **降级**：`ai_only` 和 `hybrid` 模式下 AI 未配置时，自动降级为 `_scrape_provider_first()` 行为，而非返回空结果
4. **配置校验**：`ai_only` + AI 未配置 → error 阻止保存；`hybrid` + AI 未配置 → warning 提示
5. **向后兼容**：旧配置中 `llm.enabled: false` 但字段完整 → AI 变为可用（合理正向调整）

## 范围与非目标

**范围内：**
- `LLMConfig.is_effective()` 逻辑改为只看字段完整度
- `metadata_scrape_flow.py` 中 `_scrape_ai_only()` 和 `_scrape_hybrid()` 的 AI 不可用降级逻辑
- `config_validator.py` 中移除对 `llm.enabled` 的引用
- `config.yaml.example` 移除 `llm.enabled` 配置项
- 前端移除 toggle 开关，简化状态显示
- 新增降级场景的单元测试

**非目标：**
- 不修改 `LLMConfig` 数据类结构（`enabled` 字段保留但标记 deprecated）
- 不修改 `scrape_series_metadata()` 的降级逻辑（与单文件刮削保持一致即可）
- 不修改 `scrape_mode` 相关的任何逻辑
- 不修改 Provider 相关逻辑

## 方案详述

### 核心判定链变化

**改前：**
```
config.yaml llm.enabled: true/false
    → LLMConfig.is_effective() = enabled AND is_configured()
        → LLMScraper.enabled
            → ai_available 局部变量
```

**改后：**
```
config.yaml llm.api_key + llm.base_url + llm.model 是否都填了
    → LLMConfig.is_effective() = is_configured()（忽略 enabled 字段）
        → LLMScraper.enabled
            → ai_available 局部变量
```

### 降级行为矩阵

| scrape_mode | AI 已配置 | AI 未配置 |
|-------------|---------|----------|
| `provider_first` | Provider 为主，AI 补充缺失维度 | 纯 Provider（不变） |
| `ai_only` | 纯 AI 刮削 | **自动降级为 `_scrape_provider_first()`** + 日志警告 + trace 标记 |
| `hybrid` | Provider + AI 联合 | **自动降级为 `_scrape_provider_first()`** + 日志警告 + trace 标记 |

### 降级实现细节

在 `scrape_metadata()` 调度器中加入降级逻辑：

```python
def scrape_metadata(scraper, video_filename, ...):
    scrape_mode = getattr(scraper.view.metadata, "scrape_mode", "hybrid")
    if scrape_mode not in VALID_SCRAPE_MODES:
        scrape_mode = "hybrid"

    ai_available = scraper.llm_scraper.enabled

    # 降级：ai_only / hybrid 模式下 AI 不可用 → 自动切到 provider_first
    if scrape_mode in ("ai_only", "hybrid") and not ai_available:
        log.warning(
            f"[metadata_scraper] scrape_mode={scrape_mode} but AI not configured, "
            f"falling back to provider_first"
        )
        result = _scrape_provider_first(scraper, video_filename, subtitle_filenames, conn)
        _inject_trace_fields(result, scrape_mode, ai_invoked=False,
                             ai_invoke_reason="AI未配置-已降级为provider_first")
        return result

    if scrape_mode == "ai_only":
        return _scrape_ai_only(scraper, ...)
    elif scrape_mode == "provider_first":
        return _scrape_provider_first(scraper, ...)
    else:
        return _scrape_hybrid(scraper, ...)
```

**关键设计决定**：降级判断放在调度器中而非各模式函数内部。好处：
- 各模式函数内部不再需要 `if not ai_available: return minimal` 的重复代码
- 降级行为统一，`ai_only` 和 `hybrid` 都降级到 `provider_first`
- `_scrape_ai_only()` 可以简化（去掉 AI 不可用的分支）

### 前端改动

**移除的元素：**
- `cfg-llm_enabled` checkbox toggle 开关
- toggle 相关的说明文案（"Provider 刮削不够用时开启"等）

**保留的元素：**
- AI 刮削卡片（`#ai-scrape-card`）
- API Key / 接口地址 / 模型ID / 备选模型 等输入框
- 超时 / 重试 / 置信度阈值 等配置项
- 保存按钮

**状态显示变化：**

| 改前 | 改后 |
|------|------|
| toggle 开关 + 状态标签（未启用 / 已配置 / 未配置） | 仅状态标签（已配置 / 未配置），基于字段完整度 |
| 状态由 toggle + 字段共同决定 | 状态仅由字段完整度决定 |

**`updateAiConfigStatus()` 简化：**
```javascript
function updateAiConfigStatus() {
    const model = document.getElementById("cfg-llm_model")?.value?.trim();
    const apiKey = document.getElementById("cfg-llm_api_key")?.value?.trim();
    const baseUrl = document.getElementById("cfg-llm_base_url")?.value?.trim();
    const configured = !!(model && apiKey && baseUrl);

    const status = document.getElementById("ai-scrape-status");
    if (status) {
        status.textContent = configured ? "已配置" : "未配置";
        status.className = "config-collapse-status " + (configured ? "status-configured" : "status-unconfigured");
    }
}
```

**`buildLlmConfigPayload()` 简化：**
- 移除 `enabled` 字段（或始终设为 `true`，因为开关已不存在）

### 配置校验变化

| 场景 | 改前 | 改后 |
|------|------|------|
| `ai_only` + AI 未配置 | error（基于 `llm.enabled`） | error（基于字段完整度） |
| `hybrid` + AI 未配置 | warning（基于 `llm.enabled`） | warning（基于字段完整度） |
| `provider_first` + AI 未配置 | 无提示 | 无提示（不变） |

---

## 实施任务

### Phase 1: 后端核心逻辑

- [ ] **T1.1** `LLMConfig.is_effective()` 改为只看字段完整度
  - 文件：[config_view.py](file:///Users/wangwei/Documents/code/nas_media_manage/media_importer/core/config_view.py)
  - `is_effective()` 方法改为 `return self.is_configured()`（忽略 `self.enabled`）
  - `enabled` 字段保留但加注释标记 deprecated
  - 验收：`LLMConfig(enabled=False, api_key="sk-xxx", base_url="http://...", model="gpt-4").is_effective()` 返回 `True`

- [ ] **T1.2** `scrape_metadata()` 调度器加入降级逻辑
  - 文件：[metadata_scrape_flow.py](file:///Users/wangwei/Documents/code/nas_media_manage/media_importer/scraper/metadata_scrape_flow.py)
  - 在模式分发前检查：`scrape_mode in ("ai_only", "hybrid") and not ai_available` → 降级到 `_scrape_provider_first()`
  - trace 中注入 `ai_invoke_reason: "AI未配置-已降级为provider_first"`
  - 验收：`ai_only` + AI 未配置 → 实际走 `_scrape_provider_first()` 逻辑，trace 标记降级

- [ ] **T1.3** 简化 `_scrape_ai_only()` 和 `_scrape_hybrid()`
  - 文件：[metadata_scrape_flow.py](file:///Users/wangwei/Documents/code/nas_media_manage/media_importer/scraper/metadata_scrape_flow.py)
  - 移除 `_scrape_ai_only()` 中 `if not scraper.llm_scraper.enabled: return minimal` 分支（调度器已处理）
  - 移除 `_scrape_hybrid()` 中 `ai_available` 局部变量和所有 `if not ai_available` 分支
  - `_scrape_provider_first()` 保持不变（AI 不可用时已有完整的降级逻辑）
  - 验收：三个模式函数代码更简洁，`ai_only` 和 `hybrid` 不再包含 AI 不可用的死代码

- [ ] **T1.4** `scrape_series_metadata()` 适配
  - 文件：[metadata_scrape_flow.py](file:///Users/wangwei/Documents/code/nas_media_manage/media_importer/scraper/metadata_scrape_flow.py)
  - 同样在入口处加入降级逻辑：`ai_only` / `hybrid` + AI 未配置 → 降级到 `provider_first` 行为
  - 验收：剧集刮削三种模式下 AI 不可用时行为正确

- [ ] **T1.5** `config_validator.py` 适配
  - 文件：[config_validator.py](file:///Users/wangwei/Documents/code/nas_media_manage/media_importer/core/config_validator.py)
  - `ai_only` 检查改为基于字段完整度（`api_key` + `base_url` + `model` 是否都填了），而非 `llm.enabled`
  - `hybrid` 检查同理
  - 移除对 `llm.enabled` 的直接引用
  - 验收：`ai_only` + 字段缺失 → error；`hybrid` + 字段缺失 → warning

- [ ] **T1.6** `config.yaml.example` 移除 `llm.enabled`
  - 文件：[config.yaml.example](file:///Users/wangwei/Documents/code/nas_media_manage/config.yaml.example)
  - 删除 `enabled: true` 行
  - 加注释说明"AI 是否可用由 API Key、接口地址、模型ID 是否完整决定"
  - 验收：配置文件中无 `llm.enabled` 项

### Phase 2: 前端

- [ ] **T2.1** 移除 toggle 开关 HTML
  - 文件：[index.html](file:///Users/wangwei/Documents/code/nas_media_manage/media_importer/webui/index.html)
  - 删除 `#ai-scrape-card` 中的 `<label class="toggle-pill">` 及其内部 `<input id="cfg-llm_enabled">`
  - 删除 toggle 相关的说明文案（"Provider 刮削不够用时开启"等段落）
  - 验收：AI 刮削卡片中无 toggle 开关，无相关说明文案

- [ ] **T2.2** 简化 `updateAiConfigStatus()`
  - 文件：[cinema-app.js](file:///Users/wangwei/Documents/code/nas_media_manage/media_importer/webui/js/cinema-app.js)
  - 移除对 `cfg-llm_enabled` 的读取
  - 状态判定改为仅基于三个字段是否都填了
  - 移除 toggle 的 change 事件监听
  - 验收：状态标签正确显示"已配置 / 未配置"

- [ ] **T2.3** 简化 `buildLlmConfigPayload()`
  - 文件：[cinema-config.js](file:///Users/wangwei/Documents/code/nas_media_manage/media_importer/webui/js/cinema-config.js)
  - 移除 `enabled: !!document.getElementById("cfg-llm_enabled")?.checked`
  - 或始终设为 `enabled: true`（向后兼容旧配置读取）
  - 验收：保存配置时不再依赖 toggle 状态

- [ ] **T2.4** 配置加载时不再设置 toggle 状态
  - 文件：[cinema-app.js](file:///Users/wangwei/Documents/code/nas_media_manage/media_importer/webui/js/cinema-app.js)
  - 移除 `document.getElementById("cfg-llm_enabled").checked = ...` 行
  - 验收：页面加载时无 toggle 相关 JS 错误

- [ ] **T2.5** 清理 `config.js` 中的旧引用
  - 文件：[config.js](file:///Users/wangwei/Documents/code/nas_media_manage/media_importer/webui/js/config.js)
  - 移除 `cfg-llm_enabled` 的 checked 设置逻辑
  - 验收：无残留引用

### Phase 3: 测试

- [ ] **T3.1** `is_effective()` 单元测试（6 个用例）→ 详见 §3.2
- [ ] **T3.2** 调度器降级单元测试（5 个用例）→ 详见 §3.3
- [ ] **T3.3** 简化后模式函数测试（删除 1 旧 + 新增 2）→ 详见 §3.4
- [ ] **T3.4** `scrape_series_metadata()` 降级测试（2 个用例）→ 详见 §3.5
- [ ] **T3.5** 配置校验测试（2 个新用例）→ 详见 §3.6
- [ ] **T3.6** 回归测试（全量 `pytest tests/ -v`）→ 详见 §3.7

#### 3.1 测试策略总览

| 层级 | 测试文件 | 新增/修改 | 用例数 | 覆盖目标 |
|------|---------|----------|--------|---------|
| 单元 | `tests/test_config_view.py` | 修改 | +3 | `is_effective()` 新判定逻辑 |
| 单元 | `tests/test_scrape_mode.py` | 修改 | +8 | 调度器降级 + 模式函数简化 + 配置校验 |
| 单元 | `tests/test_scrape_mode.py` | 修改 | +2 | `scrape_series_metadata()` 降级 |
| 回归 | `tests/` 全量 | 不改 | 387+ | 确保无回归 |

---

#### 3.2 单元测试：`is_effective()` 只看字段完整度

**文件**：[tests/test_config_view.py](file:///Users/wangwei/Documents/code/nas_media_manage/tests/test_config_view.py)（修改，在 `TestConfigViewDefaults` 类中新增 3 个方法）

**测试类**：`TestLLMConfigIsEffective`（新建，使用 `unittest` 风格与现有测试文件一致）

| # | 测试方法 | 输入 | 期望 | 覆盖场景 |
|---|---------|------|------|---------|
| 1 | `test_effective_when_configured_even_if_disabled` | `LLMConfig(enabled=False, api_key="sk-xxx", base_url="http://x", model="gpt-4")` | `is_effective() → True` | enabled=false 但字段完整 → 仍判定为可用 |
| 2 | `test_not_effective_when_api_key_missing` | `LLMConfig(enabled=True, api_key="", base_url="http://x", model="gpt-4")` | `is_effective() → False` | 缺少 api_key → 不可用 |
| 3 | `test_not_effective_when_model_missing` | `LLMConfig(enabled=True, api_key="sk-xxx", base_url="http://x", model="")` | `is_effective() → False` | 缺少 model → 不可用 |
| 4 | `test_not_effective_when_base_url_missing` | `LLMConfig(enabled=True, api_key="sk-xxx", base_url="", model="gpt-4")` | `is_effective() → False` | 缺少 base_url → 不可用 |
| 5 | `test_effective_when_all_filled_enabled_true` | `LLMConfig(enabled=True, api_key="sk-xxx", base_url="http://x", model="gpt-4")` | `is_effective() → True` | 全部完整 + enabled=true → 可用（正向） |
| 6 | `test_effective_when_all_filled_enabled_false` | `LLMConfig(enabled=False, api_key="sk-xxx", base_url="http://x", model="gpt-4")` | `is_effective() → True` | 全部完整 + enabled=false → 仍可用（核心变化） |

**Mock 依赖**：无。`LLMConfig` 是纯数据类，不需要 mock。

**验收**：6 个测试全部通过。

---

#### 3.3 单元测试：调度器降级逻辑

**文件**：[tests/test_scrape_mode.py](file:///Users/wangwei/Documents/code/nas_media_manage/tests/test_scrape_mode.py)（修改，新增测试类）

**测试类**：`TestScrapeMetadataDegradation`（使用 `pytest` 风格与现有测试文件一致）

**通用 Mock 策略**：每个测试用例构建一个 `scraper` mock，关键属性：
- `scraper.view.metadata.scrape_mode` — 控制模式
- `scraper.llm_scraper.enabled` — 控制 AI 是否可用
- `scraper._cleaner.clean()` — 返回 `CleanResult` mock
- `scraper._search_all_providers()` — 返回 `(None, [])`（无 Provider 结果）
- `scraper.confidence_engine.calculate_ai_only()` — 返回 `ConfidenceResult` mock
- `scraper.llm_scraper.scrape()` — 返回基础刮削结果

| # | 测试方法 | scrape_mode | AI 可用 | 期望行为 | 验证点 |
|---|---------|------------|---------|---------|--------|
| 1 | `test_ai_only_without_ai_falls_back_to_provider_first` | `ai_only` | `False` | 实际执行 `_scrape_provider_first()` 逻辑 | 1) `_search_all_providers` 被调用（证明走了 provider_first）；2) trace 中 `scrape_mode="ai_only"`（保留原始模式）；3) trace 中 `ai_invoke_reason` 包含"降级" |
| 2 | `test_hybrid_without_ai_falls_back_to_provider_first` | `hybrid` | `False` | 实际执行 `_scrape_provider_first()` 逻辑 | 同上 |
| 3 | `test_provider_first_without_ai_no_degradation` | `provider_first` | `False` | 正常走 `_scrape_provider_first()` | 1) 不被调度器拦截；2) trace 中 `scrape_mode="provider_first"`；3) `ai_invoke_reason` 不包含"降级" |
| 4 | `test_ai_only_with_ai_no_degradation` | `ai_only` | `True` | 正常走 `_scrape_ai_only()` | 1) `_search_all_providers` 不被调用（ai_only 不调 Provider）；2) `llm_scraper.scrape()` 被调用 |
| 5 | `test_hybrid_with_ai_no_degradation` | `hybrid` | `True` | 正常走 `_scrape_hybrid()` | 1) `_search_all_providers` 被调用；2) `llm_scraper.scrape()` 被调用 |

**关键实现细节**：
- 测试 1、2 中需要验证 `_search_all_providers` 被调用（证明降级到了 provider_first，而 provider_first 会调 Provider 搜索）
- 测试 4 中需要验证 `_search_all_providers` **不被调用**（ai_only 正常路径不调 Provider）
- 使用 `patch("media_importer.scraper.metadata_scrape_flow._get_enabled_dims", return_value=None)` 避免数据库依赖

**验收**：5 个测试全部通过。

---

#### 3.4 单元测试：简化后的模式函数

**文件**：[tests/test_scrape_mode.py](file:///Users/wangwei/Documents/code/nas_media_manage/tests/test_scrape_mode.py)（修改，在现有 `TestAiOnlyMode` 类中修改 + 新增 `TestHybridModeSimplified` 类）

**3.4.1 修改 `TestAiOnlyMode`**

| # | 测试方法 | 改动 | 说明 |
|---|---------|------|------|
| 1 | `test_ai_only_llm_disabled` | **删除** | 调度器已处理降级，此测试不再有意义 |
| 2 | `test_ai_only_llm_error` | **保留** | LLM 调用异常仍需测试（`LLMScrapeError` 异常处理） |
| 3 | `test_ai_only_no_provider_search` | **保留** | 验证 ai_only 不调 Provider |
| 4 | `test_ai_only_with_year_suspect` | **保留** | 验证年份可疑时 ai_clean |

**3.4.2 新增 `TestHybridModeSimplified`**

| # | 测试方法 | 输入 | 期望 | 覆盖场景 |
|---|---------|------|------|---------|
| 1 | `test_hybrid_with_provider_result_calls_ai` | AI 可用 + Provider 有结果 | `llm_scraper.scrape_with_context()` 被调用 | hybrid 正常路径：Provider + AI 联合 |
| 2 | `test_hybrid_without_provider_result_calls_ai` | AI 可用 + Provider 无结果 | `llm_scraper.scrape()` 被调用 | hybrid 降级：无 Provider 时纯 AI |

**注意**：`_scrape_hybrid()` 简化后不再有 `if not ai_available` 分支（调度器已处理），所以不需要测试"AI 不可用"场景——那已由调度器降级测试覆盖。

**验收**：删除 1 个旧测试，保留 3 个旧测试，新增 2 个测试，共 5 个全部通过。

---

#### 3.5 单元测试：`scrape_series_metadata()` 降级

**文件**：[tests/test_scrape_mode.py](file:///Users/wangwei/Documents/code/nas_media_manage/tests/test_scrape_mode.py)（修改，新增测试类）

**测试类**：`TestScrapeSeriesMetadataDegradation`

| # | 测试方法 | scrape_mode | AI 可用 | 期望 |
|---|---------|------------|---------|------|
| 1 | `test_series_ai_only_without_ai_falls_back` | `ai_only` | `False` | 走 provider_first 路径（尝试 Provider 搜索），trace 标记降级 |
| 2 | `test_series_hybrid_without_ai_falls_back` | `hybrid` | `False` | 同上 |

**Mock 策略**：
- `scraper.providers` 包含一个 mock provider（`search()` 返回空，触发 AI 降级路径）
- `scraper.llm_scraper.scrape_series()` mock 返回基础结果
- 验证 Provider 搜索被尝试（证明降级到了 provider_first 路径）

**验收**：2 个测试全部通过。

---

#### 3.6 单元测试：配置校验

**文件**：[tests/test_scrape_mode.py](file:///Users/wangwei/Documents/code/nas_media_manage/tests/test_scrape_mode.py)（修改，在现有 `TestConfigValidatorScrapeMode` 类中新增 2 个方法）

| # | 测试方法 | 配置 | 期望 |
|---|---------|------|------|
| 1 | `test_ai_only_without_llm_fields_is_error` | `scrape_mode="ai_only"`, `llm.api_key=""`, `llm.base_url=""`, `llm.model=""` | `validate_config()` 返回 error（基于字段缺失） |
| 2 | `test_hybrid_without_llm_fields_is_warning` | `scrape_mode="hybrid"`, `llm.api_key=""`, `llm.base_url=""`, `llm.model=""` | `validate_config()` 返回 warning（基于字段缺失） |

**注意**：现有 `test_invalid_scrape_mode` 和 `test_valid_scrape_mode` 保持不变，它们测试的是 `scrape_mode` 值本身的有效性，不涉及 LLM 配置。

**验收**：2 个新测试 + 2 个旧测试 = 4 个全部通过。

---

#### 3.7 回归测试

**命令**：`cd /Users/wangwei/Documents/code/nas_media_manage && PYTHONPATH=. python -m pytest tests/ -v`

**重点关注文件**（按风险排序）：

| 优先级 | 测试文件 | 原因 | 预期 |
|--------|---------|------|------|
| P0 | `tests/test_scrape_mode.py` | 本次核心改动，新增 + 修改测试最多 | 全部通过 |
| P0 | `tests/test_config_view.py` | `is_effective()` 改动影响 `ConfigView` 行为 | 全部通过 |
| P1 | `tests/test_confidence_engine.py` | 置信度引擎依赖 `LLMScraper.enabled` 判定 | 全部通过 |
| P1 | `tests/test_def_cart_08_config_missing.py` | 测试无 API Key 场景，`is_effective()` 变化可能影响 | 全部通过 |
| P1 | `tests/test_def_pipe_03_scrape.py` | 测试无 Provider + LLM 关闭时的实例化 | 全部通过 |
| P2 | `tests/test_feature_import_flow.py` | 导入流程中可能间接依赖 `ai_available` | 全部通过 |
| P2 | `tests/test_feature_providers.py` | Provider 逻辑不变，但需确认无间接影响 | 全部通过 |
| P2 | `tests/test_scrape_ui.py` | 前端 Playwright 测试，toggle 移除后选择器可能失效 | 可能需要更新选择器 |
| P3 | `tests/` 其余文件 | 低风险，但需全量跑一次 | 全部通过 |

**回归测试检查清单**：

- [ ] `test_scrape_mode.py` — 所有测试通过（含新增 + 修改）
- [ ] `test_config_view.py` — 所有测试通过（含新增 `is_effective` 测试）
- [ ] `test_confidence_engine.py` — 无回归
- [ ] `test_def_cart_08_config_missing.py` — 无回归（确认 `is_effective` 变化不影响该测试的断言）
- [ ] `test_def_pipe_03_scrape.py` — 无回归
- [ ] `test_feature_import_flow.py` — 无回归
- [ ] `test_feature_providers.py` — 无回归
- [ ] `test_scrape_ui.py` — 如失败，更新 Playwright 选择器（移除 `cfg-llm_enabled` 引用）
- [ ] `tests/` 全量 — `387+ passed, 0 failed`

**如果回归测试发现失败**：
1. 优先修复本次改动引入的问题
2. 如果失败是预期行为变化（如 `test_def_cart_08_config_missing.py` 中期望 `is_effective=False` 但新逻辑返回 `True`），更新测试断言以匹配新行为
3. 记录所有因行为变化导致的测试修改

---

#### 3.8 测试用例汇总

| 测试文件 | 新增 | 修改 | 删除 | 最终用例数变化 |
|---------|------|------|------|-------------|
| `tests/test_config_view.py` | +6 | 0 | 0 | +6 |
| `tests/test_scrape_mode.py` | +9 | 0 | -1 | +8 |
| **合计** | **+15** | **0** | **-1** | **+14** |

**新增的 15 个测试用例覆盖：**
- `is_effective()` 6 种字段组合
- 调度器降级 5 种模式 × AI 可用性组合
- 简化后 hybrid 模式 2 种路径
- 剧集刮削降级 2 种场景
- 配置校验 2 种场景（已扣除重复计入的 2 个）

---

## 对现有代码的影响评估

| 文件 | 改动类型 | 影响范围 | 风险 |
|------|---------|---------|------|
| [config_view.py](file:///Users/wangwei/Documents/code/nas_media_manage/media_importer/core/config_view.py) | 修改 1 行 | `is_effective()` 判定逻辑 | **中** — 影响所有依赖 `LLMScraper.enabled` 的代码 |
| [metadata_scrape_flow.py](file:///Users/wangwei/Documents/code/nas_media_manage/media_importer/scraper/metadata_scrape_flow.py) | 重构 | 调度器 + 两个模式函数 | **高** — 刮削核心入口，降级逻辑必须正确 |
| [config_validator.py](file:///Users/wangwei/Documents/code/nas_media_manage/media_importer/core/config_validator.py) | 修改 | 配置校验 | 低 — 仅改判定条件 |
| [config.yaml.example](file:///Users/wangwei/Documents/code/nas_media_manage/config.yaml.example) | 删除 1 行 | 配置模板 | 极低 |
| [index.html](file:///Users/wangwei/Documents/code/nas_media_manage/media_importer/webui/index.html) | 删除 + 修改 | AI 刮削卡片 UI | 低 — 仅删除元素 |
| [cinema-app.js](file:///Users/wangwei/Documents/code/nas_media_manage/media_importer/webui/js/cinema-app.js) | 简化 | 状态更新逻辑 | 低 — 代码减少 |
| [cinema-config.js](file:///Users/wangwei/Documents/code/nas_media_manage/media_importer/webui/js/cinema-config.js) | 简化 | 配置保存 payload | 低 — 移除 1 个字段 |
| [config.js](file:///Users/wangwei/Documents/code/nas_media_manage/media_importer/webui/js/config.js) | 删除 | 旧版配置加载 | 极低 |

---

## 决策理由

### 为什么降级放在调度器而非各模式函数内部？

1. **单一职责**：调度器负责"选模式 + 降级"，模式函数负责"执行刮削"
2. **消除死代码**：`_scrape_ai_only()` 中 `if not enabled: return minimal` 在降级后永远不会执行
3. **统一降级目标**：`ai_only` 和 `hybrid` 都降级到 `provider_first`，而非各自返回空结果
4. **trace 一致性**：降级标记在调度器统一注入，不会遗漏

### 为什么 `_scrape_provider_first()` 内部仍保留 `ai_available` 检查？

`provider_first` 模式下 AI 不可用是**正常情况**（用户可能故意不配 AI），不是降级。内部保留 `ai_available` 检查是为了在 AI 不可用时跳过 AI 补充步骤，这是设计意图而非异常路径。

### 为什么 `llm.enabled` 字段保留而非删除？

向后兼容。旧配置文件可能包含 `llm.enabled: false`，如果删除字段会导致 YAML 解析警告。保留字段但忽略其值是最安全的做法。

---

## 假设审计

| 假设 | 状态 | 证据 |
|------|------|------|
| `LLMConfig.is_configured()` 的判定逻辑（api_key + base_url + model 都非空）能准确反映"AI 可用" | 已验证 | [config_view.py:L100-103](file:///Users/wangwei/Documents/code/nas_media_manage/media_importer/core/config_view.py#L100-L103) |
| `_scrape_provider_first()` 在 AI 不可用时能正常工作 | 已验证 | 当前代码中已有完整的 `ai_available` 检查分支 |
| 前端 `updateAiConfigStatus()` 的监听器列表中没有其他依赖 `cfg-llm_enabled` 的逻辑 | 待验证 | 需要在 T2.2 实施时确认 |
| `config.js` 是旧版代码，移除引用不影响主流程 | 待验证 | 需要确认 `config.js` 是否仍被加载 |

---

## 风险分析

| 风险 | 可能性 | 影响 | 缓解措施 |
|------|--------|------|---------|
| 旧配置 `llm.enabled: false` + 字段完整 → AI 被意外启用 | 低 | 中 — 用户可能不想用 AI 但被强制启用 | 用户可通过切换 `scrape_mode` 到 `provider_first` 来禁用 AI；这是合理的正向调整 |
| 降级逻辑错误导致 `ai_only` 降级后行为异常 | 低 | 高 — 刮削结果错误 | T3.2 完整测试降级场景 |
| `_scrape_hybrid()` 简化时误删了 Provider-only 分支 | 中 | 高 — hybrid 模式下 AI 不可用时无结果 | T1.3 仔细审查，保留 Provider-only 构建逻辑 |
| 前端移除 toggle 后旧缓存导致 JS 错误 | 低 | 低 — 控制台报错但不影响功能 | T2.4 移除所有 `cfg-llm_enabled` 引用 |

---

## 验收标准

1. **AI 可用性判定**：仅由 API Key + 接口地址 + 模型ID 是否完整决定，`llm.enabled` 不再影响
2. **降级行为**：`ai_only` / `hybrid` + AI 未配置 → 自动走 `provider_first` 逻辑，trace 标记降级
3. **前端 UI**：AI 刮削卡片无 toggle 开关，状态显示"已配置 / 未配置"
4. **配置校验**：`ai_only` + 字段缺失 → error；`hybrid` + 字段缺失 → warning
5. **向后兼容**：旧配置 `llm.enabled: false` + 字段完整 → AI 可用（正向调整）
6. **测试覆盖**：新增 9 个测试全部通过，全部现有测试无回归
