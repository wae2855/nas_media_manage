import os
from typing import Optional

from media_importer.features.import_flow.services import ReviewDecisionService
from media_importer.features.import_flow.utils import PipelineError
from media_importer.features.scraping.match_engine import MatchEngine
from media_importer.infrastructure.db import get_enabled_dimensions
from media_importer.infrastructure.db import (
    list_all_tasks as db_list_all_tasks,
)
from media_importer.infrastructure.db import (
    update_task as db_update_task,
)


class ScrapeStepsMixin:
    def _load_manual_provider_binding(self, task: dict) -> dict | None:
        binding = task.get("manual_provider_binding") or {}
        if not isinstance(binding, dict) or not binding.get("item_id"):
            return None
        from media_importer.features.tasks.search_service import load_provider_candidate

        selected = load_provider_candidate(
            self.config,
            self.task_manager.conn,
            provider_type=str(binding.get("provider_type") or ""),
            item_id=str(binding.get("item_id") or ""),
            media_type=str(binding.get("media_type") or ""),
            language=str(binding.get("language") or "") or None,
        )
        result = dict(selected["scrape_result"])
        dimensions = dict(selected.get("dimensions") or {})
        dim_sources = dict(selected.get("dim_sources") or {})
        if str(binding.get("media_type")) == "tv":
            for name in ("season", "episode"):
                value = binding.get(name)
                if value is not None:
                    result[name] = value
                    dimensions[name] = value
                    dim_sources[name] = "file:filename"
        result.update({
            "provider_type": str(binding.get("provider_type") or ""),
            "provider_id": str(binding.get("item_id") or ""),
            "media_type": str(binding.get("media_type") or ""),
            "match_level": "AUTO_PASS",
            "match_concerns": [],
            "tier_short_reason": "已使用人工确认的作品",
            "selected_candidate": {
                "provider_type": str(binding.get("provider_type") or ""),
                "provider_id": str(binding.get("item_id") or ""),
                "title": result.get("title_cn") or result.get("title_en", ""),
                "year": result.get("year"),
                "media_type": str(binding.get("media_type") or ""),
            },
            "dimensions": dimensions,
            "scrape_trace": {
                "manual_selected": True,
                "manual_binding_consumed": True,
                "provider_type": str(binding.get("provider_type") or ""),
                "provider_id": str(binding.get("item_id") or ""),
                "language": selected.get("language", ""),
                "provider_dimensions": selected.get("dimensions", {}),
                "dimension_mapping_evidence": (
                    result.get("scrape_trace", {}).get(
                        "dimension_mapping_evidence", {}
                    )
                    if isinstance(result.get("scrape_trace"), dict)
                    else {}
                ),
                "dim_sources": dim_sources,
            },
        })
        task["_manual_binding_consumed"] = True
        self._log(
            "info",
            f"使用人工确认作品继续处理: {result.get('title_cn') or result.get('title_en')}",
            task,
            "scrape",
        )
        return result

    def _step_scrape(self, task: dict):
        self._update_progress(task, 3, "scrape", 35)
        self._log("info", f"刮削元数据: {task.get('source_filename', '')}", task, "scrape")

        file_dimensions = {}
        try:
            from media_importer.features.scraping import get_dimensions_for_file
            from media_importer.features.scraping.file_analyzer import analyze_file
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
            result = self._load_manual_provider_binding(task)
            if result is None:
                # 先由统一匹配器决定作品身份，再按同一候选抓取完整元数据，
                # 避免刮削器与匹配器各搜一次后给出不同结论。
                match_engine = MatchEngine(
                    self.scraper.config if hasattr(self.scraper, 'config') else {}
                )
                video_path = task.get("video_path") or task.get("source_path", "")
                providers = self.scraper.providers if hasattr(self.scraper, 'providers') else []
                match_result = match_engine.match(
                    filename=task.get("source_filename", ""),
                    providers=providers,
                    conn=self.task_manager.conn,
                    video_path=video_path,
                )
                result = self.scraper.scrape(
                    task.get("source_filename", ""),
                    task.get("subtitle_files", []),
                    conn=self.task_manager.conn,
                    video_path=video_path,
                    match_result=match_result,
                )
                match_dict = match_result.to_dict()
            else:
                match_dict = {
                    "match_level": "AUTO_PASS",
                    "concerns": [],
                    "match_tier": 0,
                    "tier_short_reason": "已使用人工确认的作品",
                    "ai_reason": "",
                    "selected_candidate": result.get("selected_candidate"),
                    "manual_selected": True,
                }
            task["scrape_result"] = result

            result['match_level'] = match_dict['match_level']
            result['match_concerns'] = match_dict['concerns']
            result['match_trace'] = match_dict
            result['match_tier'] = match_dict.get('match_tier', 0)
            result['tier_short_reason'] = match_dict.get('tier_short_reason', '')
            result['ai_reason'] = match_dict.get('ai_reason', '')
            result['selected_candidate'] = match_dict.get('selected_candidate')

            # 当 LLM 刮削未返回 Provider 详情时，从 selected_candidate 回填
            selected = match_dict.get('selected_candidate')
            if selected and selected.get('provider_type') and selected.get('provider_id'):
                if not result.get('provider_type'):
                    result['provider_type'] = selected['provider_type']
                    result['provider_id'] = selected['provider_id']
                if not result.get('title_cn'):
                    result['title_cn'] = selected.get('title', '')
                if not result.get('title_en'):
                    result['title_en'] = selected.get('title', '')
                if not result.get('year'):
                    result['year'] = selected.get('year')

            media_type = result.get('media_type', '')
            if (
                media_type
                and media_type.lower() in ('tv', 'series')
                and not task.get("_manual_binding_consumed")
            ):
                series_dims = self._get_series_dimensions(task, result)
                if series_dims:
                    original_dims = dict(result.get('dimensions', {}))
                    result.setdefault('dimensions', {}).update(series_dims)
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

            # 使用正式维度解析服务，基于显式来源记录
            from media_importer.features.scraping.dimension_resolution import resolve_dimension_sources
            scrape_trace = result.get('scrape_trace', {})
            if not isinstance(scrape_trace, dict):
                scrape_trace = {}

            # 从 scrape_trace 中提取显式来源记录
            provider_dim_names = set(scrape_trace.get("provider_dimensions", {}).keys()) if isinstance(scrape_trace.get("provider_dimensions"), dict) else set()
            # 如果 scrape_trace 未提供显式来源，从 provider_dimensions 推断
            if not provider_dim_names:
                provider_dims = result.get("provider_dimensions", {})
                if isinstance(provider_dims, dict):
                    provider_dim_names = set(provider_dims.keys())

            resolution = resolve_dimension_sources(
                scrape_result=result,
                file_dimensions=file_dimensions,
                provider_type=result.get("provider_type", "tmdb"),
                provider_dim_names=provider_dim_names,
            )
            dim_sources = resolution.dim_sources
            task["dim_sources"] = dim_sources

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
                match_level=result.get('match_level', ''),
                match_concerns=match_concerns_json,
                match_trace=_json.dumps(result.get('match_trace', {}), ensure_ascii=False) if result.get('match_trace') else '',
                scrape_trace=scrape_trace,
                provider_type=result.get('provider_type', ''),
                provider_id=result.get('provider_id', ''),
                thumbnail_path=thumbnail_path,
                dim_sources=dim_sources,
                manual_provider_binding={},
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
            elif match_level == 'NEEDS_CONFIRM':
                detail_parts.append("匹配=需确认")
            else:
                detail_parts.append("匹配=需确认")
            dims_str = ', '.join(f'{k}={v}' for k, v in scrape_dimensions.items())
            if dims_str:
                detail_parts.append(f"维度=[{dims_str}]")
            self._log("info", f"刮削结果: {', '.join(detail_parts)}", task, "scrape")

        except PipelineError:
            raise
        except Exception as e:
            raise PipelineError(f"刮削失败: {e}") from e

        self._update_progress(task, 3, "scrape", 50)

    def _step_validate(self, task: dict):
        self._update_progress(task, 4, "validate", 52)
        self._log("info", f"验证刮削结果: {task.get('source_filename', '')}", task, "validate")

        scraped = task.get("scrape_result", {})
        if not scraped:
            raise PipelineError("刮削结果为空，无法验证")

        enabled_dims = get_enabled_dimensions(self.task_manager.conn) if hasattr(self.task_manager, "conn") else []
        decision = ReviewDecisionService().evaluate(
            scraped,
            required_dimensions=self.config.get("required_dimensions") or [],
            dim_labels={d["name"]: (d.get("label") or d["name"]) for d in enabled_dims},
        )

        if decision.action == "confirm":
            task["_needs_confirm"] = True
            if decision.concerns:
                existing = scraped.get('match_concerns', [])
                existing_keys = {(c.get('code', ''), c.get('message', '')) for c in existing if isinstance(c, dict)}
                for c in decision.concerns:
                    key = (c.get('code', ''), c.get('message', ''))
                    if key not in existing_keys:
                        existing.append(c)
                scraped['match_concerns'] = existing
                self._log("warn", f"需要人工确认，共 {len(existing)} 条关注点", task, "validate")
            else:
                self._log("warn", "需要人工确认", task, "validate")
            return

        if decision.action == "needs_review":
            task["_needs_review"] = True
            task["skip_reason"] = "需要人工审核"
            self._log("warn", "需要人工审核", task, "validate")
            return

        if decision.action == "failed":
            task["_force_fail"] = True
            task["_fail_reason"] = "匹配失败，无法识别"
            self._log("warn", "匹配失败，无法识别", task, "validate")
            return

        if decision.warnings:
            self._log("warn", f"刮削警告: {'; '.join(decision.warnings)}", task, "validate")
        self._update_progress(task, 4, "validate", 55)

    def _get_series_dimensions(self, task: dict, scrape_result: dict) -> dict:
        cached_dims = self._find_cached_series_dims(task, scrape_result)
        if cached_dims is not None:
            return cached_dims
        return {}

    def _find_cached_series_dims(self, task: dict, scrape_result: dict) -> Optional[dict]:
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
                return {
                    name: value
                    for name, value in t_dims.items()
                    if name not in {"season", "episode"}
                }
        return None
