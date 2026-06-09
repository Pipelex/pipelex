"""The ``--temporal`` flag surface on ``pipelex validate`` subcommands.

Locks the public CLI contract that ``bundle`` / ``pipe`` / ``method`` each expose
``--temporal/--no-temporal`` (parity with ``pipelex run``). The flag overrides
``temporal.is_enabled`` for the boot; the validation sweep stays in-process regardless,
so the *behavioural* guarantee (validation does not dispatch to Temporal under a
Temporal-enabled hub) is exercised by the distributed e2e scenario, not here.

Asserts on the resolved Click parameters rather than on rendered ``--help`` text: the
help renderer line-wraps option names at narrow terminal widths (CI's non-tty width
splits ``--temporal`` across lines), which is a presentation detail, not the contract.
Introspecting the command's params is width-independent and short-circuits before any
Pipelex boot, so this stays a true unit test.
"""

from __future__ import annotations

import click
import pytest
from typer.main import get_command

from pipelex.cli.commands.validate.app import validate_app


class TestValidateTemporalFlag:
    @pytest.mark.parametrize("subcommand", ["bundle", "pipe", "method"])
    def test_temporal_flag_exposed(self, subcommand: str) -> None:
        group = get_command(validate_app)
        assert isinstance(group, click.Group)
        command = group.commands[subcommand]
        flag_opts: list[str] = [opt for param in command.params for opt in (*param.opts, *param.secondary_opts)]
        assert "--temporal" in flag_opts
        assert "--no-temporal" in flag_opts
