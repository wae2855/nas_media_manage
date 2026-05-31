import os
from datetime import datetime
from media_importer.core.db import (
    update_task as db_update_task,
    list_all_tasks as db_list_all_tasks,
    get_subtitles_by_task as db_get_subtitles,
    update_subtitle as db_update_subtitle,
)
from media_importer.scraper.llm_scraper import LLMScrapeError
from media_importer.storage.classifier import classify, render_template
from media_importer.storage.dedup_checker import check_duplicate
from media_importer.storage.file_mover import apply_filename_template, move_to_import, delete_source_with_companions, delete_source_files, remove_empty_parent_dir
from .utils import PipelineError, PipelineSkipError, _extract_series_name


class StepsMixin:
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

    def _step_scrape(self, task: dict):
        self._update_progress(task, 3, "scrape", 35)
        self._log("info", f"刮削元数据: {task.get('source_filename', '')}", task, "scrape")

        file_dimensions = {}
        try:
            from media_importer.scraper.dimension_manager import get_dimensions_for_file
            from media_importer.storage.file_analyzer import analyze_file
            file_dims_config = get_dimensions_for_file(self.task_manager.conn)
            if file_dims_config:
                video_path = task.get("video_path") or task.get("source_path", "")
                if video_path and os.path.isfile(video_path):
                    file_dimensions = analyze_file(video_path, file_dims_config)
                    if file_dimensions:
                        fd_str = ', '.join(f'{k}={v["value"]}' for k, v in file_dimensions.items())
                        self._log("info", f"文件推导维度: [{fd_str}]", task, "scrape")
        except Exception as e:
            self._log("warning", f"文件维度分析失败（不影响刮削）: {e}", task, "scrape")

        try:
            result = self.scraper.scrape(
                task.get("source_filename", ""),
                task.get("subtitle_files", []),
                conn=self.task_manager.conn
            )
            task["scrape_result"] = result
            if self.metrics:
                self.metrics.record_llm_call(success=True)

            media_type = result.get('type', '')
            if media_type and media_type.lower() in ('tv', 'series'):
                series_dims = self._get_series_dimensions(task, result)
                if series_dims:
                    original_dims = dict(result.get('dimensions', {}))
                    result['dimensions'].update(series_dims)
                    task["scrape_result"] = result
                    changed = {k: f'{original_dims.get(k)} -> {v}'
                               for k, v in series_dims.items()
                               if original_dims.get(k) != v}
                    if changed:
                        changed_str = ', '.join(f'{k}={v}' for k, v in changed.items())
                        self._log("info", f"整剧维度覆盖: [{changed_str}]", task, "scrape")

            scrape_dimensions = result.get("dimensions", {})
            for dim_name, dim_info in file_dimensions.items():
                if dim_info.get('value') is not None:
                    scrape_dimensions[dim_name] = dim_info['value']
            result['dimensions'] = scrape_dimensions
            task["scrape_dimensions"] = scrape_dimensions
            task["scrape_title_cn"] = result.get('title_cn', '')
            task["scrape_title_en"] = result.get('title_en', '')
            task["scrape_year"] = result.get('year', '')
            task["scrape_media_type"] = media_type
            task["scrape_season"] = result.get('season', None)
            task["scrape_episode"] = result.get('episode', None)
            task["scrape_confidence"] = result.get('confidence', 0)

            scrape_trace = result.get('scrape_trace')
            if scrape_trace:
                task["scrape_trace"] = scrape_trace

            db_update_task(
                self.task_manager.conn, task.get("task_id", ""),
                scrape_result=result,
                scrape_dimensions=scrape_dimensions,
                scrape_title_cn=result.get('title_cn', ''),
                scrape_title_en=result.get('title_en', ''),
                scrape_year=result.get('year', ''),
                scrape_media_type=media_type,
                scrape_season=result.get('season', None),
                scrape_episode=result.get('episode', None),
                scrape_confidence=result.get('confidence', 0),
                scrape_trace=scrape_trace,
            )

            detail_parts = []
            if result.get('title_cn'):
                detail_parts.append(f"标题={result['title_cn']}")
            if result.get('title_en'):
                detail_parts.append(f"英文名={result['title_en']}")
            if result.get('year'):
                detail_parts.append(f"年份={result['year']}")
            if media_type:
                detail_parts.append(f"类型={media_type}")
            if result.get('season'):
                detail_parts.append(f"季={result['season']}")
            if result.get('episode'):
                detail_parts.append(f"集={result['episode']}")
            detail_parts.append(f"置信度={result.get('confidence', 0)}")
            dims_str = ', '.join(f'{k}={v}' for k, v in scrape_dimensions.items())
            if dims_str:
                detail_parts.append(f"维度=[{dims_str}]")
            self._log("info", f"刮削结果: {', '.join(detail_parts)}", task, "scrape")

        except LLMScrapeError as e:
            if self.metrics:
                self.metrics.record_llm_call(success=False)
            raise PipelineError(f"刮削失败: {e}")

        self._update_progress(task, 3, "scrape", 50)

    def _step_validate(self, task: dict):
        self._update_progress(task, 4, "validate", 52)
        self._log("info", f"验证刮削结果: {task.get('source_filename', '')}", task, "validate")

        scraped = task.get("scrape_result", {})
        if not scraped:
            raise PipelineError("刮削结果为空，无法验证")
        missing_fields = []
        warnings = []

        title_cn = scraped.get('title_cn')
        title_en = scraped.get('title_en')
        year = scraped.get('year')
        media_type = scraped.get('type')

        has_title = bool(title_cn or title_en)
        has_type = bool(media_type)
        has_year = bool(year)

        if not has_title:
            missing_fields.append("中文名(title_cn)和英文名(title_en)都缺失")
        if not has_type:
            missing_fields.append("媒体类型(type)缺失")
        if not has_year:
            if has_title and has_type:
                warnings.append(f"年份缺失(可接受，标题已识别: {title_cn or title_en})")
            else:
                missing_fields.append("年份(year)缺失")
        if title_cn and not title_en:
            warnings.append("缺少英文名(可接受)")
        if year:
            try:
                y = int(year)
                if y < 1900 or y > 2030:
                    warnings.append(f"年份异常: {year}")
                    missing_fields.append(f"年份异常: {year}")
            except ValueError:
                warnings.append(f"年份格式异常: {year}")

        if missing_fields:
            confirm_reason = f"刮削信息不足，需要人工确认。缺失字段: {'; '.join(missing_fields)}"
            if warnings:
                confirm_reason += f"。警告: {'; '.join(warnings)}"
            task["_needs_confirm"] = True
            task["_confirm_reason"] = confirm_reason
            self._log("warn", confirm_reason, task, "validate")
            return

        confidence = scraped.get('confidence', 0)
        gate_blocked = scraped.get('confidence_gate_blocked')
        search_conf = scraped.get('confidence_search', 0)
        data_gate = scraped.get('confidence_data_gate', 1)

        level = self.scraper.confidence_engine.get_confidence_level(confidence, gate_blocked)

        if level == "NEEDS_REVIEW" and gate_blocked:
            blocked_dim = gate_blocked.get("dim_name", "未知维度")
            blocked_source = gate_blocked.get("source", "未知来源")
            skip_reason = f"来源不信任: {blocked_dim} 的来源 {blocked_source} 未在信任列表中"
            gate_reason = gate_blocked.get("reason", "")
            if gate_reason:
                skip_reason += f" ({gate_reason})"
            task["status"] = "NEEDS_REVIEW"
            task["skip_reason"] = skip_reason
            task["_needs_review"] = True
            self._log("warn", f"数据门控拦截({confidence:.3f}, 搜索={search_conf:.3f}, 门控={data_gate:.1f}): {skip_reason}", task, "validate")
            return

        if level == "FAILED":
            task["_force_fail"] = True
            task["_fail_reason"] = f"置信度过低({confidence:.3f}, 搜索={search_conf:.3f})"
            self._log("warn", task["_fail_reason"], task, "validate")
            return

        if level == "NEEDS_REVIEW":
            confirm_reason = f"置信度偏低({confidence:.3f}, 搜索={search_conf:.3f})，需要人工审核"
            if warnings:
                confirm_reason += f"。警告: {'; '.join(warnings)}"
            task["_needs_confirm"] = True
            task["_confirm_reason"] = confirm_reason
            self._log("warn", confirm_reason, task, "validate")
            return

        if level == "CONFIRMING":
            confirm_reason = f"置信度{confidence:.3f}(搜索={search_conf:.3f})，需要人工确认"
            if warnings:
                confirm_reason += f"。警告: {'; '.join(warnings)}"
            task["_needs_confirm"] = True
            task["_confirm_reason"] = confirm_reason
            self._log("warn", confirm_reason, task, "validate")
            return

        if warnings:
            self._log("warn", f"刮削警告: {'; '.join(warnings)}", task, "validate")
        self._update_progress(task, 4, "validate", 55)

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

    def _get_series_dimensions(self, task: dict, scrape_result: dict) -> dict:
        cached_dims = self._find_cached_series_dims(task, scrape_result)
        if cached_dims is not None:
            return cached_dims
        series_name = _extract_series_name(task.get("source_filename", ""))
        if not series_name:
            return {}
        title_from_scrape = scrape_result.get('title_cn', '') or scrape_result.get('title_en', '')
        query_name = title_from_scrape if title_from_scrape else series_name
        self._log("info", f"按剧名整体刮削维度: {query_name}", task, "scrape")
        try:
            series_result = self.scraper.scrape_series(query_name)
            if self.metrics:
                self.metrics.record_llm_call(success=True)
            series_dims = series_result.get('dimensions', {})
            if series_dims:
                self._log("info",
                          f"整剧维度结果: [{', '.join(f'{k}={v}' for k, v in series_dims.items())}]",
                          task, "scrape")
                return series_dims
        except LLMScrapeError as e:
            self._log("warn", f"整剧维度刮削失败，使用逐集结果: {e}", task, "scrape")
            if self.metrics:
                self.metrics.record_llm_call(success=False)
        return {}

    def _find_cached_series_dims(self, task: dict, scrape_result: dict) -> dict:
        title = scrape_result.get('title_cn', '') or scrape_result.get('title_en', '')
        if not title:
            return None
        try:
            tasks = db_list_all_tasks(self.task_manager.conn, limit=500)
        except Exception:
            return None
        tid = task.get("task_id", "")
        for t in tasks:
            if t.get("task_id") == tid:
                continue
            if t.get("status") not in ('SUCCESS',):
                continue
            t_result = t.get("scrape_result", {})
            if isinstance(t_result, str):
                continue
            t_dims = t_result.get('dimensions', {}) if isinstance(t_result, dict) else {}
            if t_dims.get('media_type') not in ('tv', 'TV', 'series'):
                continue
            t_title = t_result.get('title_cn', '') or t_result.get('title_en', '')
            if t_title and t_title == title:
                self._log("info", f"复用同剧缓存维度: {title}", task, "scrape")
                return t_dims
        return None

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
                self._log("info", f"替换模式: 将删除已存在文件 {dedup_result['existing_file']}", task, "dedup")
                if os.path.exists(dedup_result['existing_path']):
                    from media_importer.core.safety import safe_delete
                    allowed_dirs = [task.get("import_path", "")]
                    ok, msg = safe_delete(dedup_result['existing_path'], allowed_base_dirs=allowed_dirs)
                    if ok:
                        self._log("info", f"已删除已存在文件: {dedup_result['existing_file']}", task, "dedup")
                    else:
                        self._log("warning", f"删除文件失败: {msg}", task, "dedup")
                        raise PipelineError(f"无法删除已存在文件: {msg}")
            elif strategy == 'quality':
                quality_decision = dedup_result.get('quality_decision')
                if quality_decision == 'replace':
                    self._log("info", f"质量优先: 新文件质量更高，将替换已存在文件", task, "dedup")
                    if os.path.exists(dedup_result['existing_path']):
                        from media_importer.core.safety import safe_delete
                        allowed_dirs = [task.get("import_path", "")]
                        ok, msg = safe_delete(dedup_result['existing_path'], allowed_base_dirs=allowed_dirs)
                        if ok:
                            self._log("info", f"已删除已存在文件: {dedup_result['existing_file']}", task, "dedup")
                        else:
                            self._log("warning", f"删除文件失败: {msg}", task, "dedup")
                            raise PipelineError(f"无法删除已存在文件: {msg}")
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

        if source_dir and original_source_video:
            video_exts = [ext.lower() for ext in self.config.get('video_extensions', [])]
            sub_exts = [ext.lower() for ext in self.config.get('subtitle_extensions', [])]
            companion_count = delete_source_with_companions(
                original_source_video, original_source_subs,
                video_exts, sub_exts, allowed_base_dirs=allowed_dirs
            )
            remove_empty_parent_dir(original_source_video, source_dir)
            msg = f"已清理源目录文件: {os.path.basename(original_source_video)}"
            if companion_count > 0:
                msg += f" (含 {companion_count} 个附属文件)"
            self._log("info", msg, task, "import")

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
        if source_dir and original_source_video:
            video_exts = [ext.lower() for ext in self.config.get('video_extensions', [])]
            sub_exts = [ext.lower() for ext in self.config.get('subtitle_extensions', [])]
            delete_source_with_companions(
                original_source_video, original_source_subs,
                video_exts, sub_exts, allowed_base_dirs=allowed_dirs
            )
            remove_empty_parent_dir(original_source_video, source_dir)

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
