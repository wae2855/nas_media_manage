#!/usr/bin/env python3
import os
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from media_importer.features import import_flow
from media_importer.features.import_flow import (
    ClassificationService,
    ConfirmMixin,
    DedupService,
    FileStepsMixin,
    ImportService,
    PipelineRunner,
    ReviewDecision,
    ReviewDecisionService,
    ScrapeStepsMixin,
    SourceCleanupService,
    StepsMixin,
    TaskContext,
    mark_imported,
)
from media_importer.features.import_flow import context as feature_context
from media_importer.features.import_flow import lifecycle as feature_lifecycle
from media_importer.features.import_flow import utils as feature_utils
from media_importer.features.tasks import mark_imported as task_mark_imported


class TestImportFlowFeature(unittest.TestCase):
    def test_feature_public_imports_are_available(self):
        self.assertIs(import_flow.TaskContext, TaskContext)
        self.assertIs(import_flow.PipelineRunner, PipelineRunner)
        self.assertIs(import_flow.ClassificationService, ClassificationService)
        self.assertIs(import_flow.DedupService, DedupService)
        self.assertIs(import_flow.ImportService, ImportService)
        self.assertIs(import_flow.SourceCleanupService, SourceCleanupService)
        self.assertIs(import_flow.ReviewDecision, ReviewDecision)
        self.assertIs(import_flow.ReviewDecisionService, ReviewDecisionService)
        self.assertIs(import_flow.StepsMixin, StepsMixin)
        self.assertIs(import_flow.FileStepsMixin, FileStepsMixin)
        self.assertIs(import_flow.ScrapeStepsMixin, ScrapeStepsMixin)
        self.assertIs(import_flow.ConfirmMixin, ConfirmMixin)
        self.assertIs(mark_imported, task_mark_imported)
        self.assertTrue(feature_utils.PIPELINE_STEPS)

    def test_feature_lifecycle_reexports_task_lifecycle_functions(self):
        self.assertIs(feature_lifecycle.mark_imported, task_mark_imported)
        self.assertTrue(hasattr(feature_lifecycle, "mark_failed"))
        self.assertTrue(hasattr(feature_lifecycle, "reset_for_retry"))

    def test_feature_context_preserves_task_dict_contract(self):
        task = {"task_id": "t1", "source_path": "/source/movie.mkv"}
        ctx = TaskContext(task)

        ctx.mark_temp("/temp/movie.mkv", ["/temp/movie.srt"])
        fields = ctx.to_update_fields("video_path", "subtitle_files", "missing")

        self.assertIs(feature_context.TaskContext, TaskContext)
        self.assertEqual(ctx.current_video_path, "/temp/movie.mkv")
        self.assertEqual(fields, {
            "video_path": "/temp/movie.mkv",
            "subtitle_files": ["/temp/movie.srt"],
        })

    def test_feature_patch_path_controls_review_service(self):
        engine = object()
        with patch(
            "media_importer.features.import_flow.services.review.ReviewDecisionService.evaluate",
            return_value=ReviewDecision(action="continue"),
        ) as patched:
            decision = ReviewDecisionService().evaluate({}, engine)

        self.assertEqual(decision.action, "continue")
        patched.assert_called_once_with({}, engine)

    def test_feature_service_patch_path_controls_dedup_service(self):
        with patch(
            "media_importer.features.import_flow.services.dedup.check_duplicate",
            return_value={"is_duplicate": False},
        ) as patched:
            service = DedupService({
                "duplicate_handling": {"enabled": True},
                "path_rules": [{"template": "/library/movies"}],
            })
            with patch("media_importer.features.import_flow.services.dedup.os.path.isdir", return_value=True):
                decision = service.check_task({"scrape_result": {}, "video_path": "/tmp/movie.mkv"})

        self.assertEqual(decision.action, "continue")
        patched.assert_called_once()


if __name__ == "__main__":
    unittest.main()
