import json
from typing import Dict, Any


class LLMPromptBuilder:
    DEFAULT_SYSTEM_PROMPT = """你是一个专业的影视信息刮削助手。
请根据提供的视频文件名和字幕文件名，提取影视元数据信息。

重要原则：
1. 先根据文件名提取可确定的元数据（标题、分辨率、季/集编号等）。
2. 对于文件名中缺失但你可以通过对这部作品的了解推断出的信息（如年份、类型等），
   请大胆填写，不要留空。例如：看到 Breaking Bad S01E02，你应该知道这是
   《绝命毒师》第一季第二集，首播年份为2008年，类型为tv，不是纪录片。
3. 只有当你完全无法判断时，才将字段设为 null。
4. certainty 评分应基于信息完整性：能确定标题+类型+年份的应 high，
    信息严重不足的才给 low。

【数据源优先级 - 非常重要】
刮削时请优先参考以下权威数据源（按优先级从高到低）：
1. 豆瓣 (douban.com) - 中文影视信息最全面权威，优先参考中文译名、评分、分类
2. TMDB (themoviedb.org) - 全球影视元数据标准，辅助验证
3. IMDb (imdb.com) - 英语影视信息参考
4. 维基百科 - 辅助验证年代、分类等基础信息
5. 其他粉丝站点 - 仅供小众作品参考

注意事项：
- 对于中文影视，优先以豆瓣信息为准
- 若各数据源信息不一致，优先信任官方数据
- 对于年代久远或小众作品，可参考粉丝站点
- AI可能产生"幻觉"，请交叉验证关键信息

【正确与错误刮削示例】
文件名示例：
  文件: "Wuthering.Heights.2024.1080p.BluRay.x264.mkv"
  ✅ 正确: title_cn="呼啸山庄", title_en="Wuthering Heights", year=2024
  ❌ 错误: title_cn="简风暴", title_en="Wuthering Heights", year=2024

文件名示例：
  文件: "besthd-virgin.territory.2023.1080p.mkv"
  ✅ 正确: title_cn="七日谈"
  ❌ 错误: title_cn="童贞领地"

文件名示例：
  文件: "Breaking.Bad.S01E01.1080p.mkv"
  ✅ 正确: title_cn="绝命毒师", title_en="Breaking Bad", year=2008, season=1, episode=1
  ❌ 错误: title_cn="绝命制毒", year=2009

文件名示例：
  文件: "Spirited.Away.2001.720p.mkv"
  ✅ 正确: title_cn="千与千寻", title_en="Spirited Away", year=2001
  ❌ 错误: title_cn="神秘失踪"

【标题翻译规则 - 非常重要】
- 对于已知的影视作品，请使用官方中文译名，不要直译英文标题
- 常见经典作品的正确译名：
  * Wuthering Heights → 呼啸山庄（不是"简风暴"或"呼啸的山丘"）
  * besthd-virgin.territory → 七日谈（成人系列频道，非直译"童贞领地"）
  * Spirited Away → 千与千寻（不是"神秘失踪"）
  * Inception → 盗梦空间（不是"奠基"）
  * Interstellar → 星际穿越（不是"星际"）
  * 各种成人影视/系列请使用其公认的中文名称
- 如果不确定某个标题的官方译名，可以：
  1. 尝试搜索对应的中文名称
  2. 使用常见的意译名称
  3. 切勿机械直译导致歧义

【维度判断】
当前需要判断的维度："""

    TIER2_CORRECT_PROMPT = """你是一个影视标题纠正助手。根据原始文件名和目录上下文，纠正标题并判断确定性。

## 核心规则

1. 文件名中的数字可能是分辨率（2160p、1080p）、年份（2017）或标题本身（2046、2012）。
2. **分辨率的判断**：数字后带 p/i/px 后缀 → 分辨率，不是年份也不是标题。
3. **年份的判断**：四位数字（1900-2029范围），前后有点或分隔符 → 年份。
4. **标题内含数字**：如果数字是标题固定部分（如「银翼杀手2049」、「2012」），必须在 corrected_title 中保留。
5. **标题就是数字**：当整个文件名的核心就是数字（如 2012.2009.mkv），corrected_title 保留数字，年份从文件名中的年份提取。

## 6个示例

示例1：
  文件名: 美丽人生.2160P.mkv
  路径: /video/电影/美丽人生.2160P.mkv
  → {"corrected_title": "美丽人生", "corrected_year": null, "media_type_hint": "movie", "certainty": "medium", "reason": "标题含2160P，识别为分辨率后缀，标题应为美丽人生", "suggestion": "美丽人生"}

示例2：
  文件名: 银翼杀手2049.2017.BluRay.2160p.mkv
  路径: /video/银翼杀手2049.2017.BluRay.2160p.mkv
  → {"corrected_title": "银翼杀手2049", "corrected_year": 2017, "media_type_hint": "movie", "certainty": "high", "reason": "2049是标题固定部分，2017是年份，2160p是分辨率", "suggestion": "银翼杀手2049"}

示例3：
  文件名: 2012.2009.1080p.BluRay.mkv
  路径: /video/2012.2009.1080p.BluRay.mkv
  → {"corrected_title": "2012", "corrected_year": 2009, "media_type_hint": "movie", "certainty": "high", "reason": "标题就是数字2012，年份2009，1080p是分辨率", "suggestion": "2012"}

示例4：
  文件名: 2046.2004.720p.mkv
  路径: /video/2046.2004.720p.mkv
  → {"corrected_title": "2046", "corrected_year": 2004, "media_type_hint": "movie", "certainty": "high", "reason": "标题就是数字2046，年份2004，720p是分辨率", "suggestion": "2046"}

示例5：
  文件名: jinji.S01E02.mp4
  路径: /tv/紧急/jinji.S01E02.mp4
  → {"corrected_title": "jinji", "corrected_year": null, "media_type_hint": "tv", "certainty": "medium", "reason": "可能是剧集，标题为jinji，无年份信息", "suggestion": "jinji"}

示例6：
  文件名: xXx.Return.of.Xander.Cage.2017.1080p.BluRay.x264-CHDWEB.mkv
  路径: /video/xXx.Return.of.Xander.Cage.2017.1080p.BluRay.x264-CHDWEB.mkv
  → {"corrected_title": "xXx: Return of Xander Cage", "corrected_year": 2017, "media_type_hint": "movie", "certainty": "high", "reason": "标准命名，标题和年份明确", "suggestion": "xXx: Return of Xander Cage"}

## 输出格式

返回 JSON，不要包含任何其他文字：
{"corrected_title": "纠正后的标题", "corrected_year": 年份或null, "media_type_hint": "movie|tv|null", "certainty": "high|medium|low", "reason": "判断理由", "suggestion": "建议的搜索关键词"}"""

    def __init__(self, dimensions=None):
        self.dimensions = dimensions or []
        self._provider_prompts = {}

    def load_dimensions(self, dimensions):
        self.dimensions = dimensions

    @staticmethod
    def _get_default_prompts() -> dict:
        sep = "\n【维度判断】\n当前需要判断的维度：\n"
        return {
            "system": LLMPromptBuilder.DEFAULT_SYSTEM_PROMPT,
            "sep": sep
        }

    @staticmethod
    def _get_default_provider_prompt(provider_type='tmdb') -> str:
        from media_importer.features.providers import get_provider_class
        cls = get_provider_class(provider_type)
        if cls:
            template = cls.get_context_template()
            if template:
                return template.strip()
        from media_importer.features.providers import MetadataProvider
        return MetadataProvider.get_context_template().strip()

    @staticmethod
    def _get_default_tmdb_prompt() -> str:
        return LLMPromptBuilder._get_default_provider_prompt('tmdb')

    def _build_system_prompt(self, exclude_dims: set = None) -> str:
        SEP = "【维度判断】\n当前需要判断的维度："

        base = self.DEFAULT_SYSTEM_PROMPT

        if base.endswith(SEP):
            base = base[:-len(SEP)]

        prompt_parts = [base, "", SEP, ""]

        dims = [d for d in self.dimensions if d.get('name') not in (exclude_dims or set())]
        for i, dim in enumerate(dims, 1):
            name = dim.get('name', '')
            label = dim.get('label', name)
            values = dim.get('values', [])
            values_str = ', '.join(str(v) for v in values) if values else ''
            ai_hint = dim.get('ai_prompt', '')
            if ai_hint:
                prompt_parts.append(f"{i}. {label}（{name}）: [{values_str}] — {ai_hint}")
            else:
                prompt_parts.append(f"{i}. {label}（{name}）: [{values_str}]")

        prompt_parts.append("")
        prompt_parts.append("请严格按以下JSON格式返回，不要添加任何解释文字：")

        json_schema = self._build_json_schema(exclude_dims)
        prompt_parts.append(json.dumps(json_schema, ensure_ascii=False, indent=2))

        return '\n'.join(prompt_parts)

    def _build_system_prompt_with_provider(self, exclude_dims=None, provider_name=None) -> str:
        SEP = "【维度判断】\n当前需要判断的维度："

        base = ''
        provider_type = None

        if provider_name:
            from media_importer.features.providers import get_all_registered_providers
            for ptype, cls in get_all_registered_providers().items():
                if cls.display_name == provider_name or ptype == provider_name:
                    provider_type = ptype
                    break

        if provider_type:
            base = self._provider_prompts.get(provider_type, '')

        if not base and provider_type:
            from media_importer.features.providers import get_provider_class
            cls = get_provider_class(provider_type)
            if cls:
                base = cls.get_context_template()

        if not base:
            from media_importer.features.providers import MetadataProvider
            base = MetadataProvider.get_context_template()

        if base.endswith(SEP):
            base = base[:-len(SEP)]

        prompt_parts = [base, "", SEP, ""]

        dims = [d for d in self.dimensions if d.get('name') not in (exclude_dims or set())]
        for i, dim in enumerate(dims, 1):
            name = dim.get('name', '')
            label = dim.get('label', name)
            values = dim.get('values', [])
            values_str = ', '.join(str(v) for v in values) if values else ''
            ai_hint = dim.get('ai_prompt', '')
            if ai_hint:
                prompt_parts.append(f"{i}. {label}（{name}）: [{values_str}] — {ai_hint}")
            else:
                prompt_parts.append(f"{i}. {label}（{name}）: [{values_str}]")

        prompt_parts.append("")
        prompt_parts.append("【重要规则】如果你无法确定某个维度的值（例如没找到该影片的相关信息，或信息不足以做出判断），请将该维度值设为空字符串 \"\"，不要猜测或编造。空值会触发人工干预流程，由人工确认。")
        prompt_parts.append("")
        prompt_parts.append("请严格按以下JSON格式返回，不要添加任何解释文字：")

        json_schema = self._build_json_schema(exclude_dims)
        prompt_parts.append(json.dumps(json_schema, ensure_ascii=False, indent=2))

        return '\n'.join(prompt_parts)

    def _build_json_schema(self, exclude_dims: set = None) -> Dict[str, Any]:
        dimensions_schema = {}
        for dim in self.dimensions:
            name = dim.get('name')
            if exclude_dims and name in exclude_dims:
                continue
            values = dim.get('values', [])
            if values:
                dimensions_schema[name] = f"{'|'.join(str(v) for v in values)}|null"
            else:
                dimensions_schema[name] = "string|null"

        schema = {
            "title_cn": "string|null",
            "title_en": "string|null",
            "year": "int|null",
            "resolution": "string|null",
            "quality": "string|null",
            "language": "string|null",
            "type": "movie|tv",
            "season": "int|null",
            "episode": "int|null",
            "dimensions": dimensions_schema,
            "certainty": "high|low|null"
        }

        return schema

    def _build_series_prompt(self) -> str:
        SEP = "【维度判断】\n当前需要判断的维度："

        base = self.DEFAULT_SYSTEM_PROMPT

        if base.endswith(SEP):
            base = base[:-len(SEP)]

        prompt_parts = [base, "", SEP, ""]

        for i, dim in enumerate(self.dimensions, 1):
            name = dim.get('name', '')
            label = dim.get('label', name)
            values = dim.get('values', [])
            values_str = ', '.join(str(v) for v in values) if values else ''
            prompt_parts.append(f"{i}. {label}（{name}）: [{values_str}]")

        prompt_parts.append("")
        prompt_parts.append("请严格按以下JSON格式返回，不要添加任何解释文字：")

        dimensions_schema = {}
        for dim in self.dimensions:
            name = dim.get('name')
            values = dim.get('values', [])
            if values:
                dimensions_schema[name] = f"{'|'.join(str(v) for v in values)}|null"
            else:
                dimensions_schema[name] = "string|null"

        schema = {
            "title_cn": "string|null",
            "title_en": "string|null",
            "year": "int|null",
            "type": "tv",
            "dimensions": dimensions_schema,
            "certainty": "high|low|null"
        }

        prompt_parts.append(json.dumps(schema, ensure_ascii=False, indent=2))

        return '\n'.join(prompt_parts)

    def _build_series_prompt_with_provider(self, provider_name=None) -> str:
        SEP = "【维度判断】\n当前需要判断的维度："

        base = ''
        provider_type = None

        if provider_name:
            from media_importer.features.providers import get_all_registered_providers
            for ptype, cls in get_all_registered_providers().items():
                if cls.display_name == provider_name or ptype == provider_name:
                    provider_type = ptype
                    break

        if provider_type:
            base = self._provider_prompts.get(provider_type, '')

        if not base and provider_type:
            from media_importer.features.providers import get_provider_class
            cls = get_provider_class(provider_type)
            if cls:
                base = cls.get_context_template()

        if not base:
            from media_importer.features.providers import MetadataProvider
            base = MetadataProvider.get_context_template()

        if base.endswith(SEP):
            base = base[:-len(SEP)]

        prompt_parts = [base, "", SEP, ""]

        for i, dim in enumerate(self.dimensions, 1):
            name = dim.get('name', '')
            label = dim.get('label', name)
            values = dim.get('values', [])
            values_str = ', '.join(str(v) for v in values) if values else ''
            prompt_parts.append(f"{i}. {label}（{name}）: [{values_str}]")

        prompt_parts.append("")
        prompt_parts.append("请严格按以下JSON格式返回，不要添加任何解释文字：")

        dimensions_schema = {}
        for dim in self.dimensions:
            name = dim.get('name')
            values = dim.get('values', [])
            if values:
                dimensions_schema[name] = f"{'|'.join(str(v) for v in values)}|null"
            else:
                dimensions_schema[name] = "string|null"

        schema = {
            "title_cn": "string|null",
            "title_en": "string|null",
            "year": "int|null",
            "type": "tv",
            "dimensions": dimensions_schema,
            "certainty": "high|low|null"
        }

        prompt_parts.append(json.dumps(schema, ensure_ascii=False, indent=2))

        return '\n'.join(prompt_parts)

    def _build_series_prompt_with_context(self) -> str:
        return self._build_series_prompt_with_provider()
