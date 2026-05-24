"""Unit tests for Log.configure_if_unset (doctor's idempotent bootstrap).

Pins the doctor's once-per-process guard: setup_doctor_runtime relies on the bool
return value to decide whether the caller (an embedder, an interleaved test) had
already configured logging — and to respect their package log level when so.
"""

from __future__ import annotations

import pytest

from pipelex.tools.log.log import Log
from pipelex.tools.log.log_config import LogConfig
from pipelex.tools.misc.toml_utils import load_toml_from_path


@pytest.fixture
def log_config() -> LogConfig:
    """Build a real LogConfig from the package defaults — no hand-rolled stub."""
    from pipelex.system.configuration.config_loader import ConfigLoader  # noqa: PLC0415

    loader = ConfigLoader()
    config_dict = load_toml_from_path(loader.pipelex_root_dir / "pipelex.toml")
    return LogConfig.model_validate(config_dict["pipelex"]["log_config"])


class TestLogConfigureIfUnset:
    def test_returns_true_and_applies_on_fresh_instance(self, log_config: LogConfig) -> None:
        """A fresh Log() instance has no config; configure_if_unset must apply it."""
        fresh_log = Log()

        applied = fresh_log.configure_if_unset(log_config=log_config)

        assert applied is True
        # rich_handler is only built inside configure(); seeing it set proves we
        # didn't take the no-op branch.
        assert fresh_log.rich_handler is not None

    def test_returns_false_after_prior_configure_without_raising(self, log_config: LogConfig) -> None:
        """A second call must no-op and return False instead of raising RuntimeError.

        Pins the contract that lets doctor coexist with library embedders / interleaved
        tests that already called log.configure earlier in the process.
        """
        fresh_log = Log()
        fresh_log.configure(log_config=log_config)

        applied = fresh_log.configure_if_unset(log_config=log_config)

        assert applied is False

    def test_returns_true_again_after_reset(self, log_config: LogConfig) -> None:
        """log.reset() must restore the unset state so configure_if_unset can re-apply."""
        fresh_log = Log()
        fresh_log.configure(log_config=log_config)
        fresh_log.reset()

        applied = fresh_log.configure_if_unset(log_config=log_config)

        assert applied is True
