"""The pretty-print mode is configuration: shipped as `rich`, applied at boot, and read through the enum."""

from __future__ import annotations

from pathlib import Path

import pytest
import tomli

from pipelex.config import get_config
from pipelex.tools.misc.pretty import PrettyPrinter, PrettyPrintMode

PIPELEX_REPO_ROOT = Path(__file__).resolve().parents[5]
PACKAGE_DEFAULT_TOML = PIPELEX_REPO_ROOT / "pipelex" / "pipelex.toml"


class TestPrettyPrintModeConfig:
    def test_shipped_default_is_rich(self) -> None:
        """The packaged defaults carry the key, so an older user file inherits it without a migration."""
        with PACKAGE_DEFAULT_TOML.open("rb") as toml_file:
            shipped = tomli.load(toml_file)
        assert shipped["runtime"]["log"]["pretty_print_mode"] == PrettyPrintMode.RICH

    def test_boot_applies_the_configured_mode(self) -> None:
        """`Pipelex.make()` (run by the module fixture) sets the printer's mode from `[runtime.log]`."""
        assert PrettyPrinter.mode is get_config().runtime.log.pretty_print_mode

    @pytest.mark.parametrize(
        ("mode", "expected_is_silent"),
        [
            (PrettyPrintMode.RICH, False),
            (PrettyPrintMode.POOR, False),
            (PrettyPrintMode.SILENT, True),
        ],
    )
    def test_is_silent(self, mode: PrettyPrintMode, expected_is_silent: bool) -> None:
        assert mode.is_silent is expected_is_silent
