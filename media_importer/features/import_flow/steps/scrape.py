import os
from media_importer.core.db import (
    update_task as db_update_task,
    list_all_tasks as db_list_all_tasks,
)
from media_importer.features.import_flow.services import ReviewDecisionService
from media_importer.features.scraping import LLMScrapeError
from media_importer.features.scraping.match_engine import MatchEngine
from media_importer.features.import_flow.utils import PipelineError, _extract_series_name


class ScrapeStepsMixin:
    def _step_scrape(self, task: dict):
        self._update_progress(task, 3, "scrape", 35)
        self._log("info", f"刮削元数据: {task.get('source_filename', '')}", task, "scrape")

        file_dimensions = {}
        try:
            from media_importer.features.scraping import get_dimensions_for_file
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

            # 三级匹配引擎：运行 MatchEngine 获取 match_level、match_concerns、match_trace
            match_engine = MatchEngine(self.scraper.config if hasattr(self.scraper, 'config') else {})
            video_path = task.get("video_path") or task.get("source_path", "")
            providers = self.scraper.providers if hasattr(self.scraper, 'providers') else []
            match_result = match_engine.match(
                filename=task.get("source_filename", ""),
                providers=providers,
                conn=self.task_manager.conn,
                video_path=video_path,
            )
            match_dict = match_result.to_dict()
            result['match_level'] = match_dict['match_level']
            result['match_concerns'] = match_dict['concerns']
            result['match_trace'] = match_dict

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
            task["match_level"] = result.get('match_level', '')
            task["match_concerns"] = result.get('match_concerns', [])
            task["provider_type"] = result.get('provider_type', '')
            task["provider_id"] = result.get('provider_id', '')

            # 下载海报缩略图到 resource_dir/thumbnail/
            poster_url = result.get('poster_url', '')
            thumbnail_path = ""
            if poster_url:
                try:
                    from media_importer.features.scraping.thumbnail_downloader import download_thumbnail
                    config = getattr(self, 'config', None) or {}
                    title = result.get('title_cn', '') or result.get('title_en', '') or result.get('title', '')
                    provider_id = result.get('provider_id', '')
                    saved = download_thumbnail(poster_url, config, title=title, provider_id=provider_id)
                    if saved:
                        thumbnail_path = saved
                        self._log("info", f"海报缩略图已保存: {os.path.basename(saved)}", task, "scrape")
                except Exception as e:
                    self._log("warning", f"海报缩略图下载失败（不影响刮削）: {e}", task, "scrape")

            scrape_trace = result.get('scrape_trace')
            if scrape_trace:
                task["scrape_trace"] = scrape_trace
            task["thumbnail_path"] = thumbnail_path

            # 序列化 match_concerns 为 JSON
            import json as _json
            match_concerns_json = _json.dumps(
                result.get('match_concerns', []),
                ensure_ascii=False
            ) if result.get('match_concerns') else ''

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
                match_level=result.get('match_level', ''),
                match_concerns=match_concerns_json,
                match_trace=_json.dumps(result.get('match_trace', {}), ensure_ascii=False) if result.get('match_trace') else '',
                scrape_trace=scrape_trace,
                provider_type=result.get('provider_type', ''),
                provider_id=result.get('provider_id', ''),
                thumbnail_path=thumbnail_path,
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
            match_level = result.get('match_level', '')
            if match_level == 'AUTO_PASS':
                detail_parts.append("匹配=自动通过")
            elif match_level == 'CONTEXT_PASS':
                detail_parts.append("匹配=AI辅助通过")
            elif match_level == 'NEEDS_CONFIRM':
                detail_parts.append("匹配=需确认")
            else:
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

        decision = ReviewDecisionService().evaluate(
            scraped,
            self.scraper.confidence_engine if hasattr(self.scraper, 'confidence_engine') else None,
        )

        if decision.action == "confirm":
            task["_needs_confirm"] = True
            task["_confirm_reason"] = decision.reason
            self._log("warn", decision.reason, task, "validate")
            return

        if decision.action == "needs_review":
            task["skip_reason"] = decision.reason
            task["_needs_review"] = True
            self._log("warn", f"需要人工审核: {decision.reason}", task, "validate")
            return

        if decision.action == "failed":
            task["_force_fail"] = True
            task["_fail_reason"] = decision.reason
            self._log("warn", task["_fail_reason"], task, "validate")
            return

        if decision.warnings:
            self._log("warn", f"刮削警告: {'; '.join(decision.warnings)}", task, "validate")
        self._update_progress(task, 4, "validate", 55)

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
