"""Regression guard for the shipped console targets.

Two TOML files ship in the PyPI wheel and define every consumer's defaults
before any user/project override:

- ``pipelex/pipelex.toml`` — the package-default that ``Pipelex.make()`` loads first.
- ``pipelex/kit/configs/pipelex.toml`` — the template ``pipelex init`` copies to
  ``~/.pipelex/``.

The contract these defaults must satisfy:

- ``console_log_target`` defaults to stderr — logs are diagnostics and must stay
  off the data channel so JSON-emitting CLI commands (e.g.
  ``pipelex-agent models --format json``) stay parseable by downstream tooling
  (``mthds-js`` calls ``JSON.parse(stdout)``).
- ``console_print_target`` defaults to stdout — the main ``pipelex`` CLI emits
  human-facing tables (``show backends``, ``show models``, ``which``, ``doctor``)
  via that channel and ``pipelex show backends > out.txt`` must keep working.

PR #452 introduced the targetable console settings with the stated intent of
stderr for logs; the print target then got over-corrected to stderr in commit
ac858de8, which broke the redirect-to-file flow. This test pins both knobs in
both shipped TOMLs and fails fast if either is flipped in either direction.
"""

from pathlib import Path
from typing import Any

import pytest
import tomli

from pipelex.system.console_target import ConsoleTarget

PIPELEX_REPO_ROOT = Path(__file__).resolve().parents[4]
PACKAGE_DEFAULT_TOML = PIPELEX_REPO_ROOT / "pipelex" / "pipelex.toml"
KIT_TEMPLATE_TOML = PIPELEX_REPO_ROOT / "pipelex" / "kit" / "configs" / "pipelex.toml"


class TestShippedConsoleTargets:
    @pytest.mark.parametrize(
        ("label", "toml_path"),
        [
            ("package-default", PACKAGE_DEFAULT_TOML),
            ("kit-template", KIT_TEMPLATE_TOML),
        ],
    )
    def test_shipped_targets_are_log_stderr_and_print_stdout(
        self,
        label: str,
        toml_path: Path,
    ) -> None:
        """Both shipped TOMLs route logs to stderr and prints to stdout.

        Reads each file directly (bypassing the layered loader) so the assertion
        is against the shipped values, not the merged config produced by the
        dev project or the user's ``~/.pipelex/`` override. The kit template
        intentionally carries only the user-facing subset of ``LogConfig``
        fields, so we assert against the raw TOML values rather than
        reconstructing the full model.
        """
        assert toml_path.is_file(), f"[{label}] toml not found at {toml_path}"
        with toml_path.open("rb") as toml_file:
            raw_config: dict[str, Any] = tomli.load(toml_file)

        log_config_section = raw_config["pipelex"]["log_config"]
        log_target_raw = log_config_section.get("console_log_target")
        print_target_raw = log_config_section.get("console_print_target")

        assert log_target_raw == ConsoleTarget.STDERR, (
            f"[{label}] console_log_target must be stderr — logs are diagnostics and must stay off the data channel; got {log_target_raw!r}"
        )
        assert print_target_raw == ConsoleTarget.STDOUT, (
            f"[{label}] console_print_target must be stdout — the main pipelex CLI emits human-facing tables "
            f"(show backends/models, which, doctor) via that channel and must remain redirectable to a file; "
            f"got {print_target_raw!r}"
        )
