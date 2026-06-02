# Repository Structure

本文件定义新架构下仓库目录的归属。后续移动、归档和删除文件时以此为准。

## Classification

| Status | Meaning |
|--------|---------|
| `current` | 当前事实来源，AI 和开发者应优先读取。 |
| `feature_target` | 将迁移为 feature-first 新结构的目标目录。 |
| `infrastructure` | 可被多个 feature 复用的底层设施。 |
| `entrypoint` | CLI、HTTP、启动组装入口。 |
| `frontend` | 前端实现，后续单独重做。 |
| `archive_candidate` | 历史文档、旧脚本、旧测试、废弃结构或被替代内容。 |
| `generated_ignored` | 生成物或本地运行产物，不作为源码事实。 |

## Target Code Shape

```text
media_importer/
├── app/                 # CLI/API/startup composition
├── features/            # feature-first business modules
│   ├── import_flow/
│   ├── scraping/
│   ├── configuration/
│   ├── tasks/
│   ├── source_cleaning/
│   ├── recycle/
│   ├── providers/
│   └── prompts/
├── infrastructure/      # shared DB/filesystem/provider/LLM/metrics/logger adapters
├── shared/              # tiny shared constants/helpers without feature ownership
└── webui/               # current frontend; planned for redesign
```

## Current Top-level Inventory

| Path | Status | Decision |
|------|--------|----------|
| `media_importer/` | current | Main package. Will be reshaped into feature-first code. |
| `tests/` | current | Keep only current/gated tests; archive historical scripts after inventory. |
| `docs/` | current | Rebuild around current facts; archive old documents. |
| `config/` | current | Runtime config examples and local config. Configuration feature must document it. |
| `deploy/` | generated_ignored | Package tooling stays; generated package workspace remains ignored. |
| `data/` | generated_ignored | Local runtime data, not source truth. |
| `logs/` | generated_ignored | Local logs, not source truth. |
| `screenshots/` | archive_candidate | UI test artifacts; archive or ignore after frontend plan. |
| `build/` | generated_ignored | Local/package build output, not architecture evidence. |
| `scripts/` | current | Utility scripts; keep small and documented when used by workflows. |
| `hermes/` | current | Notification integration package copied by release build. |
| `.trae/` | archive_candidate | Local agent/tooling context; not product source truth. |
| `.pytest_cache/` | generated_ignored | Local pytest cache. |
| `theme_preview.html` | archive_candidate | Root-level visual artifact; verify with frontend redesign before deleting. |
| `config.yaml.example` | current | Root config example. Keep aligned with config docs. |
| `README.md` | current | Human-facing project overview. |
| `pytest.ini` | current | Test configuration. |
| `requirements.txt` | current | Dependency source. |
| `start.sh` | entrypoint | Keep until app entrypoints are reorganized. |
| `AGENTS.md` | current | AI execution entry. Must point to current docs only. |

## Current Package Inventory

| Path | Status | Decision |
|------|--------|----------|
| `media_importer/api/` | entrypoint | Keep route table, then distribute handlers by feature where useful. |
| `media_importer/core/` | infrastructure | Split into `features/tasks`, `features/configuration`, and shared infrastructure. |
| `media_importer/features/` | current | Feature-first business source of truth. Expand here before touching old technical layers. |
| `media_importer/pipeline/` | archive_candidate | Replaced by `features/import_flow`; archive after imports are moved. |
| `media_importer/scraper/` | feature_target | Move to `features/scraping` and `features/providers`. |
| `media_importer/storage/` | infrastructure | Split filesystem utilities into infrastructure and feature-owned services. |
| `media_importer/monitor/` | infrastructure | Keep or move under notification/monitoring feature. |
| `media_importer/notify/` | feature_target | Move to notification/monitoring feature. |
| `media_importer/webui/` | frontend | Keep temporarily; frontend redesign is a later workstream. |
| `media_importer/config/` | archive_candidate | Package-local config copy; verify need before archiving. |
| `media_importer/data/` | generated_ignored | Runtime data; should not be source truth. |

## Documentation Inventory

| Path | Status | Decision |
|------|--------|----------|
| `docs/README.md` | current | Main documentation entry. |
| `docs/INDEX.md` | current | Feature-first index after rebuild. |
| `docs/ai-map.md` | current | AI task navigation after rebuild. |
| `docs/architecture/` | current | Current architecture facts only. |
| `docs/features/` | feature_target | New feature documentation location. |
| `docs/modules/` | archive_candidate | Replace with feature docs or keep only as temporary bridge. |
| `docs/product/` | current | Product and frontend preparation facts. |
| `docs/workflows/` | current | Closed-loop lifecycle workflows. |
| `docs/tracking/` | current | Pending acceptance and completed item records. |
| `docs/standards/` | current | Rules updated after user acceptance. |
| `docs/testing/` | current | Current test policy and inventory. |
| `docs/plans/` | current | Only active/pending plans. Completed or replaced plans go to archive. |
| `docs/decisions/` | current | Active ADRs; superseded ADRs remain but must state historical status. |
| `docs/_archive/` | archive | Historical documentation and replaced plans only. |
| `docs/_archive/2026-06-02-feature-first-reorg/docs/legacy-chinese/` | archive | Historical Chinese docs moved out of active docs. |
| `docs/_archive/2026-06-02-feature-first-reorg/docs/plans/` | archive | Completed, superseded, or replaced plans. |
| `docs/_archive/2026-06-02-feature-first-reorg/tests/` | archive | Historical script-style tests removed from default test tree. |

## Archive Rule

Current docs must not link archived files as current facts. If history is needed, link to an archive README or ADR that explains the historical context.
