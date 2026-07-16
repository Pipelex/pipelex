"""The delivery axis: *whether the caller waits* for a pipe to complete.

``DeliveryMode`` is a **closed** core ``StrEnum`` and is **endpoint-intrinsic** — set by
the endpoint, never received from a caller and never carried in config. ``/execute`` and
``/validate`` are synchronous (``BLOCKING``); ``/start`` is fire-and-forget
(``FIRE_AND_FORGET``). Delivery is passed as a parameter to ``OrchestratorProtocol.run``;
each orchestrator honors it per its nature (an in-process orchestrator always blocks; a
Temporal orchestrator awaits completion vs returns a workflow id).

This axis is genuinely closed, so the StrEnum-everywhere standard applies in full:
exhaustive ``match``/``case`` with no default arm. A future ``STREAMING`` delivery would
be core's call to add here, never a plugin's — which is exactly why it stays an enum,
unlike the open :mod:`pipelex.runtime_bridge.orchestration_mode` token.
"""

from enum import StrEnum


class DeliveryMode(StrEnum):
    """Whether a pipe run blocks until completion or returns immediately.

    BLOCKING: the call awaits the pipe to completion and returns the full output.
        Set by the synchronous endpoints (``/execute``, ``/validate``).
    FIRE_AND_FORGET: the call returns immediately (with a workflow id when the
        orchestrator is async-capable); completion is signalled out-of-band via the
        DeliveryAssignment (webhook / storage). Set by ``/start``. Only an
        async-capable orchestrator (``supports_fire_and_forget``) can honor it
        genuinely; the endpoint checks capability before dispatching.
    """

    BLOCKING = "blocking"
    FIRE_AND_FORGET = "fire_and_forget"
