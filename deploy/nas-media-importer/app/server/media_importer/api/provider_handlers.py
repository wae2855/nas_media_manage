import os
import time
import copy

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
                config = dict(p)
                if not config.get("api_key") or config.get("api_key") == "***":
                    legacy = globals._config.get("metadata", {}).get(provider_type, {}) if globals._config else {}
                    if legacy and isinstance(legacy, dict):
                        for key in ("api_key", "language", "fallback_language", "request_timeout", "max_retries"):
                            if key in legacy and (key not in config or config.get(key) in (None, "", "***")):
                                config[key] = legacy[key]
                return config
        legacy = globals._config.get("metadata", {}).get(provider_type, {}) if globals._config else {}
        if legacy and isinstance(legacy, dict) and legacy.get("api_key"):
            config = {"type": provider_type, "enabled": legacy.get("enabled", True)}
            config.update(legacy)
            return config
        return {}

    def _create_provider_instance(self, provider_type: str):
        from media_importer.scraper.providers import get_provider_class
        cls = get_provider_class(provider_type)
        if not cls:
            return None
        config = self._get_provider_config(provider_type)
        if not config:
            return None
        try:
            return cls(config)
        except Exception:
            return None

    def _providers_list(self):
        from media_importer.scraper.providers import get_all_registered_providers, create_providers
        from media_importer.core.config_loader import mask_sensitive

        all_providers = get_all_registered_providers()
        enabled_types = set()
        if globals._config:
            for p in globals._config.get("metadata", {}).get("providers", []):
                if p.get("enabled", False):
                    enabled_types.add(p.get("type", ""))
            if not enabled_types:
                metadata = globals._config.get("metadata", {})
                for ptype in all_providers:
                    legacy = metadata.get(ptype, {})
                    if isinstance(legacy, dict) and legacy.get("enabled", False):
                        enabled_types.add(ptype)

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

    def _provider_test(self, body: dict, provider_type: str):
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

    def _provider_genres_list(self, provider_type: str):
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

    def _provider_preview(self, body: dict, provider_type: str):
        query = (body or {}).get("query", "").strip()
        media_type = (body or {}).get("type", "movie")

        if not query:
            json_response(self, 400, message="请输入影视名称")
            return

        provider = self._create_provider_instance(provider_type)
        if not provider:
            json_response(self, 400, message=f"Provider '{provider_type}' 未配置或创建失败")
            return

        try:
            search_result = provider.search(query, media_type=media_type)
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

    def _provider_search(self, body: dict, provider_type: str):
        query = (body or {}).get("query", "").strip()
        media_type = (body or {}).get("type", "movie")
        language = (body or {}).get("language", "").strip() or None

        if not query:
            json_response(self, 400, message="请输入影视名称")
            return

        provider = self._create_provider_instance(provider_type)
        if not provider:
            json_response(self, 400, message=f"Provider '{provider_type}' 未配置或创建失败")
            return

        try:
            search_result = provider.search(query, media_type=media_type)

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

    def _provider_details(self, body: dict, provider_type: str):
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

    def _provider_prompts_get(self, provider_type: str):
        from media_importer.scraper.llm_scraper import LLMScraper

        default_prompt = LLMScraper._get_default_provider_prompt(provider_type)

        config_path = globals._config.get("_config_path") if globals._config else None
        if config_path:
            prompts_dir = os.path.dirname(os.path.dirname(os.path.abspath(config_path)))
        else:
            prompts_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

        from media_importer.scraper.providers import get_provider_class
        cls = get_provider_class(provider_type)
        prompt_filename = f"{provider_type}_prompts.md"
        if cls and hasattr(cls, "provider_type"):
            prompt_filename = f"{cls.provider_type}_prompts.md"
        user_file = os.path.join(prompts_dir, "config", prompt_filename)

        custom_prompt = ""
        using_custom = False

        if os.path.isfile(user_file):
            try:
                import yaml as _yaml
                with open(user_file, "r", encoding="utf-8") as f:
                    content = f.read()
                if "system_prompt:" in content:
                    data = _yaml.safe_load(content)
                    if data and isinstance(data, dict):
                        custom_prompt = (data.get("system_prompt") or "").strip()
                        using_custom = bool(custom_prompt)
            except Exception:
                pass

        system_prompt = custom_prompt if custom_prompt else default_prompt

        json_response(self, 200, data={
            "system_prompt": system_prompt,
            "using_custom": using_custom,
        })

    def _provider_prompts_save(self, body: dict, provider_type: str):
        try:
            if not body:
                json_response(self, 400, message="Empty body")
                return

            system_prompt = body.get("system_prompt", "").strip()

            config_path = globals._config.get("_config_path") if globals._config else None
            if config_path:
                prompts_dir = os.path.dirname(os.path.dirname(os.path.abspath(config_path)))
            else:
                prompts_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

            from media_importer.scraper.providers import get_provider_class
            cls = get_provider_class(provider_type)
            prompt_filename = f"{provider_type}_prompts.md"
            if cls and hasattr(cls, "provider_type"):
                prompt_filename = f"{cls.provider_type}_prompts.md"
            prompts_file = os.path.join(prompts_dir, "config", prompt_filename)

            display_name = cls.display_name if cls else provider_type
            head_comment = f"""# ============================================================
# LLM+{display_name} 刮削提示词配置
# ============================================================
# 当 {display_name} API 命中元数据后，使用此提示词让 AI 整理/校验 {display_name} 数据
# 程序会自动追加维度列表和 JSON Schema，此文件只需编写上半部
# 如需恢复出厂默认，点击 WebUI 中的 "重置为默认" 即可

"""

            from ruamel.yaml import YAML
            from ruamel.yaml.scalarstring import LiteralScalarString

            yaml = YAML()
            yaml.preserve_quotes = True
            yaml.width = 120

            doc = {}
            if system_prompt:
                doc["system_prompt"] = LiteralScalarString(system_prompt)

            with open(prompts_file, "w", encoding="utf-8") as f:
                f.write(head_comment)
                yaml.dump(doc, f)

            json_response(self, 200, message=f"LLM+{display_name} 提示词已保存，重启服务后生效")
        except Exception as e:
            json_response(self, 500, message=f"保存提示词失败: {str(e)}")

    def _provider_prompts_reset(self, body: dict, provider_type: str):
        try:
            config_path = globals._config.get("_config_path") if globals._config else None
            if config_path:
                prompts_dir = os.path.dirname(os.path.dirname(os.path.abspath(config_path)))
            else:
                prompts_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

            from media_importer.scraper.providers import get_provider_class
            cls = get_provider_class(provider_type)
            prompt_filename = f"{provider_type}_prompts.md"
            if cls and hasattr(cls, "provider_type"):
                prompt_filename = f"{cls.provider_type}_prompts.md"
            prompts_file = os.path.join(prompts_dir, "config", prompt_filename)

            if os.path.isfile(prompts_file):
                os.remove(prompts_file)

            display_name = cls.display_name if cls else provider_type
            json_response(self, 200, message=f"已恢复出厂默认 LLM+{display_name} 提示词，重启服务后生效")
        except Exception as e:
            json_response(self, 500, message=f"恢复默认提示词失败: {str(e)}")
