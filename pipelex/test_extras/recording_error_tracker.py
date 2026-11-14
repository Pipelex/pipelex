"""An error tracker that keeps what it receives, for tests here and in hosts that report through the seam.

``recording_error_tracker()`` installs one as the process's only tracker for the block, and puts the trackers installed
before it back on the way out, so a test asserts on the reports an error produced without any destination receiving
them.
"""

from collections.abc import Generator
from contextlib import contextmanager

from typing_extensions import override

from pipelex.system.error_tracking.error_report import ErrorReport
from pipelex.system.error_tracking.error_tracker import ErrorTrackerAbstract
from pipelex.system.error_tracking.error_tracking import install_error_trackers, installed_error_trackers


class RecordingErrorTracker(ErrorTrackerAbstract):
    """Keeps every report it receives, in order, and whether it was closed."""

    def __init__(self) -> None:
        self.reports: list[ErrorReport] = []
        self.is_closed = False

    @override
    def report(self, *, report: ErrorReport) -> None:
        self.reports.append(report)

    @override
    def close(self) -> None:
        self.is_closed = True


@contextmanager
def recording_error_tracker() -> Generator[RecordingErrorTracker, None, None]:
    """Install a recording tracker as the only one for the block, then the trackers installed before it again."""
    previous_trackers = installed_error_trackers()
    recorder = RecordingErrorTracker()
    install_error_trackers(trackers=[recorder])
    try:
        yield recorder
    finally:
        install_error_trackers(trackers=previous_trackers)
