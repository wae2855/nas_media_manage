# Configuration Architecture

## Current Pattern

- 配置格式：YAML。
- 业务入口：`media_importer/features/configuration/`。
- 应用层辅助：`media_importer/features/configuration/application_service.py`。
- 加载实现：`media_importer/core/config_loader.py`。
- 自动迁移：`media_importer/core/config_migrations.py`。
- 校验入口：`media_importer/core/config_validator.py`。
- 前端配置 API：`media_importer/api/config_handlers.py`。
- 业务读取门面：`media_importer.features.configuration.ConfigView`，实现位于 `media_importer/core/config_view.py`。

## Change Rule

新增配置项必须同步：

```text
config.yaml.example
-> config_loader
-> config_migrations
-> config_validator
-> config_view
-> config_handlers
-> webui
-> docs
-> tests
```

## ConfigView

`ConfigView` 是业务层读取配置的稳定入口。业务代码从 `media_importer.features.configuration` 导入它；底层实现文件保留在 `core/config_view.py`。它保留 `raw` 原始 dict 兼容旧代码，同时提供 typed sections：

- `paths`
- `source_policy`
- `dedup`
- `filename_templates`
- `manual_review`
- `metadata`
- `llm`
- `scanner`
- `source_cleaner`

新增配置项时，loader/migration/validator 仍负责配置文件生命周期；业务代码优先通过 `ConfigView` 读取，避免散落深层 `config.get(...)`。

当前 `config_handlers.py` 中的 UI 配置投影、分区保存拆分、权限检查请求组装、路径测试结果组装和 watcher 状态投影已下沉到 configuration feature application service；`reload` 和 watcher/notifier 全局编排仍待后续继续薄化。
