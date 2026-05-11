"""Unit tests for the strict ``--task-queue`` validation in
``pipelex.temporal.worker_cli._validate_task_queue_known``.

A worker polling a queue that nothing routes to is almost always a typo, so
the worker CLI must fail fast at startup with a "did you mean?" suggestion
when a close match exists.
"""

import pytest

from pipelex.temporal.exceptions import WorkerTaskQueueUnknownError
from pipelex.temporal.worker_cli import _validate_task_queue_known  # noqa: PLC2701  # pyright: ignore[reportPrivateUsage]


class TestWorkerTaskQueueValidation:
    """Strict CLI startup validation: known queues pass, unknown queues raise."""

    def test_default_task_queue_passes(self) -> None:
        """The worker's ``default_task_queue`` is always a known queue and must
        not raise even when no routing/options entries reference it.
        """
        # Shipping pipelex.toml uses "temporal_task_queue" as default.
        _validate_task_queue_known("temporal_task_queue")

    def test_unknown_queue_raises_with_known_queues_listed(self) -> None:
        """Unknown queue raises ``WorkerTaskQueueUnknownError`` with the full
        known-queue list in the message.
        """
        with pytest.raises(WorkerTaskQueueUnknownError) as exc_info:
            _validate_task_queue_known("totally_unknown_queue")
        message = str(exc_info.value)
        assert "totally_unknown_queue" in message
        assert "Known queues" in message
        assert "temporal_task_queue" in message

    def test_typo_close_to_known_queue_suggests_correction(self) -> None:
        """A typo within Levenshtein-2 of a known queue includes a "Did you
        mean?" suggestion in the error message.
        """
        # "temporal_task_queu" is one char away from "temporal_task_queue".
        with pytest.raises(WorkerTaskQueueUnknownError) as exc_info:
            _validate_task_queue_known("temporal_task_queu")
        message = str(exc_info.value)
        assert "Did you mean 'temporal_task_queue'?" in message
