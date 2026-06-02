# Module: Core Recycle

## Code

- `media_importer/core/recycle/manager.py` compatibility alias
- `media_importer/core/recycle/browser.py` compatibility alias
- `media_importer/core/recycle/__init__.py`
- `media_importer/features/recycle/manager.py`
- `media_importer/features/recycle/browser.py`

## Responsibility

回收站移动、恢复、浏览、永久删除和过期清理。

实现已迁移到 `media_importer/features/recycle/`。`core/recycle/*` 保留旧 import 和测试 patch 路径兼容。

## Safety Rule

删除或覆盖影视文件必须走回收站。不得绕过 `move_to_recycle()` 直接删除源文件或入库文件。

## Tests

- `tests/test_recycle_safety.py`
- `tests/test_feature_recycle_compatibility.py`
- `tests/test_integration_recycle.py`
