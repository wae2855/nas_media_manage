from dataclasses import dataclass
from typing import Dict, Optional


SUPPORTED_PROVIDERS: Dict[str, str] = {
    "zhipu": "智谱 GLM",
    "qwen": "通义千问",
    "moonshot": "Kimi/Moonshot",
}

PROVIDER_DETECTION_MAP = {
    "bigmodel.cn": "zhipu",
    "zhipu": "zhipu",
    "dashscope": "qwen",
    "aliyun": "qwen",
    "moonshot": "moonshot",
}

SEARCH_TYPE_MAP = {
    "zhipu": [
        {"value": "search_std", "label": "标准搜索"},
        {"value": "search_pro", "label": "增强搜索"},
    ],
    "qwen": [
        {"value": "enable_search", "label": "标准搜索"},
        {"value": "forced_search", "label": "强制搜索"},
    ],
    "moonshot": [
        {"value": "web_search", "label": "联网搜索"},
    ],
}

DEFAULT_SEARCH_TYPE = {
    "zhipu": "search_std",
    "qwen": "enable_search",
    "moonshot": "web_search",
}


def detect_provider(base_url: str) -> Optional[str]:
    if not base_url:
        return None
    url_lower = base_url.lower()
    for keyword, provider in PROVIDER_DETECTION_MAP.items():
        if keyword in url_lower:
            return provider
    return None


@dataclass(frozen=True)
class WebSearchConfig:
    detected_provider: Optional[str] = None
    search_type: str = ""
    enabled: bool = False
    enabled_for_scrape: bool = True
    enabled_for_series_scrape: bool = True

    def should_search(self, scenario: str) -> bool:
        if not self.enabled:
            return False
        if self.detected_provider is None:
            return False
        if scenario == "scrape":
            return self.enabled_for_scrape
        if scenario == "series_scrape":
            return self.enabled_for_series_scrape
        return False

    def effective_provider(self) -> Optional[str]:
        return self.detected_provider

    def supports_web_search(self) -> bool:
        return self.enabled and self.detected_provider is not None

    def effective_search_type(self) -> str:
        if self.search_type:
            return self.search_type
        return DEFAULT_SEARCH_TYPE.get(self.detected_provider or "", "")


def build_web_search_config(ai_search_config: dict) -> WebSearchConfig:
    ai_search_config = ai_search_config or {}
    provider = ai_search_config.get("provider", "")
    if not provider and ai_search_config.get("base_url"):
        provider = detect_provider(ai_search_config.get("base_url", "")) or ""
    detected = provider if provider in SUPPORTED_PROVIDERS else None
    return WebSearchConfig(
        detected_provider=detected,
        search_type=ai_search_config.get("search_type", ""),
        enabled=ai_search_config.get("enabled", False),
        enabled_for_scrape=ai_search_config.get("enabled_for_scrape", True),
        enabled_for_series_scrape=ai_search_config.get("enabled_for_series_scrape", True),
    )
