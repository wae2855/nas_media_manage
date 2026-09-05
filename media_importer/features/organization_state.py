"""Shared task organization state constants without feature-layer imports."""

from functools import wraps
from threading import RLock

_reorganization_lock = RLock()


def serialize_reorganization(function):
    """Single-process server: serialize child creation and resurrection across connections."""
    @wraps(function)
    def wrapped(*args, **kwargs):
        with _reorganization_lock:
            return function(*args, **kwargs)
    return wrapped

TASK_KIND_IMPORT = "IMPORT"
TASK_KIND_REORGANIZE = "REORGANIZE"
ORGANIZATION_FALLBACK_PENDING = "FALLBACK_PENDING"
ORGANIZATION_ORGANIZED = "ORGANIZED"

__all__ = [
    "serialize_reorganization",
    "TASK_KIND_IMPORT",
    "TASK_KIND_REORGANIZE",
    "ORGANIZATION_FALLBACK_PENDING",
    "ORGANIZATION_ORGANIZED",
]
