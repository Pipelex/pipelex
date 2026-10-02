"""Unit tests for Log.configure_if_unset (doctor's idempotent bootstrap).

Pins the once-per-process guard that lets the doctor's setup_doctor_runtime coexist
with library embedders or interleaved tests that may already have called
``log.configure`` earlier in the same process — instead of raising the once-per-process
RuntimeError, ``configure_if_unset`` returns False and no-ops.

Each test uses the ``fresh_log`` fixture so the handler ``configure`` installs on the
global root logger is removed on teardown; otherwise handlers accumulate across the
suite and pollute later test output.
"""

from __future__ import annotations

import logging
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
    from pipelex.system.configuration.config_loader import ConfigLoader  # ruff: ignore[import-outside-top-level]

    loader = ConfigLoader()
    config_dict = load_toml_from_path(loader.pipelex_root_dir / "pipelex.toml")
    return LogConfig.model_validate(config_dict["runtime"]["log"])


@pytest.fixture
def fresh_log() -> Iterator[Log]:
    """Yield a fresh Log() instance and reset it on teardown.

    ``Log.configure`` attaches a holding handler to the global root logger
    (``logging.getLogger()``), which a sink's handler later replaces. Without explicit
    cleanup these handlers leak across tests in the same process — later tests inherit
    duplicated handlers and stray output. ``reset()`` removes them.
    """
    log_instance = Log()
    try:
        yield log_instance
    finally:
        log_instance.reset()


class TestLogConfigureIfUnset:
    def test_returns_true_and_applies_on_fresh_instance(self, fresh_log: Log, log_config: LogConfig) -> None:
        """A fresh Log() instance has no config; configure_if_unset must apply it."""
        root_handlers_before = list(logging.getLogger().handlers)

        applied = fresh_log.configure_if_unset(log_config=log_config)

        assert applied is True
        # The holding handler is only installed inside configure(); seeing one more root handler
        # proves we didn't take the no-op branch.
        assert len(logging.getLogger().handlers) == len(root_handlers_before) + 1

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

    def test_reset_leaves_every_other_root_handler_in_place(self, fresh_log: Log, log_config: LogConfig) -> None:
        """Teardown removes what configure installed and nothing else: a host's handler survives a Pipelex reset."""
        root_logger = logging.getLogger()
        foreign = logging.NullHandler()
        root_logger.addHandler(foreign)
        try:
            fresh_log.configure(log_config=log_config)
            fresh_log.reset()

            assert foreign in root_logger.handlers
        finally:
            root_logger.removeHandler(foreign)
