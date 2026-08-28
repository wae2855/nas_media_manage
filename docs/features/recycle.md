# Recycle Feature

回收站负责所有源文件、入库文件和清理文件的安全删除边界。任何影视文件删除或覆盖前都必须先进入回收站。

## Code Entrypoints

| Path | Role |
|------|------|
| `media_importer/features/recycle/manager.py` | Move files and companions into recycle with metadata. |
| `media_importer/features/recycle/browser.py` | List, restore, delete, and cleanup recycle entries. |
| `media_importer/features/recycle/ledger.py` | SQLite recycle-item ledger, stable opaque IDs, sidecar import, and root-boundary checks. |
| `media_importer/features/recycle/__init__.py` | Public recycle feature API. |
| `media_importer/infrastructure/filesystem/safety.py` | Path validation and low-level safe filesystem primitives. |

## Related Areas

- Config: `source_policy.recycle_dir`, source directories, library directories.
- API: recycle list, restore, delete, cleanup handlers.
- Storage: file move/overwrite flows must call recycle before destructive action.
- Frontend: recycle management view and source cleaner actions.

## Tests

- `tests/test_recycle_safety.py`
- `tests/test_recycle_list_payload.py`
- `tests/test_recycle_api_boundary.py`
- `tests/test_verified_transfer.py`
- File operation regression tests that touch delete/overwrite behavior.

## Safety Rules

- Do not use direct `os.remove()` for media/source/library files.
- Temporary files are only directly deletable inside explicit temp or `.tmp` / `.copying` boundaries.
- Metadata must preserve original path, reason, task id when available, and source zone.
- HTTP list/restore/delete uses server-side recycle item IDs; clients cannot submit physical recycle paths.
- Restore and cross-device recycle reuse verified `.copying` transfer. Source/recycle data is removed only after size and SHA-256 verification plus atomic publish.
- `overwrite` restore fails closed until the existing destination has first been recorded and moved into recycle; it never falls back to permanent deletion.
- `recycle_dir` must already exist on a local disk. Missing roots are treated as a mount/authorization failure and are not recreated.

## Migration Notes

- New code should import from `media_importer.features.recycle`.
- Keep `docs/standards/safety.md` synchronized with any destructive behavior change.
