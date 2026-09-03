"""Provider 维度映射界面合同。

Requirement: REQ-20260901-233114
"""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DIMENSION_GENRE = (ROOT / "media_importer/webui/js/dimension-genre.js").read_text(
    encoding="utf-8"
)
DIMENSION_MAPPING = (
    ROOT / "media_importer/webui/js/dimension-mapping.js"
).read_text(encoding="utf-8")
DIMENSION_MAPPING_CSS = (
    ROOT / "media_importer/webui/css/dimension-mapping.css"
).read_text(encoding="utf-8")
INDEX_HTML = (ROOT / "media_importer/webui/index.html").read_text(encoding="utf-8")


def test_dimension_renderer_has_no_retired_trust_html_reference():
    assert "trustHtml" not in DIMENSION_GENRE


def test_mapping_editor_is_explicit_non_dismissible_and_preserves_failed_draft():
    assert 'dismissOnBackdrop: false' in DIMENSION_MAPPING
    assert 'closeOnClick: false' in DIMENSION_MAPPING
    assert "已保留当前填写内容" in DIMENSION_MAPPING
    assert "data-map-preview" in DIMENSION_MAPPING
    assert "dimension-mapping.js" in INDEX_HTML


def test_mapping_editor_uses_product_dropdown_instead_of_native_selects():
    assert "<select" not in DIMENSION_MAPPING
    assert 'role="combobox"' in DIMENSION_MAPPING
    assert 'role="listbox"' in DIMENSION_MAPPING
    assert "data-map-select-option" in DIMENSION_MAPPING
    assert "_handleMappingSelectKeydown" in DIMENSION_MAPPING
    assert 'event.key === "Escape"' in DIMENSION_MAPPING
    assert 'control.classList.add("opens-up")' in DIMENSION_MAPPING
    assert ".provider-map-select-panel" in DIMENSION_MAPPING_CSS
    assert ".provider-map-select.opens-up" in DIMENSION_MAPPING_CSS
    assert ".provider-map-select-option.is-selected" in DIMENSION_MAPPING_CSS


def test_media_candidate_filter_is_default_collapsed_and_has_plain_language_controls():
    assert '<details class="form-card form-card-full media-candidate-settings">' in INDEX_HTML
    assert "忽略明显广告和小视频片段" in INDEX_HTML
    assert "cfg-media-candidate-small-max-inline" in INDEX_HTML
    assert "cfg-media-candidate-ratio-inline" in INDEX_HTML
    assert "cfg-media-candidate-patterns-inline" in INDEX_HTML
