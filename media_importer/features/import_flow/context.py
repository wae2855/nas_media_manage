class TaskContext:
    def __init__(self, task: dict):
        self.raw = task

    @property
    def task_id(self) -> str:
        return self.raw.get("task_id", "")

    @property
    def source_path(self) -> str:
        return self.raw.get("source_path", "")

    @property
    def source_filename(self) -> str:
        return self.raw.get("source_filename", "")

    @property
    def current_video_path(self) -> str:
        return self.raw.get("video_path") or self.raw.get("source_path", "")

    @property
    def subtitle_files(self) -> list:
        return self.raw.get("subtitle_files", [])

    @property
    def subtitle_source_files(self) -> list:
        return self.raw.get("subtitle_source_files", [])

    @property
    def scrape_result(self):
        return self.raw.get("scrape_result", {})

    @property
    def scrape_dimensions(self):
        return self.raw.get("scrape_dimensions", {})

    @property
    def file_location(self) -> str:
        return self.raw.get("file_location", "source")

    def mark_scraped(self, result: dict):
        self.raw["scrape_result"] = result
        self.raw["scrape_dimensions"] = result.get("dimensions", {})
        self.raw["scrape_title_cn"] = result.get("title_cn", "")
        self.raw["scrape_title_en"] = result.get("title_en", "")
        self.raw["scrape_year"] = result.get("year", "")
        self.raw["scrape_media_type"] = result.get("media_type", "")
        self.raw["scrape_season"] = result.get("season")
        self.raw["scrape_episode"] = result.get("episode")
        if result.get("scrape_trace"):
            self.raw["scrape_trace"] = result.get("scrape_trace")

    def to_update_fields(self, *field_names: str) -> dict:
        return {
            field: self.raw.get(field)
            for field in field_names
            if field in self.raw
        }
