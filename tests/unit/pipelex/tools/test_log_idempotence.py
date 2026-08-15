"""Unit tests for Log.configure_if_unset (doctor's idempotent bootstrap).

Pins the once-per-process guard that lets the doctor's setup_doctor_runtime coexist
with library embedders or interleaved tests that may already have called
``log.configure`` earlier in the same process — instead of raising the once-per-process
RuntimeError, ``configure_if_unset`` returns False and no-ops.

Each test uses the ``fresh_log`` fixture so the RichHandler installed by ``configure``
is removed from the global root logger on teardown; otherwise handlers accumulate
across the suite and pollute later test output.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from pipelex.tools.log.log import Log
from pipelex.tools.log.log_config import LogConfig
from pipelex.tools.misc.toml_utils import load_toml_from_path

if TYPE_CHECKING:
    from collections.abc import Iterator


@pytest.fixture
def log_config() -> LogConfig:
    """Build a real LogConfig from the package defaults — no hand-rolled stub."""
    from pipelex.system.configuration.config_loader import ConfigLoader  # noqa: PLC0415

    loader = ConfigLoader()
    config_dict = load_toml_from_path(loader.pipelex_root_dir / "pipelex.toml")
    return LogConfig.model_validate(config_dict["runtime"]["log"])


@pytest.fixture
def fresh_log() -> Iterator[Log]:
    """Yield a fresh Log() instance and reset it on teardown.

    ``Log.configure`` attaches a RichHandler to the global root logger
    (``logging.getLogger()``) and StreamHandlers to every named poor_logger. Without
    explicit cleanup these handlers leak across tests in the same process — later tests
    inherit duplicated handlers and stray output. ``reset()`` removes them.
    """
    log_instance = Log()
    try:
        yield log_instance
    finally:
        log_instance.reset()


class TestLogConfigureIfUnset:
    def test_returns_true_and_applies_on_fresh_instance(self, fresh_log: Log, log_config: LogConfig) -> None:
        """A fresh Log() instance has no config; configure_if_unset must apply it."""
        applied = fresh_log.configure_if_unset(log_config=log_config)

        assert applied is True
        # rich_handler is only built inside configure(); seeing it set proves we
        # didn't take the no-op branch.
        assert fresh_log.rich_handler is not None

    def test_returns_false_after_prior_configure_without_raising(self, fresh_log: Log, log_config: LogConfig) -> None:
        """A second call must no-op and return False instead of raising RuntimeError.

        Pins the contract that lets doctor coexist with library embedders / interleaved
        tests that already called log.configure earlier in the process.
        """
        fresh_log.configure(log_config=log_config)

        applied = fresh_log.configure_if_unset(log_config=log_config)

        assert applied is False

    def test_returns_true_again_after_reset(self, fresh_log: Log, log_config: LogConfig) -> None:
        """log.reset() must restore the unset state so configure_if_unset can re-apply."""
        fresh_log.configure(log_config=log_config)
        fresh_log.reset()

        applied = fresh_log.configure_if_unset(log_config=log_config)

        assert applied is True
