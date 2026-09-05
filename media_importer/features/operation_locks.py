"""Process-wide serialization for task mutations that can race file disposal."""

from __future__ import annotations

from functools import wraps
from threading import Lock, RLock

_source_disposition_locks: dict[str, RLock] = {}
_source_disposition_registry_lock = Lock()


def serialize_source_disposition(key_resolver):
    """Serialize only operations targeting the same source unit or task key."""

    def decorate(function):
        @wraps(function)
        def wrapped(*args, **kwargs):
            key = str(key_resolver(*args, **kwargs) or "unbound")
            with _source_disposition_registry_lock:
                operation_lock = _source_disposition_locks.setdefault(key, RLock())
            with operation_lock:
                return function(*args, **kwargs)

        return wrapped

    return decorate


__all__ = ["serialize_source_disposition"]
