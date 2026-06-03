import os

from media_importer.features.providers import get_provider_class

from .prompt_builder import LLMPromptBuilder


GLOBAL_PROMPT_FILENAME = "scraper_prompts.md"
GLOBAL_PROMPT_EXAMPLE_FILENAME = "scraper_prompts.example.md"
PROMPT_DIMENSION_SEPARATOR = "【维度判断】\n当前需要判断的维度："


def load_global_prompt_for_ui(config_path: str = None) -> dict:
    system_prompt, using_custom = _load_global_prompt(config_path)
    return {"system_prompt": system_prompt, "using_custom": using_custom}


def load_provider_prompt_for_ui(config_path: str, provider_type: str) -> dict:
    default_prompt = LLMPromptBuilder._get_default_provider_prompt(provider_type)
    custom_prompt = _read_system_prompt(
        _prompt_file(config_path, _provider_prompt_filename(provider_type))
    )
    return {
        "system_prompt": custom_prompt or default_prompt,
        "using_custom": bool(custom_prompt),
    }


def save_global_prompt(config_path: str, body: dict):
    if not body:
        raise ValueError("Empty body")
    _write_prompt_file(
        _prompt_file(config_path, GLOBAL_PROMPT_FILENAME),
        _global_prompt_header(),
        (body.get("system_prompt", "") or "").strip(),
    )


def reset_global_prompt(config_path: str):
    _remove_prompt_file(_prompt_file(config_path, GLOBAL_PROMPT_FILENAME))


def save_provider_prompt(config_path: str, provider_type: str, body: dict) -> str:
    if not body:
        raise ValueError("Empty body")
    display_name = _provider_display_name(provider_type)
    _write_prompt_file(
        _prompt_file(config_path, _provider_prompt_filename(provider_type)),
        _provider_prompt_header(display_name),
        (body.get("system_prompt", "") or "").strip(),
    )
    return display_name


def reset_provider_prompt(config_path: str, provider_type: str) -> str:
    display_name = _provider_display_name(provider_type)
    _remove_prompt_file(_prompt_file(config_path, _provider_prompt_filename(provider_type)))
    return display_name


def _load_global_prompt(config_path: str = None) -> tuple:
    user_prompt = _read_system_prompt(_prompt_file(config_path, GLOBAL_PROMPT_FILENAME))
    if user_prompt:
        return user_prompt, True

    example_prompt = _read_system_prompt(
        _prompt_file(config_path, GLOBAL_PROMPT_EXAMPLE_FILENAME)
    )
    if example_prompt:
        return example_prompt, False

    default_prompt = LLMPromptBuilder.DEFAULT_SYSTEM_PROMPT
    if default_prompt.endswith(PROMPT_DIMENSION_SEPARATOR):
        default_prompt = default_prompt[:-len(PROMPT_DIMENSION_SEPARATOR)]
    return default_prompt, False


def _prompt_file(config_path: str, filename: str) -> str:
    return os.path.join(_prompts_root(config_path), "config", filename)


def _prompts_root(config_path: str = None) -> str:
    if config_path:
        return os.path.dirname(os.path.dirname(os.path.abspath(config_path)))
    return os.path.dirname(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    )


def _provider_prompt_filename(provider_type: str) -> str:
    cls = get_provider_class(provider_type)
    if cls and hasattr(cls, "provider_type"):
        return f"{cls.provider_type}_prompts.md"
    return f"{provider_type}_prompts.md"


def _provider_display_name(provider_type: str) -> str:
    cls = get_provider_class(provider_type)
    return cls.display_name if cls else provider_type


def _read_system_prompt(path: str) -> str:
    if not os.path.isfile(path):
        return ""
    try:
        import yaml as _yaml
        with open(path, "r", encoding="utf-8") as prompt_file:
            content = prompt_file.read()
        if "system_prompt:" not in content:
            return ""
        data = _yaml.safe_load(content)
        if data and isinstance(data, dict):
            return (data.get("system_prompt") or "").strip()
    except Exception:
        return ""
    return ""


def _write_prompt_file(path: str, header: str, system_prompt: str):
    from ruamel.yaml import YAML
    from ruamel.yaml.scalarstring import LiteralScalarString

    yaml = YAML()
    yaml.preserve_quotes = True
    yaml.width = 120

    doc = {}
    if system_prompt:
        doc["system_prompt"] = LiteralScalarString(system_prompt)

    with open(path, "w", encoding="utf-8") as prompt_file:
        prompt_file.write(header)
        yaml.dump(doc, prompt_file)


def _remove_prompt_file(path: str):
    if os.path.isfile(path):
        os.remove(path)


def _global_prompt_header() -> str:
    return """# ============================================================
# LLM 刮削提示词配置 - 用户自定义
# ============================================================
# 在此文件中修改提示词内容，程序会优先使用此处配置
# 提示词分为两半：上半部（此文件）由您编写，下半部（维度列表+JSON Schema）由程序自动追加
# 如需恢复出厂默认，点击 WebUI 中的 "重置为默认" 即可

"""


def _provider_prompt_header(display_name: str) -> str:
    return f"""# ============================================================
# LLM+{display_name} 刮削提示词配置
# ============================================================
# 当 {display_name} API 命中元数据后，使用此提示词让 AI 整理/校验 {display_name} 数据
# 程序会自动追加维度列表和 JSON Schema，此文件只需编写上半部
# 如需恢复出厂默认，点击 WebUI 中的 "重置为默认" 即可

"""
