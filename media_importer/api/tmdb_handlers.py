import time
import logging
import os
import sqlite3
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeout
from media_importer.api import globals
from .utils import json_response


class TMDbHandlersMixin:
    _tmdb_genres_cache = None
    _tmdb_genres_cache_time = 0
    _TMDB_GENRES_CACHE_TTL = 3600

    def _tmdb_genres_list(self):
        now = time.time()
        if (TMDbHandlersMixin._tmdb_genres_cache is not None
                and now - TMDbHandlersMixin._tmdb_genres_cache_time < TMDbHandlersMixin._TMDB_GENRES_CACHE_TTL):
            json_response(self, 200, data=TMDbHandlersMixin._tmdb_genres_cache)
            return

        api_key = self._get_real_config_value("metadata", "tmdb", "api_key")
        if not api_key:
            json_response(self, 400, message="TMDB API Key 未配置，请先在配置面板中填写 API Key")
            return

        try:
            from media_importer.features.scraping import TMDbClient
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
            TMDbHandlersMixin._tmdb_genres_cache = cache_data
            TMDbHandlersMixin._tmdb_genres_cache_time = now

            json_response(self, 200, data=cache_data)
        except Exception as e:
            json_response(self, 503, message=f"获取 TMDB 类型列表失败: {str(e)}")

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
            from media_importer.features.scraping import TMDbClient, TMDbError
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
            from media_importer.features.scraping import TMDbClient, TMDbError
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
            from media_importer.features.scraping import TMDbClient, TMDbError
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

        from media_importer.features.scraping import MetadataScraper
        from media_importer.features.scraping import FilenameCleaner
        from media_importer.features.scraping.match_engine import MatchEngine
        from media_importer.features.providers import create_providers

        logger = globals._global_logger
        cleaner = FilenameCleaner()
        clean_result = cleaner.clean(filename)
        providers = create_providers(globals._config)

        if logger:
            logger.info(f"[scrape_preview] 开始: filename={filename}, provider_enabled={bool(providers)}")

        # 单一刮削流程
        scrape_result = {}
        scrape_elapsed = 0
        conn = None
        try:
            metadata_scraper = MetadataScraper(globals._config)
            db_path = os.path.join(
                globals._config.get("_data_dir",
                    os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "..", "data")),
                "tasks.db")
            conn = sqlite3.connect(db_path, check_same_thread=False)
            conn.row_factory = sqlite3.Row
            t0 = time.time()
            scrape_result = metadata_scraper.scrape(filename, conn=conn) or {}
            scrape_elapsed = round(time.time() - t0, 2)
        except Exception as e:
            if logger:
                logger.error(f"[scrape_preview] 刮削异常: {e}")
            scrape_result = {"error": str(e)}
        finally:
            if conn:
                try:
                    conn.close()
                except Exception:
                    pass

        # 三级匹配引擎
        match_engine = MatchEngine(globals._config or {})
        match_result = match_engine.match(
            filename=filename,
            providers=providers,
            conn=None,
            video_path=filename,
        )
        match_dict = match_result.to_dict()

        # 入库路径计算
        import_path = ""
        used_fallback = False
        matched_rule = None
        try:
            from media_importer.features.import_flow.classify import classify
            dims = scrape_result.get("dimensions", {})
            media_type = scrape_result.get("type") or scrape_result.get("media_type", "movie")
            rules = (globals._config or {}).get("classification", {}).get("rules", [])
            for idx, rule in enumerate(rules):
                if classify(dims, rule.get("match_conditions", {})):
                    import_path = rule.get("import_path", "")
                    matched_rule = idx + 1
                    break
            if not import_path:
                import_path = (globals._config or {}).get("classification", {}).get("fallback_dir", "")
                used_fallback = bool(import_path)
        except Exception:
            pass

        if logger:
            logger.info(f"[scrape_preview] 完成: {scrape_elapsed}s, match_level={match_dict.get('match_level')}")

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
            "scrape_result": scrape_result,
            "scrape_elapsed": scrape_elapsed,
            "match_result": match_dict,
            "import_path": {
                "import_path": import_path,
                "used_fallback": used_fallback,
                "matched_rule": matched_rule,
            },
        })

    def _decorate_scrape_preview_mode(self, mode_data: dict):
        result = mode_data.get("result") or {}
        trace = result.get("scrape_trace", {}) if isinstance(result, dict) else {}
        confidence_detail = result.get("confidence_detail", {}) if isinstance(result, dict) else {}
        if not confidence_detail:
            confidence_calc = trace.get("confidence_calc", {}) if isinstance(trace, dict) else {}
            confidence_detail = {
                "formula": confidence_calc.get("formula", ""),
                "final_confidence": confidence_calc.get("final_confidence", result.get("confidence", 0)),
                "search_conf": result.get("confidence_search"),
                "data_gate": result.get("confidence_data_gate"),
                "detail": confidence_calc,
            }
        mode_data["confidence_detail"] = confidence_detail
        mode_data["ai_invoked"] = trace.get("ai_invoked", False)
        mode_data["ai_invoke_reason"] = trace.get("ai_invoke_reason")
        mode_data["search_enhanced"] = result.get("search_enhanced", trace.get("search_enhanced", False))
        mode_data["provider_type"] = result.get("provider_type", "")
        mode_data["provider_id"] = result.get("provider_id", "")

    def _build_scrape_preview_recommendation(self, modes_result: dict):
        best_mode = None
        best_confidence = -1
        for mode_key in ("provider_first", "ai_only"):
            result = modes_result.get(mode_key, {}).get("result", {})
            if not isinstance(result, dict) or result.get("error"):
                continue
            confidence = result.get("confidence", 0)
            if isinstance(confidence, (int, float)) and confidence > best_confidence:
                best_confidence = confidence
                best_mode = mode_key

        if not best_mode:
            return None

        reasons = {
            "provider_first": "置信度最高且优先使用 Provider，AI 调用最少，成本最低",
            "ai_only": "纯 AI 刮削置信度最高，适合冷门影片或 Provider 数据不完整的场景",
        }
        return {
            "best_mode": best_mode,
            "best_confidence": round(best_confidence, 4),
            "reason": reasons.get(best_mode, ""),
        }

    def _resolve_import_paths(self, modes_result: dict) -> dict:
        """Calculate import directory for each mode using classification rules."""
        from media_importer.features.import_flow.services.classification_rules import classify, render_template
        from media_importer.features.scraping.dimension_manager import get_dimensions_for_scrape

        config = globals._config or {}
        path_rules = config.get("path_rules", [])
        fallback_dir = config.get("fallback_dir", "")
        db_path = os.path.join(
            config.get("_data_dir",
                os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")),
            "tasks.db")

        enabled_dims = set()
        try:
            conn = sqlite3.connect(db_path)
            conn.row_factory = sqlite3.Row
            dims = get_dimensions_for_scrape(conn)
            if dims:
                enabled_dims = {d.get("name") for d in dims if d.get("enabled")}
            conn.close()
        except Exception:
            pass

        result = {}
        for mode_key in ("provider_first", "ai_only"):
            mode_data = modes_result.get(mode_key, {})
            scrape_result = mode_data.get("result", {})
            if not isinstance(scrape_result, dict) or scrape_result.get("error"):
                result[mode_key] = {"import_path": "", "used_fallback": False, "matched_rule": None}
                continue

            import_path = classify(scrape_result, path_rules, enabled_dims)
            used_fallback = False
            matched_rule = None

            if import_path:
                # Find which rule matched
                dimensions = scrape_result.get("dimensions", {})
                for i, rule in enumerate(path_rules):
                    from media_importer.features.import_flow.services.classification_rules import match_conditions
                    if match_conditions(dimensions, rule.get("conditions", {}), enabled_dims):
                        matched_rule = i + 1
                        break
            elif fallback_dir:
                import_path = render_template(fallback_dir, scrape_result)
                used_fallback = True

            result[mode_key] = {
                "import_path": import_path or "",
                "used_fallback": used_fallback,
                "matched_rule": matched_rule,
            }

        return result
