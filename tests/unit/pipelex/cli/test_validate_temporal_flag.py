"""The ``--temporal`` flag surface on ``pipelex validate`` subcommands.

Locks the public CLI contract that ``bundle`` / ``pipe`` / ``method`` each expose
``--temporal/--no-temporal`` (parity with ``pipelex run``). The flag overrides
``temporal.is_enabled`` for the boot; the validation sweep stays in-process regardless,
so the *behavioural* guarantee (validation does not dispatch to Temporal under a
Temporal-enabled hub) is exercised by the distributed e2e scenario, not here. ``--help``
short-circuits before any Pipelex boot, so this stays a true unit test.
"""

from __future__ import annotations

import pytest
from typer.testing import CliRunner

from pipelex.cli.commands.validate.app import validate_app


class TestValidateTemporalFlag:
    @pytest.mark.parametrize("subcommand", ["bundle", "pipe", "method"])
    def test_temporal_flag_exposed(self, subcommand: str) -> None:
        result = CliRunner().invoke(validate_app, [subcommand, "--help"])
        assert result.exit_code == 0
        assert "--temporal" in result.output
        assert "--no-temporal" in result.output
