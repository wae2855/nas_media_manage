# Module: Core DB

## Code

- `media_importer/core/db/connection.py`
- `media_importer/core/db/task_repo.py`
- `media_importer/core/db/subtitle_repo.py`
- `media_importer/core/db/dimension_repo.py`
- `media_importer/core/db/cleaner_repo.py`
- `media_importer/core/db/migrations.py`
- `media_importer/core/db/constants.py`

## Responsibility

SQLite 初始化、迁移、repo 访问和共享常量。

## Extension Points

- 新字段：更新 migration、repo、测试和数据模型文档。
- 新状态：更新 constants、task lifecycle、API、前端、测试和文档。

## Tests

- `tests/test_task_operations.py`
- task/config/source-cleaner 相关单测
