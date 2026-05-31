from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field


@dataclass
class Genre:
    id: str
    name: str


@dataclass
class SearchItem:
    provider_type: str
    item_id: str
    title: str
    original_title: str
    year: Optional[int]
    media_type: str
    poster_url: Optional[str]
    vote_average: Optional[float]
    raw_data: dict


@dataclass
class SearchResult:
    items: List[SearchItem]
    total_results: int


@dataclass
class MediaDetails:
    provider_type: str
    item_id: str
    media_type: str
    title: str
    original_title: str
    year: Optional[int]
    genres: List[Genre]
    overview: str
    vote_average: float
    origin_country: List[str]
    original_language: str
    adult: bool
    tagline: str
    poster_url: str
    raw_data: dict
    rating_info: Optional[dict] = None


@dataclass
class DimensionMapping:
    name: str
    value: Any
    confidence: float
    source: str


class MetadataProvider(ABC):

    @property
    @abstractmethod
    def provider_type(self) -> str:
        pass

    @property
    @abstractmethod
    def display_name(self) -> str:
        pass

    @abstractmethod
    def search(self, query: str, year: Optional[int] = None,
               media_type: Optional[str] = None) -> SearchResult:
        pass

    @abstractmethod
    def get_details(self, item_id: str, media_type: str) -> MediaDetails:
        pass

    @abstractmethod
    def get_genres(self, media_type: Optional[str] = None) -> list:
        pass

    @abstractmethod
    def test_connection(self) -> bool:
        pass

    @abstractmethod
    def map_dimensions(self, dim_configs: list, details: MediaDetails) -> List[DimensionMapping]:
        pass

    @classmethod
    def get_config_schema(cls) -> dict:
        return {"fields": []}

    @classmethod
    def get_context_template(cls) -> str:
        return (
            "系统已通过 {provider_name} API 获取到该影视作品的元数据，"
            "请基于这些数据整理为系统所需的格式化信息。\n\n"
            "重要原则：\n"
            "1. {provider_name} 数据是优先参考来源，标题、年份、类型等基础信息优先采用。\n"
            "2. 若 {provider_name} 数据不完整或存疑，请结合你的知识进行补充判断。\n"
            "3. 如果 {provider_name} 数据与文件名信息有冲突，以 {provider_name} 数据为准，但季/集编号以文件名为准。\n\n"
            "以下维度的映射数据已自动提取为参考（如为 null 表示未提供），请对每个维度给出判断：\n"
        )

    def get_prompt_file_name(self) -> str:
        return f"{self.provider_type}_prompts.md"
