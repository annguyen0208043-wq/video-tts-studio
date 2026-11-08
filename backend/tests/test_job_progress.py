import threading

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.session import Base
from app.models import Job, Project
from app.services import job_service
from app.services.job_service import JobManager


def test_slow_progress_writer_does_not_block_and_coalesces_latest_value():
    manager = JobManager()
    entered = threading.Event()
    release = threading.Event()
    submitted = threading.Event()
    published = threading.Event()
    batches = []
    def write(progress):
        batches.append(progress)
        if len(batches) == 1:
            entered.set()
            release.wait(3)
        else:
            published.set()
    manager._write_progress_batch = write
    try:
        manager._report_progress("render", 1)
        assert entered.wait(2)
        def report():
            for value in range(2, 81):
                manager._report_progress("render", value)
            submitted.set()
        thread = threading.Thread(target=report)
        thread.start()
        assert submitted.wait(1), "Encoder callbacks waited for the database"
        thread.join()
        release.set()
        assert published.wait(2)
        assert batches == [{"render": 1}, {"render": 80}]
    finally:
        release.set()
        if manager._progress_thread:
            manager._progress_thread.join(timeout=3)
        manager.executor.shutdown()
        manager.tts_executor.shutdown()


def test_late_progress_cannot_overwrite_completed_or_cancelled_jobs(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{(tmp_path / 'progress.db').as_posix()}")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    monkeypatch.setattr(job_service, "SessionLocal", factory)
    with factory() as db:
        project = Project(name="Progress guard")
        db.add(project)
        db.flush()
        rows = [Job(project_id=project.id, kind="render", status=status, progress=progress, input_json={})
                for status, progress in [("rendering", 1), ("completed", 100), ("cancelled", 5)]]
        db.add_all(rows)
        db.commit()
        ids = [row.id for row in rows]
    JobManager._write_progress_batch(dict.fromkeys(ids, 75))
    with factory() as db:
        assert [db.get(Job, job_id).progress for job_id in ids] == [75, 100, 5]
    engine.dispose()
