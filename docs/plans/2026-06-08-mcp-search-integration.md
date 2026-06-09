---
title: "feat: MCP Search Integration for LLM Scraping"
type: plan
date: 2026-06-08
status: draft
confidence: high
---

# MCP 搜索集成方案

## 概述

当前LLM刮削器缺少实时联网搜索能力，需要集成MCP (Model Context Protocol) 工具来提供：
1. 互联网搜索能力（如 web_search_prime）
2. 浏览器自动化能力（如 integrated_browser）
3. 其他MCP工具能力扩展

## 背景与目标

### 现状

- 当前 [LLMScraper](file:///Users/wangwei/Documents/code/nas_media_manage/media_importer/scraper/llm_scraper.py) 仅支持基础文本补全，无工具调用能力
- [SourceCleaner](file:///Users/wangwei/Documents/code/nas_media_manage/media_importer/features/source_cleaning/cleaner.py) 已有AI分析，但同样无工具调用
- 项目已有良好的配置框架和Feature架构

### 目标

1. **最小侵入性**：在现有架构基础上新增MCP支持，不破坏现有功能
2. **可配置**：MCP工具和使用场景可配置
3. **可扩展**：易于添加新的MCP工具
4. **向后兼容**：不配置MCP时，仍按原流程工作

## 架构设计

### 总体架构

```
┌─────────────────────────────────────────────────────────────────┐
│                         LLM刮削流程                              │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ┌──────────────┐     ┌──────────────┐     ┌──────────────┐   │
│  │  文件名输入   │────▶│  LLM推理     │────▶│  刮削结果    │   │
│  └──────────────┘     └──────────────┘     └──────────────┘   │
│                             │                                   │
│                             ▼                                   │
│                    ┌─────────────────┐                          │
│                    │  MCP工具调用器   │                          │
│                    └─────────────────┘                          │
│                             │                                   │
│              ┌──────────────┼──────────────┐                    │
│              ▼              ▼              ▼                    │
│         ┌──────────┐  ┌──────────┐  ┌──────────┐               │
│         │ Web搜索  │  │ 浏览器   │  │ 其他工具 │               │
│         └──────────┘  └──────────┘  └──────────┘               │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### 核心模块

| 模块 | 文件位置 | 职责 |
|------|----------|------|
| **MCP客户端** | `features/mcp/mcp_client.py` | MCP工具发现、调用、响应解析 |
| **工具定义** | `features/mcp/tools/` | 具体MCP工具封装 |
| **刮削器集成** | `scraper/llm_scraper.py` 更新 | LLM工具调用流程集成 |
| **配置** | `core/config_view.py` 更新 | MCP相关配置项 |

## 实现细节

### Phase 1: MCP 客户端基础设施

#### 1.1 创建MCP模块结构

```
media_importer/features/mcp/
├── __init__.py
├── client.py           # MCP客户端核心
├── tools/
│   ├── __init__.py
│   ├── base.py         # 工具基类
│   ├── web_search.py   # Web搜索工具
│   └── browser.py      # 浏览器工具
└── config.py           # MCP配置模型
```

#### 1.2 配置模型扩展

更新 [`ConfigView`](file:///Users/wangwei/Documents/code/nas_media_manage/media_importer/core/config_view.py) 新增MCP配置：

```yaml
llm:
  # ... 现有配置 ...
  
  # MCP 配置
  mcp:
    enabled: false
    tools:
      - name: web_search_prime
        type: search
        config:
          # 工具特定配置
      - name: integrated_browser
        type: browser
        config:
          # 浏览器工具配置
    
    # 哪些刮削场景启用MCP
    scenarios:
      scrape: true        # 纯AI刮削时启用
      scrape_with_context: false  # 已有Provider上下文时禁用
      series_scrape: true # 整剧刮削时启用
      source_cleaner: false  # 源目录清理时禁用
```

### Phase 2: 工具定义与实现

#### 2.1 Web搜索工具 (`web_search_prime`)

根据可用的MCP工具，包装 `web_search_prime`：

```python
class WebSearchTool(MCPServer):
    name = "web_search_prime"
    tool_name = "web_search_prime"
    
    async def search(self, query: str, num_results: int = 5) -> List[SearchResult]:
        """执行搜索并返回结果"""
        pass
```

#### 2.2 浏览器工具 (`integrated_browser`)

```python
class BrowserTool(MCPServer):
    name = "integrated_browser"
    
    async def navigate(self, url: str):
        pass
    
    async def search(self, query: str):
        pass
```

### Phase 3: LLM刮削器集成

#### 3.1 更新LLMScraper支持工具调用

修改 [`LLMScraper`](file:///Users/wangwei/Documents/code/nas_media_manage/media_importer/scraper/llm_scraper.py)：

```python
class LLMScraper:
    def __init__(self, config: dict, mcp_client: Optional[MCPClient] = None):
        # ... 现有代码 ...
        self.mcp_client = mcp_client
        self.use_mcp = config.get("llm", {}).get("mcp", {}).get("enabled", False)
    
    def scrape_with_tools(self, video_filename: str, ...) -> Dict:
        """支持MCP工具调用的刮削方法"""
        # 1. 首次调用LLM
        # 2. 如果LLM返回工具调用，执行MCP工具
        # 3. 将工具结果附加到上下文
        # 4. 再次调用LLM获取最终结果
        pass
```

#### 3.2 工具调用流程

```
┌─────────────┐
│ 首次LLM调用 │
└──────┬──────┘
       │
       ├─ 需要搜索？
       │       │
       │       ▼
       │  ┌───────────────┐
       │  │ Web搜索       │
       │  └───────┬───────┘
       │          │
       │          ▼
       │  ┌───────────────┐
       │  │ 浏览器        │
       │  └───────┬───────┘
       │          │
       │          └─▶ 收集结果
       │
       ▼
  ┌───────────────┐
  │ 二次LLM调用   │
  │ (含工具结果)  │
  └───────┬───────┘
          │
          ▼
  ┌───────────────┐
  │ 返回刮削结果  │
  └───────────────┘
```

### Phase 4: 配置集成

#### 4.1 更新配置模板

更新 [`config.yaml.example`](file:///Users/wangwei/Documents/code/nas_media_manage/config.yaml.example) 新增MCP配置：

```yaml
llm:
  # ... 现有配置 ...
  
  # MCP (Model Context Protocol) 工具集成
  mcp:
    enabled: false              # 是否启用MCP工具
    
    # MCP工具列表
    tools:
      # Web搜索工具 (使用 web_search_prime MCP)
      - name: web_search
        type: web_search_prime
        enabled: true
        config:
          # 工具特定配置（如果需要）
          
      # 浏览器工具 (使用 integrated_browser MCP)
      - name: browser
        type: integrated_browser
        enabled: false
        config: {}
    
    # 使用场景配置
    scenarios:
      # 纯AI刮削时启用 (metadata_scraper.py:226+)
      scrape: true
      # 已有Provider上下文时是否使用 (通常不启用)
      scrape_with_context: false
      # 整剧刮削时启用
      series_scrape: true
      # 源目录清理时启用
      source_cleaner: false
```

## 使用场景设计

### 场景1: 纯AI刮削时搜索影视信息

```
输入: "Breaking.Bad.S01E01.1080p.mkv"

流程:
1. LLM 识别出剧名 Breaking Bad
2. LLM 决定需要搜索最新评分、官方译名等信息
3. 通过MCP调用 web_search_prime: "绝命毒师 Breaking Bad 评分 译名"
4. 将搜索结果附加到上下文
5. LLM 基于搜索结果输出完整刮削信息
```

### 场景2: 整剧刮削时搜索

```
输入: 剧名 "权力的游戏"

流程:
1. LLM 调用搜索工具查询该剧信息
2. 基于搜索结果判断地区、类型等维度
3. 输出整剧维度信息
```

### 场景3: 无MCP时的降级流程

```
当MCP未配置时：
- 保持现有行为不变
- 不进行任何工具调用
- 使用LLM自身知识进行刮削
```

## API与协议设计

### MCP客户端接口

```python
class MCPClient:
    def __init__(self, config: dict):
        pass
    
    async def call_tool(self, server_name: str, tool_name: str, args: dict) -> Any:
        """调用MCP工具"""
        pass
    
    async def list_tools(self) -> List[ToolInfo]:
        """列出可用工具"""
        pass
    
    def is_available(self) -> bool:
        """检查MCP是否可用"""
        pass
```

### LLM工具调用协议

使用标准的OpenAI函数调用协议（兼容其他模型）：

```json
{
  "messages": [
    {"role": "user", "content": "刮削视频文件名..."}
  ],
  "tools": [
    {
      "type": "function",
      "function": {
        "name": "web_search",
        "description": "搜索互联网获取信息",
        "parameters": {
          "type": "object",
          "properties": {
            "query": {"type": "string"},
            "num_results": {"type": "number"}
          },
          "required": ["query"]
        }
      }
    }
  ]
}
```

## 风险与缓解

| 风险 | 影响 | 缓解措施 |
|------|------|----------|
| MCP调用增加延迟 | 中 | 可配置场景禁用；缓存重复查询 |
| 无MCP时功能降级 | 低 | 保持向后兼容，不启用即可 |
| MCP工具依赖变化 | 中 | 抽象工具接口，可替换实现 |
| 搜索成本增加 | 低 | 可配置启用/禁用；限制调用次数 |

## 实施计划

### 阶段1: 基础设施 (第1-2天)
- [ ] 创建MCP模块结构
- [ ] 实现基础MCP客户端
- [ ] 配置模型扩展

### 阶段2: Web搜索工具 (第3-4天)
- [ ] 集成web_search_prime MCP
- [ ] 实现搜索工具包装
- [ ] 基础测试

### 阶段3: LLM集成 (第5-6天)
- [ ] 更新LLMScraper支持工具调用
- [ ] 实现刮削流程集成
- [ ] 端到端测试

### 阶段4: 文档与完善 (第7天)
- [ ] 更新配置文档
- [ ] 添加使用说明
- [ ] 完善错误处理

## 验收标准

1. ✅ MCP配置存在且默认禁用
2. ✅ 不配置MCP时，现有功能完全正常
3. ✅ 配置MCP后，刮削器可以调用搜索工具
4. ✅ 搜索结果能正确影响刮削输出
5. ✅ 所有现有测试通过

## 相关文档

- [`docs/features/scraping.md`](file:///Users/wangwei/Documents/code/nas_media_manage/docs/features/scraping.md)
- [`docs/ai-map.md`](file:///Users/wangwei/Documents/code/nas_media_manage/docs/ai-map.md)
- [`media_importer/scraper/llm_scraper.py`](file:///Users/wangwei/Documents/code/nas_media_manage/media_importer/scraper/llm_scraper.py)
