import os
import time
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QObject, QThread, QTimer, Slot
from PySide6.QtTest import QSignalSpy, QTest
from PySide6.QtWidgets import QApplication
import pytest

from romkit_core.tasks import report
from romkit_studio.services.task_runner import TaskRunner

pytestmark = pytest.mark.integration


def wait_for(spy, timeout=5000):
    deadline = time.monotonic() + timeout / 1000
    while spy.count() == 0 and time.monotonic() < deadline:
        QApplication.processEvents()
        time.sleep(0.005)
    assert spy.count(), "Task did not finish"


def test_long_task_keeps_ui_alive_and_delivers_on_ui_thread(qapp):
    app = qapp
    runner = TaskRunner()
    finished, results = QSignalSpy(runner.finished), QSignalSpy(runner.result)
    ticks, threads = [], []
    class Receiver(QObject):
        @Slot(str, object)
        def progress(self, task_id, value):
            threads.append(QThread.currentThread())
    receiver = Receiver()
    runner.progress.connect(receiver.progress)
    timer = QTimer()
    timer.timeout.connect(lambda: ticks.append(1))
    timer.start(20)
    def slow(progress):
        for count in range(20):
            time.sleep(0.1)
            report(progress, count + 1, 20, "Working")
        return 42
    runner.submit(slow, with_progress=True)
    wait_for(finished)
    timer.stop()
    assert len(ticks) >= 20
    assert threads and all(thread == app.thread() for thread in threads)
    assert results.at(0)[1] == 42
    assert not runner.busy


def test_task_error_preserves_traceback_and_finishes(qapp):
    app = qapp
    runner = TaskRunner()
    errors, finished = QSignalSpy(runner.error), QSignalSpy(runner.finished)
    def failing():
        raise ValueError("Fixture failure")
    runner.submit(failing)
    wait_for(finished)
    error = errors.at(0)[1]
    assert error.message == "Fixture failure"
    assert "ValueError" in error.traceback and "failing" in error.traceback
    assert not runner.busy


def test_cancel_does_not_publish_partial_result(qapp):
    app = qapp
    runner = TaskRunner()
    results, finished = QSignalSpy(runner.result), QSignalSpy(runner.finished)
    def slow(progress):
        time.sleep(0.05)
        report(progress, 1, 1)
        return "partial"
    runner.submit(slow, with_progress=True)
    runner.cancel_all()
    wait_for(finished)
    assert results.count() == 0
