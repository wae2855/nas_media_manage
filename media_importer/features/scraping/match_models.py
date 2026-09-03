"""两级匹配策略的数据模型。"""

from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class SelectedCandidate:
    """L4: 最终选中的候选信息（结构化）"""
    provider_type: str = ""
    provider_id: str = ""
    title: str = ""
    year: Optional[int] = None
    media_type: str = ""
    why_selected: str = ""  # WhySelected 枚举值
    score: Optional[float] = None  # 评分（若适用）

    def to_dict(self) -> dict:
        return {
            "provider_type": self.provider_type,
            "provider_id": self.provider_id,
            "title": self.title,
            "year": self.year,
            "media_type": self.media_type,
            "why_selected": self.why_selected,
            "score": self.score,
        }


@dataclass
class MatchConcern:
    """匹配疑虑原因。"""
    code: str       # NO_TITLE / FUZZY_TITLE / CONFLICTING_INFO / IDENTITY_CONFLICT / IDENTITY_LOOKUP_FAILED / CLOSE_CANDIDATES
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
    """两级匹配引擎的最终结果。"""
    match_level: str            # AUTO_PASS / CONTEXT_PASS / NEEDS_CONFIRM / FAILED
    provider_id: Optional[str] = None
    provider_title: str = ""
    match_tier: int = 0         # 命中的级别（1/2/3）
    concerns: List[MatchConcern] = field(default_factory=list)
    trace_steps: List[MatchTraceStep] = field(default_factory=list)
    candidates: List[dict] = field(default_factory=list)  # 第三级的候选列表
    confirm_reason: str = ""     # 废弃，保留字段以便编译，但不再写入新值

    # 新增字段
    tier_short_reason: str = ""           # L2
    ai_reason: str = ""                   # L3
    selected_candidate: Optional[SelectedCandidate] = None  # L4
    identity_evidence: dict = field(default_factory=dict)

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
            # 新字段
            "tier_short_reason": self.tier_short_reason,
            "ai_reason": self.ai_reason,
            "selected_candidate": self.selected_candidate.to_dict() if self.selected_candidate else None,
            "identity_evidence": self.identity_evidence,
            # confirm_reason 废弃，不再输出
        }
