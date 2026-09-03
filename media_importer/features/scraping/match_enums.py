"""刮削匹配相关的枚举定义"""


class TierShortReason:
    """L2: 一句话原因枚举（程序兜底，AI 应优先返回 ≤30 字）"""
    # Tier 1
    TIER1_UNIQUE = "唯一精确匹配"
    TIER1_EVIDENCE_CONVERGED = "文件名与目录名指向同一作品"
    TIER1_FOLDER_RESCUE = "文件名信息不足，目录片名与年份精确匹配"
    TIER1_PROVIDER_ALIAS = "标题命中影视资料官方别名"
    TIER1_TOP_RATED = "同名{count}部，预选热度最高，请确认"
    TIER1_MULTI = "{count}部同名作品，需确认"
    TIER1_FUZZY = "标题不完全匹配"
    TIER1_NO_RESULT = "影视库无结果"
    # Tier 2
    TIER2_HIGH_PASS = "AI 高确定性匹配通过"
    TIER2_MEDIUM = "AI 建议候选，需确认"
    TIER2_LOW = "AI 低确定性，需确认"
    TIER2_AI_FAILED = "AI 不可用，降级到候选列表"
    TIER2_INVALID = "文件名无可识别影视信息"
    # Tier 3
    TIER3_FALLBACK = "无法自动确认，请选择正确作品"
    # 兜底
    UNKNOWN = "匹配结果未知"


class WhySelected:
    """L4: 最终候选选择原因枚举"""
    UNIQUE_MATCH = "unique_match"           # 唯一精确匹配
    EVIDENCE_CONVERGED = "evidence_converged"  # 文件名与目录名收敛到同一作品
    FOLDER_RESCUE = "folder_rescue"         # 弱文件名由可信目录片名补足
    PROVIDER_ALIAS = "provider_alias"       # 标题命中 Provider 官方别名
    TOP_RATED = "top_rated"                 # 评分打破平局
    AI_SUGGESTION = "ai_suggestion"         # AI 建议（含年份纠正等）
    FIRST_CANDIDATE = "first_candidate"     # Provider 排序第一，仅供用户确认
    USER_PICK = "user_pick"                 # 用户人工选择（review 后写入）
    EXPLICIT_ID = "explicit_provider_id"     # 文件名显式 Provider ID
    NFO_ID = "nfo_provider_id"               # 相邻 NFO Provider ID
    FOLDER_ID = "folder_provider_id"         # 作品目录显式 Provider ID
    HISTORICAL_BINDING = "historical_provider_binding"  # 已保存的历史 Provider 绑定


class MatchTier:
    """L1: match_tier 枚举（明确语义）"""
    TIER1 = 1  # Provider 精确匹配
    TIER2 = 2  # AI 辅助匹配
    TIER3 = 3  # 用户确认降级
