from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, List, Optional


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
    total_results: int = 0


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
    source_reliability: float
    source: str
    evidence: dict | None = None


class MetadataProvider(ABC):

    # 子类通过类变量设置，注册器在类级别访问
    provider_type: str = ""
    display_name: str = ""

    @abstractmethod
    def search(self, query: str, year: Optional[int] = None,
               media_type: Optional[str] = None) -> SearchResult:
        pass

    @abstractmethod
    def get_details(self, item_id: str, media_type: str) -> MediaDetails:
        pass

    @abstractmethod
    def get_genres(self, media_type: Optional[str] = None) -> Any:
        pass

    @abstractmethod
    def test_connection(self) -> bool:
        pass

    @abstractmethod
    def map_dimensions(self, dim_configs: list, details: MediaDetails) -> List[DimensionMapping]:
        pass

    def get_alternative_titles(self, item_id: str, media_type: str) -> List[str]:
        """Return Provider-authoritative aliases when supported.

        Matching treats an empty result or adapter failure as no evidence.  The
        default keeps third-party Providers source-compatible.
        """
        return []

    def get_by_provider_id(
        self,
        item_id: str,
        media_type: Optional[str] = None,
    ) -> SearchResult:
        """Resolve this Provider's native ID into standard candidates.

        Providers that do not support deterministic ID lookup remain source
        compatible and simply return no candidates.
        """
        return SearchResult(items=[])

    def lookup_external_id(
        self,
        external_id: str,
        external_source: str,
        media_type: Optional[str] = None,
    ) -> SearchResult:
        """Resolve a foreign Provider ID into standard candidates when supported."""
        return SearchResult(items=[])

    @classmethod
    def get_config_schema(cls) -> dict:
        return {"fields": []}

    @classmethod
    def get_dimension_capabilities(cls) -> dict:
        return {"display_name": cls.display_name or cls.provider_type, "fields": []}

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
