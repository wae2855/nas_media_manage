# 维度启用/禁用全场景修复计划

> 日期: 2026-06-10 | 状态: pending

---

## 一、背景

维度（dimension）的 `is_enabled` 开关影响 AI prompt 生成、Provider 映射、置信度计算、路径规则匹配、任务卡片展示、详情模态框编辑、规则编辑器等 14 个系统区域。经全局笛卡尔积分析，当前存在 9 个漏洞，其中 4 个 P0 级阻塞问题。

### 核心矛盾

1. **前端存在两个独立的"已启用维度"缓存**（`currentEnabledDimensions` 与 `_enabledDimensions`），更新不同步，导致启用维度后任务卡片和规则编辑器看不到。
2. **路径规则匹配和 reclassify 入口不感知维度启用状态**，导致禁用维度的历史值仍参与规则匹配。
3. **禁用维度时规则编辑器不再显示该维度条件**，但禁用前置拦截又检查规则中是否使用该维度，形成 UX 死锁。

---

## 二、目标与非目标

### 目标

1. 统一前端维度缓存，消除 `currentEnabledDimensions` 与 `_enabledDimensions` 双缓存问题
2. 修复"禁用→启用"后任务卡片和规则编辑器不显示维度的问题
3. 修复禁用维度时规则编辑器不显示条件导致用户无法删除规则的 UX 死锁
4. reclassify API 入口校验维度启用状态，拒绝已禁用维度的修改请求
5. 路径规则匹配感知维度启用状态，已禁用维度的条件不参与匹配
6. 前端 `handleSaveDims` 改为只发送变更字段，避免"看不见的"禁用维度值被回写
7. 补充维度状态变更的单元测试、API 测试和集成测试

### 非目标

1. 不改变维度数据模型（不新增字段）
2. 不改变 DB 迁移逻辑
3. 不改变 AI prompt 生成、Provider 映射、置信度引擎的现有逻辑（这些已正确过滤 enabled）
4. 不引入维度版本管理或历史数据清理机制

---

## 三、设计决策

### D1：统一前端缓存到 `currentEnabledDimensions`

`path-rules.js` 的 `_enabledDimensions` 与 `cinema-app.js` 的 `currentEnabledDimensions` 合并为一个全局变量。所有消费者统一读取 `currentEnabledDimensions`。

理由：
- 消除双缓存不一致的根因
- `_enabledDimensions` 的格式（带 type/options）可通过一个转换函数从 `currentEnabledDimensions` 派生
- 减少维护成本

### D2：规则编辑器在维度禁用后仍显示该维度条件（标记为"已禁用"）

当前逻辑：规则编辑器只渲染 `_enabledDimensions` 中的维度。维度禁用后，该维度的条件字段从规则编辑器中消失。

改为：规则编辑器渲染时，除了已启用维度，还额外检查**当前规则中已使用的维度**（从 `conditions` 中提取），即使该维度已禁用，也渲染其条件字段并标记为"已禁用"状态。

理由：
- 消除 UX 死锁：用户可以看到并删除使用了已禁用维度的规则条件
- 禁用前置拦截（`isDimensionUsedInRules`）仍然生效，但用户有途径清理

### D3：reclassify 入口校验维度启用状态

`reclassify_task_for_api` 在收到 `dimensions` 入参后，先查询当前启用的维度列表，拒绝任何已禁用维度名。

理由：
- 防止已禁用维度的值被回写到 `scrape_dimensions`
- 与前端权限矩阵保持一致（前端不显示已禁用维度，后端不应接受）

### D4：路径规则匹配感知维度启用状态

`classification_rules.match_conditions` 增加可选参数 `enabled_dims`。传入时，过滤掉 `conditions` 中已禁用维度的键，使它们不参与匹配。

调用方（`ClassificationService.classify_task`、`ClassificationService.preview_classify`）在调用时传入当前启用的维度集合。

理由：
- 禁用维度的历史值不应影响规则匹配结果
- 与规则编辑器的语义一致（编辑器不显示已禁用维度条件）

### D5：前端 `handleSaveDims` 只发送变更字段

当前行为：`handleSaveDims` 收集所有 `[data-task-dim]` 的值，全量发送。

改为：只发送与当前值不同的字段（diff 模式）。

理由：
- 避免"看不见的"禁用维度值被无意识地回写
- 减少不必要的 API 调用

---

## 四、修复清单

| # | 优先级 | 修复项 | 涉及文件 |
|---|--------|--------|---------|
| 1 | P0 | 统一前端维度缓存 | `cinema-app.js`, `path-rules.js`, `cinema-config.js`, `cinema-tasks.js`, `dimensions.js` |
| 2 | P0 | 规则编辑器显示已禁用维度的条件字段 | `path-rules.js` |
| 3 | P0 | reclassify 入口校验维度启用状态 | `review_service.py` |
| 4 | P0 | 路径规则匹配感知维度启用状态 | `classification_rules.py`, `classification.py`, `confirm.py` |
| 5 | P1 | 前端 handleSaveDims 改为 diff 模式 | `cinema-tasks.js` |
| 6 | P2 | 提示词模板引用禁用维度时给出警告 | `dimensions.js`（前端） |

---

## 五、测试用例清单

### 5.1 单元测试 — 后端

#### T1: `match_conditions` 传入 `enabled_dims` 过滤禁用维度条件

**文件**: `tests/test_dimension_enabled_filter.py`（新建）

```python
# T1.1: enabled_dims 为 None 时行为不变（向后兼容）
def test_match_conditions_no_filter_backward_compat():
    dims = {"genre": "action", "region": "US"}
    conds = {"genre": "action", "region": "US"}
    assert match_conditions(dims, conds) is True

# T1.2: 传入 enabled_dims，过滤掉不在其中的条件键
def test_match_conditions_filters_disabled_dim():
    dims = {"genre": "action", "region": "US"}
    conds = {"genre": "action", "region": "US"}
    # region 已禁用，不参与匹配 → 只匹配 genre
    assert match_conditions(dims, conds, enabled_dims={"genre"}) is True

# T1.3: 禁用维度导致唯一条件被过滤 → 规则匹配失败
def test_match_conditions_all_conditions_filtered():
    dims = {"genre": "action"}
    conds = {"genre": "action"}
    # genre 已禁用 → 无有效条件 → 不匹配
    assert match_conditions(dims, conds, enabled_dims=set()) is False

# T1.4: 空 conditions 始终匹配（兜底规则）
def test_match_conditions_empty_conditions_always_match():
    dims = {"genre": "action"}
    conds = {}
    assert match_conditions(dims, conds, enabled_dims={"genre"}) is True
    assert match_conditions(dims, conds, enabled_dims=set()) is True

# T1.5: 部分条件被过滤，剩余条件仍正常匹配
def test_match_conditions_partial_filter():
    dims = {"genre": "action", "region": "US", "year": "2024"}
    conds = {"genre": "action", "region": "CN", "year": "2024"}
    # region 已禁用 → 只匹配 genre + year
    assert match_conditions(dims, conds, enabled_dims={"genre", "year"}) is True

# T1.6: 部分条件被过滤，剩余条件不匹配
def test_match_conditions_partial_filter_mismatch():
    dims = {"genre": "action", "region": "US"}
    conds = {"genre": "comedy", "region": "US"}
    # region 已禁用 → 只匹配 genre → genre 不匹配
    assert match_conditions(dims, conds, enabled_dims={"genre"}) is False
```

#### T2: `classify()` 传入 `enabled_dims`

**文件**: `tests/test_dimension_enabled_filter.py`

```python
# T2.1: 正常匹配（所有维度启用）
def test_classify_with_all_dims_enabled():
    # 准备 path_rules 和 scraped_info，所有维度启用
    # 验证返回正确的 import_path

# T2.2: 某维度禁用，其条件不参与匹配 → 可能匹配到不同规则
def test_classify_with_disabled_dim_skips_condition():
    # 规则 A: genre=action → /movies/action/
    # 规则 B: genre=comedy → /movies/comedy/
    # scraped_info: genre=action, region=US
    # 规则 A 条件: genre=action, region=US
    # 规则 B 条件: genre=comedy
    # 如果 region 禁用 → 规则 A 条件只剩 genre=action → 匹配
    # 验证返回 /movies/action/

# T2.3: 所有维度禁用 → 只匹配兜底规则
def test_classify_all_dims_disabled_fallback():
    # 验证返回兜底目录
```

#### T3: `reclassify_task_for_api` 拒绝已禁用维度

**文件**: `tests/test_dimension_enabled_filter.py`

```python
# T3.1: 入参包含已禁用维度名 → 返回 400
def test_reclassify_rejects_disabled_dimension_name():
    result = reclassify_task_for_api(pipeline, task_id, {"disabled_dim": "value"}, conn)
    assert result.code == 400
    assert "已禁用" in result.message

# T3.2: 入参仅包含已启用维度名 → 正常
def test_reclassify_accepts_enabled_dimension_name():
    result = reclassify_task_for_api(pipeline, task_id, {"enabled_dim": "value"}, conn)
    assert result.code == 200

# T3.3: 入参混合启用和禁用维度名 → 返回 400
def test_reclassify_rejects_mixed_dimensions():
    result = reclassify_task_for_api(pipeline, task_id, {"enabled": "v1", "disabled": "v2"}, conn)
    assert result.code == 400

# T3.4: 空 dimensions → 返回 400（已有逻辑）
def test_reclassify_empty_dimensions():
    result = reclassify_task_for_api(pipeline, task_id, {}, conn)
    assert result.code == 400
```

#### T4: `reclassify_task` 内部清洗禁用维度值

**文件**: `tests/test_dimension_enabled_filter.py`

```python
# T4.1: reclassify 后 scrape_dimensions 不包含已禁用维度的值
def test_reclassify_cleans_disabled_dim_from_scrape_dimensions():
    # 任务 scrape_dimensions 包含 {enabled: v1, disabled: v2}
    # 调用 reclassify_task 后
    # 验证 scrape_dimensions 只包含 {enabled: v1}

# T4.2: reclassify 后 scrape_dimensions 保留已启用维度的新值
def test_reclassify_preserves_enabled_dim_new_value():
    # 验证新值被正确写入
```

### 5.2 单元测试 — 前端（JS）

#### T5: `loadEnabledDimensions()` 更新 `currentEnabledDimensions`

**文件**: `tests/test_frontend_dimension_cache.js`（新建，或用现有测试框架）

```javascript
// T5.1: 调用 loadEnabledDimensions 后 currentEnabledDimensions 被更新
test("loadEnabledDimensions updates currentEnabledDimensions", async () => {
    // mock API 返回 [{name: "genre", is_enabled: true}, ...]
    await loadEnabledDimensions();
    expect(currentEnabledDimensions.length).toBeGreaterThan(0);
    expect(currentEnabledDimensions.some(d => d.name === "genre")).toBe(true);
});

// T5.2: enableDimension 后 currentEnabledDimensions 包含新启用的维度
test("enableDimension refreshes currentEnabledDimensions", async () => {
    // 初始 currentEnabledDimensions 不含 "genre"
    currentEnabledDimensions = [];
    // mock enable API
    await enableDimension("genre");
    expect(currentEnabledDimensions.some(d => d.name === "genre")).toBe(true);
});

// T5.3: disableDimension 后 currentEnabledDimensions 不包含已禁用的维度
test("disableDimension refreshes currentEnabledDimensions", async () => {
    currentEnabledDimensions = [{name: "genre"}, {name: "region"}];
    await disableDimension("genre");
    expect(currentEnabledDimensions.some(d => d.name === "genre")).toBe(false);
    expect(currentEnabledDimensions.some(d => d.name === "region")).toBe(true);
});
```

#### T6: 规则编辑器显示已禁用维度的条件字段

**文件**: `tests/test_frontend_dimension_cache.js`

```javascript
// T6.1: 规则使用了已禁用维度 → 条件字段仍渲染，标记为"已禁用"
test("rule editor shows disabled dim condition with disabled marker", () => {
    currentEnabledDimensions = [{name: "region"}];  // genre 已禁用
    const rules = [{conditions: {genre: "action", region: "US"}, template: "/test/"}];
    renderPathRules(rules);
    // 验证 DOM 中存在 genre 的条件字段
    // 验证 genre 字段有 disabled 样式/属性
    // 验证 region 字段正常可编辑
});

// T6.2: 规则未使用已禁用维度 → 不渲染额外字段
test("rule editor does not show disabled dim if not used in rule", () => {
    currentEnabledDimensions = [{name: "region"}];
    const rules = [{conditions: {region: "US"}, template: "/test/"}];
    renderPathRules(rules);
    // 验证 DOM 中不存在 genre 的条件字段
});

// T6.3: 删除规则中已禁用维度的条件后 → 禁用前置拦截不再阻止
test("can disable dimension after removing it from all rules", async () => {
    // 初始规则包含 genre 条件
    // 用户删除 genre 条件
    // 调用 disableDimension("genre")
    // 验证 isDimensionUsedInRules("genre") === false
    // 验证禁用成功
});
```

#### T7: `handleSaveDims` 只发送变更字段

**文件**: `tests/test_frontend_dimension_cache.js`

```javascript
// T7.1: 只修改了一个维度 → 只发送该维度的值
test("handleSaveDims sends only changed dimensions", async () => {
    // 模拟 task.scrape_dimensions = {genre: "action", region: "US"}
    // 用户只修改 genre → "comedy"
    // 验证 API 请求 body 为 {dimensions: {genre: "comedy"}}
    // 不包含 region
});

// T7.2: 未做任何修改 → 不发送请求
test("handleSaveDims does not send request if nothing changed", async () => {
    // 验证没有 API 调用
});

// T7.3: 修改了多个维度 → 发送所有变更
test("handleSaveDims sends all changed dimensions", async () => {
    // 修改 genre 和 region
    // 验证 API 请求 body 包含两个维度
});
```

### 5.3 API 集成测试

#### T8: `POST /api/dimensions/{name}/enable` 后任务列表 API 返回的维度正确

**文件**: `tests/test_dimension_enable_disable_api.py`（新建）

```python
# T8.1: 启用维度后 GET /api/dimensions/enabled 包含该维度
def test_enable_dimension_appears_in_enabled_list(api_client, test_db):
    # 1. 确保维度初始为 disabled
    # 2. POST /api/dimensions/genre/enable
    # 3. GET /api/dimensions/enabled
    # 4. 验证返回列表中包含 genre

# T8.2: 禁用维度后 GET /api/dimensions/enabled 不包含该维度
def test_disable_dimension_removed_from_enabled_list(api_client, test_db):
    # 1. 确保维度初始为 enabled
    # 2. POST /api/dimensions/genre/disable
    # 3. GET /api/dimensions/enabled
    # 4. 验证返回列表中不包含 genre

# T8.3: 启用维度后 GET /api/dimensions 全量列表中 is_enabled=1
def test_enable_dimension_is_enabled_true_in_full_list(api_client, test_db):
    pass

# T8.4: 禁用维度后 GET /api/dimensions 全量列表中 is_enabled=0
def test_disable_dimension_is_enabled_false_in_full_list(api_client, test_db):
    pass
```

#### T9: `POST /api/tasks/{id}/reclassify` 拒绝已禁用维度

**文件**: `tests/test_dimension_enable_disable_api.py`

```python
# T9.1: reclassify 入参包含已禁用维度 → 400
def test_reclassify_api_rejects_disabled_dim(api_client, test_db):
    # 1. 创建 AWAIT_REVIEW 任务
    # 2. 禁用某维度
    # 3. POST /api/tasks/{id}/reclassify body={dimensions: {disabled_dim: "value"}}
    # 4. 验证 400

# T9.2: reclassify 入参仅包含已启用维度 → 200
def test_reclassify_api_accepts_enabled_dim(api_client, test_db):
    pass

# T9.3: reclassify 后任务 scrape_dimensions 不包含已禁用维度值
def test_reclassify_api_cleans_disabled_dim_value(api_client, test_db):
    # 1. 任务 scrape_dimensions 原本包含 {enabled: v1, disabled: v2}
    # 2. 调用 reclassify 修改 enabled 的值
    # 3. 验证 scrape_dimensions 只包含 {enabled: new_v1}
    pass
```

#### T10: 路径规则匹配端到端

**文件**: `tests/test_dimension_enable_disable_api.py`

```python
# T10.1: 禁用维度后 classify 不使用该维度条件
def test_classify_skips_disabled_dim_condition(api_client, test_db):
    # 1. 创建路径规则: genre=action → /movies/action/
    # 2. 创建任务 scrape_dimensions={genre: "action"}
    # 3. 禁用 genre 维度
    # 4. 调用 classify-preview
    # 5. 验证不匹配 genre=action 规则（因为 genre 条件被过滤）

# T10.2: 启用维度后 classify 使用该维度条件
def test_classify_uses_enabled_dim_condition(api_client, test_db):
    # 1. 创建路径规则: genre=action → /movies/action/
    # 2. 创建任务 scrape_dimensions={genre: "action"}
    # 3. 确保 genre 已启用
    # 4. 调用 classify-preview
    # 5. 验证匹配 genre=action 规则

# T10.3: 所有维度禁用后 classify 使用兜底规则
def test_classify_fallback_when_all_dims_disabled(api_client, test_db):
    pass
```

### 5.4 回归测试

#### T11: 现有测试全部通过

```bash
# 所有维度相关测试
python -m pytest tests/test_feature_task_cancel.py tests/test_cleanup_orphaned_state.py
python -m pytest tests/test_feature_task_review.py
python -m pytest tests/test_feature_task_queue.py
python -m pytest tests/test_feature_task_list.py
python -m pytest tests/test_feature_task_file_lifecycle.py
python -m pytest tests/test_task_context_lifecycle.py tests/test_stage_lifecycle.py
python -m pytest tests/test_classify_preview.py
python -m pytest tests/test_feature_entrypoints.py
python -m pytest tests/test_architecture_guards.py
```

#### T12: 架构护栏测试

```python
# T12.1: features/ 不直接依赖 webui/
# T12.2: features/tasks/ 不直接依赖 api/
# T12.3: 无循环导入
```

---

## 六、实施顺序

按依赖关系排列，每个阶段完成后运行对应测试：

| 阶段 | 修复项 | 依赖 | 测试 |
|------|--------|------|------|
| Phase 1 | 修复 4: 路径规则匹配感知维度启用状态 | 无 | T1, T2, T10 |
| Phase 2 | 修复 3: reclassify 入口校验维度启用状态 | Phase 1 | T3, T4, T9 |
| Phase 3 | 修复 1: 统一前端维度缓存 | 无（纯前端） | T5 |
| Phase 4 | 修复 2: 规则编辑器显示已禁用维度条件 | Phase 3 | T6 |
| Phase 5 | 修复 5: handleSaveDims 改为 diff 模式 | Phase 3 | T7 |
| Phase 6 | 修复 6: 提示词模板引用禁用维度警告 | Phase 3 | 手动验证 |
| Phase 7 | 全量回归 | Phase 1-6 | T8, T11, T12 |

Phase 1-2 可并行（后端独立），Phase 3-5 可并行（前端独立），Phase 6 为锦上添花。

---

## 七、涉及文件清单

### 后端

| 文件 | 修改类型 |
|------|---------|
| `media_importer/features/import_flow/services/classification_rules.py` | `match_conditions` 增加 `enabled_dims` 参数 |
| `media_importer/features/import_flow/services/classification.py` | `classify_task` / `preview_classify` 传入 `enabled_dims` |
| `media_importer/features/import_flow/confirm.py` | `reclassify_task` 清洗禁用维度值 |
| `media_importer/features/tasks/review_service.py` | `reclassify_task_for_api` 校验维度启用状态 |

### 前端

| 文件 | 修改类型 |
|------|---------|
| `media_importer/webui/js/cinema-app.js` | 无修改（`currentEnabledDimensions` 已是全局变量） |
| `media_importer/webui/js/path-rules.js` | `loadEnabledDimensions` 改为更新 `currentEnabledDimensions`；`_getDimensions` 改为从 `currentEnabledDimensions` 派生；规则编辑器渲染已禁用维度的条件字段 |
| `media_importer/webui/js/cinema-config.js` | 移除重复的 `loadDimensionVars` / `loadDimensionsList`，统一用 `loadEnabledDimensions` |
| `media_importer/webui/js/cinema-tasks.js` | `handleSaveDims` 改为 diff 模式 |
| `media_importer/webui/js/dimensions.js` | `enableDimension` / `disableDimension` 调用统一的 `loadEnabledDimensions` |

### 测试

| 文件 | 类型 |
|------|------|
| `tests/test_dimension_enabled_filter.py` | 新建 — 后端单元测试 |
| `tests/test_dimension_enable_disable_api.py` | 新建 — API 集成测试 |
| `tests/test_frontend_dimension_cache.js` | 新建 — 前端单元测试（如前端测试框架可用） |

---

## 八、风险与回滚

- **风险**：`match_conditions` 增加参数可能影响其他调用方。缓解：参数设为可选，默认 `None`（行为不变）。
- **风险**：前端缓存统一后，`_getDimensions` 的格式转换逻辑需要仔细对齐。缓解：先在 `path-rules.js` 中增加一个 `_normalizeDimensions(raw)` 转换函数。
- **回滚**：所有修改都是增量式的（增加参数、增加校验），可通过 revert commit 安全回滚。
