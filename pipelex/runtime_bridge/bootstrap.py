"""Idempotent Pipelex boot helpers for use inside any host runtime that embeds Pipelex.

Pipelex's own ``Pipelex.make()`` raises if a singleton already exists. The
bridge boundary is a hot path that can be reached from many concurrent
activities (Mistral Workflows, raw Temporal, future plugins), so we wrap the
boot in an idempotent guard so callers don't have to think about it.
"""

import threading
from typing import Any

from pipelex.pipelex import Pipelex

# Serializes the check-then-make below. Without it, two concurrent first-calls in
# a fresh worker can both pass the readiness check and both call ``Pipelex.make``;
# the loser then hits ``PipelexSetupError("Pipelex is already initialized")``.
# ``MetaSingleton`` has no lock of its own. The race is across THREADS only — the
# function is a sync ``def`` with no ``await`` between the check and the make, so
# asyncio tasks on a single loop cannot interleave there; it bites Temporal's
# sync-activity thread pool / multi-thread workers.
_boot_lock = threading.Lock()


def ensure_pipelex_booted(
    *,
    config_overrides: dict[str, Any] | None = None,
) -> None:
    """Boot Pipelex on first call; no-op if already initialized.

    Idempotent and thread-safe across its own callers: ``_boot_lock`` serializes
    concurrent first-calls so ``Pipelex.make`` runs exactly once and late callers
    re-check ``is_fully_booted()`` and adopt the result without touching a
    half-built instance. If the host already booted Pipelex (e.g. at worker
    startup) and that singleton is fully booted, this adopts it without
    re-initializing — the intended pattern is to boot Pipelex before serving
    bridge traffic.

    Not supported: racing a *separate* external ``Pipelex.make()`` that is
    mid-initialization on another thread. That external boot does not take
    ``_boot_lock``, so within its setup window ``is_fully_booted()`` is False and
    this helper would attempt its own ``make`` and hit
    ``PipelexSetupError("Pipelex is already initialized")``. Standard hosts boot
    before bringing up concurrent bridge callers, so this is not reached; the
    residual race and a bounded-wait fix are written up in
    ``wip/runtime-bridge/bridge-bootstrap-external-race.md``.
    """
    if Pipelex.is_fully_booted():
        return
    with _boot_lock:
        # Re-check inside the lock: another thread may have finished booting while we waited.
        if not Pipelex.is_fully_booted():
            Pipelex.make(config_overrides=config_overrides)
