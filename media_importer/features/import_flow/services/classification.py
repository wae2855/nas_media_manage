import os
from dataclasses import dataclass
from typing import Optional

from media_importer.features.configuration import ConfigView

from .classification_rules import classify, render_template
from .paths import resolve_project_path


@dataclass
class ClassificationResult:
    import_path: str
    classify_result: str
    dimensions_text: str
    used_fallback: bool = False
    rules_description: str = ""


class ClassificationService:
    def __init__(self, config: dict):
        self.config = ConfigView.from_dict(config)

    def classify_task(self, task: dict, enabled_dims: Optional[set] = None) -> ClassificationResult:
        path_rules = self.config.paths.path_rules
        scraped = task.get("scrape_result", {})
        dimensions = task.get("scrape_dimensions", {})
        dimensions_text = self._format_dimensions(dimensions)

        import_path = classify(scraped, path_rules, enabled_dims)
        used_fallback = False
        if not import_path:
            fallback_dir = self.config.paths.fallback_dir
            if fallback_dir:
                import_path = render_template(fallback_dir, scraped)
                used_fallback = True
            else:
                return ClassificationResult(
                    import_path="",
                    classify_result="",
                    dimensions_text=dimensions_text,
                    rules_description=self._format_rules(path_rules),
                )

        import_path = resolve_project_path(import_path, self.config)  # type: ignore[arg-type]
        return ClassificationResult(
            import_path=import_path,
            classify_result=import_path,
            dimensions_text=dimensions_text,
            used_fallback=used_fallback,
        )

    @staticmethod
    def _format_dimensions(dimensions: dict) -> str:
        if not dimensions:
            return "无"
        return ", ".join(f"{key}={value}" for key, value in dimensions.items())

    @staticmethod
    def _format_rules(path_rules: list) -> str:
        rules = []
        for index, rule in enumerate(path_rules):
            conditions = rule.get("conditions", {})
            conditions_text = ", ".join(
                f"{key}={value}" for key, value in conditions.items()
            )
            rules.append(f"规则{index + 1}: [{conditions_text}]")
        return "; ".join(rules) if rules else "无规则配置"

    def preview_classify(self, task: dict, override_dimensions: Optional[dict] = None,
                         override_filename: Optional[str] = None, enabled_dims: Optional[set] = None) -> dict:
        """预览分类结果，不执行任何文件操作。"""
        path_rules = self.config.paths.path_rules
        scraped = task.get("scrape_result", {})
        dimensions = override_dimensions if override_dimensions else task.get("scrape_dimensions", {})
        dimensions_text = self._format_dimensions(dimensions)

        import_path = classify(scraped, path_rules, enabled_dims)
        used_fallback = False
        warnings = []
        matched_rule = None

        if not import_path:
            fallback_dir = self.config.paths.fallback_dir
            if fallback_dir:
                import_path = render_template(fallback_dir, scraped)
                used_fallback = True
                warnings.append("未匹配到入库规则，已使用兜底目录")
            else:
                return {
                    "import_path": "",
                    "final_filename": "",
                    "full_path": "",
                    "matched_rule": None,
                    "used_fallback": False,
                    "warnings": ["未匹配到任何入库规则，且未配置兜底目录（fallback_dir），无法预览入库路径"],
                    "rules_description": self._format_rules(path_rules),
                    "dimensions_text": dimensions_text,
                }

        import_path = resolve_project_path(import_path, self.config)  # type: ignore[arg-type]

        final_filename = override_filename or task.get("final_filename", "") or task.get("source_filename", "")
        full_path = os.path.join(import_path, final_filename) if import_path and final_filename else ""

        return {
            "import_path": import_path,
            "final_filename": final_filename,
            "full_path": full_path,
            "matched_rule": matched_rule,
            "used_fallback": used_fallback,
            "warnings": warnings,
            "rules_description": self._format_rules(path_rules) if used_fallback else "",
            "dimensions_text": dimensions_text,
        }
