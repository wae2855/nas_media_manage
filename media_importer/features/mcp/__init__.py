"""
MCP (Model Context Protocol) integration feature.

This module provides MCP tool integration for LLM scraping and analysis.
"""
from .client import MCPClient, ToolInfo, ToolResult
from .config import MCPConfig, MCPToolConfig, MCPScenarioConfig
from .factory import MCPToolFactory

__all__ = [
    "MCPClient",
    "ToolInfo",
    "ToolResult",
    "MCPConfig",
    "MCPToolConfig",
    "MCPScenarioConfig",
    "MCPToolFactory",
]
