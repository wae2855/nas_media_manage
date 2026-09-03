"""Provider 维度映射自定义下拉的真实浏览器合同。

Requirement: REQ-20260901-233114
"""

from __future__ import annotations

import os
import shutil
import socket
import tempfile
import threading
import time
import urllib.request

from playwright.sync_api import sync_playwright

from media_importer.api.handler import start_server
from media_importer.features.configuration import load_config


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _wait_for_server(port: int, timeout: float = 10) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            response = urllib.request.urlopen(
                f"http://127.0.0.1:{port}/api/health",
                timeout=2,
            )
            if response.status == 200:
                return
        except OSError:
            time.sleep(0.2)
    raise RuntimeError("维度映射浏览器测试服务未启动")


def _mapping_descriptors(page) -> list[dict]:
    return page.evaluate(
        """_dimensionsData.flatMap((dim) => {
          let mappings = dim.provider_mappings || {};
          if (typeof mappings === "string") {
            try { mappings = JSON.parse(mappings); } catch (_) { mappings = {}; }
          }
          return Object.entries(mappings)
            .filter(([, mapping]) => mapping && mapping.schema_version === 2)
            .map(([provider]) => ({ dimension: dim.name, provider }));
        })"""
    )


def test_all_mapping_editors_use_product_dropdown_with_keyboard_and_mobile_fit():
    test_root = tempfile.mkdtemp(prefix="dimension_mapping_ui_")
    try:
        paths = {}
        for name in ("source", "temp", "recycle", "logs", "resources", "library", "data"):
            path = os.path.join(test_root, name)
            os.makedirs(path)
            paths[name] = path
        config_path = os.path.join(test_root, "config.yaml")
        with open(config_path, "w", encoding="utf-8") as handle:
            handle.write(
                f"""source_dir: {paths['source']}
log_dir: {paths['logs']}
resource_dir: {paths['resources']}
library_roots:
  - id: main
    name: 主片库
    path: {paths['library']}
    enabled: true
default_library_root_id: main
source_policy:
  recycle_dir: {paths['recycle']}
metadata:
  providers: []
"""
            )
        config = load_config(config_path)
        config["_data_dir"] = paths["data"]
        port = _free_port()
        server = threading.Thread(
            target=start_server,
            args=("127.0.0.1", port, config),
            daemon=True,
        )
        server.start()
        _wait_for_server(port)

        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            page = browser.new_page(viewport={"width": 1440, "height": 1024})
            page_errors = []
            page.on("pageerror", lambda error: page_errors.append(str(error)))
            page.goto(f"http://127.0.0.1:{port}/", wait_until="networkidle")
            page.evaluate("loadDimensions()")
            mappings = _mapping_descriptors(page)
            assert len(mappings) == 7
            adult_marker = page.evaluate(
                """(() => {
                  const dim = _dimensionsData.find(
                    (item) => item.name === "content_sensitivity"
                  );
                  return {
                    label: dim && dim.label,
                    values: (dim && dim.value_list || []).map(
                      (item) => ({ value: item.value, label: item.label })
                    ),
                  };
                })()"""
            )
            assert adult_marker == {
                "label": "成人电影标记",
                "values": [
                    {"value": "normal", "label": "否"},
                    {"value": "adult", "label": "是"},
                ],
            }

            page.evaluate(
                "openProviderMappingEditor('content_sensitivity', 'tmdb')"
            )
            page.wait_for_selector("[data-provider-map-editor]")
            adult_editor = page.locator("[data-provider-map-editor]")
            assert "成人电影标记" in adult_editor.inner_text()
            assert adult_editor.locator(".provider-map-rule").count() == 2
            page.locator(".cinema-modal-close").click()

            for item in mappings:
                page.evaluate(
                    "([dimension, provider]) => "
                    "openProviderMappingEditor(dimension, provider)",
                    [item["dimension"], item["provider"]],
                )
                page.wait_for_selector("[data-provider-map-editor]")
                editor = page.locator("[data-provider-map-editor]")
                assert editor.locator("select").count() == 0
                controls = editor.locator("[data-map-select]")
                assert controls.count() >= 2

                control = controls.first
                trigger = control.locator(".provider-map-select-trigger")
                trigger.press("ArrowDown")
                assert trigger.get_attribute("aria-expanded") == "true"
                focused = page.locator("[data-map-select-option]:focus")
                assert focused.count() == 1
                focused.press("End")
                page.locator("[data-map-select-option]:focus").press("Enter")
                assert trigger.get_attribute("aria-expanded") == "false"
                draft = page.evaluate(
                    "_collectProviderMappingDraft("
                    "document.querySelector('.cinema-modal-overlay'))"
                )
                assert draft["rules"]
                assert draft["unmatched"]
                page.locator(".cinema-modal-close").click()

            page.close()
            mobile = browser.new_page(viewport={"width": 390, "height": 844})
            mobile.goto(f"http://127.0.0.1:{port}/", wait_until="networkidle")
            mobile.evaluate("loadDimensions()")
            mobile.evaluate("openProviderMappingEditor('restricted_level', 'tmdb')")
            mobile.wait_for_selector("[data-provider-map-editor]")
            trigger = mobile.locator(
                "[data-map-unmatched] .provider-map-select-trigger"
            )
            trigger.scroll_into_view_if_needed()
            trigger.click()
            panel = mobile.locator("[data-map-unmatched] .provider-map-select-panel")
            panel_box = panel.bounding_box()
            body_box = mobile.locator(".cinema-modal-body").bounding_box()
            assert panel_box is not None and body_box is not None
            assert panel_box["y"] >= body_box["y"] - 1
            assert panel_box["y"] + panel_box["height"] <= (
                body_box["y"] + body_box["height"] + 1
            )
            assert mobile.evaluate(
                "document.documentElement.scrollWidth <= innerWidth + 1"
            )
            assert not page_errors
            browser.close()
    finally:
        shutil.rmtree(test_root, ignore_errors=True)
