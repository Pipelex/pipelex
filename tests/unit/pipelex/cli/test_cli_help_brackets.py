r"""Help text keeps its square brackets on every CLI.

Typer renders every help text, option help, docstring, epilog and help panel through Rich markup, and Rich reads a
bracketed lowercase word such as `[run]` or `[str]` as a style tag: one that names no style renders as nothing, so
"Default: [run] execution" printed as "Default:  execution". A bracket meant literally is escaped as `\[`.
"""

from __future__ import annotations

import inspect
import logging
from typing import TYPE_CHECKING

import click
import pytest
import typer
from rich.text import Text
from typer.testing import CliRunner

from pipelex.cli._cli import app as pipelex_app
from pipelex.cli.agent_cli._agent_cli import app as agent_app
from pipelex.cli.dev_cli._dev_cli import app as dev_app

if TYPE_CHECKING:
    from collections.abc import Iterator

    from pytest_mock import MockerFixture

ROOT_CLI_MODULE = "pipelex.cli._cli"
RUN_SETTING_DEFAULT = "Default: [run] execution, else local."


def _rendered_help(*, app: typer.Typer, args: list[str]) -> str:
    """Render `<args> --help` through the real app, as one line of plain text.

    Rich wraps a long help over several rows of the options table, so the box drawing and the line breaks are folded
    away and a sentence reads whole at any terminal width; the colour codes a forced terminal adds are stripped too.
    """
    result = CliRunner().invoke(app, [*args, "--help"], env={"COLUMNS": "200"})
    assert result.exit_code == 0, result.output
    return " ".join(click.unstyle(result.output).replace("│", " ").split())


def _help_texts(*, command: click.Command, path: str) -> Iterator[tuple[str, str]]:
    """Every text Typer renders through Rich markup for a command and its subcommands, with where it comes from."""
    command_texts = {
        "help": command.help,
        "short_help": command.short_help,
        "epilog": command.epilog,
        "rich_help_panel": getattr(command, "rich_help_panel", None),
    }
    for label, text in command_texts.items():
        if text:
            yield f"{path} ({label})", text
    for param in command.params:
        for label in ("help", "rich_help_panel"):
            text = getattr(param, label, None)
            if isinstance(text, str) and text:
                yield f"{path} {param.name} ({label})", text
    if isinstance(command, click.Group):
        for name, subcommand in command.commands.items():
            yield from _help_texts(command=subcommand, path=f"{path} {name}")


class TestCliHelpBrackets:
    @pytest.fixture(autouse=True)
    def _restore_logging_cutoff(self) -> Iterator[None]:
        """Restore the process-global `logging.disable` threshold that the agent CLI's app callback arms."""
        original_disable = logging.root.manager.disable
        yield
        logging.disable(original_disable)

    @pytest.mark.parametrize(
        ("app", "args", "expected_phrases"),
        [
            (pipelex_app, ["--no-logo", "run", "bundle"], [RUN_SETTING_DEFAULT]),
            (pipelex_app, ["--no-logo", "run", "pipe"], [RUN_SETTING_DEFAULT]),
            (pipelex_app, ["--no-logo", "run", "method"], [RUN_SETTING_DEFAULT]),
            (agent_app, ["run", "bundle"], [RUN_SETTING_DEFAULT]),
            (agent_app, ["run", "pipe"], [RUN_SETTING_DEFAULT]),
            (agent_app, ["run", "method"], [RUN_SETTING_DEFAULT]),
            (agent_app, ["init"], ['"backends": list[str],', "written to [run] execution;"]),
        ],
        ids=[
            "pipelex-run-bundle",
            "pipelex-run-pipe",
            "pipelex-run-method",
            "pipelex-agent-run-bundle",
            "pipelex-agent-run-pipe",
            "pipelex-agent-run-method",
            "pipelex-agent-init",
        ],
    )
    def test_rendered_help_keeps_the_bracketed_words(
        self,
        mocker: MockerFixture,
        app: typer.Typer,
        args: list[str],
        expected_phrases: list[str],
    ) -> None:
        mocker.patch(f"{ROOT_CLI_MODULE}.check_readiness")
        rendered = _rendered_help(app=app, args=args)
        for phrase in expected_phrases:
            assert phrase in rendered, f"`{' '.join(args)} --help` lost a bracket: {phrase!r} is not in the rendered help:\n{rendered}"

    def test_rich_markup_renders_every_help_text_verbatim(self) -> None:
        r"""Rich renders every help text of every CLI as written, bar the `\[` escapes: no bracket is taken as a style."""
        offenders: list[str] = []
        for program, app in (("pipelex", pipelex_app), ("pipelex-agent", agent_app), ("pipelex-dev", dev_app)):
            for where, text in _help_texts(command=typer.main.get_command(app), path=program):
                written = inspect.cleandoc(text)
                rendered = Text.from_markup(written).plain
                if rendered != written.replace("\\[", "["):
                    offenders.append(f"{where}: {written!r} renders as {rendered!r}")
        assert not offenders, "Rich markup swallows a bracket in these help texts; escape it as \\[:\n" + "\n".join(offenders)
