# Module: Recycle Feature

## Code

- `media_importer/features/recycle/manager.py`
- `media_importer/features/recycle/browser.py`
- `media_importer/features/recycle/__init__.py`
- `media_importer/core/recycle/manager.py` compatibility alias
- `media_importer/core/recycle/browser.py` compatibility alias
- `media_importer/core/safety.py` safety facade
- `media_importer/api/recycle_handlers.py`

## Responsibility

回收站业务域，负责把文件或目录安全移入回收站、生成元数据、浏览回收站、恢复、永久删除和按保留天数清理。

当前实现所在地：

- 移入回收站: `media_importer/features/recycle/manager.py`
- 浏览/恢复/永久删除/过期清理: `media_importer/features/recycle/browser.py`

## Compatibility

以下旧路径必须继续可用：

- `media_importer.core.recycle`
- `media_importer.core.recycle.manager`
- `media_importer.core.recycle.browser`
- `media_importer.core.safety`

`core/safety.py` 是文件安全 facade，删除/覆盖相关调用仍可从这里进入。

## Safety

- 影视文件删除或覆盖必须先调用回收站入口。
- 临时文件边界之外不得直接 `os.remove()`。
- 回收站元数据必须保留 `original_path`、`source_zone`、`reason`、`moved_at`。
- 恢复和永久删除只处理回收站内已有条目。

## Tests

- `tests/test_feature_recycle_compatibility.py`
- `tests/test_recycle_safety.py`
- `tests/test_integration_recycle.py`
