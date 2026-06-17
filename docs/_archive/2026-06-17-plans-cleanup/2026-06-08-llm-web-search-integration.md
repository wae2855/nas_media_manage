- **Requirement**: 待注册
- **Supersedes**: [2026-06-08-mcp-search-integration.md](2026-06-08-mcp-search-integration.md)（旧方案依赖 Trae MCP，不适用于独立部署，已删除）
- **Status**: completed（修订版 v4，已完成实施）

# LLM 联网搜索集成方案（修订版 v4）

## 1. 背景与问题

当前 AI 刮削完全依赖 LLM 的静态知识，无法获取影视最新信息（新片、评分、分级等），导致刮削准确率受限。

**旧方案（已废弃）**：基于 MCP 协议，依赖 Trae 环境提供 MCP Server，**不适用于独立部署在 fnOS NAS 上的产品**，方案 A 无法落地，全部删除。

## 2. 方案概述

利用大模型厂商 API **自带的联网搜索能力**，在调用 LLM 时直接传入搜索工具声明，由模型厂商服务端执行搜索并返回增强结果。

**核心思路**：不改架构，不改协议，只改 API 调用参数。

### 2.1 模型使用场景分析

当前系统有 3 条独立的 LLM 调用通道，服务 7 个业务场景：

```
通道 A: 刮削模型通道 (model + fallback_model)
  ├── 纯 AI 刮削 scrape()               → 从文件名推断完整元数据（重活，需搜索增强）
  ├── 整剧刮削 scrape_series()           → 按剧名刮削维度（中等，需搜索增强）
  └── Provider 失败降级 scrape()         → 兜底纯 AI 刮削（重活）

通道 B: 辅助模型通道 (fast_model → fallback 到 model)
  ├── 标题提取 extract_title()           → 从文件名提取标题+年份（轻活）
  └── Provider+AI scrape_with_context() → 整理 Provider 数据为标准格式（中等）

通道 C: 清理器模型 (source_cleaner_model → fallback 到 fast_model → model)
  └── 源目录 AI 清理 _call_llm()         → 分析垃圾文件（轻活，独立 urllib）
```

**各场景对模型能力的要求**：

| 场景 | 实际输入 | 模型要求 | 推荐策略 |
|------|---------|---------|---------|
| 标题提取 | 一个文件名 | 极低 | 速度优先，最便宜的即可 |
| Provider 数据整理 | TMDB JSON + 文件名 | 低 | 速度优先 |
| 源目录清理 | 文件名列表 | 低 | 速度优先 |
| **纯 AI 刮削** | 文件名（+字幕名） | **中等**，需要影视知识 | 准确率优先 + 搜索增强 |
| **整剧刮削** | 剧名 | **中等**，需要影视知识 | 准确率优先 + 搜索增强 |

**结论**：所有功能都不需要 GPT-4 级别模型。轻量模型（MiniMax-M2.7-highspeed、DeepSeek-V3、GLM-4-flash 等）足以覆盖辅助任务；刮削场景需要联网搜索增强。

### 2.2 按使用场景区分搜索需求

| 场景 | 是否需要搜索 | 说明 |
|------|-------------|------|
| **AI 刮削**（纯 AI 刮削、整剧刮削） | ✅ 需要 | 需要获取实时影视信息（评分、分级、译名、年份等） |
| **AI 辅助**（标题提取、数据整理、源目录清理） | ❌ 不需要 | 基于已有信息做判断，不需要联网搜索 |

各厂商实现方式：

| 厂商 | 联网搜索方式 | 兼容 OpenAI 格式 |
|------|-------------|-----------------|
| 智谱 GLM | `tools: [{"type": "web_search", ...}]` | 是（OpenAI 兼容） |
| DeepSeek | 暂无 API 级联网搜索 | — |
| OpenAI | Responses API `tools: [{"type": "web_search_preview"}]` | 新 API |
| MiniMax | `plugins: ["web_search"]` | 部分兼容 |
| 通义千问 | `enable_search: true`（参数级） | 是 |

## 3. 技术方案

### 3.1 配置层

在 `config.yaml` 的 `llm` 节下，将现有 `mcp` 配置替换为 `web_search` 配置：

```yaml
llm:
  api_key: ""
  base_url: "https://api.openai.com/v1"
  model: "gpt-3.5-turbo"
  fallback_model: ""
  fast_model: ""
  fast_base_url: ""
  fast_api_key: ""
  source_cleaner_model: ""
  timeout: 30
  max_retries: 2
  retry_delay: 3
  confidence_threshold: 0.8
  verify_ssl: true
  system_prompt: ""

  web_search:
    enabled: false
    provider: "none"              # 搜索提供商（用户明确指定）：
                                  #   "zhipu"   - 智谱 GLM web_search
                                  #   "minimax" - MiniMax web_search
                                  #   "qwen"    - 通义千问 enable_search
                                  #   "openai"  - OpenAI web_search_preview
                                  #   "none"    - 不启用
    enabled_for:
      scrape: true
      series_scrape: true
      source_cleaner: false
```

**关于 `provider` 字段**：当前 YAML 中 `llm.provider` 字段在整个后端 Python 运行时中**没有任何消费逻辑**（`LLMConfig` 无此字段，后端从不读取），属于死字段。在本次重构中**删除**。

### 3.2 核心变化对比

| 原方案 | 修订后方案 | 原因 |
|--------|-----------|------|
| `llm.provider` 字段 | **删除** | 死字段，base_url 已由用户维护，provider 不做任何 URL/header 构建 |
| `provider: "auto"` 自动推断 | **用户明确指定 provider** | 中转/代理服务无法通过 URL 准确判断厂商 |
| 新增 `clean_*` 字段 | **复用现有 `fast_*` 字段** | 功能重叠，fast_model 已有 fallback 到 model 的机制 |
| 不区分使用场景 | 天然区分：搜索只用于刮削，不用于辅助 | 辅助是基于已有数据的判断，不需要搜索 |
| 搜索降级和模型降级混在一起 | 两层降级：搜索降级 → 模型降级，层次递进 | 不同层面的降级不应交叉 |

### 3.3 ConfigView 变更

在 `LLMConfig` 中：

1. **删除** `mcp: dict` 字段
2. **新增** `web_search: dict` 字段
3. **保留** `fast_model` / `fast_base_url` / `fast_api_key`（前端"AI 辅助"区块复用）
4. **暴露** `source_cleaner_model`（当前为计算属性，改为用户可配置字段）

```python
@dataclass(frozen=True)
class LLMConfig:
    api_key: str = ""
    base_url: str = "https://api.openai.com/v1"
    model: str = "gpt-3.5-turbo"
    fast_model: str = ""
    fast_base_url: str = ""
    fast_api_key: str = ""
    source_cleaner_model: str = ""
    timeout: int = 30
    max_retries: int = 2
    retry_delay: int = 3
    fallback_model: str = ""
    confidence_threshold: float = 0.8
    verify_ssl: bool = True
    system_prompt: str = ""
    web_search: dict = field(default_factory=dict)
```

`source_cleaner_model` 的 fallback 逻辑保持不变（`fast_model || model || "gpt-4o-mini"`），但允许用户通过前端显式配置覆盖。

### 3.4 WebSearchConfig 数据类

新增 `media_importer/features/scraping/web_search_config.py`：

```python
@dataclass(frozen=True)
class WebSearchConfig:
    enabled: bool = False
    provider: str = "none"
    enabled_for_scrape: bool = True
    enabled_for_series_scrape: bool = True
    enabled_for_source_cleaner: bool = False

    def should_search(self, scenario: str) -> bool:
        if not self.enabled:
            return False
        if self.provider == "none":
            return False

        if scenario == "scrape":
            return self.enabled_for_scrape
        elif scenario == "series_scrape":
            return self.enabled_for_series_scrape
        elif scenario == "source_cleaner":
            return self.enabled_for_source_cleaner
        elif scenario == "scrape_with_context":
            return False

        return False

    def effective_provider(self) -> str:
        return self.provider
```

### 3.5 LLMScraper 变更

**删除**：全部 MCP 相关代码（`mcp_client`、`_call_llm_with_tools`、`_scrape_with_tools_async`、`_call_api_with_tools`、`scrape_with_mcp`、`scrape_series_with_mcp`、`scrape_with_context_mcp`）。

**修改构造函数**：移除 `mcp_client` 参数，新增 `web_search_config` 成员。

**修改调用链**：`scrape` / `scrape_series` → `_retry_with_fallback` → `_call_api` → `_do_call`，整条链新增可选 `scenario` 参数。`_call_fast_api` 路径（`extract_title`、`scrape_with_context`）不需要 scenario。

#### 3.5.1 拆分 `_do_call` 为三个方法

当前 `_do_call` 是一个 37 行的方法，内含 URL 构造、请求头、payload 构建、SSL 处理、HTTP 发送、响应解析全部逻辑。拆分为：

```python
def _build_payload(self, system_prompt: str, user_content: str, model: str) -> dict:
    return {
        'model': model,
        'messages': [
            {'role': 'system', 'content': system_prompt},
            {'role': 'user', 'content': user_content}
        ],
        'temperature': 0.3
    }

def _send_request(self, url: str, payload: dict, api_key: str) -> str:
    headers = {
        'Content-Type': 'application/json',
        'Authorization': f'Bearer {api_key}'
    }
    data = json.dumps(payload).encode('utf-8')
    req = urllib.request.Request(url, data=data, headers=headers, method='POST')
    ctx = None
    if not self.verify_ssl:
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE

    try:
        with urllib.request.urlopen(req, timeout=self.timeout, context=ctx) as response:
            response_data = response.read().decode('utf-8')
            result = json.loads(response_data)
            return result['choices'][0]['message']['content']
    except urllib.error.HTTPError as e:
        body = {}
        try:
            body = json.loads(e.read().decode('utf-8'))
        except Exception:
            pass
        raise self._classify_error(e.code, body)
    except Exception as e:
        raise LLMApiError(f"request failed: {e}") from e
```

#### 3.5.2 修改后的 `_do_call`

```python
def _do_call(self, system_prompt: str, user_content: str, model: str,
             base_url: str, api_key: str, scenario: Optional[str] = None) -> str:
    url = f"{base_url.rstrip('/')}/chat/completions"
    payload = self._build_payload(system_prompt, user_content, model)

    if scenario and self.web_search_config.should_search(scenario):
        provider = self.web_search_config.effective_provider()
        self._inject_search(payload, provider)

    try:
        return self._send_request(url, payload, api_key)
    except LLMWebSearchError as e:
        logger.warning("web search failed, falling back to normal call: %s", e)
        payload = self._build_payload(system_prompt, user_content, model)
        return self._send_request(url, payload, api_key)
```

#### 3.5.3 搜索注入

```python
def _inject_search(self, payload: dict, provider: str) -> None:
    if provider == "zhipu":
        payload["tools"] = [{"type": "web_search", "web_search": {"enable": True}}]
    elif provider == "qwen":
        payload["enable_search"] = True
    elif provider == "minimax":
        payload["plugins"] = ["web_search"]
    elif provider == "openai":
        pass
```

#### 3.5.4 scenario 参数传递路径

```
scrape(scenario="scrape")
  → _retry_with_fallback(scenario="scrape")
    → _call_api(sp, uc, model, scenario="scrape")
      → _do_call(sp, uc, model, base_url, api_key, scenario="scrape")

scrape_series(scenario="series_scrape")
  → _retry_with_fallback(scenario="series_scrape")
    → _call_api(sp, uc, model, scenario="series_scrape")
      → _do_call(..., scenario="series_scrape")

extract_title()                    # 无 scenario，不注入搜索
  → _call_fast_api(sp, uc)
    → _do_call(sp, uc, fast_model, fast_base_url, fast_api_key)  # 无 scenario

scrape_with_context()              # 无 scenario，不注入搜索
  → _retry_with_fallback(use_fast=True)
    → _call_fast_api(sp, uc)
      → _do_call(sp, uc, fast_model, fast_base_url, fast_api_key)
```

### 3.6 异常处理与降级（层次化降级）

**核心原则**：模型降级和搜索降级是两个独立层次，有明确递进关系。

```
层次 1: 搜索降级（发生在 _do_call 内部）
    模型没问题，但搜索功能出问题（额度不足/不支持）
    → 去掉搜索参数重试一次（搜索降级）
    → 搜索降级后仍然失败 → 抛出，交给上层模型降级

层次 2: 模型降级（发生在 _retry_with_fallback）
    模型本身出问题（认证失败/限流/服务端错误）
    → 主模型 → fallback 模型 → 重试
```

#### 异常分类与处理

| 异常类型 | 场景 | 处理策略 |
|----------|------|----------|
| 搜索额度不足 | 429/402 + 搜索关键字 | **搜索降级** |
| 搜索功能不可用 | 400 + 搜索关键字 | **搜索降级** |
| LLM 认证失败 | 401/403 | 不搜索降级，走模型降级 |
| LLM 全局限流 | 429 无搜索关键字 | 不搜索降级，走模型降级 |
| LLM 服务端错误 | 5xx / 超时 | 不搜索降级，走模型降级 |
| 搜索结果干扰输出 | JSON 解析失败 | `_parse_response` 容错 |

#### 异常识别

```python
class LLMWebSearchError(Exception):
    pass

class LLMApiError(Exception):
    pass

def _classify_error(self, status_code: int, body: dict) -> Exception:
    err_msg = str(body).lower()

    if status_code in (401, 403):
        return LLMApiError("auth failed")
    if status_code == 429:
        if any(kw in err_msg for kw in ["web_search", "search", "quota"]):
            return LLMWebSearchError("web search quota exceeded")
        return LLMApiError("rate limited")
    if status_code == 400:
        if any(kw in err_msg for kw in ["web_search", "search", "plugin", "tool"]):
            return LLMWebSearchError("web search not available")
        return LLMApiError("bad request")
    if status_code >= 500:
        return LLMApiError("server error")

    return LLMApiError("unknown error")
```

**兼容性**：保留 `LLMScrapeError` 作为 `LLMApiError` 的别名，避免破坏现有 `except LLMScrapeError` 的调用方。

### 3.7 响应解析

现有 `_parse_response` 已有正则提取 JSON 块的逻辑，足够应对搜索增强后的响应。需验证边界情况：

- 正常 JSON 响应（模型整合搜索结果到 JSON）
- 响应包含搜索来源信息（智谱返回搜索结果）
- 搜索结果导致输出格式偏移（额外文本、引用标记如 `[1]`）

### 3.8 前端配置

AI 配置页面拆分为两个独立的手风琴区块：

- **AI 刮削**：可选，不配置则走纯刮削器（TMDB 等 Provider），配置后刮削器 + AI 结合取置信度高的结果
- **AI 辅助**：必填，用于标题清洗、刮削结果整理、源目录智能清理等轻量任务

#### 3.8.1 整体布局

```html
<section class="config-stage-panel" data-config-panel="ai">
  <div class="section-title"><h2>AI配置</h2>...</div>
  <div class="config-form-grid">

    <!-- ===== 区块一：AI 刮削（可折叠，可选） ===== -->
    <article class="form-card form-card-full config-collapse-card" id="ai-scrape-card">
      <div class="config-collapse-header" data-collapse-toggle="ai-scrape-body">
        <div class="config-collapse-header-left">
          <span class="config-collapse-chevron">▸</span>
          <div>
            <b>AI 刮削</b>
            <small>可选。不配置则走纯刮削器；配置后刮削器 + AI 结合，取置信度高的结果</small>
          </div>
        </div>
        <div class="config-collapse-header-right">
          <span class="config-collapse-status" id="ai-scrape-status">未配置</span>
        </div>
      </div>
      <div class="config-collapse-body" id="ai-scrape-body">
        <article class="form-card form-card-full config-guide-card">
          <span>💡 AI 刮削说明</span>
          <div class="config-guide-list compact">
            <div>
              <b>不配置 AI 刮削</b>
              <small>系统使用刮削器（TMDB 等 Provider）独立完成元数据获取，不调用大模型。</small>
            </div>
            <div>
              <b>配置 AI 刮削</b>
              <small>刮削器结果与 AI 结果合并，同一字段取置信度更高的值。适合刮削器覆盖不到的冷门影片。</small>
            </div>
            <div>
              <b>联网搜索增强</b>
              <small>开启后 AI 可获取最新影视信息（评分、分级、译名等），提高刮削准确率。需要模型厂商支持。</small>
            </div>
            <div>
              <b>模型要求</b>
              <small>不需要高端模型。MiniMax-M2.7、DeepSeek-V3、智谱 GLM-4-flash 等轻量模型 + 搜索即可覆盖。支持所有兼容 OpenAI API 格式的服务。</small>
            </div>
          </div>
        </article>

        <label class="form-card form-card-full">
          <span>API Key</span>
          <input id="cfg-llm_api_key" type="password" placeholder="sk-..." />
          <p>已配置时可以留空，保存后保持原值。</p>
        </label>
        <label class="form-card form-card-full">
          <span>接口地址</span>
          <input id="cfg-llm_base_url" type="text" placeholder="https://api.openai.com/v1" />
          <p>支持所有兼容 OpenAI API 格式的大模型服务，请填写正确的接口地址。</p>
        </label>
        <label class="form-card form-card-full">
          <span>刮削模型ID</span>
          <input id="cfg-llm_model" type="text" placeholder="gpt-4o-mini / deepseek-chat / MiniMax-M2.7" />
          <p>用于纯 AI 刮削和整剧刮削，需要模型有一定影视知识。</p>
        </label>
        <label class="form-card form-card-full">
          <span>备选模型ID</span>
          <input id="cfg-llm_fallback_model" type="text" placeholder="主模型失败时降级使用" />
          <p>主模型失败时自动切换。</p>
        </label>
        <label class="form-card form-card-full">
          <span>超时时间（秒）</span>
          <input id="cfg-llm_timeout" type="number" min="5" max="120" value="30" />
        </label>
        <label class="form-card form-card-full">
          <span>最大重试次数</span>
          <input id="cfg-llm_max_retries" type="number" min="0" max="10" value="2" />
        </label>
        <label class="form-card form-card-full">
          <span>重试间隔（秒）</span>
          <input id="cfg-llm_retry_delay" type="number" min="1" max="60" value="3" />
        </label>
        <label class="form-card form-card-full">
          <span>默认置信度阈值</span>
          <input id="cfg-llm_confidence_threshold" type="number" min="0" max="1" step="0.1" value="0.8" />
        </label>
        <article class="form-card form-card-full">
          <span>连通性</span>
          <label class="toggle-row-inline">
            <input id="cfg-llm_verify_ssl" type="checkbox" />
            <b>验证 SSL 证书</b>
          </label>
          <div class="inline-action-row">
            <button class="btn btn-secondary btn-sm" type="button" data-llm-test="inline">测试 LLM 连通性</button>
          </div>
        </article>

        <!-- 联网搜索配置（子手风琴，嵌套在 AI 刮削内） -->
        <article class="form-card form-card-full config-collapse-card config-collapse-sub" id="ai-search-card">
          <div class="config-collapse-header" data-collapse-toggle="ai-search-body">
            <div class="config-collapse-header-left">
              <span class="config-collapse-chevron">▸</span>
              <div>
                <b>联网搜索增强</b>
                <small>利用大模型厂商自带的搜索能力获取最新影视信息，提高刮削准确率</small>
              </div>
            </div>
            <label class="toggle-pill">
              <input id="cfg-llm_web_search_enabled" type="checkbox" />
              <span class="toggle-pill-ui"></span>
            </label>
          </div>
          <div class="config-collapse-body" id="ai-search-body">
            <label class="form-card form-card-full">
              <span>搜索提供商</span>
              <select id="cfg-llm_web_search_provider">
                <option value="none">不启用</option>
                <option value="zhipu">智谱 GLM</option>
                <option value="minimax">MiniMax</option>
                <option value="qwen">通义千问</option>
                <option value="openai">OpenAI</option>
              </select>
              <p>请确认您的大模型厂商支持联网搜索功能后再选择。不同厂商搜索参数格式不同，选错不生效。</p>
            </label>
            <article class="form-card form-card-full">
              <span>启用搜索的场景</span>
              <label class="toggle-row-inline">
                <input id="cfg-llm_web_search_enabled_for_scrape" type="checkbox" checked />
                <b>纯 AI 刮削</b>
                <small>无 Provider 数据时，AI 联网搜索获取影片信息</small>
              </label>
              <label class="toggle-row-inline">
                <input id="cfg-llm_web_search_enabled_for_series_scrape" type="checkbox" checked />
                <b>整剧信息刮削</b>
                <small>批量刮削时联网获取剧集最新信息</small>
              </label>
              <label class="toggle-row-inline">
                <input id="cfg-llm_web_search_enabled_for_source_cleaner" type="checkbox" />
                <b>源目录 AI 清理</b>
                <small>通常不需要，基于已有数据做判断即可</small>
              </label>
            </article>
          </div>
        </article>
      </div>
    </article>

    <!-- ===== 区块二：AI 辅助（可折叠，必填） ===== -->
    <article class="form-card form-card-full config-collapse-card" id="ai-assist-card">
      <div class="config-collapse-header" data-collapse-toggle="ai-assist-body">
        <div class="config-collapse-header-left">
          <span class="config-collapse-chevron">▸</span>
          <div>
            <b>AI 辅助</b>
            <small>必填。用于标题清洗、刮削结果整理、源目录智能清理。推荐速度快、成本低的模型。</small>
          </div>
        </div>
        <div class="config-collapse-header-right">
          <span class="config-collapse-status" id="ai-assist-status">未配置</span>
        </div>
      </div>
      <div class="config-collapse-body" id="ai-assist-body">
        <article class="form-card form-card-full config-guide-card">
          <span>💡 AI 辅助说明</span>
          <div class="config-guide-list compact">
            <div>
              <b>必须配置</b>
              <small>标题清洗、刮削结果整理、源目录智能清理依赖大模型。未配置时相关功能不可用。</small>
            </div>
            <div>
              <b>不需要联网搜索</b>
              <small>辅助任务基于已有数据做判断（文件名解析、格式转换、分类识别等），不需要模型联网搜索能力。</small>
            </div>
            <div>
              <b>模型要求低</b>
              <small>推荐使用速度快、成本低的模型，如 MiniMax-M2.7-highspeed、DeepSeek-V3、GLM-4-flash 等。</small>
            </div>
          </div>
        </article>

        <label class="form-card form-card-full">
          <span>辅助模型ID <b class="required-mark">*</b></span>
          <input id="cfg-llm_fast_model" type="text" placeholder="gpt-4o-mini / MiniMax-M2.7-highspeed" required />
          <p>用于标题清洗、Provider 数据整理等轻量任务。留空则使用刮削模型。</p>
        </label>
        <label class="form-card form-card-full">
          <span>接口地址</span>
          <input id="cfg-llm_fast_base_url" type="text" placeholder="留空则使用刮削区块的接口地址" />
          <p>辅助模型和刮削模型使用不同厂商时可单独填写。</p>
        </label>
        <label class="form-card form-card-full">
          <span>API Key</span>
          <input id="cfg-llm_fast_api_key" type="password" placeholder="留空则使用刮削区块的 API Key" />
        </label>
        <label class="form-card form-card-full">
          <span>清理模型ID</span>
          <input id="cfg-llm_source_cleaner_model" type="text" placeholder="留空则使用辅助模型" />
          <p>用于源目录 AI 清理。留空默认使用辅助模型，无需单独配置。</p>
        </label>
      </div>
    </article>

  </div>
</section>
```

**字段与 LLMConfig 的映射**：

| 前端区块 | 前端 ID | YAML 字段 | LLMConfig 字段 |
|----------|---------|-----------|----------------|
| AI 刮削 | `cfg-llm_api_key` | `llm.api_key` | `api_key` |
| | `cfg-llm_base_url` | `llm.base_url` | `base_url` |
| | `cfg-llm_model` | `llm.model` | `model` |
| | `cfg-llm_fallback_model` | `llm.fallback_model` | `fallback_model` |
| | `cfg-llm_timeout` | `llm.timeout` | `timeout` |
| | `cfg-llm_max_retries` | `llm.max_retries` | `max_retries` |
| | `cfg-llm_retry_delay` | `llm.retry_delay` | `retry_delay` |
| | `cfg-llm_confidence_threshold` | `llm.confidence_threshold` | `confidence_threshold` |
| | `cfg-llm_verify_ssl` | `llm.verify_ssl` | `verify_ssl` |
| 联网搜索 | `cfg-llm_web_search_enabled` | `llm.web_search.enabled` | — |
| | `cfg-llm_web_search_provider` | `llm.web_search.provider` | — |
| | `cfg-llm_web_search_enabled_for_scrape` | `llm.web_search.enabled_for.scrape` | — |
| | `cfg-llm_web_search_enabled_for_series_scrape` | `llm.web_search.enabled_for.series_scrape` | — |
| | `cfg-llm_web_search_enabled_for_source_cleaner` | `llm.web_search.enabled_for.source_cleaner` | — |
| AI 辅助 | `cfg-llm_fast_model` | `llm.fast_model` | `fast_model` |
| | `cfg-llm_fast_base_url` | `llm.fast_base_url` | `fast_base_url` |
| | `cfg-llm_fast_api_key` | `llm.fast_api_key` | `fast_api_key` |
| | `cfg-llm_source_cleaner_model` | `llm.source_cleaner_model` | `source_cleaner_model` |

#### 3.8.2 手风琴交互逻辑

```javascript
document.querySelectorAll('.config-collapse-header[data-collapse-toggle]').forEach(function(header) {
  header.addEventListener('click', function(e) {
    if (e.target.closest('.toggle-pill')) return;

    var targetId = this.getAttribute('data-collapse-toggle');
    var body = document.getElementById(targetId);
    var card = this.closest('.config-collapse-card');
    var chevron = this.querySelector('.config-collapse-chevron');

    var isOpen = body.classList.contains('open');
    if (isOpen) {
      body.classList.remove('open');
      card.classList.remove('expanded');
      if (chevron) chevron.textContent = '▸';
    } else {
      body.classList.add('open');
      card.classList.add('expanded');
      if (chevron) chevron.textContent = '▾';
    }
  });
});
```

#### 3.8.3 CSS 样式

同 v2，不重复列出（`.config-collapse-card`、`.config-collapse-header`、`.config-collapse-body`、`.config-collapse-sub`、`.required-mark`）。

#### 3.8.4 配置状态检测

```javascript
function updateAiConfigStatus() {
  var llm = currentConfig.llm || {};

  var scrapeConfigured = !!(llm.api_key && llm.base_url && llm.model);
  var scrapeStatus = document.getElementById('ai-scrape-status');
  if (scrapeStatus) {
    scrapeStatus.textContent = scrapeConfigured ? '已配置' : '未配置';
    scrapeStatus.className = 'config-collapse-status' + (scrapeConfigured ? ' configured' : '');
  }

  var assistConfigured = !!(llm.fast_model || llm.model);
  var assistStatus = document.getElementById('ai-assist-status');
  if (assistStatus) {
    assistStatus.textContent = assistConfigured ? '已配置' : '未配置';
    assistStatus.className = 'config-collapse-status' + (assistConfigured ? ' configured' : '');
  }
}
```

#### 3.8.5 保存校验

AI 辅助区块保存时校验必填字段：

```javascript
function _validateAiAssistConfig() {
  var fastModel = document.getElementById('cfg-llm_fast_model').value.trim();
  var mainModel = document.getElementById('cfg-llm_model').value.trim();
  if (!fastModel && !mainModel) {
    showToast('AI 辅助必须配置辅助模型ID或刮削模型ID', 'error');
    return false;
  }
  return true;
}
```

#### 3.8.6 config.js 读取/保存变更

前端 ID 策略：**一次性替换**所有旧 ID（去掉 `-inline` 后缀），与新手风琴布局统一。实施时用 grep 确保所有 JS 引用同步更新。

**加载**：

```javascript
var llm = currentConfig.llm || {};

// AI 刮削字段
document.getElementById('cfg-llm_api_key').value = llm.api_key || '';
document.getElementById('cfg-llm_base_url').value = llm.base_url || '';
document.getElementById('cfg-llm_model').value = llm.model || '';
document.getElementById('cfg-llm_fallback_model').value = llm.fallback_model || '';
document.getElementById('cfg-llm_timeout').value = llm.timeout || 30;
document.getElementById('cfg-llm_max_retries').value = llm.max_retries || 2;
document.getElementById('cfg-llm_retry_delay').value = llm.retry_delay || 3;
document.getElementById('cfg-llm_confidence_threshold').value = llm.confidence_threshold || 0.8;
document.getElementById('cfg-llm_verify_ssl').checked = llm.verify_ssl !== false;

// 联网搜索配置
var ws = llm.web_search || {};
document.getElementById('cfg-llm_web_search_enabled').checked = !!ws.enabled;
document.getElementById('cfg-llm_web_search_provider').value = ws.provider || 'none';
document.getElementById('cfg-llm_web_search_enabled_for_scrape').checked = ws.enabled_for_scrape !== false;
document.getElementById('cfg-llm_web_search_enabled_for_series_scrape').checked = ws.enabled_for_series_scrape !== false;
document.getElementById('cfg-llm_web_search_enabled_for_source_cleaner').checked = !!ws.enabled_for_source_cleaner;

// AI 辅助配置（复用现有 fast_* 字段）
document.getElementById('cfg-llm_fast_model').value = llm.fast_model || '';
document.getElementById('cfg-llm_fast_base_url').value = llm.fast_base_url || '';
document.getElementById('cfg-llm_fast_api_key').value = llm.fast_api_key || '';
document.getElementById('cfg-llm_source_cleaner_model').value = llm.source_cleaner_model || '';

updateAiConfigStatus();
```

**保存**：

```javascript
llm: {
  api_key: document.getElementById('cfg-llm_api_key').value,
  base_url: document.getElementById('cfg-llm_base_url').value.trim(),
  model: document.getElementById('cfg-llm_model').value.trim(),
  fallback_model: document.getElementById('cfg-llm_fallback_model').value.trim(),
  timeout: parseInt(document.getElementById('cfg-llm_timeout').value) || 30,
  max_retries: parseInt(document.getElementById('cfg-llm_max_retries').value) || 2,
  retry_delay: parseInt(document.getElementById('cfg-llm_retry_delay').value) || 3,
  confidence_threshold: parseFloat(document.getElementById('cfg-llm_confidence_threshold').value) || 0.8,
  verify_ssl: document.getElementById('cfg-llm_verify_ssl').checked,
  system_prompt: llm.system_prompt || '',
  web_search: {
    enabled: document.getElementById('cfg-llm_web_search_enabled').checked,
    provider: document.getElementById('cfg-llm_web_search_provider').value,
    enabled_for_scrape: document.getElementById('cfg-llm_web_search_enabled_for_scrape').checked,
    enabled_for_series_scrape: document.getElementById('cfg-llm_web_search_enabled_for_series_scrape').checked,
    enabled_for_source_cleaner: document.getElementById('cfg-llm_web_search_enabled_for_source_cleaner').checked
  },
  fast_model: document.getElementById('cfg-llm_fast_model').value.trim(),
  fast_base_url: document.getElementById('cfg-llm_fast_base_url').value.trim(),
  fast_api_key: document.getElementById('cfg-llm_fast_api_key').value,
  source_cleaner_model: document.getElementById('cfg-llm_source_cleaner_model').value.trim()
}
```

**注意**：不再保存 `provider` 字段。

### 3.9 配置迁移

`core/config_migrations.py` 新增迁移函数：

```python
def _migrate_mcp_to_web_search(config: dict) -> None:
    llm = config.get("llm", {})
    if "mcp" not in llm:
        return

    mcp = llm.pop("mcp")

    # 只迁移 enabled 和 scenarios，tools 直接丢弃（不再需要）
    if mcp.get("enabled"):
        scenarios = mcp.get("scenarios", {})
        llm["web_search"] = {
            "enabled": True,
            "provider": "none",
            "enabled_for_scrape": scenarios.get("scrape", True),
            "enabled_for_series_scrape": scenarios.get("series_scrape", True),
            "enabled_for_source_cleaner": scenarios.get("source_cleaner", False),
        }
```

**迁移要点**：
- `mcp.tools` 直接丢弃（搜索功能改由厂商 API 提供）
- `mcp.enabled → web_search.enabled`
- `mcp.scenarios.* → web_search.enabled_for_*`
- `provider` 默认 `"none"`（需要用户手动选择，不自动推断）
- 无 `mcp` 配置时不产生 `web_search` 节点

### 3.10 删除 `provider` 字段

| 位置 | 操作 |
|------|------|
| `config.yaml` | 删除 `llm.provider` 行 |
| `config.yaml.example` | 删除 `llm.provider` 行 |
| `index.html` | 删除 LLM 提供商下拉框 `<select id="cfg-llm_provider-inline">` |
| `legacy-config.html` | 删除 LLM 提供商下拉框 `<select id="cfg-llm_provider">` |
| `config.js` | 删除 `provider` 读取/保存代码 |
| `cinema-app.js` | 删除 `provider` 读取代码 |
| `cinema-config.js` | 删除 `provider` 保存和测试代码 |
| `connectivity_handlers.py` | 删除 `provider = body.get("provider")` 行 |

## 4. 需要删除的代码

| 文件/目录 | 操作 |
|-----------|------|
| `media_importer/features/mcp/` | **整个目录删除** |
| `docs/features/mcp_integration.md` | **删除** |
| `docs/plans/2026-06-08-mcp-search-integration.md` | **移入 _archive** |
| `llm_scraper.py` 中全部 MCP 相关方法 | **删除**（共 8 个方法/成员） |
| `config_view.py` 中 `mcp` 字段 | **删除**，替换为 `web_search` |
| `config.yaml.example` 中 `mcp` 配置 | **删除**，替换为 `web_search`（见 §10.13 精确内容） |
| `llm.provider` 字段 | **删除**（全链路：YAML、前端、API） |

## 5. 影响范围

| 模块 | 变更类型 | 影响评估 |
|------|---------|---------|
| `core/config_view.py` | 删 `mcp`、删 `provider` 相关、新增 `web_search`、暴露 `source_cleaner_model` | 低风险 |
| `core/config_migrations.py` | 新增 `_migrate_mcp_to_web_search` | 低风险 |
| `core/config_loader.py` | 新增 import + 调用迁移函数（见 §10.9） | 低风险 |
| `features/scraping/web_search_config.py` | 新增 | 无风险 |
| `scraper/llm_scraper.py` | 删 MCP 代码，拆分 `_do_call`，搜索注入/降级 | 中风险 |
| `scraper/llm_scraper.py` | 删 `mcp_client` 参数，新增 `web_search_config` | 低风险 |
| `webui/index.html` | 重构 AI 配置为手风琴布局，删除 provider 下拉框 | 中风险 |
| `webui/js/config.js` + `cinema-*.js` | 手风琴交互、搜索配置、状态检测、删除 provider 逻辑 | 中风险 |
| `webui/css/config.css` | 新增手风琴样式 | 低风险 |
| `api/connectivity_handlers.py` | 删除 provider 读取 | 低风险 |
| `api/config_handlers.py` | 脱敏字段新增 `fast_api_key`（见 §10.10） | 低风险 |
| `features/mcp/` | 整个目录删除 | 清理，无影响 |

## 6. 实施阶段

### Phase 1: 清理旧代码
- 删除 `media_importer/features/mcp/` 整个目录
- 删除 `llm_scraper.py` 中全部 MCP 相关方法和 `__init__` 的 `mcp_client` 参数
- 删除 `config_view.py` 中 `mcp` 字段
- 删除 `llm.provider` 字段（YAML、前端、API 全链路）
- 将旧 plan 和 mcp 文档移入 `docs/_archive/`
- **验证**：运行 `python -m pytest tests/ --ignore=tests/test_*_ui.py --ignore=tests/test_frontend_*.py` 确保删除不破坏功能

### Phase 2: 新增配置层
- 新增 `WebSearchConfig` 数据类 (`features/scraping/web_search_config.py`)
- 更新 `LLMConfig`：添加 `web_search` 字段，暴露 `source_cleaner_model`
- 更新 `config_migrations.py`：新增 `_migrate_mcp_to_web_search`
- 更新 `config.yaml.example`：添加 `web_search` 配置示例，删除 `mcp` 和 `provider`
- **验证**：运行配置层单元测试

### Phase 3: 核心逻辑改造
- 修改 `LLMScraper.__init__`：移除 `mcp_client`，新增 `web_search_config`
- 拆分 `_do_call` 为 `_build_payload` + `_send_request` + `_do_call`
- `_send_request` 中按 HTTP 状态码分类抛出 `LLMWebSearchError` / `LLMApiError`
- 修改 `_do_call`：添加 `scenario` 参数、搜索注入、搜索降级
- 新增 `_inject_search` 和 `_classify_error` 方法
- 修改 `_call_api` 添加 `scenario` 参数透传
- 修改 `_retry_with_fallback` 添加 `scenario` 参数透传
- 修改 `scrape` / `scrape_series` 传入对应 scenario
- **验证**：运行 LLMScraper 单元测试 + 全量非 UI 测试

### Phase 4: 前端配置
- `index.html` 重构 AI 配置为手风琴布局（AI 刮削 + AI 辅助两个区块）
- `config.css` 新增手风琴样式
- `config.js` + `cinema-*.js`：删除 provider 逻辑，一次性替换 ID（去掉 `-inline`），新增搜索配置读取/保存、状态检测、必填校验
- **验证**：手动验证前端交互

### Phase 5: 测试与文档
- 新增全部单元测试
- 更新相关文档
- **验证**：全量测试 + 编译检查

## 7. 验收标准

1. 配置 `web_search.enabled: true` 且 `provider != none` 后，AI 刮削和整剧刮削请求自动携带搜索参数。
2. 源目录清理默认不携带搜索参数（除非用户手动开启）。
3. 配置 `web_search.enabled: false` 或 `provider: none` 后，行为与当前完全一致。
4. 不配置 `web_search` 时，不影响任何现有功能。
5. 旧 `mcp` 配置能自动迁移到 `web_search`（`mcp.tools` 丢弃，只迁移 enabled + scenarios）。
6. 前端 AI 配置使用手风琴布局：**AI 刮削**（可选）和 **AI 辅助**（必填）两个独立区块。
7. AI 辅助区块复用现有 `fast_model` / `fast_base_url` / `fast_api_key` 字段，不新增 `clean_*` 字段。
8. AI 辅助区块包含 `source_cleaner_model` 配置入口（留空则 fallback 到 fast_model）。
9. `llm.provider` 字段全链路删除（YAML、前端、API、文档）。
10. AI 辅助保存时校验辅助模型ID或刮削模型ID至少填一个。
11. 联网搜索配置作为子手风琴嵌套在 AI 刮削区块内，带 toggle-pill 开关。
12. 搜索异常（额度不足/不支持）正确触发搜索降级。
13. 搜索降级后仍失败，异常传递给模型降级层。
14. 模型层异常（401/429 无搜索关键字/5xx/超时）不触发搜索降级。
15. 所有现有测试通过。
16. `features/mcp/` 目录完全删除。

## 8. 风险与限制

| 风险 | 应对 |
|------|------|
| 部分厂商搜索功能收费或限流 | 默认关闭，用户按需开启 |
| 搜索结果可能干扰 JSON 输出格式 | 现有 `_parse_response` 已有正则提取容错 |
| 搜索增加响应时间 | 用户自行权衡，可随时关闭 |
| 不同厂商参数格式不一致 | provider 适配层隔离差异，用户自己选对厂商 |
| OpenAI 需 Responses API 而非 chat/completions | 初期只列出选项，暂不实现 |
| 前端 ID 一次性替换可能遗漏引用 | 实施时用 grep 确保所有 JS/HTML 引用同步更新 |
| `scrape_series_with_context` 使用主模型而非快速模型 | 保持现状，整剧维度刮削用主模型是合理选择 |

## 9. 测试规划

### 9.1 Mock 策略

所有 LLM 相关测试通过 mock `urllib.request.urlopen` 模拟 HTTP 响应：

```python
from unittest.mock import patch, MagicMock

def _mock_urlopen_response(status_code, body_dict):
    mock_resp = MagicMock()
    mock_resp.read.return_value = json.dumps(body_dict).encode('utf-8')
    mock_resp.__enter__ = lambda s: s
    mock_resp.__exit__ = lambda s, *a: None
    return mock_resp

def _mock_urlopen_error(status_code, body_dict):
    err = urllib.error.HTTPError(
        url='http://test', code=status_code,
        msg='error', hdrs={}, fp=None
    )
    err.read = lambda: json.dumps(body_dict).encode('utf-8')
    return err
```

**核心 mock 点**：`media_importer.scraper.llm_scraper.urllib.request.urlopen`

### 9.2 单元测试

| 测试文件 | 测试内容 | 数量 |
|----------|---------|------|
| `tests/test_web_search_config.py` | WebSearchConfig 数据类 | 8 |
| | - `should_search` 各场景组合（enabled/disabled + provider/none） | |
| | - 不同场景（scrape/series/source_cleaner/scrape_with_context）开关 | |
| | - `effective_provider` 直接返回用户配置值 | |
| `tests/test_config_view.py`（追加） | LLMConfig 字段解析 | 4 |
| | - 从 dict 正确解析 web_search 配置 | |
| | - 不配置 web_search 时默认值 | |
| | - 旧 mcp 字段不再被解析 | |
| | - `source_cleaner_model` 显式配置覆盖 fallback | |
| `tests/test_config_migrations.py`（追加） | mcp → web_search 迁移 | 4 |
| | - `mcp.enabled` → `web_search.enabled` | |
| | - `mcp.scenarios` → `web_search.enabled_for_*` | |
| | - 无 mcp 配置时不产生 web_search | |
| | - `mcp.tools` 被丢弃，不迁移到新配置 | |
| `tests/test_llm_scraper.py`（新增） | 搜索注入 | 5 |
| | - `_inject_search("zhipu")` 注入 tools | |
| | - `_inject_search("qwen")` 注入 enable_search | |
| | - `_inject_search("minimax")` 注入 plugins | |
| | - `_inject_search("none")` 不修改 payload | |
| | - `_inject_search("openai")` 不修改 payload | |
| `tests/test_llm_scraper.py`（追加） | 搜索场景路由 | 5 |
| | - `scrape` + enabled → 注入参数 | |
| | - `series_scrape` + enabled → 注入参数 | |
| | - `source_cleaner` + disabled → 不注入 | |
| | - `scrape_with_context` → 不注入（无 scenario） | |
| | - `enabled=false` → 不注入 | |
| `tests/test_llm_scraper.py`（追加） | 异常处理与层次化降级 | 8 |
| | - 搜索额度不足（429 + search 关键字）→ 搜索降级成功 | |
| | - 搜索功能不可用（400 + plugin 关键字）→ 搜索降级成功 | |
| | - 认证失败（401）→ 不搜索降级，抛 LLMApiError | |
| | - 全局限流（429 无搜索关键字）→ 不搜索降级 | |
| | - 搜索降级后仍失败 → 抛 LLMApiError | |
| | - 降级时记录 WARNING 日志 | |
| | - `_build_payload` 生成正确的 OpenAI 格式 | |
| | - `_send_request` 正确提取 `choices[0].message.content` | |
| `tests/test_llm_scraper.py`（追加） | 响应解析容错 | 3 |
| | - 搜索结果包含 `[1]` 引用标记时 `_parse_response` 仍能提取 JSON | |
| | - 搜索结果包含额外文本时 JSON 提取正确 | |
| | - 删除 MCP 方法后现有 scrape 流程不受影响 | |

### 9.3 集成测试

| 测试文件 | 测试内容 | 数量 |
|----------|---------|------|
| `tests/test_config_round_trip.py`（追加） | 配置写入 → 读取 → 验证 web_search + fast_model 字段完整 | 2 |
| `tests/test_architecture_guards.py`（追加） | `features/mcp/` 不存在 | 1 |
| | `llm_scraper.py` 不导入 mcp 相关模块 | 1 |

### 9.4 测试策略

- **Phase 1 完成后**：运行现有测试确保删除不破坏功能
- **Phase 2 完成后**：运行配置层单元测试
- **Phase 3 完成后**：运行 LLMScraper 单元测试 + 全量非 UI 测试
- **Phase 4 完成后**：手动验证前端手风琴交互、配置分组和必填校验
- **Phase 5**：全量测试 + 编译检查

### 9.5 手动验证项（需要前端配置 + API Key）

以下测试需要用户在前端配置好 LLM API Key 后手动触发：

1. 配置 AI 刮削（API Key + base_url + model），触发一次刮削任务，验证结果正常
2. 开启联网搜索（选择正确的搜索提供商），触发一次刮削，验证结果包含最新信息
3. 故意选择错误的搜索提供商，验证搜索降级正常工作
4. 配置 AI 辅助（fast_model），触发一次标题清洗，验证结果正常
5. 不配置 AI 辅助，验证系统提示"必须配置"

### 9.6 不需要测试的内容

- 实际调用厂商 API 的联网搜索（需要真实 API Key，属于手动验证）
- 前端 UI 渲染（无自动化测试环境）
- OpenAI Responses API（初期不支持）

## 10. 实施细节（执行者必读）

本节是计划的核心实施指南，包含每个文件的具体修改点、精确代码和注意事项。
**执行者应先通读本节，再按 Phase 顺序实施。**

### 10.1 config_view.py 精确变更

**文件**：`media_importer/core/config_view.py`

#### 10.1.1 LLMConfig 数据类（第 81-97 行区域）

变更内容：
- 删除 `mcp: dict = field(default_factory=dict)`
- 新增 `web_search: dict = field(default_factory=dict)`

修改后完整 LLMConfig：

```python
@dataclass(frozen=True)
class LLMConfig:
    api_key: str = ""
    base_url: str = "https://api.openai.com/v1"
    model: str = "gpt-3.5-turbo"
    fast_model: str = ""
    fast_base_url: str = ""
    fast_api_key: str = ""
    source_cleaner_model: str = "gpt-4o-mini"
    timeout: int = 30
    max_retries: int = 2
    retry_delay: int = 3
    fallback_model: str = ""
    confidence_threshold: float = 0.8
    verify_ssl: bool = True
    system_prompt: str = ""
    web_search: dict = field(default_factory=dict)
```

#### 10.1.2 from_dict 中 LLMConfig 构造（第 197-213 行区域）

**当前代码第 204 行**：
```python
source_cleaner_model=llm.get("fast_model", "") or llm.get("model", "gpt-4o-mini"),
```

**问题**：当前 YAML 不支持 `source_cleaner_model` 独立键，该值完全从 `fast_model` 和 `model` 推导。

**修改为**（新增三级 fallback）：
```python
source_cleaner_model=llm.get("source_cleaner_model", "") or llm.get("fast_model", "") or llm.get("model", "gpt-4o-mini"),
```

这意味着：YAML 有 `source_cleaner_model` → 用它；没有 → 用 `fast_model`；也没有 → 用 `model`。

**当前代码第 212 行**：
```python
mcp=_dict(llm.get("mcp", {})),
```

**修改为**：
```python
web_search=_dict(llm.get("web_search", {})),
```

#### 10.1.3 effective_fast_model 属性（第 98-100 行）

**不修改**。保持现有 fallback 逻辑：`fast_model || fallback_model || model`。这个属性被 `LLMScraper.__init__` 读取赋给 `self.fast_model`，行为不变。

### 10.2 SourceCleaner 兼容性说明

**文件**：`media_importer/features/source_cleaning/cleaner.py`

SourceCleaner **不经过 LLMScraper**，有独立的 `_call_llm` 方法（第 336-354 行）。

#### 当前配置读取（第 315-322 行）：

```python
api_key = llm_config.api_key                              # 始终用主 API Key
api_base = llm_config.effective_fast_base_url             # fast_base_url || base_url
model = llm_config.source_cleaner_model                   # source_cleaner_model
```

**关键点**：
- `api_key` 读的是 `llm_config.api_key`（主 Key），**不是** `effective_fast_api_key`
- `api_base` 读的是 `effective_fast_base_url`（属性），即 `fast_base_url || base_url`
- `model` 读的是 `source_cleaner_model` 字段

#### 需要做的修改

**SourceCleaner 的 `_call_llm` 和 `_ai_analyze_directory` 不需要任何修改。**

原因：我们修改了 `from_dict` 中 `source_cleaner_model` 的取值链（10.1.2），让它支持 `source_cleaner_model` → `fast_model` → `model` 三级 fallback。SourceCleaner 读到的值会自动跟随变化，代码无需改动。

**SourceCleaner 不受搜索注入影响**：因为它有独立的 `_call_llm`，不经过 `LLMScraper._do_call`，不会注入搜索参数。

### 10.3 LLMScraper 精确变更

**文件**：`media_importer/scraper/llm_scraper.py`

#### 10.3.1 异常类定义（文件开头，第 13 行区域）

**当前**：
```python
class LLMScrapeError(Exception):
    pass
```

**修改为**：
```python
class LLMApiError(Exception):
    pass

class LLMWebSearchError(Exception):
    pass

class LLMScrapeError(LLMApiError):
    pass
```

**设计说明**：
- `LLMScrapeError` 继承 `LLMApiError`，现有 `except LLMScrapeError` 代码仍然有效
- `_retry_with_fallback` 的 except 子句改为捕获 `LLMApiError`（同时兼容旧 `LLMScrapeError`）
- `_do_call` 中搜索降级只捕获 `LLMWebSearchError`

#### 10.3.2 构造函数变更（第 20-56 行区域）

**当前签名**：`def __init__(self, config: dict, mcp_client=None)`

**修改为**：`def __init__(self, config: dict)`

**删除**：
```python
self.mcp_client = mcp_client
self._use_mcp = False
if self.mcp_client and hasattr(self.mcp_client, 'is_available'):
    self._use_mcp = self.mcp_client.is_available()
```

**新增**（在构造函数末尾）：
```python
ws_dict = llm_config.web_search or {}
self.web_search_config = WebSearchConfig(
    enabled=ws_dict.get("enabled", False),
    provider=ws_dict.get("provider", "none"),
    enabled_for_scrape=ws_dict.get("enabled_for_scrape", True),
    enabled_for_series_scrape=ws_dict.get("enabled_for_series_scrape", True),
    enabled_for_source_cleaner=ws_dict.get("enabled_for_source_cleaner", False),
)
```

**新增导入**（文件顶部）：
```python
from media_importer.features.scraping.web_search_config import WebSearchConfig
```

#### 10.3.3 _build_payload 新增方法

在 `_do_call` 之前新增：

```python
def _build_payload(self, system_prompt: str, user_content: str, model: str) -> dict:
    return {
        'model': model,
        'messages': [
            {'role': 'system', 'content': system_prompt},
            {'role': 'user', 'content': user_content}
        ],
        'temperature': 0.3
    }
```

#### 10.3.4 _send_request 新增方法

```python
def _send_request(self, url: str, payload: dict, api_key: str) -> str:
    headers = {
        'Content-Type': 'application/json',
        'Authorization': f'Bearer {api_key}'
    }
    data = json.dumps(payload).encode('utf-8')
    req = urllib.request.Request(url, data=data, headers=headers, method='POST')
    ctx = None
    if not self.verify_ssl:
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
    try:
        with urllib.request.urlopen(req, timeout=self.timeout, context=ctx) as response:
            response_data = response.read().decode('utf-8')
            result = json.loads(response_data)
            return result['choices'][0]['message']['content']
    except urllib.error.HTTPError as e:
        body = {}
        try:
            body = json.loads(e.read().decode('utf-8'))
        except Exception:
            pass
        raise self._classify_error(e.code, body)
    except Exception as e:
        raise LLMApiError(f"request failed: {e}") from e
```

#### 10.3.5 _inject_search 新增方法

```python
def _inject_search(self, payload: dict, provider: str) -> None:
    if provider == "zhipu":
        payload["tools"] = [{"type": "web_search", "web_search": {"enable": True}}]
    elif provider == "qwen":
        payload["enable_search"] = True
    elif provider == "minimax":
        payload["plugins"] = ["web_search"]
```

#### 10.3.6 _classify_error 新增方法

```python
def _classify_error(self, status_code: int, body: dict) -> Exception:
    err_msg = str(body).lower()
    if status_code in (401, 403):
        return LLMApiError(f"auth failed: {status_code}")
    if status_code == 429:
        if any(kw in err_msg for kw in ["web_search", "search", "quota"]):
            return LLMWebSearchError(f"web search quota exceeded: {body}")
        return LLMApiError(f"rate limited: {body}")
    if status_code == 400:
        if any(kw in err_msg for kw in ["web_search", "search", "plugin", "tool"]):
            return LLMWebSearchError(f"web search not available: {body}")
        return LLMApiError(f"bad request: {body}")
    if status_code >= 500:
        return LLMApiError(f"server error: {status_code}")
    return LLMApiError(f"unknown error: {status_code} {body}")
```

#### 10.3.7 _do_call 重写（替换当前第 84-120 行）

**新签名**：`def _do_call(self, system_prompt, user_content, model, base_url, api_key, scenario=None)`

```python
def _do_call(self, system_prompt: str, user_content: str, model: str,
             base_url: str, api_key: str, scenario: str = None) -> str:
    url = f"{base_url.rstrip('/')}/chat/completions"
    payload = self._build_payload(system_prompt, user_content, model)

    if scenario and self.web_search_config.should_search(scenario):
        provider = self.web_search_config.effective_provider()
        self._inject_search(payload, provider)

    try:
        return self._send_request(url, payload, api_key)
    except LLMWebSearchError as e:
        logger.warning("web search failed, falling back to normal call: %s", e)
        fallback_payload = self._build_payload(system_prompt, user_content, model)
        return self._send_request(url, fallback_payload, api_key)
```

#### 10.3.8 _call_api 和 _call_fast_api 修改

**_call_api**（添加 scenario 参数）：
```python
def _call_api(self, system_prompt: str, user_content: str, model: str,
              scenario: str = None) -> str:
    return self._do_call(system_prompt, user_content, model,
                         self.base_url, self.api_key, scenario=scenario)
```

**_call_fast_api**（不添加 scenario，辅助任务不需要搜索）：
```python
def _call_fast_api(self, system_prompt: str, user_content: str) -> str:
    return self._do_call(system_prompt, user_content, self.fast_model,
                         self.fast_base_url, self.fast_api_key)
```

#### 10.3.9 _retry_with_fallback 完整重写（替换当前第 171-200 行）

```python
def _retry_with_fallback(self, system_prompt: str, user_content: str,
                          use_fast: bool = False, scenario: str = None) -> Dict[str, Any]:
    if use_fast:
        models_to_try = [self.fast_model]
        call_fn = self._call_fast_api
    else:
        models_to_try = [self.model]
        if self.fallback_model and self.fallback_model != self.model:
            models_to_try.append(self.fallback_model)
        call_fn = self._call_api

    last_error = None

    for model in models_to_try:
        for attempt in range(self.max_retries):
            try:
                if use_fast:
                    raw_response = call_fn(system_prompt, user_content)
                else:
                    raw_response = call_fn(system_prompt, user_content, model, scenario=scenario)
                return self._parse_response(raw_response)
            except (LLMScrapeError, LLMApiError) as e:
                last_error = e
                if attempt < self.max_retries - 1:
                    time.sleep(self.retry_delay)
                continue

    if last_error:
        raise last_error
    raise LLMScrapeError("所有重试均失败")
```

**与当前代码的差异**：
1. 新增 `scenario` 参数，透传给 `_call_api`
2. except 子句从 `LLMScrapeError` 改为 `(LLMScrapeError, LLMApiError)`，兼容新旧异常
3. `use_fast=True` 路径不传 scenario（fast 通道永远不注入搜索）

#### 10.3.10 业务方法 scenario 传入

| 方法 | 当前调用 | 修改为 |
|------|---------|--------|
| `scrape` (第 213 行) | `_retry_with_fallback(sp, uc)` | `_retry_with_fallback(sp, uc, scenario="scrape")` |
| `scrape_with_context` (第 268 行) | `_retry_with_fallback(sp, uc, use_fast=True)` | **不变**（use_fast=True 不走搜索） |
| `scrape_series` (第 278 行) | `_retry_with_fallback(sp, uc)` | `_retry_with_fallback(sp, uc, scenario="series_scrape")` |
| `scrape_series_with_context` (第 294 行) | `_retry_with_fallback(sp, uc)` | `_retry_with_fallback(sp, uc, scenario="series_scrape")` |
| `extract_title` (第 202 行) | `_call_fast_api(sp, uc)` | **不变** |

**注意**：`scrape_series_with_context` 传 `scenario="series_scrape"` 但 `use_fast=False`（保持当前行为，使用主模型通道）。搜索注入会在主模型通道的 `_do_call` 中发生。

#### 10.3.11 删除全部 MCP 相关代码

删除以下方法和成员（约第 296-459 行）：

- `self.mcp_client` / `self._use_mcp`（构造函数中）
- `_call_llm_with_tools`
- `_scrape_with_tools_async`
- `_call_api_with_tools`
- `scrape_with_mcp`
- `scrape_series_with_mcp`
- `scrape_with_context_mcp`

### 10.4 config_migrations.py 精确变更

**文件**：`media_importer/core/config_migrations.py`

在文件末尾新增迁移函数，并在 `load_config` 的调用链中注册它。

```python
def _migrate_mcp_to_web_search(config: dict) -> None:
    llm = config.get("llm", {})
    if "mcp" not in llm:
        return

    mcp = llm.pop("mcp")

    if mcp.get("enabled"):
        scenarios = mcp.get("scenarios", {})
        llm["web_search"] = {
            "enabled": True,
            "provider": "none",
            "enabled_for_scrape": scenarios.get("scrape", True),
            "enabled_for_series_scrape": scenarios.get("series_scrape", True),
            "enabled_for_source_cleaner": scenarios.get("source_cleaner", False),
        }

    llm.pop("provider", None)
```

**在 `config_loader.py` 的 `load_config()` 末尾调用**：
```python
_migrate_mcp_to_web_search(config)
```

### 10.5 前端精确变更

#### 10.5.1 index.html

**替换范围**：当前 `data-config-panel="ai"` 整个 section 的内容（约第 500-630 行区域），用 §3.8.1 的新 HTML 替换。

**替换步骤**：
1. 定位 `<section class="config-stage-panel" data-config-panel="ai">` 开始标签
2. 定位对应的 `</section>` 结束标签
3. 替换内部全部内容为 §3.8.1 的新 HTML
4. 删除 `cfg-llm_provider-inline` 下拉框（如果新 HTML 中不包含它）

**额外注意**：`system_prompt` 字段在当前 HTML 中有一个 textarea。新 HTML 中未包含此字段的 UI 元素，但保存逻辑中用 `llm.system_prompt || ''` 保持原值。这意味着用户将无法在前端编辑 system_prompt，但配置不会丢失。如果需要保留编辑功能，在"AI 刮削"区块末尾（联网搜索之前）添加：

```html
<label class="form-card form-card-full">
  <span>自定义系统提示词</span>
  <textarea id="cfg-llm_system_prompt" rows="3" placeholder="留空使用默认提示词"></textarea>
  <p>高级选项。影响 AI 刮削时的系统提示词。</p>
</label>
```

加载逻辑追加：
```javascript
document.getElementById('cfg-llm_system_prompt').value = llm.system_prompt || '';
```

保存逻辑修改：
```javascript
system_prompt: document.getElementById('cfg-llm_system_prompt')?.value || llm.system_prompt || '',
```

#### 10.5.2 config.css 新增样式

**文件**：`media_importer/webui/css/config.css`

在文件末尾追加以下样式：

```css
.config-collapse-card {
  border: 1px solid var(--border-color, #e0e0e0);
  border-radius: 8px;
  overflow: hidden;
  margin-bottom: 8px;
}

.config-collapse-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 12px 16px;
  cursor: pointer;
  background: var(--surface-secondary, #f8f9fa);
  user-select: none;
}

.config-collapse-header:hover {
  background: var(--surface-hover, #f0f1f3);
}

.config-collapse-header-left {
  display: flex;
  align-items: flex-start;
  gap: 8px;
}

.config-collapse-header-left b {
  display: block;
  font-size: 14px;
}

.config-collapse-header-left small {
  display: block;
  color: var(--text-secondary, #888);
  font-size: 12px;
  margin-top: 2px;
}

.config-collapse-chevron {
  font-size: 12px;
  line-height: 1;
  margin-top: 2px;
  transition: transform 0.2s ease;
}

.config-collapse-card.expanded .config-collapse-chevron {
  transform: rotate(90deg);
}

.config-collapse-body {
  max-height: 0;
  overflow: hidden;
  transition: max-height 0.3s ease-out;
  padding: 0 16px;
}

.config-collapse-body.open {
  max-height: 2000px;
  padding: 16px;
}

.config-collapse-sub .config-collapse-header {
  background: var(--surface-tertiary, #f0f1f3);
  padding: 8px 12px;
  border-top: 1px solid var(--border-color, #e0e0e0);
}

.config-collapse-sub .config-collapse-body {
  border-top: none;
}

.config-collapse-status {
  font-size: 12px;
  padding: 2px 8px;
  border-radius: 4px;
  background: var(--badge-bg, #e8e8e8);
  color: var(--text-secondary, #888);
}

.config-collapse-status.configured {
  background: var(--success-bg, #e8f5e9);
  color: var(--success-text, #2e7d32);
}

.config-guide-card {
  background: var(--info-bg, #e3f2fd);
  border: 1px solid var(--info-border, #bbdefb);
  border-radius: 6px;
  padding: 12px 16px;
  margin-bottom: 8px;
}

.config-guide-card > span {
  font-weight: 600;
  display: block;
  margin-bottom: 8px;
}

.config-guide-list.compact > div {
  margin-bottom: 6px;
  padding-left: 8px;
}

.config-guide-list.compact b {
  font-size: 13px;
}

.config-guide-list.compact small {
  display: block;
  color: var(--text-secondary, #666);
  font-size: 12px;
  margin-top: 1px;
}

.required-mark {
  color: var(--error-text, #d32f2f);
}
```

#### 10.5.3 config.js / cinema-config.js / cinema-app.js 变更

**关键变更列表**：

| 文件 | 变更 |
|------|------|
| `config.js` | 删除 `provider` 读取（第 312 行区域）、保存（第 759 行区域）、测试连通性（第 1296 行区域） |
| `cinema-app.js` | 删除 `setFieldValue("cfg-llm_provider-inline", ...)` （第 488 行区域） |
| `cinema-config.js` | 删除 `provider: ...` 保存（第 136 行区域）、测试连通性（第 714 行区域） |

**新增**：所有手风琴交互代码（§3.8.2）、状态检测（§3.8.4）、保存校验（§3.8.5）、配置加载/保存（§3.8.6）。

**ID 替换**：将所有 `cfg-llm_*-inline` 引用替换为 `cfg-llm_*`（去掉 `-inline` 后缀）。使用 `grep -r "cfg-llm.*-inline" media_importer/webui/` 确认所有引用。

### 10.6 新增文件

#### 10.6.1 web_search_config.py

**路径**：`media_importer/features/scraping/web_search_config.py`

```python
from dataclasses import dataclass

@dataclass(frozen=True)
class WebSearchConfig:
    enabled: bool = False
    provider: str = "none"
    enabled_for_scrape: bool = True
    enabled_for_series_scrape: bool = True
    enabled_for_source_cleaner: bool = False

    def should_search(self, scenario: str) -> bool:
        if not self.enabled:
            return False
        if self.provider == "none":
            return False
        if scenario == "scrape":
            return self.enabled_for_scrape
        elif scenario == "series_scrape":
            return self.enabled_for_series_scrape
        elif scenario == "source_cleaner":
            return self.enabled_for_source_cleaner
        return False

    def effective_provider(self) -> str:
        return self.provider
```

### 10.7 每个阶段的具体文件清单

#### Phase 1: 清理旧代码

| 操作 | 文件 |
|------|------|
| 删除目录 | `media_importer/features/mcp/` |
| 移入归档 | `docs/features/mcp_integration.md` → `docs/_archive/` |
| 移入归档 | `docs/plans/2026-06-08-mcp-search-integration.md` → `docs/_archive/` |
| 删除 MCP 方法 | `media_importer/scraper/llm_scraper.py`（第 296-459 行区域） |
| 删除 mcp_client 参数 | `media_importer/scraper/llm_scraper.py`（构造函数签名 + 内部赋值） |
| 删除 mcp 字段 | `media_importer/core/config_view.py`（`mcp: dict` + from_dict 中的 `mcp=`） |
| 删除 provider 字段 | `config/config.yaml`、`config.yaml.example`、`webui/index.html`、`webui/legacy-config.html`、`webui/js/config.js`、`webui/js/cinema-app.js`、`webui/js/cinema-config.js`、`media_importer/api/connectivity_handlers.py` |

**验证**：`python -m compileall -q media_importer` + `python -m pytest tests/ --ignore=tests/test_*_ui.py --ignore=tests/test_frontend_*.py`

#### Phase 2: 新增配置层

| 操作 | 文件 |
|------|------|
| 新增 | `media_importer/features/scraping/web_search_config.py` |
| 修改 | `media_importer/core/config_view.py`（新增 `web_search` 字段、修改 `source_cleaner_model` 取值链） |
| 修改 | `media_importer/core/config_migrations.py`（新增 `_migrate_mcp_to_web_search`） |
| 修改 | `media_importer/core/config_loader.py`（新增 import + 调用 `_migrate_mcp_to_web_search`，见 §10.9） |
| 修改 | `config.yaml.example`（新增 `web_search` 配置示例，见 §10.13） |
| 修改 | `media_importer/api/config_handlers.py`（新增 `("llm", "fast_api_key")` 脱敏，见 §10.10） |

**验证**：新增 `tests/test_web_search_config.py` + `python -m pytest tests/test_config_view.py tests/test_web_search_config.py`

#### Phase 3: 核心逻辑改造

| 操作 | 文件 |
|------|------|
| 修改 | `media_importer/scraper/llm_scraper.py`（按 10.3 节全部变更） |

**验证**：新增 `tests/test_llm_scraper.py` + `python -m pytest tests/ --ignore=tests/test_*_ui.py`

#### Phase 4: 前端配置

| 操作 | 文件 |
|------|------|
| 重写 AI 配置区域 | `media_importer/webui/index.html` |
| 新增手风琴样式 | `media_importer/webui/css/config.css` |
| 修改配置加载/保存 | `media_importer/webui/js/config.js` |
| 修改配置加载/保存 | `media_importer/webui/js/cinema-app.js` |
| 修改配置加载/保存 | `media_importer/webui/js/cinema-config.js` |

**验证**：启动服务手动验证

#### Phase 5: 测试与文档

| 操作 | 文件 |
|------|------|
| 新增 | `tests/test_web_search_config.py` |
| 新增 | `tests/test_llm_scraper.py` |
| 追加 | `tests/test_config_view.py`（web_search 字段测试） |
| 追加 | `tests/test_config_migrations.py`（mcp 迁移测试） |
| 追加 | `tests/test_architecture_guards.py`（MCP 目录不存在断言） |

**验证**：`python -m pytest tests/ --ignore=tests/test_*_ui.py` + `python -m compileall -q media_importer`

### 10.8 注意事项清单

1. **不要修改 SourceCleaner**（`features/source_cleaning/cleaner.py`）：它有独立的 `_call_llm`，不经过 LLMScraper，搜索注入不影响它。`source_cleaner_model` 取值链的变更通过 `config_view.py` 的 `from_dict` 自动生效。

2. **不要修改 `_parse_response`**：现有的正则提取 JSON 逻辑已经足够健壮（处理 think 标签、代码块等），搜索增强后的响应通常仍包含有效 JSON。

3. **`effective_fast_model` 属性不修改**：保持 `fast_model || fallback_model || model` 的 fallback 逻辑。`LLMScraper.__init__` 读取它赋给 `self.fast_model`，行为不变。

4. **`_call_fast_api` 不添加 scenario 参数**：辅助任务（标题提取、Provider 数据整理）永远不需要搜索注入。

5. **`_do_call` 搜索降级只重试一次**：不是无限重试。搜索降级 = 去掉搜索参数重发一次，如果还是失败就抛异常给上层的模型降级层。

6. **前端 ID 去掉 `-inline` 后缀是破坏性变更**：需要同时更新所有 JS 文件中的 `getElementById` 调用。用 `grep -r "cfg-llm.*-inline" media_importer/webui/` 确认无遗漏。

7. **`web_search` 字段在 ConfigView 中是透传 dict**：不结构化为独立数据类。只有 `LLMScraper.__init__` 会把它解析为 `WebSearchConfig`。前端保存/加载也是直接操作 dict。

8. **config.yaml.example 需要同步更新**：删除 `mcp` 和 `provider` 配置节，新增 `web_search` 配置节（含完整注释）。

### 10.9 补充：config_loader.py 集成细节

**文件**：`media_importer/core/config_loader.py`

#### 10.9.1 新增导入（第 8-14 行区域）

当前导入：
```python
from .config_migrations import (
    _migrate_confidence_v1_to_v2,
    _migrate_source_policy,
    _normalize_bool_strings,
    BOOL_TRUE_STRINGS,
    BOOL_FALSE_STRINGS,
)
```

**修改为**：
```python
from .config_migrations import (
    _migrate_confidence_v1_to_v2,
    _migrate_source_policy,
    _migrate_mcp_to_web_search,
    _normalize_bool_strings,
    BOOL_TRUE_STRINGS,
    BOOL_FALSE_STRINGS,
)
```

#### 10.9.2 调用位置（`load_config()` 函数内）

在 `_normalize_bool_strings(config)` 之前调用（第 258 行区域，`return config` 之前两行）：

```python
    _normalize_bool_strings(config)

    return config
```

**修改为**：

```python
    _migrate_mcp_to_web_search(config)
    _normalize_bool_strings(config)

    return config
```

**位置说明**：`_migrate_mcp_to_web_search` 放在 `_normalize_bool_strings` 之前，因为迁移可能引入新的 `enabled` 字段（布尔值），后续 `_normalize_bool_strings` 会正确处理字符串 `"true"` / `"false"` 到布尔值的转换。`BOOL_KEYS` 已包含 `'enabled'`。

### 10.10 补充：敏感字段脱敏

**文件**：`media_importer/api/config_handlers.py`

#### 10.10.1 `_filter_sensitive_fields` 方法（第 197-215 行区域）

当前敏感字段列表：
```python
sensitive_fields = [
    ("server", "api_key"),
    ("llm", "api_key"),
    ("hermes", "webhook", "secret"),
]
```

**修改为**：
```python
sensitive_fields = [
    ("server", "api_key"),
    ("llm", "api_key"),
    ("llm", "fast_api_key"),
    ("hermes", "webhook", "secret"),
]
```

**原因**：`fast_api_key` 是 AI 辅助区块的 API Key，与 `llm.api_key` 同等敏感。用户在前端留空时前端传空字符串（不是 `***`），此时不会触发脱敏删除，保持 pass-through 行为；用户已填值时，GET 返回 `***`，保存时如果前端传回 `***` 则删除该字段不覆盖原值。

### 10.11 补充：不需要修改的文件（执行者必读）

以下文件在本次变更中**明确不需要修改**，执行者不应触碰：

| 文件 | 不修改原因 |
|------|-----------|
| `media_importer/features/scraping/__init__.py` | 当前第 20 行 `from media_importer.scraper.llm_scraper import LLMScrapeError, LLMScraper`。`LLMScrapeError` 改为继承 `LLMApiError` 后，类本身仍然存在，re-export 路径不变。`WebSearchConfig` 是内部类，不需要 re-export。 |
| `media_importer/features/source_cleaning/cleaner.py` | 独立 `_call_llm`，不经过 `LLMScraper`。`source_cleaner_model` 取值链变更通过 `config_view.py` 的 `from_dict` 自动生效（见 §10.2）。 |
| `media_importer/features/scraping/metadata_scraper.py` | 第 25 行 `LLMScraper(config)` 调用不变（未传 `mcp_client`）。 |
| `media_importer/api/tmdb_handlers.py` | 第 265 行 `LLMScraper(globals._config)` 调用不变（未传 `mcp_client`）。 |
| `tests/test_scrape_ui.py` | 其中的 `test_provider_*` 函数测试的是 **metadata providers**（TMDB 等元数据刮削器），使用选择器 `data-section="metadata.providers"` 和 `.provider-card`。与 LLM 配置中的 `provider` 下拉框完全无关，不受影响。 |
| `tests/test_config_view.py` | 第 137 行创建 `LLMScraper({"llm": {...}})` 不传 `mcp_client`。构造函数删除 `mcp_client` 参数后，该调用仍然有效（不传多余参数）。`web_search_config` 从 `llm_config.web_search` 构建，测试 config 中无 `web_search` 键时会得到空 dict 默认值，行为正确。 |
| `tests/test_feature_entrypoints.py` | 第 246-250 行从 `features.scraping` 导入 `LLMScraper`。由于 `features/scraping/__init__.py` 不变，re-export 路径不变，测试应继续通过。 |

### 10.12 补充：system_prompt 前端处理决策

**决策**：在新的手风琴布局中**不提供** `system_prompt` 的 UI 编辑入口。

**原因**：
1. `system_prompt` 是高级用户功能，大多数用户不需要修改
2. 当前已有 `config/scraper_prompts.md` 文件提供提示词自定义
3. YAML 中 `system_prompt` 的值通过保存逻辑 `system_prompt: llm.system_prompt || ''` 自动保留

**保存逻辑**（§3.8.6 中已有）：
```javascript
system_prompt: llm.system_prompt || '',
```

这行确保前端不发送 `system_prompt` 时，YAML 中的现有值被保留。如果将来需要提供编辑入口，可参考 §10.5.1 末尾的 textarea 扩展方案。

### 10.13 补充：config.yaml.example 精确内容

**文件**：`config/config.yaml.example`

#### 删除内容（第 210-244 行区域）

将当前整个 `llm:` 配置块：
```yaml
llm:
  provider: "openai"              # LLM提供商
  api_key: ""                     # [必须] API密钥
  base_url: "https://api.openai.com/v1" # API地址，可改为国内代理或其他兼容接口
  model: "gpt-3.5-turbo"         # 主模型名称
  timeout: 30                     # API超时时间（秒）
  max_retries: 2                  # 最大重试次数
  retry_delay: 3                  # 重试间隔（秒）
  fallback_model: "gpt-3.5-turbo" # 备选模型（主模型失败时降级使用）
  fast_model: ""                  # 快速模型（标题清洗+TMDB结果整理，留空则使用fallback_model）
  fast_base_url: ""               # 快速模型API地址（留空则使用base_url）
  fast_api_key: ""                # 快速模型API密钥（留空则使用api_key）
  confidence_threshold: 0.8       # AI置信度阈值（低于此值的刮削结果将被拒绝）
  verify_ssl: true                # 是否验证SSL证书（代理环境可设为false）
  system_prompt: ""               # 如需自定义刮削提示词，请在 config/scraper_prompts.md 中配置
  
  # MCP (Model Context Protocol) 工具集成配置
  mcp:
    enabled: false                # 是否启用MCP工具集成
    # MCP工具列表
    tools:
      - name: web_search
        type: web_search          # 使用web_search_prime MCP
        enabled: true
        config: {}
      - name: browser
        type: integrated_browser
        enabled: false
        config: {}
    # 哪些场景启用MCP
    scenarios:
      scrape: true                # 纯AI刮削时启用
      scrape_with_context: false  # 已有Provider上下文时不启用
      series_scrape: true         # 整剧刮削时启用
      source_cleaner: false       # 源目录清理时不启用
```

#### 替换为

```yaml
llm:
  api_key: ""                     # [必须] AI刮削API密钥
  base_url: "https://api.openai.com/v1" # API地址，支持所有兼容OpenAI格式的服务
  model: "gpt-3.5-turbo"         # 刮削模型（用于纯AI刮削和整剧刮削）
  timeout: 30                     # API超时时间（秒）
  max_retries: 2                  # 最大重试次数
  retry_delay: 3                  # 重试间隔（秒）
  fallback_model: "gpt-3.5-turbo" # 备选模型（主模型失败时降级使用）
  fast_model: ""                  # 辅助模型（标题清洗、数据整理等，留空则使用刮削模型）
  fast_base_url: ""               # 辅助模型API地址（留空则使用base_url）
  fast_api_key: ""                # 辅助模型API密钥（留空则使用api_key）
  source_cleaner_model: ""        # 源目录清理模型（留空则使用辅助模型）
  confidence_threshold: 0.8       # AI置信度阈值（低于此值的刮削结果将被拒绝）
  verify_ssl: true                # 是否验证SSL证书（代理环境可设为false）
  system_prompt: ""               # 如需自定义刮削提示词，请在 config/scraper_prompts.md 中配置

  # 联网搜索增强配置
  web_search:
    enabled: false                # 是否启用联网搜索增强
    provider: "none"              # 搜索提供商：
                                  #   "zhipu"   - 智谱 GLM web_search
                                  #   "minimax" - MiniMax web_search
                                  #   "qwen"    - 通义千问 enable_search
                                  #   "openai"  - OpenAI web_search_preview（暂不支持）
                                  #   "none"    - 不启用
    enabled_for_scrape: true      # 纯AI刮削时启用搜索
    enabled_for_series_scrape: true # 整剧刮削时启用搜索
```

**变更点**：
1. 删除 `provider: "openai"` 行
2. 新增 `source_cleaner_model: ""` 行
3. 将整个 `mcp:` 配置块替换为 `web_search:` 配置块
4. 更新注释措辞（"快速模型"→"辅助模型"等）

## 13. v4 修订记录（2026-06-10）

### 13.1 前端问题修复

**问题 1：手风琴折叠不生效**
- 根因：AI 刮削和 AI 辅助卡片缺少默认 `open` 类，CSS 选择器 `.config-collapse-card.open .config-collapse-body` 使用后代选择器导致嵌套子面板（联网搜索）被错误展开
- 修复：
  - HTML: `ai-scrape-card` 和 `ai-assist-card` 添加 `open` 类
  - CSS: 后代选择器改为直接子元素选择器 `>`
  - CSS: 手风琴样式从 `config.css`（仅 legacy-config.html 引用）迁移到 `cinema-pages.css`（index.html 引用）
  - JS: `data-collapse-toggle` 事件处理中排除 `input`、`.toggle-pill`、`label.toggle-pill` 的点击冒泡
  - 卡片间距从 16px 增加到 20px

**问题 2：LLM 有效性测试按钮报错**
- 根因：测试按钮不可见是因为它在 AI 刮削 body 中，body 因缺少 `open` 类而隐藏
- 修复后验证：测试按钮正常工作，显示"LLM API连通正常 (状态码: 200)"

**问题 3：联网搜索与 AI 辅助中源目录清理重叠**
- 决策：联网搜索仅服务于刮削场景（scrape + series_scrape），源目录清理使用辅助模型，不需要联网搜索
- 修复：
  - HTML: 移除联网搜索中的 `enabled_for_source_cleaner` 复选框
  - JS: 移除 `cinema-app.js`、`config.js`、`cinema-config.js` 中所有 `cfg-llm_web_search_enabled_for_source_cleaner` 引用
  - Python: `WebSearchConfig` 移除 `enabled_for_source_cleaner` 字段和对应路由逻辑
  - Python: `llm_scraper.py` 和 `config_migrations.py` 同步移除
  - 测试: 更新 44 个测试用例中所有相关断言

### 13.2 配置校验+演示功能

**新增功能**：AI 配置面板新增"运行演示"按钮，点击弹出演示弹窗，支持三个场景：

| 场景 | 使用的模型通道 | 示例输入 | 说明 |
|------|---------------|---------|------|
| AI 刮削演示 | 刮削模型 + 联网搜索 | Inception.2010.1080p.BluRay.x264.mp4 | 完整刮削流程 |
| 标题提取演示 | 辅助模型 (fast_model) | The.Dark.Knight.2008.2160p.UHD.BluRay.x265.mkv | 文件名清洗提取 |
| 源目录清理演示 | 清理模型 (source_cleaner_model) | sample.mp4 | 文件保留判断 |

**实现**：
- 后端: `POST /api/config/ai-demo` 端点（`connectivity_handlers.py`），接收 `scenario` 和 `config_override`
- 前端: Modal 弹窗（`index.html` body 末尾），CSS 样式（`cinema-pages.css`），JS 交互（`cinema-config.js` + `cinema-app.js`）
- 交互: 点击场景卡片 → 显示 loading → 调用后端 → 展示 JSON 结果 + 耗时
- 关闭方式: 关闭按钮、点击遮罩层、ESC 键

### 13.3 变更文件清单

| 文件 | 变更类型 | 说明 |
|------|---------|------|
| `media_importer/webui/index.html` | 修改 | 添加 open 类、移除 source_cleaner 复选框、添加演示按钮和弹窗 |
| `media_importer/webui/css/cinema-pages.css` | 修改 | 新增手风琴样式 + 演示弹窗样式，CSS 版本号升至 v6 |
| `media_importer/webui/js/cinema-app.js` | 修改 | 折叠事件排除 toggle-pill、移除 source_cleaner 加载、新增演示弹窗事件 |
| `media_importer/webui/js/cinema-config.js` | 修改 | 移除 source_cleaner web search 引用、新增 openAiDemoModal/closeAiDemoModal/runAiDemo |
| `media_importer/webui/js/config.js` | 修改 | 移除 source_cleaner web search 引用 |
| `media_importer/features/scraping/web_search_config.py` | 修改 | 移除 enabled_for_source_cleaner 字段和路由 |
| `media_importer/scraper/llm_scraper.py` | 修改 | 移除 enabled_for_source_cleaner 构造参数 |
| `media_importer/core/config_migrations.py` | 修改 | 迁移逻辑不再生成 enabled_for_source_cleaner |
| `media_importer/api/connectivity_handlers.py` | 修改 | 新增 _config_ai_demo 方法 |
| `media_importer/api/routes.py` | 修改 | 注册 /api/config/ai-demo 路由 |
| `tests/test_llm_web_search.py` | 修改 | 更新所有 source_cleaner 相关断言 |
