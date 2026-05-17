#!/usr/bin/env python3
import hashlib
import hmac
import json
import time
import urllib.request
import urllib.error
import ssl
from datetime import datetime


EVENT_TYPE_DISPLAY = {
    "task_complete": "✅ 任务完成",
    "task_failed": "❌ 任务失败",
    "task_skipped": "⏭️ 任务跳过",
    "batch_complete": "📦 批量处理完成"
}


class HermesNotifier:
    def __init__(self, config: dict):
        hermes_cfg = config.get("hermes", {})
        webhook_cfg = hermes_cfg.get("webhook", {})

        self.enabled = hermes_cfg.get("enabled", False)
        self.base_url = webhook_cfg.get("base_url", "").rstrip("/")
        self.route_name = webhook_cfg.get("route_name", "media-normalize")
        self.secret = webhook_cfg.get("secret", "")
        self.timeout = webhook_cfg.get("timeout", 30)
        self.max_retries = webhook_cfg.get("max_retries", 3)
        self.retry_delay = webhook_cfg.get("retry_delay", 5)
        self.enabled_events = set(webhook_cfg.get("events", [
            "task_complete", "task_failed", "task_skipped", "batch_complete"
        ]))

        self._webhook_url = ""
        if self.base_url and self.route_name:
            self._webhook_url = f"{self.base_url}/webhooks/{self.route_name}"

    def should_notify(self, event_type: str) -> bool:
        if not self.enabled:
            return False
        if not self._webhook_url:
            return False
        return event_type in self.enabled_events

    def notify(self, event_type: str, task=None, extra_data: dict = None):
        if not self.should_notify(event_type):
            return

        payload = self._build_payload(event_type, task, extra_data)
        self._send_with_retry(payload)

    def notify_batch_complete(self, tasks: list, summary: dict = None):
        if not self.should_notify("batch_complete"):
            return

        payload = self._build_batch_payload(tasks, summary)
        self._send_with_retry(payload)

    def _build_payload(self, event_type: str, task, extra_data: dict = None) -> dict:
        payload = {
            "event_type": event_type,
            "event_type_display": EVENT_TYPE_DISPLAY.get(event_type, event_type),
            "timestamp": datetime.now().isoformat(),
            "video_file": "",
            "status": "",
            "extra_info": "",
            "task": {}
        }

        if task:
            payload["video_file"] = task.video_file
            payload["status"] = task.status
            payload["task"] = task.to_dict()

            if event_type == "task_complete":
                payload["extra_info"] = (
                    f"入库路径: {task.import_path}\n"
                    f"最终文件名: {task.final_filename}"
                )
            elif event_type == "task_failed":
                payload["extra_info"] = (
                    f"错误信息: {task.error_message}\n"
                    f"重试次数: {task.retry_count}"
                )
            elif event_type == "task_skipped":
                payload["extra_info"] = task.error_message or "同名文件已存在"

        if extra_data:
            payload.update(extra_data)

        return payload

    def _build_batch_payload(self, tasks: list, summary: dict = None) -> dict:
        if summary is None:
            summary = {"total": len(tasks)}
            status_counts = {}
            for t in tasks:
                s = t.status
                status_counts[s] = status_counts.get(s, 0) + 1
            summary.update(status_counts)

        lines = [f"总计: {summary.get('total', 0)}"]
        for status in ["SUCCESS", "FAILED", "SKIPPED"]:
            count = summary.get(status, 0)
            if count > 0:
                icon = {"SUCCESS": "✅", "FAILED": "❌", "SKIPPED": "⏭️"}.get(status, "")
                lines.append(f"{icon} {status}: {count}")

        return {
            "event_type": "batch_complete",
            "event_type_display": EVENT_TYPE_DISPLAY["batch_complete"],
            "timestamp": datetime.now().isoformat(),
            "video_file": "",
            "status": "BATCH_COMPLETE",
            "extra_info": "\n".join(lines),
            "task": {},
            "batch_summary": summary
        }

    def _sign(self, payload_bytes: bytes) -> str:
        if not self.secret:
            return ""
        signature = hmac.new(
            self.secret.encode("utf-8"),
            payload_bytes,
            hashlib.sha256
        ).hexdigest()
        return signature

    def _send_with_retry(self, payload: dict):
        payload_bytes = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        signature = self._sign(payload_bytes)

        headers = {
            "Content-Type": "application/json",
            "X-Webhook-Signature": signature
        }

        last_error = None
        for attempt in range(1, self.max_retries + 1):
            try:
                self._send_request(payload_bytes, headers)
                return
            except Exception as e:
                last_error = e
                if attempt < self.max_retries:
                    time.sleep(self.retry_delay)

    def _send_request(self, payload_bytes: bytes, headers: dict):
        req = urllib.request.Request(
            self._webhook_url,
            data=payload_bytes,
            headers=headers,
            method="POST"
        )

        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE

        response = urllib.request.urlopen(req, timeout=self.timeout, context=ctx)
        status_code = response.getcode()

        if status_code >= 400:
            raise HermesNotifyError(
                f"Webhook返回错误状态码: {status_code}"
            )


class HermesNotifyError(Exception):
    pass
