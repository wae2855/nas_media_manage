import threading

from media_importer.core.db.cleaner_repo import get_cleaner_status
from media_importer.core.db.connection import _sqlite_conn_lock, init_db
from media_importer.core.db.dimension_repo import get_all_dimensions
from media_importer.core.db.subtitle_repo import get_subtitles_by_task
from media_importer.core.db.task_repo import list_tasks


def test_cleaner_repository_uses_shared_sqlite_lock(tmp_path):
    conn = init_db(str(tmp_path / "media.db"))
    started = threading.Event()
    finished = threading.Event()

    def read_status():
        started.set()
        get_cleaner_status(conn)
        finished.set()

    with _sqlite_conn_lock:
        worker = threading.Thread(target=read_status)
        worker.start()
        assert started.wait(1)
        assert not finished.wait(0.05)

    assert finished.wait(1)
    worker.join(timeout=1)
    conn.close()


def test_shared_connection_serializes_concurrent_repository_reads(tmp_path):
    conn = init_db(str(tmp_path / "media.db"))
    barrier = threading.Barrier(8)
    failures = []

    def read_repeatedly(worker_id):
        try:
            barrier.wait(timeout=2)
            for _ in range(50):
                if worker_id % 2:
                    get_cleaner_status(conn)
                else:
                    list_tasks(conn, page=1, page_size=5)
                get_subtitles_by_task(conn, "missing-task")
                get_all_dimensions(conn)
        except Exception as exc:  # pragma: no cover - asserted through failures
            failures.append(exc)

    workers = [threading.Thread(target=read_repeatedly, args=(index,)) for index in range(8)]
    for worker in workers:
        worker.start()
    for worker in workers:
        worker.join(timeout=5)

    assert not failures
    assert all(not worker.is_alive() for worker in workers)
    conn.close()
