from .defaults import PromptDefaults
from .prompt_builder import LLMPromptBuilder

__all__ = [
    "LLMPromptBuilder",
    "PromptDefaults",
]


def __getattr__(name):
    if name == "LLMScraper":
        from media_importer.features.scraping.llm_scraper import LLMScraper
        return LLMScraper
    raise AttributeError(name)
