from dataclasses import dataclass, field


@dataclass
class ReviewDecision:
    action: str       # continue / confirm / needs_review / failed
    reason: str = ""
    warnings: list = field(default_factory=list)


class ReviewDecisionService:
    def evaluate(self, scraped: dict) -> ReviewDecision:
        """根据刮削结果决定任务流向。

        基于 match_level 判断，不再依赖旧数值。
        """
        if not scraped:
            return ReviewDecision(action="failed", reason="刮削结果为空，无法验证")

        match_level = scraped.get("match_level", "NEEDS_CONFIRM")
        concerns = scraped.get("match_concerns", [])
        missing_fields, warnings = self._validate_required_fields(scraped)

        if missing_fields:
            reason = self._build_confirm_reason(scraped, missing_fields, concerns)
            return ReviewDecision(action="confirm", reason=reason, warnings=warnings)

        if match_level == "AUTO_PASS":
            return ReviewDecision(action="continue", warnings=warnings)

        if match_level == "CONTEXT_PASS":
            return ReviewDecision(action="continue", warnings=warnings)

        if match_level == "NEEDS_CONFIRM":
            reason = self._build_confirm_reason(scraped, missing_fields, concerns)
            return ReviewDecision(action="confirm", reason=reason, warnings=warnings)

        return ReviewDecision(action="failed", reason="匹配失败，无法识别", warnings=warnings)

    def _build_confirm_reason(self, scraped: dict, missing_fields: list, concerns: list) -> str:
        reason_parts = []
        for concern in concerns or []:
            if not isinstance(concern, dict):
                continue
            message = concern.get("message") or ""
            detail = concern.get("detail") or ""
            if message:
                reason_parts.append(message)
            if detail and detail != message:
                reason_parts.append(detail)

        ai_reasons = self._collect_ai_reasons(scraped.get("match_trace") or {})
        for reason in ai_reasons:
            if reason not in reason_parts:
                reason_parts.append(reason)

        if not reason_parts:
            provider_id = scraped.get("provider_id") or ""
            if provider_id:
                reason_parts.append("匹配结果需要人工确认")
            else:
                reason_parts.append("未匹配到可直接入库的 Provider 结果")

        suggestions = self._build_suggestions(missing_fields, scraped)
        if suggestions:
            reason_parts.append("缺失字段需人工确认")
            reason_parts.append("建议补充或核对：" + "、".join(suggestions))

        candidates = (scraped.get("match_trace") or {}).get("candidates") or []
        if candidates:
            reason_parts.append("已默认加载候选列表中排序最靠前的结果，请检查后确认")

        return "；".join(str(part) for part in reason_parts if part)

    def _collect_ai_reasons(self, match_trace: dict) -> list:
        reasons = []
        steps = []
        if isinstance(match_trace, dict):
            steps = match_trace.get("trace_steps") or match_trace.get("trace") or []
        if not isinstance(steps, list):
            return reasons
        for step in steps:
            if not isinstance(step, dict):
                continue
            ai_reason = str(step.get("ai_reason") or "").strip()
            if ai_reason:
                reasons.append(ai_reason)
        return reasons

    def _build_suggestions(self, missing_fields: list, scraped: dict) -> list:
        suggestions = []
        for field in missing_fields:
            if field == "title":
                suggestions.append("精确中文名或英文名")
            elif field == "year":
                suggestions.append("上映年份，用于区分同名作品")
            elif field == "media_type":
                suggestions.append("媒体类型（电影或电视剧）")
            elif field.startswith("year_invalid"):
                suggestions.append("合法年份")
        return suggestions

    def _validate_required_fields(self, scraped: dict):
        """校验必填字段。标题可由 title_cn、title_en 或 title 任一提供。"""
        missing_fields = []
        warnings = []

        title_cn = scraped.get("title_cn")
        title_en = scraped.get("title_en")
        title = scraped.get("title")
        year = scraped.get("year")
        media_type = scraped.get("media_type")

        has_title = bool(title_cn or title_en or title)
        has_type = bool(media_type)
        has_year = bool(year)

        if not has_title:
            missing_fields.append("title")
        if not has_type:
            missing_fields.append("media_type")
        if not has_year:
            if has_title and has_type:
                warnings.append(f"年份缺失(可接受，标题已识别: {title_cn or title_en or title})")
            else:
                missing_fields.append("year")
        if title_cn and not title_en:
            warnings.append("缺少英文名(可接受)")
        if year:
            try:
                parsed_year = int(year)
                if parsed_year < 1900 or parsed_year > 2030:
                    warnings.append(f"年份异常: {year}")
                    missing_fields.append("year_invalid")
            except (ValueError, TypeError):
                warnings.append(f"年份格式异常: {year}")

        return missing_fields, warnings
