import os
from datetime import datetime
from media_importer.core.db import (
    update_task as db_update_task,
    get_subtitles_by_task as db_get_subtitles,
    update_subtitle as db_update_subtitle,
)
from media_importer.storage.classifier import classify, render_template
from media_importer.storage.dedup_checker import check_duplicate
from media_importer.storage.file_mover import apply_filename_template, move_to_import, delete_source_files, remove_empty_parent_dir
from .utils import PipelineError, PipelineSkipError


class FileStepsMixin:
    def _step_copy(self, task: dict):
        self._update_progress(task, 2, "copy", 20)
        file_location = task.get("file_location", "source")
        if file_location in ("source", "recycle"):
            video_path = task.get("source_path", "")
        else:
            video_path = task.get("video_path") or task.get("source_path", "")
        subtitle_files = task.get("subtitle_files", [])
        self._log("info", f"复制文件: {task.get('source_filename', '')} (从{file_location})", task, "copy")

        def progress_cb(copied, total):
            pct = int(20 + (copied / total) * 10) if total > 0 else 25
            self._update_progress(task, 2, "copy", pct,
                                  bytes_copied=copied, total_bytes=total)

        def heartbeat_cb():
            self.task_manager.update_task(task)

        try:
            copied = self.copier.copy_to_temp(
                video_path, subtitle_files,
                progress_cb, heartbeat_cb, heartbeat_interval=30
            )
            task["video_path"] = copied[0]
            task["subtitle_files"] = copied[1:] if len(copied) > 1 else []
            tid = task.get("task_id", "")
            if tid:
                sub_target_paths = copied[1:] if len(copied) > 1 else []
                subs = db_get_subtitles(self.task_manager.conn, tid)
                for i, sub in enumerate(subs):
                    if i < len(sub_target_paths):
                        db_update_subtitle(self.task_manager.conn, sub["id"],
                                           target_path=sub_target_paths[i])
        except IOError as e:
            raise PipelineError(f"复制失败: {e}")

        self._update_progress(task, 2, "copy", 30)

    def _step_classify(self, task: dict):
        self._update_progress(task, 5, "classify", 56)
        self._log("info", f"分类匹配: {task.get('source_filename', '')}", task, "classify")

        path_rules = self.config.get('path_rules', [])
        dimensions = task.get("scrape_dimensions", {})
        dims_str = ', '.join(f'{k}={v}' for k, v in dimensions.items()) if dimensions else '无'
        self._log("info", f"文件维度: [{dims_str}]", task, "classify")

        scraped = task.get("scrape_result", {})
        import_path = classify(scraped, path_rules)
        if not import_path:
            fallback_dir = self.config.get("fallback_dir", "")
            if fallback_dir:
                import_path = render_template(fallback_dir, scraped)
                self._log("info", f"无匹配规则，使用兜底目录: {import_path}", task, "classify")
            else:
                rules_desc = []
                for i, rule in enumerate(path_rules):
                    cond = rule.get('conditions', {})
                    cond_str = ', '.join(f'{k}={v}' for k, v in cond.items())
                    rules_desc.append(f"规则{i+1}: [{cond_str}]")
                self._log("error",
                      f"无匹配规则。文件维度=[{dims_str}], "
                      f"可用规则: {'; '.join(rules_desc) if rules_desc else '无规则配置'}",
                      task, "classify")
            raise PipelineError(f"分类匹配失败，无匹配规则。维度=[{dims_str}]")

        self._log("info", f"匹配路径: {import_path}", task, "classify")

        if not os.path.isabs(import_path):
            project_root = os.path.dirname(
                os.path.dirname(os.path.abspath(
                    self.config.get('_config_path', '')
                ))
            )
            if project_root:
                import_path = os.path.join(project_root, import_path)

        task["import_path"] = import_path
        task["classify_result"] = import_path
        db_update_task(self.task_manager.conn, task.get("task_id", ""),
                       import_path=import_path, classify_result=import_path)
        self._update_progress(task, 5, "classify", 60)

    def _get_import_roots(self) -> list:
        path_rules = self.config.get('path_rules', [])
        templates = [r.get('template', '') for r in path_rules if r.get('template')]
        if not templates:
            return []
        roots = []
        for tpl in templates:
            if not os.path.isabs(tpl):
                project_root = os.path.dirname(
                    os.path.dirname(os.path.abspath(
                        self.config.get('_config_path', '')
                    ))
                )
                if project_root:
                    tpl = os.path.join(project_root, tpl)
            tpl = os.path.normpath(tpl)
            parts = tpl.split(os.sep)
            for i, p in enumerate(parts):
                if p.startswith('{'):
                    if i > 0:
                        roots.append(os.sep.join(parts[:i]))
                    break
            else:
                roots.append(tpl)
        return roots

    def _step_dedup(self, task: dict):
        self._update_progress(task, 6, "dedup", 65)
        dedup_cfg = self.config.get('duplicate_handling', {}) or {}
        self._log("info", f"同名检测: {task.get('source_filename', '')}", task, "dedup")
        strategy = dedup_cfg.get('strategy', 'skip')
        import_roots = self._get_import_roots()
        dedup_result = {'is_duplicate': False}
        scraped = task.get("scrape_result", {})
        video_path = task.get("video_path", "")
        for search_dir in import_roots:
            if not os.path.isdir(search_dir):
                continue
            result = check_duplicate(search_dir, scraped, strategy, video_path)
            if result['is_duplicate']:
                dedup_result = result
                break
        if dedup_result['is_duplicate']:
            if strategy == 'skip':
                skip_msg = dedup_result.get('skip_message',
                    f"同名文件已存在: {dedup_result.get('existing_file', 'unknown')}")
                raise PipelineSkipError(skip_msg)
            elif strategy == 'rename':
                task["final_filename"] = os.path.basename(
                    dedup_result['suggested_filename']
                )
            elif strategy == 'replace':
                self._log("info", f"替换模式: 将移入回收站已存在文件 {dedup_result['existing_file']}", task, "dedup")
                if os.path.exists(dedup_result['existing_path']):
                    from media_importer.core.safety import move_to_recycle
                    recycle_dir = self.config.get("source_policy", {}).get("recycle_dir", "")
                    source_dir = self.config.get("source_dir", "")
                    ok, dest, msg = move_to_recycle(
                        dedup_result['existing_path'], recycle_dir,
                        reason="dedup_replace", task_id=task.get("task_id", ""),
                        source_dir=source_dir, import_roots=import_roots,
                    )
                    if ok:
                        self._log("info", f"已移入回收站: {dedup_result['existing_file']}", task, "dedup")
                    else:
                        self._log("warning", f"移入回收站失败: {msg}", task, "dedup")
                        raise PipelineError(f"无法移入回收站: {msg}")
            elif strategy == 'quality':
                quality_decision = dedup_result.get('quality_decision')
                if quality_decision == 'replace':
                    self._log("info", f"质量优先: 新文件质量更高，将替换已存在文件", task, "dedup")
                    if os.path.exists(dedup_result['existing_path']):
                        from media_importer.core.safety import move_to_recycle
                        recycle_dir = self.config.get("source_policy", {}).get("recycle_dir", "")
                        source_dir = self.config.get("source_dir", "")
                        ok, dest, msg = move_to_recycle(
                            dedup_result['existing_path'], recycle_dir,
                            reason="quality_replace", task_id=task.get("task_id", ""),
                            source_dir=source_dir, import_roots=import_roots,
                        )
                        if ok:
                            self._log("info", f"已移入回收站: {dedup_result['existing_file']}", task, "dedup")
                        else:
                            self._log("warning", f"移入回收站失败: {msg}", task, "dedup")
                            raise PipelineError(f"无法移入回收站: {msg}")
                else:
                    skip_msg = dedup_result.get('skip_message', "质量优先: 保留已存在文件")
                    raise PipelineSkipError(skip_msg)

        task["dedup_result"] = dedup_result
        if dedup_result.get('existing_file'):
            task["dedup_existing_file"] = dedup_result['existing_file']
        db_update_task(
            self.task_manager.conn, task.get("task_id", ""),
            dedup_result=task.get("dedup_result", {}),
            dedup_existing_file=task.get("dedup_existing_file", ""),
        )
        self._update_progress(task, 6, "dedup", 70)

    def _step_rename(self, task: dict):
        self._update_progress(task, 7, "rename", 72)
        self._log("info", f"生成文件名: {task.get('source_filename', '')}", task, "rename")

        if not task.get("final_filename"):
            templates = self.config.get('filename_templates', {})
            video_ext = os.path.splitext(task.get("video_path", ""))[1]
            scraped = task.get("scrape_result", {})
            if scraped.get('type') == 'tv':
                template = templates.get('tv', '')
            else:
                template = templates.get('movie', '')
            task["final_filename"] = apply_filename_template(
                scraped, template, video_ext
            )
        self._update_progress(task, 7, "rename", 75)

    def _get_allowed_dirs(self) -> list:
        allowed_dirs = [
            self.config.get('source_dir', ''),
            self.config.get('temp_dir', ''),
        ]
        for r in self.config.get('path_rules', []):
            tpl = r.get('template', '')
            if tpl:
                parts = tpl.split('/')
                for i, p in enumerate(parts):
                    if p.startswith('{'):
                        allowed_dirs.append('/'.join(parts[:i]))
                        break
                else:
                    allowed_dirs.append(tpl.rstrip('/'))
        return allowed_dirs

    def _step_import(self, task: dict, original_source_video: str,
                     original_source_subs: list):
        self._update_progress(task, 8, "import", 80)
        self._log("info", f"入库: {task.get('source_filename', '')}", task, "import")

        templates = self.config.get('filename_templates', {})
        allowed_dirs = self._get_allowed_dirs()
        temp_video_path = task.get("video_path", "")

        move_result = move_to_import(
            temp_video_path,
            task.get("subtitle_files", []),
            task.get("import_path", ""),
            task.get("scrape_result", {}),
            templates,
            allowed_base_dirs=allowed_dirs,
            overwrite=False,
        )
        task["video_path"] = move_result.get('video', temp_video_path)
        task["subtitle_files"] = move_result.get('subtitles', [])
        task["import_video_path"] = move_result.get('video', "")

        source_dir = self.config.get('source_dir', '')
        source_policy = self.config.get("source_policy", {})
        cleanup_source_after_done = source_policy.get("cleanup_source_after_done", False)

        if source_dir and original_source_video and cleanup_source_after_done:
            recycle_dir = source_policy.get("recycle_dir", "")
            if recycle_dir:
                from media_importer.core.safety import move_to_recycle_with_companions
                video_exts = [ext.lower() for ext in self.config.get('video_extensions', [])]
                sub_exts = [ext.lower() for ext in self.config.get('subtitle_extensions', [])]
                companion_count = move_to_recycle_with_companions(
                    original_source_video, original_source_subs,
                    video_exts, sub_exts, recycle_dir,
                    reason="source_cleanup", task_id=task.get("task_id", ""),
                    source_dir=source_dir, import_roots=self._get_allowed_dirs(),
                    allowed_base_dirs=allowed_dirs,
                )
                remove_empty_parent_dir(original_source_video, source_dir)
                msg = f"已将源文件移入回收站: {os.path.basename(original_source_video)}"
                if companion_count > 1:
                    msg += f" (含 {companion_count - 1} 个附属文件)"
                self._log("info", msg, task, "import")
        elif source_dir and original_source_video:
            self._log("info", f"源文件保留（配置: cleanup_source_after_done=false）: {os.path.basename(original_source_video)}", task, "import")

        temp_dir = self.config.get('temp_dir', '')
        if temp_video_path and temp_dir and str(temp_video_path).startswith(temp_dir):
            delete_source_files([temp_video_path], allowed_base_dirs=allowed_dirs)
            self._log("info", f"已清理临时文件: {os.path.basename(temp_video_path)}", task, "import")

        tid = task.get("task_id", "")
        db_update_task(self.task_manager.conn, tid,
                       import_video_path=task.get("import_video_path", ""),
                       import_success=1)

        import_subs = move_result.get('subtitles', [])
        subs = db_get_subtitles(self.task_manager.conn, tid)
        now = datetime.now().isoformat()
        for i, sub in enumerate(subs):
            import_path = import_subs[i] if i < len(import_subs) else ""
            db_update_subtitle(self.task_manager.conn, sub["id"],
                               status="SUCCESS", import_path=import_path,
                               confirm_status="CONFIRMED", completed_at=now)

        self._update_progress(task, 8, "import", 90)

    def _step_import_from_confirm(self, task: dict, original_source_video: str,
                                   original_source_subs: list):
        self._update_progress(task, 8, "import", 80)
        tid = task.get("task_id", "")
        self._log("info", f"确认入库: {task.get('source_filename', '')}", task, "import")

        manual_review = self.config.get("manual_review", {})
        temp_dir = self.config.get("temp_dir", "")
        temp_video_path = task.get("video_path", "")

        if manual_review.get("enabled", False):
            for ext in (".temp", ".tmp"):
                if temp_video_path.endswith(ext):
                    new_path = temp_video_path[:-len(ext)]
                    if os.path.exists(temp_video_path):
                        os.rename(temp_video_path, new_path)
                        task["video_path"] = new_path
                        temp_video_path = new_path
                    break

        self._step_dedup(task)
        self._step_rename(task)

        templates = self.config.get('filename_templates', {})
        allowed_dirs = self._get_allowed_dirs()

        move_result = move_to_import(
            temp_video_path,
            task.get("subtitle_files", []),
            task.get("import_path", ""),
            task.get("scrape_result", {}),
            templates,
            allowed_base_dirs=allowed_dirs,
        )

        task["video_path"] = move_result.get('video', temp_video_path)
        task["subtitle_files"] = move_result.get('subtitles', [])
        task["import_video_path"] = move_result.get('video', "")

        source_dir = self.config.get('source_dir', '')
        source_policy = self.config.get("source_policy", {})
        cleanup_source_after_done = source_policy.get("cleanup_source_after_done", False)

        if source_dir and original_source_video and cleanup_source_after_done:
            recycle_dir = source_policy.get("recycle_dir", "")
            if recycle_dir:
                from media_importer.core.safety import move_to_recycle_with_companions
                video_exts = [ext.lower() for ext in self.config.get('video_extensions', [])]
                sub_exts = [ext.lower() for ext in self.config.get('subtitle_extensions', [])]
                move_to_recycle_with_companions(
                    original_source_video, original_source_subs,
                    video_exts, sub_exts, recycle_dir,
                    reason="source_cleanup", task_id=task.get("task_id", ""),
                    source_dir=source_dir, import_roots=self._get_allowed_dirs(),
                    allowed_base_dirs=allowed_dirs,
                )
                remove_empty_parent_dir(original_source_video, source_dir)
        elif source_dir and original_source_video:
            self._log("info", f"源文件保留（配置: cleanup_source_after_done=false）: {os.path.basename(original_source_video)}", task, "import")

        if temp_dir and temp_video_path:
            delete_source_files([temp_video_path], allowed_base_dirs=allowed_dirs)

        db_update_task(self.task_manager.conn, tid,
                       import_video_path=task.get("import_video_path", ""),
                       import_success=1)

        import_subs = move_result.get('subtitles', [])
        subs = db_get_subtitles(self.task_manager.conn, tid)
        now = datetime.now().isoformat()
        for i, sub in enumerate(subs):
            import_path = import_subs[i] if i < len(import_subs) else ""
            db_update_subtitle(self.task_manager.conn, sub["id"],
                               status="SUCCESS", import_path=import_path,
                               confirm_status="CONFIRMED", completed_at=now)

        self._update_progress(task, 8, "import", 90)

    def _step_notify(self, task: dict):
        self._update_progress(task, 9, "notify", 95)

    def _step_record(self, task: dict):
        self._update_progress(task, 10, "record", 100)
        self.task_manager.update_task(task)
