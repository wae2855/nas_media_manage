"""LLM HTTP client implementation — extracted from LLMScraper."""
import json
import logging
import re
import time
import ssl
import urllib.request
import urllib.error
from typing import Dict, Any, Optional

from media_importer.scraper.exceptions import LLMApiError, LLMWebSearchError, LLMScrapeError

logger = logging.getLogger("media_importer.ai")


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
                  base_url: str, api_key: str, scenario: Optional[str] = None) -> str:
    trimmed = (base_url or "").rstrip("/")
    if trimmed.endswith("/chat/completions"):
        url = trimmed
    else:
        url = f"{trimmed}/chat/completions"
    payload = _build_payload_int(self, system_prompt, user_content, model)

    if scenario and self.web_search_config.should_search(scenario):
        provider = self.web_search_config.effective_provider()
        _inject_web_search_impl(self, payload, provider)

    # 注：提示词日志由 _run_with_strategy_impl 统一记录（带 attempt 维度），
    # 此处不再重复输出，避免每次调用产生两条 prompt_summary。

    try:
        return self._send_request(url, payload, api_key)
    except Exception as e:
        if isinstance(e, LLMWebSearchError):
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


def _resolve_connection(self, cfg_key: str):
    if cfg_key == "ai_assist":
        return self.fast_model, self.fast_base_url, self.fast_api_key, False
    if cfg_key == "ai_search":
        return self.model, self.base_url, self.api_key, True
    raise ValueError(f"未知模型配置: {cfg_key}")


def _run_with_strategy_impl(self, system_prompt, user_content, scene, scenario,
                            on_success):
    """场景策略 + 多模型重试 + 结构化日志 共享实现。

    参数：
    - on_success(raw_response, cfg_key, model, attempt)：单次成功回调，
      返回最终结果；用于 _retry_with_fallback_impl 转 dict、_call_with_retry_impl 直接返回 raw。
    """
    if not hasattr(self, "scene_strategy"):
        raise LLMScrapeError("LLMScraper 未注入 scene_strategy；请通过 __init__ 传入 ConfigView")

    strategy = self.scene_strategy.model_sequence(scene)
    if not strategy:
        logger.warning(
            f"ai.scene.strategy_missing scene={scene} fallback_to=ai_search "
            f"reason=ai_scene_strategy_not_configured"
        )
        strategy = ["ai_search"]

    total_start = time.monotonic()
    last_error = None

    log_prompt_enabled = bool(getattr(self, "view", None) and self.view.ai_assist.log_prompt)

    for idx, cfg_key in enumerate(strategy):
        try:
            model, base_url, api_key, default_use_search = _resolve_connection(self, cfg_key)
        except ValueError as e:
            last_error = e
            continue
        for attempt in range(self.max_retries):
            logger.info(
                f"ai.scene.start scene={scene} model={cfg_key} "
                f"attempt={attempt + 1}/{self.max_retries} "
                f"system_prompt_len={len(system_prompt)} user_prompt_len={len(user_content)}"
            )
            if log_prompt_enabled:
                logger.info(
                    f"ai.scene.prompt_summary scene={scene} model={cfg_key} "
                    f"system_prompt_len={len(system_prompt)} "
                    f"system_prompt_preview={system_prompt[:200]!r} "
                    f"user_prompt_len={len(user_content)} "
                    f"user_prompt_preview={user_content[:200]!r}"
                )
            logger.debug(
                f"ai.scene.prompt scene={scene} model={cfg_key} "
                f"system_prompt={system_prompt!r} user_prompt={user_content!r}"
            )
            t0 = time.monotonic()
            try:
                search_scenario = scenario if (default_use_search and scenario) else None
                # 注入 scene 到 _do_call_impl 上下文，供 prompt 日志使用
                self._current_scene = scene
                self._current_cfg_key = cfg_key
                raw = self._do_call(system_prompt, user_content, model,
                                    base_url, api_key, scenario=search_scenario)
                elapsed_ms = int((time.monotonic() - t0) * 1000)
                logger.info(
                    f"ai.scene.success scene={scene} model={cfg_key} "
                    f"attempt={attempt + 1} elapsed_ms={elapsed_ms}"
                )
                return on_success(raw, cfg_key, model, attempt + 1)
            except (LLMScrapeError, LLMApiError, LLMWebSearchError) as e:
                last_error = e
                elapsed_ms = int((time.monotonic() - t0) * 1000)
                if attempt < self.max_retries - 1:
                    logger.warning(
                        f"ai.scene.retry scene={scene} model={cfg_key} "
                        f"attempt={attempt + 1} elapsed_ms={elapsed_ms} "
                        f"error={type(e).__name__} reason={str(e)[:200]} "
                        f"next_attempt_in={self.retry_delay}s"
                    )
                    time.sleep(self.retry_delay)
                else:
                    logger.warning(
                        f"ai.scene.model_exhausted scene={scene} model={cfg_key} "
                        f"attempts={self.max_retries} last_error={type(e).__name__}"
                    )
        # 当前模型全部重试失败，切换到下一个 fallback 模型
        if idx < len(strategy) - 1:
            logger.warning(
                f"ai.scene.fallback scene={scene} from={cfg_key} "
                f"to={strategy[idx + 1]} reason=all_retries_failed"
            )

    total_elapsed_ms = int((time.monotonic() - total_start) * 1000)
    logger.error(
        f"ai.scene.failure scene={scene} last_model={strategy[-1]} "
        f"last_error={type(last_error).__name__ if last_error else 'Unknown'} "
        f"reason={str(last_error)[:200] if last_error else 'unknown'} "
        f"total_elapsed_ms={total_elapsed_ms}"
    )
    if last_error:
        raise last_error
    raise LLMScrapeError("所有重试均失败")


def _retry_with_fallback_impl(self, system_prompt: str, user_content: str,
                               scene: Optional[str] = None, scenario: Optional[str] = None,
                               use_fast: Optional[bool] = None) -> Dict[str, Any]:
    """多模型 fallback 重试入口（返回 parse 后的 dict）。

    参数约定：
    - scene：5 个场景 key。SceneStrategyResolver 获取模型序列。
    - use_fast：旧兼容入口（True → scene="dimension_mapping"，False → scene="dimension_supplement"）。
    """
    if scene is None:
        scene = "dimension_mapping" if use_fast else "dimension_supplement"

    def _on_success(raw, cfg_key, model, attempt):
        return _parse_response_impl(self, raw)

    return _run_with_strategy_impl(
        self, system_prompt, user_content, scene, scenario, _on_success,
    )


def _call_with_retry_impl(self, system_prompt: str, user_content: str,
                          scene: str, scenario: Optional[str] = None) -> str:
    """通用 LLM 调用入口：按场景策略多模型重试并 fallback，返回原始响应字符串。

    与 _retry_with_fallback_impl 区别：
    - 不调用 _parse_response_impl，保留 raw 文本给调用方自行解析（适合非刮削场景如 source_clean）。
    """
    def _on_success(raw, cfg_key, model, attempt):
        return raw

    return _run_with_strategy_impl(
        self, system_prompt, user_content, scene, scenario, _on_success,
    )
