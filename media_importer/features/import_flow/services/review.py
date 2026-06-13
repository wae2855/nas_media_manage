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