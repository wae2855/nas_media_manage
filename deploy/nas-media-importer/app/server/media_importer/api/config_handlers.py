import os
import time

from media_importer.core.config_loader import load_config, mask_sensitive
from media_importer.api import globals
from media_importer.core.config_validator import validate_config
from media_importer.notify.hermes_hook import HermesNotifier
from media_importer.monitor.file_watcher import FileWatcher
from media_importer.core.metrics import get_metrics
from media_importer.core.db import list_tasks as db_list
from .utils import json_response


class ConfigHandlersMixin:
    def _config(self):
        masked = mask_sensitive(globals._config) if globals._config else {}
        prompts_data = self._load_prompts_for_ui()
        json_response(self, 200, data={"config": masked, "prompts": prompts_data})

    def _config_save(self, body: dict):

        if not body:
            json_response(self, 400, message="Empty config")
            return

        try:
            config_path = globals._config.get("_config_path") if globals._config else None
            if not config_path:
                json_response(self, 500, message="Config path not found")
                return

            from ruamel.yaml import YAML
            from ruamel.yaml.comments import CommentedMap
            from ruamel.yaml.scalarstring import SingleQuotedScalarString, DoubleQuotedScalarString

            yaml = YAML()
            yaml.preserve_quotes = True
            yaml.width = 120

            with open(config_path, "r", encoding="utf-8") as f:
                config_doc = yaml.load(f)

            config_to_save = self._filter_sensitive_fields(body, config_doc)

            YAML_RESERVED_WORDS = {'true', 'false', 'yes', 'no', 'on', 'off', 'null', '~'}
            YAML_SPECIAL_CHARS = set('{}:#&*!|>\'\"\'')

            def _needs_quote(value):
                if not isinstance(value, str):
                    return False
                if value.lower() in YAML_RESERVED_WORDS:
                    return True
                if any(c in value for c in YAML_SPECIAL_CHARS):
                    return True
                if ' ' in value:
                    return True
                if value and value[0].isdigit():
                    try:
                        float(value)
                        return True
                    except ValueError:
                        pass
                return False

            def _quote_value(value):
                if isinstance(value, str) and _needs_quote(value):
                    return SingleQuotedScalarString(value)
                return value

            def _was_quoted(value):
                return isinstance(value, (SingleQuotedScalarString, DoubleQuotedScalarString))

            def _process_list(new_list, old_list=None):
                result = []
                for i, item in enumerate(new_list):
                    old_item = None
                    if old_list and i < len(old_list):
                        old_item = old_list[i]
                    if isinstance(item, dict):
                        old_dict = old_item if isinstance(old_item, (dict, CommentedMap)) else None
                        result.append(_process_dict(item, old_dict))
                    elif isinstance(item, str):
                        result.append(_quote_value(item))
                    elif isinstance(item, bool):
                        result.append(item)
                    else:
                        result.append(item)
                return result

            def _process_dict(new_dict, old_dict=None):
                result = CommentedMap()
                for k, v in new_dict.items():
                    old_val = None
                    if old_dict and k in old_dict:
                        old_val = old_dict[k]
                    if isinstance(v, dict):
                        old_sub = old_val if isinstance(old_val, (dict, CommentedMap)) else None
                        result[k] = _process_dict(v, old_sub)
                    elif isinstance(v, list):
                        old_sub_list = old_val if isinstance(old_val, list) else None
                        result[k] = _process_list(v, old_sub_list)
                    elif isinstance(v, str):
                        result[k] = _quote_value(v)
                    elif isinstance(v, bool):
                        result[k] = v
                    else:
                        result[k] = v
                return result

            def update_nested(target, source):
                for key, value in source.items():
                    if key == "_config_path":
                        continue
                    if key == "hooks":
                        continue
                    if isinstance(value, dict):
                        if key in target and isinstance(target.get(key), (dict, CommentedMap)):
                            update_nested(target[key], value)
                        else:
                            target[key] = _process_dict(value)
                    elif isinstance(value, list):
                        old_list = target.get(key) if isinstance(target, (dict, CommentedMap)) else None
                        target[key] = _process_list(value, old_list)
                    elif isinstance(value, str):
                        target[key] = _quote_value(value)
                    elif isinstance(value, bool):
                        target[key] = value
                    else:
                        target[key] = value

            update_nested(config_doc, config_to_save)

            def _normalize_quotes(doc):
                if isinstance(doc, (dict, CommentedMap)):
                    for key in list(doc.keys()):
                        value = doc[key]
                        if isinstance(value, bool):
                            doc[key] = value
                        elif isinstance(value, str) and not _was_quoted(value):
                            if _needs_quote(value):
                                doc[key] = SingleQuotedScalarString(value)
                        elif isinstance(value, list):
                            _normalize_list_quotes(value)
                        elif isinstance(value, (dict, CommentedMap)):
                            _normalize_quotes(value)

            def _normalize_list_quotes(lst):
                for i in range(len(lst)):
                    item = lst[i]
                    if isinstance(item, (dict, CommentedMap)):
                        _normalize_quotes(item)
                    elif isinstance(item, bool):
                        lst[i] = item
                    elif isinstance(item, str) and not _was_quoted(item):
                        if _needs_quote(item):
                            lst[i] = SingleQuotedScalarString(item)

            _normalize_quotes(config_doc)

            with open(config_path, "w", encoding="utf-8") as f:
                yaml.dump(config_doc, f)

            has_running_tasks = globals._global_task_manager and globals._global_task_manager.has_running_tasks()

            if has_running_tasks:

                globals._config_dirty = True
                json_response(self, 200, message="配置已保存到文件。当前有任务正在执行，任务完成后自动同步内存配置，或点击「重载配置」立即生效（可能影响正在执行的任务）")
            else:
                if isinstance(globals._config, dict):
                    self._update_config_safely(globals._config, body)
                recycle_dir = globals._config.get("source_policy", {}).get("recycle_dir", "")
                if recycle_dir and not os.path.exists(recycle_dir):
                    try:
                        os.makedirs(recycle_dir, exist_ok=True)
                    except OSError:
                        pass

                if "file_watcher" in body:
                    try:
                        self._reload_watcher()
                        json_response(self, 200, message="轮询监控配置已保存并立即生效")
                        return
                    except Exception as e:
                        globals._global_logger.error(f"文件监控配置更新后重启失败: {e}")

                json_response(self, 200, message="配置已保存并生效")
        except Exception as e:
            import traceback
            error_msg = f"保存配置失败: {e}\n{traceback.format_exc()}"
            json_response(self, 500, message=error_msg)

    def _config_save_section(self, body: dict):
        section = body.get("section", "")
        data = body.get("data", {})

        if not section or not data:
            json_response(self, 400, message="缺少 section 或 data 参数")
            return

        section_map = {
            "basic": ["source_dir", "temp_dir", "source_policy"],
            "path_rules": ["path_rules", "fallback_dir"],
            "import_options": ["manual_review", "duplicate_handling", "filename_templates"],
            "metadata.providers": ["metadata"],
            "llm": ["llm"],
            "server": ["server"],
            "hermes": ["hermes"],
            "file_watcher": ["file_watcher"],
            "advanced": ["log_dir", "task_queue"],
            "confidence": ["confidence"],
        }

        if section not in section_map:
            json_response(self, 400, message=f"未知的配置区块: {section}")
            return

        try:
            section_body = {}
            for key in section_map[section]:
                if key in data:
                    section_body[key] = data[key]

            if not section_body:
                json_response(self, 400, message="区块数据为空")
                return

            if section == "metadata.providers":
                self._merge_provider_sensitive_fields(section_body)

            self._config_save(section_body)
        except Exception as e:
            json_response(self, 500, message=f"保存区块配置失败: {str(e)}")

    def _merge_provider_sensitive_fields(self, section_body: dict):
        new_providers = []
        if isinstance(section_body.get("metadata"), dict):
            new_providers = section_body["metadata"].get("providers", [])
        if not new_providers:
            return
        existing_providers = globals._config.get("metadata", {}).get("providers", []) if globals._config else []
        legacy_configs = {}
        metadata = globals._config.get("metadata", {}) if globals._config else {}
        for ptype in set(p.get("type", "") for p in new_providers):
            legacy = metadata.get(ptype, {})
            if isinstance(legacy, dict) and legacy.get("api_key"):
                legacy_configs[ptype] = legacy
        for new_p in new_providers:
            ptype = new_p.get("type", "")
            existing_p = None
            for ep in existing_providers:
                if ep.get("type") == ptype:
                    existing_p = ep
                    break
            if not new_p.get("api_key") or new_p.get("api_key") == "***":
                if existing_p and existing_p.get("api_key") and existing_p.get("api_key") != "***":
                    new_p["api_key"] = existing_p["api_key"]
                elif ptype in legacy_configs and legacy_configs[ptype].get("api_key"):
                    new_p["api_key"] = legacy_configs[ptype]["api_key"]

    def _config_validate(self):
        try:
            results = validate_config(globals._config, test_llm=False, test_hermes=False)
            json_response(self, 200, data=results, message="配置验证完成: " + results['overall'])
        except Exception as e:
            json_response(self, 500, message="配置验证失败: " + str(e))

    def _config_reload(self):

        try:
            config_path = globals._config.get("_config_path") if globals._config else None
            new_config = load_config(config_path) if config_path else load_config()

            if globals._global_task_manager and globals._global_task_manager.has_running_tasks():
                json_response(self, 400, message="当前有任务正在执行，请等待任务完成后再重载配置")
                return

            globals._config.clear()
            globals._config.update(new_config)

            if globals._global_pipeline:
                globals._global_pipeline.config = globals._config
                from media_importer.scraper.llm_scraper import LLMScraper
                globals._global_pipeline.scraper = LLMScraper(globals._config)
                globals._global_pipeline.copier = type(globals._global_pipeline.copier)(globals._config.get('temp_dir', ''))

            hermes_cfg = globals._config.get("hermes", {})
            if hermes_cfg.get("enabled", False):
                globals._global_notifier = HermesNotifier(globals._config)
            else:
                globals._global_notifier = None

            if globals._global_pipeline:
                globals._global_pipeline.notifier = globals._global_notifier

            self._reload_watcher()

            json_response(self, 200, message="配置已重载并生效")
        except Exception as e:
            json_response(self, 500, message="配置重载失败: " + str(e))

    def _reload_watcher(self):

        if globals._global_watcher:
            globals._global_watcher.stop()
            globals._global_watcher = None

        watcher_cfg = globals._config.get("file_watcher", {})
        if watcher_cfg.get("enabled", False):
            def on_new_files(new_files):
                if globals._global_pipeline and not globals._global_pipeline.is_paused():
                    try:
                        globals._global_pipeline.run_all()
                    except Exception as e:
                        globals._global_logger.error("批量处理异常: " + str(e))

            globals._global_watcher = FileWatcher(globals._config, on_new_files=on_new_files, logger=globals._global_logger)
            globals._global_watcher.start()
            globals._global_logger.info("文件监控已应用新配置并重启: "
                                f"enabled={watcher_cfg.get('enabled')}, "
                                f"poll_interval={watcher_cfg.get('poll_interval')}s")
        else:
            globals._global_logger.info("文件监控已停用（配置 enabled=false）")

    def _config_test_llm(self, body: dict):
        base_url = body.get("base_url", "")
        api_key = body.get("api_key", "")
        model = body.get("model", "")
        provider = body.get("provider", "openai")

        if not api_key or self._is_masked_value(api_key):
            api_key = self._get_real_config_value("llm", "api_key")
            if not api_key:
                json_response(self, 200, data={"success": False, "message": "API Key 未配置"})
                return

        if not base_url or self._is_masked_value(base_url):
            base_url = self._get_real_config_value("llm", "base_url")
            if not base_url:
                json_response(self, 200, data={"success": False, "message": "API 地址未配置"})
                return

        if not model:
            model = self._get_real_config_value("llm", "model")
            if not model:
                json_response(self, 200, data={"success": False, "message": "模型名称未配置"})
                return

        try:
            from media_importer.core.config_validator import test_llm_api
            ok, msg = test_llm_api(base_url, api_key, model, timeout=15)
            json_response(self, 200, data={"success": ok, "message": msg})
        except Exception as e:
            json_response(self, 200, data={"success": False, "message": "测试异常: " + str(e)})

    def _config_test_hermes(self, body: dict):
        base_url = body.get("base_url", "")
        route_name = body.get("route_name", "")
        secret = body.get("secret", "")

        if not base_url or self._is_masked_value(base_url):
            base_url = self._get_real_config_value("hermes", "webhook", "base_url")
        if not route_name:
            route_name = self._get_real_config_value("hermes", "webhook", "route_name")
        if not secret or self._is_masked_value(secret):
            secret = self._get_real_config_value("hermes", "webhook", "secret")

        if not base_url:
            json_response(self, 200, data={"success": False, "message": "Webhook 地址未配置"})
            return

        if not route_name:
            json_response(self, 200, data={"success": False, "message": "路由名称未配置"})
            return

        try:
            from media_importer.core.config_validator import test_hermes_webhook
            ok, msg = test_hermes_webhook(base_url, route_name, secret, timeout=15)
            json_response(self, 200, data={"success": ok, "message": msg})
        except Exception as e:
            json_response(self, 200, data={"success": False, "message": "测试异常: " + str(e)})

    _tmdb_genres_cache = None
    _tmdb_genres_cache_time = 0
    _TMDB_GENRES_CACHE_TTL = 3600

    def _tmdb_genres_list(self):
        import time
        now = time.time()
        if (ConfigHandlersMixin._tmdb_genres_cache is not None
                and now - ConfigHandlersMixin._tmdb_genres_cache_time < ConfigHandlersMixin._TMDB_GENRES_CACHE_TTL):
            json_response(self, 200, data=ConfigHandlersMixin._tmdb_genres_cache)
            return

        api_key = self._get_real_config_value("metadata", "tmdb", "api_key")
        if not api_key:
            json_response(self, 400, message="TMDB API Key 未配置，请先在配置面板中填写 API Key")
            return

        try:
            from media_importer.scraper.tmdb_client import TMDbClient
            client = TMDbClient(api_key)
            raw = client.get_genre_list()

            movie_genres = raw.get("movie", [])
            tv_genres = raw.get("tv", [])

            GENRE_GROUP_MAP = {
                28: "动作/冒险", 12: "动作/冒险", 10759: "动作/冒险", 37: "动作/冒险",
                27: "恐怖/悬疑", 9648: "恐怖/悬疑", 53: "恐怖/悬疑", 10758: "恐怖/悬疑",
                878: "科幻/奇幻", 14: "科幻/奇幻", 10765: "科幻/奇幻",
                10752: "战争/军事", 10768: "战争/军事",
                35: "喜剧",
                18: "剧情/情感", 10749: "剧情/情感", 80: "剧情/情感", 36: "剧情/情感",
                10751: "剧情/情感", 10766: "剧情/情感", 10770: "剧情/情感",
                99: "纪录/纪实",
                16: "动画",
                10402: "音乐/演出",
                10762: "儿童/家庭",
                10763: "电视节目", 10764: "电视节目", 10767: "电视节目",
                10760: "其他", 10769: "其他",
            }

            NAME_ZH_MAP = {
                28: "动作", 12: "冒险", 16: "动画", 35: "喜剧", 80: "犯罪",
                99: "纪录片", 18: "剧情", 14: "奇幻", 36: "历史", 10402: "音乐",
                878: "科幻", 10749: "爱情", 53: "惊悚", 10752: "战争", 37: "西部",
                27: "恐怖", 9648: "悬疑", 10759: "动作冒险", 10765: "科幻/奇幻",
                10766: "肥皂剧", 10768: "战争政治", 10758: "恐怖/悬疑",
                10762: "儿童", 10763: "新闻", 10764: "真人秀", 10767: "脱口秀",
                10760: "短剧", 10769: "海外剧", 10770: "电视电影", 10751: "家庭",
            }

            seen_ids = set()
            combined = []
            for g in movie_genres:
                gid = g.get("id")
                if gid in seen_ids:
                    continue
                seen_ids.add(gid)
                en_name = g.get("name", "")
                zh_name = NAME_ZH_MAP.get(gid, en_name)
                group = GENRE_GROUP_MAP.get(gid, "其他")
                is_both = any(tg.get("id") == gid for tg in tv_genres)
                combined.append({
                    "id": gid,
                    "name": f"{zh_name} ({en_name})",
                    "type": "both" if is_both else "movie",
                    "group": group,
                })
            for g in tv_genres:
                gid = g.get("id")
                if gid in seen_ids:
                    continue
                seen_ids.add(gid)
                en_name = g.get("name", "")
                zh_name = NAME_ZH_MAP.get(gid, en_name)
                group = GENRE_GROUP_MAP.get(gid, "其他")
                combined.append({
                    "id": gid,
                    "name": f"{zh_name} ({en_name})",
                    "type": "tv",
                    "group": group,
                })

            cache_data = {"movie": movie_genres, "tv": tv_genres, "combined": combined}
            ConfigHandlersMixin._tmdb_genres_cache = cache_data
            ConfigHandlersMixin._tmdb_genres_cache_time = now

            json_response(self, 200, data=cache_data)
        except Exception as e:
            json_response(self, 503, message=f"获取 TMDB 类型列表失败: {str(e)}")

    def _config_test_tmdb(self, body: dict):
        api_key = body.get("api_key", "")

        if not api_key or self._is_masked_value(api_key):
            api_key = self._get_real_config_value("metadata", "tmdb", "api_key")
            if not api_key:
                json_response(self, 200, data={"success": False, "message": "API Key 未配置"})
                return

        try:
            from media_importer.scraper.tmdb_client import TMDbClient
            client = TMDbClient(api_key)
            ok = client.test_connection()
            msg = "连接成功" if ok else "连接失败，请检查 API Key 是否正确"
            json_response(self, 200, data={"success": ok, "message": msg})
        except Exception as e:
            json_response(self, 200, data={"success": False, "message": "测试异常: " + str(e)})

    def _tmdb_preview(self, body: dict):
        query = (body or {}).get("query", "").strip()
        media_type = (body or {}).get("type", "movie")

        if not query:
            json_response(self, 400, message="请输入影视名称")
            return

        api_key = self._get_real_config_value("metadata", "tmdb", "api_key")
        if not api_key:
            json_response(self, 400, message="TMDB API Key 未配置，请先在配置面板中填写 API Key")
            return

        try:
            from media_importer.scraper.tmdb_client import TMDbClient, TMDbError
            client = TMDbClient(api_key)

            if media_type == "tv":
                search_result = client.search_tv(query)
                if not search_result:
                    json_response(self, 200, data={"found": False, "message": "未找到匹配的电视剧"})
                    return
                tmdb_id = search_result.get("id")
                details = client.get_tv_details(tmdb_id)
            else:
                search_result = client.search_movie(query)
                if not search_result:
                    json_response(self, 200, data={"found": False, "message": "未找到匹配的电影"})
                    return
                tmdb_id = search_result.get("id")
                details = client.get_movie_details(tmdb_id)

            preview = {
                "found": True,
                "type": media_type,
                "id": tmdb_id,
                "title": details.get("title") or details.get("name", ""),
                "original_title": details.get("original_title") or details.get("original_name", ""),
                "release_date": details.get("release_date") or details.get("first_air_date", ""),
                "overview": details.get("overview", ""),
                "genres": [{"id": g.get("id"), "name": g.get("name")} for g in details.get("genres", [])],
                "production_countries": [{"iso_3166_1": c.get("iso_3166_1"), "name": c.get("name")} for c in details.get("production_countries", [])],
                "origin_country": details.get("origin_country", []),
                "original_language": details.get("original_language", ""),
                "vote_average": details.get("vote_average", 0),
                "popularity": details.get("popularity", 0),
                "poster_path": details.get("poster_path", ""),
                "raw": details,
            }
            json_response(self, 200, data=preview)
        except TMDbError as e:
            json_response(self, 503, message=f"TMDB API 调用失败: {str(e)}")
        except Exception as e:
            json_response(self, 500, message=f"预览异常: {str(e)}")

    def _tmdb_search(self, body: dict):
        query = (body or {}).get("query", "").strip()
        media_type = (body or {}).get("type", "movie")
        language = (body or {}).get("language", "").strip() or None

        if not query:
            json_response(self, 400, message="请输入影视名称")
            return

        api_key = self._get_real_config_value("metadata", "tmdb", "api_key")
        if not api_key:
            json_response(self, 400, message="TMDB API Key 未配置")
            return

        try:
            from media_importer.scraper.tmdb_client import TMDbClient, TMDbError
            client = TMDbClient(api_key)

            if media_type == "tv":
                search_result = client.search_tv_list(query, language=language)
            else:
                search_result = client.search_movie_list(query, language=language)

            results = search_result.get("results", [])[:10]
            items = []
            for r in results:
                item = {
                    "id": r.get("id"),
                    "title": r.get("title") or r.get("name", ""),
                    "original_title": r.get("original_title") or r.get("original_name", ""),
                    "release_date": r.get("release_date") or r.get("first_air_date", ""),
                    "vote_average": r.get("vote_average", 0),
                    "poster_path": r.get("poster_path", ""),
                    "overview": (r.get("overview", "") or "")[:100],
                    "genre_ids": r.get("genre_ids", []),
                    "media_type": media_type,
                }
                items.append(item)

            json_response(self, 200, data={
                "total_results": search_result.get("total_results", 0),
                "items": items,
            })
        except TMDbError as e:
            json_response(self, 503, message=f"TMDB API 调用失败: {str(e)}")
        except Exception as e:
            json_response(self, 500, message=f"搜索异常: {str(e)}")

    def _tmdb_details(self, body: dict):
        tmdb_id = (body or {}).get("id")
        media_type = (body or {}).get("type", "movie")

        if not tmdb_id:
            json_response(self, 400, message="请提供 TMDB ID")
            return

        api_key = self._get_real_config_value("metadata", "tmdb", "api_key")
        if not api_key:
            json_response(self, 400, message="TMDB API Key 未配置")
            return

        try:
            from media_importer.scraper.tmdb_client import TMDbClient, TMDbError
            client = TMDbClient(api_key)

            if media_type == "tv":
                details = client.get_tv_details(int(tmdb_id))
            else:
                details = client.get_movie_details(int(tmdb_id))

            json_response(self, 200, data={
                "found": True,
                "type": media_type,
                "details": details,
            })
        except TMDbError as e:
            json_response(self, 503, message=f"TMDB API 调用失败: {str(e)}")
        except Exception as e:
            json_response(self, 500, message=f"详情获取异常: {str(e)}")

    def _scrape_preview(self, body: dict):
        filename = (body or {}).get("filename", "").strip()

        if not filename:
            json_response(self, 400, message="请输入视频文件名")
            return

        import time
        import logging
        from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeout
        from media_importer.scraper.llm_scraper import LLMScraper
        from media_importer.scraper.metadata_scraper import MetadataScraper
        from media_importer.scraper.confidence_engine import FilenameCleaner
        from media_importer.scraper.providers import create_providers

        logger = globals._global_logger
        cleaner = FilenameCleaner()
        clean_result = cleaner.clean(filename)

        ai_result = None
        provider_ai_result = None
        ai_elapsed = 0
        provider_ai_elapsed = 0
        providers = create_providers(globals._config)
        provider_enabled = bool(providers)
        preview_timeout = 60

        if logger:
            logger.info(f"[scrape_preview] 开始: filename={filename}, provider_enabled={provider_enabled}")

        def _run_ai_only():
            try:
                if logger:
                    logger.info("[scrape_preview] 纯AI刮削开始")
                llm_scraper = LLMScraper(globals._config)
                t0 = time.time()
                result = llm_scraper.scrape(filename)
                elapsed = round(time.time() - t0, 2)
                if logger:
                    logger.info(f"[scrape_preview] 纯AI刮削完成: {elapsed}s")
                return result, elapsed
            except Exception as e:
                if logger:
                    logger.error(f"[scrape_preview] 纯AI刮削异常: {e}")
                return {"error": str(e)}, 0

        def _run_provider_ai():
            try:
                if logger:
                    logger.info("[scrape_preview] Provider+AI刮削开始")
                metadata_scraper = MetadataScraper(globals._config)
                conn = getattr(globals._global_task_manager, 'conn', None) if globals._global_task_manager else None
                t0 = time.time()
                result = metadata_scraper.scrape(filename, conn=conn)
                elapsed = round(time.time() - t0, 2)
                if logger:
                    logger.info(f"[scrape_preview] Provider+AI刮削完成: {elapsed}s")
                return result, elapsed
            except Exception as e:
                if logger:
                    logger.error(f"[scrape_preview] Provider+AI刮削异常: {e}")
                return {"error": str(e)}, 0

        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = {}
            futures['ai'] = executor.submit(_run_ai_only)
            if provider_enabled:
                futures['provider'] = executor.submit(_run_provider_ai)

            for key, future in futures.items():
                try:
                    result, elapsed = future.result(timeout=preview_timeout)
                    if key == 'ai':
                        ai_result = result
                        ai_elapsed = elapsed
                    else:
                        provider_ai_result = result
                        provider_ai_elapsed = elapsed
                except FuturesTimeout:
                    if logger:
                        logger.warning(f"[scrape_preview] {key} 超时 ({preview_timeout}s)")
                    if key == 'ai':
                        ai_result = {"error": f"纯 AI 刮削超时（{preview_timeout} 秒），请检查 LLM 连接配置"}
                    else:
                        provider_ai_result = {"error": f"Provider+AI 刮削超时（{preview_timeout} 秒），可能原因：元数据源 API 不可达或 LLM 响应过慢，请参考「纯 AI 刮削」结果"}
                except Exception as e:
                    if logger:
                        logger.error(f"[scrape_preview] {key} 异常: {e}")
                    if key == 'ai':
                        ai_result = {"error": str(e)}
                    else:
                        provider_ai_result = {"error": str(e)}

        if logger:
            logger.info(f"[scrape_preview] 完成: ai={ai_elapsed}s, provider_ai={provider_ai_elapsed}s")

        json_response(self, 200, data={
            "filename": filename,
            "clean_result": {
                "clean_title": clean_result.clean_title,
                "year": clean_result.year,
                "season": clean_result.season,
                "episode": clean_result.episode,
                "method": clean_result.method,
                "removed_items": clean_result.removed_items,
            },
            "ai_only": ai_result,
            "ai_only_elapsed": ai_elapsed,
            "provider_ai": provider_ai_result,
            "provider_ai_elapsed": provider_ai_elapsed,
        })

    def _config_check_permission(self, body: dict):
        try:
            from media_importer.monitor.permission_checker import check_config_permissions
            cfg_to_check = body if body else (globals._config or {})
            result = check_config_permissions(cfg_to_check)
            json_response(self, 200, data=result, message="权限检测完成")
        except Exception as e:
            json_response(self, 500, message=f"权限检测异常: {e}")

    def _path_test(self, body: dict):
        try:
            path = (body or {}).get("path", "").strip()
            need_write = bool((body or {}).get("need_write", True))
            if not path:
                json_response(self, 400, message="path 参数必填")
                return
            from media_importer.monitor.permission_checker import check_path_permission, get_current_user
            result = check_path_permission(path, need_write=need_write)
            result["user"] = get_current_user()
            json_response(self, 200, data=result, message=result["message"])
        except Exception as e:
            json_response(self, 500, message=f"路径测试异常: {e}")

    def _watcher_status(self):
        if not globals._global_watcher:
            json_response(self, 200, data={"enabled": False, "status": "not_started"})
            return
        json_response(self, 200, data={
            "enabled": globals._global_watcher.is_running(),
            "poll_interval": globals._global_watcher.poll_interval,
            "status": "running" if globals._global_watcher.is_running() else "stopped"
        })

    def _watcher_control(self, query):
        action = query.get("action", [None])[0]
        if not globals._global_watcher:
            json_response(self, 400, message="Watcher not initialized")
            return

        if action == "pause":
            globals._global_watcher.stop()
            json_response(self, 200, message="轮询已暂停")
        elif action == "resume":
            globals._global_watcher.start()
            json_response(self, 200, message="轮询已恢复")
        elif action == "status":
            self._watcher_status()
        else:
            json_response(self, 400, message="Invalid action: use pause/resume/status")

    def _health(self):
        from media_importer.core.safety import check_write_permission
        checks = {}
        overall = "ok"

        try:
            source_dir = globals._config.get("source_dir", "")
            if os.path.isdir(source_dir):
                if os.access(source_dir, os.R_OK):
                    checks["source_dir"] = "ok"
                else:
                    checks["source_dir"] = "no_read_permission"
            else:
                checks["source_dir"] = "error"
        except Exception:
            checks["source_dir"] = "error"
            overall = "degraded"

        try:
            temp_dir = globals._config.get("temp_dir", "")
            if os.path.isdir(temp_dir):
                ok, _ = check_write_permission(temp_dir)
                checks["temp_dir"] = "ok" if ok else "no_write_permission"
            else:
                checks["temp_dir"] = "error"
        except Exception:
            checks["temp_dir"] = "error"
            overall = "degraded"

        try:
            log_dir = globals._config.get("log_dir", "") if globals._config else ""
            checks["log_dir_path"] = log_dir
            if os.path.isdir(log_dir):
                ok, _ = check_write_permission(log_dir)
                checks["log_dir"] = "ok" if ok else "no_write_permission"
            else:
                checks["log_dir"] = "error"
        except Exception:
            checks["log_dir"] = "error"
            overall = "degraded"

        try:
            llm_config = globals._config.get("llm", {})
            api_key = llm_config.get("api_key", "")
            checks["llm_api"] = "ok" if api_key else "skipped"
        except Exception:
            checks["llm_api"] = "skipped"

        try:
            hermes_enabled = globals._config.get("hermes", {}).get("enabled", False)
            checks["hermes"] = "ok" if hermes_enabled else "disabled"
        except Exception:
            checks["hermes"] = "disabled"

        try:
            disk_check_dir = globals._config.get("temp_dir", "/tmp")
            stat = os.statvfs(disk_check_dir)
            free_gb = stat.f_bavail * stat.f_frsize / (1024**3)
            checks["disk_space"] = "ok" if free_gb > 1 else "low"
        except Exception:
            checks["disk_space"] = "error"
            overall = "degraded"

        if "error" in checks.values():
            overall = "degraded"

        json_response(self, 200, data={
            "status": overall,
            "checks": checks,
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S")
        }, message=f"Health check: {overall}")

    def _metrics(self):
        m = get_metrics()
        counts = globals._global_task_manager.count_by_status() if globals._global_task_manager else {}
        json_response(self, 200, data={
            **m.to_dict(),
            "queue_by_status": counts
        })

    def _logs(self, query: dict):
        limit = int(query.get("limit", [100])[0])
        task_id = query.get("task_id", [None])[0]

        if globals._global_logger:
            result_lines = globals._global_logger.get_recent_logs(limit=limit, task_id=task_id)
        else:
            result_lines = []

        json_response(self, 200, data={"logs": result_lines})

    def _list_tasks(self, query):
        from media_importer.core.db import VALID_STATUSES
        status = query.get("status", [None])[0]
        limit = int(query.get("limit", [20])[0])
        offset = int(query.get("offset", [0])[0])
        show_all = query.get("all", ["false"])[0].lower() == "true"
        page = query.get("page", [None])[0]
        format_mode = query.get("format", ["json"])[0].lower()

        if status:
            status = status.strip().upper()
        if status and status != "ALL" and status not in VALID_STATUSES:
            if globals._global_logger:
                globals._global_logger.warning(f"Invalid status filter: {status}, VALID_STATUSES={VALID_STATUSES}")
            json_response(self, 400, message=f"Invalid status: {status}")
            return

        if status and status == "ALL":
            status = None

        if page is not None:
            page_num = int(page)
            page_size = limit
        else:
            page_num = (offset // limit) + 1 if limit > 0 else 1
            page_size = limit

        rows, total, total_pages = db_list(
            globals._global_task_manager.conn,
            page=page_num,
            page_size=page_size,
            status=status,
        )
        counts = globals._global_task_manager.count_by_status()
        active_count = sum(counts.get(s, 0) for s in ("PENDING", "PROCESSING", "FAILED", "CONFIRMING"))

        json_data = {
            "tasks": rows,
            "total": total,
            "total_pages": total_pages,
            "page": page_num,
            "page_size": page_size,
            "active_count": active_count,
            "by_status": counts,
        }

        if format_mode == "text":
            from .utils import format_tasks_to_text
            text_output = format_tasks_to_text(json_data)
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Content-Length", str(len(text_output.encode("utf-8"))))
            self.send_header("Connection", "close")
            self.end_headers()
            self.wfile.write(text_output.encode("utf-8"))
            self.wfile.flush()
        else:
            json_response(self, 200, data=json_data)

    def _get_real_config_value(self, *path) -> str:
        if globals._config:
            value = globals._config
            for key in path:
                if isinstance(value, dict) and key in value:
                    value = value[key]
                else:
                    value = ""
                    break
            if isinstance(value, str) and not self._is_masked_value(value) and value:
                return value
        if len(path) >= 3 and path[0] == "metadata":
            provider_type = path[1]
            provider_field = path[2] if len(path) == 3 else None
            if provider_field:
                providers = globals._config.get("metadata", {}).get("providers", []) if globals._config else []
                for p in providers:
                    if p.get("type") == provider_type:
                        val = p.get(provider_field, "")
                        if val and isinstance(val, str) and not self._is_masked_value(val):
                            return val
                        break
        config_path = globals._config.get("_config_path") if globals._config else None
        if not config_path or not os.path.isfile(config_path):
            return ""
        try:
            import yaml as _yaml
            with open(config_path, "r", encoding="utf-8") as f:
                file_config = _yaml.safe_load(f)
            value = file_config
            for key in path:
                if isinstance(value, dict) and key in value:
                    value = value[key]
                else:
                    if len(path) >= 3 and path[0] == "metadata":
                        provider_type = path[1]
                        provider_field = path[2] if len(path) == 3 else None
                        if provider_field:
                            providers = file_config.get("metadata", {}).get("providers", []) if isinstance(file_config, dict) else []
                            for p in providers:
                                if isinstance(p, dict) and p.get("type") == provider_type:
                                    val = p.get(provider_field, "")
                                    if val and isinstance(val, str):
                                        return val
                                    break
                    return ""
            return value if isinstance(value, str) else str(value) if value else ""
        except Exception:
            return ""

    def _filter_sensitive_fields(self, body: dict, original_config: dict) -> dict:
        import copy
        filtered = copy.deepcopy(body)

        sensitive_fields = [
            ("server", "api_key"),
            ("llm", "api_key"),
            ("hermes", "webhook", "secret"),
        ]

        for field_path in sensitive_fields:
            current_value = self._get_nested_value(filtered, field_path)
            if current_value and self._is_masked_value(current_value):
                self._delete_nested_path(filtered, field_path)

        if "hooks" in filtered:
            del filtered["hooks"]

        return filtered

    def _get_nested_value(self, obj: dict, path: tuple) -> any:
        current = obj
        for key in path:
            if isinstance(current, dict) and key in current:
                current = current[key]
            else:
                return None
        return current

    def _delete_nested_path(self, obj: dict, path: tuple):
        if len(path) == 0:
            return

        current = obj
        for key in path[:-1]:
            if isinstance(current, dict) and key in current:
                current = current[key]
            else:
                return

        if len(path) == 1:
            if path[0] in current:
                del current[path[0]]
        else:
            last_key = path[-1]
            if last_key in current:
                del current[last_key]

    def _is_masked_value(self, value: str) -> bool:
        if not isinstance(value, str):
            return False
        return "***" in value

    def _update_config_safely(self, target: dict, source: dict):
        if not isinstance(target, dict) or not isinstance(source, dict):
            return
        for key, value in source.items():
            if key == "_config_path":
                continue
            if key == "hooks":
                continue
            if isinstance(value, dict) and isinstance(target.get(key), dict):
                self._update_config_safely(target[key], value)
            elif isinstance(value, str) and self._is_masked_value(value):
                pass
            else:
                target[key] = value
