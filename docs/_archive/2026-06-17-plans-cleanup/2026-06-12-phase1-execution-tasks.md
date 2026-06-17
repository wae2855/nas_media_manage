# 阶段 1 执行文档：后端核心替换

> 本文档供 deepseek-v4flash / minimax-m3 等模型直接执行。
> 每个任务都是原子操作，包含精确的文件路径、代码骨架和验证步骤。
> **严格按任务编号顺序执行**，不可跳步。

---

## 任务 1.1：创建 `match_models.py` 数据模型

**文件**：`media_importer/features/scraping/match_models.py`

**操作**：新建文件

**完整代码**：

```python
"""三级匹配策略的数据模型。"""

from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class MatchConcern:
    """匹配疑虑原因。"""
    code: str       # NO_YEAR_MULTI_MATCH / YEAR_MISMATCH / FUZZY_TITLE / NO_PROVIDER_RESULT / NO_TITLE / CONFLICTING_INFO / AI_UNCERTAIN
    message: str    # 用户可读文案
    detail: str     # 详细技术说明


@dataclass
class MatchTraceStep:
    """匹配路径追踪的单个步骤。"""
    tier: int                   # 1 / 2 / 3
    name: str                   # "Provider精确匹配" / "上下文辅助匹配" / "用户确认"
    matched: bool               # 本级是否匹配成功
    search_query: str = ""      # 搜索查询
    match_level: str = ""       # TitleMatcher 的 L1-L7 级别
    reason: str = ""            # 匹配/未匹配原因
    ai_reason: str = ""         # AI 判断理由（仅第二级）


@dataclass
class MatchResult:
    """三级匹配引擎的最终结果。"""
    match_level: str            # AUTO_PASS / CONTEXT_PASS / NEEDS_CONFIRM
    provider_id: Optional[int] = None
    provider_title: str = ""
    match_tier: int = 0         # 命中的级别（1/2/3）
    concerns: List[MatchConcern] = field(default_factory=list)
    trace_steps: List[MatchTraceStep] = field(default_factory=list)
    candidates: List[dict] = field(default_factory=list)  # 第三级的候选列表
    confidence_reason: str = ""  # 匹配成功或失败的原因说明

    def to_dict(self) -> dict:
        """转换为可序列化的字典。"""
        return {
            "match_level": self.match_level,
            "provider_id": self.provider_id,
            "provider_title": self.provider_title,
            "match_tier": self.match_tier,
            "concerns": [
                {"code": c.code, "message": c.message, "detail": c.detail}
                for c in self.concerns
            ],
            "trace": [
                {
                    "tier": s.tier,
                    "name": s.name,
                    "matched": s.matched,
                    "search_query": s.search_query,
                    "match_level": s.match_level,
                    "reason": s.reason,
                    "ai_reason": s.ai_reason,
                }
                for s in self.trace_steps
            ],
            "candidates": self.candidates,
            "confidence_reason": self.confidence_reason,
        }
```

**验证**：
```bash
cd /Users/wangwei/Documents/code/nas_media_manage
PYTHONPYCACHEPREFIX=/private/tmp/nas_media_manage_pycache python -m compileall -q media_importer/features/scraping/match_models.py
```

---

## 任务 1.2：创建 `match_engine.py` 核心引擎

**文件**：`media_importer/features/scraping/match_engine.py`

**操作**：新建文件

**完整代码**：

```python
"""三级匹配引擎：Provider精确匹配 → 上下文辅助匹配 → 用户确认。"""

import logging
import os
from typing import List, Optional

from media_importer.features.scraping.match_models import (
    MatchConcern,
    MatchResult,
    MatchTraceStep,
)
from media_importer.scraper.title_matcher import TitleMatcher
from media_importer.scraper.filename_cleaner import FilenameCleaner

logger = logging.getLogger(__name__)


class MatchEngine:
    """三级匹配引擎。

    第一级：Provider 精确匹配（标题+年份 → TMDB 精确结果）
    第二级：上下文辅助匹配（目录信息 + AI 从候选列表中选出）
    第三级：用户确认（展示候选列表 + 疑虑原因）
    """

    def __init__(self, config: dict = None):
        self.config = config or {}
        self.title_matcher = TitleMatcher()
        self.filename_cleaner = FilenameCleaner()

    def match(self, filename: str, providers: list, conn=None) -> MatchResult:
        """执行三级匹配。

        Args:
            filename: 原始视频文件名
            providers: 已启用的 Provider 实例列表
            conn: 数据库连接（用于维度查询）

        Returns:
            MatchResult 包含匹配级别、疑虑原因和追踪信息
        """
        # 清洗文件名
        clean_result = self.filename_cleaner.clean(filename)
        clean_title = clean_result.get("clean_title", "")
        cjk_title = clean_result.get("cjk_title", "")
        year = clean_result.get("year")
        season = clean_result.get("season")
        episode = clean_result.get("episode")

        if not clean_title and not cjk_title:
            return MatchResult(
                match_level="NEEDS_CONFIRM",
                match_tier=0,
                concerns=[MatchConcern(
                    code="NO_TITLE",
                    message="无法从文件名提取有效标题",
                    detail=f"文件名: {filename}",
                )],
                trace_steps=[MatchTraceStep(
                    tier=0, name="文件名清洗", matched=False,
                    reason="清洗后标题为空",
                )],
            )

        # 第一级：Provider 精确匹配
        result = self._tier1_exact_match(
            clean_title, cjk_title, year, season, episode, providers
        )
        if result:
            return result

        # 第二级：上下文辅助匹配（阶段 2 实现，当前跳过）
        # result = self._tier2_context_match(...)
        # if result:
        #     return result

        # 第三级：用户确认
        return self._tier3_user_confirm(
            clean_title, cjk_title, year, season, episode, providers
        )

    def _tier1_exact_match(
        self,
        clean_title: str,
        cjk_title: str,
        year: Optional[int],
        season: Optional[int],
        episode: Optional[int],
        providers: list,
    ) -> Optional[MatchResult]:
        """第一级：Provider 精确匹配。

        逻辑：
        1. 用标题+年份搜索 Provider
        2. 对每个搜索结果用 TitleMatcher 计算匹配级别
        3. 如果 L1/L2 精确匹配且唯一 → AUTO_PASS
        4. 如果 L3（精确但无年份）且唯一 → AUTO_PASS
        5. 否则返回 None，进入下一级
        """
        concerns = []
        trace_steps = []

        for provider in providers:
            # 优先用 CJK 标题搜索
            search_titles = []
            if cjk_title:
                search_titles.append(cjk_title)
            if clean_title and clean_title != cjk_title:
                search_titles.append(clean_title)
            if not search_titles and clean_title:
                search_titles.append(clean_title)

            for search_title in search_titles:
                try:
                    search_results = provider.search(search_title, year=year)
                except Exception as e:
                    logger.warning(f"Provider {provider.__class__.__name__} 搜索失败: {e}")
                    continue

                if not search_results:
                    continue

                # 对每个结果计算匹配级别
                exact_matches = []
                for item in search_results:
                    match_result = self.title_matcher.match_standard(
                        clean_title, item, year, season
                    )
                    if match_result.level in ("L1", "L2"):
                        exact_matches.append((item, match_result))
                    elif match_result.level == "L3" and year is None:
                        exact_matches.append((item, match_result))

                if len(exact_matches) == 1:
                    # 唯一精确匹配 → AUTO_PASS
                    item, match_result = exact_matches[0]
                    trace_steps.append(MatchTraceStep(
                        tier=1,
                        name="Provider精确匹配",
                        matched=True,
                        search_query=f"{search_title} (year={year})",
                        match_level=match_result.level,
                        reason=f"唯一精确匹配: {item.title} (T={match_result.T:.2f})",
                    ))
                    return MatchResult(
                        match_level="AUTO_PASS",
                        provider_id=item.id,
                        provider_title=item.title,
                        match_tier=1,
                        trace_steps=trace_steps,
                        confidence_reason=f"标题精确匹配({match_result.level})，年份{'一致' if year else '无但唯一'}",
                    )

                elif len(exact_matches) > 1:
                    # 多个精确匹配 → 需要进一步判断
                    concerns.append(MatchConcern(
                        code="NO_YEAR_MULTI_MATCH",
                        message=f"找到 {len(exact_matches)} 部同名作品",
                        detail=f"搜索 '{search_title}' 返回 {len(exact_matches)} 条精确匹配",
                    ))
                    trace_steps.append(MatchTraceStep(
                        tier=1,
                        name="Provider精确匹配",
                        matched=False,
                        search_query=f"{search_title} (year={year})",
                        reason=f"多个精确匹配({len(exact_matches)}条)，无法自动确定",
                    ))
                    # 不返回，继续尝试其他搜索标题或进入下一级

                else:
                    # 无精确匹配
                    if year and search_results:
                        # 有年份但无精确匹配，尝试不带年份重新搜索
                        concerns.append(MatchConcern(
                            code="FUZZY_TITLE",
                            message=f"标题不完全匹配，最高相似度不足",
                            detail=f"搜索 '{search_title}' 无精确匹配",
                        ))
                    trace_steps.append(MatchTraceStep(
                        tier=1,
                        name="Provider精确匹配",
                        matched=False,
                        search_query=f"{search_title} (year={year})",
                        reason="无精确匹配",
                    ))

        if not trace_steps:
            # 所有 Provider 都无结果
            concerns.append(MatchConcern(
                code="NO_PROVIDER_RESULT",
                message="刮削源未找到匹配作品",
                detail=f"搜索标题: {cjk_title or clean_title}",
            ))
            trace_steps.append(MatchTraceStep(
                tier=1,
                name="Provider精确匹配",
                matched=False,
                reason="所有 Provider 搜索无结果",
            ))

        # 第一级未匹配成功，返回 None 让 match() 进入下一级
        # 但先保存 concerns 和 trace 供后续使用
        self._pending_concerns = concerns
        self._pending_trace = trace_steps
        return None

    def _tier3_user_confirm(
        self,
        clean_title: str,
        cjk_title: str,
        year: Optional[int],
        season: Optional[int],
        episode: Optional[int],
        providers: list,
    ) -> MatchResult:
        """第三级：用户确认。

        收集 Provider 搜索候选列表，生成疑虑原因，返回 NEEDS_CONFIRM。
        """
        concerns = getattr(self, '_pending_concerns', [])
        trace_steps = getattr(self, '_pending_trace', [])
        candidates = []

        for provider in providers:
            search_titles = []
            if cjk_title:
                search_titles.append(cjk_title)
            if clean_title and clean_title != cjk_title:
                search_titles.append(clean_title)
            if not search_titles and clean_title:
                search_titles.append(clean_title)

            for search_title in search_titles:
                try:
                    results = provider.search(search_title, year=year)
                    for item in results[:5]:
                        candidates.append({
                            "id": item.id,
                            "title": item.title,
                            "year": item.year,
                            "media_type": item.media_type,
                            "overview": getattr(item, 'overview', '')[:100] if hasattr(item, 'overview') else '',
                        })
                except Exception:
                    continue
                if candidates:
                    break
            if candidates:
                break

        trace_steps.append(MatchTraceStep(
            tier=3,
            name="用户确认",
            matched=False,
            reason="需要用户从候选列表中选择",
        ))

        if not concerns:
            concerns.append(MatchConcern(
                code="FUZZY_TITLE",
                message="无法自动匹配，需要人工确认",
                detail=f"搜索标题: {cjk_title or clean_title}",
            ))

        return MatchResult(
            match_level="NEEDS_CONFIRM",
            match_tier=3,
            concerns=concerns,
            trace_steps=trace_steps,
            candidates=candidates[:5],
            confidence_reason="；".join(c.message for c in concerns),
        )
```

**验证**：
```bash
PYTHONPYCACHEPREFIX=/private/tmp/nas_media_manage_pycache python -m compileall -q media_importer/features/scraping/match_engine.py
```

---

## 任务 1.3：改造 `review.py` — 基于 match_level 判断

**文件**：`media_importer/features/import_flow/services/review.py`

**操作**：替换整个文件内容

**替换前**（当前代码，92 行）：基于 confidence_engine.get_confidence_level() 判断
**替换后**：

```python
from dataclasses import dataclass, field


@dataclass
class ReviewDecision:
    action: str       # continue / confirm / needs_review / failed
    reason: str = ""
    warnings: list = field(default_factory=list)


class ReviewDecisionService:
    def evaluate(self, scraped: dict, confidence_engine=None) -> ReviewDecision:
        """根据刮削结果决定任务流向。

        新逻辑：基于 match_level 判断，不再依赖置信度数值。
        confidence_engine 参数保留但不再使用，保持接口兼容。
        """
        if not scraped:
            return ReviewDecision(action="failed", reason="刮削结果为空，无法验证")

        missing_fields, warnings = self._validate_required_fields(scraped)
        if missing_fields:
            reason = f"刮削信息不足，需要人工确认。缺失字段: {'; '.join(missing_fields)}"
            if warnings:
                reason += f"。警告: {'; '.join(warnings)}"
            return ReviewDecision(action="confirm", reason=reason, warnings=warnings)

        match_level = scraped.get("match_level", "NEEDS_CONFIRM")
        concerns = scraped.get("match_concerns", [])

        if match_level == "AUTO_PASS":
            return ReviewDecision(action="continue", warnings=warnings)

        if match_level == "CONTEXT_PASS":
            return ReviewDecision(action="continue", warnings=warnings)

        if match_level == "NEEDS_CONFIRM":
            if concerns:
                reason = "；".join(c.get("message", "") for c in concerns if c.get("message"))
            else:
                reason = "需要人工确认"
            return ReviewDecision(action="confirm", reason=reason, warnings=warnings)

        return ReviewDecision(action="failed", reason="匹配失败，无法识别", warnings=warnings)

    def _validate_required_fields(self, scraped: dict):
        """校验必填字段（逻辑不变）。"""
        missing_fields = []
        warnings = []

        title_cn = scraped.get("title_cn")
        title_en = scraped.get("title_en")
        year = scraped.get("year")
        media_type = scraped.get("type")

        has_title = bool(title_cn or title_en)
        has_type = bool(media_type)
        has_year = bool(year)

        if not has_title:
            missing_fields.append("中文名(title_cn)和英文名(title_en)都缺失")
        if not has_type:
            missing_fields.append("媒体类型(type)缺失")
        if not has_year:
            if has_title and has_type:
                warnings.append(f"年份缺失(可接受，标题已识别: {title_cn or title_en})")
            else:
                missing_fields.append("年份(year)缺失")
        if title_cn and not title_en:
            warnings.append("缺少英文名(可接受)")
        if year:
            try:
                parsed_year = int(year)
                if parsed_year < 1900 or parsed_year > 2030:
                    warnings.append(f"年份异常: {year}")
                    missing_fields.append(f"年份异常: {year}")
            except ValueError:
                warnings.append(f"年份格式异常: {year}")

        return missing_fields, warnings
```

**关键变更**：
- `evaluate()` 的 `confidence_engine` 参数保留但不再使用（保持调用方兼容）
- 判断逻辑从 `confidence_engine.get_confidence_level(confidence, gate_blocked)` 改为读取 `scraped["match_level"]`
- 移除所有 `confidence`、`gate_blocked`、`search_conf`、`data_gate` 相关逻辑
- `_validate_required_fields()` 完全不变

**验证**：
```bash
PYTHONPYCACHEPREFIX=/private/tmp/nas_media_manage_pycache python -m compileall -q media_importer/features/import_flow/services/review.py
```

---

## 任务 1.4：改造 `scrape.py` — 使用 MatchEngine + 写入新字段

**文件**：`media_importer/features/import_flow/steps/scrape.py`

**操作**：精确替换以下 4 处

### 替换 1：添加 import（第 6 行后）

在第 7 行 `from media_importer.features.scraping import LLMScrapeError` 后添加：

```python
from media_importer.features.scraping.match_engine import MatchEngine
```

### 替换 2：`_step_scrape` 中写入新字段（第 67-69 行区域）

将：
```python
            task["scrape_confidence"] = result.get('confidence', 0)
            task["provider_type"] = result.get('provider_type', '')
            task["provider_id"] = result.get('provider_id', '')
```

替换为：
```python
            task["scrape_confidence"] = result.get('confidence', 0)
            task["match_level"] = result.get('match_level', '')
            task["match_concerns"] = result.get('match_concerns', [])
            task["provider_type"] = result.get('provider_type', '')
            task["provider_id"] = result.get('provider_id', '')
```

### 替换 3：`_step_scrape` 中 db_update_task 写入新字段（第 92-107 行区域）

将：
```python
            db_update_task(
                self.task_manager.conn, task.get("task_id", ""),
                scrape_result=result,
                scrape_dimensions=scrape_dimensions,
                scrape_title_cn=result.get('title_cn', ''),
                scrape_title_en=result.get('title_en', ''),
                scrape_year=result.get('year', ''),
                scrape_media_type=media_type,
                scrape_season=result.get('season', None),
                scrape_episode=result.get('episode', None),
                scrape_confidence=result.get('confidence', 0),
                scrape_trace=scrape_trace,
                provider_type=result.get('provider_type', ''),
                provider_id=result.get('provider_id', ''),
                thumbnail_path=thumbnail_path,
            )
```

替换为：
```python
            # 序列化 match_concerns 为 JSON
            import json as _json
            match_concerns_json = _json.dumps(
                result.get('match_concerns', []),
                ensure_ascii=False
            ) if result.get('match_concerns') else ''

            db_update_task(
                self.task_manager.conn, task.get("task_id", ""),
                scrape_result=result,
                scrape_dimensions=scrape_dimensions,
                scrape_title_cn=result.get('title_cn', ''),
                scrape_title_en=result.get('title_en', ''),
                scrape_year=result.get('year', ''),
                scrape_media_type=media_type,
                scrape_season=result.get('season', None),
                scrape_episode=result.get('episode', None),
                scrape_confidence=result.get('confidence', 0),
                match_level=result.get('match_level', ''),
                match_concerns=match_concerns_json,
                match_trace=_json.dumps(result.get('match_trace', {}), ensure_ascii=False) if result.get('match_trace') else '',
                scrape_trace=scrape_trace,
                provider_type=result.get('provider_type', ''),
                provider_id=result.get('provider_id', ''),
                thumbnail_path=thumbnail_path,
            )
```

### 替换 4：`_step_scrape` 日志中替换置信度展示（第 122 行）

将：
```python
            detail_parts.append(f"置信度={result.get('confidence', 0)}")
```

替换为：
```python
            match_level = result.get('match_level', '')
            if match_level == 'AUTO_PASS':
                detail_parts.append("匹配=自动通过")
            elif match_level == 'CONTEXT_PASS':
                detail_parts.append("匹配=AI辅助通过")
            elif match_level == 'NEEDS_CONFIRM':
                detail_parts.append("匹配=需确认")
            else:
                detail_parts.append(f"置信度={result.get('confidence', 0)}")
```

### 替换 5：`_step_validate` 简化（第 135-171 行）

将整个 `_step_validate` 方法替换为：

```python
    def _step_validate(self, task: dict):
        self._update_progress(task, 4, "validate", 52)
        self._log("info", f"验证刮削结果: {task.get('source_filename', '')}", task, "validate")

        scraped = task.get("scrape_result", {})
        if not scraped:
            raise PipelineError("刮削结果为空，无法验证")

        decision = ReviewDecisionService().evaluate(
            scraped,
            self.scraper.confidence_engine if hasattr(self.scraper, 'confidence_engine') else None,
        )

        if decision.action == "confirm":
            task["_needs_confirm"] = True
            task["_confirm_reason"] = decision.reason
            self._log("warn", decision.reason, task, "validate")
            return

        if decision.action == "needs_review":
            task["skip_reason"] = decision.reason
            task["_needs_review"] = True
            self._log("warn", f"需要人工审核: {decision.reason}", task, "validate")
            return

        if decision.action == "failed":
            task["_force_fail"] = True
            task["_fail_reason"] = decision.reason
            self._log("warn", task["_fail_reason"], task, "validate")
            return

        if decision.warnings:
            self._log("warn", f"刮削警告: {'; '.join(decision.warnings)}", task, "validate")
        self._update_progress(task, 4, "validate", 55)
```

**验证**：
```bash
PYTHONPYCACHEPREFIX=/private/tmp/nas_media_manage_pycache python -m compileall -q media_importer/features/import_flow/steps/scrape.py
```

---

## 任务 1.5：DB 新增字段

**文件**：`media_importer/core/db/constants.py`

**操作**：在 `CREATE_TASKS_TABLE` SQL 中，在 `scrape_confidence REAL DEFAULT 0,` 行后添加 3 个新字段

找到：
```python
    scrape_confidence REAL DEFAULT 0,
```

在其后添加：
```python
    match_level TEXT DEFAULT NULL,
    match_concerns TEXT DEFAULT NULL,
    match_trace TEXT DEFAULT NULL,
```

**文件**：`media_importer/core/db/task_repo.py`

**操作**：在 `update_task` 函数的 `valid_columns` 集合中添加 3 个新字段

找到（第 153-169 行）：
```python
    valid_columns = {
        ...
        "scrape_confidence",
        "scrape_trace",
        ...
    }
```

在 `"scrape_confidence",` 行后添加：
```python
        "match_level",
        "match_concerns",
        "match_trace",
```

在 `_row_to_dict` 的 JSON 解析区域（`get_task` 函数中），在 `scrape_trace` 解析后添加：

```python
    if row and row.get('match_concerns'):
        try:
            row['match_concerns'] = json.loads(row['match_concerns'])
        except (json.JSONDecodeError, TypeError):
            pass
    if row and row.get('match_trace'):
        try:
            row['match_trace'] = json.loads(row['match_trace'])
        except (json.JSONDecodeError, TypeError):
            pass
```

**数据库迁移**：对于已有数据库，需要执行 ALTER TABLE。在 `media_importer/core/db/connection.py` 的初始化逻辑中添加迁移：

找到 DB 初始化/迁移代码位置，添加：
```python
    # 迁移：添加 match_level / match_concerns / match_trace 字段
    try:
        conn.execute("ALTER TABLE tasks ADD COLUMN match_level TEXT DEFAULT NULL")
    except sqlite3.OperationalError:
        pass  # 字段已存在
    try:
        conn.execute("ALTER TABLE tasks ADD COLUMN match_concerns TEXT DEFAULT NULL")
    except sqlite3.OperationalError:
        pass
    try:
        conn.execute("ALTER TABLE tasks ADD COLUMN match_trace TEXT DEFAULT NULL")
    except sqlite3.OperationalError:
        pass
```

**验证**：
```bash
PYTHONPYCACHEPREFIX=/private/tmp/nas_media_manage_pycache python -m compileall -q media_importer/core/db/constants.py media_importer/core/db/task_repo.py media_importer/core/db/connection.py
```

---

## 任务 1.6：配置迁移 v2→v3

**文件**：`media_importer/core/config_migrations.py`

**操作**：添加新的迁移函数

在文件末尾添加：

```python
def _migrate_confidence_v2_to_v3(config: dict) -> dict:
    """移除 confidence 区块，迁移 ai_only 模式，保留 manual_review。"""
    config.pop("confidence", None)
    config.get("llm", {}).pop("confidence_threshold", None)

    # 迁移 scrape_mode: ai_only / hybrid → provider_first
    metadata = config.get("metadata", {})
    if metadata.get("scrape_mode") in ("ai_only", "hybrid"):
        metadata["scrape_mode"] = "provider_first"

    return config
```

然后在配置加载的迁移链中注册此迁移。找到 `_migrate_config` 或类似的迁移入口函数，在最后一步调用 `_migrate_confidence_v2_to_v3`。

**验证**：
```bash
PYTHONPYCACHEPREFIX=/private/tmp/nas_media_manage_pycache python -m compileall -q media_importer/core/config_migrations.py
```

---

## 任务 1.7：Feature Flag 支持

**文件**：`media_importer/features/import_flow/steps/scrape.py`

**操作**：在 `_step_scrape` 中添加 feature flag 判断

在 `self.scraper.scrape(...)` 调用之前，添加 feature flag 逻辑：

```python
        # Feature flag: 使用新匹配引擎
        use_new_engine = self.config.get("features", {}).get("use_new_match_engine", True)
```

在 scrape 结果获取后，如果使用新引擎，补充 match_level 等字段：

```python
        # 如果使用新匹配引擎，从 result 中提取 match_level
        if use_new_engine and 'match_level' not in result:
            # 旧 scraper 不返回 match_level，用 confidence 映射
            confidence = result.get('confidence', 0)
            if confidence >= 0.8:
                result['match_level'] = 'AUTO_PASS'
            elif confidence >= 0.5:
                result['match_level'] = 'NEEDS_CONFIRM'
            else:
                result['match_level'] = 'NEEDS_CONFIRM'
            result['match_concerns'] = []
```

**验证**：
```bash
PYTHONPYCACHEPREFIX=/private/tmp/nas_media_manage_pycache python -m compileall -q media_importer/features/import_flow/steps/scrape.py
```

---

## 任务 1.8：编写单元测试

**文件**：`tests/test_match_engine.py`

**操作**：新建文件

```python
"""三级匹配引擎单元测试。"""

import unittest
from unittest.mock import MagicMock, patch
from media_importer.features.scraping.match_engine import MatchEngine
from media_importer.features.scraping.match_models import MatchResult, MatchConcern


class TestTier1ExactMatch(unittest.TestCase):
    """第一级精确匹配测试。"""

    def setUp(self):
        self.engine = MatchEngine()
        # Mock Provider
        self.provider = MagicMock()
        self.provider.__class__.__name__ = "MockProvider"

    def test_english_title_with_year_exact_match(self):
        """英文名+年份精确匹配 → AUTO_PASS"""
        from media_importer.features.providers.base import SearchItem
        self.provider.search.return_value = [
            SearchItem(id=27205, title="Inception", year=2010, media_type="movie")
        ]
        # Mock TitleMatcher
        with patch.object(self.engine.title_matcher, 'match_standard') as mock_match:
            mock_match.return_value = MagicMock(level="L1", T=1.0)
            result = self.engine.match("Inception.2010.1080p.BluRay.mkv", [self.provider])
        self.assertEqual(result.match_level, "AUTO_PASS")
        self.assertEqual(result.match_tier, 1)
        self.assertEqual(result.provider_id, 27205)

    def test_no_year_multiple_exact_matches(self):
        """无年份多同名 → NEEDS_CONFIRM + NO_YEAR_MULTI_MATCH"""
        from media_importer.features.providers.base import SearchItem
        self.provider.search.return_value = [
            SearchItem(id=1, title="Spider-Man", year=2002, media_type="movie"),
            SearchItem(id=2, title="Spider-Man", year=2017, media_type="movie"),
        ]
        with patch.object(self.engine.title_matcher, 'match_standard') as mock_match:
            mock_match.return_value = MagicMock(level="L3", T=0.7)
            result = self.engine.match("Spider-Man.mkv", [self.provider])
        self.assertEqual(result.match_level, "NEEDS_CONFIRM")
        concern_codes = [c.code for c in result.concerns]
        self.assertIn("NO_YEAR_MULTI_MATCH", concern_codes)

    def test_no_title_extracted(self):
        """无法提取标题 → NEEDS_CONFIRM + NO_TITLE"""
        with patch.object(self.engine.filename_cleaner, 'clean') as mock_clean:
            mock_clean.return_value = {"clean_title": "", "cjk_title": "", "year": None, "season": None, "episode": None}
            result = self.engine.match("video.mkv", [self.provider])
        self.assertEqual(result.match_level, "NEEDS_CONFIRM")
        concern_codes = [c.code for c in result.concerns]
        self.assertIn("NO_TITLE", concern_codes)

    def test_provider_search_exception(self):
        """Provider 搜索异常 → 不崩溃，进入下一级"""
        self.provider.search.side_effect = Exception("API timeout")
        result = self.engine.match("Inception.2010.mkv", [self.provider])
        # 应该不崩溃，进入第三级
        self.assertIn(result.match_level, ("NEEDS_CONFIRM",))

    def test_no_provider_results(self):
        """Provider 无结果 → NEEDS_CONFIRM + NO_PROVIDER_RESULT"""
        self.provider.search.return_value = []
        with patch.object(self.engine.title_matcher, 'match_standard') as mock_match:
            # TitleMatcher 不会被调用因为无结果
            result = self.engine.match("AbcdefgRandomMovie.2023.mkv", [self.provider])
        self.assertEqual(result.match_level, "NEEDS_CONFIRM")
        concern_codes = [c.code for c in result.concerns]
        self.assertIn("NO_PROVIDER_RESULT", concern_codes)


class TestConcernGeneration(unittest.TestCase):
    """疑虑原因生成测试。"""

    def test_concern_has_required_fields(self):
        """每个 concern 都有 code + message + detail"""
        concern = MatchConcern(
            code="NO_YEAR_MULTI_MATCH",
            message="找到 3 部同名作品",
            detail="搜索 'Spider-Man' 返回 3 条精确匹配",
        )
        self.assertEqual(concern.code, "NO_YEAR_MULTI_MATCH")
        self.assertTrue(concern.message)
        self.assertTrue(concern.detail)

    def test_all_concern_codes_defined(self):
        """7 种 concern.code 都已定义"""
        valid_codes = {
            "NO_YEAR_MULTI_MATCH", "YEAR_MISMATCH", "FUZZY_TITLE",
            "NO_PROVIDER_RESULT", "NO_TITLE", "CONFLICTING_INFO", "AI_UNCERTAIN",
        }
        # 验证代码中使用的 code 都在有效集合中
        self.assertEqual(len(valid_codes), 7)


class TestMatchResultSerialization(unittest.TestCase):
    """MatchResult 序列化测试。"""

    def test_to_dict(self):
        """MatchResult.to_dict() 可序列化"""
        result = MatchResult(
            match_level="AUTO_PASS",
            provider_id=27205,
            provider_title="Inception",
            match_tier=1,
            concerns=[MatchConcern(code="NO_TITLE", message="test", detail="test")],
        )
        d = result.to_dict()
        self.assertEqual(d["match_level"], "AUTO_PASS")
        self.assertEqual(len(d["concerns"]), 1)
        self.assertEqual(d["concerns"][0]["code"], "NO_TITLE")


if __name__ == "__main__":
    unittest.main()
```

**验证**：
```bash
python -m pytest tests/test_match_engine.py -v
```

---

## 任务 1.9：编写审核决策测试

**文件**：`tests/test_review_decision_v2.py`

**操作**：新建文件

```python
"""ReviewDecisionService 基于 match_level 的测试。"""

import unittest
from media_importer.features.import_flow.services.review import ReviewDecisionService


class TestReviewDecisionV2(unittest.TestCase):

    def setUp(self):
        self.service = ReviewDecisionService()

    def test_auto_pass_continues(self):
        """AUTO_PASS → continue"""
        decision = self.service.evaluate({"match_level": "AUTO_PASS", "title_cn": "测试", "type": "movie", "year": 2020})
        self.assertEqual(decision.action, "continue")

    def test_context_pass_continues(self):
        """CONTEXT_PASS → continue"""
        decision = self.service.evaluate({"match_level": "CONTEXT_PASS", "title_cn": "测试", "type": "movie", "year": 2020})
        self.assertEqual(decision.action, "continue")

    def test_needs_confirm_with_concerns(self):
        """NEEDS_CONFIRM 有疑虑 → confirm + 疑虑文案"""
        decision = self.service.evaluate({
            "match_level": "NEEDS_CONFIRM",
            "title_cn": "测试",
            "type": "movie",
            "year": 2020,
            "match_concerns": [{"code": "NO_YEAR_MULTI_MATCH", "message": "找到3部同名作品", "detail": "..."}],
        })
        self.assertEqual(decision.action, "confirm")
        self.assertIn("3部同名", decision.reason)

    def test_needs_confirm_no_concerns(self):
        """NEEDS_CONFIRM 无疑虑 → confirm + 默认文案"""
        decision = self.service.evaluate({
            "match_level": "NEEDS_CONFIRM",
            "title_cn": "测试",
            "type": "movie",
            "year": 2020,
            "match_concerns": [],
        })
        self.assertEqual(decision.action, "confirm")
        self.assertIn("人工确认", decision.reason)

    def test_empty_scraped(self):
        """空结果 → failed"""
        decision = self.service.evaluate({})
        self.assertEqual(decision.action, "failed")

    def test_missing_title(self):
        """标题缺失 → confirm"""
        decision = self.service.evaluate({"type": "movie", "year": 2020})
        self.assertEqual(decision.action, "confirm")
        self.assertIn("缺失", decision.reason)

    def test_backward_compatible_confidence_engine_param(self):
        """confidence_engine 参数保留但不用，不报错"""
        mock_engine = MagicMock()
        decision = self.service.evaluate(
            {"match_level": "AUTO_PASS", "title_cn": "测试", "type": "movie", "year": 2020},
            confidence_engine=mock_engine,
        )
        self.assertEqual(decision.action, "continue")
        mock_engine.assert_not_called()


if __name__ == "__main__":
    unittest.main()
```

**验证**：
```bash
python -m pytest tests/test_review_decision_v2.py -v
```

---

## 任务 1.10：编写配置迁移测试

**文件**：`tests/test_config_migration_v3.py`

**操作**：新建文件

```python
"""配置迁移 v2→v3 测试。"""

import unittest
from media_importer.core.config_migrations import _migrate_confidence_v2_to_v3


class TestConfigMigrationV3(unittest.TestCase):

    def test_removes_confidence_block(self):
        """移除 confidence 区块"""
        config = {
            "confidence": {"R_formula": "log", "pass_threshold": 0.8},
            "metadata": {"scrape_mode": "provider_first"},
        }
        result = _migrate_confidence_v2_to_v3(config)
        self.assertNotIn("confidence", result)
        self.assertEqual(result["metadata"]["scrape_mode"], "provider_first")

    def test_removes_confidence_threshold(self):
        """移除 llm.confidence_threshold"""
        config = {
            "llm": {"confidence_threshold": 0.8, "model": "test"},
            "metadata": {"scrape_mode": "provider_first"},
        }
        result = _migrate_confidence_v2_to_v3(config)
        self.assertNotIn("confidence_threshold", result["llm"])
        self.assertEqual(result["llm"]["model"], "test")

    def test_migrates_ai_only_to_provider_first(self):
        """ai_only → provider_first"""
        config = {"metadata": {"scrape_mode": "ai_only"}}
        result = _migrate_confidence_v2_to_v3(config)
        self.assertEqual(result["metadata"]["scrape_mode"], "provider_first")

    def test_migrates_hybrid_to_provider_first(self):
        """hybrid → provider_first"""
        config = {"metadata": {"scrape_mode": "hybrid"}}
        result = _migrate_confidence_v2_to_v3(config)
        self.assertEqual(result["metadata"]["scrape_mode"], "provider_first")

    def test_preserves_provider_first(self):
        """provider_first 不变"""
        config = {"metadata": {"scrape_mode": "provider_first"}}
        result = _migrate_confidence_v2_to_v3(config)
        self.assertEqual(result["metadata"]["scrape_mode"], "provider_first")

    def test_no_confidence_block_no_error(self):
        """无 confidence 区块不报错"""
        config = {"metadata": {"scrape_mode": "provider_first"}}
        result = _migrate_confidence_v2_to_v3(config)
        self.assertEqual(result["metadata"]["scrape_mode"], "provider_first")

    def test_preserves_manual_review(self):
        """manual_review 不受影响"""
        config = {
            "manual_review": {"enabled": False},
            "metadata": {"scrape_mode": "provider_first"},
        }
        result = _migrate_confidence_v2_to_v3(config)
        self.assertEqual(result["manual_review"]["enabled"], False)


if __name__ == "__main__":
    unittest.main()
```

**验证**：
```bash
python -m pytest tests/test_config_migration_v3.py -v
```

---

## 任务 1.11：迁移保留的旧测试

**操作**：将 `tests/test_confidence_engine.py` 中的 `TestFilenameCleaner` 和 `TestTitleMatcher` 类复制到新文件

**文件**：`tests/test_filename_cleaner.py`（新建）

从 `tests/test_confidence_engine.py` 中提取 `TestFilenameCleaner` 类的完整代码，放入此文件。确保 import 正确。

**文件**：`tests/test_title_matcher.py`（新建）

从 `tests/test_confidence_engine.py` 中提取 `TestTitleMatcher` 类的完整代码，放入此文件。确保 import 正确。

**验证**：
```bash
python -m pytest tests/test_filename_cleaner.py tests/test_title_matcher.py -v
```

---

## 任务 1.12：全量回归验证

**执行**：

```bash
# 1. 编译检查
PYTHONPYCACHEPREFIX=/private/tmp/nas_media_manage_pycache python -m compileall -q media_importer tests

# 2. 非 UI 测试
python -m pytest tests/ \
  --ignore=tests/test_*_ui.py \
  --ignore=tests/test_frontend_*.py \
  --ignore=tests/test_scrape_ui.py \
  -v

# 3. 架构护栏
python -m pytest tests/test_architecture_guards.py -v
```

**预期**：
- 编译检查：0 errors
- 新测试全部 GREEN
- 旧测试中 `test_confidence_engine.py` 的 `TestCalcR`、`TestAggregate`、`TestConfidenceEngineCalculate`、`TestConfidenceEngineAiOnly` 可能 FAIL（因为 review.py 改了），这是预期的，不影响
- 其他旧测试全部 GREEN

---

## 阶段 1 完成标准

- [ ] `match_models.py` 编译通过
- [ ] `match_engine.py` 编译通过
- [ ] `review.py` 改造后编译通过
- [ ] `scrape.py` 改造后编译通过
- [ ] DB 新增字段，旧数据库可自动迁移
- [ ] 配置迁移 v2→v3 正常工作
- [ ] `test_match_engine.py` 全部 GREEN
- [ ] `test_review_decision_v2.py` 全部 GREEN
- [ ] `test_config_migration_v3.py` 全部 GREEN
- [ ] `test_filename_cleaner.py` + `test_title_matcher.py` GREEN
- [ ] 非 UI 全量回归无新增失败
