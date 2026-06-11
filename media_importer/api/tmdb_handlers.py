import time
import logging
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
        from media_importer.features.providers import create_providers

        logger = globals._global_logger
        cleaner = FilenameCleaner()
        clean_result = cleaner.clean(filename)
        providers = create_providers(globals._config)
        provider_enabled = bool(providers)
        current_mode = "hybrid"
        if globals._config:
            current_mode = globals._config.get("metadata", {}).get("scrape_mode", "hybrid")

        llm_config = globals._config.get("llm", {}) if globals._config else {}
        llm_timeout = int(llm_config.get("timeout", 30))
        llm_max_retries = int(llm_config.get("max_retries", 2))
        preview_timeout = (llm_max_retries + 1) * llm_timeout + 15

        if logger:
            logger.info(
                f"[scrape_preview] 开始: filename={filename}, "
                f"provider_enabled={provider_enabled}, current_mode={current_mode}"
            )

        def _run_mode(mode_key):
            try:
                if logger:
                    logger.info(f"[scrape_preview] {mode_key} 开始")
                metadata_scraper = MetadataScraper(globals._config)
                conn = getattr(globals._global_task_manager, 'conn', None) if globals._global_task_manager else None
                t0 = time.time()
                result = metadata_scraper.scrape(filename, conn=conn, force_mode=mode_key)
                elapsed = round(time.time() - t0, 2)
                if logger:
                    logger.info(f"[scrape_preview] {mode_key} 完成: {elapsed}s")
                return result, elapsed
            except Exception as e:
                if logger:
                    logger.error(f"[scrape_preview] {mode_key} 异常: {e}")
                return {"error": str(e)}, 0

        modes_result = {}
        executor = ThreadPoolExecutor(max_workers=3)
        try:
            futures = {
                "provider_first": executor.submit(_run_mode, "provider_first"),
                "ai_only": executor.submit(_run_mode, "ai_only"),
                "hybrid": executor.submit(_run_mode, "hybrid"),
            }

            for mode_key, future in futures.items():
                try:
                    result, elapsed = future.result(timeout=preview_timeout)
                    modes_result[mode_key] = {
                        "result": result,
                        "elapsed": elapsed,
                    }
                except FuturesTimeout:
                    if logger:
                        logger.warning(f"[scrape_preview] {mode_key} 超时 ({preview_timeout}s)")
                    modes_result[mode_key] = {
                        "result": {"error": f"{mode_key} 刮削超时（{preview_timeout} 秒）"},
                        "elapsed": preview_timeout,
                    }
                except Exception as e:
                    if logger:
                        logger.error(f"[scrape_preview] {mode_key} 异常: {e}")
                    modes_result[mode_key] = {
                        "result": {"error": str(e)},
                        "elapsed": 0,
                    }
        finally:
            executor.shutdown(wait=False)

        for mode_data in modes_result.values():
            self._decorate_scrape_preview_mode(mode_data)

        recommendation = self._build_scrape_preview_recommendation(modes_result)

        if logger:
            logger.info("[scrape_preview] 完成")

        ai_only = modes_result.get("ai_only", {})
        hybrid = modes_result.get("hybrid", {})
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
            "modes": modes_result,
            "current_mode": current_mode,
            "recommendation": recommendation,
            "ai_only": ai_only.get("result"),
            "ai_only_elapsed": ai_only.get("elapsed", 0),
            "provider_ai": hybrid.get("result"),
            "provider_ai_elapsed": hybrid.get("elapsed", 0),
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
        for mode_key in ("provider_first", "ai_only", "hybrid"):
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
            "hybrid": "联合刮削置信度最高，数据最完整，但 API 调用成本较高",
        }
        return {
            "best_mode": best_mode,
            "best_confidence": round(best_confidence, 4),
            "reason": reasons.get(best_mode, ""),
        }
