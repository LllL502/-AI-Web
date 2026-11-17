"""Compensate filesystem writes when the owning database transaction fails."""
from contextlib import contextmanager
from contextvars import ContextVar
import logging
from django.db import transaction

_writes = ContextVar('item_media_writes', default=None)
logger = logging.getLogger(__name__)


@contextmanager
def atomic_media():
    parent = _writes.get()
    writes = [] if parent is None else parent
    start = len(writes)
    token = _writes.set(writes)
    def cleanup():
        for storage, name in reversed(writes[start:]):
            try:
                storage.delete(name)
            except Exception:
                logger.exception('Media compensation failed for %s; run reconcile_media', name)
        del writes[start:]
    try:
        with transaction.atomic():
            yield
            rollback_only = transaction.get_rollback()
        if rollback_only:
            cleanup()
    except BaseException:
        cleanup()
        raise
    finally:
        _writes.reset(token)


def save_file(field, name, content):
    name = field.field.generate_filename(field.instance, name)
    writes = _writes.get()
    if writes is None:
        raise RuntimeError('Media writes require atomic_media')
    if field.storage.exists(name):
        raise RuntimeError('Unexpected UUID media filename collision')
    # Register before storage writes, including a backend that writes then raises.
    writes.append((field.storage, name))
    actual = field.storage.save(name, content)
    if actual != name:
        writes.append((field.storage, actual))
    field.name = actual
    field._committed = True
