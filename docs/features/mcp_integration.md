# MCP (Model Context Protocol) 集成

## 概述

本项目已集成 MCP (Model Context Protocol)，支持通过 MCP 工具增强 LLM 刮削能力，例如网络搜索、浏览器自动化等功能。

## 架构

```
media_importer/features/mcp/
├── __init__.py          # 模块入口
├── config.py             # 配置模型
├── client.py            # MCP 客户端
├── factory.py           # 工具工厂
├── example.py          # 使用示例
└── tools/
    ├── __init__.py
    ├── base.py          # 工具基类
    ├── web_search.py     # 网络搜索工具
    └── browser.py         # 浏览器工具
```

## 快速开始

### 1. 配置

在 `config.yaml` 中启用 MCP：

```yaml
llm:
  # ... 其他 LLM 配置 ...
  
  mcp:
    enabled: true
    
    tools:
      - name: web_search
        type: web_search
        enabled: true
        config: {}
    
    scenarios:
      scrape: true
      series_scrape: true
```

### 2. 使用

```python
from media_importer.features.mcp import MCPConfig, MCPToolFactory
from media_importer.scraper.llm_scraper import LLMScraper

# 从配置创建 MCP 客户端
mcp_config = MCPConfig.from_dict(config_dict["llm"]["mcp"])
mcp_client = MCPToolFactory.create_client(mcp_config)

# 创建带有 MCP 的刮削器
scraper = LLMScraper(config_dict, mcp_client=mcp_client)

# 使用 MCP 增强的刮削
result = scraper.scrape_with_mcp(video_filename)
```

## 工具类型

### Dummy 工具（内置测试用）

用于测试和演示，不依赖外部 MCP 服务器。

### Web Search 工具

通过 MCP 搜索网络搜索（需要 MCP 服务器支持）。

### Browser 工具

浏览器自动化（需要 MCP 服务器支持）。

## 使用场景

可配置哪些刮削场景使用 MCP：

- `scrape`: 纯 LLM 刮削（无 Provider 数据）
- `scrape_with_context`: 带 Provider 上下文刮削
- `series_scrape`: 整剧刮削
- `source_cleaner`: 源目录清理

## 向后兼容

默认情况下，MCP 是禁用的。不配置 MCP 时，系统完全按原方式工作，不会影响现有功能。

## 进一步信息

- 配置示例：见 `config.yaml.example`
- 代码示例：见 `media_importer/features/mcp/example.py`
- 架构设计：见 `docs/plans/2026-06-08-mcp-search-integration.md`
