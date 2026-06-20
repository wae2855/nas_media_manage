"""infrastructure.db 是 DB 层的推荐 import 入口(facade 阶段)。

本模块显式 re-export core.db 的 public 符号。消费者应从 media_importer.infrastructure.db import,
不应直接 import media_importer.core.db(architecture guard 会拦截)。

Phase 5 决策:先 facade,后真实文件搬迁。core/db/ 下的文件位置暂不变。
"""

from media_importer.core.db.constants import (
    VALID_STATUSES,
    DEFAULT_DIMENSIONS,
    CREATE_TASKS_TABLE,
    CREATE_SUBTITLES_TABLE,
    CREATE_DIMENSIONS_TABLE,
    CREATE_TASKS_INDEXES,
    CREATE_SUBTITLES_INDEXES,
)
from media_importer.core.db.connection import (
    init_db,
    _migrate_schema,
    _row_to_dict,
    _rows_to_dicts,
    _sqlite_conn_lock,
    logger,
)
from media_importer.core.db.migrations import (
    _seed_dimensions,
)
from media_importer.core.db.dimension_repo import (
    get_all_dimensions,
    get_enabled_dimensions,
    get_dimension,
    update_dimension,
    enable_dimension,
    disable_dimension,
    reset_dimension,
)
from media_importer.core.db.task_repo import (
    create_task,
    get_task,
    find_by_source_path,
    find_by_source_filename,
    find_by_fingerprint,
    list_tasks,
    update_task,
    count_by_status,
    count_by_status_and_stage,
    delete_task,
    clear_tasks,
    has_running_tasks,
    count_by_specific_status,
    find_failed_too_many,
    get_next_pending,
    list_all_tasks,
    count_all_tasks,
)
from media_importer.core.db.subtitle_repo import (
    create_subtitles,
    get_subtitles_by_task,
    update_subtitle,
    update_subtitles_by_task,
    count_subtitles_by_task,
)
from media_importer.core.db.cleaner_repo import (  # noqa: F401
    get_cleaner_records,
    get_cleaner_status,
    init_cleaner_tables,
    save_cleaner_record,
)