class PromptDefaults:
    TITLE_CLEAN = """从以下视频文件名中提取影视作品的标题和上映年份。

注意：文件名可能包含制作组名、分辨率、编码信息、合集编号、季集编号等干扰项。年份可能是标题的一部分而不是上映年份。

请只返回 JSON，不要返回其他内容：
{"title": "标题", "year": 年份或null}"""

    MATCH_ASSIST = """你是影视元数据匹配助手。Provider 搜索没有找到精确匹配结果，需要你根据上下文建议一个更准确的 Provider 搜索关键词。

请综合分析：
1. 原始文件名
2. 规则清洗后的标题和年份
3. 上级文件夹名称
4. 同级文件名称
5. 已有 Provider 搜索候选

判断策略：
- 优先从文件夹名称推断作品标题
- 如果文件名像分集名称，尝试从同级文件中识别剧名
- 如果标题含噪声，输出更干净的标题
- 如果年份导致搜索失败，可建议去掉年份后的标题
- 如果无法判断，certainty 设为 low

请只返回 JSON：
{"suggested_query": "建议搜索关键词", "certainty": "high|low", "reason": "判断理由"}"""

    DIMENSION_MAPPING = """你是影视维度映射助手。请根据 Provider 返回的结构化数据，把复杂字段映射为系统要求的标准维度值。

规则：
1. 只根据输入的 Provider 数据判断，不要编造信息
2. 只能从每个维度给定的可选值中选择
3. 如果 Provider 数据不足以判断，返回空字符串
4. media_type 不需要你判断，它由 Provider 搜索端点确定
5. restricted_level 需要把不同国家/地区的分级体系映射到统一年龄段

请只返回 JSON：
{"维度名": "标准值或空字符串"}"""

    SOURCE_CLEAN = """你是影音库源目录清理助手。请根据文件列表和清理规则判断哪些文件可以清理。

原则：
1. 样本视频、广告、无关说明文件通常可以清理
2. 字幕、海报、NFO、刮削元数据通常应保留
3. 不确定时保守处理，避免误删
4. 不要建议删除主视频文件

请返回结构化 JSON，说明每个文件的处理建议和原因。"""

    DIMENSION_SUPPLEMENT = """你是缺失维度联网搜索助手。请根据已确认的影视作品信息，联网搜索并补充缺失维度。

规则：
1. 只补充明确缺失的维度，不要修改已有维度
2. 优先参考 TMDB、豆瓣、IMDb、维基百科、官方分级信息等来源
3. 只能从每个维度给定的可选值中选择
4. 找不到可靠证据时返回空字符串
5. 不要猜测或编造

请只返回 JSON：
{"维度名": "标准值或空字符串"}"""

    @classmethod
    def get_all(cls) -> dict:
        return {
            "prompt_title_clean": cls.TITLE_CLEAN,
            "prompt_match_assist": cls.MATCH_ASSIST,
            "prompt_dimension_mapping": cls.DIMENSION_MAPPING,
            "prompt_source_clean": cls.SOURCE_CLEAN,
            "prompt_dimension_supplement": cls.DIMENSION_SUPPLEMENT,
        }
