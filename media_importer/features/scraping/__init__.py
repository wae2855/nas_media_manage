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
    list_dimensions,
    list_enabled_dimensions,
    reset_dimension_detail,
    update_dimension_detail,
)
from .filename_cleaner import FilenameCleaner
from .metadata_scraper import MetadataScraper
from .title_matcher import TitleMatcher, _similarity

__all__ = [
    "CleanResult",
    "DEFAULT_CONFIDENCE_CONFIG",
    "DimensionActionResult",
    "FilenameCleaner",
    "MatchResult",
    "MetadataScraper",
    "TMDbClient",
    "TMDbError",
    "TitleMatcher",
    "_similarity",
    "check_tier_access",
    "disable_dimension_detail",
    "enable_dimension_detail",
    "get_dimensions_for_file",
    "get_dimension_detail",
    "get_dimensions_for_provider",
    "get_dimensions_for_tmdb",
    "list_dimensions",
    "list_enabled_dimensions",
    "map_provider_to_dimension",
    "map_tmdb_to_dimension",
    "reset_dimension_detail",
    "update_dimension_detail",
]
