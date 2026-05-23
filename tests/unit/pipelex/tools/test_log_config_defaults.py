"""Regression guard for the package-default console targets.

The package-default ``pipelex/pipelex.toml`` is the only config layer that ships in the
PyPI wheel. Its ``[pipelex.log_config]`` values define what every consumer sees before
any user/project override. Logs and rich prints MUST default to stderr so the stdout
channel stays clean for JSON-emitting CLI commands (e.g. ``pipelex-agent models
--format json``) that downstream tooling parses (``mthds-js`` calls
``JSON.parse(stdout)``).

PR #452 introduced the targetable console settings with the stated intent of defaulting
to stderr but accidentally wired the defaults to stdout. This test pins the corrected
default and fails fast if anyone flips the values back.
"""

from pathlib import Path
from typing import Any

import tomli

from pipelex.system.console_target import ConsoleTarget
from pipelex.tools.log.log_config import LogConfig

PIPELEX_PACKAGE_DEFAULT_TOML = Path(__file__).resolve().parents[4] / "pipelex" / "pipelex.toml"


class TestPackageDefaultLogConfig:
    def test_package_default_targets_are_stderr(self) -> None:
        """Loading the package-default ``[pipelex.log_config]`` yields stderr targets.

        Reads ``pipelex/pipelex.toml`` directly (bypassing the layered loader) so the
        assertion is against the shipped defaults, not whatever the dev project or the
        user's ``~/.pipelex/`` override.
        """
        assert PIPELEX_PACKAGE_DEFAULT_TOML.is_file(), f"Package-default toml not found at {PIPELEX_PACKAGE_DEFAULT_TOML}"
        with PIPELEX_PACKAGE_DEFAULT_TOML.open("rb") as toml_file:
            raw_config: dict[str, Any] = tomli.load(toml_file)

        log_config_section = raw_config["pipelex"]["log_config"]
        log_config = LogConfig.model_validate(log_config_section)

        assert log_config.console_log_target == ConsoleTarget.STDERR, (
            f"Package default console_log_target must be stderr to keep logs off the data channel; got {log_config.console_log_target!r}"
        )
        assert log_config.console_print_target == ConsoleTarget.STDERR, (
            f"Package default console_print_target must be stderr to keep prints off the data channel; got {log_config.console_print_target!r}"
        )
