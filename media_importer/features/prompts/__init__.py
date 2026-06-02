from .prompt_builder import LLMPromptBuilder

__all__ = [
    "LLMPromptBuilder",
    "LLMScraper",
]


def __getattr__(name):
    if name == "LLMScraper":
        from media_importer.scraper.llm_scraper import LLMScraper
        return LLMScraper
    raise AttributeError(name)
