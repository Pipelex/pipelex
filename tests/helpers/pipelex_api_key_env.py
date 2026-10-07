"""Hold `PIPELEX_API_KEY` steady for a test that saves or reads one.

`pipelex login` sets the variable in the process environment directly, as a new process would see it, so a test must
have monkeypatch record the variable before the code under test touches it: `monkeypatch.delenv` on an absent variable
records nothing, and the key a test saved would leak into every later test of the worker.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from pipelex.hosted.client_factory import PIPELEX_API_KEY_ENV_KEY

if TYPE_CHECKING:
    import pytest


def isolate_pipelex_api_key(monkeypatch: pytest.MonkeyPatch, *, value: str | None = None) -> None:
    """Set `PIPELEX_API_KEY` to `value`, or unset it, and restore the developer's own at teardown whatever the test wrote."""
    monkeypatch.setenv(PIPELEX_API_KEY_ENV_KEY, value if value is not None else "recorded-then-unset")
    if value is None:
        monkeypatch.delenv(PIPELEX_API_KEY_ENV_KEY)
