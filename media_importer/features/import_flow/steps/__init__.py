from media_importer.features.import_flow.services.classification_rules import (
    classify as classify,
)
from media_importer.features.import_flow.services.classification_rules import (
    render_template as render_template,
)
from media_importer.features.import_flow.services.dedup_rules import (
    check_duplicate as check_duplicate,
)
from media_importer.features.import_flow.services.file_operations import (
    move_to_import as move_to_import,
)
from media_importer.features.import_flow.services.naming import (
    apply_filename_template as apply_filename_template,
)
from media_importer.features.source_files import (
    delete_source_files as delete_source_files,
)
from media_importer.features.source_files import (
    remove_empty_parent_dir as remove_empty_parent_dir,
)

from .file import FileStepsMixin
from .scrape import ScrapeStepsMixin


class StepsMixin(FileStepsMixin, ScrapeStepsMixin):
    """流水线步骤组合（file + scrape）。"""


__all__ = [
    "FileStepsMixin",
    "ScrapeStepsMixin",
    "StepsMixin",
    "classify",
    "render_template",
    "check_duplicate",
    "move_to_import",
    "apply_filename_template",
    "delete_source_files",
    "remove_empty_parent_dir",
]
