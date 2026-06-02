# Module Map

## Dependency Direction

```text
api / media_importer.py / monitor
        |
        v
features
        |
        v
infrastructure adapters
        |
        v
shared helpers
```

Rules:

- `features/` 是业务事实源，可以调用 infrastructure 和 shared。
- `api`、CLI 和 watcher 是入口层，只调用 feature application/service，不承载复杂业务策略。
- `core`、`storage`、`scraper`、`notify`、`monitor` 中仍在用的实现需要逐步迁移到 feature 或 infrastructure。
- 旧 wrapper 可以依赖 feature，但 feature 不应依赖旧 wrapper。
- `webui` 只通过 HTTP API 与后端交互。
- `features/source_cleaning/`、`features/recycle/`、`features/import_flow/` 已是当前业务实现入口。

## Documentation Mapping

业务文档在 [../features/](../features/)；仓库结构在 [repository-structure.md](repository-structure.md)；代码和文档索引在 [../INDEX.md](../INDEX.md)。
