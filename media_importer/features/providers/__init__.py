from typing import Dict, List, Type, Optional

from media_importer.features.configuration import ConfigView
from .base import (
    DimensionMapping,
    Genre,
    MediaDetails,
    MetadataProvider,
    SearchItem,
    SearchResult,
)

_PROVIDER_REGISTRY: Dict[str, Type['MetadataProvider']] = {}


def register_provider(cls: Type['MetadataProvider']) -> Type['MetadataProvider']:
    _PROVIDER_REGISTRY[cls.provider_type] = cls
    return cls


def get_provider_class(provider_type: str) -> Optional[Type['MetadataProvider']]:
    return _PROVIDER_REGISTRY.get(provider_type)


def get_all_provider_types() -> list:
    return list(_PROVIDER_REGISTRY.keys())


def get_all_registered_providers() -> Dict[str, Type['MetadataProvider']]:
    return dict(_PROVIDER_REGISTRY)


def create_providers(config: dict) -> list:
    providers_config = ConfigView.from_dict(config).metadata.providers
    providers = []
    for pconf in providers_config:
        if not pconf.get("enabled", False):
            continue
        cls = get_provider_class(pconf.get("type", ""))
        if cls:
            try:
                providers.append(cls(pconf))
            except Exception as e:
                import logging
                logging.getLogger(__name__).error(
                    f"Failed to create provider {pconf.get('type')}: {e}"
                )
    return providers


from .tmdb_provider import TMDbProvider  # noqa: E402, F401

__all__ = [
    "DimensionMapping",
    "Genre",
    "MediaDetails",
    "MetadataProvider",
    "SearchItem",
    "SearchResult",
    "TMDbProvider",
    "create_providers",
    "get_all_provider_types",
    "get_all_registered_providers",
    "get_provider_class",
    "register_provider",
]
