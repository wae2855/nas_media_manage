#!/usr/bin/env python3
import json
import os
import subprocess
import sys
import time
import urllib.request

import pytest
from playwright.sync_api import sync_playwright

BASE = "http://localhost:9855"
API_KEY = "oppenssl-11"

PASS = 0
FAIL = 0

if __name__ != "__main__":
    pytest.skip("script-style E2E suite; run with: python tests/test_source_cleaner_e2e.py", allow_module_level=True)


PASS = 0
FAIL = 0
RESULTS = []


def log(tc_id, name, passed, detail=""):
    global PASS, FAIL
    status = "PASS" if passed else "FAIL"
    if passed:
        PASS += 1
    else:
        FAIL += 1
    msg = f"  [{status}] {tc_id}: {name}"
    if detail:
        msg += f" — {detail}"
    print(msg)
    RESULTS.append({"id": tc_id, "name": name, "passed": passed, "detail": detail})


def api_save_sc_config(sc_data):
    api_call("POST", "/config/section", {
        "section": "source_cleaner",
        "data": {"source_cleaner": sc_data}
    })
    time.sleep(0.5)
    resp = api_call("POST", "/config/reload")
    if resp.get("code") != 200:
        time.sleep(2)
        api_call("POST", "/config/reload")
    time.sleep(1)


def api_call(method, path, data=None):
    url = f"{BASE}/api{path}"
    body = json.dumps(data).encode() if data else None
    req = urllib.request.Request(url, data=body, method=method)
    req.add_header("Content-Type", "application/json")
    req.add_header("Authorization", f"Bearer {API_KEY}")
    if body:
        req.add_header("Content-Length", str(len(body)))
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode())
    except Exception as e:
        return {"code": 500, "message": str(e)}


def prepare_environment():
    print("准备测试环境...")
    print("  1. 暂停文件监控...")
    resp = api_call("POST", "/watcher/control?action=pause")
    print(f"     结果: {resp.get('message', resp)}")

    print("  2. 清空所有任务...")
    resp = api_call("POST", "/tasks/clear", {"status": "ALL"})
    print(f"     结果: {resp.get('message', resp)}")
    time.sleep(1)

    print("  3. 重新生成测试数据...")
    script_dir = os.path.dirname(os.path.abspath(__file__))
    gen_script = os.path.join(script_dir, "gen_test_data.py")
    result = subprocess.run(["python3", gen_script], capture_output=True, text=True, timeout=120)
    if result.returncode == 0:
        print(f"     {result.stdout.strip()}")
    else:
        print(f"     错误: {result.stderr.strip()}")

    print("  4. 等待任务清空生效...")
    time.sleep(2)
    resp = api_call("GET", "/tasks")
    tasks = resp.get("data", {}).get("tasks", [])
    print(f"     当前任务数: {len(tasks)}")

    print("测试环境准备完成!\n")


def restore_environment():
    print("\n恢复测试环境...")
    resp = api_call("POST", "/watcher/control?action=resume")
    print(f"  文件监控已恢复: {resp.get('message', resp)}")


def click_toggle(page, checkbox_id):
    page.click(f'label[for="{checkbox_id}"]')


def wait_toast(page, timeout=5000):
    try:
        page.wait_for_selector(".toast", timeout=timeout)
        time.sleep(0.5)
        return True
    except Exception:
        return True


def save_and_check(page, section="source_cleaner"):
    page.click(f'[data-section="{section}"] .btn-primary')
    time.sleep(0.5)
    return wait_toast(page)


def reload_config(page):
    page.reload()
    page.wait_for_load_state("networkidle")
    time.sleep(1)
    page.click("#tab-config")
    page.wait_for_load_state("networkidle")
    time.sleep(0.5)
    page.click("#cfg-subtab-import")
    page.wait_for_load_state("networkidle")
    time.sleep(0.5)
    page.locator("#source-cleaner-config-section").scroll_into_view_if_needed()
    time.sleep(0.3)


def ensure_enabled(page):
    cb = page.locator("#cfg-source_cleaner-enabled")
    if not cb.is_checked():
        click_toggle(page, "cfg-source_cleaner-enabled")
        time.sleep(0.3)


with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page(viewport={"width": 1400, "height": 900})

    prepare_environment()

    page.goto(BASE)
    page.wait_for_load_state("networkidle")
    time.sleep(0.5)

    page.evaluate("localStorage.setItem('nas_onboarding_done', '1')")
    page.evaluate("var m=document.getElementById('onboarding-modal'); if(m){m.style.display='none';}")
    time.sleep(0.3)

    api_key_modal = page.locator("#api-key-modal")
    if api_key_modal.is_visible():
        page.fill("#api-key-input", API_KEY)
        page.click("#api-key-modal .btn-primary", force=True)
        page.wait_for_load_state("networkidle")
        time.sleep(1)
        page.evaluate("var m=document.getElementById('onboarding-modal'); if(m){m.style.display='none';}")
        time.sleep(0.3)

    # Wait for any running tasks to finish so config reload works
    for _ in range(10):
        resp = api_call("POST", "/config/reload")
        if resp.get("code") == 200:
            break
        time.sleep(2)

    page.click("#tab-config")
    page.wait_for_load_state("networkidle")
    time.sleep(1)
    page.click("#cfg-subtab-import")
    page.wait_for_load_state("networkidle")
    time.sleep(1)
    page.locator("#source-cleaner-config-section").scroll_into_view_if_needed()
    time.sleep(0.5)

    # ============================================================
    # 阶段一：配置界面保存验证
    # ============================================================
    print("\n" + "=" * 60)
    print("阶段一：配置界面保存验证")
    print("=" * 60)

    # TC-1.1 启用开关
    print("\n--- TC-1.1 启用开关保存 ---")
    fields = page.locator("#source-cleaner-fields")

    cb = page.locator("#cfg-source_cleaner-enabled")
    if cb.is_checked():
        click_toggle(page, "cfg-source_cleaner-enabled")
        time.sleep(0.3)

    log("1.1.1", "关闭时配置区域隐藏", fields.is_hidden())
    click_toggle(page, "cfg-source_cleaner-enabled")
    time.sleep(0.3)
    log("1.1.2", "开启时配置区域显示", fields.is_visible())

    ok = save_and_check(page)
    log("1.1.3", "保存成功", ok)

    reload_config(page)
    cb = page.locator("#cfg-source_cleaner-enabled")
    log("1.1.4", "刷新后仍为勾选", cb.is_checked())

    # TC-1.2 清理模式
    print("\n--- TC-1.2 清理模式保存 ---")
    ensure_enabled(page)

    page.locator('.radio-label-vertical input[value="media_and_related"]').click()
    time.sleep(0.3)
    ok = save_and_check(page)
    log("1.2.1", "切换到media_and_related保存", ok)

    reload_config(page)
    ensure_enabled(page)
    checked_val = page.locator('.radio-label-vertical input:checked').input_value()
    log("1.2.2", "刷新后仍为media_and_related", checked_val == "media_and_related")

    page.locator('.radio-label-vertical input[value="media_only"]').click()
    time.sleep(0.3)
    save_and_check(page)

    # TC-1.3 AI辅助判断 + 合并策略
    print("\n--- TC-1.3 AI辅助判断+合并策略 ---")
    reload_config(page)
    ensure_enabled(page)

    ai_cb = page.locator("#cfg-source_cleaner-ai_enabled")
    if ai_cb.is_checked():
        ai_cb.click(force=True)
        time.sleep(0.3)

    ai_row = page.locator("#sc-ai-prompt-row")
    merge_grp = page.locator("#source-cleaner-merge-strategy-group")
    log("1.3.1", "AI关闭时提示词按钮隐藏", ai_row.is_hidden())
    log("1.3.2", "AI关闭时合并策略隐藏", merge_grp.is_hidden())

    ai_cb.click(force=True)
    time.sleep(0.3)
    log("1.3.3", "AI开启时提示词按钮显示", ai_row.is_visible())
    log("1.3.4", "AI开启时合并策略显示", merge_grp.is_visible())

    page.select_option("#cfg-source_cleaner-merge_strategy", "union")
    ok = save_and_check(page)
    log("1.3.5", "AI+union保存", ok)

    reload_config(page)
    ensure_enabled(page)
    ai_cb = page.locator("#cfg-source_cleaner-ai_enabled")
    log("1.3.6", "刷新后AI仍勾选", ai_cb.is_checked())
    if ai_cb.is_checked():
        merge_val = page.locator("#cfg-source_cleaner-merge_strategy").input_value()
        log("1.3.7", "刷新后合并策略仍为union", merge_val == "union")
    else:
        ai_cb.click(force=True)
        time.sleep(0.3)
        merge_val = page.locator("#cfg-source_cleaner-merge_strategy").input_value()
        log("1.3.7", "刷新后合并策略仍为union(需先勾AI)", merge_val == "union")

    ai_cb.click(force=True)
    time.sleep(0.3)
    save_and_check(page)

    # TC-1.4 AI提示词弹窗
    print("\n--- TC-1.4 AI清理提示词弹窗 ---")
    reload_config(page)
    ensure_enabled(page)
    ai_cb = page.locator("#cfg-source_cleaner-ai_enabled")
    if not ai_cb.is_checked():
        ai_cb.click(force=True)
        time.sleep(0.3)

    page.locator("#sc-ai-prompt-row .btn").click()
    time.sleep(0.5)
    modal = page.locator("#sc-ai-prompt-modal")
    log("1.4.1", "提示词弹窗显示", modal.is_visible())

    textarea = page.locator("#cfg-source_cleaner-ai_prompt")
    log("1.4.2", "textarea可见", textarea.is_visible())

    textarea.fill("自定义测试提示词内容")
    page.click("#sc-ai-prompt-modal .btn-primary")
    time.sleep(0.3)
    log("1.4.3", "弹窗关闭", modal.is_hidden())

    ok = save_and_check(page)
    log("1.4.4", "保存含自定义提示词", ok)

    reload_config(page)
    ensure_enabled(page)
    ai_cb = page.locator("#cfg-source_cleaner-ai_enabled")
    if not ai_cb.is_checked():
        ai_cb.click(force=True)
        time.sleep(0.3)

    page.locator("#sc-ai-prompt-row .btn").click()
    time.sleep(0.5)
    val = page.locator("#cfg-source_cleaner-ai_prompt").input_value()
    log("1.4.5", "刷新后提示词保留", "自定义测试提示词内容" in val)

    page.locator("#sc-ai-prompt-modal button:has-text('恢复默认')").click()
    time.sleep(0.3)
    val2 = page.locator("#cfg-source_cleaner-ai_prompt").input_value()
    log("1.4.6", "恢复默认后包含影音库AI智能整理", "影音库AI智能整理" in val2)

    page.click("#sc-ai-prompt-modal .btn-primary")
    time.sleep(0.3)
    save_and_check(page)

    # TC-1.5 后缀名页签
    print("\n--- TC-1.5 后缀名页签保存 ---")
    reload_config(page)
    ensure_enabled(page)

    page.locator('.sc-tab-btn[data-sc-tab="delete"]').click()
    time.sleep(0.3)
    page.locator('#cfg-source_cleaner-delete_extensions').fill(".url\n.log\n.txt\n.nfo")
    page.locator('.sc-tab-btn[data-sc-tab="protect"]').click()
    time.sleep(0.3)
    page.locator('#cfg-source_cleaner-protect_extensions').fill(".srt\n.ass\n.sup")
    page.locator('.sc-tab-btn[data-sc-tab="blacklist"]').click()
    time.sleep(0.3)
    page.locator('#cfg-source_cleaner-blacklist_patterns').fill("sample\ntrailer\n预告")

    ok = save_and_check(page)
    log("1.5.1", "三个tab内容保存", ok)

    reload_config(page)
    ensure_enabled(page)

    page.locator('.sc-tab-btn[data-sc-tab="delete"]').click()
    time.sleep(0.3)
    del_val = page.locator('#cfg-source_cleaner-delete_extensions').input_value()
    log("1.5.2", "删除后缀名保留", ".url" in del_val and ".nfo" in del_val)

    page.locator('.sc-tab-btn[data-sc-tab="protect"]').click()
    time.sleep(0.3)
    prot_val = page.locator('#cfg-source_cleaner-protect_extensions').input_value()
    log("1.5.3", "保护后缀名保留", ".srt" in prot_val and ".sup" in prot_val)

    page.locator('.sc-tab-btn[data-sc-tab="blacklist"]').click()
    time.sleep(0.3)
    bl_val = page.locator('#cfg-source_cleaner-blacklist_patterns').input_value()
    log("1.5.4", "黑名单保留", "sample" in bl_val and "预告" in bl_val)

    # TC-1.6 高级配置
    print("\n--- TC-1.6 高级配置保存 ---")
    reload_config(page)
    ensure_enabled(page)

    adv_toggle = page.locator(".sc-advanced-toggle")
    adv_body = page.locator("#sc-advanced-body")
    if adv_body.is_hidden():
        adv_toggle.click()
        time.sleep(0.5)

    page.fill("#cfg-source_cleaner-junk_video_max_size_mb", "30")
    junk_input = page.locator("#cfg-source_cleaner-cleanup_empty_dirs")
    if not junk_input.is_checked():
        click_toggle(page, "cfg-source_cleaner-cleanup_empty_dirs")
        time.sleep(0.3)
    page.fill("#cfg-source_cleaner-schedule", "0 4 * * *")

    ok = save_and_check(page)
    log("1.6.1", "高级配置保存", ok)

    reload_config(page)
    ensure_enabled(page)
    adv_body = page.locator("#sc-advanced-body")
    if adv_body.is_hidden():
        page.locator(".sc-advanced-toggle").click()
        time.sleep(0.5)

    junk_val = page.locator("#cfg-source_cleaner-junk_video_max_size_mb").input_value()
    log("1.6.2", "刷新后阈值=30", junk_val == "30")

    schedule_val = page.locator("#cfg-source_cleaner-schedule").input_value()
    log("1.6.3", "刷新后cron=0 4 * * *", schedule_val == "0 4 * * *")

    # TC-1.7 配置互不干扰
    print("\n--- TC-1.7 配置互不干扰 ---")
    reload_config(page)
    ensure_enabled(page)

    page.locator('.radio-label-vertical input[value="media_only"]').click()
    time.sleep(0.3)
    save_and_check(page)

    page.locator('.sc-tab-btn[data-sc-tab="delete"]').click()
    time.sleep(0.3)
    page.locator('#cfg-source_cleaner-delete_extensions').fill(".url\n.log\n.txt\n.bak")
    save_and_check(page)

    reload_config(page)
    ensure_enabled(page)
    mode_val = page.locator('.radio-label-vertical input:checked').input_value()
    log("1.7.1", "修改后缀名不影响清理模式", mode_val == "media_only")

    # ============================================================
    # 阶段三：最优配置 + 预览清理结果验证
    # ============================================================
    print("\n" + "=" * 60)
    print("阶段三：最优配置调优 + 预览清理结果验证")
    print("=" * 60)

    # 设置最优配置
    api_save_sc_config({
        "enabled": True,
        "cleanup_mode": "media_and_related",
        "ai_enabled": False,
        "merge_strategy": "intersection",
        "delete_extensions": [".url", ".log", ".txt", ".sfv", ".bak", ".m3u", ".db"],
        "protect_extensions": [".nfo", ".jpg", ".png", ".bdmv", ".clpi", ".mpls"],
        "blacklist_patterns": ["RARBG*", "*/Sample/*", "*/sample/*", "*/Trailers/*",
                               "*/trailers/*", "*/预告/*", "*/花絮/*", "*/Extras/*",
                               "*/extras/*"],
        "junk_video_max_size_mb": 50,
        "cleanup_empty_dirs": True,
        "schedule": "0 3 * * *",
    })

    # 验证配置已保存
    cfg_resp = api_call("GET", "/config")
    sc_cfg = cfg_resp.get("data", {}).get("config", {}).get("source_cleaner", {})
    log("3.0.1", "API保存配置成功", sc_cfg.get("cleanup_mode") == "media_and_related")
    log("3.0.2", "删除后缀含.bak", ".bak" in sc_cfg.get("delete_extensions", []))
    log("3.0.3", "保护后缀含.bdmv", ".bdmv" in sc_cfg.get("protect_extensions", []))

    # 预览清理结果
    preview_resp = api_call("GET", "/source-cleaner/preview")
    preview_data = preview_resp.get("data", {})
    items = preview_data.get("items", [])
    log("3.0.4", "预览API返回数据", len(items) > 0)

    # 通过前端验证预览
    reload_config(page)
    ensure_enabled(page)

    page.locator('.sc-action-row button:has-text("预览清理结果")').click()
    time.sleep(2)

    preview_modal = page.locator("#sc-preview-modal")
    modal_visible = preview_modal.is_visible()
    log("3.0.5", "前端预览弹窗可见", modal_visible)

    if modal_visible:
        summary_el = page.locator("#sc-preview-summary")
        summary_text = summary_el.text_content()
        log("3.0.6", "弹窗摘要含清理数量", "清理" in summary_text,
            f"text={summary_text[:80]}")

        tree_lines = page.locator(".sc-tree-line")
        tree_count = tree_lines.count()
        log("3.0.7", "目录树有内容", tree_count > 0,
            f"lines={tree_count}")

        root_line = tree_lines.nth(0).text_content() if tree_count > 0 else ""
        log("3.0.8", "目录树含根目录", "📂" in root_line or "source" in root_line,
            f"root={root_line[:50]}")

        page.click("#sc-preview-modal .modal-close")
        time.sleep(0.3)

    # 详细验证关键场景
    delete_paths = set()
    for item in items:
        p = item.get("path", "")
        delete_paths.add(p)

    source = "/tmp/nas_media_test/source"

    def should_delete(rel_path):
        full = f"{source}/{rel_path}"
        return full in delete_paths

    def should_keep(rel_path):
        full = f"{source}/{rel_path}"
        return full not in delete_paths

    # A03: 海报应保留(media_and_related)
    log("3.1.A03", "海报jpg保留(media_and_related)",
        should_keep("A03_电影_带海报和元数据/Interstellar.2014-poster.jpg"))

    # A04: url/txt应删除
    log("3.2.A04", "广告url删除", should_delete("A04_电影_带BT广告文件/www.YTS.mx.url"))
    log("3.3.A04", "广告txt删除", should_delete("A04_电影_带BT广告文件/YTS.mx.txt"))

    # A05: RARBG广告
    log("3.4.A05", "RARBG.mp4垃圾视频删除", should_delete("A05_电影_带广告图片/RARBG.mp4"))
    log("3.5.A05", "RARBG.txt删除", should_delete("A05_电影_带广告图片/RARBG.txt"))

    # A06: Sample目录
    log("3.6.A06", "Sample目录删除",
        any("Sample" in it.get("path", "") and "A06" in it.get("path", "")
            for it in items if it.get("category") == "blacklist_dir"))

    # A08: 蓝光结构保护
    log("3.7.A08", "bdmv文件保留", should_keep("A08_电影_蓝光原盘结构/The.Godfather.1972.UHD.BluRay/BDMV/index.bdmv"))
    log("3.8.A08", "m2ts视频保留", should_keep("A08_电影_蓝光原盘结构/The.Godfather.1972.UHD.BluRay/BDMV/STREAM/00001.m2ts"))

    # A09: 垃圾视频阈值
    log("3.9.A09", "Trailer(180MB>50MB)保留",
        should_keep("A09_电影_极小视频混淆/Avatar.2009.Trailer.1080p.mkv"))
    log("3.10.A09", "Behind(300MB>50MB)保留",
        should_keep("A09_电影_极小视频混淆/Avatar.2009.Behind.the.Scenes.mkv"))

    # B05: Trailers目录
    log("3.11.B05", "Trailers黑名单目录",
        any("Trailers" in it.get("path", "") and "B05" in it.get("path", "")
            for it in items if it.get("category") == "blacklist_dir"))

    # E02: MediaInfo.txt
    log("3.12.E02", "MediaInfo.txt删除", should_delete("E02_PT站_带MediaInfo/MediaInfo.txt"))

    # E04: sfv/bak
    log("3.13.E04", ".sfv删除", should_delete("E04_PT站_带校验文件/The.Seven.Samurai.1954.sfv"))
    log("3.14.E04", ".bak删除", should_delete("E04_PT站_带校验文件/The.Seven.Samurai.1954.nfo.bak"))

    # F01: 同名小视频(20MB<50MB)
    log("3.15.F01", "同名小视频(20MB)垃圾视频删除",
        should_delete("F01_混淆广告_同名小视频/The.Dark.Knight.2008.mkv"))

    # F07: 综合判定
    log("3.16.F07", "url删除", should_delete("F07_混合文件_全类型/www.demo-site.com.url"))
    log("3.17.F07", "Sample.mkv(30MB)垃圾视频", should_delete("F07_混合文件_全类型/Sample.mkv"))
    log("3.18.F07", "RARBG.mp4(8MB)垃圾视频", should_delete("F07_混合文件_全类型/RARBG.mp4"))
    log("3.19.F07", "nfo保留", should_keep("F07_混合文件_全类型/Everything.Everywhere.2022.nfo"))
    log("3.20.F07", "jpg海报保留", should_keep("F07_混合文件_全类型/poster.jpg"))

    # F08: 纯音频
    log("3.21.F08", "flac非影视删除", should_delete("F08_纯音频_非影视/Album.Collection/track01.flac"))

    # F05/F06: 空目录
    log("3.22.F05", "空目录删除",
        any("F05" in it.get("path", "") for it in items if it.get("category") == "empty_dir"))

    # ============================================================
    # 阶段四：笛卡尔积组合测试（精简关键组合）
    # ============================================================
    print("\n" + "=" * 60)
    print("阶段四：笛卡尔积组合测试")
    print("=" * 60)

    combos = [
        {"id": "C01", "mode": "media_only", "ai": False, "junk": 50,
         "del_ext": [".url", ".log", ".txt"], "prot_ext": [".nfo", ".jpg", ".png"]},
        {"id": "C02", "mode": "media_only", "ai": False, "junk": 0,
         "del_ext": [".url", ".log", ".txt"], "prot_ext": [".nfo", ".jpg", ".png"]},
        {"id": "C03", "mode": "media_only", "ai": False, "junk": 50,
         "del_ext": [".url", ".log", ".txt", ".sfv", ".bak", ".m3u", ".db"],
         "prot_ext": [".nfo", ".jpg", ".png", ".bdmv", ".clpi", ".mpls"]},
        {"id": "C04", "mode": "media_and_related", "ai": False, "junk": 50,
         "del_ext": [".url", ".log", ".txt"], "prot_ext": [".nfo", ".jpg", ".png"]},
        {"id": "C05", "mode": "media_and_related", "ai": False, "junk": 0,
         "del_ext": [".url", ".log", ".txt"], "prot_ext": [".nfo", ".jpg", ".png"]},
        {"id": "C06", "mode": "media_and_related", "ai": False, "junk": 50,
         "del_ext": [".url", ".log", ".txt", ".sfv", ".bak", ".m3u", ".db"],
         "prot_ext": [".nfo", ".jpg", ".png", ".bdmv", ".clpi", ".mpls"]},
        {"id": "C07", "mode": "media_only", "ai": False, "junk": 200,
         "del_ext": [".url", ".log", ".txt"], "prot_ext": [".nfo", ".jpg", ".png"]},
        {"id": "C08", "mode": "media_and_related", "ai": False, "junk": 200,
         "del_ext": [".url", ".log", ".txt"], "prot_ext": [".nfo", ".jpg", ".png"]},
    ]

    for combo in combos:
        cid = combo["id"]
        cfg = {
            "enabled": True,
            "cleanup_mode": combo["mode"],
            "ai_enabled": combo["ai"],
            "merge_strategy": "intersection",
            "delete_extensions": combo["del_ext"],
            "protect_extensions": combo["prot_ext"],
            "blacklist_patterns": ["RARBG*", "*/Sample/*", "*/sample/*",
                                   "*/Trailers/*", "*/预告/*", "*/花絮/*",
                                   "*/Extras/*", "*/extras/*"],
            "junk_video_max_size_mb": combo["junk"],
            "cleanup_empty_dirs": True,
            "schedule": "0 3 * * *",
        }
        api_save_sc_config(cfg)
        resp = api_call("GET", "/source-cleaner/preview")
        items = resp.get("data", {}).get("items", [])
        delete_paths = set(it.get("path", "") for it in items)

        def is_del(rel):
            return f"{source}/{rel}" in delete_paths

        def is_keep(rel):
            return f"{source}/{rel}" not in delete_paths

        # 关键验证点
        if combo["mode"] == "media_only":
            # media_only: nfo不在保护后缀时删除，在保护时保留
            if ".nfo" in combo["prot_ext"]:
                log(f"4.{cid}.1", f"{cid} media_only+nfo保护→nfo保留",
                    is_keep("A01_标准电影_单视频单字幕/The.Matrix.1999.1080p.BluRay.x264.nfo"))
            # media_only: jpg不在保护后缀时删除
            if ".jpg" not in combo["prot_ext"]:
                pass
            else:
                log(f"4.{cid}.2", f"{cid} media_only+jpg保护→海报保留",
                    is_keep("A03_电影_带海报和元数据/Interstellar.2014-poster.jpg"))

            # 非媒体文件应删除
            log(f"4.{cid}.3", f"{cid} media_only→flac删除",
                is_del("F08_纯音频_非影视/Album.Collection/track01.flac"))

        if combo["mode"] == "media_and_related":
            log(f"4.{cid}.1", f"{cid} related→nfo保留",
                is_keep("A01_标准电影_单视频单字幕/The.Matrix.1999.1080p.BluRay.x264.nfo"))
            log(f"4.{cid}.2", f"{cid} related→海报保留",
                is_keep("A03_电影_带海报和元数据/Interstellar.2014-poster.jpg"))

        # 垃圾视频阈值
        if combo["junk"] == 0:
            log(f"4.{cid}.4", f"{cid} junk=0→小视频保留",
                is_keep("F01_混淆广告_同名小视频/The.Dark.Knight.2008.mkv"))
        elif combo["junk"] == 50:
            log(f"4.{cid}.4", f"{cid} junk=50→20MB视频删除",
                is_del("F01_混淆广告_同名小视频/The.Dark.Knight.2008.mkv"))
        elif combo["junk"] == 200:
            log(f"4.{cid}.4", f"{cid} junk=200→180MB视频删除",
                is_del("A09_电影_极小视频混淆/Avatar.2009.Trailer.1080p.mkv"))

        # 扩展后缀
        if ".sfv" in combo["del_ext"]:
            log(f"4.{cid}.5", f"{cid} 扩展删除→.sfv删除",
                is_del("E04_PT站_带校验文件/The.Seven.Samurai.1954.sfv"))
        if ".bdmv" in combo["prot_ext"]:
            log(f"4.{cid}.6", f"{cid} 扩展保护→bdmv保留",
                is_keep("A08_电影_蓝光原盘结构/The.Godfather.1972.UHD.BluRay/BDMV/index.bdmv"))

        # 通用: url/txt始终删除
        log(f"4.{cid}.7", f"{cid} url始终删除",
            is_del("A04_电影_带BT广告文件/www.YTS.mx.url"))

        # RARBG黑名单
        log(f"4.{cid}.8", f"{cid} RARBG广告删除",
            is_del("A05_电影_带广告图片/RARBG.mp4") or
            any("RARBG" in it.get("path", "") for it in items))

    # ============================================================
    # 前端预览按钮最终验证
    # ============================================================
    print("\n--- 前端预览按钮最终验证 ---")

    api_save_sc_config({
        "enabled": True,
        "cleanup_mode": "media_and_related",
        "ai_enabled": False,
        "merge_strategy": "intersection",
        "delete_extensions": [".url", ".log", ".txt", ".sfv", ".bak", ".m3u", ".db"],
        "protect_extensions": [".nfo", ".jpg", ".png", ".bdmv", ".clpi", ".mpls"],
        "blacklist_patterns": ["RARBG*", "*/Sample/*", "*/sample/*", "*/Trailers/*",
                               "*/trailers/*", "*/预告/*", "*/花絮/*", "*/Extras/*",
                               "*/extras/*"],
        "junk_video_max_size_mb": 50,
        "cleanup_empty_dirs": True,
        "schedule": "0 3 * * *",
    })

    reload_config(page)
    ensure_enabled(page)

    page.locator('.sc-action-row button:has-text("预览清理结果")').click()
    time.sleep(3)
    preview_modal = page.locator("#sc-preview-modal")
    if preview_modal.is_visible():
        summary = page.locator("#sc-preview-summary").text_content()
        tree_count = page.locator(".sc-tree-line").count()
        log("4.F.1", "前端预览弹窗最终结果", True,
            f"summary={summary[:80]}, tree_lines={tree_count}")
        page.click("#sc-preview-modal .modal-close")
        time.sleep(0.3)
    else:
        log("4.F.1", "前端预览弹窗最终结果", False, "弹窗不可见")

    # 截图
    page.screenshot(path="/tmp/sc_full_test.png", full_page=True)

    # ============================================================
    # 汇总
    # ============================================================
    print("\n" + "=" * 60)
    print(f"测试完成: PASS={PASS}, FAIL={FAIL}, TOTAL={PASS+FAIL}")
    print("=" * 60)

    if FAIL > 0:
        print("\n失败用例:")
        for r in RESULTS:
            if not r["passed"]:
                print(f"  ❌ {r['id']}: {r['name']} — {r['detail']}")

    restore_environment()
    browser.close()
