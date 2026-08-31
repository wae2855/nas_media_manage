import os
import shutil
import socket
import tempfile
import threading
import time
import unittest
import urllib.request

from playwright.sync_api import sync_playwright

from media_importer.api.handler import start_server
from media_importer.features.configuration import load_config


def _free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("", 0))
        return sock.getsockname()[1]


def _wait_for_server(port, timeout=10):
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            if urllib.request.urlopen(f"http://127.0.0.1:{port}/api/health", timeout=2).status == 200:
                return
        except OSError:
            time.sleep(0.2)
    raise RuntimeError("测试服务未在预期时间内启动")


class TestStorageDirectoryButtonsUi(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmpdir = tempfile.mkdtemp(prefix="storage_buttons_ui_")
        paths = {}
        for name in ("source", "temp", "recycle", "logs", "resources", "library"):
            path = os.path.join(cls.tmpdir, name)
            os.makedirs(path)
            paths[name] = path
        cls.paths = paths
        cls.config_path = os.path.join(cls.tmpdir, "config.yaml")
        with open(cls.config_path, "w", encoding="utf-8") as handle:
            handle.write(
                f"""source_dir: {paths['source']}
temp_dir: {paths['temp']}
log_dir: {paths['logs']}
resource_dir: {paths['resources']}
library_root: {paths['library']}
library_roots:
  - id: main
    name: 主片库
    path: {paths['library']}
    enabled: true
default_library_root_id: main
fallback_library_root_id: main
fallback_dir: 未分类
path_rules:
  - conditions: {{}}
    template: "{{title_cn}}"
source_policy:
  recycle_dir: {paths['recycle']}
metadata:
  providers: []
"""
            )
        config = load_config(cls.config_path)
        cls.port = _free_port()
        cls.base_url = f"http://127.0.0.1:{cls.port}"
        cls.server = threading.Thread(
            target=start_server,
            args=("127.0.0.1", cls.port, config),
            daemon=True,
        )
        cls.server.start()
        _wait_for_server(cls.port)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmpdir, ignore_errors=True)

    def test_every_storage_button_opens_the_expected_fnos_authorization_flow(self):
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            page = browser.new_page(viewport={"width": 1440, "height": 1000})
            try:
                page.goto(self.base_url)
                page.wait_for_load_state("networkidle")
                page.locator(".bottom-nav [data-nav='config']").click()
                page.evaluate("setConfigStage('temp')")
                page.wait_for_selector("#storage-readiness-grid .storage-readiness-card")
                page.evaluate(
                    """(folders) => {
                      window.__openedFnosUrls = [];
                      window.open = (url) => {
                        window.__openedFnosUrls.push(String(url));
                        return { closed: false };
                      };
                      const capability = {
                        available: true,
                        enforced: true,
                        folders,
                        message: "测试授权目录",
                      };
                      currentFnosDirectoryCapability = capability;
                      renderStorageReadiness(
                        currentStorageReadinessSnapshot,
                        currentConfigSnapshot,
                        capability,
                      );
                    }""",
                    list(self.paths.values()),
                )

                for role in ("source", "temp", "recycle", "log", "resource"):
                    button = page.locator(f'[data-fnos-auth-role="{role}"]')
                    self.assertEqual(button.count(), 1, f"{role} 按钮数量异常")
                    button.click()
                    opened = page.evaluate("window.__openedFnosUrls.at(-1)")
                    pending = page.evaluate(
                        "JSON.parse(localStorage.getItem('nmmi-fnos-auth-pending'))"
                    )
                    self.assertIn("/app-auth/pick-shared-file", opened)
                    self.assertEqual(pending["role"], role)

                library_reauthorize = page.locator(
                    '[data-fnos-auth-role="library"][data-fnos-auth-path]'
                )
                self.assertEqual(library_reauthorize.count(), 1)
                library_reauthorize.click()
                opened = page.evaluate("window.__openedFnosUrls.at(-1)")
                pending = page.evaluate(
                    "JSON.parse(localStorage.getItem('nmmi-fnos-auth-pending'))"
                )
                self.assertIn("/app-auth/authorize-shared-file", opened)
                self.assertEqual(pending["role"], "library")
                self.assertEqual(pending["path"], os.path.realpath(self.paths["library"]))

                add_library = page.locator(
                    '[data-fnos-auth-role="library"]:not([data-fnos-auth-path])'
                )
                self.assertEqual(add_library.count(), 1)
                add_library.click()
                self.assertIn(
                    "/app-auth/pick-shared-file",
                    page.evaluate("window.__openedFnosUrls.at(-1)"),
                )
            finally:
                browser.close()

    def test_directory_role_payloads_keep_each_storage_role_separate(self):
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            page = browser.new_page()
            try:
                page.goto(self.base_url)
                page.wait_for_load_state("networkidle")
                patches = page.evaluate(
                    """() => ({
                      source: _directoryRolePatch('source', '/new/source'),
                      temp: _directoryRolePatch('temp', '/new/temp'),
                      recycle: _directoryRolePatch('recycle', '/new/recycle'),
                      log: _directoryRolePatch('log', '/new/log'),
                      resource: _directoryRolePatch('resource', '/new/resource'),
                    })"""
                )
                self.assertEqual(patches["source"], {"source_dir": "/new/source"})
                self.assertEqual(patches["temp"], {"temp_dir": "/new/temp"})
                self.assertEqual(patches["log"], {"log_dir": "/new/log"})
                self.assertEqual(patches["resource"], {"resource_dir": "/new/resource"})
                self.assertEqual(
                    patches["recycle"]["source_policy"]["recycle_dir"],
                    "/new/recycle",
                )
            finally:
                browser.close()

    def test_staged_library_roots_can_fail_visibly_then_commit_without_reselecting(self):
        roots = [
            {
                "id": f"library-{index}",
                "name": f"片库 {index}",
                "path": os.path.join(self.tmpdir, f"library-{index}"),
                "enabled": True,
            }
            for index in range(1, 6)
        ]
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            page = browser.new_page(viewport={"width": 1440, "height": 1000})
            page_errors = []
            page.on("pageerror", lambda error: page_errors.append(str(error)))
            try:
                page.goto(self.base_url)
                page.wait_for_load_state("networkidle")
                page.locator(".bottom-nav [data-nav='config']").click()
                page.evaluate("setConfigStage('temp')")
                page.wait_for_selector("#storage-readiness-grid")
                page.evaluate(
                    """(roots) => {
                      currentConfigSnapshot = {
                        ...currentConfigSnapshot,
                        _library_migration_error: "检测到旧版绝对入库规则",
                        library_root: "",
                        library_roots: roots,
                        default_library_root_id: roots[0].id,
                      };
                      renderStorageReadiness(
                        currentStorageReadinessSnapshot,
                        currentConfigSnapshot,
                        currentFnosDirectoryCapability,
                      );
                      window.__migrationRequests = [];
                      window.__migrationLoadCount = 0;
                      window.apiRequest = async (method, endpoint, body) => {
                        if (method === "POST" && endpoint === "/config") {
                          window.__migrationRequests.push(body);
                          return await new Promise((resolve) => {
                            window.__resolveMigration = resolve;
                          });
                        }
                        return { code: 500, message: "测试未处理的请求" };
                      };
                      window.loadDirectoryConfig = async () => {
                        window.__migrationLoadCount += 1;
                        const next = { ...currentConfigSnapshot };
                        delete next._library_migration_error;
                        currentConfigSnapshot = next;
                        renderStorageReadiness(
                          currentStorageReadinessSnapshot,
                          currentConfigSnapshot,
                          currentFnosDirectoryCapability,
                        );
                      };
                    }""",
                    roots,
                )

                callout = page.locator(".directory-migration-callout")
                self.assertIn("已暂存 5 个片库根", callout.inner_text())
                self.assertEqual(callout.get_by_text("继续添加片库", exact=True).count(), 1)
                confirm = callout.locator('[data-library-migration-action="commit"]')
                self.assertEqual(confirm.count(), 1)
                self.assertEqual(confirm.inner_text(), "已选齐，确认关联（5）")

                page.set_viewport_size({"width": 390, "height": 844})
                self.assertTrue(confirm.is_visible())
                self.assertTrue(callout.get_by_text("继续添加片库", exact=True).is_visible())
                self.assertLessEqual(
                    page.evaluate("document.documentElement.scrollWidth"),
                    page.evaluate("document.documentElement.clientWidth") + 1,
                )
                page.set_viewport_size({"width": 1440, "height": 1000})

                confirm.click()
                page.wait_for_function("Boolean(window.__resolveMigration)")
                self.assertTrue(confirm.is_disabled())
                self.assertEqual(confirm.inner_text(), "正在检查 5 个片库…")
                self.assertIn("正在检查 5 个片库", callout.inner_text())

                page.evaluate(
                    """window.__resolveMigration({
                      code: 400,
                      message: "配置未保存：第 3 条旧规则不在已选择的任何片库根目录下",
                    })"""
                )
                page.wait_for_function(
                    """document.querySelector('[data-library-migration-feedback]')?.textContent.includes('第 3 条旧规则')"""
                )
                self.assertTrue(confirm.is_enabled())
                self.assertIn("第 3 条旧规则", callout.inner_text())
                self.assertEqual(
                    page.evaluate("currentConfigSnapshot.library_roots.length"),
                    5,
                )
                request = page.evaluate("window.__migrationRequests[0]")
                self.assertTrue(request["_migrate_legacy_library_rules"])
                self.assertEqual(len(request["library_roots"]), 5)

                page.evaluate("window.__resolveMigration = null")
                confirm.click()
                page.wait_for_function("Boolean(window.__resolveMigration)")
                page.evaluate(
                    "window.__resolveMigration({ code: 200, message: '旧片库规则已迁移并保存' })"
                )
                page.wait_for_function(
                    "document.querySelector('.directory-migration-callout') === null"
                )
                self.assertEqual(page.evaluate("window.__migrationLoadCount"), 1)
                self.assertEqual(page_errors, [])
            finally:
                browser.close()

    def test_migration_modal_keeps_failure_reason_inside_the_dialog(self):
        addition = {
            "id": "documentary",
            "name": "纪录片",
            "path": os.path.join(self.tmpdir, "documentary"),
            "enabled": True,
        }
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            page = browser.new_page(viewport={"width": 1280, "height": 860})
            try:
                page.goto(self.base_url)
                page.wait_for_load_state("networkidle")
                page.evaluate(
                    """(addition) => {
                      currentConfigSnapshot = {
                        ...currentConfigSnapshot,
                        _library_migration_error: "检测到旧版绝对入库规则",
                        library_root: "",
                        library_roots: [],
                        default_library_root_id: "",
                      };
                      window.apiRequest = async (method, endpoint) => {
                        if (method === "POST" && endpoint === "/config") {
                          return await new Promise((resolve) => {
                            window.__resolveModalMigration = resolve;
                          });
                        }
                        return { code: 500, message: "测试未处理的请求" };
                      };
                      window.__migrationPromise = confirmLibraryRootAdditions([addition]);
                    }""",
                    addition,
                )

                modal = page.locator(".cinema-modal")
                modal.get_by_text("已选齐，确认关联", exact=True).click()
                page.wait_for_function("Boolean(window.__resolveModalMigration)")
                self.assertIn("正在检查 1 个片库", modal.inner_text())
                page.evaluate(
                    """window.__resolveModalMigration({
                      code: 400,
                      message: "配置未保存：旧兜底目录不在已选择的任何片库根目录下",
                    })"""
                )
                page.wait_for_function(
                    """document.querySelector('.cinema-modal [data-library-migration-feedback]')?.textContent.includes('旧兜底目录')"""
                )
                self.assertEqual(page.locator(".cinema-modal").count(), 1)
                self.assertIn("旧兜底目录", modal.inner_text())
                self.assertTrue(
                    modal.get_by_text("已选齐，确认关联", exact=True).is_enabled()
                )
            finally:
                browser.close()
