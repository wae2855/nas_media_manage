"""LLM HTTP client implementation — extracted from LLMScraper."""
import json
import re
import time
import ssl
import urllib.request
import urllib.error
from typing import Dict, Any

from media_importer.scraper.exceptions import LLMApiError, LLMWebSearchError, LLMScrapeError


def _build_payload_int(self, system_prompt: str, user_content: str, model: str) -> dict:
    return {
        'model': model,
        'messages': [
            {'role': 'system', 'content': system_prompt},
            {'role': 'user', 'content': user_content}
        ],
        'temperature': 0.3
    }


def _send_request_impl(self, url: str, payload: dict, api_key: str,
                       max_tool_rounds: int = 5) -> str:
    headers = {
        'Content-Type': 'application/json',
        'Authorization': f'Bearer {api_key}'
    }
    ctx = None
    if not self.verify_ssl:
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE

    try:
        for _ in range(max_tool_rounds):
            data = json.dumps(payload).encode('utf-8')
            req = urllib.request.Request(url, data=data, headers=headers, method='POST')
            with urllib.request.urlopen(req, timeout=self.timeout, context=ctx) as response:
                response_data = response.read().decode('utf-8')
                result = json.loads(response_data)

            choice = result['choices'][0]
            finish_reason = choice.get('finish_reason', 'stop')

            if finish_reason != 'tool_calls':
                return choice['message']['content']

            assistant_msg = choice['message']
            payload['messages'].append(assistant_msg)

            tool_calls = assistant_msg.get('tool_calls', [])
            for tc in tool_calls:
                tc_name = tc.get('function', {}).get('name', '')
                tc_args = tc.get('function', {}).get('arguments', '{}')
                tc_id = tc.get('id', '')

                if tc_name == '$web_search':
                    tool_result = tc_args
                else:
                    tool_result = f"Error: unknown tool '{tc_name}'"

                payload['messages'].append({
                    'role': 'tool',
                    'tool_call_id': tc_id,
                    'name': tc_name,
                    'content': tool_result,
                })

        return choice['message'].get('content') or ''

    except urllib.error.HTTPError as e:
        body = {}
        try:
            body = json.loads(e.read().decode('utf-8'))
        except Exception:
            pass
        raise _classify_error_impl(e.code, body)
    except Exception as e:
        if isinstance(e, (LLMScrapeError, LLMWebSearchError)):
            raise
        raise LLMApiError(f"request failed: {e}") from e


def _inject_web_search_impl(self, payload: dict, provider: str) -> None:
    search_type = self.web_search_config.effective_search_type()
    if provider == "zhipu":
        web_search = {"enable": True}
        if search_type:
            web_search["search_type"] = search_type
        payload["tools"] = [{"type": "web_search", "web_search": web_search}]
    elif provider == "qwen":
        payload["enable_search"] = True
        if search_type == "forced_search":
            payload["search_options"] = {"forced_search": True}
    elif provider == "moonshot":
        payload["tools"] = [{"type": "builtin_function", "function": {"name": "$web_search"}}]


def _classify_error_impl(status_code: int, body: dict) -> Exception:
    err_msg = str(body).lower()
    if status_code in (401, 403):
        return LLMApiError(f"auth failed: {status_code}")
    if status_code == 429:
        if any(kw in err_msg for kw in ["web_search", "search", "quota"]):
            return LLMWebSearchError(f"web search quota exceeded: {body}")
        return LLMApiError(f"rate limited: {body}")
    if status_code == 400:
        if any(kw in err_msg for kw in ["web_search", "search", "plugin", "tool"]):
            return LLMWebSearchError(f"web search not available: {body}")
        return LLMApiError(f"bad request: {body}")
    if status_code >= 500:
        return LLMApiError(f"server error: {status_code}")
    return LLMApiError(f"unknown error: {status_code} {body}")


def _do_call_impl(self, system_prompt: str, user_content: str, model: str,
                  base_url: str, api_key: str, scenario: str = None) -> str:
    trimmed = (base_url or "").rstrip("/")
    if trimmed.endswith("/chat/completions"):
        url = trimmed
    else:
        url = f"{trimmed}/chat/completions"
    payload = _build_payload_int(self, system_prompt, user_content, model)

    if scenario and self.web_search_config.should_search(scenario):
        provider = self.web_search_config.effective_provider()
        _inject_web_search_impl(self, payload, provider)

    try:
        return self._send_request(url, payload, api_key)
    except Exception as e:
        if isinstance(e, LLMWebSearchError):
            import logging
            logger = logging.getLogger(__name__)
            logger.warning("web search failed, falling back to normal call: %s", e)
            fallback_payload = _build_payload_int(self, system_prompt, user_content, model)
            return self._send_request(url, fallback_payload, api_key)
        raise


def _parse_response_impl(self, raw_text: str) -> Dict[str, Any]:
    try:
        text = raw_text.strip()

        think_match = re.search(r'</think\s*>', text, re.DOTALL)
        if think_match:
            text = text[think_match.end():].strip()

        if text.startswith('```json'):
            text = text[7:]
        if text.endswith('```'):
            text = text[:-3]
        text = text.strip()

        json_match = re.search(r'\{[\s\S]*\}', text)
        if json_match:
            text = json_match.group(0)

        result = json.loads(text)

        required_fields = ['title_cn', 'title_en', 'year', 'type']
        for field in required_fields:
            if field not in result:
                result[field] = None

        for field in ['resolution', 'quality', 'language', 'season', 'episode']:
            if field not in result:
                result[field] = None

        if 'dimensions' not in result:
            result['dimensions'] = {}

        known_dim_names = {d['name'] for d in self.prompt_builder.dimensions if d.get('name')}
        if known_dim_names and isinstance(result['dimensions'], dict):
            result['dimensions'] = {
                k: v for k, v in result['dimensions'].items()
                if k in known_dim_names
            }

        result['raw_info'] = raw_text
        return result
    except json.JSONDecodeError as e:
        raise LLMScrapeError(f"JSON解析失败: {str(e)}, 原始内容: {raw_text[:200]}")


def _retry_with_fallback_impl(self, system_prompt: str, user_content: str,
                               use_fast: bool = False, scenario: str = None) -> Dict[str, Any]:
    if use_fast:
        models_to_try = [(self.fast_model, self.fast_base_url, self.fast_api_key, False)]
    else:
        models_to_try = [(self.model, self.base_url, self.api_key, True)]

    last_error = None

    for model, base_url, api_key, use_search in models_to_try:
        for attempt in range(self.max_retries):
            try:
                search_scenario = scenario if (use_search and scenario) else None
                raw_response = self._do_call(system_prompt, user_content, model,
                                             base_url, api_key, scenario=search_scenario)
                return _parse_response_impl(self, raw_response)
            except (LLMScrapeError, LLMApiError, LLMWebSearchError) as e:
                last_error = e
                if attempt < self.max_retries - 1:
                    time.sleep(self.retry_delay)
                continue

    if last_error:
        raise last_error
    raise LLMScrapeError("所有重试均失败")
