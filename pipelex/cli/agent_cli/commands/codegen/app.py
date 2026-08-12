"""Agent CLI codegen subcommand group.

The agent-CLI mirror of the bare `pipelex codegen` family (see the codegen spec →
"CLI: codegen"): the same engine, presented through the agent CLI's two-stream envelopes
(`--format` / `--error-format`, markdown default). `inputs` has no mirror here — the existing
`pipelex-agent inputs` group already surfaces that projection.
"""

from __future__ import annotations

import typer

from pipelex.cli.agent_cli.commands.codegen.check_cmd import agent_codegen_check_cmd
from pipelex.cli.agent_cli.commands.codegen.types_cmd import agent_codegen_types_cmd

codegen_app = typer.Typer(
    add_completion=False,
    no_args_is_help=True,
)

codegen_app.command(name="types", help="Project the crate's concept set into typed artifacts for a target flavor")(agent_codegen_types_cmd)
codegen_app.command(name="check", help="Verify generated artifacts are current — offline, no engine, no API key")(agent_codegen_check_cmd)
