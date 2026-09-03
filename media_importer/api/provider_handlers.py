import copy
import time

from media_importer.api import globals

from .utils import json_response


class ProviderHandlersMixin:

    _genres_cache = {}
    _genres_cache_time = {}
    _GENRES_CACHE_TTL = 3600

    def _get_provider_config(self, provider_type: str) -> dict:
        providers = globals._config.get("metadata", {}).get("providers", []) if globals._config else []
        for p in providers:
            if p.get("type") == provider_type:
                return dict(p)
        return {}

    def _create_provider_instance(self, provider_type: str):
        from media_importer.features.providers import get_provider_class
        cls = get_provider_class(provider_type)
        if not cls:
            return None
        config = self._get_provider_config(provider_type)
        if not config:
            return None
        try:
            return cls(config)  # type: ignore[call-arg]
        except Exception:
            return None

    def _providers_list(self, *, body: dict, params: dict, query: dict):
        from media_importer.features.providers import get_all_registered_providers

        all_providers = get_all_registered_providers()
        enabled_types = set()
        if globals._config:
            for p in globals._config.get("metadata", {}).get("providers", []):  # type: ignore[union-attr]
                if p.get("enabled", False):
                    enabled_types.add(p.get("type", ""))

        result = []
        for ptype, cls in all_providers.items():
            config = self._get_provider_config(ptype)
            masked_config = copy.deepcopy(config) if config else {}
            if masked_config.get("api_key"):
                masked_config["api_key"] = "***"
            result.append({
                "type": ptype,
                "display_name": cls.display_name if hasattr(cls, "display_name") else ptype,
                "enabled": ptype in enabled_types,
                "config_schema": cls.get_config_schema(),
                "config": masked_config,
            })

        json_response(self, 200, data={"providers": result})

    def _provider_test(self, *, body: dict, params: dict, query: dict):
        provider_type = params.get("provider_type", "")
        provider = self._create_provider_instance(provider_type)
        if not provider:
            json_response(self, 200, data={"success": False, "message": f"Provider '{provider_type}' 未配置或创建失败"})
            return

        try:
            ok = provider.test_connection()
            msg = "连接成功" if ok else "连接失败，请检查配置是否正确"
            json_response(self, 200, data={"success": ok, "message": msg})
        except Exception as e:
            json_response(self, 200, data={"success": False, "message": "测试异常: " + str(e)})

    def _provider_genres_list(self, *, body: dict, params: dict, query: dict):
        provider_type = params.get("provider_type", "")
        now = time.time()
        cache = ProviderHandlersMixin._genres_cache.get(provider_type)
        cache_time = ProviderHandlersMixin._genres_cache_time.get(provider_type, 0)
        if cache is not None and now - cache_time < ProviderHandlersMixin._GENRES_CACHE_TTL:
            json_response(self, 200, data=cache)
            return

        provider = self._create_provider_instance(provider_type)
        if not provider:
            json_response(self, 400, message=f"Provider '{provider_type}' 未配置或创建失败")
            return

        try:
            genres_data = provider.get_genres()

            ProviderHandlersMixin._genres_cache[provider_type] = genres_data
            ProviderHandlersMixin._genres_cache_time[provider_type] = now

            json_response(self, 200, data=genres_data)
        except Exception as e:
            json_response(self, 503, message=f"获取类型列表失败: {str(e)}")

    def _provider_dimension_capabilities(self, *, body: dict, params: dict, query: dict):
        from media_importer.features.providers import get_provider_class

        provider_type = params.get("provider_type", "")
        cls = get_provider_class(provider_type)
        if not cls:
            json_response(self, 404, message=f"Provider 不存在: {provider_type}")
            return
        try:
            json_response(self, 200, data=cls.get_dimension_capabilities())
        except Exception as e:
            json_response(self, 500, message=f"获取 Provider 映射能力失败: {e}")

    def _provider_preview(self, *, body: dict, params: dict, query: dict):
        provider_type = params.get("provider_type", "")
        query_str = (body or {}).get("query", "").strip()
        media_type = (body or {}).get("type", "movie")

        if not query_str:
            json_response(self, 400, message="请输入影视名称")
            return

        provider = self._create_provider_instance(provider_type)
        if not provider:
            json_response(self, 400, message=f"Provider '{provider_type}' 未配置或创建失败")
            return

        try:
            search_result = provider.search(query_str, media_type=media_type)
            if not search_result.items:
                json_response(self, 200, data={"found": False, "message": "未找到匹配结果"})
                return

            first_item = search_result.items[0]
            details = provider.get_details(first_item.item_id, first_item.media_type)

            preview = {
                "found": True,
                "type": details.media_type,
                "id": details.item_id,
                "title": details.title,
                "original_title": details.original_title,
                "year": details.year,
                "overview": details.overview,
                "genres": [{"id": g.id, "name": g.name} for g in details.genres],
                "origin_country": details.origin_country,
                "original_language": details.original_language,
                "vote_average": details.vote_average,
                "poster_url": details.poster_url,
                "raw": details.raw_data,
            }
            json_response(self, 200, data=preview)
        except Exception as e:
            json_response(self, 500, message=f"预览异常: {str(e)}")

    def _provider_search(self, *, body: dict, params: dict, query: dict):
        provider_type = params.get("provider_type", "")
        query_str = (body or {}).get("query", "").strip()
        media_type = (body or {}).get("type", "movie")
        _language = (body or {}).get("language", "").strip() or None

        if not query_str:
            json_response(self, 400, message="请输入影视名称")
            return

        provider = self._create_provider_instance(provider_type)
        if not provider:
            json_response(self, 400, message=f"Provider '{provider_type}' 未配置或创建失败")
            return

        try:
            search_result = provider.search(query_str, media_type=media_type)

            items = []
            for item in search_result.items[:10]:
                items.append({
                    "id": item.item_id,
                    "title": item.title,
                    "original_title": item.original_title,
                    "year": item.year,
                    "vote_average": item.vote_average,
                    "poster_url": item.poster_url,
                    "overview": (item.raw_data.get("overview", "") or "")[:100],
                    "genre_ids": item.raw_data.get("genre_ids", []),
                    "media_type": item.media_type,
                })

            json_response(self, 200, data={
                "total_results": search_result.total_results,
                "items": items,
            })
        except Exception as e:
            json_response(self, 500, message=f"搜索异常: {str(e)}")

    def _provider_details(self, *, body: dict, params: dict, query: dict):
        provider_type = params.get("provider_type", "")
        item_id = (body or {}).get("id")
        media_type = (body or {}).get("type", "movie")

        if not item_id:
            json_response(self, 400, message="请提供 ID")
            return

        provider = self._create_provider_instance(provider_type)
        if not provider:
            json_response(self, 400, message=f"Provider '{provider_type}' 未配置或创建失败")
            return

        try:
            details = provider.get_details(str(item_id), media_type)

            json_response(self, 200, data={
                "found": True,
                "type": details.media_type,
                "details": details.raw_data,
            })
        except Exception as e:
            json_response(self, 500, message=f"详情获取异常: {str(e)}")
