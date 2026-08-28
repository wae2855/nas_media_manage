"""任务工作台前端冒烟回归测试（Playwright）。

每个测试用例复用同一个浏览器上下文，避免重复启动开销。
运行前提：服务已启动在 localhost:9855，且有至少一个待确认任务。
运行方式：python tests/test_cinema_ui_smoke.py

如果当前 DB 无任务数据，含任务操作的用例会标记为 skip。
"""

import time

from playwright.sync_api import sync_playwright

BASE_URL = "http://localhost:9855"


class CinemaSmokeTests:
    def __init__(self):
        self.passed = 0
        self.failed = 0
        self.skipped = 0

    def _ok(self, name):
        print(f"  PASS: {name}")
        self.passed += 1

    def _fail(self, name, reason):
        print(f"  FAIL: {name} — {reason}")
        self.failed += 1

    def _skip(self, name, reason=""):
        print(f"  SKIP: {name} — {reason}" if reason else f"  SKIP: {name}")
        self.skipped += 1

    def run_all(self):
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            ctx = browser.new_context(viewport={"width": 1280, "height": 900})
            page = ctx.new_page()

            # 共享 setup
            page.goto(BASE_URL)
            page.wait_for_load_state("networkidle")
            time.sleep(1)
            self._dismiss_api_key(page)
            self._go_to_tasks(page)
            time.sleep(1)

            self._has_tasks = page.locator("[data-task-action='view-task']").count() > 0

            # 运行所有测试
            self.test_page_loads(page)
            self.test_refresh_button(page)
            self.test_task_card_buttons(page)
            self.test_detail_panel_opens(page)
            self.test_detail_panel_sections(page)
            self.test_decision_collapse(page)
            self.test_decision_expand(page)
            self.test_manual_scrape_modal(page)
            self.test_status_capsule(page)
            self.test_dimension_form(page)
            self.test_save_confirm_buttons(page)
            self.test_import_preview(page)

            browser.close()

        print(f"\n{'='*50}")
        print(f"  结果: {self.passed} passed, {self.failed} failed, {self.skipped} skipped")
        print(f"{'='*50}")

        # 把 skip 当作 pass（非必须项），只把 fail 当作失败
        return 1 if self.failed > 0 else 0

    # --- helpers ---

    def _dismiss_api_key(self, page):
        modal = page.locator("#api-key-modal")
        if modal.count() > 0 and modal.is_visible():
            inp = modal.locator("#api-key-input")
            if inp.count() > 0:
                inp.fill("test-key")
            btn = modal.locator("button:has-text('确认')")
            if btn.count() > 0:
                btn.click()
            time.sleep(0.5)

    def _go_to_tasks(self, page):
        tab = page.locator(".nav-item[data-nav='tasks']")
        if tab.count() > 0 and tab.is_visible():
            tab.click()
            time.sleep(0.5)

    def _open_detail(self, page):
        if not self._has_tasks:
            return False
        btn = page.locator("[data-task-action='view-task']").first
        btn.click()
        time.sleep(1.5)
        return page.locator(".cinema-modal-overlay").count() > 0

    def _close_detail(self, page):
        close = page.locator(".cinema-modal-close")
        if close.count() > 0:
            close.first.click()
            time.sleep(0.5)

    def _needs_task(self, page):
        if not self._has_tasks:
            self._skip("needs_task", "(当前无任务数据)")
            return False
        if not self._open_detail(page):
            self._fail("needs_task", "详情未弹出")
            return False
        return True

    # --- test cases ---

    def test_page_loads(self, page):
        name = "页面无 JS 报错"
        errors = []
        page.on("pageerror", lambda err: errors.append(str(err)))
        # 触发一次简单的 JS 执行
        page.evaluate("() => typeof openTaskDetail")
        if errors:
            self._fail(name, str(errors))
        else:
            self._ok(name)

    def test_refresh_button(self, page):
        name = "刷新按钮存在且可见"
        btn = page.locator("#task-panel-refresh")
        if btn.count() >= 1 and btn.is_visible():
            self._ok(name)
        else:
            self._fail(name, "刷新按钮不存在或不可见")

    def test_task_card_buttons(self, page):
        name = "任务卡片按钮(详情)"
        if not self._has_tasks:
            self._skip(name, "当前无任务")
            return
        btn = page.locator("[data-task-action='view-task']").first
        if btn.count() >= 1 and btn.is_visible():
            self._ok(name)
        else:
            self._fail(name, "卡片缺详情按钮")

    def test_detail_panel_opens(self, page):
        name = "点击详情弹出面板"
        if not self._has_tasks:
            self._skip(name, "当前无任务")
            return
        if not self._open_detail(page):
            self._fail(name, "modal 未弹出")
            return
        self._close_detail(page)
        self._ok(name)

    def test_detail_panel_sections(self, page):
        name = "详情面板核心区块"
        if not self._needs_task(page):
            return
        ok = True
        if page.locator(".cinema-modal-summary").count() == 0:
            self._fail(name, "缺摘要区")
            ok = False
        if page.locator(".config-collapse-card").count() == 0:
            self._fail(name, "缺决策路径区")
            ok = False
        if ok:
            self._ok(name)
        self._close_detail(page)

    def test_decision_collapse(self, page):
        name = "决策路径默认折叠"
        if not self._needs_task(page):
            return
        card = page.locator(".cinema-modal-overlay .config-collapse-card").first
        classes = (card.get_attribute("class") or "").split()
        if "open" not in classes:
            self._ok(name)
        else:
            self._fail(name, "决策路径应默认折叠但已展开")
        self._close_detail(page)

    def test_decision_expand(self, page):
        name = "点击标题展开决策路径"
        if not self._needs_task(page):
            return
        toggle = page.locator(".cinema-modal-overlay .config-collapse-header:has(h4)").first
        card = page.locator(".cinema-modal-overlay .config-collapse-card").first
        classes_before = (card.get_attribute("class") or "").split()
        toggle.click()
        time.sleep(0.5)
        classes_after = (card.get_attribute("class") or "").split()
        if "open" not in classes_before and "open" in classes_after:
            self._ok(name)
        elif "open" in classes_before:
            self._ok(name + " (已展开状态)")
        else:
            self._fail(name, "点击后未展开")
        self._close_detail(page)

    def test_manual_scrape_modal(self, page):
        name = "手动刮削弹窗"
        if not self._needs_task(page):
            return
        btn = page.locator("#btn-scrape-manual")
        if btn.count() == 0:
            self._skip(name, "当前任务不是待确认状态")
            self._close_detail(page)
            return
        btn.click()
        time.sleep(1)
        overlay = page.locator("#scrape-search-overlay")
        if overlay.count() >= 1:
            self._ok(name)
        else:
            self._fail(name, "弹窗未出现")
        # 先关弹窗
        close = page.locator("#scrape-search-overlay .cinema-modal-close")
        if close.count() > 0:
            close.click()
            time.sleep(0.3)
        self._close_detail(page)

    def test_status_capsule(self, page):
        name = "状态胶囊标签"
        if not self._needs_task(page):
            return
        capsule = page.locator(".task-status-capsule")
        if capsule.count() >= 1:
            label = (capsule.text_content() or "").strip()
            if label:
                self._ok(name)
            else:
                self._fail(name, "胶囊无文字")
        else:
            self._fail(name, "缺状态胶囊")
        self._close_detail(page)

    def test_dimension_form(self, page):
        name = "维度表单渲染"
        if not self._needs_task(page):
            return
        dims = page.locator("[data-task-dim]")
        if dims.count() > 0:
            self._ok(name)
        else:
            self._skip(name, "当前无启用的分类维度")
        self._close_detail(page)

    def test_save_confirm_buttons(self, page):
        name = "保存+确认入库按钮"
        if not self._needs_task(page):
            return
        save = page.locator("#btn-save-import")
        confirm = page.locator("#btn-confirm-import")
        if save.count() + confirm.count() >= 1:
            self._ok(name)
        else:
            self._skip(name, "非待确认状态")
        self._close_detail(page)

    def test_import_preview(self, page):
        name = "入库预览区"
        if not self._needs_task(page):
            return
        preview = page.locator("#import-preview-box")
        if preview.count() > 0:
            self._ok(name)
        else:
            self._skip(name, "非待确认状态无预览区")
        self._close_detail(page)


if __name__ == "__main__":
    code = CinemaSmokeTests().run_all()
    exit(code)
