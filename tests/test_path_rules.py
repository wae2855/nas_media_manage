#!/usr/bin/env python3
"""build_path_test_payload() 单测。

该函数被 `POST /api/path/test` 调用，负责：
- 校验 path 必填（空路径抛 ValueError）
- 调用 check_path_permission 判断路径是否可读/可写
- 注入当前用户名

测试 mock 掉 check_path_permission 与 get_current_user，验证入参、异常、user 注入。
"""

import os
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from media_importer.features.configuration.application_service import build_path_test_payload


def _fake_perm(readable=True, writable=True, msg="ok"):
    return {
        "readable": readable,
        "writable": writable,
        "message": msg,
    }


class TestBuildPathTestPayload(unittest.TestCase):
    def test_missing_path_raises_value_error(self):
        with self.assertRaises(ValueError) as ctx:
            build_path_test_payload({}, lambda *a, **k: _fake_perm(), lambda: "user1")
        self.assertIn("path", str(ctx.exception).lower())

    def test_empty_path_raises_value_error(self):
        with self.assertRaises(ValueError):
            build_path_test_payload({"path": "   "}, lambda *a, **k: _fake_perm(), lambda: "user1")

    def test_default_need_write_is_true(self):
        captured = {}

        def fake_perm(path, need_write):
            captured["path"] = path
            captured["need_write"] = need_write
            return _fake_perm()

        build_path_test_payload({"path": "/data/source"}, fake_perm, lambda: "alice")
        self.assertEqual(captured["path"], "/data/source")
        self.assertTrue(captured["need_write"])

    def test_explicit_need_write_false_is_passed_through(self):
        captured = {}

        def fake_perm(path, need_write):
            captured["need_write"] = need_write
            return _fake_perm()

        build_path_test_payload(
            {"path": "/data/source", "need_write": False},
            fake_perm,
            lambda: "alice",
        )
        self.assertFalse(captured["need_write"])

    def test_path_is_stripped(self):
        captured = {}

        def fake_perm(path, need_write):
            captured["path"] = path
            return _fake_perm()

        build_path_test_payload({"path": "  /data/source  "}, fake_perm, lambda: "alice")
        self.assertEqual(captured["path"], "/data/source")

    def test_current_user_is_injected_into_result(self):
        result = build_path_test_payload(
            {"path": "/data/source"},
            lambda *a, **k: _fake_perm(msg="can read"),
            lambda: "bob",
        )
        self.assertEqual(result["user"], "bob")
        self.assertEqual(result["readable"], True)
        self.assertEqual(result["writable"], True)
        self.assertEqual(result["message"], "can read")

    def test_unwritable_path_returns_writable_false(self):
        result = build_path_test_payload(
            {"path": "/data/source", "need_write": True},
            lambda *a, **k: _fake_perm(readable=True, writable=False, msg="read-only"),
            lambda: "alice",
        )
        self.assertFalse(result["writable"])
        self.assertTrue(result["readable"])
        self.assertEqual(result["user"], "alice")

    def test_unreadable_path_returns_readable_false(self):
        result = build_path_test_payload(
            {"path": "/data/source"},
            lambda *a, **k: _fake_perm(readable=False, writable=False, msg="denied"),
            lambda: "alice",
        )
        self.assertFalse(result["readable"])
        self.assertFalse(result["writable"])

    def test_empty_body_dict_raises_value_error(self):
        """空 dict（缺 path）应抛 ValueError。"""
        with self.assertRaises(ValueError):
            build_path_test_payload({}, lambda *a, **k: _fake_perm(), lambda: "user1")

    def test_get_current_user_is_called_each_invoke(self):
        counter = {"n": 0}

        def get_user():
            counter["n"] += 1
            return "u" + str(counter["n"])

        build_path_test_payload({"path": "/a"}, lambda *a, **k: _fake_perm(), get_user)
        build_path_test_payload({"path": "/b"}, lambda *a, **k: _fake_perm(), get_user)
        self.assertEqual(counter["n"], 2)
