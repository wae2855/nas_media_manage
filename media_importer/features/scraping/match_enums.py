"""刮削匹配相关的枚举定义"""


class TierShortReason:
    """L2: 一句话原因枚举（程序兜底，AI 应优先返回 ≤30 字）"""
    # Tier 1
    TIER1_UNIQUE = "唯一精确匹配"
    TIER1_TOP_RATED = "同名{count}部，自动选评分最高"
    TIER1_MULTI = "{count}部同名作品，需确认"
    TIER1_FUZZY = "标题不完全匹配"
    TIER1_NO_RESULT = "Provider 无结果"
    # Tier 2
    TIER2_HIGH_PASS = "AI 高确定性匹配通过"
    TIER2_MEDIUM = "AI 建议候选，需确认"
    TIER2_LOW = "AI 低确定性，需确认"
    TIER2_AI_FAILED = "AI 不可用，降级到候选列表"
    TIER2_INVALID = "文件名无可识别影视信息"
    # Tier 3
    TIER3_FALLBACK = "AI 不可用，候选列表供选择"
    # 兜底
    UNKNOWN = "匹配结果未知"


class WhySelected:
    """L4: 最终候选选择原因枚举"""
    UNIQUE_MATCH = "unique_match"           # 唯一精确匹配
    TOP_RATED = "top_rated"                 # 评分打破平局
    AI_SUGGESTION = "ai_suggestion"         # AI 建议（含年份纠正等）
    FIRST_CANDIDATE = "first_candidate"     # Provider 排序第一（AI 不可用降级）
    USER_PICK = "user_pick"                 # 用户人工选择（review 后写入）


class MatchTier:
    """L1: match_tier 枚举（明确语义）"""
    TIER1 = 1  # Provider 精确匹配
    TIER2 = 2  # AI 辅助匹配
    TIER3 = 3  # 用户确认降级
