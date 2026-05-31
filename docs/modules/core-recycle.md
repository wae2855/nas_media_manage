# Module: Core Recycle

## Code

- `media_importer/core/recycle/manager.py`
- `media_importer/core/recycle/browser.py`
- `media_importer/core/recycle/__init__.py`

## Responsibility

回收站移动、恢复、浏览、永久删除和过期清理。

## Safety Rule

删除或覆盖影视文件必须走回收站。不得绕过 `move_to_recycle()` 直接删除源文件或入库文件。

## Tests

- `tests/test_recycle_and_safety.py`
- `tests/test_integration_recycle.py`
