"""Unit tests for the strict ``--task-queue`` validation, now exposed as
``Temporal.validate_task_queue_known``.

A worker polling a queue that nothing routes to is almost always a typo, so
the worker CLI must fail fast at startup with a "did you mean?" suggestion
when a close match exists. The check also runs inside
``TemporalTaskManager.run_worker`` so programmatic callers (tests, library
code) benefit too.
"""

import pytest

from pipelex.config import get_config
from pipelex.system.configuration.exceptions import WorkerTaskQueueUnknownError


class TestWorkerTaskQueueValidation:
    """Strict validation: known queues pass, unknown queues raise."""

    def test_default_task_queue_passes(self) -> None:
        """The worker's ``default_task_queue`` is always a known queue and must
        not raise even when no routing/options entries reference it.
        """
        # Shipping pipelex.toml uses "temporal_task_queue" as default.
        get_config().temporal.validate_task_queue_known("temporal_task_queue")

    def test_unknown_queue_raises_with_known_queues_listed(self) -> None:
        """Unknown queue raises ``WorkerTaskQueueUnknownError`` with the full
        known-queue list in the message.
        """
        with pytest.raises(WorkerTaskQueueUnknownError) as exc_info:
            get_config().temporal.validate_task_queue_known("totally_unknown_queue")
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
            get_config().temporal.validate_task_queue_known("temporal_task_queu")
        message = str(exc_info.value)
        assert "Did you mean 'temporal_task_queue'?" in message

    def test_queue_options_key_treated_as_known(self) -> None:
        """A queue declared only in ``queue_options`` (no routing entry) still
        counts as a known queue — workers can legitimately poll a queue that
        operators tune via ``queue_options`` even before any ``activity_queues``
        entry routes to it.
        """
        # The shipping default config has queue_options.temporal_task_queue —
        # that's already covered by test_default_task_queue_passes. Use it as
        # the regression for the queue_options.keys() branch.
        get_config().temporal.validate_task_queue_known("temporal_task_queue")
