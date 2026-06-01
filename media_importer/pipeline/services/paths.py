import os


def project_root_from_config(config: dict) -> str:
    config_path = config.get("_config_path", "")
    if not config_path:
        return ""
    return os.path.dirname(os.path.dirname(os.path.abspath(config_path)))


def resolve_project_path(path: str, config: dict) -> str:
    if not path or os.path.isabs(path):
        return path
    project_root = project_root_from_config(config)
    if not project_root:
        return path
    return os.path.join(project_root, path)


def import_roots_from_config(config: dict) -> list:
    templates = [
        rule.get("template", "")
        for rule in config.get("path_rules", [])
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
    allowed_dirs = [
        config.get("source_dir", ""),
        config.get("temp_dir", ""),
    ]
    for rule in config.get("path_rules", []):
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
