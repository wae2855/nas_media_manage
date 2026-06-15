from .scrape import ScrapeStepsMixin
from .file import FileStepsMixin
from media_importer.features.import_flow.services.classification_rules import classify, render_template
from media_importer.features.import_flow.services.dedup_rules import check_duplicate
from media_importer.features.import_flow.services.file_operations import (
    delete_source_files,
    move_to_import,
    remove_empty_parent_dir,
)
from media_importer.features.import_flow.services.naming import apply_filename_template


class StepsMixin(ScrapeStepsMixin, FileStepsMixin):
    pass
