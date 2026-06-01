#!/usr/bin/env python3
import os
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from media_importer.core import task_lifecycle as core_lifecycle
from media_importer.core.task_lifecycle import mark_imported as core_mark_imported
from media_importer.domains import import_flow
from media_importer.domains.import_flow import (
    ReviewDecision,
    ReviewDecisionService,
    TaskContext,
    mark_imported,
)
from media_importer.domains.import_flow import lifecycle as domain_lifecycle
from media_importer.pipeline.context import TaskContext as PipelineTaskContext
from media_importer.pipeline.services.review import (
    ReviewDecision as PipelineReviewDecision,
)
from media_importer.pipeline.services.review import (
    ReviewDecisionService as PipelineReviewDecisionService,
)


class TestImportFlowDomainCompatibility(unittest.TestCase):
    def test_domain_public_imports_reexport_existing_objects(self):
        self.assertIs(TaskContext, PipelineTaskContext)
        self.assertIs(ReviewDecision, PipelineReviewDecision)
        self.assertIs(ReviewDecisionService, PipelineReviewDecisionService)
        self.assertIs(mark_imported, core_mark_imported)
        self.assertIs(import_flow.TaskContext, PipelineTaskContext)

    def test_domain_lifecycle_module_reexports_existing_functions(self):
        self.assertIs(domain_lifecycle.mark_imported, core_lifecycle.mark_imported)
        self.assertIs(domain_lifecycle.mark_failed, core_lifecycle.mark_failed)
        self.assertIs(domain_lifecycle.reset_for_retry, core_lifecycle.reset_for_retry)

    def test_domain_context_preserves_task_dict_contract(self):
        task = {"task_id": "t1", "source_path": "/source/movie.mkv"}
        ctx = TaskContext(task)

        ctx.mark_temp("/temp/movie.mkv", ["/temp/movie.srt"])
        fields = ctx.to_update_fields("video_path", "subtitle_files", "missing")

        self.assertEqual(ctx.current_video_path, "/temp/movie.mkv")
        self.assertEqual(fields, {
            "video_path": "/temp/movie.mkv",
            "subtitle_files": ["/temp/movie.srt"],
        })

    def test_old_patch_path_still_affects_domain_import(self):
        engine = object()
        with patch(
            "media_importer.pipeline.services.review.ReviewDecisionService.evaluate",
            return_value=ReviewDecision(action="continue"),
        ) as patched:
            decision = ReviewDecisionService().evaluate({}, engine)

        self.assertEqual(decision.action, "continue")
        patched.assert_called_once_with({}, engine)


if __name__ == "__main__":
    unittest.main()
