"""Hold `PIPELEX_API_KEY` and `PIPELEX_BASE_URL` steady for a test that saves or reads them.

`pipelex login` sets both variables in the process environment directly, as a new process would see them, so a test
must have monkeypatch record a variable before the code under test touches it: `monkeypatch.delenv` on an absent
variable records nothing, and the value a test saved would leak into every later test of the worker.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from pipelex.hosted.client_factory import PIPELEX_API_KEY_ENV_KEY, PIPELEX_BASE_URL_ENV_KEY

if TYPE_CHECKING:
    import pytest


def isolate_env_var(monkeypatch: pytest.MonkeyPatch, *, key: str, value: str | None = None) -> None:
    """Set `key` to `value`, or unset it, and restore the developer's own at teardown whatever the test wrote."""
    monkeypatch.setenv(key, value if value is not None else "recorded-then-unset")
    if value is None:
        monkeypatch.delenv(key)


def isolate_pipelex_api_key(monkeypatch: pytest.MonkeyPatch, *, value: str | None = None) -> None:
    """Set `PIPELEX_API_KEY` to `value`, or unset it, and restore the developer's own at teardown whatever the test wrote."""
    isolate_env_var(monkeypatch, key=PIPELEX_API_KEY_ENV_KEY, value=value)


def isolate_pipelex_base_url(monkeypatch: pytest.MonkeyPatch, *, value: str | None = None) -> None:
    """Set `PIPELEX_BASE_URL` to `value`, or unset it, and restore the developer's own at teardown whatever the test wrote."""
    isolate_env_var(monkeypatch, key=PIPELEX_BASE_URL_ENV_KEY, value=value)
