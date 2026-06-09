"""
Base class for MCP tools.
"""
import logging
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional

from ..client import ToolInfo


logger = logging.getLogger(__name__)


class BaseMCPTool(ABC):
    """Base class for MCP tools."""
    
    name: str = ""
    description: str = ""
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
    
    @abstractmethod
    def get_tool_info(self) -> ToolInfo:
        """Get tool information for LLM."""
        pass
    
    @abstractmethod
    async def execute(self, **kwargs) -> Any:
        """Execute the tool."""
        pass


class DummyTool(BaseMCPTool):
    """
    Dummy tool for testing/fallback.
    
    This tool doesn't require any external MCP server and always
    returns simulated results. It's useful for testing the MCP
    integration without needing actual MCP servers.
    """
    
    name = "dummy_search"
    description = "Dummy search tool for testing (returns simulated results)"
    
    def get_tool_info(self) -> ToolInfo:
        return ToolInfo(
            name=self.name,
            description=self.description,
            parameters={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Search query"
                    },
                    "num_results": {
                        "type": "number",
                        "description": "Number of results to return",
                        "default": 5
                    }
                },
                "required": ["query"]
            }
        )
    
    async def execute(self, query: str, num_results: int = 5) -> Dict[str, Any]:
        """Execute dummy search."""
        logger.debug(f"Dummy search called with query: {query}")
        
        # Return simulated results
        return {
            "results": [
                {
                    "title": f"Simulated result 1 for: {query}",
                    "content": "This is a simulated search result. "
                              "Configure real MCP tools to get actual results.",
                    "url": "https://example.com/result1"
                },
                {
                    "title": f"Simulated result 2 for: {query}",
                    "content": "Another simulated result.",
                    "url": "https://example.com/result2"
                }
            ][:num_results],
            "query": query,
            "total_results": num_results
        }
