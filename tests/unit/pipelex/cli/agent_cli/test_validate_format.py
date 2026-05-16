"""Unit tests for the agent CLI validate command --format option."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

import pytest

from pipelex.cli.agent_cli.commands.agent_output import CliOutputFormat
from pipelex.cli.agent_cli.commands.validate.pipe_cmd import validate_pipe_cmd
from pipelex.tools.log.log_levels import LogLevel

if TYPE_CHECKING:
    from pytest_mock import MockerFixture

VALIDATE_PIPE_MODULE = "pipelex.cli.agent_cli.commands.validate.pipe_cmd"


class TestValidateFormat:
    """validate pipe --all emits markdown by default and JSON with --format json."""

    def _patch_validate(self, mocker: MockerFixture) -> Any:
        """Patch the validate pipe command's dependencies and return a mock typer context."""
        result: dict[str, Any] = {
            "success": True,
            "validated_pipes": [{"pipe_code": "p1", "status": "SUCCESS"}],
            "total_pipes": 1,
        }
        mocker.patch(f"{VALIDATE_PIPE_MODULE}.make_pipelex_for_agent_cli")
        mocker.patch(f"{VALIDATE_PIPE_MODULE}.Pipelex.teardown_if_needed")
        mocker.patch(f"{VALIDATE_PIPE_MODULE}.validate_all_core", new=mocker.AsyncMock(return_value=result))
        ctx = mocker.MagicMock()
        ctx.obj = {"log_level": LogLevel.WARNING}
        return ctx

    def test_validate_markdown_is_default(self, mocker: MockerFixture, capsys: pytest.CaptureFixture[str]) -> None:
        """Validate pipe --all with no --format produces markdown to stdout."""
        ctx = self._patch_validate(mocker)

        validate_pipe_cmd(ctx=ctx, validate_all=True, output_format=CliOutputFormat.MARKDOWN)

        out = capsys.readouterr().out
        assert out.startswith("# Validation passed")
        assert "`p1` — SUCCESS" in out
        with pytest.raises(json.JSONDecodeError):
            json.loads(out)

    def test_validate_json_with_format_json(self, mocker: MockerFixture, capsys: pytest.CaptureFixture[str]) -> None:
        """Validate pipe --all --format json produces valid JSON to stdout."""
        ctx = self._patch_validate(mocker)

        validate_pipe_cmd(ctx=ctx, validate_all=True, output_format=CliOutputFormat.JSON)

        parsed = json.loads(capsys.readouterr().out)
        assert parsed["success"] is True
        assert parsed["total_pipes"] == 1
