"""
Example: How to use MCP integration in the media importer.

This file demonstrates how to set up and use MCP tools
for enhanced LLM scraping capabilities.
"""
import os
import sys
import logging

# Add the project root to Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../..'))

from media_importer.features.mcp import MCPConfig, MCPToolConfig, MCPScenarioConfig
from media_importer.features.mcp import MCPToolFactory
from media_importer.scraper.llm_scraper import LLMScraper

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def example_basic_setup():
    """Example 1: Basic MCP setup with dummy tools."""
    print("=" * 60)
    print("Example 1: Basic MCP Setup")
    print("=" * 60)
    
    # Create MCP configuration
    config = MCPConfig(
        enabled=True,
        tools=[
            MCPToolConfig(
                name="dummy_search",
                type="dummy",
                enabled=True,
                config={}
            )
        ],
        scenarios=MCPScenarioConfig(
            scrape=True,
            scrape_with_context=False,
            series_scrape=True,
            source_cleaner=False
        )
    )
    
    # Create MCP client
    client = MCPToolFactory.create_client(config)
    
    print(f"MCP client available: {client.is_available()}")
    print(f"Available tools: {[t.name for t in client.list_tools()]}")
    print()


def example_with_llm_scraper():
    """Example 2: Using MCP with LLMScraper."""
    print("=" * 60)
    print("Example 2: MCP + LLMScraper Integration")
    print("=" * 60)
    
    # Create configuration dict (like from config.yaml)
    config_dict = {
        "llm": {
            "api_key": "test-key",
            "base_url": "https://api.openai.com/v1",
            "model": "gpt-3.5-turbo",
            "mcp": {
                "enabled": True,
                "tools": [
                    {
                        "name": "dummy_search",
                        "type": "dummy",
                        "enabled": True
                    }
                ],
                "scenarios": {
                    "scrape": True,
                    "series_scrape": True
                }
            }
        }
    }
    
    # Create MCP client
    from media_importer.features.mcp import MCPConfig
    mcp_config = MCPConfig.from_dict(config_dict["llm"]["mcp"])
    mcp_client = MCPToolFactory.create_client(mcp_config)
    
    # Initialize LLMScraper with MCP client
    scraper = LLMScraper(config_dict, mcp_client=mcp_client)
    
    print(f"LLMScraper initialized with MCP: {scraper._use_mcp}")
    print()
    
    # Note: In real usage, you would use scraper.scrape_with_mcp()
    # instead of scraper.scrape() to enable tool use


def example_config_from_file():
    """Example 3: Loading MCP config from config.yaml."""
    print("=" * 60)
    print("Example 3: Loading MCP Config from File")
    print("=" * 60)
    
    # In real usage, you would load config from your config file
    # For this example, we'll simulate it
    print("To use MCP in your project:")
    print()
    print("1. Update your config.yaml with MCP settings (see config.yaml.example)")
    print("2. Initialize MCP client and pass it to LLMScraper")
    print()
    print("Example code snippet:")
    print("""
    from media_importer.features.mcp import MCPToolFactory
    from media_importer.core.config_view import ConfigView
    
    # Load config
    config = load_your_config()
    config_view = ConfigView.from_dict(config)
    
    # Create MCP client
    mcp_config = MCPConfig.from_dict(config_view.llm.mcp)
    mcp_client = MCPToolFactory.create_client(mcp_config)
    
    # Create scraper with MCP
    scraper = LLMScraper(config, mcp_client=mcp_client)
    
    # Use enhanced scraping methods
    result = scraper.scrape_with_mcp(video_filename)
    """)
    print()


def example_scenarios():
    """Example 4: Different MCP usage scenarios."""
    print("=" * 60)
    print("Example 4: MCP Usage Scenarios")
    print("=" * 60)
    
    scenarios = [
        ("scrape", "Pure LLM scraping without Provider data"),
        ("scrape_with_context", "Scraping with TMDB/Provider context"),
        ("series_scrape", "TV show series-level scraping"),
        ("source_cleaner", "Source directory cleanup analysis")
    ]
    
    print("You can configure which scenarios use MCP:")
    for scenario, desc in scenarios:
        print(f"  - {scenario:<20} {desc}")
    print()
    print("This is done via the 'scenarios' section in mcp config.")
    print()


if __name__ == "__main__":
    print()
    print("📺 Media Importer MCP Integration Examples")
    print()
    
    example_basic_setup()
    example_with_llm_scraper()
    example_config_from_file()
    example_scenarios()
    
    print("=" * 60)
    print("Done!")
    print("=" * 60)
