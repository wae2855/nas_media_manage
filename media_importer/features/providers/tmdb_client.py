#!/usr/bin/env python3
import json
import ssl
import time
import urllib.parse
import urllib.request
from typing import Any, Dict, List, Optional


class TMDbError(Exception):
    pass


class TMDbClient:
    BASE_URL = "https://api.themoviedb.org/3"

    def __init__(self, api_key: str, language: str = "zh-CN",
                 fallback_language: str = "en-US", timeout: int = 10,
                 max_retries: int = 3):
        self.api_key = api_key
        self.language = language
        self.fallback_language = fallback_language
        self.timeout = timeout
        self.max_retries = max_retries

    def _request(self, endpoint: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        url = f"{self.BASE_URL}/{endpoint.lstrip('/')}"

        if params is None:
            params = {}

        params["api_key"] = self.api_key

        url_parts = list(urllib.parse.urlparse(url))
        query = dict(urllib.parse.parse_qsl(url_parts[4]))
        query.update(params)
        url_parts[4] = urllib.parse.urlencode(query)
        url = urllib.parse.urlunparse(url_parts)

        last_error = None
        for attempt in range(self.max_retries):
            try:
                context = ssl.create_default_context()
                context.check_hostname = False
                context.verify_mode = ssl.CERT_NONE

                with urllib.request.urlopen(url, timeout=self.timeout, context=context) as response:
                    data = response.read().decode('utf-8')
                    result = json.loads(data)

                    if "success" in result and not result["success"]:
                        raise TMDbError(result.get("status_message", "TMDb API error"))

                    return result
            except Exception as e:
                last_error = e
                if attempt < self.max_retries - 1:
                    time.sleep(1)
                continue

        raise TMDbError(
            f"TMDb 详情获取失败: Request failed after {self.max_retries} attempts: {last_error}"
            + ("（SSL 连接被中断，请检查网络连接或代理设置）" if "SSL" in str(last_error) else "")
        )

    def search_movie_list(self, title: str, year: Optional[int] = None,
                          language: Optional[str] = None) -> Dict[str, Any]:
        params: Dict[str, Any] = {"query": title, "language": language or self.language}
        if year is not None:
            params["primary_release_year"] = year
        result = self._request("/search/movie", params)
        return {
            "total_results": result.get("total_results", 0),
            "results": result.get("results", []),
        }

    def search_tv_list(self, title: str, year: Optional[int] = None,
                       language: Optional[str] = None) -> Dict[str, Any]:
        params: Dict[str, Any] = {"query": title, "language": language or self.language}
        if year is not None:
            params["first_air_date_year"] = year
        result = self._request("/search/tv", params)
        return {
            "total_results": result.get("total_results", 0),
            "results": result.get("results", []),
        }

    def search_movie(self, title: str, year: Optional[int] = None) -> Optional[Dict[str, Any]]:
        params: Dict[str, Any] = {"query": title, "language": self.language}
        if year is not None:
            params["primary_release_year"] = year

        result = self._request("/search/movie", params)
        results = result.get("results", [])

        if results:
            best_match = results[0]
            movie_id = best_match["id"]
            return self.get_movie_details(movie_id)

        if self.language != self.fallback_language:
            params["language"] = self.fallback_language
            result = self._request("/search/movie", params)
            results = result.get("results", [])
            if results:
                movie_id = results[0]["id"]
                return self.get_movie_details(movie_id)

        return None

    def search_tv(self, title: str, year: Optional[int] = None) -> Optional[Dict[str, Any]]:
        params: Dict[str, Any] = {"query": title, "language": self.language}
        if year is not None:
            params["first_air_date_year"] = year

        result = self._request("/search/tv", params)
        results = result.get("results", [])

        if results:
            best_match = results[0]
            tv_id = best_match["id"]
            return self.get_tv_details(tv_id)

        if self.language != self.fallback_language:
            params["language"] = self.fallback_language
            result = self._request("/search/tv", params)
            results = result.get("results", [])
            if results:
                tv_id = results[0]["id"]
                return self.get_tv_details(tv_id)

        return None

    def get_movie_details(self, movie_id: int) -> Dict[str, Any]:
        return self._request(f"/movie/{movie_id}", {"language": self.language})

    def get_tv_details(self, tv_id: int) -> Dict[str, Any]:
        return self._request(f"/tv/{tv_id}", {"language": self.language})

    def get_tv_season(self, tv_id: int, season_num: int) -> Optional[Dict[str, Any]]:
        try:
            return self._request(f"/tv/{tv_id}/season/{season_num}", {"language": self.language})
        except TMDbError:
            return None

    def get_movie_release_dates(self, movie_id: int) -> List[Dict[str, Any]]:
        try:
            result = self._request(f"/movie/{movie_id}/release_dates", {})
            return result.get('results', [])
        except TMDbError:
            return []

    def get_tv_release_dates(self, tv_id: int) -> List[Dict[str, Any]]:
        try:
            result = self._request(f"/tv/{tv_id}/content_ratings", {})
            return result.get('results', [])
        except TMDbError:
            return []

    def test_connection(self) -> bool:
        try:
            self._request("/authentication")
            return True
        except TMDbError:
            return False

    def get_genre_list(self) -> Dict[str, Any]:
        movie_genres = self._request("/genre/movie/list", {"language": "zh-CN"})
        tv_genres = self._request("/genre/tv/list", {"language": "zh-CN"})
        return {
            "movie": movie_genres.get("genres", []),
            "tv": tv_genres.get("genres", []),
        }
