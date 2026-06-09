"""
MCP configuration models.
"""
from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional


@dataclass
class MCPToolConfig:
    """Configuration for a single MCP tool."""
    name: str = ""
    type: str = ""
    enabled: bool = True
    config: Dict[str, Any] = field(default_factory=dict)
    display_name: Optional[str] = None


@dataclass
class MCPScenarioConfig:
    """Configuration for MCP usage scenarios."""
    scrape: bool = True
    scrape_with_context: bool = False
    series_scrape: bool = True
    source_cleaner: bool = False


@dataclass
class MCPConfig:
    """Main MCP configuration."""
    enabled: bool = False
    tools: List[MCPToolConfig] = field(default_factory=list)
    scenarios: MCPScenarioConfig = field(default_factory=MCPScenarioConfig)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "MCPConfig":
        """Create MCPConfig from a dictionary."""
        data = data or {}
        
        # Parse tools
        tools = []
        for tool_data in data.get("tools", []):
            tools.append(MCPToolConfig(
                name=tool_data.get("name", ""),
                type=tool_data.get("type", ""),
                enabled=tool_data.get("enabled", True),
                config=tool_data.get("config", {}),
                display_name=tool_data.get("display_name"),
            ))
        
        # Parse scenarios
        scenario_data = data.get("scenarios", {})
        scenarios = MCPScenarioConfig(
            scrape=scenario_data.get("scrape", True),
            scrape_with_context=scenario_data.get("scrape_with_context", False),
            series_scrape=scenario_data.get("series_scrape", True),
            source_cleaner=scenario_data.get("source_cleaner", False),
        )
        
        return cls(
            enabled=data.get("enabled", False),
            tools=tools,
            scenarios=scenarios,
        )
    
    def get_tool(self, name: str) -> Optional[MCPToolConfig]:
        """Get a tool by name."""
        for tool in self.tools:
            if tool.name == name and tool.enabled:
                return tool
        return None
    
    def get_enabled_tools(self) -> List[MCPToolConfig]:
        """Get all enabled tools."""
        return [tool for tool in self.tools if tool.enabled]
    
    def is_scenario_enabled(self, scenario: str) -> bool:
        """Check if a scenario is enabled."""
        if not self.enabled:
            return False
        return getattr(self.scenarios, scenario, False)
