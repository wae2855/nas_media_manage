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
    confidence: dict = field(default_factory=dict)


@dataclass(frozen=True)
class LLMConfig:
    api_key: str = ""
    base_url: str = "https://api.openai.com/v1"
    model: str = "gpt-3.5-turbo"
    fast_model: str = ""
    fast_base_url: str = ""
    fast_api_key: str = ""
    source_cleaner_model: str = "gpt-4o-mini"
    timeout: int = 30
    max_retries: int = 2
    retry_delay: int = 3
    fallback_model: str = ""
    confidence_threshold: float = 0.8
    verify_ssl: bool = True
    system_prompt: str = ""

    @property
    def effective_fast_model(self) -> str:
        return self.fast_model or self.fallback_model or self.model

    @property
    def effective_fast_base_url(self) -> str:
        return self.fast_base_url or self.base_url

    @property
    def effective_fast_api_key(self) -> str:
        return self.fast_api_key or self.api_key


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
    ai_prompt: str = ""


@dataclass(frozen=True)
class ConfigView:
    raw: dict
    paths: PathConfig
    source_policy: SourcePolicyConfig
    dedup: DedupConfig
    filename_templates: FilenameTemplateConfig
    manual_review: ManualReviewConfig
    metadata: MetadataProviderConfig
    llm: LLMConfig
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
        llm = _dict(config.get("llm"))
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
                confidence=_dict(config.get("confidence")),
            ),
            llm=LLMConfig(
                api_key=llm.get("api_key", ""),
                base_url=llm.get("base_url") or llm.get("api_base", "https://api.openai.com/v1"),
                model=llm.get("model", "gpt-3.5-turbo"),
                fast_model=llm.get("fast_model", ""),
                fast_base_url=llm.get("fast_base_url", ""),
                fast_api_key=llm.get("fast_api_key", ""),
                source_cleaner_model=llm.get("fast_model", "") or llm.get("model", "gpt-4o-mini"),
                timeout=llm.get("timeout", 30),
                max_retries=llm.get("max_retries", 2),
                retry_delay=llm.get("retry_delay", 3),
                fallback_model=llm.get("fallback_model", ""),
                confidence_threshold=llm.get("confidence_threshold", 0.8),
                verify_ssl=llm.get("verify_ssl", True),
                system_prompt=llm.get("system_prompt", ""),
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
                ai_prompt=source_cleaner.get("ai_prompt", ""),
            ),
        )

    def filename_template_dict(self) -> dict:
        templates = dict(self.filename_templates.raw)
        templates.setdefault("movie", self.filename_templates.movie)
        templates.setdefault("tv", self.filename_templates.tv)
        templates.setdefault("subtitle", self.filename_templates.subtitle)
        return templates
