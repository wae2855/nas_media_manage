#!/usr/bin/env python3
"""
Phase 5 HTTP API 集成测试
用 subprocess 启动服务器进行端到端测试
"""
import json
import time
import subprocess
import sys
import os
import unittest

SERVER_PORT = 18765


def api_request(method, path, body=None):
    import urllib.request
    url = f"http://127.0.0.1:{SERVER_PORT}{path}"
    headers = {}
    data = None
    if body and method in ("POST", "DELETE"):
        headers["Content-Type"] = "application/json"
        data = json.dumps(body).encode("utf-8")

    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            raw = resp.read()
            return resp.status, json.loads(raw.decode("utf-8"))
    except urllib.error.HTTPError as e:
        raw = e.read()
        try:
            return e.code, json.loads(raw.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            return e.code, {"raw": raw.decode("utf-8", errors="replace")}
    except Exception as e:
        return 0, {"error": str(e)}


class TestHTTPAPI(unittest.TestCase):
    server_process = None

    @classmethod
    def setUpClass(cls):
        if cls.server_process is not None:
            return

        config_path = os.path.join(os.path.dirname(__file__), "..", "media_importer", "config.yaml")
        script = os.path.join(os.path.dirname(__file__), "..", "media_importer", "media_importer.py")

        cls.server_process = subprocess.Popen(
            [sys.executable, script, "-c", config_path, "serve", "-p", str(SERVER_PORT), "--host", "127.0.0.1"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=os.path.dirname(os.path.dirname(__file__))
        )

        for _ in range(30):
            try:
                status, _ = api_request("GET", "/api/health")
                if status == 200:
                    return
            except Exception:
                pass
            time.sleep(0.3)

        stderr = cls.server_process.stderr.read().decode("utf-8", errors="replace") if cls.server_process.stderr else ""
        raise RuntimeError(f"API server failed to start. stderr: {stderr[:500]}")

    @classmethod
    def tearDownClass(cls):
        if cls.server_process:
            cls.server_process.terminate()
            cls.server_process.wait(timeout=5)

    def test_health(self):
        status, body = api_request("GET", "/api/health")
        self.assertEqual(status, 200)
        self.assertEqual(body["code"], 200)
        self.assertIn("status", body["data"])
        self.assertIn("checks", body["data"])
        print(f"  ✅ GET /api/health → status={body['data']['status']}")

    def test_metrics(self):
        status, body = api_request("GET", "/api/metrics")
        self.assertEqual(status, 200)
        self.assertIn("total_tasks", body["data"])
        self.assertIn("success_rate", body["data"])
        print(f"  ✅ GET /api/metrics → total={body['data']['total_tasks']}")

    def test_config(self):
        status, body = api_request("GET", "/api/config")
        self.assertEqual(status, 200)
        self.assertIn("config", body["data"])
        print(f"  ✅ GET /api/config → config keys={list(body['data']['config'].keys())[:3]}")

    def test_list_tasks_empty(self):
        status, body = api_request("GET", "/api/tasks")
        self.assertEqual(status, 200)
        self.assertIn("tasks", body["data"])
        self.assertIn("total", body["data"])
        print(f"  ✅ GET /api/tasks → total={body['data']['total']}")

    def test_list_tasks_filter(self):
        status, body = api_request("GET", "/api/tasks?status=PENDING&limit=10")
        self.assertEqual(status, 200)
        self.assertIsInstance(body["data"]["tasks"], list)
        print(f"  ✅ GET /api/tasks?status=PENDING → {len(body['data']['tasks'])} tasks")

    def test_task_not_found(self):
        status, body = api_request("GET", "/api/tasks/nonexistent123")
        self.assertEqual(status, 404)
        self.assertIn("not_found", body["status"])
        print(f"  ✅ GET /api/tasks/nonexistent123 → 404")

    def test_delete_task_not_found(self):
        status, body = api_request("DELETE", "/api/tasks/nonexistent123")
        self.assertEqual(status, 404)
        print(f"  ✅ DELETE /api/tasks/nonexistent123 → 404")

    def test_retry_task_not_found(self):
        status, body = api_request("POST", "/api/tasks/nonexistent123/retry", {})
        self.assertEqual(status, 404)
        print(f"  ✅ POST /api/tasks/nonexistent123/retry → 404")

    def test_clear_tasks(self):
        status, body = api_request("POST", "/api/tasks/clear", {"status": "SUCCESS"})
        self.assertEqual(status, 200)
        print(f"  ✅ POST /api/tasks/clear → cleared")

    def test_queue_status(self):
        status, body = api_request("GET", "/api/queue/status")
        self.assertEqual(status, 200)
        self.assertIn("paused", body["data"])
        self.assertIn("by_status", body["data"])
        print(f"  ✅ GET /api/queue/status → paused={body['data']['paused']}")

    def test_queue_pause_resume(self):
        s1, b1 = api_request("POST", "/api/queue/pause")
        self.assertEqual(s1, 200)
        print(f"  ✅ POST /api/queue/pause → {b1['message']}")

        s2, b2 = api_request("POST", "/api/queue/resume")
        self.assertEqual(s2, 200)
        print(f"  ✅ POST /api/queue/resume → {b2['message']}")

    def test_queue_retry_all(self):
        status, body = api_request("POST", "/api/queue/retry-all")
        self.assertEqual(status, 200)
        self.assertIn("retried_count", body["data"])
        print(f"  ✅ POST /api/queue/retry-all → retried {body['data']['retried_count']}")

    def test_logs(self):
        status, body = api_request("GET", "/api/logs?limit=10")
        self.assertEqual(status, 200)
        self.assertIn("logs", body["data"])
        print(f"  ✅ GET /api/logs → {len(body['data']['logs'])} entries")

    def test_run_batch(self):
        status, body = api_request("POST", "/api/run")
        self.assertEqual(status, 202)
        print(f"  ✅ POST /api/run → {body['message']}")

    def test_run_file_missing_path(self):
        status, body = api_request("POST", "/api/run/file", {})
        self.assertEqual(status, 400)
        print(f"  ✅ POST /api/run/file (no path) → 400")

    def test_run_file_not_found(self):
        status, body = api_request("POST", "/api/run/file", {"path": "/nonexistent/file.mkv"})
        self.assertEqual(status, 404)
        print(f"  ✅ POST /api/run/file (not found) → 404")

    def test_config_reload(self):
        status, body = api_request("POST", "/api/config/reload")
        self.assertEqual(status, 200)
        print(f"  ✅ POST /api/config/reload → {body['message']}")

    def test_not_found(self):
        status, body = api_request("GET", "/api/nonexistent")
        self.assertEqual(status, 404)
        self.assertIn("not_found", body["status"])
        print(f"  ✅ GET /api/nonexistent → 404")

    def test_response_format(self):
        status, body = api_request("GET", "/api/health")
        self.assertIn("code", body)
        self.assertIn("status", body)
        self.assertIn("message", body)
        self.assertIn("data", body)
        print(f"  ✅ Response format correct: code={body['code']}, status={body['status']}")


if __name__ == "__main__":
    suite = unittest.TestLoader().loadTestsFromTestCase(TestHTTPAPI)
    runner = unittest.TextTestRunner(verbosity=0)
    result = runner.run(suite)

    print(f"\n{'='*60}")
    print(f"HTTP API 集成测试: {result.testsRun} 个测试")
    print(f"  失败: {len(result.failures)}")
    print(f"  错误: {len(result.errors)}")

    if result.failures:
        print("\n失败:")
        for test, traceback in result.failures:
            print(f"  ❌ {test}\n{traceback[:300]}")

    if result.errors:
        print("\n错误:")
        for test, traceback in result.errors:
            print(f"  ❌ {test}\n{traceback[:300]}")

    if result.wasSuccessful():
        print("\n✅ 全部 HTTP API 测试通过！")
    else:
        print("\n❌ 部分测试失败")
        sys.exit(1)
