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
    confirm_reason: str = ""     # 匹配成功或失败的原因说明（NEEDS_CONFIRM 时填充原因）

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
            "confirm_reason": self.confirm_reason,
        }