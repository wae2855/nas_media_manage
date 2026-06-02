from dataclasses import dataclass

from media_importer.core.config_view import ConfigView
from media_importer.storage.classifier import classify, render_template
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

    def classify_task(self, task: dict) -> ClassificationResult:
        path_rules = self.config.paths.path_rules
        scraped = task.get("scrape_result", {})
        dimensions = task.get("scrape_dimensions", {})
        dimensions_text = self._format_dimensions(dimensions)

        import_path = classify(scraped, path_rules)
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

        import_path = resolve_project_path(import_path, self.config)
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
