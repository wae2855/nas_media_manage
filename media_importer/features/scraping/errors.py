"""LLM scraper exception classes — extracted to avoid circular imports."""


class LLMApiError(Exception):
    pass


class LLMWebSearchError(Exception):
    pass


class LLMScrapeError(LLMApiError):
    pass
