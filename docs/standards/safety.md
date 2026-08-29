# Safety Standards

## File Delete Rule

所有删除或覆盖影视文件必须先移入回收站，禁止直接 `os.remove()` 删除源文件或入库文件。

## Temporary Files

临时文件可直接删除的边界：

- `.tmp`
- `.copying`
- 明确位于 `temp_dir` 的处理副本

## Allowed Directories

文件移动和删除应传入 `allowed_base_dirs` 或等价保护，避免路径穿越和误删。

路径校验、权限检查、安全移动/删除和指纹基础能力位于 `media_importer/infrastructure/filesystem/`。`media_importer/core/safety.py` 只作为旧导入兼容 facade。

## Source Cleanup

源文件处理由三种互斥模式控制：

- `preserve_all`: 不写入源目录；
- `preserve_media`: 保留媒体，仅由源目录清理器回收规则/LLM 判定的垃圾；
- `recycle_source_unit`: 同一来源单元全部媒体任务成功且快照未变化后整组回收。

失败、跳过、待确认、存在未建任务媒体、快照变化或挂载/回收目录异常时，来源单元必须保持不变。源目录根本身永远不得作为文件夹来源单元移动。

主任务完成、跳过或临时文件场景的源文件策略位于 `media_importer/features/source_files/`。源目录清理器仍位于 `media_importer/features/source_cleaning/`。

## Deploy Directory

`deploy/` 目录不是默认开发源。同步部署目录必须作为明确任务执行。
