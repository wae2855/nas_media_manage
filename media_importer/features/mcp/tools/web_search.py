"""
Web search tool integration using web_search_prime MCP.
"""
import logging
from typing import Dict, Any

from .base import BaseMCPTool
from ..client import ToolInfo


logger = logging.getLogger(__name__)


class WebSearchTool(BaseMCPTool):
    """
    Web search tool wrapper for web_search_prime MCP.
    
    This tool integrates with the web_search_prime MCP server
    to provide internet search capabilities.
    """
    
    name = "web_search"
    description = "Search the internet for up-to-date information about movies, TV shows, and other media"
    
    def get_tool_info(self) -> ToolInfo:
        return ToolInfo(
            name=self.name,
            description=self.description,
            parameters={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Search query (e.g., 'Breaking Bad TV show rating', 'Inception movie 2010')"
                    },
                    "num_results": {
                        "type": "number",
                        "description": "Number of search results to return",
                        "default": 5
                    }
                },
                "required": ["query"]
            }
        )
    
    async def execute(self, query: str, num_results: int = 5) -> Dict[str, Any]:
        """
        Execute web search.
        
        Note: This is a placeholder. To use the real web_search_prime MCP,
        you need to integrate with the MCP server via the run_mcp tool.
        
        Args:
            query: Search query
            num_results: Number of results
            
        Returns:
            Search results
        """
        logger.info(f"Web search called (placeholder) with query: {query}")
        
        # This is a placeholder. The actual integration would use:
        # from the assistant's run_mcp tool to call the web_search_prime MCP.
        # For now, we return a message indicating that this is a placeholder.
        
        return {
            "results": [
                {
                    "title": "Web Search Placeholder",
                    "content": "Web search integration requires MCP setup. "
                              "This is a simulated result. To enable real search, "
                              "configure the web_search_prime MCP server.",
                    "url": "https://example.com/placeholder"
                }
            ],
            "query": query,
            "total_results": 1,
            "note": "This is a placeholder. Real MCP integration not implemented yet."
        }


class WebSearchPrimeTool(BaseMCPTool):
    """
    Web search tool for web_search_prime MCP (direct integration).
    
    This tool is designed to work with the run_mcp function to call
    the actual web_search_prime MCP server.
    """
    
    name = "web_search_prime"
    description = "Search the internet using the web_search_prime MCP server"
    
    def __init__(self, config: Dict[str, Any], mcp_runner=None):
        super().__init__(config)
        self._mcp_runner = mcp_runner
    
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
                        "description": "Number of results",
                        "default": 5
                    }
                },
                "required": ["query"]
            }
        )
    
    async def execute(self, query: str, num_results: int = 5) -> Dict[str, Any]:
        """
        Execute search using web_search_prime MCP.
        
        Args:
            query: Search query
            num_results: Number of results
            
        Returns:
            Search results
        """
        logger.debug(f"web_search_prime called with query: {query}")
        
        if self._mcp_runner:
            # Use the provided MCP runner
            try:
                result = await self._mcp_runner(
                    server_name="mcp_web_search_prime",
                    tool_name="web_search_prime",
                    args={"query": query, "num": num_results}
                )
                return result
            except Exception as e:
                logger.error(f"Error calling web_search_prime MCP: {e}")
                return {
                    "error": str(e),
                    "query": query,
                    "results": []
                }
        
        # Fallback to placeholder
        return {
            "results": [],
            "query": query,
            "error": "No MCP runner configured",
            "note": "Configure an MCP runner to use real web search"
        }
