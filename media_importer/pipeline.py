#!/usr/bin/env python3
import os
import re
import time
import threading
from task_manager import Task, TaskManager
from file_scanner import scan_source_dir
from file_copier import FileCopier
from llm_scraper import LLMScraper, LLMScrapeError
from classifier import classify
from dedup_checker import check_duplicate
from file_mover import apply_filename_template, move_to_import, delete_source_files, delete_source_with_companions, remove_empty_parent_dir, cleanup_source_non_media
from hooks import HookRunner


def _extract_series_name(filename: str) -> str:
    name = os.path.splitext(filename)[0]
    name = re.sub(r'[._]', ' ', name)
    name = re.sub(r'\b[Ss]\d{1,2}[Ee]\d{1,2}\b.*$', '', name)
    name = re.sub(r'\b[Ss]\d{1,2}\b.*$', '', name)
    name = re.sub(r'\b(?:2160p|1080p|720p|480p|4K|UHD|HDR)\b.*$', '', name, flags=re.IGNORECASE)
    name = re.sub(r'\b(?:WEB|HDTV|BluRay|BDRip|WEBRip|WEB-DL|REMUX)\b.*$', '', name, flags=re.IGNORECASE)
    name = re.sub(r'\b(?:x264|x265|HEVC|H\.?264|H\.?265|AAC|DTS|DD|ATMOS)\b.*$', '', name, flags=re.IGNORECASE)
    name = name.strip(' -.')
    return name


PIPELINE_STEPS = [
    (1, "scan", "扫描源目录"),
    (2, "copy", "复制到临时目录"),
    (3, "scrape", "AI刮削元数据"),
    (4, "validate", "验证刮削结果"),
    (5, "classify", "分类匹配路径"),
    (6, "dedup", "同名文件检测"),
    (7, "rename", "生成目标文件名"),
    (8, "import", "入库移动文件"),
    (9, "notify", "发送通知"),
    (10, "record", "记录处理结果")
]


class PipelineRunner:
    def __init__(self, config: dict, task_manager: TaskManager,
                 metrics=None, logger=None, notifier=None):
        self.config = config
        self.task_manager = task_manager
        self.metrics = metrics
        self.logger = logger
        self.notifier = notifier
        self.hooks = HookRunner(config, logger)
        self._paused = threading.Event()

        self.scraper = LLMScraper(config)
        self.copier = FileCopier(config.get('temp_dir', ''))
        
        # 错误通知去重
        self._last_notified_error = None
        self._last_notified_time = 0
        self._error_notify_cooldown = 300  # 5分钟内相同系统错误只通知一次

    def pause(self):
        self._paused.set()

    def resume(self):
        self._paused.clear()

    def is_paused(self) -> bool:
        return self._paused.is_set()

    def _log(self, level: str, message: str, task: Task = None, step: str = ""):
        if self.logger:
            if task:
                self.logger.step_log(task.task_id, step, level, message)
            else:
                log_method = getattr(self.logger, level.lower(), self.logger.info)
                log_method(message)

    def _update_progress(self, task: Task, step_num: int, step_name: str,
                         percentage: int, **kwargs):
        self.task_manager.update_progress(
            task, step_num, step_name, percentage, **kwargs
        )

    def _is_system_error(self, error_message: str) -> bool:
        """判断是否是系统级错误（如API配置错误、网络错误等）"""
        system_error_keywords = [
            "API", "api", "认证", "密钥", "key", "连接", "网络",
            "timeout", "timeout", "配置", "config", "401", "403", "404"
        ]
        error_lower = error_message.lower()
        return any(keyword in error_lower for keyword in system_error_keywords)
    
    def _notify_program_error(self, error_type: str, error_message: str, extra_data: dict = None):
        """智能发送程序错误通知，避免通知风暴"""
        if not self.notifier:
            return
        
        current_time = time.time()
        error_key = f"{error_type}:{error_message[:100]}"  # 用错误前100字符作为标识
        
        # 检查是否在冷却期内
        if (self._last_notified_error == error_key and 
            current_time - self._last_notified_time < self._error_notify_cooldown):
            self._log("debug", f"跳过重复系统错误通知: {error_type}", None, "notify")
            return
        
        # 发送通知
        try:
            self.notifier.notify_program_error(error_type, error_message, extra_data)
            self._last_notified_error = error_key
            self._last_notified_time = current_time
            self._log("info", f"发送系统错误通知: {error_type}", None, "notify")
        except Exception as e:
            self._log("warn", f"系统错误通知发送失败: {e}", None, "notify")

    def _notify(self, event_type: str, task: Task):
        if self.notifier and self.notifier.should_notify(event_type):
            try:
                self.notifier.notify(event_type, task)
            except Exception as e:
                self._log("warn", f"通知发送失败: {e}", task, "notify")

    def scan_and_create_tasks(self) -> list:
        source_dir = self.config.get('source_dir', '')
        groups = scan_source_dir(source_dir, self.config)

        tasks = []
        for group in groups:
            video_path = group['video']
            video_file = os.path.basename(video_path)
            subtitle_files = group.get('subtitles', [])
            file_size_mb = 0
            try:
                file_size_mb = os.path.getsize(video_path) / (1024 * 1024)
            except OSError:
                pass

            task = self.task_manager.create_task(
                video_path=video_path,
                video_file=video_file,
                subtitle_files=subtitle_files,
                file_size_mb=file_size_mb
            )
            tasks.append(task)

        self._log("info", f"扫描完成，创建 {len(tasks)} 个任务")
        return tasks

    def process_one(self, task: Task) -> bool:
        original_source_video = task.video_path
        original_source_subs = list(task.subtitle_files)
        temp_video_path_for_cleanup = None
        
        try:
            task.transition_to("PROCESSING")
            self.task_manager.update_task(task)
        except ValueError as e:
            self._log("error", f"任务状态转换失败: {e}", task)
            return False

        try:
            self.hooks.run_before_process(task.to_dict())
            self._step_copy(task)
            temp_video_path_for_cleanup = task.video_path
            self._step_scrape(task)
            self._step_validate(task)
            self._step_classify(task)
            self._step_dedup(task)
            self._step_rename(task)
            self._step_import(task, original_source_video, original_source_subs)
            self._step_notify(task)
            self._step_record(task)

            task.transition_to("SUCCESS")
            self.task_manager.update_task(task)
            self.hooks.run_after_success(task.to_dict())
            if self.metrics:
                self.metrics.record_task_complete("success")
            self._log("info", f"任务处理成功: {task.video_file}", task)
            return True

        except PipelineSkipError as e:
            task.transition_to("SKIPPED")
            task.error_message = str(e)
            self.task_manager.update_task(task)
            if self.metrics:
                self.metrics.record_task_complete("skipped")
            self._log("info", f"任务跳过: {task.video_file} - {e}", task)
            self._cleanup_temp_on_failure(task, temp_video_path_for_cleanup)
            
            delete_after_process = self.config.get('source_file_handling', {}).get('delete_after_process', True)
            if delete_after_process:
                source_dir = self.config.get('source_dir', '')
                if source_dir and original_source_video and original_source_video.startswith(source_dir):
                    video_exts = [ext.lower() for ext in self.config.get('video_extensions', [])]
                    sub_exts = [ext.lower() for ext in self.config.get('subtitle_extensions', [])]
                    companion_count = delete_source_with_companions(
                        original_source_video, original_source_subs,
                        video_exts, sub_exts, allowed_base_dirs=[source_dir]
                    )
                    msg = f"已清理源目录文件: {os.path.basename(original_source_video)}"
                    if companion_count > 0:
                        msg += f" (含 {companion_count} 个附属文件)"
                    self._log("info", msg, task, "cleanup")
                    remove_empty_parent_dir(original_source_video, source_dir)
            else:
                self._log("info", f"保留源目录文件（配置为不删除）: {os.path.basename(original_source_video)}", task, "cleanup")
            
            return True

        except Exception as e:
            error_msg = str(e)
            task.transition_to("FAILED")
            task.error_message = error_msg
            self.task_manager.update_task(task)
            self.hooks.run_after_failure(task.to_dict())
            if self.metrics:
                self.metrics.record_task_complete("failed")
            self._log("error", f"任务失败: {task.video_file} - {e}", task)
            self._cleanup_temp_on_failure(task, temp_video_path_for_cleanup)
            
            # 检查是否是系统级错误，需要通知
            if self._is_system_error(error_msg):
                self._notify_program_error(
                    "system_error",
                    error_msg,
                    {"video_file": task.video_file, "task_id": task.task_id}
                )
            
            return False

    def _cleanup_temp_on_failure(self, task: Task, temp_video_path: str):
        """失败时清理 temp 目录文件，保留 source 让用户查看"""
        temp_dir = self.config.get('temp_dir', '')
        source_dir = self.config.get('source_dir', '')
        allowed_dirs = [
            source_dir,
            temp_dir,
        ]
        
        files_to_delete = []
        
        if temp_video_path and temp_dir and temp_video_path.startswith(temp_dir):
            files_to_delete.append(temp_video_path)
            for sub in task.subtitle_files:
                if temp_dir in sub:
                    files_to_delete.append(sub)
        
        if files_to_delete:
            delete_source_files(files_to_delete, allowed_base_dirs=allowed_dirs)
            self._log("info", f"已清理 temp 目录失败文件: {len(files_to_delete)} 个", task, "cleanup")

    def run_all(self):
        self._log("info", "开始批量处理")
        
        source_dir = self.config.get("source_dir", "")
        delete_after_process = self.config.get('source_file_handling', {}).get('delete_after_process', True)

        if delete_after_process and source_dir:
            video_exts = [ext.lower() for ext in self.config.get('video_extensions', [])]
            sub_exts = [ext.lower() for ext in self.config.get('subtitle_extensions', [])]
            deleted_files, deleted_dirs = cleanup_source_non_media(source_dir, video_exts, sub_exts)
            if deleted_files > 0 or deleted_dirs > 0:
                self._log("info", f"源目录预清理: 删除 {deleted_files} 个非媒体文件, {deleted_dirs} 个空目录")

        pending_tasks = self.task_manager.get_next_pending()
        
        if pending_tasks is None:
            self.scan_and_create_tasks()
            all_tasks = self.task_manager.list_tasks(limit=10000)
            video_count = sum(1 for t in all_tasks if t.status == "PENDING")
            subtitle_count = sum(len(t.subtitle_files) for t in all_tasks if t.status == "PENDING")
            if video_count > 0 and self.notifier:
                self.notifier.notify_batch_start(source_dir, video_count, subtitle_count)
        else:
            all_tasks = self.task_manager.list_tasks(status="PENDING", limit=10000)
            if self.notifier:
                video_count = len(all_tasks)
                subtitle_count = sum(len(t.subtitle_files) for t in all_tasks)
                self.notifier.notify_batch_start(source_dir, video_count, subtitle_count)
        
        batch_stats = {"PROCESSING": 0, "SUCCESS": 0, "FAILED": 0, "SKIPPED": 0,
                        "total": 0, "subtitle_count": 0, "video_count": 0}
        
        while not self._paused.is_set():
            task = self.task_manager.get_next_pending()
            if task is None:
                break
            batch_stats["total"] += 1
            batch_stats["subtitle_count"] += len(task.subtitle_files)
            batch_stats["video_count"] += 1
            self.process_one(task)
            final_status = task.status
            batch_stats[final_status] = batch_stats.get(final_status, 0) + 1

        batch_stats["total_files"] = batch_stats["video_count"] + batch_stats["subtitle_count"]

        if self.notifier and self.notifier.should_notify("batch_complete"):
            try:
                self.notifier.notify_batch_complete([], summary=batch_stats)
            except Exception:
                pass

        self._log("info", "批量处理完成")

    def _step_copy(self, task: Task):
        self._update_progress(task, 2, "copy", 20)
        self._log("info", f"复制文件: {task.video_file}", task, "copy")

        def progress_cb(copied, total):
            pct = int(20 + (copied / total) * 10) if total > 0 else 25
            self._update_progress(task, 2, "copy", pct,
                                  bytes_copied=copied, total_bytes=total)

        def heartbeat_cb():
            """心跳回调：更新任务时间戳，防止超时被认为是死锁"""
            self.task_manager.update_task(task)

        try:
            copied = self.copier.copy_to_temp(
                task.video_path, task.subtitle_files, 
                progress_cb, heartbeat_cb, heartbeat_interval=30
            )
            task.video_path = copied[0]
            task.subtitle_files = copied[1:] if len(copied) > 1 else []
        except IOError as e:
            raise PipelineError(f"复制失败: {e}")

        self._update_progress(task, 2, "copy", 30)

    def _step_scrape(self, task: Task):
        self._update_progress(task, 3, "scrape", 35)
        self._log("info", f"刮削元数据: {task.video_file}", task, "scrape")

        try:
            result = self.scraper.scrape(
                task.video_file, task.subtitle_files
            )
            task.scraped_info = result
            if self.metrics:
                self.metrics.record_llm_call(success=True)

            media_type = result.get('type', '')
            if media_type and media_type.lower() in ('tv', 'series'):
                series_dims = self._get_series_dimensions(task, result)
                if series_dims:
                    original_dims = dict(result.get('dimensions', {}))
                    result['dimensions'].update(series_dims)
                    task.scraped_info = result
                    changed = {k: f'{original_dims.get(k)} -> {v}' for k, v in series_dims.items() if original_dims.get(k) != v}
                    if changed:
                        changed_str = ', '.join(f'{k}={v}' for k, v in changed.items())
                        self._log("info", f"整剧维度覆盖: [{changed_str}]", task, "scrape")

            title_cn = result.get('title_cn') or ''
            title_en = result.get('title_en') or ''
            year = result.get('year') or ''
            confidence = result.get('confidence', 0)
            season = result.get('season')
            episode = result.get('episode')
            dims = result.get('dimensions', {})
            dims_str = ', '.join(f'{k}={v}' for k, v in dims.items()) if dims else ''

            detail_parts = []
            if title_cn:
                detail_parts.append(f"标题={title_cn}")
            if title_en:
                detail_parts.append(f"英文名={title_en}")
            if year:
                detail_parts.append(f"年份={year}")
            if media_type:
                detail_parts.append(f"类型={media_type}")
            if season:
                detail_parts.append(f"季={season}")
            if episode:
                detail_parts.append(f"集={episode}")
            detail_parts.append(f"置信度={confidence}")
            if dims_str:
                detail_parts.append(f"维度=[{dims_str}]")

            self._log("info", f"刮削结果: {', '.join(detail_parts)}", task, "scrape")

        except LLMScrapeError as e:
            if self.metrics:
                self.metrics.record_llm_call(success=False)
            raise PipelineError(f"刮削失败: {e}")

        self._update_progress(task, 3, "scrape", 50)

    def _step_validate(self, task: Task):
        self._update_progress(task, 4, "validate", 52)
        self._log("info", f"验证刮削结果: {task.video_file}", task, "validate")

        scraped = task.scraped_info
        missing_fields = []
        warnings = []

        title_cn = scraped.get('title_cn')
        title_en = scraped.get('title_en')
        year = scraped.get('year')
        media_type = scraped.get('type')
        confidence = scraped.get('confidence', 0)

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

        if year and (int(year) < 1900 or int(year) > 2030):
            warnings.append(f"年份异常: {year}")
            missing_fields.append(f"年份异常: {year}")

        if scraped.get('low_confidence'):
            if has_title and confidence >= 0.5:
                warnings.append(f"AI置信度偏低({confidence})，但标题已识别，继续处理")
            else:
                missing_fields.append("AI置信度过低")

        if missing_fields:
            error_msg = f"刮削信息不足，需要人工干预。缺失字段: {'; '.join(missing_fields)}"
            if warnings:
                error_msg += f"。警告: {'; '.join(warnings)}"
            raise PipelineError(error_msg)

        if warnings:
            self._log("warn", f"刮削警告: {'; '.join(warnings)}", task, "validate")

        self._update_progress(task, 4, "validate", 55)

    def _step_classify(self, task: Task):
        self._update_progress(task, 5, "classify", 56)
        self._log("info", f"分类匹配: {task.video_file}", task, "classify")

        path_rules = self.config.get('path_rules', [])
        dimensions = task.scraped_info.get('dimensions', {})

        dims_str = ', '.join(f'{k}={v}' for k, v in dimensions.items()) if dimensions else '无'
        self._log("info", f"文件维度: [{dims_str}]", task, "classify")

        import_path = classify(task.scraped_info, path_rules)
        if not import_path:
            rules_desc = []
            for i, rule in enumerate(path_rules):
                cond = rule.get('conditions', {})
                cond_str = ', '.join(f'{k}={v}' for k, v in cond.items())
                rules_desc.append(f"规则{i+1}: [{cond_str}]")
            self._log("error", f"无匹配规则。文件维度=[{dims_str}], 可用规则: {'; '.join(rules_desc) if rules_desc else '无规则配置'}", task, "classify")
            raise PipelineError(f"分类匹配失败，无匹配规则。维度=[{dims_str}]")

        self._log("info", f"匹配路径: {import_path}", task, "classify")

        if not os.path.isabs(import_path):
            project_root = os.path.dirname(
                os.path.dirname(os.path.abspath(self.config.get('_config_path', '')))
            )
            if project_root:
                import_path = os.path.join(project_root, import_path)

        task.import_path = import_path
        self._update_progress(task, 5, "classify", 60)

    def _get_series_dimensions(self, task: Task, scrape_result: dict) -> dict:
        cached_dims = self._find_cached_series_dims(task, scrape_result)
        if cached_dims is not None:
            return cached_dims

        series_name = _extract_series_name(task.video_file)
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
                self._log("info", f"整剧维度结果: [{', '.join(f'{k}={v}' for k, v in series_dims.items())}]", task, "scrape")
                return series_dims
        except LLMScrapeError as e:
            self._log("warn", f"整剧维度刮削失败，使用逐集结果: {e}", task, "scrape")
            if self.metrics:
                self.metrics.record_llm_call(success=False)

        return {}

    def _find_cached_series_dims(self, task: Task, scrape_result: dict) -> dict:
        title = scrape_result.get('title_cn', '') or scrape_result.get('title_en', '')
        if not title:
            return None

        if not hasattr(self, 'task_manager') or not self.task_manager:
            return None

        try:
            tasks = self.task_manager.list_all_tasks(limit=500)
        except Exception:
            return None

        for t in tasks:
            if t.task_id == task.task_id:
                continue
            if t.status not in ('SUCCESS', 'completed'):
                continue
            t_dims = t.scraped_info.get('dimensions', {})
            if t_dims.get('media_type') not in ('tv', 'TV', 'series'):
                continue
            t_title = t.scraped_info.get('title_cn', '') or t.scraped_info.get('title_en', '')
            if t_title and t_title == title:
                self._log("info", f"复用同剧缓存维度: {title}", task, "scrape")
                return t_dims

        return None

    def _get_import_root(self) -> str:
        path_rules = self.config.get('path_rules', [])
        templates = [r.get('template', '') for r in path_rules if r.get('template')]
        if not templates:
            return ''
        abs_templates = []
        for tpl in templates:
            if not os.path.isabs(tpl):
                project_root = os.path.dirname(
                    os.path.dirname(os.path.abspath(self.config.get('_config_path', '')))
                )
                if project_root:
                    tpl = os.path.join(project_root, tpl)
            abs_templates.append(os.path.normpath(tpl))
        if len(abs_templates) == 1:
            parts = abs_templates[0].split(os.sep)
            for i, p in enumerate(parts):
                if p.startswith('{'):
                    return os.sep.join(parts[:i]) if i > 0 else ''
            return abs_templates[0]
        prefix_parts = []
        split_templates = [t.split(os.sep) for t in abs_templates]
        min_len = min(len(t) for t in split_templates)
        for i in range(min_len):
            part = split_templates[0][i]
            if part.startswith('{'):
                break
            if all(t[i] == part for t in split_templates):
                prefix_parts.append(part)
            else:
                break
        return os.sep.join(prefix_parts) if prefix_parts else ''

    def _step_dedup(self, task: Task):
        self._update_progress(task, 6, "dedup", 65)
        self._log("info", f"同名检测: {task.video_file}", task, "dedup")

        strategy = self.config.get('duplicate_handling', {}).get('strategy', 'skip')
        import_root = self._get_import_root()
        dedup_search_dir = import_root if import_root else task.import_path
        dedup_result = check_duplicate(
            dedup_search_dir, task.scraped_info, strategy, task.video_path
        )

        if dedup_result['is_duplicate']:
            if strategy == 'skip':
                skip_msg = dedup_result.get('skip_message', 
                    f"同名文件已存在: {dedup_result.get('existing_file', 'unknown')}")
                raise PipelineSkipError(skip_msg)
            elif strategy == 'rename':
                task.final_filename = os.path.basename(
                    dedup_result['suggested_filename']
                )
            elif strategy == 'replace':
                self._log("info", f"替换模式: 将删除已存在文件 {dedup_result['existing_file']}", task, "dedup")
                if os.path.exists(dedup_result['existing_path']):
                    from safety import safe_delete
                    allowed_dirs = [task.import_path]
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
                        from safety import safe_delete
                        allowed_dirs = [task.import_path]
                        ok, msg = safe_delete(dedup_result['existing_path'], allowed_base_dirs=allowed_dirs)
                        if ok:
                            self._log("info", f"已删除已存在文件: {dedup_result['existing_file']}", task, "dedup")
                        else:
                            self._log("warning", f"删除文件失败: {msg}", task, "dedup")
                            raise PipelineError(f"无法删除已存在文件: {msg}")
                elif quality_decision == 'keep_existing':
                    skip_msg = dedup_result.get('skip_message', "质量优先: 保留已存在文件")
                    raise PipelineSkipError(skip_msg)

        self._update_progress(task, 6, "dedup", 70)

    def _step_rename(self, task: Task):
        self._update_progress(task, 7, "rename", 72)
        self._log("info", f"生成文件名: {task.video_file}", task, "rename")

        if not task.final_filename:
            templates = self.config.get('filename_templates', {})
            video_ext = os.path.splitext(task.video_path)[1]
            if task.scraped_info.get('type') == 'tv':
                template = templates.get('tv', '')
            else:
                template = templates.get('movie', '')
            task.final_filename = apply_filename_template(
                task.scraped_info, template, video_ext
            )

        self._update_progress(task, 7, "rename", 75)

    def _step_import(self, task: Task, original_source_video: str, original_source_subs: list):
        self._update_progress(task, 8, "import", 80)
        self._log("info", f"入库: {task.video_file}", task, "import")

        templates = self.config.get('filename_templates', {})
        temp_dir = self.config.get('temp_dir', '')
        allowed_dirs = [
            self.config.get('source_dir', ''),
            temp_dir,
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

        temp_video_path = task.video_path

        move_result = move_to_import(
            task.video_path, task.subtitle_files,
            task.import_path, task.scraped_info, templates,
            allowed_base_dirs=allowed_dirs
        )

        task.video_path = move_result['video']
        task.subtitle_files = move_result['subtitles']

        source_dir = self.config.get('source_dir', '')
        delete_after_process = self.config.get('source_file_handling', {}).get('delete_after_process', True)

        if delete_after_process and source_dir and original_source_video:
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
        elif not delete_after_process and source_dir and original_source_video:
            self._log("info", f"保留源目录文件（配置为不删除）: {os.path.basename(original_source_video)}", task, "import")

        if temp_video_path and temp_dir and temp_video_path.startswith(temp_dir):
            delete_source_files([temp_video_path], allowed_base_dirs=allowed_dirs)
            self._log("info", f"已清理临时文件: {os.path.basename(temp_video_path)}", task, "import")

        self._update_progress(task, 8, "import", 90)

    def _step_notify(self, task: Task):
        self._update_progress(task, 9, "notify", 95)

    def _step_record(self, task: Task):
        self._update_progress(task, 10, "record", 100)
        task.add_log("record", "INFO", f"处理完成: {task.final_filename}")
        self.task_manager.update_task(task)


class PipelineError(Exception):
    pass


class PipelineSkipError(Exception):
    pass
