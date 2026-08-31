import os
from dataclasses import dataclass, field


def _list(value, default=None) -> list:
    if isinstance(value, list):
        return value
    return list(default or [])


def _dict(value) -> dict:
    return value if isinstance(value, dict) else {}


def _extensions(values: list) -> tuple:
    return tuple(
        ext.lower() if str(ext).startswith(".") else f".{str(ext).lower()}"
        for ext in values
    )


DEFAULT_MOVIE_TEMPLATE = "{title_cn}.{title_en}.{year}.{resolution}.{quality}.{ext}"
DEFAULT_TV_TEMPLATE = "{title_cn}.{title_en}.{year}.S{season}E{episode}.{ext}"
DEFAULT_SUBTITLE_TEMPLATE = "{video_filename}.{lang}.{ext}"


@dataclass(frozen=True)
class PathConfig:
    source_dir: str = ""
    temp_dir: str = ""
    log_dir: str = "logs"
    library_root: str = ""
    library_roots: tuple = field(default_factory=tuple)
    default_library_root_id: str = ""
    fallback_library_root_id: str = ""
    fallback_dir: str = ""
    config_path: str = ""
    data_dir: str = ""
    path_rules: list = field(default_factory=list)
    video_extensions: tuple = field(default_factory=tuple)
    subtitle_extensions: tuple = field(default_factory=tuple)

    @property
    def project_root(self) -> str:
        if not self.config_path:
            return ""
        return os.path.dirname(os.path.dirname(os.path.abspath(self.config_path)))


@dataclass(frozen=True)
class SourcePolicyConfig:
    recycle_dir: str = ""
    cleanup_source_after_done: bool = False
    mode: str = "preserve_all"
    recycle_retention_days: int = 30
    scan_recursive: bool = True
    scan_max_depth: int = 5
    unit_settle_seconds: int = 120
    unit_incomplete_patterns: tuple = field(default_factory=tuple)


@dataclass(frozen=True)
class DedupConfig:
    enabled: bool = True
    strategy: str = "confirm"


@dataclass(frozen=True)
class FilenameTemplateConfig:
    movie: str = DEFAULT_MOVIE_TEMPLATE
    tv: str = DEFAULT_TV_TEMPLATE
    subtitle: str = DEFAULT_SUBTITLE_TEMPLATE
    raw: dict = field(default_factory=dict)


@dataclass(frozen=True)
class ManualReviewConfig:
    enabled: bool = False


@dataclass(frozen=True)
class MetadataProviderConfig:
    providers: list = field(default_factory=list)
    scrape_mode: str = "provider_first"  # 当前唯一模式：provider_first


@dataclass(frozen=True)
class ScannerConfig:
    scan_source: bool = True
    skip_existing: bool = True
    sort_by: str = "filename"
    sort_reverse: bool = False
    group_delay_sec: int = 0


@dataclass(frozen=True)
class SourceCleanerConfig:
    enabled: bool = False
    cleanup_mode: str = "media_only"
    ai_enabled: bool = False
    merge_strategy: str = "intersection"
    junk_video_max_size_mb: int = 50
    delete_extensions: tuple = field(default_factory=lambda: (".url", ".log", ".txt"))
    protect_extensions: tuple = field(default_factory=lambda: (".nfo", ".jpg", ".png"))
    blacklist_patterns: list = field(default_factory=lambda: ["RARBG*", "*/Sample/*", "*/sample/*"])
    cleanup_empty_dirs: bool = True


@dataclass(frozen=True)
class ConfigView:
    raw: dict
    paths: PathConfig
    source_policy: SourcePolicyConfig
    dedup: DedupConfig
    filename_templates: FilenameTemplateConfig
    manual_review: ManualReviewConfig
    metadata: MetadataProviderConfig
    scanner: ScannerConfig
    source_cleaner: SourceCleanerConfig

    @classmethod
    def from_dict(cls, config: dict):
        if isinstance(config, cls):
            return config
        config = config or {}
        source_policy = _dict(config.get("source_policy"))
        filename_templates = _dict(config.get("filename_templates"))
        metadata = _dict(config.get("metadata"))
        source_cleaner = _dict(config.get("source_cleaner"))
        source_mode = source_policy.get("mode")
        if source_mode not in {"preserve_all", "preserve_media", "recycle_source_unit"}:
            if source_policy.get("cleanup_source_after_done") is True:
                source_mode = "recycle_source_unit"
            elif source_cleaner.get("enabled") is True:
                source_mode = "preserve_media"
            else:
                source_mode = "preserve_all"

        paths = PathConfig(
            source_dir=config.get("source_dir", ""),
            temp_dir=config.get("temp_dir", ""),
            log_dir=config.get("log_dir", "logs"),
            library_root=config.get("library_root", ""),
            library_roots=tuple(_list(config.get("library_roots"))),
            default_library_root_id=config.get("default_library_root_id", ""),
            fallback_library_root_id=config.get("fallback_library_root_id", ""),
            fallback_dir=config.get("fallback_dir", ""),
            config_path=config.get("_config_path", ""),
            data_dir=config.get("_data_dir", ""),
            path_rules=_list(config.get("path_rules")),
            video_extensions=_extensions(_list(config.get("video_extensions"))),
            subtitle_extensions=_extensions(_list(config.get("subtitle_extensions"))),
        )
        return cls(
            raw=config,
            paths=paths,
            source_policy=SourcePolicyConfig(
                recycle_dir=source_policy.get("recycle_dir", ""),
                cleanup_source_after_done=(
                    source_mode == "recycle_source_unit"
                ),
                mode=source_mode,
                recycle_retention_days=source_policy.get("recycle_retention_days", 30),
                scan_recursive=source_policy.get("scan_recursive", True),
                scan_max_depth=source_policy.get("scan_max_depth", 5),
                unit_settle_seconds=max(0, int(source_policy.get("unit_settle_seconds", 120))),
                unit_incomplete_patterns=tuple(_list(
                    source_policy.get("unit_incomplete_patterns"),
                    ["*.part", "*.partial", "*.aria2", "*.!qB", "*.crdownload"],
                )),
            ),
            dedup=DedupConfig(
                enabled=True,
                strategy="confirm",
            ),
            filename_templates=FilenameTemplateConfig(
                movie=filename_templates.get("movie", DEFAULT_MOVIE_TEMPLATE),
                tv=filename_templates.get("tv", DEFAULT_TV_TEMPLATE),
                subtitle=filename_templates.get("subtitle", DEFAULT_SUBTITLE_TEMPLATE),
                raw=filename_templates,
            ),
            manual_review=ManualReviewConfig(
                enabled=_dict(config.get("manual_review")).get("enabled", False),
            ),
            metadata=MetadataProviderConfig(
                providers=_list(metadata.get("providers")),
                scrape_mode=metadata.get("scrape_mode", "provider_first"),
            ),
            scanner=ScannerConfig(
                scan_source=config.get("scan_source", True),
                skip_existing=config.get("skip_existing", True),
                sort_by=config.get("sort_by", "filename"),
                sort_reverse=config.get("sort_reverse", False),
                group_delay_sec=config.get("group_delay_sec", 0),
            ),
            source_cleaner=SourceCleanerConfig(
                enabled=(source_mode == "preserve_media" and source_cleaner.get("enabled", False)),
                cleanup_mode=source_cleaner.get("cleanup_mode", "media_only"),
                ai_enabled=(source_mode == "preserve_media" and source_cleaner.get("enabled", False)
                            and source_cleaner.get("ai_enabled", False)),
                merge_strategy=source_cleaner.get("merge_strategy", "intersection"),
                junk_video_max_size_mb=source_cleaner.get("junk_video_max_size_mb", 50),
                delete_extensions=_extensions(_list(source_cleaner.get("delete_extensions"), [".url", ".log", ".txt"])),
                protect_extensions=_extensions(_list(source_cleaner.get("protect_extensions"), [".nfo", ".jpg", ".png"])),
                blacklist_patterns=_list(source_cleaner.get("blacklist_patterns"), ["RARBG*", "*/Sample/*", "*/sample/*"]),
                cleanup_empty_dirs=source_cleaner.get("cleanup_empty_dirs", True),
            ),
        )

    def filename_template_dict(self) -> dict:
        templates = dict(self.filename_templates.raw)
        templates.setdefault("movie", self.filename_templates.movie)
        templates.setdefault("tv", self.filename_templates.tv)
        templates.setdefault("subtitle", self.filename_templates.subtitle)
        return templates
