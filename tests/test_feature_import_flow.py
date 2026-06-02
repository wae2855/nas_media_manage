#!/usr/bin/env python3
import os
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from media_importer.core import task_lifecycle as core_lifecycle
from media_importer.core.task_lifecycle import mark_imported as core_mark_imported
from media_importer.features import import_flow
from media_importer.features.import_flow import (
    ClassificationService,
    ConfirmMixin,
    DedupService,
    ImportService,
    PipelineRunner,
    ReviewDecision,
    ReviewDecisionService,
    FileStepsMixin,
    ScrapeStepsMixin,
    SourceCleanupService,
    StepsMixin,
    TaskContext,
    mark_imported,
)
from media_importer.features.import_flow import lifecycle as feature_lifecycle
from media_importer.features.import_flow import context as feature_context
from media_importer.features.import_flow import confirm as feature_confirm
from media_importer.features.import_flow import runner as feature_runner
from media_importer.features.import_flow import steps as feature_steps
from media_importer.features.import_flow.steps import file as feature_steps_file
from media_importer.features.import_flow.steps import scrape as feature_steps_scrape
from media_importer.features.import_flow import utils as feature_utils
from media_importer.pipeline.confirm import ConfirmMixin as PipelineConfirmMixin
from media_importer.pipeline.context import TaskContext as PipelineTaskContext
from media_importer.pipeline.runner import PipelineRunner as PipelinePackageRunner
from media_importer.pipeline.steps import StepsMixin as PipelineStepsMixin
from media_importer.pipeline.steps_file import FileStepsMixin as PipelineFileStepsMixin
from media_importer.pipeline.steps_scrape import (
    ScrapeStepsMixin as PipelineScrapeStepsMixin,
)
import media_importer.pipeline.confirm as legacy_confirm
import media_importer.pipeline.context as legacy_context
import media_importer.pipeline.runner as legacy_runner
import media_importer.pipeline.steps as legacy_steps
import media_importer.pipeline.steps_file as legacy_steps_file
import media_importer.pipeline.steps_scrape as legacy_steps_scrape
import media_importer.pipeline.utils as legacy_utils
from media_importer.pipeline.services import (
    ClassificationService as PipelineClassificationService,
)
from media_importer.pipeline.services import DedupService as PipelineDedupService
from media_importer.pipeline.services import ImportService as PipelineImportService
from media_importer.pipeline.services import (
    SourceCleanupService as PipelineSourceCleanupService,
)
from media_importer.pipeline.services.review import (
    ReviewDecision as PipelineReviewDecision,
)
from media_importer.pipeline.services.review import (
    ReviewDecisionService as PipelineReviewDecisionService,
)


class TestImportFlowFeatureCompatibility(unittest.TestCase):
    def test_feature_public_imports_reexport_existing_objects(self):
        self.assertIs(TaskContext, PipelineTaskContext)
        self.assertIs(feature_context, legacy_context)
        self.assertIs(ConfirmMixin, PipelineConfirmMixin)
        self.assertIs(feature_confirm, legacy_confirm)
        self.assertIs(PipelineRunner, PipelinePackageRunner)
        self.assertIs(feature_runner, legacy_runner)
        self.assertIs(StepsMixin, PipelineStepsMixin)
        self.assertIs(FileStepsMixin, PipelineFileStepsMixin)
        self.assertIs(ScrapeStepsMixin, PipelineScrapeStepsMixin)
        self.assertIs(feature_steps, legacy_steps)
        self.assertIs(feature_steps_file, legacy_steps_file)
        self.assertIs(feature_steps_scrape, legacy_steps_scrape)
        self.assertIs(feature_utils.PipelineError, legacy_utils.PipelineError)
        self.assertIs(feature_utils.PipelineSkipError, legacy_utils.PipelineSkipError)
        self.assertIs(feature_utils.PIPELINE_STEPS, legacy_utils.PIPELINE_STEPS)
        self.assertIs(feature_utils._extract_series_name, legacy_utils._extract_series_name)
        self.assertIs(ClassificationService, PipelineClassificationService)
        self.assertIs(DedupService, PipelineDedupService)
        self.assertIs(ImportService, PipelineImportService)
        self.assertIs(SourceCleanupService, PipelineSourceCleanupService)
        self.assertIs(ReviewDecision, PipelineReviewDecision)
        self.assertIs(ReviewDecisionService, PipelineReviewDecisionService)
        self.assertIs(mark_imported, core_mark_imported)
        self.assertIs(import_flow.TaskContext, PipelineTaskContext)

    def test_feature_lifecycle_module_reexports_existing_functions(self):
        self.assertIs(feature_lifecycle.mark_imported, core_lifecycle.mark_imported)
        self.assertIs(feature_lifecycle.mark_failed, core_lifecycle.mark_failed)
        self.assertIs(feature_lifecycle.reset_for_retry, core_lifecycle.reset_for_retry)

    def test_feature_context_preserves_task_dict_contract(self):
        task = {"task_id": "t1", "source_path": "/source/movie.mkv"}
        ctx = TaskContext(task)

        ctx.mark_temp("/temp/movie.mkv", ["/temp/movie.srt"])
        fields = ctx.to_update_fields("video_path", "subtitle_files", "missing")

        self.assertEqual(ctx.current_video_path, "/temp/movie.mkv")
        self.assertEqual(fields, {
            "video_path": "/temp/movie.mkv",
            "subtitle_files": ["/temp/movie.srt"],
        })

    def test_old_patch_path_still_affects_feature_import(self):
        engine = object()
        with patch(
            "media_importer.pipeline.services.review.ReviewDecisionService.evaluate",
            return_value=ReviewDecision(action="continue"),
        ) as patched:
            decision = ReviewDecisionService().evaluate({}, engine)

        self.assertEqual(decision.action, "continue")
        patched.assert_called_once_with({}, engine)

    def test_old_service_patch_path_still_affects_feature_service(self):
        with patch(
            "media_importer.pipeline.services.dedup.check_duplicate",
            return_value={"is_duplicate": False},
        ) as patched:
            service = DedupService({
                "duplicate_handling": {"enabled": True},
                "path_rules": [{"template": "/library/movies"}],
            })
            with patch("media_importer.pipeline.services.dedup.os.path.isdir", return_value=True):
                decision = service.check_task({"scrape_result": {}, "video_path": "/tmp/movie.mkv"})

        self.assertEqual(decision.action, "continue")
        patched.assert_called_once()


if __name__ == "__main__":
    unittest.main()
