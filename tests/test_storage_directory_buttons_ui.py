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
        for name in ("source", "recycle", "logs", "resources", "library"):
            path = os.path.join(cls.tmpdir, name)
            os.makedirs(path)
            paths[name] = path
        cls.paths = paths
        cls.config_path = os.path.join(cls.tmpdir, "config.yaml")
        with open(cls.config_path, "w", encoding="utf-8") as handle:
            handle.write(
                f"""source_dir: {paths['source']}
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
    library_root_id: main
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
                page.evaluate("setConfigStage('storage')")
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

                for role in ("source", "recycle", "log", "resource"):
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

    def test_unverified_non_library_paths_offer_direct_reauthorization(self):
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            page = browser.new_page(viewport={"width": 1440, "height": 1000})
            try:
                page.goto(self.base_url)
                page.wait_for_load_state("networkidle")
                page.locator(".bottom-nav [data-nav='config']").click()
                page.evaluate("setConfigStage('storage')")
                page.wait_for_selector("#storage-readiness-grid .storage-readiness-card")
                page.evaluate(
                    """(authorizedFolders) => {
                      window.__openedFnosUrls = [];
                      window.open = (url) => {
                        window.__openedFnosUrls.push(String(url));
                        return { closed: false };
                      };
                      const capability = {
                        available: true,
                        enforced: true,
                        folders: authorizedFolders,
                        message: "部分目录需要重新授权",
                      };
                      currentFnosDirectoryCapability = capability;
                      const readiness = {
                        ...currentStorageReadinessSnapshot,
                        locations: currentStorageReadinessSnapshot.locations.map((item) =>
                          ["source", "recycle"].includes(item.role)
                            ? {
                                ...item,
                                level: "error",
                                status: "OFFLINE",
                                message: "目录尚未授权给本应用，请先通过 fnOS 目录选择器授权",
                                authorization: {
                                  required: true,
                                  authorized: false,
                                  root: "",
                                },
                              }
                            : item,
                        ),
                      };
                      renderStorageReadiness(
                        readiness,
                        currentConfigSnapshot,
                        capability,
                      );
                    }""",
                    [
                        self.paths["logs"],
                        self.paths["resources"],
                        self.paths["library"],
                    ],
                )

                for role in ("source", "recycle"):
                    button = page.locator(f'[data-fnos-auth-role="{role}"]')
                    self.assertEqual(button.inner_text(), "重新授权")
                    self.assertEqual(
                        button.get_attribute("data-fnos-auth-path"),
                        self.paths[role],
                    )
                    button.click()
                    self.assertIn(
                        "/app-auth/authorize-shared-file",
                        page.evaluate("window.__openedFnosUrls.at(-1)"),
                    )

                self.assertEqual(page.locator('[data-fnos-auth-role="temp"]').count(), 0)
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
                      recycle: _directoryRolePatch('recycle', '/new/recycle'),
                      log: _directoryRolePatch('log', '/new/log'),
                      resource: _directoryRolePatch('resource', '/new/resource'),
                    })"""
                )
                self.assertEqual(patches["source"], {"source_dir": "/new/source"})
                self.assertEqual(patches["log"], {"log_dir": "/new/log"})
                self.assertEqual(patches["resource"], {"resource_dir": "/new/resource"})
                self.assertEqual(
                    patches["recycle"]["source_policy"]["recycle_dir"],
                    "/new/recycle",
                )
            finally:
                browser.close()

    def test_app_private_directories_are_explained_as_system_managed(self):
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            page = browser.new_page(viewport={"width": 390, "height": 844})
            try:
                page.goto(self.base_url)
                page.wait_for_load_state("networkidle")
                page.locator(".bottom-nav [data-nav='config']").click()
                page.evaluate("setConfigStage('storage')")
                page.wait_for_selector("#storage-readiness-grid .storage-readiness-card")
                page.evaluate(
                    """() => {
                      const readiness = {
                        ...currentStorageReadinessSnapshot,
                        locations: currentStorageReadinessSnapshot.locations.map((item) =>
                          item.role === "log"
                            ? {
                                ...item,
                                managed_by_app: true,
                                level: "ok",
                                status: "ONLINE",
                                message: "应用私有目录可用，无需 fnOS 共享目录授权",
                              }
                            : item,
                        ),
                      };
                      renderStorageReadiness(readiness, currentConfigSnapshot, {
                        available: true,
                        enforced: true,
                        folders: [],
                      });
                    }"""
                )

                log_card = page.locator(".storage-readiness-card").filter(has_text="运行日志")
                self.assertIn("应用私有目录", log_card.inner_text())
                self.assertIn("系统托管", log_card.inner_text())
                self.assertIn("无需 fnOS", log_card.inner_text())
                self.assertEqual(
                    page.evaluate("document.documentElement.scrollWidth <= innerWidth"),
                    True,
                )
            finally:
                browser.close()

    # Requirement: REQ-20260831-224737
    def test_existing_library_authorization_auto_refreshes_storage_status(self):
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            page = browser.new_page(viewport={"width": 1280, "height": 900})
            try:
                page.goto(self.base_url)
                page.wait_for_load_state("networkidle")
                page.locator(".bottom-nav [data-nav='config']").click()
                page.evaluate("setConfigStage('storage')")
                page.wait_for_selector("#storage-readiness-grid .storage-readiness-card")
                page.evaluate(
                    """(libraryPath) => {
                      const state = "test-existing-library-auth";
                      localStorage.setItem("nmmi-fnos-auth-pending", JSON.stringify({
                        state,
                        role: "library",
                        path: libraryPath,
                        appName: "nas-media-importer",
                        createdAt: Date.now(),
                      }));
                      window.__authFolderReads = 0;
                      window.__configReloads = 0;
                      window.__authToasts = [];
                      currentFnosDirectoryCapability = {
                        available: true,
                        enforced: true,
                        folders: [],
                        message: "测试授权同步",
                      };
                      renderStorageReadiness(
                        currentStorageReadinessSnapshot,
                        currentConfigSnapshot,
                        currentFnosDirectoryCapability,
                      );
                      getFnosAuthorizedFolders = async () => {
                        window.__authFolderReads += 1;
                        currentFnosDirectoryCapability = {
                          available: true,
                          enforced: true,
                          folders: window.__authFolderReads >= 2 ? [libraryPath] : [],
                          message: "测试授权同步",
                        };
                        return currentFnosDirectoryCapability;
                      };
                      loadDirectoryConfig = async () => {
                        window.__configReloads += 1;
                        renderStorageReadiness(
                          currentStorageReadinessSnapshot,
                          currentConfigSnapshot,
                          currentFnosDirectoryCapability,
                        );
                      };
                      showToast = (message) => window.__authToasts.push(message);
                      window.__authCompletion = _completeFnosAuthorization({
                        state,
                        status: "success",
                        appName: "nas-media-importer",
                        path: libraryPath,
                      });
                    }""",
                    os.path.realpath(self.paths["library"]),
                )

                sync_notice = page.locator("[data-fnos-auth-sync-status]")
                self.assertTrue(sync_notice.is_visible())
                self.assertIn("正在同步", sync_notice.inner_text())
                self.assertTrue(
                    page.locator("[data-fnos-auth-role]").first.is_disabled()
                )
                page.wait_for_function(
                    "window.__authCompletion && window.__configReloads === 1"
                )
                page.evaluate("window.__authCompletion")
                self.assertEqual(page.locator("[data-fnos-auth-sync-status]").count(), 0)
                self.assertGreaterEqual(page.evaluate("window.__authFolderReads"), 2)
                self.assertIn(
                    "授权状态已更新",
                    " ".join(page.evaluate("window.__authToasts")),
                )
                timeout_result = page.evaluate(
                    """async (libraryPath) => {
                      window.__timeoutFolderReads = 0;
                      getFnosAuthorizedFolders = async () => {
                        window.__timeoutFolderReads += 1;
                        return {
                          available: true,
                          enforced: true,
                          folders: [],
                          message: "尚未同步",
                        };
                      };
                      return await waitForFnosAuthorizedPaths([libraryPath], [0, 0]);
                    }""",
                    os.path.realpath(self.paths["library"]),
                )
                self.assertFalse(timeout_result["ready"])
                self.assertEqual(page.evaluate("window.__timeoutFolderReads"), 2)
            finally:
                browser.close()

    # Requirement: REQ-20260831-224737
    def test_rule_template_tokens_insert_at_caret_and_replace_selection(self):
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            page = browser.new_page(viewport={"width": 1280, "height": 900})
            try:
                page.goto(self.base_url)
                page.wait_for_load_state("networkidle")
                page.locator(".bottom-nav [data-nav='config']").click()
                page.evaluate("setConfigStage('rules')")
                page.evaluate(
                    """() => {
                      currentEnabledDimensions = [{
                        name: "genre",
                        label: "类型",
                        value_list: [],
                      }];
                      openRuleEditor(0);
                    }"""
                )
                modal = page.locator(".cinema-modal")
                input_box = modal.locator("#rule-template-input")
                assistant = modal.locator(".rule-template-assistant")
                self.assertFalse(assistant.evaluate("el => el.open"))
                assistant.locator("summary").click()
                self.assertTrue(assistant.evaluate("el => el.open"))
                input_box.fill("电影//")
                input_box.evaluate("el => el.setSelectionRange(3, 3)")
                modal.locator('[data-rule-template-token="{year}"]').click()
                self.assertEqual(input_box.input_value(), "电影/{year}/")

                input_box.evaluate(
                    """el => {
                      const start = el.value.indexOf("{year}");
                      el.setSelectionRange(start, start + "{year}".length);
                    }"""
                )
                modal.locator('[data-rule-template-token="{title_cn}"]').click()
                self.assertEqual(input_box.input_value(), "电影/{title_cn}/")
                self.assertEqual(
                    modal.locator("[data-rule-template-token]").count(),
                    8,
                )
                self.assertEqual(
                    modal.locator('[data-rule-template-token="{resolution}"]').count(),
                    1,
                )
                self.assertEqual(
                    modal.locator(
                        '[data-rule-template-token="{dimension.genre}"]'
                    ).count(),
                    1,
                )
                self.assertTrue(input_box.evaluate("el => document.activeElement === el"))

                page.set_viewport_size({"width": 390, "height": 844})
                self.assertTrue(modal.locator(".rule-template-assistant").is_visible())
                self.assertLessEqual(
                    page.evaluate("document.documentElement.scrollWidth"),
                    page.evaluate("document.documentElement.clientWidth") + 1,
                )
            finally:
                browser.close()

    def test_rule_template_input_removes_a_leading_slash_before_save(self):
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            page = browser.new_page(viewport={"width": 1280, "height": 900})
            try:
                page.goto(self.base_url)
                page.wait_for_load_state("networkidle")
                page.locator(".bottom-nav [data-nav='config']").click()
                page.evaluate("setConfigStage('rules')")
                page.evaluate("openRuleEditor(0)")

                modal = page.locator(".cinema-modal")
                input_box = modal.locator("#rule-template-input")
                input_box.fill("/{year}")
                self.assertEqual(input_box.input_value(), "{year}")
                self.assertIn(
                    "无需输入开头 /",
                    page.locator("#toast").inner_text(),
                )

                modal.get_by_text("保存规则", exact=True).click()
                self.assertEqual(page.locator(".cinema-modal").count(), 0)
                self.assertEqual(
                    page.evaluate("currentConfigSnapshot.path_rules[0].template"),
                    "{year}",
                )
            finally:
                browser.close()

    def test_rule_editor_requires_a_real_explicit_library(self):
        roots = [
            {"id": "main", "name": "主片库", "path": "/vol1/movies", "enabled": True},
            {"id": "archive", "name": "归档盘", "path": "/vol2/archive", "enabled": True},
            {"id": "unused", "name": "备用盘", "path": "/vol3/unused", "enabled": True},
        ]
        rules = [
            {"name": "未关联", "conditions": {}, "template": "/old/movies/{title_cn}"},
            {"name": "坏引用", "conditions": {}, "template": "电影", "library_root_id": "gone"},
            {"name": "已关联", "conditions": {}, "template": "经典", "library_root_id": "archive"},
        ]
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            page = browser.new_page(viewport={"width": 1280, "height": 900})
            try:
                page.goto(self.base_url)
                page.wait_for_load_state("networkidle")
                page.locator(".bottom-nav [data-nav='config']").click()
                page.evaluate("setConfigStage('rules')")
                page.evaluate(
                    """({roots, rules}) => {
                      currentConfigSnapshot = {
                        ...currentConfigSnapshot,
                        library_roots: roots,
                        default_library_root_id: "main",
                        fallback_library_root_id: "main",
                        fallback_dir: "未分类",
                        path_rules: rules,
                      };
                      renderLibraryRootList(currentConfigSnapshot);
                      renderRuleList(rules);
                    }""",
                    {"roots": roots, "rules": rules},
                )

                cards = page.locator(".rule-inline-item")
                self.assertIn("尚未选择片库", cards.nth(0).inner_text())
                self.assertIn("片库不存在：gone", cards.nth(1).inner_text())
                self.assertIn("归档盘", cards.nth(2).inner_text())

                cards.nth(0).get_by_text("编辑", exact=True).click()
                modal = page.locator(".cinema-modal")
                self.assertEqual(modal.locator("#rule-library-root-input").input_value(), "")
                self.assertIn("旧版入库路径（仅供参考）", modal.inner_text())
                page.set_viewport_size({"width": 390, "height": 844})
                self.assertTrue(modal.locator("#rule-library-root-input").is_visible())
                self.assertLessEqual(
                    page.evaluate("document.documentElement.scrollWidth"),
                    page.evaluate("document.documentElement.clientWidth") + 1,
                )
                page.set_viewport_size({"width": 1280, "height": 900})
                modal.locator("#rule-library-root-input").select_option("archive")
                self.assertEqual(modal.locator("#rule-template-input").input_value(), "")
                modal.locator("#rule-template-input").fill("电影/{title_cn}")
                modal.get_by_text("保存规则", exact=True).click()
                self.assertEqual(
                    page.evaluate("currentConfigSnapshot.path_rules[0].library_root_id"),
                    "archive",
                )

                page.locator('.rule-inline-item [data-rule-action="edit"][data-rule-index="1"]').click()
                modal = page.locator(".cinema-modal")
                self.assertEqual(modal.locator("#rule-library-root-input").input_value(), "")
                modal.get_by_text("取消", exact=True).click()

                page.evaluate(
                    """() => {
                      window.__rulesSaveRequests = 0;
                      window.apiRequest = async () => {
                        window.__rulesSaveRequests += 1;
                        return { code: 200 };
                      };
                    }"""
                )
                page.evaluate("saveRulesConfig()")
                self.assertEqual(page.evaluate("window.__rulesSaveRequests"), 0)
                self.assertTrue(page.get_by_text("备用盘", exact=False).first.is_visible())
            finally:
                browser.close()

    # Requirement: REQ-20260831-214244
    def test_storage_check_keeps_rule_assignment_issues_out_of_the_directory_page(self):
        roots = [
            {"id": "documentary", "name": "纪录片", "path": "/vol2/1000/documentary", "enabled": True},
            {"id": "movies", "name": "电影", "path": "/vol5/1000/movies", "enabled": True},
            {"id": "tv", "name": "电视剧", "path": "/vol1/1000/TV", "enabled": True},
            {"id": "tv-r", "name": "电视剧-限制级", "path": "/vol2/1000/TV-R", "enabled": True},
            {"id": "x-rated", "name": "电影-限制级", "path": "/vol2/1000/X-rated", "enabled": True},
        ]
        legacy_rules = [
            {"conditions": {"media_type": "tv", "restricted": "no", "documentary": "no"}, "template": "/vol1/1000/TV/{title_cn} ({year})/Season {season}/"},
            {"conditions": {"media_type": "tv", "restricted": "yes", "documentary": "no"}, "template": "/vol2/1000/TV-R/{title_cn} ({year})/Season {season}/"},
            {"conditions": {"media_type": "tv", "restricted": "no", "documentary": "yes"}, "template": "/vol2/1000/documentary/TV/{title_cn} ({year})/Season {season}/"},
            {"conditions": {"media_type": "movie", "documentary": "no", "restricted": "no"}, "template": "/vol5/1000/movies/{year}/"},
            {"conditions": {"media_type": "movie", "documentary": "no", "restricted": "yes"}, "template": "/vol2/1000/X-rated/"},
            {"conditions": {"media_type": "movie", "documentary": "yes", "restricted": "no"}, "template": "/vol2/1000/documentary/movies/"},
            {"conditions": {}, "template": "/vol3/1000/remote/movie/"},
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
                page.evaluate("setConfigStage('storage')")
                page.wait_for_selector("#storage-readiness-grid")
                page.evaluate(
                    """({roots, legacyRules}) => {
                      currentConfigSnapshot = {
                        ...currentConfigSnapshot,
                        _library_migration_error: "检测到旧版绝对入库规则",
                        library_root: "",
                        library_roots: roots,
                        default_library_root_id: roots[0].id,
                        path_rules: legacyRules,
                      };
                      renderStorageReadiness(
                        currentStorageReadinessSnapshot,
                        currentConfigSnapshot,
                        currentFnosDirectoryCapability,
                      );
                    }""",
                    {"roots": roots, "legacyRules": legacy_rules},
                )

                storage = page.locator("#storage-readiness-grid")
                self.assertEqual(storage.locator(".directory-migration-callout").count(), 0)
                self.assertEqual(storage.locator(".legacy-rule-coverage").count(), 0)
                self.assertEqual(storage.locator(".storage-add-library").count(), 1)
                self.assertEqual(storage.get_by_text("添加目标片库", exact=True).count(), 1)
                self.assertNotIn("旧规则待设置", storage.inner_text())
                self.assertNotIn("默认入库规则", storage.inner_text())
                self.assertNotIn("/vol3/1000/remote/movie", storage.inner_text())
                self.assertEqual(page.evaluate("currentConfigStage"), "storage")

                page.set_viewport_size({"width": 390, "height": 844})
                self.assertTrue(storage.get_by_text("添加目标片库", exact=True).is_visible())
                self.assertLessEqual(
                    page.evaluate("document.documentElement.scrollWidth"),
                    page.evaluate("document.documentElement.clientWidth") + 1,
                )
                self.assertEqual(page_errors, [])
            finally:
                browser.close()

    # Requirement: REQ-20260831-214244
    def test_library_setup_modal_saves_directories_without_rule_content_or_navigation(self):
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
                      window.__libraryRequests = [];
                      window.apiRequest = async (method, endpoint, body) => {
                        if (method === "POST" && endpoint === "/config") {
                          window.__libraryRequests.push(body);
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
                self.assertNotIn("旧版入库规则", modal.inner_text())
                self.assertNotIn("尚未选择目标片库", modal.inner_text())
                modal.get_by_text("添加并保存", exact=True).click()
                page.wait_for_function("Boolean(window.__resolveModalMigration)")
                request = page.evaluate("window.__libraryRequests[0]")
                self.assertEqual(len(request["library_roots"]), 1)
                self.assertNotIn("path_rules", request)
                self.assertEqual(page.evaluate("currentConfigStage"), "start")
                page.evaluate(
                    """window.__resolveModalMigration({
                      code: 400,
                      message: "配置未保存：片库目录授权失效",
                    })"""
                )
                self.assertEqual(page.locator(".cinema-modal").count(), 1)
                self.assertTrue(
                    modal.get_by_text("添加并保存", exact=True).is_enabled()
                )
                self.assertEqual(page.evaluate("currentConfigStage"), "start")
            finally:
                browser.close()
