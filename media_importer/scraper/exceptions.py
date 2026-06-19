"""兼容入口:exceptions 已迁移到 media_importer.features.scraping.errors。

本文件保留为旧路径兼容层,请勿新增依赖。生产代码应直接 import 新路径。

绕过 features/scraping 包级 __init__ 的反向 import 链路(scraper.llm_scraper -> scraper.exceptions ->
features.scraping/__init__ -> scraper.llm_scraper),用 importlib 直接加载子模块文件,
避免循环导入。S-Phase 3b 迁移 llm_scraper 后,此 hack 可删除,恢复常规 from-import 写法。
"""

import importlib.util
import os
import sys as _sys


_HERE = os.path.dirname(os.path.abspath(__file__))
_ERRORS_PATH = os.path.normpath(
    os.path.join(_HERE, "..", "features", "scraping", "errors.py")
)
_LAZY_MOD_KEY = "media_importer.features.scraping.errors"


def _load_errors():
    """直接加载 errors.py 文件,绕过 features/scraping 包的 __init__ 初始化。"""
    if _LAZY_MOD_KEY in _sys.modules:
        return _sys.modules[_LAZY_MOD_KEY]
    spec = importlib.util.spec_from_file_location(_LAZY_MOD_KEY, _ERRORS_PATH)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load spec for {_ERRORS_PATH}")
    mod = importlib.util.module_from_spec(spec)
    _sys.modules[_LAZY_MOD_KEY] = mod
    spec.loader.exec_module(mod)
    return mod


_EXPORTS = ("LLMApiError", "LLMWebSearchError", "LLMScrapeError")


def __getattr__(name):
    if name in _EXPORTS:
        value = getattr(_load_errors(), name)
        globals()[name] = value
        return value
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def __dir__():
    return sorted(list(globals().keys()) + list(_EXPORTS))