from media_importer.api import globals
from media_importer.features.tasks import delete_task as delete_task_service

from .utils import json_response


def delete_task(handler, task_id: str, delete_files: bool = False,
                globals_module=None, respond=None):
    state = globals_module or globals
    write_response = respond or json_response

    result = delete_task_service(
        state._global_task_manager,
        state._config or {},
        task_id,
        delete_files=delete_files,
    )
    write_response(handler, result.status_code, data=result.data, message=result.message)
