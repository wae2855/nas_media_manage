# Module Map

## Dependency Direction

```text
api / media_importer.py / monitor
        |
        v
features
        |
        v
infrastructure adapters / current implementation directories
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

## Allowed During Migration

- `features/*` can temporarily call `core`, `storage`, `scraper`, `notify`, and `monitor` implementation files when no feature-owned service exists yet.
- `features/*/__init__.py` may re-export legacy implementation objects as public feature APIs while the implementation moves.
- `api/*_handlers.py` may call legacy implementations only when no feature service exists; new behavior should introduce or reuse a feature service first.

## Not Allowed For New Work

- Do not add new public imports from archived paths such as `media_importer.pipeline`.
- Do not add new business strategies to `storage/` if they belong to import flow, source cleaning, or recycle.
- Do not add new scraping/provider/prompt public entrypoints under `scraper/`; expose them through `features/scraping`, `features/providers`, or `features/prompts`.
- Do not let API handlers become the owner of classification, dedup, task lifecycle, scraping, file deletion, or provider decisions.

## Migration Priority

1. Move real implementation behind existing feature public APIs.
2. Split filesystem, DB, client, logger, and metrics adapters into infrastructure.
3. Thin API/CLI/watcher after feature services exist.
4. Add dependency direction tests for each migrated slice.

## Documentation Mapping

业务文档在 [../features/](../features/)；仓库结构在 [repository-structure.md](repository-structure.md)；代码和文档索引在 [../INDEX.md](../INDEX.md)。
