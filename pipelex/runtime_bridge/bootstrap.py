"""Idempotent Pipelex boot helpers for use inside any host runtime that embeds Pipelex.

Pipelex's own ``Pipelex.make()`` raises if a singleton already exists. The
bridge boundary is a hot path that can be reached from many concurrent
activities (Mistral Workflows, raw Temporal, future plugins), so we wrap the
boot in an idempotent guard so callers don't have to think about it.
"""

from typing import Any

from pipelex.pipelex import Pipelex


def ensure_pipelex_booted(
    config_overrides: dict[str, Any] | None = None,
) -> None:
    """Boot Pipelex on first call; no-op if already initialized.

    Idempotent. Safe to call from inside an activity; safe to call from a
    worker entry-point before activities start. If a Pipelex singleton was
    already created externally (e.g. via the user's worker bootstrap), this
    function adopts that singleton without re-initializing.
    """
    if Pipelex.get_optional_instance() is None:
        Pipelex.make(config_overrides=config_overrides)
