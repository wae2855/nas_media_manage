from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
README = (ROOT / "README.md").read_text(encoding="utf-8")


def test_readme_explains_product_install_safety_and_contribution():
    required_sections = (
        "## 主要功能",
        "## 适用范围与限制",
        "## fnOS 安装",
        "## 本地开发",
        "## 文件安全边界",
        "## 参与贡献",
        "## 支持项目",
        "## 许可证",
    )

    for section in required_sections:
        assert section in README

    assert "不使用 AI 猜测影片身份" in README
    assert "来源直达目标侧任务暂存" in README
    assert "默认不覆盖" in README
    assert "LOCAL_BUILD PASS" in README


def test_readme_uses_product_support_qr_assets_with_alt_text():
    assets = {
        "media_importer/webui/assets/support/developer-reward-qr.png": (
            "支持独立开发者的微信赞赏二维码"
        ),
        "media_importer/webui/assets/support/developer-wechat-qr.png": (
            "添加项目维护者微信的二维码"
        ),
    }

    for relative_path, alt_text in assets.items():
        assert (ROOT / relative_path).is_file()
        assert f'src="{relative_path}"' in README
        assert f'alt="{alt_text}"' in README

    assert "赞助不会解锁额外功能" in README


def test_readme_uses_desktop_and_mobile_screenshots_with_alt_text():
    screenshots = {
        "screenshots/pc-001.png": "桌面端任务工作台",
        "screenshots/pc-002.png": "桌面端片库总览",
        "screenshots/pc-003.png": "桌面端片库搭建向导",
        "screenshots/IMG_1836.PNG": "移动端片库总览",
        "screenshots/IMG_1837.PNG": "移动端任务工作台",
        "screenshots/IMG_1838.PNG": "移动端片库搭建向导",
    }

    assert "## 界面预览" in README
    assert "fnOS 真机验收通过的 `v0.3.34`" in README
    for relative_path, alt_prefix in screenshots.items():
        assert (ROOT / relative_path).is_file()
        assert f'src="{relative_path}"' in README
        assert f'alt="{alt_prefix}' in README


def test_readme_and_license_are_ready_for_public_distribution():
    license_text = (ROOT / "LICENSE").read_text(encoding="utf-8")

    assert "MIT License" in license_text
    assert "Copyright (c) 2026 wae2855" in license_text
    assert "扫描 → 复制到 temp" not in README
    assert "AI 刮削" not in README
    assert "Hermes" not in README
    assert "/Users/" not in README
    assert "config/config.yaml" in README
