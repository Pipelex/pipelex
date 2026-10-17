"""Unit tests: agent CLI method commands report method-reference failures through the structured error envelope."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any, cast

import pytest
import typer
from mthds.package.exceptions import VCSFetchError

from pipelex.cli.agent_cli.commands.agent_output import CliOutputFormat, set_agent_cli_error_format
from pipelex.cli.agent_cli.commands.inputs.method_cmd import inputs_method_cmd
from pipelex.cli.agent_cli.commands.run.method_cmd import run_method_cmd
from pipelex.cli.agent_cli.commands.validate.method_cmd import validate_method_cmd

if TYPE_CHECKING:
    from pathlib import Path

    from pytest_mock import MockerFixture

BROKEN_REF = "github.com/test/broken-repo"


def _parse_single_json_error(stderr_text: str) -> dict[str, Any]:
    """Parse the one JSON error object printed on stderr."""
    start = stderr_text.index("{")
    parsed, _ = json.JSONDecoder().raw_decode(stderr_text, start)
    assert isinstance(parsed, dict)
    return cast("dict[str, Any]", parsed)


class TestAgentMethodRefErrors:
    """A fetch failure surfaces as its problem, never unstructured Typer text."""

    def _mock_failing_clone(self, mocker: MockerFixture, tmp_path: Path) -> None:
        mocker.patch("pipelex.methods.fetching.clone_default_branch", side_effect=VCSFetchError("connection refused"))
        mocker.patch("pipelex.cli.method_resolver.tempfile.mkdtemp", return_value=str(tmp_path / "dest"))

    def test_run_method_fetch_failure_reports_its_problem(self, mocker: MockerFixture, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        """`run method <ref>` with a failing fetch exits 1 with the fetch failure's problem as JSON on stderr."""
        self._mock_failing_clone(mocker, tmp_path)

        with pytest.raises(typer.Exit) as exc_info:
            run_method_cmd(name=BROKEN_REF, error_format=CliOutputFormat.JSON)

        assert exc_info.value.exit_code == 1
        error_obj = _parse_single_json_error(capsys.readouterr().err)
        assert error_obj["code"] == "method.fetch_failed"
        assert error_obj["diagnostics"]["error_class"] == "MethodFetchError"
        assert "connection refused" in error_obj["message"]

    def test_validate_method_fetch_failure_reports_its_problem(
        self, mocker: MockerFixture, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """`validate method <ref>` with a failing fetch is a no-verdict condition: exit 2, its problem."""
        self._mock_failing_clone(mocker, tmp_path)

        with pytest.raises(typer.Exit) as exc_info:
            validate_method_cmd(name=BROKEN_REF, output_format=CliOutputFormat.JSON)

        assert exc_info.value.exit_code == 2
        error_obj = _parse_single_json_error(capsys.readouterr().err)
        assert error_obj["code"] == "method.fetch_failed"
        assert error_obj["diagnostics"]["error_class"] == "MethodFetchError"
        assert "connection refused" in error_obj["message"]

    def test_inputs_method_fetch_failure_reports_its_problem(self, mocker: MockerFixture, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        """`inputs method <ref>` with a failing fetch exits 1 with its problem (JSON is its error default)."""
        set_agent_cli_error_format(CliOutputFormat.JSON)
        self._mock_failing_clone(mocker, tmp_path)

        with pytest.raises(typer.Exit) as exc_info:
            inputs_method_cmd(name=BROKEN_REF)

        assert exc_info.value.exit_code == 1
        error_obj = _parse_single_json_error(capsys.readouterr().err)
        assert error_obj["code"] == "method.fetch_failed"
        assert error_obj["diagnostics"]["error_class"] == "MethodFetchError"
        assert "connection refused" in error_obj["message"]
