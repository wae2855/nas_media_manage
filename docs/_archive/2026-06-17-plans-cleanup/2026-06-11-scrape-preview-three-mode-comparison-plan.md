# 配置模拟测试三模式并列对比 - 详细改造计划

## 1. 目标

将当前"配置模拟测试"界面从时间线纵向两列（纯AI + Provider+AI）改造为三模式横向并列对比（provider_first / ai_only / hybrid），每列独立展示刮削结果、置信度、计算过程、AI搜索增强标记。

## 2. 决策确认

| 决策点 | 结论 |
|--------|------|
| AI 未配置时 ai_only/hybrid 是否展示 | 始终展示，未配置时显示"AI 未配置，无法执行" |
| 并行还是串行 | 三个模式并行执行 |
| 置信度计算过程展示 | 内联展示简化公式 + 关键分解值，复杂详情仍可点击弹窗 |
| 底部对比总结 | 保留，给出推荐模式 |

## 3. 涉及文件清单

| 文件 | 改动类型 | 说明 |
|------|----------|------|
| `media_importer/scraper/metadata_scrape_flow.py` | 修改 | `scrape_metadata()` 新增 `force_mode` 参数 |
| `media_importer/api/tmdb_handlers.py` | 修改 | `_scrape_preview()` 三模式并行 + 新返回结构 |
| `media_importer/features/scraping/confidence_engine.py` | 修改 | `calculate()` / `calculate_ai_only()` 返回 `confidence_detail` |
| `media_importer/webui/partials/advanced-pages.html` | 修改 | 模拟测试区域 HTML 结构调整 |
| `media_importer/webui/js/cinema-config.js` | 修改 | `renderSimulatorPreview()` 重写 |
| `media_importer/webui/css/cinema-confidence.css` | 修改 | 新增三列布局样式，保留现有样式 |
| `tests/test_scrape_preview.py` | 新增 | 三模式预览 API 测试 |

## 4. 后端改造

### 4.1 `scrape_metadata()` 新增 `force_mode` 参数

**文件**：`media_importer/scraper/metadata_scrape_flow.py`

**改动位置**：`scrape_metadata()` 函数签名和分发逻辑（L193-226）

**改动内容**：

```python
def scrape_metadata(scraper, video_filename: str, subtitle_filenames: List[str] = None,
                    conn=None, force_mode: Optional[str] = None) -> Dict[str, Any]:
    """Dispatch to the appropriate scrape mode handler.

    Args:
        force_mode: If set, overrides the configured scrape_mode.
                    Must be one of 'provider_first', 'ai_only', 'hybrid'.
                    Used by scrape_preview API to test all modes independently.
    """
    log = logging.getLogger(__name__)
    if subtitle_filenames is None:
        subtitle_filenames = []

    if force_mode is not None and force_mode in VALID_SCRAPE_MODES:
        scrape_mode = force_mode
    else:
        scrape_mode = getattr(scraper.view.metadata, "scrape_mode", "hybrid")
        if scrape_mode not in VALID_SCRAPE_MODES:
            scrape_mode = "hybrid"

    ai_available = bool(scraper.llm_scraper.enabled)

    # 降级逻辑：force_mode 为 ai_only/hybrid 但 AI 不可用时，返回错误标记而非降级
    if force_mode is not None and scrape_mode in ("ai_only", "hybrid") and not ai_available:
        log.warning(
            f"[metadata_scraper] force_mode={force_mode} but AI not configured"
        )
        return {
            "error": "AI 刮削未配置",
            "title": "",
            "year": None,
            "media_type": "movie",
            "confidence": 0,
            "scrape_trace": {
                "scrape_mode": force_mode,
                "ai_invoked": False,
                "ai_invoke_reason": "AI未配置",
            },
        }

    # 非 force_mode 的降级逻辑保持不变
    if scrape_mode in ("ai_only", "hybrid") and not ai_available:
        log.warning(...)
        # 原有降级逻辑
        ...

    if scrape_mode == "ai_only":
        return _scrape_ai_only(scraper, video_filename, subtitle_filenames, conn)
    elif scrape_mode == "provider_first":
        return _scrape_provider_first(scraper, video_filename, subtitle_filenames, conn)
    else:
        return _scrape_hybrid(scraper, video_filename, subtitle_filenames, conn)
```

**要点**：
- `force_mode` 为 `None` 时行为完全不变，保证向后兼容
- `force_mode` 指定了 AI 模式但 AI 不可用时，不降级，而是返回带 `error` 字段的结果
- 需要 `from typing import Optional`（文件顶部已有）

### 4.2 `MetadataScraper.scrape()` 透传 `force_mode`

**文件**：`media_importer/features/scraping/metadata_scraper.py`

**改动位置**：`scrape()` 方法（L308-310）

**改动内容**：

```python
def scrape(self, video_filename: str, subtitle_filenames: List[str] = None,
           conn=None, force_mode: Optional[str] = None) -> Dict[str, Any]:
    return scrape_metadata(self, video_filename, subtitle_filenames, conn, force_mode=force_mode)
```

### 4.3 置信度引擎返回 `confidence_detail`

**文件**：`media_importer/features/scraping/confidence_engine.py`

**改动位置**：`calculate()` 方法（L180-260）和 `calculate_ai_only()` 方法（L262-334）

**改动内容**：在 `ConfidenceResult` 中新增 `confidence_detail` 字段，包含公式分解值。

**`calculate()` 方法**（Provider 路径）：

```python
# 在 return ConfidenceResult(...) 之前，新增：
confidence_detail = {
    "formula": "T × R × data_gate",
    "T": round(T, 4),
    "R": round(R, 4),
    "R_formula": R_formula,
    "R_base": round(R_base, 4),
    "total_results": total_results,
    "search_conf": round(search_conf, 4),
    "data_gate": data_gate,
    "gate_blocked": gate_blocked is not None,
    "final_confidence": final_confidence,
}

return ConfidenceResult(
    ...
    confidence_detail=confidence_detail,  # 新增
)
```

**`calculate_ai_only()` 方法**（AI 路径）：

```python
# 在 return ConfidenceResult(...) 之前，新增：
confidence_detail = {
    "formula": "objective_cap × data_gate",
    "objective_cap": round(objective_cap, 4),
    "clean_title": clean_result.clean_title,
    "llm_title": llm_title,
    "data_gate": data_gate,
    "gate_blocked": gate_blocked is not None,
    "final_confidence": final_confidence,
}

return ConfidenceResult(
    ...
    confidence_detail=confidence_detail,  # 新增
)
```

**`ConfidenceResult` dataclass**（`confidence_models.py`）：

```python
@dataclass
class ConfidenceResult:
    final_confidence: float
    search_conf: float = 0.0
    data_conf: float = 1.0
    data_gate: float = 1.0
    gate_blocked: Optional[Dict[str, Any]] = None
    veto: Optional[Dict[str, Any]] = None
    llm_raw_confidence: Optional[float] = None
    dimensions: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    scrape_trace: Dict[str, Any] = field(default_factory=dict)
    confidence_detail: Dict[str, Any] = field(default_factory=dict)  # 新增
```

### 4.4 `_scrape_preview` API 改造

**文件**：`media_importer/api/tmdb_handlers.py`

**改动位置**：`_scrape_preview()` 方法（L234-348），整体重写

**改动内容**：

```python
def _scrape_preview(self, body: dict):
    filename = (body or {}).get("filename", "").strip()

    if not filename:
        json_response(self, 400, message="请输入视频文件名")
        return

    from media_importer.features.scraping import LLMScraper
    from media_importer.features.scraping import MetadataScraper
    from media_importer.features.scraping import FilenameCleaner
    from media_importer.features.providers import create_providers

    logger = globals._global_logger
    cleaner = FilenameCleaner()
    clean_result = cleaner.clean(filename)

    providers = create_providers(globals._config)
    provider_enabled = bool(providers)

    llm_config = globals._config.get("llm", {}) if globals._config else {}
    llm_timeout = int(llm_config.get("timeout", 30))
    llm_max_retries = int(llm_config.get("max_retries", 2))
    preview_timeout = (llm_max_retries + 1) * llm_timeout + 15

    current_mode = globals._config.get("metadata", {}).get("scrape_mode", "hybrid") \
        if globals._config else "hybrid"

    if logger:
        logger.info(f"[scrape_preview] 开始: filename={filename}, "
                    f"provider_enabled={provider_enabled}, current_mode={current_mode}")

    # ---- 三个模式的任务定义 ----

    def _run_provider_first():
        try:
            if logger:
                logger.info("[scrape_preview] provider_first 开始")
            metadata_scraper = MetadataScraper(globals._config)
            conn = getattr(globals._global_task_manager, 'conn', None) \
                if globals._global_task_manager else None
            t0 = time.time()
            result = metadata_scraper.scrape(filename, conn=conn,
                                             force_mode="provider_first")
            elapsed = round(time.time() - t0, 2)
            if logger:
                logger.info(f"[scrape_preview] provider_first 完成: {elapsed}s")
            return result, elapsed
        except Exception as e:
            if logger:
                logger.error(f"[scrape_preview] provider_first 异常: {e}")
            return {"error": str(e)}, 0

    def _run_ai_only():
        try:
            if logger:
                logger.info("[scrape_preview] ai_only 开始")
            llm_scraper = LLMScraper(globals._config)
            if not llm_scraper.enabled:
                return {
                    "error": "AI 刮削未配置，请在 AI 配置页中启用并填写 API Key",
                    "title": "",
                    "year": None,
                    "media_type": "movie",
                    "confidence": 0,
                    "scrape_trace": {"scrape_mode": "ai_only", "ai_invoked": False,
                                     "ai_invoke_reason": "AI未配置"},
                }, 0
            t0 = time.time()
            result = llm_scraper.scrape(filename)
            elapsed = round(time.time() - t0, 2)
            if logger:
                logger.info(f"[scrape_preview] ai_only 完成: {elapsed}s")
            return result, elapsed
        except Exception as e:
            if logger:
                logger.error(f"[scrape_preview] ai_only 异常: {e}")
            return {"error": str(e)}, 0

    def _run_hybrid():
        try:
            if logger:
                logger.info("[scrape_preview] hybrid 开始")
            metadata_scraper = MetadataScraper(globals._config)
            conn = getattr(globals._global_task_manager, 'conn', None) \
                if globals._global_task_manager else None
            t0 = time.time()
            result = metadata_scraper.scrape(filename, conn=conn,
                                             force_mode="hybrid")
            elapsed = round(time.time() - t0, 2)
            if logger:
                logger.info(f"[scrape_preview] hybrid 完成: {elapsed}s")
            return result, elapsed
        except Exception as e:
            if logger:
                logger.error(f"[scrape_preview] hybrid 异常: {e}")
            return {"error": str(e)}, 0

    # ---- 三任务并行 ----
    executor = ThreadPoolExecutor(max_workers=3)
    modes_result = {}
    try:
        futures = {
            "provider_first": executor.submit(_run_provider_first),
            "ai_only": executor.submit(_run_ai_only),
            "hybrid": executor.submit(_run_hybrid),
        }

        for mode_key, future in futures.items():
            try:
                result, elapsed = future.result(timeout=preview_timeout)
                modes_result[mode_key] = {
                    "result": result,
                    "elapsed": elapsed,
                }
            except FuturesTimeout:
                if logger:
                    logger.warning(f"[scrape_preview] {mode_key} 超时 ({preview_timeout}s)")
                modes_result[mode_key] = {
                    "result": {"error": f"{mode_key} 刮削超时（{preview_timeout} 秒）"},
                    "elapsed": preview_timeout,
                }
            except Exception as e:
                if logger:
                    logger.error(f"[scrape_preview] {mode_key} 异常: {e}")
                modes_result[mode_key] = {
                    "result": {"error": str(e)},
                    "elapsed": 0,
                }
    finally:
        executor.shutdown(wait=False)

    # ---- 提取各模式的 confidence_detail ----
    for mode_key in modes_result:
        result = modes_result[mode_key]["result"]
        if result and not result.get("error"):
            # 从 scrape_trace 中提取 confidence_detail
            trace = result.get("scrape_trace", {})
            confidence_calc = trace.get("confidence_calc", {})
            modes_result[mode_key]["confidence_detail"] = {
                "formula": confidence_calc.get("formula", ""),
                "final_confidence": confidence_calc.get("final_confidence",
                                                        result.get("confidence", 0)),
                "search_conf": result.get("confidence_search"),
                "data_gate": result.get("confidence_data_gate"),
                "detail": confidence_calc,
            }
            # AI 相关标记
            modes_result[mode_key]["ai_invoked"] = trace.get("ai_invoked", False)
            modes_result[mode_key]["ai_invoke_reason"] = trace.get("ai_invoke_reason")
            modes_result[mode_key]["search_enhanced"] = result.get("search_enhanced",
                trace.get("search_enhanced", False))
            modes_result[mode_key]["provider_type"] = result.get("provider_type", "")
            modes_result[mode_key]["provider_id"] = result.get("provider_id", "")

    # ---- 推荐最佳模式 ----
    best_mode = None
    best_confidence = -1
    for mode_key in ["provider_first", "ai_only", "hybrid"]:
        r = modes_result.get(mode_key, {}).get("result", {})
        if r and not r.get("error"):
            conf = r.get("confidence", 0)
            if isinstance(conf, (int, float)) and conf > best_confidence:
                best_confidence = conf
                best_mode = mode_key

    recommendation = None
    if best_mode:
        recommendation = {
            "best_mode": best_mode,
            "best_confidence": round(best_confidence, 4),
            "reason": _build_recommendation_reason(best_mode, best_confidence, modes_result),
        }

    if logger:
        logger.info(f"[scrape_preview] 完成")

    json_response(self, 200, data={
        "filename": filename,
        "clean_result": {
            "clean_title": clean_result.clean_title,
            "year": clean_result.year,
            "season": clean_result.season,
            "episode": clean_result.episode,
            "method": clean_result.method,
            "removed_items": clean_result.removed_items,
        },
        "modes": modes_result,
        "current_mode": current_mode,
        "recommendation": recommendation,
    })


def _build_recommendation_reason(best_mode, best_confidence, modes_result):
    """构建推荐理由文本。"""
    reasons = {
        "provider_first": "置信度最高且优先使用 Provider，AI 调用最少，成本最低",
        "ai_only": "纯 AI 刮削置信度最高，适合冷门影片或 Provider 数据不完整的场景",
        "hybrid": "联合刮削置信度最高，数据最完整，但 API 调用成本较高",
    }
    return reasons.get(best_mode, "")
```

**注意**：`_build_recommendation_reason` 是新增的模块级辅助函数，放在 `_scrape_preview` 方法之前或之后。

### 4.5 API 返回结构

```json
{
  "code": 200,
  "data": {
    "filename": "Dune.Part.Two.2024.1080p.BluRay.x265.mkv",
    "clean_result": {
      "clean_title": "Dune Part Two",
      "year": 2024,
      "season": null,
      "episode": null,
      "method": "regex",
      "removed_items": ["1080p", "BluRay", "x265"]
    },
    "modes": {
      "provider_first": {
        "result": {
          "title_cn": "沙丘2",
          "title_en": "Dune: Part Two",
          "year": 2024,
          "type": "movie",
          "confidence": 0.92,
          "dimensions": { "genre": {...}, "rating": {...} },
          "scrape_trace": { "scrape_mode": "provider_first", "ai_invoked": false, ... },
          "provider_type": "tmdb",
          "provider_id": "693134",
          "poster_url": "https://..."
        },
        "elapsed": 3.2,
        "ai_invoked": false,
        "ai_invoke_reason": null,
        "search_enhanced": false,
        "provider_type": "tmdb",
        "confidence_detail": {
          "formula": "T × R × data_gate",
          "final_confidence": 0.92,
          "search_conf": 0.92,
          "data_gate": 1.0,
          "detail": { "T": 0.92, "R": 1.0, "R_formula": "log", ... }
        }
      },
      "ai_only": {
        "result": { ... },
        "elapsed": 2.1,
        "ai_invoked": true,
        "search_enhanced": true,
        "confidence_detail": {
          "formula": "objective_cap × data_gate",
          "final_confidence": 0.75,
          "detail": { "objective_cap": 0.75, "clean_title": "...", "llm_title": "...", ... }
        }
      },
      "hybrid": {
        "result": { ... },
        "elapsed": 5.4,
        "ai_invoked": true,
        "search_enhanced": false,
        "provider_type": "tmdb",
        "confidence_detail": { ... }
      }
    },
    "current_mode": "provider_first",
    "recommendation": {
      "best_mode": "provider_first",
      "best_confidence": 0.92,
      "reason": "置信度最高且优先使用 Provider，AI 调用最少，成本最低"
    }
  }
}
```

## 5. 前端改造

### 5.1 HTML 结构调整

**文件**：`media_importer/webui/partials/advanced-pages.html`

**改动位置**：`data-view="config-simulator"` 区域（L56-112）

**改动内容**：将模拟测试区域改为三列卡片布局。

```html
<section class="page-view" data-view="config-simulator">
    <div class="page-hero">
        <div>
            <div class="eyebrow">高级配置工具</div>
            <h2>配置模拟测试</h2>
            <div class="path-breadcrumb" aria-label="当前路径">
                <span>系统配置</span><i>/</i><span>高级配置</span><i>/</i><strong>模拟测试</strong>
            </div>
            <p>输入文件名，横向对比三种刮削模式的完整结果，再决定使用哪种模式。</p>
        </div>
        <div class="hero-action-group">
            <button class="btn btn-secondary" data-nav="config" data-view-target="advanced-config">返回高级配置</button>
        </div>
    </div>
    <section class="config-panel advanced-host-panel confidence-simulator-page">
        <div class="config-form-grid">
            <article class="form-card form-card-full config-guide-card">
                <span>这一页先做什么</span>
                <div class="config-guide-list compact">
                    <div>
                        <div class="start-directory-head">
                            <span class="start-directory-icon"><svg class="icon icon-sm" viewBox="0 0 24 24" aria-hidden="true"><use href="#icon-check"></use></svg></span>
                            <b>输入真实文件名</b>
                        </div>
                        <small>三种模式会同时跑一遍，横向对比刮削结果和置信度。</small>
                    </div>
                    <div>
                        <div class="start-directory-head">
                            <span class="start-directory-icon"><svg class="icon icon-sm" viewBox="0 0 24 24" aria-hidden="true"><use href="#icon-sliders"></use></svg></span>
                            <b>对比三种模式</b>
                        </div>
                        <small>Provider 优先、纯 AI、联合刮削，看哪个模式在你的文件上表现最好。</small>
                    </div>
                    <div>
                        <div class="start-directory-head">
                            <span class="start-directory-icon"><svg class="icon icon-sm" viewBox="0 0 24 24" aria-hidden="true"><use href="#icon-retry"></use></svg></span>
                            <b>有偏差就回去微调</b>
                        </div>
                        <small>调整提示词、置信度阈值或 Provider 配置后回来重跑。</small>
                    </div>
                </div>
            </article>
        </div>
        <article class="confidence-simulator">
            <div>
                <span class="confidence-kicker">三模式对比</span>
                <h3>输入一个文件名，横向对比三种刮削模式</h3>
                <p>Provider 优先 / 纯 AI 刮削 / Provider+AI 联合，三种模式同时执行，对比置信度和入库决策。</p>
            </div>
            <div class="confidence-sim-row">
                <input id="confidence-sim-filename" type="text" placeholder="例如：Dune.Part.Two.2024.1080p.mkv">
                <button class="btn btn-primary" type="button" id="btn-confidence-simulate">开始对比</button>
            </div>
            <div class="confidence-sim-result" id="confidence-sim-result">
                输入文件名后，三种刮削模式将同时执行并横向对比展示。
            </div>
        </article>
    </section>
</section>
```

### 5.2 JS 渲染逻辑重写

**文件**：`media_importer/webui/js/cinema-config.js`

**改动位置**：`renderSimulatorPreview()` 函数（L1322-1437），整体重写

**改动内容**：

```javascript
function renderSimulatorPreview(data) {
    const result = document.getElementById("confidence-sim-result");
    if (!result) return;

    const clean = data.clean_result || {};
    const modes = data.modes || {};
    const currentMode = data.current_mode || "hybrid";
    const recommendation = data.recommendation;

    // ---- 顶部：清洗结果 ----
    const removedStr = (clean.removed_items && clean.removed_items.length > 0)
        ? clean.removed_items.join(" · ") : "—";

    let html = '<div class="sim-compare">';

    // 清洗结果摘要
    html += '<div class="sim-clean-summary">';
    html += '<div class="sim-clean-title">文件名清洗结果</div>';
    html += '<div class="sim-clean-grid">';
    html += `<div class="sim-clean-item"><span class="sim-clean-label">clean_title</span><span class="sim-clean-value">${escapeHtml(clean.clean_title || "—")}</span></div>`;
    html += `<div class="sim-clean-item"><span class="sim-clean-label">year</span><span class="sim-clean-value">${clean.year || "—"}</span></div>`;
    html += `<div class="sim-clean-item"><span class="sim-clean-label">season / episode</span><span class="sim-clean-value">${clean.season ? "S" + clean.season : "—"} / ${clean.episode ? "E" + clean.episode : "—"}</span></div>`;
    html += `<div class="sim-clean-item"><span class="sim-clean-label">method</span><span class="sim-clean-value">${escapeHtml(clean.method || "regex")}</span></div>`;
    html += `<div class="sim-clean-item sim-clean-full"><span class="sim-clean-label">去除项</span><span class="sim-clean-value">${escapeHtml(removedStr)}</span></div>`;
    html += '</div></div>';

    // ---- 三列模式卡片 ----
    html += '<div class="sim-modes-grid">';

    const modeDefs = [
        { key: "provider_first", label: "Provider 优先", icon: "🔍", desc: "Provider 权威，AI 仅补缺", formula: "T × R × data_gate" },
        { key: "ai_only", label: "纯 AI 刮削", icon: "🤖", desc: "完全依赖 LLM", formula: "objective_cap × data_gate" },
        { key: "hybrid", label: "Provider + AI 联合", icon: "🔗", desc: "两者全量联合", formula: "T × R × data_gate" },
    ];

    for (const def of modeDefs) {
        const modeData = modes[def.key] || {};
        const res = modeData.result || {};
        const hasError = !!res.error;
        const isCurrent = def.key === currentMode;
        const score = Number(res.confidence);
        const hasScore = Number.isFinite(score);
        const cd = modeData.confidence_detail || {};

        html += '<div class="sim-mode-card' + (isCurrent ? ' sim-mode-current' : '') + (hasError ? ' sim-mode-error' : '') + '">';

        // 卡片头部
        html += '<div class="sim-mode-head">';
        html += `<span class="sim-mode-icon">${def.icon}</span>`;
        html += '<div class="sim-mode-head-text">';
        html += `<span class="sim-mode-label">${def.label}</span>`;
        if (isCurrent) {
            html += '<span class="sim-mode-badge">当前配置</span>';
        }
        html += `<span class="sim-mode-desc">${def.desc}</span>`;
        html += '</div></div>';

        if (hasError) {
            // 错误状态
            html += '<div class="sim-mode-body">';
            html += `<div class="sim-mode-error-msg">⚠ ${escapeHtml(res.error)}</div>`;
            html += '</div>';
        } else {
            // 正常结果
            html += '<div class="sim-mode-body">';

            // 刮削结果
            html += '<div class="sim-mode-result">';
            html += `<div class="sim-mode-field"><span class="sim-mode-fk">标题</span><span class="sim-mode-fv">${escapeHtml(res.title_cn || res.title_en || res.title || "—")}</span></div>`;
            if (res.title_en && res.title_cn && res.title_en !== res.title_cn) {
                html += `<div class="sim-mode-field"><span class="sim-mode-fk">英文</span><span class="sim-mode-fv sim-mode-fv-sub">${escapeHtml(res.title_en)}</span></div>`;
            }
            html += `<div class="sim-mode-field"><span class="sim-mode-fk">年份</span><span class="sim-mode-fv">${res.year || "—"}</span></div>`;
            html += `<div class="sim-mode-field"><span class="sim-mode-fk">类型</span><span class="sim-mode-fv">${res.type || "—"}</span></div>`;

            // Provider 信息
            if (modeData.provider_type) {
                html += `<div class="sim-mode-field"><span class="sim-mode-fk">Provider</span><span class="sim-mode-fv">${escapeHtml(modeData.provider_type)}${modeData.provider_id ? " · " + modeData.provider_id : ""}</span></div>`;
            }

            // 维度标签
            if (res.dimensions) {
                html += '<div class="sim-mode-dims">' + _renderSimDims(res.dimensions) + '</div>';
            }
            html += '</div>';

            // 置信度 + 决策
            html += '<div class="sim-mode-confidence">';
            html += `<span class="sim-mode-score" style="color:${_simConfColor(score)}">${hasScore ? score.toFixed(3) : "--"}</span>`;
            html += `<span class="sim-mode-decision" style="color:${_simConfColor(score)}">${_simDecisionLabel(score, res.confidence_gate_blocked)}</span>`;
            html += '</div>';

            // 置信度计算过程（内联）
            html += '<div class="sim-mode-calc">';
            html += `<span class="sim-mode-formula">公式：${escapeHtml(cd.formula || def.formula)}</span>`;
            if (cd.detail) {
                if (cd.detail.T !== undefined) {
                    html += `<span class="sim-mode-calc-row">T=${cd.detail.T?.toFixed(3)} · R=${cd.detail.R?.toFixed(3)} · gate=${cd.detail.data_gate ?? cd.data_gate}</span>`;
                } else if (cd.detail.objective_cap !== undefined) {
                    html += `<span class="sim-mode-calc-row">cap=${cd.detail.objective_cap?.toFixed(3)} · gate=${cd.detail.data_gate ?? cd.data_gate}</span>`;
                }
            }
            // 查看详情按钮（保留弹窗）
            if (res.scrape_trace) {
                html += `<button class="btn btn-secondary btn-xs sim-mode-detail-btn" data-confidence-detail-action="open" data-trace="${escapeHtml(JSON.stringify(res.scrape_trace))}" data-filename="${escapeHtml(data.filename || "")}">查看完整计算过程</button>`;
            }
            html += '</div>';

            // AI 标记
            html += '<div class="sim-mode-ai-tags">';
            if (modeData.ai_invoked) {
                html += '<span class="sim-ai-tag sim-ai-tag-active">🤖 AI 已调用</span>';
                if (modeData.ai_invoke_reason) {
                    html += `<span class="sim-ai-tag sim-ai-tag-reason">${escapeHtml(modeData.ai_invoke_reason)}</span>`;
                }
            } else {
                html += '<span class="sim-ai-tag sim-ai-tag-idle">📴 AI 未调用</span>';
            }
            if (modeData.search_enhanced === true) {
                html += '<span class="sim-ai-tag sim-ai-tag-search">🔍 联网搜索增强</span>';
            } else if (modeData.search_enhanced === false && modeData.ai_invoked) {
                html += '<span class="sim-ai-tag sim-ai-tag-local">📴 纯本地分析</span>';
            }
            html += '</div>';

            // 耗时
            html += `<div class="sim-mode-elapsed">耗时 ${Number(modeData.elapsed || 0).toFixed(2)}s</div>`;

            html += '</div>'; // .sim-mode-body
        }

        html += '</div>'; // .sim-mode-card
    }

    html += '</div>'; // .sim-modes-grid

    // ---- 底部推荐 ----
    if (recommendation) {
        html += '<div class="sim-recommendation">';
        html += '<div class="sim-recommend-head">';
        html += '<span class="sim-recommend-icon">💡</span>';
        html += '<span>推荐使用 <strong>' + escapeHtml(_modeLabel(recommendation.best_mode)) + '</strong></span>';
        html += '</div>';
        html += '<div class="sim-recommend-body">';
        html += `<span>置信度 ${(recommendation.best_confidence || 0).toFixed(3)} · ${escapeHtml(recommendation.reason || "")}</span>`;
        html += '</div>';
        html += '</div>';
    }

    html += '</div>'; // .sim-compare

    result.innerHTML = html;
}

// ---- 辅助函数 ----

function _simDecisionLabel(score, gateBlocked) {
    if (gateBlocked) return "🚫 维度否决";
    if (score >= 0.8) return "✅ 自动入库";
    if (score >= 0.5) return "🔵 需确认";
    if (score >= 0.3) return "🟡 需审核";
    return "🔴 失败";
}

function _modeLabel(modeKey) {
    const map = {
        "provider_first": "Provider 优先",
        "ai_only": "纯 AI 刮削",
        "hybrid": "Provider + AI 联合",
    };
    return map[modeKey] || modeKey;
}
```

**注意**：原有的 `_simConfColor`、`_renderSimDims`、`escapeHtml` 等辅助函数保持不变，继续复用。

### 5.3 CSS 样式新增

**文件**：`media_importer/webui/css/cinema-confidence.css`

**改动位置**：在文件末尾追加新样式，保留现有 `.sim-timeline` 等样式不变（其他页面可能引用）

**新增样式**：

```css
/* ============================================================
   三模式对比布局
   ============================================================ */

.sim-compare {
    display: grid;
    gap: 16px;
}

/* 清洗结果摘要 */
.sim-clean-summary {
    padding: 14px 18px;
    border: 1px solid rgba(234,191,99,0.14);
    border-radius: var(--radius);
    background: rgba(234,191,99,0.06);
}

.sim-clean-title {
    color: var(--gold);
    font-size: 12px;
    font-weight: 900;
    letter-spacing: 0.04em;
    margin-bottom: 10px;
}

.sim-clean-grid {
    display: grid;
    grid-template-columns: repeat(4, minmax(0, 1fr));
    gap: 8px;
}

.sim-clean-item {
    display: flex;
    flex-direction: column;
    gap: 2px;
}

.sim-clean-full {
    grid-column: 1 / -1;
}

.sim-clean-label {
    color: var(--muted);
    font-size: 10px;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.05em;
}

.sim-clean-value {
    color: var(--ink);
    font-size: 13px;
    font-weight: 600;
    word-break: break-all;
}

/* 三列网格 */
.sim-modes-grid {
    display: grid;
    grid-template-columns: repeat(3, minmax(0, 1fr));
    gap: 12px;
}

/* 模式卡片 */
.sim-mode-card {
    display: flex;
    flex-direction: column;
    border: 1px solid rgba(255,255,255,0.08);
    border-radius: var(--radius);
    background: rgba(0,0,0,0.18);
    overflow: hidden;
    transition: border-color 200ms ease, box-shadow 200ms ease;
}

.sim-mode-card:hover {
    border-color: rgba(255,255,255,0.14);
}

.sim-mode-current {
    border-color: rgba(234,191,99,0.35);
    box-shadow: 0 0 0 1px rgba(234,191,99,0.12);
}

.sim-mode-error {
    border-color: rgba(239,68,68,0.25);
}

/* 卡片头部 */
.sim-mode-head {
    display: flex;
    align-items: flex-start;
    gap: 10px;
    padding: 14px 14px 10px;
    border-bottom: 1px solid rgba(255,255,255,0.05);
}

.sim-mode-icon {
    font-size: 22px;
    line-height: 1;
    flex-shrink: 0;
}

.sim-mode-head-text {
    display: flex;
    flex-direction: column;
    gap: 2px;
    min-width: 0;
}

.sim-mode-label {
    color: var(--ink);
    font-size: 14px;
    font-weight: 700;
    display: flex;
    align-items: center;
    gap: 6px;
}

.sim-mode-badge {
    display: inline-block;
    padding: 1px 7px;
    border-radius: 999px;
    background: rgba(234,191,99,0.18);
    color: var(--gold);
    font-size: 10px;
    font-weight: 900;
    white-space: nowrap;
}

.sim-mode-desc {
    color: var(--muted);
    font-size: 11px;
}

/* 卡片主体 */
.sim-mode-body {
    display: flex;
    flex-direction: column;
    gap: 10px;
    padding: 12px 14px 14px;
    flex: 1;
}

/* 刮削结果字段 */
.sim-mode-result {
    display: flex;
    flex-direction: column;
    gap: 4px;
}

.sim-mode-field {
    display: flex;
    justify-content: space-between;
    align-items: baseline;
    gap: 8px;
}

.sim-mode-fk {
    color: var(--muted);
    font-size: 11px;
    flex-shrink: 0;
}

.sim-mode-fv {
    color: var(--ink);
    font-size: 12px;
    font-weight: 600;
    text-align: right;
    word-break: break-all;
}

.sim-mode-fv-sub {
    font-weight: 400;
    color: var(--muted);
}

/* 维度标签 */
.sim-mode-dims {
    display: flex;
    flex-wrap: wrap;
    gap: 4px;
    margin-top: 2px;
}

/* 置信度区域 */
.sim-mode-confidence {
    display: flex;
    align-items: baseline;
    gap: 8px;
    padding: 10px 0 6px;
    border-top: 1px solid rgba(255,255,255,0.05);
}

.sim-mode-score {
    font-size: 28px;
    font-weight: 900;
    line-height: 1;
    font-variant-numeric: tabular-nums;
}

.sim-mode-decision {
    font-size: 12px;
    font-weight: 700;
}

/* 计算过程 */
.sim-mode-calc {
    display: flex;
    flex-direction: column;
    gap: 4px;
    padding: 8px 10px;
    border-radius: 8px;
    background: rgba(0,0,0,0.15);
    font-size: 11px;
}

.sim-mode-formula {
    color: var(--gold-2);
    font-weight: 700;
    font-family: "SF Mono", "Fira Code", monospace;
}

.sim-mode-calc-row {
    color: var(--muted);
    font-family: "SF Mono", "Fira Code", monospace;
}

.sim-mode-detail-btn {
    margin-top: 4px;
    align-self: flex-start;
    font-size: 11px;
    padding: 4px 10px;
}

/* AI 标记 */
.sim-mode-ai-tags {
    display: flex;
    flex-wrap: wrap;
    gap: 4px;
}

.sim-ai-tag {
    display: inline-block;
    padding: 2px 8px;
    border-radius: 999px;
    font-size: 10px;
    font-weight: 700;
}

.sim-ai-tag-active {
    background: rgba(139,92,246,0.15);
    color: #A78BFA;
}

.sim-ai-tag-idle {
    background: rgba(148,163,184,0.1);
    color: #94A3B8;
}

.sim-ai-tag-reason {
    background: rgba(148,163,184,0.08);
    color: var(--muted);
}

.sim-ai-tag-search {
    background: rgba(6,182,212,0.15);
    color: #06B6D4;
}

.sim-ai-tag-local {
    background: rgba(148,163,184,0.1);
    color: #94A3B8;
}

/* 耗时 */
.sim-mode-elapsed {
    color: var(--muted);
    font-size: 10px;
    margin-top: auto;
    padding-top: 6px;
    border-top: 1px solid rgba(255,255,255,0.04);
}

/* 错误消息 */
.sim-mode-error-msg {
    padding: 12px;
    border-radius: 8px;
    background: rgba(239,68,68,0.08);
    color: #FCA5A5;
    font-size: 12px;
    line-height: 1.5;
}

/* 底部推荐 */
.sim-recommendation {
    padding: 14px 18px;
    border: 1px solid rgba(34,197,94,0.2);
    border-radius: var(--radius);
    background: rgba(34,197,94,0.06);
}

.sim-recommend-head {
    display: flex;
    align-items: center;
    gap: 8px;
    color: var(--ink);
    font-size: 14px;
    font-weight: 600;
    margin-bottom: 4px;
}

.sim-recommend-icon {
    font-size: 18px;
}

.sim-recommend-head strong {
    color: #22C55E;
}

.sim-recommend-body {
    color: var(--muted);
    font-size: 12px;
    padding-left: 26px;
}

/* ============================================================
   响应式
   ============================================================ */

@media (max-width: 1200px) {
    .sim-modes-grid {
        grid-template-columns: repeat(2, minmax(0, 1fr));
    }
    .sim-clean-grid {
        grid-template-columns: repeat(2, minmax(0, 1fr));
    }
}

@media (max-width: 768px) {
    .sim-modes-grid {
        grid-template-columns: minmax(0, 1fr);
    }
    .sim-clean-grid {
        grid-template-columns: minmax(0, 1fr);
    }
    .sim-mode-score {
        font-size: 24px;
    }
}
```

## 6. 测试计划

### 6.1 后端测试

**文件**：`tests/test_scrape_preview.py`（新增）

```python
"""测试三模式刮削预览 API。"""
import pytest
from unittest.mock import patch, MagicMock


class TestScrapePreviewThreeModes:
    """POST /api/scrape/preview 三模式对比。"""

    def test_returns_three_modes_in_response(self):
        """返回的 data.modes 包含 provider_first / ai_only / hybrid 三个 key。"""
        pass

    def test_each_mode_has_result_and_elapsed(self):
        """每个模式包含 result 和 elapsed 字段。"""
        pass

    def test_each_mode_has_confidence_detail(self):
        """每个模式包含 confidence_detail（公式 + 分解值）。"""
        pass

    def test_ai_only_returns_error_when_ai_not_configured(self):
        """AI 未配置时 ai_only 返回 error 而非降级。"""
        pass

    def test_hybrid_returns_error_when_ai_not_configured(self):
        """AI 未配置时 hybrid 返回 error 而非降级。"""
        pass

    def test_provider_first_works_without_ai(self):
        """provider_first 在 AI 未配置时仍正常工作。"""
        pass

    def test_recommendation_picks_best_mode(self):
        """推荐逻辑选出置信度最高的模式。"""
        pass

    def test_current_mode_field_matches_config(self):
        """current_mode 字段反映配置中的 scrape_mode。"""
        pass

    def test_force_mode_parameter_works(self):
        """scrape_metadata(force_mode='xxx') 正确覆盖配置。"""
        pass
```

### 6.2 前端测试

使用现有 `test_def_ui_*.py` 框架，新增或扩展现有测试：

```python
class TestSimulatorThreeColumns:
    """配置模拟测试三列展示。"""

    def test_simulator_shows_three_mode_cards(self):
        """模拟结果包含三张模式卡片。"""
        pass

    def test_current_mode_has_badge(self):
        """当前配置的模式卡片显示'当前配置'标记。"""
        pass

    def test_confidence_detail_shown_inline(self):
        """置信度公式和分解值内联展示。"""
        pass

    def test_ai_tags_show_correctly(self):
        """AI 标记正确显示（已调用/未调用/联网搜索/纯本地）。"""
        pass

    def test_recommendation_section_visible(self):
        """底部推荐区域可见。"""
        pass

    def test_error_mode_shows_error_message(self):
        """错误模式显示错误信息而非崩溃。"""
        pass
```

### 6.3 回归测试

```bash
# 确保现有测试全部通过
python -m pytest tests/ -x --ignore=tests/test_scrape_preview.py

# 运行新测试
python -m pytest tests/test_scrape_preview.py -v
```

## 7. 实施顺序

| 阶段 | 任务 | 依赖 |
|------|------|------|
| 1 | `scrape_metadata()` 新增 `force_mode` | 无 |
| 2 | `MetadataScraper.scrape()` 透传 `force_mode` | 1 |
| 3 | `ConfidenceResult` 新增 `confidence_detail` | 无 |
| 4 | `calculate()` / `calculate_ai_only()` 返回 `confidence_detail` | 3 |
| 5 | `_scrape_preview` API 改造（三模式并行 + 新结构） | 1, 2, 4 |
| 6 | HTML 结构调整 | 无 |
| 7 | `renderSimulatorPreview()` 重写 | 5, 6 |
| 8 | CSS 样式新增 | 6 |
| 9 | 后端测试 | 5 |
| 10 | 前端测试 | 7, 8 |
| 11 | 回归测试 | 全部 |

阶段 1-4 可并行，阶段 5 依赖 1-4，阶段 6-8 可并行，阶段 9-11 最后执行。

## 8. 风险与注意事项

1. **向后兼容**：`force_mode=None` 时行为完全不变，现有调用方不受影响
2. **CSS 不删旧样式**：`.sim-timeline` 等旧样式保留，避免影响其他可能引用的页面
3. **API 返回结构变化**：前端 `renderSimulatorPreview()` 是唯一消费者，整体重写即可
4. **并行超时**：三任务并行时，`preview_timeout` 对每个任务独立生效
5. **AI 未配置时的处理**：`force_mode` 指定 AI 模式但 AI 不可用时，返回 error 而非降级，与正常流程不同
