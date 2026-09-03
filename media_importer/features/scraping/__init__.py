from media_importer.features.providers.tmdb_client import TMDbClient, TMDbError

from .confidence_models import (
    DEFAULT_CONFIDENCE_CONFIG,
    CleanResult,
    MatchResult,
)
from .dimension_manager import (
    check_tier_access,
    get_dimensions_for_file,
    get_dimensions_for_provider,
    get_dimensions_for_tmdb,
    map_provider_to_dimension,
    map_tmdb_to_dimension,
)
from .dimensions_service import (
    DimensionActionResult,
    disable_dimension_detail,
    enable_dimension_detail,
    get_dimension_detail,
    get_dimension_mapping_detail,
    list_dimensions,
    list_enabled_dimensions,
    preview_dimension_mapping,
    reset_dimension_detail,
    update_dimension_detail,
    update_dimension_mapping_detail,
)
from .filename_cleaner import FilenameCleaner
from .metadata_scraper import MetadataScraper
from .nfo_identity import NfoIdentity, parse_nfo_identity, read_adjacent_nfo_identities
from .release_identity import ReleaseIdentity, parse_release_identity
from .title_matcher import TitleMatcher, _similarity
from .title_normalizer import TitleNormalizer

__all__ = [
    "CleanResult",
    "DEFAULT_CONFIDENCE_CONFIG",
    "DimensionActionResult",
    "FilenameCleaner",
    "MatchResult",
    "MetadataScraper",
    "NfoIdentity",
    "ReleaseIdentity",
    "parse_release_identity",
    "parse_nfo_identity",
    "read_adjacent_nfo_identities",
    "TMDbClient",
    "TMDbError",
    "TitleMatcher",
    "TitleNormalizer",
    "_similarity",
    "check_tier_access",
    "disable_dimension_detail",
    "enable_dimension_detail",
    "get_dimensions_for_file",
    "get_dimension_detail",
    "get_dimension_mapping_detail",
    "get_dimensions_for_provider",
    "get_dimensions_for_tmdb",
    "list_dimensions",
    "list_enabled_dimensions",
    "map_provider_to_dimension",
    "map_tmdb_to_dimension",
    "preview_dimension_mapping",
    "reset_dimension_detail",
    "update_dimension_detail",
    "update_dimension_mapping_detail",
]
