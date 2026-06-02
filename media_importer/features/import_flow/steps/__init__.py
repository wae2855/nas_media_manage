from .scrape import ScrapeStepsMixin
from .file import FileStepsMixin
from media_importer.features.import_flow.services.classification_rules import classify, render_template
from media_importer.features.import_flow.services.dedup_rules import check_duplicate
from media_importer.storage.file_mover import (
    apply_filename_template, move_to_import, delete_source_files, remove_empty_parent_dir,
)


class StepsMixin(ScrapeStepsMixin, FileStepsMixin):
    pass
