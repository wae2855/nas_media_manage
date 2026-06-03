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

源文件清理必须受配置控制，并明确区分：

- 主任务完成后的源视频/字幕清理；
- 源目录清理器处理的垃圾文件清理。

主任务完成、跳过或临时文件场景的源文件策略位于 `media_importer/features/source_files/`。源目录清理器仍位于 `media_importer/features/source_cleaning/`。

## Deploy Directory

`deploy/` 目录不是默认开发源。同步部署目录必须作为明确任务执行。
