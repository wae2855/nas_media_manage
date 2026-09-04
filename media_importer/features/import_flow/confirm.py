import os
from contextlib import nullcontext
from typing import Optional

from media_importer.features.import_flow.context import TaskContext
from media_importer.features.import_flow.services import (
    ClassificationService,
    DedupService,
    apply_filename_template,
)
from media_importer.features.import_flow.utils import (
    PipelineCancelled,
    PipelineError,
    PipelineReviewRequired,
    PipelineSkipError,
)
from media_importer.features.source_files import SourceCleanupService
from media_importer.features.tasks import (
    FILE_LOCATION_RECYCLE,
    FILE_LOCATION_SOURCE,
    mark_confirming,
    mark_failed,
    mark_imported,
    mark_processing_step,
    mark_skipped,
)
from media_importer.infrastructure.db import get_enabled_dimensions
from media_importer.infrastructure.db import update_subtitles_by_task as db_update_subs
from media_importer.infrastructure.db import update_task as db_update_task


class ConfirmMixin:  # type: ignore[misc]
    def apply_scrape_candidate(
        self,
        task_id: str,
        *,
        provider_type: str,
        item_id: str,
        media_type: str,
        language: str = "",
    ) -> dict:
        """应用完整 Provider 候选并刷新入库预览，但不启动文件处理。"""

        from media_importer.features.tasks.search_service import load_provider_candidate

        selected = load_provider_candidate(
            self.config,
            self.task_manager.conn,
            provider_type=provider_type,
            item_id=item_id,
            media_type=media_type,
            language=language or None,
        )
        return ConfirmMixin.apply_loaded_scrape_candidate(
            self,
            task_id,
            selected=selected,
            provider_type=provider_type,
            item_id=item_id,
            media_type=media_type,
        )

    def apply_loaded_scrape_candidate(
        self,
        task_id: str,
        *,
        selected: dict,
        provider_type: str,
        item_id: str,
        media_type: str,
    ) -> dict:
        """Apply already-loaded Provider data to one task without file import."""

        task = self.task_manager.get_task(task_id)
        if (
            not task
            or task.get("status") != "PENDING"
            or task.get("stage") != "AWAIT_REVIEW"
        ):
            raise PipelineError("只有等待人工确认的任务可以重新选择作品资料")
        old_result = task.get("scrape_result") or {}
        old_dimensions = task.get("scrape_dimensions") or {}
        old_sources = task.get("dim_sources") or {}
        if not isinstance(old_result, dict):
            old_result = {}
        if not isinstance(old_dimensions, dict):
            old_dimensions = {}
        if not isinstance(old_sources, dict):
            old_sources = {}

        scrape_result = dict(selected["scrape_result"])
        dimensions = dict(selected.get("dimensions") or {})
        dim_sources = dict(selected.get("dim_sources") or {})

        # Provider 候选会替换旧 Provider 维度；文件探测事实继续保留。
        for name, source in old_sources.items():
            if str(source).startswith("file") and name in old_dimensions:
                dimensions[name] = old_dimensions[name]
                dim_sources[name] = source

        if media_type == "tv":
            for name in ("season", "episode"):
                value = old_result.get(name)
                if value in (None, ""):
                    value = old_dimensions.get(name)
                if value not in (None, ""):
                    scrape_result[name] = value
                    dimensions[name] = value
                    dim_sources[name] = old_sources.get(name, "file:filename")

        scrape_result["dimensions"] = dimensions
        task.update({
            "scrape_result": scrape_result,
            "scrape_dimensions": dimensions,
            "scrape_title_cn": scrape_result.get("title_cn", ""),
            "scrape_title_en": scrape_result.get("title_en", ""),
            "scrape_year": scrape_result.get("year", ""),
            "scrape_media_type": media_type,
            "scrape_season": scrape_result.get("season"),
            "scrape_episode": scrape_result.get("episode"),
            "provider_type": provider_type,
            "provider_id": str(item_id),
            "match_level": "NEEDS_CONFIRM",
            "match_concerns": [],
            "match_trace": {},
            "scrape_trace": {
                "manual_selected": True,
                "provider_type": provider_type,
                "provider_id": str(item_id),
                "language": selected.get("language", ""),
                "provider_dimensions": selected.get("dimensions", {}),
                "dimension_mapping_evidence": (
                    scrape_result.get("scrape_trace", {}).get(
                        "dimension_mapping_evidence", {}
                    )
                    if isinstance(scrape_result.get("scrape_trace"), dict)
                    else {}
                ),
            },
            "dim_sources": dim_sources,
            "final_filename": "",
            "dedup_result": {},
            "dedup_existing_file": "",
        })

        enabled_names = {
            item["name"] for item in get_enabled_dimensions(self.task_manager.conn)
        }
        classify_result = ClassificationService(self.config).classify_task(
            task,
            enabled_names,
        )
        if not classify_result.import_path:
            raise PipelineError("资料已找到，但当前入库规则无法确定目标片库")
        task["import_path"] = classify_result.import_path
        task["classify_result"] = classify_result.classify_result
        task["used_fallback"] = 1 if classify_result.used_fallback else 0

        templates = self.config.get("filename_templates", {}) or {}
        template = templates.get("tv" if media_type == "tv" else "movie", "")
        source_extension = os.path.splitext(
            task.get("source_path")
            or task.get("source_filename", "")
        )[1]
        task["final_filename"] = apply_filename_template(
            scrape_result,
            template,
            source_extension,
        )
        from media_importer.features.import_flow.services.naming import (
            plan_subtitle_filenames,
        )
        from media_importer.infrastructure.db import (
            get_subtitles_by_task,
            update_subtitle,
        )

        subtitle_rows = get_subtitles_by_task(self.task_manager.conn, task_id)
        subtitle_plan = plan_subtitle_filenames(
            [row.get("source_path", "") for row in subtitle_rows],
            task["final_filename"],
            self.config.get("filename_templates", {}).get(
                "subtitle", "{video_filename}.{lang}.{ext}"
            ),
        )
        for row, planned in zip(subtitle_rows, subtitle_plan, strict=False):
            update_subtitle(
                self.task_manager.conn,
                row["id"],
                planned_filename=planned["filename"],
                lang=planned["lang"],
            )
        thumbnail_path = ""
        poster_url = str(scrape_result.get("poster_url", "") or "")
        if poster_url:
            try:
                from media_importer.features.scraping.thumbnail_downloader import (
                    download_thumbnail,
                )

                thumbnail_path = download_thumbnail(
                    poster_url,
                    self.config,
                    title=scrape_result.get("title_cn") or scrape_result.get("title_en", ""),
                    provider_id=str(item_id),
                ) or ""
            except Exception as error:
                self._log(
                    "warning",
                    f"手动选择后的海报下载失败（不影响资料应用）: {error}",
                    task,
                    "scrape",
                )
        task["thumbnail_path"] = thumbnail_path
        dedup = DedupService(self.config).check_task(task)
        task["dedup_result"] = dedup.result
        task["dedup_existing_file"] = dedup.result.get("existing_file", "")

        from media_importer.infrastructure.db import compare_and_update_task

        fields = {
            key: task.get(key)
            for key in (
                "scrape_result", "scrape_dimensions", "scrape_title_cn",
                "scrape_title_en", "scrape_year", "scrape_media_type",
                "scrape_season", "scrape_episode", "provider_type", "provider_id",
                "match_level", "match_concerns", "match_trace", "scrape_trace",
                "dim_sources", "classify_result", "import_path", "final_filename",
                "dedup_result", "dedup_existing_file",
                "thumbnail_path", "used_fallback",
            )
        }
        updated = compare_and_update_task(
            self.task_manager.conn,
            task_id,
            expect_status="PENDING",
            expect_stage="AWAIT_REVIEW",
            **fields,
        )
        if updated is None:
            raise PipelineError("任务状态已变化，资料未应用，请刷新后重试")
        self._log(
            "info",
            f"已手动选择作品资料: {scrape_result.get('title_cn') or scrape_result.get('title_en')}",
            updated,
            "scrape",
        )
        return updated

    def confirm_task(self, task_id: str, confirmed_title: Optional[str] = None,
                     override_source: Optional[str] = None,
                     conflict_action: Optional[str] = None,
                     source_disposition: Optional[str] = None,
                     fallback_acknowledged: bool = False) -> bool:
        slot_factory = getattr(self, "task_slot", None)
        slot = slot_factory() if callable(slot_factory) else nullcontext()
        with slot:
            return self._confirm_task_impl(
                task_id,
                confirmed_title=confirmed_title,
                override_source=override_source,
                conflict_action=conflict_action,
                source_disposition=source_disposition,
                fallback_acknowledged=fallback_acknowledged,
            )

    def _confirm_task_impl(self, task_id: str, confirmed_title: Optional[str] = None,
                           override_source: Optional[str] = None,
                           conflict_action: Optional[str] = None,
                           source_disposition: Optional[str] = None,
                           fallback_acknowledged: bool = False) -> bool:
        task = self.task_manager.get_task(task_id)
        if not task or task.get("stage") != "AWAIT_REVIEW":
            raise PipelineError(f"任务不可确认: 状态={task.get('status', 'UNKNOWN') if task else 'NOT_FOUND'}/{task.get('stage', '') if task else ''}")
        ctx = TaskContext(task)
        tid = task_id
        original_source_video = task.get("source_path", "")
        subtitle_source_files = task.get("subtitle_source_files", [])
        original_source_subs = subtitle_source_files or task.get("subtitle_files", [])
        conflict = task.get("dedup_result") or {}
        has_conflict = bool(
            conflict.get("is_duplicate")
            and conflict.get("status") == "awaiting_user"
        )
        allowed_actions = {"keep_existing", "keep_both", "replace_existing"}
        if has_conflict and conflict_action not in allowed_actions:
            raise PipelineError("片库冲突必须逐项选择：保留片库文件、两个都保留或替换片库文件")
        if not has_conflict and conflict_action:
            raise PipelineError("当前任务没有待处理的片库冲突，请刷新任务")

        enabled_dim_names = {
            item["name"] for item in get_enabled_dimensions(self.task_manager.conn)
        }
        gate_classification = ClassificationService(self.config).classify_task(
            task,
            enabled_dim_names,
        )
        task["used_fallback"] = 1 if gate_classification.used_fallback else 0
        if task.get("task_kind") == "REORGANIZE" and gate_classification.used_fallback:
            raise PipelineError("重新整理任务仍未匹配正式入库规则，请调整维度或重新刮削")
        if gate_classification.used_fallback and not fallback_acknowledged:
            raise PipelineError("该影片将进入待整理区，请先明确确认后再继续")

        if has_conflict:
            existing_path = os.path.realpath(str(conflict.get("existing_path", "")))
            import_path = os.path.realpath(str(task.get("import_path", "")))
            try:
                within_target = os.path.commonpath((existing_path, import_path)) == import_path
            except ValueError:
                within_target = False
            if not within_target:
                raise PipelineError("冲突文件不在本任务实际目标目录内，已拒绝操作")

        # S3 CAS：AWAIT_REVIEW → RUNNING 一次性占用（并发双 confirm 只成功一次）
        from media_importer.features.tasks.transitions import apply as _apply_transition
        from media_importer.infrastructure.db import compare_and_update_task
        claim_fields = _apply_transition(task, "confirm_start")
        claimed = compare_and_update_task(
            self.task_manager.conn, tid,
            expect_status="PENDING", expect_stage="AWAIT_REVIEW",
            **claim_fields,
        )
        if claimed is None:
            raise PipelineError("任务状态已变更（可能已被并发确认），请刷新后重试")

        if has_conflict and conflict_action == "keep_existing":
            conflict.update({"status": "resolved", "resolved_action": "keep_existing"})
            fields = mark_skipped(
                ctx,
                "用户选择保留片库现有文件；来源文件保持不变",
                file_location=FILE_LOCATION_SOURCE,
            )
            fields["dedup_result"] = conflict
            db_update_task(self.task_manager.conn, tid, **fields)
            from media_importer.features.tasks import request_task_disposition

            disposition_result = request_task_disposition(
                self.task_manager,
                self.config,
                tid,
                source_disposition=source_disposition or "keep",
            )
            self._log(
                "info" if disposition_result.code == 200 else "warn",
                disposition_result.message,
                task,
                "dedup",
            )
            return disposition_result.code == 200

        if has_conflict:
            conflict.update({"status": "resolved", "resolved_action": conflict_action})
            if conflict_action == "keep_both":
                task["final_filename"] = str(conflict.get("suggested_filename", ""))
            task["dedup_result"] = conflict
            db_update_task(
                self.task_manager.conn,
                tid,
                dedup_result=conflict,
                final_filename=task.get("final_filename", ""),
            )

        confirmed_override = 1 if override_source else 0
        db_update_task(self.task_manager.conn, tid,
                       confirmed_override=confirmed_override,
                       confirmed_title=confirmed_title or "",
                       override_source=override_source or "")

        db_update_subs(self.task_manager.conn, tid,
                       confirm_status="CONFIRMED")

        try:
            classify_result = ClassificationService(self.config).classify_task(task, enabled_dim_names)
            task["import_path"] = classify_result.import_path
            task["classify_result"] = classify_result.classify_result
            db_update_task(self.task_manager.conn, tid,
                           import_path=classify_result.import_path,
                           classify_result=classify_result.classify_result)
            self._log("info", f"确认分类: {classify_result.import_path}", task, "classify")

            if task.get("task_kind") == "REORGANIZE":
                self._step_reorganize_from_confirm(task)
                self._step_notify(task)
                self._step_record(task)
                completion_fields = mark_imported(
                    ctx,
                    import_video_path=task.get("import_video_path", ""),
                )
                completion_fields.update({
                    "used_fallback": 0,
                    "organization_status": "ORGANIZED",
                    "source_cleanup_status": "SKIPPED",
                    "file_location": "import",
                    "video_path": task.get("import_video_path", ""),
                })
                db_update_task(self.task_manager.conn, tid, **completion_fields)
                self.hooks.run_after_success(task)
                if self.metrics:
                    self.metrics.record_task_complete("success")
                self._log(
                    "info",
                    f"重新整理完成: {task.get('source_filename', '')}",
                    task,
                )
                return True

            self._step_import_from_confirm(task, original_source_video, original_source_subs)
            self._step_notify(task)
            self._complete_source_cleanup(task)
            self._step_record(task)

            completion_fields = mark_imported(ctx)
            completion_fields.update({
                "used_fallback": 1 if classify_result.used_fallback else 0,
                "organization_status": (
                    "FALLBACK_PENDING" if classify_result.used_fallback else ""
                ),
            })
            db_update_task(self.task_manager.conn, tid, **completion_fields)
            self.hooks.run_after_success(task)
            if self.metrics:
                self.metrics.record_task_complete("success")
            self._log("info", f"确认入库完成: {task.get('source_filename', '')}", task)
            return True
        except PipelineCancelled:
            self._complete_user_stop(task)
            if self.metrics:
                self.metrics.record_task_complete("cancelled")
            return False
        except PipelineReviewRequired as e:
            review_result = e.result or task.get("dedup_result") or {}
            fields = mark_confirming(ctx, str(e))
            fields.update({
                "dedup_result": review_result,
                "dedup_existing_file": review_result.get("existing_file", ""),
                "final_filename": task.get("final_filename", ""),
                "import_path": task.get("import_path", ""),
            })
            db_update_task(self.task_manager.conn, tid, **fields)
            self._log("info", "片库冲突待用户逐项确认，现有文件未改动", task, "dedup")
            return True
        except PipelineSkipError as e:
            # 去重判重等跳过场景：标 SKIPPED 而非 FAILED（与正常流程 runner 行为一致）
            self._log("info", f"确认入库跳过: {task.get('source_filename', '')} - {e}", task)
            source_cleanup = SourceCleanupService(self.config).recycle_source_after_skip(
                task,
                original_source_video,
                original_source_subs,
            )
            file_location = FILE_LOCATION_RECYCLE if source_cleanup.moved_count else FILE_LOCATION_SOURCE
            if source_cleanup.message:
                self._log("info", source_cleanup.message, task, "cleanup")
            fields = mark_skipped(ctx, str(e), file_location=file_location)
            db_update_task(self.task_manager.conn, tid, **fields)
            if self.metrics:
                self.metrics.record_task_complete("skipped")
            return True
        except Exception as e:
            error_msg = str(e)
            db_update_task(self.task_manager.conn, tid,
                           **mark_failed(
                                ctx, error_msg,
                                file_location=FILE_LOCATION_SOURCE,
                                video_path=original_source_video,
                            ))
            self._log("error", f"确认入库失败: {task.get('source_filename', '')} - {e}", task)
            return False

    def preview_task(self, task_id: str, updates: dict) -> dict:
        """预览元数据/维度/文件名变更，只更新 DB + 重跑分类，不触发文件操作。"""
        task = self.task_manager.get_task(task_id)
        if not task:
            raise PipelineError(f"任务不存在: {task_id}")
        tid = task_id

        scrape_result = task.get("scrape_result", {})
        if isinstance(scrape_result, str):
            scrape_result = {}

        if "title_cn" in updates:
            scrape_result["title_cn"] = updates["title_cn"]
        if "title_en" in updates:
            scrape_result["title_en"] = updates["title_en"]
        if "year" in updates:
            scrape_result["year"] = updates["year"]

        current_dims = task.get("scrape_dimensions", {})
        if isinstance(current_dims, str):
            current_dims = {}
        if "dimensions" in updates:
            dims = updates["dimensions"]
            current_dims.update(dims)
            enabled_dim_names = {d["name"] for d in get_enabled_dimensions(self.task_manager.conn)}
            current_dims = {k: v for k, v in current_dims.items() if k in enabled_dim_names}
            scrape_result["dimensions"] = current_dims
            # 人工修改的维度记录来源为 manual（区别于 provider/file/default）
            dim_sources = task.get("dim_sources") or {}
            if isinstance(dim_sources, str):
                dim_sources = {}
            for k in dims:
                dim_sources[k] = "manual"
            task["dim_sources"] = dim_sources

        task["scrape_result"] = scrape_result
        task["scrape_dimensions"] = current_dims

        db_update_task(
            self.task_manager.conn, tid,
            scrape_result=scrape_result,
            scrape_dimensions=current_dims,
            scrape_title_cn=scrape_result.get("title_cn", ""),
            scrape_title_en=scrape_result.get("title_en", ""),
            scrape_year=str(scrape_result.get("year", "")) if scrape_result.get("year") else "",
            dim_sources=task.get("dim_sources", {}),
            classify_result="",
        )

        enabled_dim_names = {d["name"] for d in get_enabled_dimensions(self.task_manager.conn)}
        result = ClassificationService(self.config).classify_task(task, enabled_dim_names)
        task["import_path"] = result.import_path
        task["classify_result"] = result.classify_result
        task["used_fallback"] = 1 if result.used_fallback else 0

        if "filename" in updates:
            task["final_filename"] = updates["filename"]
        elif not task.get("final_filename"):
            templates = self.config.get("filename_templates", {})
            video_ext = os.path.splitext(task.get("video_path", "") or task.get("source_filename", ""))[1]
            if scrape_result.get("media_type") == "tv":
                template = templates.get("tv", "{title_cn}.{title_en}.{year}.S{season}E{episode}.{ext}")
            else:
                template = templates.get("movie", "{title_cn}.{title_en}.{year}.{resolution}.{quality}.{ext}")
            task["final_filename"] = apply_filename_template(scrape_result, template, video_ext)

        db_update_task(
            self.task_manager.conn, tid,
            scrape_result=scrape_result,
            scrape_dimensions=current_dims,
            classify_result=result.classify_result,
            import_path=result.import_path,
            final_filename=task["final_filename"],
            used_fallback=task["used_fallback"],
        )

        self._log("info", f"预览更新完成: {task.get('source_filename', '')}", task)
        return self.task_manager.get_task(tid)

    def reclassify_task(self, task_id: str, new_dimensions: dict) -> dict:
        task = self.task_manager.get_task(task_id)
        if not task:
            raise PipelineError(f"任务不存在: {task_id}")
        ctx = TaskContext(task)
        tid = task_id

        current_dims = task.get("scrape_dimensions", {})
        if isinstance(current_dims, str):
            current_dims = {}
        current_dims.update(new_dimensions)

        # 清洗已禁用维度的值
        enabled_dim_names = {d["name"] for d in get_enabled_dimensions(self.task_manager.conn)}
        current_dims = {k: v for k, v in current_dims.items() if k in enabled_dim_names}
        task["scrape_dimensions"] = current_dims

        # 人工重新分类的维度记录来源为 manual
        dim_sources = task.get("dim_sources", {})
        if isinstance(dim_sources, str):
            dim_sources = {}
        for k in new_dimensions:
            dim_sources[k] = "manual"
        task["dim_sources"] = dim_sources

        scrape_result = task.get("scrape_result", {})
        if isinstance(scrape_result, dict):
            scrape_result["dimensions"] = current_dims

        db_update_task(
            self.task_manager.conn, tid,
            scrape_dimensions=current_dims,
            dim_sources=dim_sources,
            classify_result="",
        )

        result = ClassificationService(self.config).classify_task(task, enabled_dim_names)
        if not result.import_path:
            raise PipelineError(f"重新分类失败，维度=[{result.dimensions_text}]")
        if result.used_fallback:
            self._log("info", f"重新分类：无匹配规则，使用兜底目录: {result.import_path}", task, "classify")

        task["import_path"] = result.import_path
        task["classify_result"] = result.classify_result
        task["used_fallback"] = 1 if result.used_fallback else 0
        fields = mark_processing_step(
            ctx, current_step=5, step_name="classify", percentage=50
        )
        fields.update({
            "import_path": result.import_path,
            "classify_result": result.classify_result,
            "used_fallback": task["used_fallback"],
        })
        db_update_task(self.task_manager.conn, tid,
                       **fields)
        self._log("info", f"任务重新分类完成: {result.import_path}，继续后续流程", task, "classify")

        # 重分类不再触发入库（改为预览逻辑，兼容旧调用方）
        templates = self.config.get("filename_templates", {})
        video_ext = os.path.splitext(task.get("video_path", "") or task.get("source_filename", ""))[1]
        if scrape_result.get("media_type") == "tv":
            template = templates.get("tv", "{title_cn}.{title_en}.{year}.S{season}E{episode}.{ext}")
        else:
            template = templates.get("movie", "{title_cn}.{title_en}.{year}.{resolution}.{quality}.{ext}")
        task["final_filename"] = apply_filename_template(
            scrape_result, template, video_ext)

        db_update_task(self.task_manager.conn, tid,
                       import_path=result.import_path,
                       classify_result=result.classify_result,
                       final_filename=task["final_filename"],
                       used_fallback=task["used_fallback"])

        self._log("info", f"重新分类（预览）完成: {result.import_path}", task, "classify")
        return self.task_manager.get_task(tid)
