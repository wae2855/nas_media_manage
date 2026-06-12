from dataclasses import dataclass
from typing import Dict, Optional


SUPPORTED_PROVIDERS: Dict[str, str] = {
    "zhipu": "智谱 GLM（tools.web_search）",
    "qwen": "通义千问（enable_search）",
    "moonshot": "Kimi/Moonshot（builtin_function.$web_search）",
}

PROVIDER_DETECTION_MAP = {
    "bigmodel.cn": "zhipu",
    "zhipu": "zhipu",
    "dashscope": "qwen",
    "aliyun": "qwen",
    "moonshot": "moonshot",
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

    def should_search(self, scenario: str) -> bool:
        if self.detected_provider is None:
            return False
        return scenario in ("scrape", "series_scrape")

    def effective_provider(self) -> Optional[str]:
        return self.detected_provider

    def supports_web_search(self) -> bool:
        return self.detected_provider is not None
