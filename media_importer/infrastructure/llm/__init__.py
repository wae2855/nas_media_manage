"""基础设施 LLM 客户端：OpenAI 兼容 HTTP 调用 + 重试 + fallback 模型。

唯一消费者是源目录清理器（ADR-0010：AI 刮削已移除，LLM 仅服务清理器场景）。
无场景策略矩阵、无联网搜索增强——那些随 AI 刮削一并退役。
"""
import json
import logging
import ssl
import time
import urllib.error
import urllib.request
from typing import Optional

logger = logging.getLogger("media_importer.ai")


class LLMError(Exception):
    """LLM 调用失败（网络/认证/响应解析）。"""


class LLMClient:
    """最小 OpenAI 兼容客户端：主模型失败自动降级 fallback_model。"""

    def __init__(self, config: dict):
        llm_cfg = config.get("llm", {}) or {}
        self.api_key = (llm_cfg.get("api_key") or "").strip()
        self.base_url = (llm_cfg.get("base_url") or "").strip().rstrip("/")
        self.model = (llm_cfg.get("model") or "").strip()
        self.fallback_model = (llm_cfg.get("fallback_model") or "").strip()
        self.timeout = int(llm_cfg.get("timeout") or 30)
        self.max_retries = max(1, int(llm_cfg.get("max_retries") or 2))
        self.retry_delay = float(llm_cfg.get("retry_delay") or 3)
        self.verify_ssl = bool(llm_cfg.get("verify_ssl", True))

    @property
    def enabled(self) -> bool:
        return bool(self.api_key and self.base_url and self.model)

    def call(self, system_prompt: str, user_prompt: str) -> str:
        """调用 LLM 返回纯文本响应；主模型重试耗尽后尝试 fallback 模型。"""
        if not self.enabled:
            raise LLMError("LLM 未配置（llm.api_key / base_url / model 不完整）")

        models = [self.model]
        if self.fallback_model and self.fallback_model != self.model:
            models.append(self.fallback_model)

        last_error: Optional[Exception] = None
        for model in models:
            for attempt in range(1, self.max_retries + 1):
                t0 = time.monotonic()
                try:
                    raw = self._do_call(system_prompt, user_prompt, model)
                    elapsed_ms = int((time.monotonic() - t0) * 1000)
                    logger.info(
                        f"ai.llm.success scene=source_clean model={model} "
                        f"attempt={attempt} elapsed_ms={elapsed_ms}"
                    )
                    return raw
                except Exception as e:
                    last_error = e
                    if attempt < self.max_retries:
                        logger.warning(
                            f"ai.llm.retry scene=source_clean model={model} "
                            f"attempt={attempt} error={type(e).__name__} "
                            f"next_in={self.retry_delay}s"
                        )
                        time.sleep(self.retry_delay)
                    else:
                        logger.warning(
                            f"ai.llm.model_exhausted scene=source_clean "
                            f"model={model} attempts={self.max_retries} "
                            f"last_error={type(e).__name__}"
                        )
        raise last_error or LLMError("LLM 调用失败")

    def _do_call(self, system_prompt: str, user_prompt: str, model: str) -> str:
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": 0.3,
        }
        data = json.dumps(payload).encode("utf-8")
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }
        url = f"{self.base_url}/chat/completions"

        ctx = None
        if not self.verify_ssl:
            ctx = ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE

        request = urllib.request.Request(url, data=data, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(request, timeout=self.timeout, context=ctx) as resp:
                result = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            raise LLMError(f"LLM HTTP {e.code}: {e.reason}") from e
        except (urllib.error.URLError, TimeoutError) as e:
            raise LLMError(f"LLM 连接失败: {e}") from e
        except json.JSONDecodeError as e:
            raise LLMError(f"LLM 响应非 JSON: {e}") from e

        try:
            content = result["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as e:
            raise LLMError(f"LLM 响应结构异常: {e}") from e
        if not isinstance(content, str) or not content.strip():
            raise LLMError("LLM 响应内容为空")
        return content
