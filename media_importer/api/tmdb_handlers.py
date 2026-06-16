# Re-export symbols from scrape_preview_job so external callers keep the same import paths.
from .scrape_preview_job import (
    _SCRAPE_PREVIEW_JOBS,
    _PREVIEW_STEP_DELAY,
    _preview_step_delay,
    _preview_add_step,
    _find_provider,
    _run_scrape_preview_job,
)

from .utils import json_response


class TMDbHandlersMixin:
    _tmdb_genres_cache = None
    _tmdb_genres_cache_time = 0
    _TMDB_GENRES_CACHE_TTL = 3600

    def _tmdb_genres_list(self):
        import time

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

    def _scrape_preview_start(self, *, body: dict, params: dict, query: dict):
        import threading
        import time
        import uuid

        filename = (body or {}).get("filename", "").strip()
        if not filename:
            json_response(self, 400, message="请输入视频文件名")
            return

        job_id = str(uuid.uuid4())
        now = time.time()
        _SCRAPE_PREVIEW_JOBS[job_id] = {
            "job_id": job_id,
            "status": "running",
            "filename": filename,
            "started_at": now,
            "updated_at": now,
            "steps": [],
            "partial": {},
            "result": None,
            "error": "",
        }

        from media_importer.api import globals
        config = globals._config or {}
        threading.Thread(
            target=_run_scrape_preview_job,
            args=(job_id, filename, config),
            daemon=True,
        ).start()

        json_response(self, 200, data={"job_id": job_id})

    def _scrape_preview_status(self, *, body: dict, params: dict, query: dict):
        job_id = params.get("job_id", "")
        job = _SCRAPE_PREVIEW_JOBS.get(job_id)
        if not job:
            json_response(self, 404, message="任务不存在或已过期")
            return

        json_response(self, 200, data={
            "job_id": job["job_id"],
            "status": job["status"],
            "filename": job["filename"],
            "steps": job["steps"],
            "partial": job.get("partial", {}),
            "result": job.get("result"),
            "error": job.get("error", ""),
        })
