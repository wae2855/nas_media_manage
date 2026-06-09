"""
MCP tool factory for creating and registering tools.
"""
import logging
from typing import Dict, Any, Optional, Callable

from .config import MCPConfig
from .client import MCPClient
from .tools.base import BaseMCPTool, DummyTool
from .tools.web_search import WebSearchTool, WebSearchPrimeTool
from .tools.browser import BrowserTool, IntegratedBrowserTool


logger = logging.getLogger(__name__)


class MCPToolFactory:
    """Factory for creating MCP tools and clients."""
    
    # Tool type registry
    _TOOL_TYPES: Dict[str, type] = {
        "dummy": DummyTool,
        "web_search": WebSearchTool,
        "web_search_prime": WebSearchPrimeTool,
        "browser": BrowserTool,
        "integrated_browser": IntegratedBrowserTool,
    }
    
    @classmethod
    def create_client(cls, config: MCPConfig, mcp_runner: Optional[Callable] = None) -> MCPClient:
        """
        Create an MCP client from configuration.
        
        Args:
            config: MCP configuration
            mcp_runner: Optional MCP runner function for direct integration
            
        Returns:
            Configured MCPClient
        """
        client = MCPClient(config)
        
        if not config.enabled:
            logger.debug("MCP is disabled, returning empty client")
            return client
        
        # Register enabled tools
        for tool_config in config.get_enabled_tools():
            try:
                tool = cls.create_tool(tool_config.type, tool_config.config, mcp_runner)
                if tool:
                    info = tool.get_tool_info()
                    client.register_tool(
                        name=tool_config.name,
                        info=info,
                        handler=tool.execute
                    )
                    logger.debug(f"Registered MCP tool: {tool_config.name} ({tool_config.type})")
            except Exception as e:
                logger.warning(f"Failed to create MCP tool {tool_config.name}: {e}")
        
        return client
    
    @classmethod
    def create_tool(cls, tool_type: str, config: Dict[str, Any], mcp_runner: Optional[Callable] = None) -> Optional[BaseMCPTool]:
        """
        Create an MCP tool instance.
        
        Args:
            tool_type: Type of tool to create
            config: Tool configuration
            mcp_runner: Optional MCP runner
            
        Returns:
            Tool instance or None
        """
        tool_class = cls._TOOL_TYPES.get(tool_type)
        if not tool_class:
            logger.warning(f"Unknown MCP tool type: {tool_type}")
            return None
        
        try:
            # Check if tool accepts mcp_runner
            import inspect
            sig = inspect.signature(tool_class.__init__)
            if 'mcp_runner' in sig.parameters:
                return tool_class(config, mcp_runner=mcp_runner)
            else:
                return tool_class(config)
        except Exception as e:
            logger.warning(f"Failed to create tool {tool_type}: {e}")
            return None
    
    @classmethod
    def register_tool_type(cls, tool_type: str, tool_class: type):
        """
        Register a new tool type.
        
        Args:
            tool_type: Tool type identifier
            tool_class: Tool class
        """
        cls._TOOL_TYPES[tool_type] = tool_class
        logger.debug(f"Registered MCP tool type: {tool_type}")
