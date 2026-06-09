- **Requirement**: 待注册
- **Supersedes**: [2026-06-08-mcp-search-integration.md](2026-06-08-mcp-search-integration.md)（旧方案依赖 Trae MCP，不适用于独立部署）
- **Status**: draft

# LLM 联网搜索集成方案

## 1. 背景与问题

当前 AI 刮削完全依赖 LLM 的静态知识，无法获取影视最新信息（新片、评分、分级等），导致刮削准确率受限。

旧方案（[2026-06-08-mcp-search-integration.md](2026-06-08-mcp-search-integration.md)）基于 MCP 协议，依赖 Trae 环境提供 MCP Server，**不适用于独立部署在 fnOS NAS 上的产品**。

## 2. 方案概述

利用大模型厂商 API **自带的联网搜索能力**，在调用 LLM 时直接传入搜索工具声明，由模型厂商服务端执行搜索并返回增强结果。

**核心思路**：不改架构，不改协议，只改 API 调用参数。

各厂商实现方式：

| 厂商 | 联网搜索方式 | 兼容 OpenAI 格式 |
|------|-------------|-----------------|
| 智谱 GLM | `tools: [{"type": "web_search", ...}]` | 是（OpenAI 兼容） |
| DeepSeek | 暂无 API 级联网搜索 | — |
| OpenAI | Responses API `tools: [{"type": "web_search_preview"}]` | 新 API |
| MiniMax | `plugins: ["web_search"]` | 部分兼容 |
| 通义千问 | `enable_search: true`（参数级） | 是 |
| 硅基流动等 | 转发厂商能力，取决于底层模型 | 取决于配置 |

**关键发现**：智谱 GLM 的联网搜索是通过在 `tools` 数组中传入 `{"type": "web_search"}` 实现的，完全兼容 OpenAI chat/completions 接口格式，无需额外 SDK 或 MCP Server。

## 3. 技术方案

### 3.1 配置层

在 `config.yaml` 的 `llm` 节下，将现有 `mcp` 配置替换为 `web_search` 配置：

```yaml
llm:
  # ... 现有配置 ...
  
  web_search:
    enabled: false                # 是否启用联网搜索
    provider: "auto"              # 搜索提供商：
                                  #   "auto"    - 根据当前 LLM provider 自动选择
                                  #   "zhipu"   - 智谱 GLM web_search
                                  #   "minimax" - MiniMax web_search
                                  #   "qwen"    - 通义千问 enable_search
                                  #   "openai"  - OpenAI web_search_preview
                                  #   "none"    - 不启用（即使 LLM 支持）
    scenarios:
      scrape: true                # 纯 AI 刮削时启用
      scrape_with_context: false  # 已有 Provider 上下文时不启用
      series_scrape: true         # 整剧刮削时启用
      source_cleaner: false       # 源目录清理时不启用
```

### 3.2 ConfigView 变更

在 `LLMConfig` 中替换 `mcp: dict` 为 `web_search: dict`：

```python
@dataclass(frozen=True)
class LLMConfig:
    # ... 现有字段 ...
    web_search: dict = field(default_factory=dict)
```

### 3.3 WebSearchConfig 数据类

新增 `media_importer/features/scraping/web_search_config.py`：

```python
@dataclass(frozen=True)
class WebSearchConfig:
    enabled: bool = False
    provider: str = "auto"  # auto / zhipu / minimax / qwen / openai / none
    scrape: bool = True
    scrape_with_context: bool = False
    series_scrape: bool = True
    source_cleaner: bool = False

    def should_search(self, scenario: str) -> bool:
        if not self.enabled:
            return False
        if self.provider == "none":
            return False
        return getattr(self, scenario, False)

    def effective_provider(self, llm_base_url: str) -> str:
        if self.provider != "auto":
            return self.provider
        # 根据 base_url 推断
        if "bigmodel.cn" in llm_base_url:
            return "zhipu"
        if "minimax" in llm_base_url:
            return "minimax"
        if "dashscope" in llm_base_url:
            return "qwen"
        if "openai.com" in llm_base_url:
            return "openai"
        return "none"
```

### 3.4 LLMScraper 变更

**删除**：全部 MCP 相关代码（`mcp_client`、`_call_llm_with_tools`、`_scrape_with_tools_async`、`_call_api_with_tools`、`scrape_with_mcp`、`scrape_series_with_mcp`、`scrape_with_context_mcp`）。

**修改**：在 `_do_call` 方法中，根据配置决定是否注入搜索工具参数：

```python
def _do_call(self, system_prompt, user_content, model,
             base_url, api_key, scenario=None):
    url = f"{base_url.rstrip('/')}/chat/completions"
    
    payload = {
        'model': model,
        'messages': [
            {'role': 'system', 'content': system_prompt},
            {'role': 'user', 'content': user_content}
        ],
        'temperature': 0.3
    }
    
    # 注入联网搜索工具
    if scenario and self.web_search_config.should_search(scenario):
        provider = self.web_search_config.effective_provider(base_url)
        search_tools = self._build_search_tools(provider)
        if search_tools:
            payload['tools'] = search_tools
    
    # ... 发送请求 ...
```

各厂商工具参数构建：

```python
def _build_search_tools(self, provider: str) -> list:
    if provider == "zhipu":
        return [{"type": "web_search", "web_search": {"enable": True}}]
    elif provider == "qwen":
        # 通义千问通过额外参数启用
        return None  # 在 payload 级别处理 enable_search
    elif provider == "minimax":
        return None  # MiniMax 通过 plugins 参数处理
    elif provider == "openai":
        # OpenAI 需要用 Responses API，chat/completions 不支持
        return None
    return None
```

**特殊处理**：部分厂商不走 `tools` 字段，需要在 payload 层面额外处理：

| 厂商 | 注入方式 |
|------|---------|
| 智谱 GLM | `payload["tools"] = [{"type": "web_search", ...}]` |
| 通义千问 | `payload["enable_search"] = True` |
| MiniMax | `payload["plugins"] = ["web_search"]` |

### 3.5 异常处理与降级

联网搜索是增强能力，不应成为刮削的阻塞点。所有搜索相关异常必须降级为无搜索的普通调用。

#### 异常分类与处理

| 异常类型 | 场景 | 处理策略 |
|----------|------|----------|
| 搜索额度不足 | 厂商返回 429/402 或额度相关错误码 | 降级：去掉搜索参数重新调用，记录警告日志 |
| 搜索功能不可用 | 厂商返回 400 提示不支持搜索 | 降级：去掉搜索参数重新调用，记录警告日志 |
| LLM 服务整体异常 | 网络超时、5xx、认证失败 | 不降级：直接向上层抛出异常（与现有行为一致） |
| 搜索结果干扰输出 | 返回的 JSON 格式异常或包含搜索引用标记 | 增强 `_parse_response` 容错：尝试提取有效 JSON |

#### 降级实现

在 `_do_call` 中用 try-except 包裹搜索增强调用：

```python
def _do_call(self, system_prompt, user_content, model,
             base_url, api_key, scenario=None):
    url = f"{base_url.rstrip('/')}/chat/completions"
    
    payload = self._build_payload(system_prompt, user_content, model)
    
    # 尝试带搜索参数调用
    if scenario and self.web_search_config.should_search(scenario):
        provider = self.web_search_config.effective_provider(base_url)
        self._inject_search(payload, provider)
    
    try:
        return self._send_request(url, payload, api_key)
    except LLMWebSearchError as e:
        # 搜索额度不足或功能不可用：降级为普通调用
        logger.warning("web search failed, falling back to normal call: %s", e)
        payload = self._build_payload(system_prompt, user_content, model)
        return self._send_request(url, payload, api_key)
```

#### 异常识别

各厂商搜索相关错误的识别方式：

```python
class LLMWebSearchError(Exception):
    """联网搜索相关异常，可降级"""

def _classify_error(self, status_code: int, body: dict, provider: str) -> Exception:
    if status_code == 401 or status_code == 403:
        return LLMAuthError("auth failed")  # 不降级
    if status_code == 429:
        # 区分：全局限流 vs 搜索额度不足
        if provider == "zhipu" and "web_search" in str(body):
            return LLMWebSearchError("web search quota exceeded")
        return LLMRateLimitError("rate limited")  # 不降级
    
    if status_code == 400:
        err_msg = str(body).lower()
        if any(kw in err_msg for kw in ["web_search", "search", "plugin", "tool"]):
            return LLMWebSearchError("web search not available")
        return LLMRequestError("bad request")  # 不降级
    
    if status_code >= 500:
        return LLMServerError("server error")  # 不降级
    
    return LLMWebSearchError("unknown error")
```

#### 降级原则

1. **搜索是锦上添花，不是必须**——任何搜索异常都应降级到普通调用。
2. **只降级一次**——降级后的普通调用如果也失败，按现有错误处理流程走，不再重试。
3. **LLM 本身的异常不降级**——认证失败、全局限流、服务端错误与搜索无关，直接抛出。
4. **日志可追溯**——每次降级记录 WARNING 级别日志，包含原始错误和降级结果。

### 3.6 响应解析

启用联网搜索后，LLM 响应可能包含搜索引用信息。解析逻辑需要兼容：

- 正常 JSON 响应（大部分情况，模型会整合搜索结果到 JSON 中）
- 响应中可能包含额外的 `web_search_result` 内容（智谱会返回搜索来源）
- 搜索结果可能导致输出格式偏移（额外的文本、引用标记）

`_parse_response` 方法需增强容错：
- 尝试标准 JSON 解析
- 如果失败，尝试从响应文本中提取 JSON 片段（正则匹配 `{...}` 块）
- 仍然失败则按现有错误处理

### 3.7 前端配置

在 `webui/js/config.js` 的 LLM 配置区域增加：

**新增 HTML 元素**（在 AI 配置 tab 下）：

```html
<div class="config-group">
  <h4>联网搜索</h4>
  <label>
    <input type="checkbox" id="cfg-llm_web_search_enabled"> 启用联网搜索
    <small>利用大模型厂商的搜索能力增强刮削准确率</small>
  </label>
  <label>
    搜索提供商
    <select id="cfg-llm_web_search_provider">
      <option value="auto">自动检测</option>
      <option value="zhipu">智谱 GLM</option>
      <option value="minimax">MiniMax</option>
      <option value="qwen">通义千问</option>
      <option value="openai">OpenAI</option>
      <option value="none">不启用</option>
    </select>
  </label>
  <small class="help-text">
    选择"自动检测"时，系统根据 API 地址自动判断。
    目前支持联网搜索的厂商：智谱 GLM、MiniMax、通义千问、OpenAI。
  </small>
</div>
```

### 3.7 配置迁移

`core/config_migrations.py` 需要处理：

- 将旧 `llm.mcp` 配置迁移到 `llm.web_search`
- 迁移逻辑：`mcp.enabled` → `web_search.enabled`，`mcp.scenarios` → `web_search.scenarios`

## 4. 需要删除的代码

| 文件/目录 | 操作 |
|-----------|------|
| `media_importer/features/mcp/` | **整个目录删除** |
| `docs/features/mcp_integration.md` | **删除** |
| `docs/plans/2026-06-08-mcp-search-integration.md` | **移入 _archive** |
| `llm_scraper.py` 中 MCP 相关方法 | **删除** |
| `config_view.py` 中 `mcp` 字段 | **替换为 web_search** |
| `config.yaml.example` 中 `mcp` 配置 | **替换为 web_search** |

## 5. 影响范围

| 模块 | 变更类型 | 影响评估 |
|------|---------|---------|
| `core/config_view.py` | 字段替换 mcp → web_search | 低风险 |
| `core/config_migrations.py` | 新增迁移规则 | 低风险 |
| `features/scraping/web_search_config.py` | 新增 | 无风险 |
| `scraper/llm_scraper.py` | 删 MCP 代码，改 _do_call | 中风险 |
| `webui/js/config.js` | 新增配置 UI | 低风险 |
| `webui/index.html` | 新增配置元素 | 低风险 |
| `api/config_handlers.py` | 脱敏字段更新 | 低风险 |
| `features/mcp/` | 整个目录删除 | 清理 |
| 配置文件 | mcp → web_search 迁移 | 低风险 |

## 6. 实施阶段

### Phase 1: 清理旧代码
- 删除 `features/mcp/` 目录
- 删除 `llm_scraper.py` 中 MCP 相关方法和 `__init__` 中的 `mcp_client` 参数
- 删除 `config_view.py` 中 `mcp` 字段
- 旧 plan 移入 `_archive`

### Phase 2: 新增配置层
- 新增 `WebSearchConfig` 数据类
- 更新 `LLMConfig`（`web_search` 字段）
- 更新 `config_migrations.py`（mcp → web_search 迁移）
- 更新 `config.yaml.example`

### Phase 3: 核心逻辑
- 修改 `LLMScraper._do_call` 支持搜索工具注入
- 新增 `_build_search_tools` 方法
- 修改 `scrape`、`scrape_with_context`、`scrape_series` 方法传入 scenario 参数

### Phase 4: 前端配置
- `config.js` 新增联网搜索配置读取/保存
- `index.html` 新增配置 UI 元素
- `config_handlers.py` 更新脱敏字段

### Phase 5: 测试与文档
- 单元测试
- 文档更新

## 7. 验收标准

1. 配置 `web_search.enabled: true` 后，AI 刮削请求自动携带搜索工具参数。
2. 配置 `web_search.enabled: false` 后，行为与当前完全一致。
3. `provider: "auto"` 能根据 `base_url` 正确推断厂商。
4. 不配置 `web_search` 时，不影响任何现有功能。
5. 旧 `mcp` 配置能自动迁移到 `web_search`。
6. 前端可配置联网搜索开关和提供商。
7. 所有现有测试通过。
8. `features/mcp/` 目录完全删除。

## 8. 风险与限制

| 风险 | 应对 |
|------|------|
| 部分厂商搜索功能收费或限流 | 默认关闭，用户按需开启 |
| 搜索结果可能干扰 JSON 输出格式 | 加强 `_parse_response` 容错 |
| 搜索增加响应时间 | 用户自行权衡 |
| 不同厂商参数格式不一致 | provider 适配层隔离差异 |
| OpenAI 需 Responses API 而非 chat/completions | 初期可不支持，后续扩展 |

## 9. 测试规划

### 9.1 单元测试

| 测试文件 | 测试内容 | 数量 |
|----------|---------|------|
| `tests/test_web_search_config.py` | WebSearchConfig 数据类 | 8 |
| | - `should_search` 各场景组合 | |
| | - `effective_provider` 自动推断逻辑 | |
| | - 边界情况（enabled=false, provider=none） | |
| `tests/test_config_view.py`（追加） | LLMConfig.web_search 字段解析 | 3 |
| | - 从 dict 正确解析 web_search 配置 | |
| | - 不配置 web_search 时默认值 | |
| | - 旧 mcp 字段不再被解析 | |
| `tests/test_config_migrations.py`（追加） | mcp → web_search 迁移 | 3 |
| | - mcp.enabled 迁移到 web_search.enabled | |
| | - mcp.scenarios 迁移到 web_search.scenarios | |
| | - 无 mcp 配置时不产生 web_search | |
| `tests/test_llm_scraper.py`（新增） | LLMScraper 搜索工具注入 | 10 |
| | - `_build_search_tools("zhipu")` 返回正确 tools | |
| | - `_build_search_tools("qwen")` 返回 None + enable_search 标记 | |
| | - `_build_search_tools("minimax")` 返回 None + plugins 标记 | |
| | - `_build_search_tools("none")` 返回空 | |
| | - `web_search.enabled=false` 时 payload 不含 tools | |
| | - `web_search.enabled=true` + `scenario="scrape"` 时 payload 含 tools | |
| | - `web_search.enabled=true` + `scenario="source_cleaner"` 时 payload 不含 tools | |
| | - `provider="auto"` 根据 base_url 正确推断 | |
| | - 不传入 scenario 时不注入 tools（向后兼容） | |
| | - 删除 MCP 方法后不影响现有 scrape 流程 | |
| `tests/test_llm_scraper.py`（追加） | 异常处理与降级 | 8 |
| | - 搜索额度不足（429 + web_search 关键字）→ 降级为普通调用 | |
| | - 搜索功能不可用（400 + search 关键字）→ 降级为普通调用 | |
| | - 认证失败（401）→ 不降级，抛出异常 | |
| | - 全局限流（429 无搜索关键字）→ 不降级，抛出异常 | |
| | - 服务端错误（5xx）→ 不降级，抛出异常 | |
| | - 降级后仍失败 → 不再重试，抛出异常 | |
| | - 降级时记录 WARNING 日志 | |
| | - 搜索结果包含引用标记时 `_parse_response` 仍能提取 JSON | |
| `tests/test_llm_scraper.py`（追加） | 响应解析增强 | 3 |
| | - 标准 JSON 响应正常解析 | |
| | - 响应包含多余文本时能提取 JSON 片段 | |
| | - 响应完全无法解析时按现有错误处理 | |

### 9.2 集成测试

| 测试文件 | 测试内容 | 数量 |
|----------|---------|------|
| `tests/test_config_round_trip.py`（追加） | 配置写入 → 读取 → 验证 web_search 字段完整 | 2 |
| `tests/test_architecture_guards.py`（追加） | `features/mcp/` 不存在（已删除） | 1 |
| | `llm_scraper.py` 不导入 mcp 相关模块 | 1 |

### 9.3 配置迁移测试

| 测试内容 | 验证 |
|----------|------|
| 旧配置 `llm.mcp.enabled: true` 迁移 | 迁移后 `llm.web_search.enabled: true` |
| 旧配置 `llm.mcp.scenarios.scrape: true` | 迁移后 `llm.web_search.scenarios.scrape: true` |
| 新配置直接用 `llm.web_search` | 无迁移，直接加载 |
| 混合配置（同时有 mcp 和 web_search） | web_search 优先，mcp 被忽略 |

### 9.4 测试策略

- **Phase 1 完成后**：运行现有测试确保删除 MCP 代码不破坏功能
- **Phase 2 完成后**：运行配置层单元测试
- **Phase 3 完成后**：运行 LLMScraper 单元测试 + 全量非 UI 测试
- **Phase 4 完成后**：手动验证前端配置页面
- **Phase 5**：全量测试 + 编译检查

### 9.5 不需要测试的内容

- 实际调用厂商 API 的联网搜索（需要真实 API Key，属于手动验证）
- 前端 UI 渲染（无自动化测试环境）
- OpenAI Responses API（初期不支持）
