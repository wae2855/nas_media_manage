---
title: "feat: 刮削模式（Scrape Mode）— AI与Provider优先级与互斥"
type: plan
date: 2026-06-11
status: complete
confidence: high
---

# 刮削模式（Scrape Mode）实施计划

## 一句话摘要

新增 `scrape_mode` 配置项（`provider_first` / `ai_only` / `hybrid`），让用户控制AI刮削与Provider刮削的优先级和互斥关系，`provider_first` 模式下Provider维度完整时跳过AI调用，维度缺失时AI精准补充。

## 问题陈述

当前刮削流程是固定的协作模式：只要Provider和AI都启用，每个文件必然走 Provider搜索→Provider详情→AI联合刮削 的完整链路。这导致：

1. **成本不可控**：Provider维度值已完整时（如TMDb返回了所有genre/country/certification），仍调用AI做维度补充
2. **无法选模式**：用户无法选择"只用Provider"或"只用AI"
3. **结果来源模糊**：维度值可能来自Provider、AI或两者混合，`hybrid`模式下AI结果会覆盖Provider已确定的维度值
4. **维度完整度判断缺失**：Provider映射可能返回 `value=None`（如TMDb无release_dates时restricted_level为None），当前代码无条件调AI补充，无法区分"Provider已确定"和"Provider未提供"

## 目标终态

1. 用户可在前端配置页选择刮削模式，三种模式行为清晰
2. `provider_first` 模式下，Provider维度值全部非None时跳过AI，有None时AI只补充缺失维度
3. `ai_only` 模式下完全跳过Provider搜索
4. `hybrid` 模式保持当前行为不变
5. 模拟对比（`/api/scrape/preview`）不受模式限制
6. 所有现有测试通过，新增测试覆盖三种模式

## 范围与非目标

**范围内：**
- 后端 `scrape_metadata()` 拆分为三种模式分支
- `ConfigView` / `config.yaml` 新增 `scrape_mode` 字段
- 前端配置页新增模式选择UI
- 维度完整度检查逻辑
- `scrape_trace` 追踪增强
- 单元测试、集成测试、回归测试

**非目标：**
- 不新增Provider类型（仍只有TMDb）
- 不修改维度数据结构或数据库schema
- 不修改置信度引擎的计算公式
- 不修改模拟预览的并行逻辑

## 方案详述

### 三种模式定义

| 模式 | 值 | 行为 | AI调用频率 |
|------|---|------|-----------|
| Provider优先 | `provider_first` | Provider搜索→详情→维度映射；维度完整则不调AI；缺失则AI精准补充；Provider无结果则降级纯AI | 低~中 |
| 纯AI | `ai_only` | 跳过Provider，纯AI刮削 | 高 |
| 混合 | `hybrid` | 当前行为，Provider+AI联合 | 高 |

### 维度完整度检查（核心逻辑）

```python
def _check_dimension_completeness(provider_dimensions: dict, enabled_dims: set) -> dict:
    provider_covered = set()
    missing_dims = set()
    for dim_name in enabled_dims:
        dim_info = provider_dimensions.get(dim_name)
        if dim_info and dim_info.get("value") is not None:
            provider_covered.add(dim_name)
        else:
            missing_dims.add(dim_name)
    return {
        "complete": len(missing_dims) == 0,
        "missing_dims": missing_dims,
        "provider_covered": provider_covered,
    }
```

**关键**：检查基于 `value is not None`，不是维度名存在。Provider映射返回 `value=None` 算缺失。

### 各模式数据流

#### provider_first 模式

```
文件名 → 正则清洗
  ├─ year_suspect=True → ai_clean(fast_model) → Provider搜索
  └─ year_suspect=False → Provider搜索
       ├─ Provider匹配(T ≥ 阈值)
       │   ├─ Provider详情 → 维度映射
       │   ├─ 维度完整度检查
       │   │   ├─ complete=True → 直接构建结果，不调AI
       │   │   └─ complete=False → scrape_with_context(exclude_dims=provider_covered)
       │   └─ confidence_engine.calculate()
       ├─ Provider匹配度低(T < 阈值)
       │   ├─ ai_clean(fast_model) → 重新Provider搜索
       │   └─ 同上处理
       └─ Provider无结果 → 纯AI刮削(model) → confidence_engine.calculate_ai_only()
```

#### ai_only 模式

```
文件名 → 正则清洗
  ├─ year_suspect=True → ai_clean(fast_model)
  └─ 纯AI刮削(model) → confidence_engine.calculate_ai_only()
```

#### hybrid 模式

```
= 当前 scrape_metadata() 的完整逻辑，不做任何修改
```

### 默认值策略

| 场景 | 默认 scrape_mode |
|------|-----------------|
| 新安装（无旧配置） | `provider_first` |
| 旧配置无 scrape_mode 字段 | `hybrid`（向后兼容） |

### scrape_trace 追踪增强

在 `scrape_trace` 中新增字段：

```python
trace = {
    "scrape_mode": "provider_first",   # 新增：当前使用的模式
    "ai_invoked": True,                # 新增：是否实际调用了AI
    "ai_invoke_reason": "维度不完整",    # 新增：调用AI的原因
    # ... 现有字段不变
}
```

| ai_invoke_reason 值 | 含义 |
|---------------------|------|
| `"维度不完整"` | Provider维度未覆盖所有启用维度 |
| `"Provider无结果"` | Provider搜索无匹配 |
| `"Provider详情失败"` | Provider详情获取异常 |
| `"标题清洗"` | year_suspect或匹配度低时的AI清洗 |
| `None` | 未调用AI（Provider数据完整） |

### 模拟对比不受模式限制

`/api/scrape/preview` 端点始终并行跑纯AI和Provider+AI两条路径，与 `scrape_mode` 配置无关。理由：模拟对比的目的是让用户看到两种方式的结果差异，帮助决定使用哪种模式。

---

## 实施任务

### Phase 1: 后端核心逻辑（数据加工流改造）

- [ ] **T1.1** ConfigView 新增 `scrape_mode` 字段
  - 文件：`media_importer/core/config_view.py`
  - `MetadataProviderConfig` dataclass 新增 `scrape_mode: str = "hybrid"`
  - `ConfigView.from_dict()` 中读取 `metadata.scrape_mode`，默认 `"hybrid"`
  - 验收：`ConfigView.from_dict({})` 返回 `metadata.scrape_mode == "hybrid"`；`ConfigView.from_dict({"metadata": {"scrape_mode": "provider_first"}})` 返回正确值

- [ ] **T1.2** config.yaml.example 新增配置项
  - 文件：`config.yaml.example`
  - 在 `metadata:` 区块下新增 `scrape_mode` 配置项及注释
  - 验收：配置文件中有 `scrape_mode` 说明

- [ ] **T1.3** 维度完整度检查函数
  - 文件：`media_importer/scraper/metadata_scrape_flow.py`
  - 新增 `_check_dimension_completeness()` 函数
  - 验收：函数正确识别 `value=None` 为缺失，`value` 非 None 为完整

- [ ] **T1.4** 拆分 `scrape_metadata()` 为三个模式函数
  - 文件：`media_importer/scraper/metadata_scrape_flow.py`
  - 新增 `_scrape_provider_first()`、`_scrape_ai_only()`
  - 将现有 `scrape_metadata()` 重命名为 `_scrape_hybrid()`
  - 新 `scrape_metadata()` 读取 `scrape_mode` 分发到对应函数
  - 验收：三种模式各自独立，`hybrid` 行为与当前完全一致

- [ ] **T1.5** `_scrape_provider_first()` 实现维度完整度检查
  - 在 Provider 详情获取 + 维度映射后，调用 `_check_dimension_completeness()`
  - complete=True：直接构建结果，不调AI，使用 `confidence_engine.calculate(llm_raw_confidence=None)`
  - complete=False：调用 `scrape_with_context(exclude_dims=provider_covered)`，AI只补充缺失维度
  - 验收：Provider维度完整时不调AI；缺失时AI只补充缺失维度

- [ ] **T1.6** `_scrape_ai_only()` 实现
  - 跳过所有 Provider 搜索
  - 仅做正则清洗 + year_suspect时的ai_clean + 纯AI刮削
  - 使用 `confidence_engine.calculate_ai_only()`
  - 验收：不调用任何Provider API

- [ ] **T1.7** scrape_trace 追踪增强
  - 文件：`media_importer/scraper/metadata_scrape_flow.py`、`media_importer/features/scraping/confidence_engine.py`
  - 在各模式函数中注入 `scrape_mode`、`ai_invoked`、`ai_invoke_reason`
  - `ConfidenceEngine.calculate()` 和 `calculate_ai_only()` 的 trace 输出中包含新字段
  - 验收：trace 中包含三个新字段

- [ ] **T1.8** `scrape_series_metadata()` 适配
  - 文件：`media_importer/scraper/metadata_scrape_flow.py`
  - `ai_only` 模式下跳过Provider，直接 `scrape_series()`
  - `provider_first` 模式下先Provider再AI补充
  - `hybrid` 保持当前行为
  - 验收：三种模式下整剧刮削行为正确

### Phase 2: 配置保存与验证

- [ ] **T2.1** SECTION_FIELD_MAP 适配
  - 文件：`media_importer/features/configuration/application_service.py`
  - `"metadata.providers"` section 的字段列表中加入 `metadata`（已包含），确保 `scrape_mode` 随 metadata 区块保存
  - 验收：保存 metadata 区块时 `scrape_mode` 被正确持久化

- [ ] **T2.2** 配置验证逻辑
  - 文件：`media_importer/features/configuration/` 下的验证模块
  - `provider_first` 模式：检查至少一个Provider已启用（警告级别，不阻止）
  - `ai_only` 模式：检查AI已启用且配置完整（错误级别，阻止保存）
  - `hybrid` 模式：检查AI和Provider都已启用（警告级别）
  - 验收：验证逻辑正确拦截无效配置

### Phase 3: 前端配置页

- [ ] **T3.1** 刮削配置区块新增模式选择下拉框
  - 文件：`media_importer/webui/js/cinema-config.js`
  - 在 LLM/AI刮削 配置区块中新增 `scrape_mode` 下拉选择
  - 选项：Provider优先（推荐）、纯AI刮削、Provider+AI联合
  - 每个选项附带说明文字
  - 验收：下拉框正确渲染，选项文字清晰

- [ ] **T3.2** buildLlmConfigPayload() 或 buildProvidersPayload() 适配
  - 文件：`media_importer/webui/js/cinema-config.js`
  - 保存时将 `scrape_mode` 值包含在 metadata payload 中
  - 验收：保存配置时 `scrape_mode` 被发送到后端

- [ ] **T3.3** 模式切换时的动态提示
  - 选择 `provider_first`：显示"AI仅在元数据源数据不完整时补充，节省API调用"
  - 选择 `ai_only`：显示"不使用元数据源API，所有信息由AI判断"
  - 选择 `hybrid`：显示"每个文件都会同时调用元数据源和AI，成本较高但结果最完整"
  - 验收：切换模式时提示文字正确更新

- [ ] **T3.4** 配置加载时回显当前模式
  - 文件：`media_importer/webui/js/cinema-config.js`
  - 从 `currentConfigSnapshot.metadata.scrape_mode` 读取当前值
  - 设置下拉框的选中状态
  - 验收：刷新页面后下拉框显示当前配置的模式

- [ ] **T3.5** 刮削预览页适配
  - 文件：`media_importer/webui/js/cinema-config.js` 或相关前端文件
  - 预览结果中展示 `scrape_mode`、`ai_invoked`、`ai_invoke_reason` 信息
  - 验收：预览结果中可见AI是否被调用及原因

### Phase 4: 测试

- [ ] **T4.1** 单元测试：维度完整度检查
  - 文件：`tests/test_scrape_mode.py`（新建）
  - 测试 `_check_dimension_completeness()` 的各种场景：
    - 所有维度都有值 → complete=True
    - 部分维度 value=None → complete=False, missing_dims 正确
    - 维度不在 provider_dimensions 中 → 算缺失
    - enabled_dims 为空 → complete=True
  - 验收：所有测试通过

- [ ] **T4.2** 单元测试：ConfigView scrape_mode 字段
  - 文件：`tests/test_config_view.py`（修改）
  - 测试默认值为 `"hybrid"`
  - 测试从配置中读取 `"provider_first"` 和 `"ai_only"`
  - 验收：所有测试通过

- [ ] **T4.3** 单元测试：三种模式的 scrape_metadata 行为
  - 文件：`tests/test_scrape_mode.py`
  - Mock LLMScraper 和 Provider
  - `provider_first` + Provider维度完整 → 不调AI
  - `provider_first` + Provider维度缺失 → AI只补充缺失维度
  - `provider_first` + Provider无结果 → 降级纯AI
  - `ai_only` → 不调Provider
  - `hybrid` → 行为与当前一致
  - 验收：所有测试通过

- [ ] **T4.4** 单元测试：scrape_series_metadata 三种模式
  - 文件：`tests/test_scrape_mode.py`
  - `ai_only` 模式下跳过Provider
  - `provider_first` 模式下先Provider再AI
  - 验收：所有测试通过

- [ ] **T4.5** 集成测试：配置保存与加载
  - 文件：`tests/test_config_save_load_e2e.py`（修改）
  - 保存 `scrape_mode=provider_first` → 重新加载 → 值正确
  - 保存 `scrape_mode=ai_only` → 重新加载 → 值正确
  - 验收：端到端保存加载正确

- [ ] **T4.6** 回归测试：现有测试全部通过
  - 运行全部现有测试，确保 `hybrid` 模式（默认值）下行为不变
  - 特别关注：
    - `tests/test_confidence_engine.py`
    - `tests/test_config_view.py`
    - `tests/test_feature_import_flow.py`
    - `tests/test_feature_providers.py`
    - `tests/test_scrape_ui.py`
  - 验收：所有现有测试通过，无回归

- [ ] **T4.7** UI测试：前端配置页模式选择
  - 文件：`tests/test_scrape_ui.py`（修改）
  - 测试模式下拉框存在且可见
  - 测试模式切换时提示文字更新
  - 验收：Playwright测试通过

---

## 对现有代码的影响评估

### 数据加工流影响（核心关注点）

| 文件 | 改动类型 | 影响范围 | 风险 |
|------|---------|---------|------|
| `metadata_scrape_flow.py` | **重构**：拆分为3个函数 | 整个刮削管道 | **高** — 这是刮削的核心入口，任何逻辑错误都会导致刮削结果错误 |
| `config_view.py` | **新增字段** | 配置读取 | 低 — 新增字段有默认值，不影响现有配置 |
| `confidence_engine.py` | **trace增强** | 置信度追踪 | 低 — 仅新增trace字段，不修改计算逻辑 |
| `application_service.py` | **配置保存** | 配置持久化 | 低 — scrape_mode随metadata区块保存 |

### 前端影响

| 文件 | 改动类型 | 影响范围 | 风险 |
|------|---------|---------|------|
| `cinema-config.js` | **新增UI** | 配置页LLM区块 | 低 — 新增下拉框，不修改现有字段 |
| `cinema-config.js` | **payload修改** | 保存逻辑 | 低 — 在metadata payload中新增scrape_mode字段 |

### 测试影响

| 测试文件 | 需要修改 | 原因 |
|---------|---------|------|
| `test_config_view.py` | 是 | 新增 scrape_mode 字段测试 |
| `test_confidence_engine.py` | 否 | 置信度计算逻辑不变 |
| `test_scrape_ui.py` | 是 | 新增模式下拉框UI测试 |
| `test_config_save_load_e2e.py` | 是 | 新增 scrape_mode 保存加载测试 |
| `test_feature_import_flow.py` | 否 | hybrid模式（默认）行为不变 |
| `test_feature_providers.py` | 否 | Provider逻辑不变 |

### 向后兼容保证

1. **旧配置无 `scrape_mode`**：默认 `hybrid`，行为与当前完全一致
2. **`scrape_metadata()` 签名不变**：外部调用者无需修改
3. **`scrape_trace` 新增字段**：旧代码不读取新字段，不受影响
4. **`/api/scrape/preview` 行为不变**：始终并行跑两条路径

---

## 决策理由

### 为什么拆分为三个独立函数而非 if-else 分支？

当前 `scrape_metadata()` 已有 370+ 行，包含大量嵌套 if-else。如果在此基础上再加 `scrape_mode` 分支，代码可读性会进一步恶化。拆分为三个独立函数后：
- 每个函数职责单一，易于理解和测试
- `hybrid` 函数保持当前逻辑不变，降低回归风险
- 新增模式不影响其他模式的代码

### 为什么 `provider_first` 的维度完整度检查基于 `value is not None`？

Provider映射可能返回 `value=None`（如TMDb无release_dates时restricted_level为None）。如果只检查维度名是否存在，会误判为"完整"，导致AI不被调用，最终结果缺少维度值。基于 `value is not None` 才能准确反映Provider是否真的提供了该维度的值。

### 为什么模拟对比不受模式限制？

模拟对比（`/api/scrape/preview`）的目的是让用户看到两种方式的结果差异，帮助决定使用哪种模式。如果受模式限制，用户在 `ai_only` 模式下就无法看到Provider的结果对比，失去了对比的意义。

### 为什么默认新安装用 `provider_first` 而非 `hybrid`？

`provider_first` 是性价比最优的模式：Provider数据完整时不调AI，节省成本；缺失时AI精准补充，保证质量。对于新用户，这是最合理的选择。但旧配置默认 `hybrid` 以保证向后兼容。

---

## 假设审计

| 假设 | 状态 | 证据 |
|------|------|------|
| Provider维度映射返回 `value=None` 表示数据缺失 | 已验证 | `dimension_manager.py` 中 `map_provider_to_dimension()` 在无匹配时返回 `{'value': None, 'confidence': 0}` |
| `scrape_with_context()` 的 `exclude_dims` 参数能正确排除Provider已映射的维度 | 已验证 | `llm_scraper.py:338` 中 `exclude_dims` 传入 `_build_system_prompt_with_provider()`，AI不判断被排除的维度 |
| `hybrid` 模式下现有测试全部通过 | 待验证 | 需要在T4.6回归测试中确认 |
| 前端 `buildProvidersPayload()` 能正确包含 `scrape_mode` | 待验证 | 需要在T3.2中确认payload结构 |
| `scrape_series_metadata()` 也需要适配三种模式 | 已验证 | 当前函数也有Provider+AI联合逻辑，需适配 |

---

## 风险分析

| 风险 | 可能性 | 影响 | 缓解措施 |
|------|--------|------|---------|
| 拆分 `scrape_metadata()` 引入逻辑错误 | 中 | 高 — 刮削结果错误 | T1.4 中 `hybrid` 函数保持原逻辑不变；T4.3 完整测试三种模式 |
| `provider_first` 维度完整度判断不准 | 低 | 中 — 该调AI时没调 | 基于 `value is not None` 而非维度名存在；T4.1 覆盖各种边界情况 |
| 前端配置保存时 `scrape_mode` 丢失 | 低 | 中 — 模式不生效 | T4.5 端到端测试保存加载 |
| 旧配置升级后默认 `hybrid` 行为变化 | 极低 | 高 — 用户无感知变化 | 默认值 `hybrid` 与当前行为完全一致 |
| `ai_only` 模式下用户误配导致刮削质量下降 | 中 | 中 — 纯AI可能不如Provider+AI | T2.2 配置验证提示；前端说明文字 |

---

## 验收标准

1. **功能正确性**：三种模式行为符合方案定义
2. **向后兼容**：旧配置（无 `scrape_mode`）默认 `hybrid`，行为与当前完全一致
3. **维度完整度**：`provider_first` 模式下，Provider维度完整时不调AI，缺失时AI只补充缺失维度
4. **配置持久化**：`scrape_mode` 保存后重启服务仍生效
5. **前端可用**：配置页可选择模式，切换时有说明文字
6. **追踪可见**：`scrape_trace` 中包含 `scrape_mode`、`ai_invoked`、`ai_invoke_reason`
7. **测试覆盖**：所有新增测试通过，所有现有测试通过（无回归）
8. **模拟对比**：`/api/scrape/preview` 不受模式限制，始终并行对比
