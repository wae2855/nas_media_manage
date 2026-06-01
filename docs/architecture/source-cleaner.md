# Source Cleaner Architecture

源目录清理器独立于主任务流，用于识别并清理源目录中的垃圾文件、广告文件、Sample、无关文本等。

## Entry Points

- `media_importer/domains/source_cleaning/cleaner.py`
- `media_importer/domains/source_cleaning/records.py`
- `media_importer/storage/source_cleaner.py` compatibility alias
- `media_importer/api/source_cleaner_handlers.py`
- `media_importer/core/db/cleaner_repo.py`
- `media_importer/webui/js/config.js`

## Boundaries

- 主任务流处理视频和字幕任务。
- 源目录清理器处理任务之外的源目录维护。
- 删除行为必须遵守回收站安全规则。
- 旧 `storage/source_cleaner.py` public import 保持可用，不能删除。
