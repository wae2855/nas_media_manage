import os

from media_importer.features.configuration import ConfigView


def _view(config) -> ConfigView:
    if isinstance(config, ConfigView):
        return config
    return ConfigView.from_dict(config)


def project_root_from_config(config: dict) -> str:
    return _view(config).paths.project_root


def resolve_project_path(path: str, config: dict) -> str:
    if not path or os.path.isabs(path):
        return path
    project_root = project_root_from_config(config)
    if not project_root:
        return path
    return os.path.join(project_root, path)


def import_roots_from_config(config: dict) -> list:
    view = _view(config)
    if view.paths.library_roots:
        return [root.get("path", "") for root in view.paths.library_roots
                if root.get("enabled", True) is not False and root.get("path")]
    if view.paths.library_root:
        return [view.paths.library_root]
    templates = [
        rule.get("template", "")
        for rule in view.paths.path_rules
        if rule.get("template")
    ]
    roots = []
    for template in templates:
        template = resolve_project_path(template, config)
        template = os.path.normpath(template)
        parts = template.split(os.sep)
        for index, part in enumerate(parts):
            if part.startswith("{"):
                if index > 0:
                    roots.append(os.sep.join(parts[:index]))
                break
        else:
            roots.append(template)
    return roots


def allowed_dirs_from_config(config: dict) -> list:
    view = _view(config)
    allowed_dirs = [
        view.paths.source_dir,
        view.paths.temp_dir,
    ]
    if view.paths.library_roots:
        allowed_dirs.extend(
            root.get("path", "") for root in view.paths.library_roots
            if root.get("enabled", True) is not False
        )
        return [path for path in allowed_dirs if path]
    if view.paths.library_root:
        allowed_dirs.append(view.paths.library_root)
        return [path for path in allowed_dirs if path]
    # fallback_dir 是合法入库目标（无规则命中时的兜底路径，Phase 2 矩阵测试发现的历史缺口）
    fallback_dir = getattr(view.paths, "fallback_dir", "")
    if fallback_dir:
        allowed_dirs.append(fallback_dir)
    for rule in view.paths.path_rules:
        template = rule.get("template", "")
        if not template:
            continue
        parts = template.split("/")
        for index, part in enumerate(parts):
            if part.startswith("{"):
                allowed_dirs.append("/".join(parts[:index]))
                break
        else:
            allowed_dirs.append(template.rstrip("/"))
    return allowed_dirs
