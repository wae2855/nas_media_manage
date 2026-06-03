from .application_service import (
    load_global_prompt_for_ui,
    load_provider_prompt_for_ui,
    reset_global_prompt,
    reset_provider_prompt,
    save_global_prompt,
    save_provider_prompt,
)
from .prompt_builder import LLMPromptBuilder

__all__ = [
    "LLMPromptBuilder",
    "LLMScraper",
    "load_global_prompt_for_ui",
    "load_provider_prompt_for_ui",
    "reset_global_prompt",
    "reset_provider_prompt",
    "save_global_prompt",
    "save_provider_prompt",
]


def __getattr__(name):
    if name == "LLMScraper":
        from media_importer.scraper.llm_scraper import LLMScraper
        return LLMScraper
    raise AttributeError(name)
