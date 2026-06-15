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
    cleanup_source_after_done: bool = True
    recycle_retention_days: int = 30
    scan_recursive: bool = True
    scan_max_depth: int = 5


@dataclass(frozen=True)
class DedupConfig:
    enabled: bool = True
    strategy: str = "skip"


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
class AiAssistConfig:
    base_url: str = ""
    model: str = ""
    api_key: str = ""
    timeout: int = 30
    max_retries: int = 2
    retry_delay: int = 3
    verify_ssl: bool = True
    prompt_title_clean: str = ""
    prompt_match_assist: str = ""
    prompt_dimension_mapping: str = ""
    prompt_source_clean: str = ""
    log_prompt: bool = True

    @property
    def is_configured(self) -> bool:
        return bool(self.api_key and self.base_url and self.model)


@dataclass
class SceneModelConfig:
    primary: str = ""
    fallback: str = ""


@dataclass
class AiSceneStrategyConfig:
    dimension_supplement: SceneModelConfig = field(default_factory=SceneModelConfig)
    dimension_mapping: SceneModelConfig = field(default_factory=SceneModelConfig)
    title_clean: SceneModelConfig = field(default_factory=SceneModelConfig)
    match_assist: SceneModelConfig = field(default_factory=SceneModelConfig)
    source_clean: SceneModelConfig = field(default_factory=SceneModelConfig)

    @classmethod
    def from_dict(cls, data: dict) -> "AiSceneStrategyConfig":
        result = cls()
        for key in (
            "dimension_supplement", "dimension_mapping",
            "title_clean", "match_assist", "source_clean",
        ):
            section = data.get(key, {}) or {}
            if not isinstance(section, dict):
                section = {}
            setattr(result, key, SceneModelConfig(
                primary=str(section.get("primary", "")),
                fallback=str(section.get("fallback", "")),
            ))
        return result


@dataclass(frozen=True)
class AiSearchConfig:
    enabled: bool = True
    provider: str = ""
    model: str = ""
    search_type: str = ""
    api_key: str = ""
    base_url: str = ""
    timeout: int = 30
    max_retries: int = 2
    retry_delay: int = 3
    verify_ssl: bool = True
    prompt_dimension_supplement: str = ""

    @property
    def is_configured(self) -> bool:
        return bool(self.api_key and self.model)

    @property
    def is_effective(self) -> bool:
        return self.enabled and self.is_configured


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
    ai_assist: AiAssistConfig
    ai_search: AiSearchConfig
    ai_scene_strategy: AiSceneStrategyConfig
    scanner: ScannerConfig
    source_cleaner: SourceCleanerConfig

    @classmethod
    def from_dict(cls, config: dict):
        if isinstance(config, cls):
            return config
        config = config or {}
        source_policy = _dict(config.get("source_policy"))
        duplicate_handling = _dict(config.get("duplicate_handling"))
        filename_templates = _dict(config.get("filename_templates"))
        metadata = _dict(config.get("metadata"))
        ai_assist = _dict(config.get("ai_assist"))
        ai_search = _dict(config.get("ai_search"))
        source_cleaner = _dict(config.get("source_cleaner"))

        paths = PathConfig(
            source_dir=config.get("source_dir", ""),
            temp_dir=config.get("temp_dir", ""),
            log_dir=config.get("log_dir", "logs"),
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
                cleanup_source_after_done=source_policy.get("cleanup_source_after_done", True),
                recycle_retention_days=source_policy.get("recycle_retention_days", 30),
                scan_recursive=source_policy.get("scan_recursive", True),
                scan_max_depth=source_policy.get("scan_max_depth", 5),
            ),
            dedup=DedupConfig(
                enabled=duplicate_handling.get("enabled", True),
                strategy=duplicate_handling.get("strategy", "skip"),
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
            ai_assist=AiAssistConfig(
                base_url=ai_assist.get("base_url", ""),
                model=ai_assist.get("model", ""),
                api_key=ai_assist.get("api_key", ""),
                timeout=ai_assist.get("timeout", 30),
                max_retries=ai_assist.get("max_retries", 2),
                retry_delay=ai_assist.get("retry_delay", 3),
                verify_ssl=ai_assist.get("verify_ssl", True),
                prompt_title_clean=ai_assist.get("prompt_title_clean", ""),
                prompt_match_assist=ai_assist.get("prompt_match_assist", ""),
                prompt_dimension_mapping=ai_assist.get("prompt_dimension_mapping", ""),
                prompt_source_clean=ai_assist.get("prompt_source_clean", ""),
                log_prompt=ai_assist.get("log_prompt", True),
            ),
            ai_scene_strategy=AiSceneStrategyConfig.from_dict(
                config.get("ai_scene_strategy", {}) or {}
            ),
            ai_search=AiSearchConfig(
                enabled=ai_search.get("enabled", True),
                provider=ai_search.get("provider", ""),
                model=ai_search.get("model", ""),
                search_type=ai_search.get("search_type", ""),
                api_key=ai_search.get("api_key", ""),
                base_url=ai_search.get("base_url", ""),
                timeout=ai_search.get("timeout", 30),
                max_retries=ai_search.get("max_retries", 2),
                retry_delay=ai_search.get("retry_delay", 3),
                verify_ssl=ai_search.get("verify_ssl", True),
                prompt_dimension_supplement=ai_search.get("prompt_dimension_supplement", ""),
            ),
            scanner=ScannerConfig(
                scan_source=config.get("scan_source", True),
                skip_existing=config.get("skip_existing", True),
                sort_by=config.get("sort_by", "filename"),
                sort_reverse=config.get("sort_reverse", False),
                group_delay_sec=config.get("group_delay_sec", 0),
            ),
            source_cleaner=SourceCleanerConfig(
                enabled=source_cleaner.get("enabled", False),
                cleanup_mode=source_cleaner.get("cleanup_mode", "media_only"),
                ai_enabled=source_cleaner.get("ai_enabled", False),
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
