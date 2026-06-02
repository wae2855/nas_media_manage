from dataclasses import dataclass, field


@dataclass
class ReviewDecision:
    action: str
    reason: str = ""
    warnings: list = field(default_factory=list)


class ReviewDecisionService:
    def evaluate(self, scraped: dict, confidence_engine) -> ReviewDecision:
        if not scraped:
            return ReviewDecision(action="failed", reason="刮削结果为空，无法验证")

        missing_fields, warnings = self._validate_required_fields(scraped)
        if missing_fields:
            reason = f"刮削信息不足，需要人工确认。缺失字段: {'; '.join(missing_fields)}"
            if warnings:
                reason += f"。警告: {'; '.join(warnings)}"
            return ReviewDecision(action="confirm", reason=reason, warnings=warnings)

        confidence = scraped.get("confidence", 0)
        gate_blocked = scraped.get("confidence_gate_blocked")
        search_conf = scraped.get("confidence_search", 0)
        data_gate = scraped.get("confidence_data_gate", 1)
        level = confidence_engine.get_confidence_level(confidence, gate_blocked)

        if level == "NEEDS_REVIEW" and gate_blocked:
            blocked_dim = gate_blocked.get("dim_name", "未知维度")
            blocked_source = gate_blocked.get("source", "未知来源")
            reason = f"来源不信任: {blocked_dim} 的来源 {blocked_source} 未在信任列表中"
            gate_reason = gate_blocked.get("reason", "")
            if gate_reason:
                reason += f" ({gate_reason})"
            return ReviewDecision(action="needs_review", reason=reason, warnings=warnings)

        if level == "FAILED":
            return ReviewDecision(
                action="failed",
                reason=f"置信度过低({confidence:.3f}, 搜索={search_conf:.3f})",
                warnings=warnings,
            )

        if level == "NEEDS_REVIEW":
            reason = f"置信度偏低({confidence:.3f}, 搜索={search_conf:.3f})，需要人工审核"
            if warnings:
                reason += f"。警告: {'; '.join(warnings)}"
            return ReviewDecision(action="confirm", reason=reason, warnings=warnings)

        if level == "CONFIRMING":
            reason = f"置信度{confidence:.3f}(搜索={search_conf:.3f})，需要人工确认"
            if warnings:
                reason += f"。警告: {'; '.join(warnings)}"
            return ReviewDecision(action="confirm", reason=reason, warnings=warnings)

        return ReviewDecision(action="continue", warnings=warnings)

    def _validate_required_fields(self, scraped: dict):
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
