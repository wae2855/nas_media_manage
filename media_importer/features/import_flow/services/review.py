from dataclasses import dataclass, field


@dataclass
class ReviewDecision:
    action: str       # continue / confirm / needs_review / failed
    concerns: list = field(default_factory=list)  # 结构化关注点列表
    warnings: list = field(default_factory=list)


class ReviewDecisionService:
    def evaluate(self, scraped: dict, required_dimensions=None, dim_labels=None) -> ReviewDecision:
        """根据刮削结果决定任务流向。

        基于 match_level 判断，返回结构化 concerns 而非拼接字符串。
        required_dimensions：必填维度名列表（如 ['restricted_level']），
        值缺失/null/空时即使匹配通过也强制进入人工确认。
        dim_labels：维度名 → 业务名映射，用于面向用户的提示文案。
        """
        if not scraped:
            return ReviewDecision(
                action="failed",
                concerns=[{"code": "EMPTY_RESULT", "message": "刮削结果为空，无法验证", "detail": ""}],
            )

        match_level = scraped.get("match_level", "NEEDS_CONFIRM")
        existing_concerns = scraped.get("match_concerns", [])
        missing_fields, warnings = self._validate_required_fields(scraped)

        if missing_fields:
            new_concerns = self._build_concerns(scraped, missing_fields, existing_concerns)
            return ReviewDecision(action="confirm", concerns=new_concerns, warnings=warnings)

        # 必填维度拦截：值缺失时强制人工干预（即使 AUTO_PASS）
        missing_dims = self._validate_required_dimensions(scraped, required_dimensions)
        if missing_dims:
            new_concerns = self._build_concerns(scraped, [], existing_concerns)
            labels = dim_labels or {}
            dim_names = "、".join(labels.get(d, d) for d in missing_dims)
            new_concerns.append({
                "code": "REQUIRED_DIM_MISSING",
                "message": f"必填维度缺失，需人工填写: {dim_names}",
                "detail": "刮削未能确定以下维度值，已按配置拦截待人工处理",
            })
            return ReviewDecision(action="confirm", concerns=new_concerns, warnings=warnings)

        if match_level == "AUTO_PASS":
            return ReviewDecision(action="continue", warnings=warnings)

        if match_level == "CONTEXT_PASS":
            return ReviewDecision(action="continue", warnings=warnings)

        if match_level == "NEEDS_CONFIRM":
            new_concerns = self._build_concerns(scraped, missing_fields, existing_concerns)
            return ReviewDecision(action="confirm", concerns=new_concerns, warnings=warnings)

        return ReviewDecision(
            action="failed",
            concerns=[{"code": "MATCH_FAILED", "message": "匹配失败，无法识别", "detail": ""}],
            warnings=warnings,
        )

    @staticmethod
    def _validate_required_dimensions(scraped: dict, required_dimensions) -> list:
        """校验必填维度：值为 None/空串/缺失 时视为缺失。"""
        if not required_dimensions:
            return []
        dimensions = scraped.get("dimensions", {}) or {}
        missing = []
        for dim_name in required_dimensions:
            value = dimensions.get(dim_name)
            if value is None or str(value).strip() in ("", "None", "null"):
                missing.append(dim_name)
        return missing

    def _build_concerns(self, scraped: dict, missing_fields: list, existing_concerns: list) -> list:
        """构建结构化关注点列表（不再拼接字符串）"""
        new_concerns = []

        for concern in existing_concerns or []:
            if isinstance(concern, dict) and concern.get("message"):
                new_concerns.append(concern)

        if missing_fields:
            suggestions = self._build_suggestions(missing_fields, scraped)
            detail = "建议补充或核对：" + "、".join(suggestions) if suggestions else ""
            new_concerns.append({
                "code": "MISSING_FIELDS",
                "message": "缺失字段需人工确认",
                "detail": detail,
            })

        provider_id = scraped.get("provider_id") or ""
        if not provider_id:
            new_concerns.append({
                "code": "NO_PROVIDER_MATCH",
                "message": "未匹配到可直接入库的 Provider 结果",
                "detail": "",
            })

        candidates = (scraped.get("match_trace") or {}).get("candidates") or []
        if candidates:
            new_concerns.append({
                "code": "CANDIDATES_AVAILABLE",
                "message": "已默认加载候选列表中排序最靠前的结果，请检查后确认",
                "detail": "",
            })

        return new_concerns

    def _build_suggestions(self, missing_fields: list, scraped: dict) -> list:
        suggestions = []
        for field_name in missing_fields:
            if field_name == "title":
                suggestions.append("精确中文名或英文名")
            elif field_name == "year":
                suggestions.append("上映年份，用于区分同名作品")
            elif field_name == "media_type":
                suggestions.append("媒体类型（电影或电视剧）")
            elif field_name.startswith("year_invalid"):
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
