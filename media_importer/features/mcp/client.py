"""
MCP client for tool integration.
"""
import logging
from typing import Dict, Any, List, Optional, Callable
from dataclasses import dataclass

from .config import MCPConfig


logger = logging.getLogger(__name__)


@dataclass
class ToolInfo:
    """Information about an available MCP tool."""
    name: str
    description: str
    parameters: Dict[str, Any]


@dataclass
class ToolResult:
    """Result of a tool call."""
    tool_name: str
    success: bool
    content: Any
    error: Optional[str] = None


class MCPClient:
    """
    MCP client for interacting with MCP tools.
    
    This is a wrapper that integrates with the available MCP servers.
    """
    
    def __init__(self, config: MCPConfig, tools: Optional[Dict[str, Callable]] = None):
        self.config = config
        self._tools = tools or {}
        self._available = False
        self._tool_registry: Dict[str, ToolInfo] = {}
    
    def register_tool(self, name: str, info: ToolInfo, handler: Callable):
        """Register a tool with the client."""
        self._tool_registry[name] = info
        self._tools[name] = handler
        self._available = True
    
    def is_available(self) -> bool:
        """Check if MCP is available."""
        return self._available and self.config.enabled
    
    async def list_tools(self) -> List[ToolInfo]:
        """List available tools."""
        if not self.is_available():
            return []
        return list(self._tool_registry.values())
    
    async def call_tool(self, name: str, args: Dict[str, Any]) -> ToolResult:
        """
        Call an MCP tool.
        
        Args:
            name: Tool name
            args: Tool arguments
            
        Returns:
            Tool result
        """
        if not self.is_available():
            return ToolResult(
                tool_name=name,
                success=False,
                content=None,
                error="MCP not available"
            )
        
        tool = self.config.get_tool(name)
        if not tool:
            return ToolResult(
                tool_name=name,
                success=False,
                content=None,
                error=f"Tool '{name}' not found or disabled"
            )
        
        if name not in self._tools:
            return ToolResult(
                tool_name=name,
                success=False,
                content=None,
                error=f"Tool handler for '{name}' not registered"
            )
        
        try:
            logger.debug(f"Calling MCP tool: {name} with args: {args}")
            handler = self._tools[name]
            result = await handler(**args)
            return ToolResult(
                tool_name=name,
                success=True,
                content=result
            )
        except Exception as e:
            logger.exception(f"Error calling MCP tool: {name}")
            return ToolResult(
                tool_name=name,
                success=False,
                content=None,
                error=str(e)
            )
    
    def get_tool_definitions(self) -> List[Dict[str, Any]]:
        """
        Get tool definitions for LLM function calling.
        
        Returns:
            List of tool definitions in OpenAI function calling format
        """
        if not self.is_available():
            return []
        
        tools = []
        for tool_name, info in self._tool_registry.items():
            tools.append({
                "type": "function",
                "function": {
                    "name": tool_name,
                    "description": info.description,
                    "parameters": info.parameters
                }
            })
        return tools
    
    def should_use_mcp_for(self, scenario: str) -> bool:
        """Check if MCP should be used for a specific scenario."""
        return self.config.is_scenario_enabled(scenario)
