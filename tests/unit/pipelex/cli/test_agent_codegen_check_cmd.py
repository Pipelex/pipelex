"""The `pipelex-agent codegen check` command: envelopes and the 0/1/2 verdict exit codes.

The offline check core is mocked out (covered by its own unit tests) so these tests pin the
agent-CLI wiring: an up-to-date verdict is a success envelope, drift is a structured
`CodegenDriftError` on stderr with exit 1, and a missing/unreadable lock is a no-verdict exit 2.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import pytest
import typer

from pipelex.cli.agent_cli.commands.agent_output import CliOutputFormat
from pipelex.cli.agent_cli.commands.codegen.check_cmd import agent_codegen_check_cmd
from pipelex.codegen.check import CodegenCheckReport, CodegenDrift, DriftCategory
from pipelex.codegen.exceptions import CodegenLockError

if TYPE_CHECKING:
    from pathlib import Path

    from pytest_mock import MockerFixture

CMD_MODULE = "pipelex.cli.agent_cli.commands.codegen.check_cmd"


class TestAgentCodegenCheckCmd:
    """The agent-CLI offline drift check, with the pure-hashing core mocked out."""

    def test_current_is_json_success_envelope(self, mocker: MockerFixture, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        mocker.patch(f"{CMD_MODULE}.run_codegen_check", return_value=CodegenCheckReport(lock_found=True))

        agent_codegen_check_cmd(root=str(tmp_path), output_format=CliOutputFormat.JSON, error_format=None)

        envelope = json.loads(capsys.readouterr().out)
        assert envelope["success"] is True
        assert envelope["is_current"] is True
        assert envelope["root"] == str(tmp_path)

    def test_current_markdown_is_the_default(self, mocker: MockerFixture, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        mocker.patch(f"{CMD_MODULE}.run_codegen_check", return_value=CodegenCheckReport(lock_found=True))

        agent_codegen_check_cmd(root=str(tmp_path), output_format=CliOutputFormat.MARKDOWN, error_format=None)

        stdout = capsys.readouterr().out
        assert stdout.startswith("# Generated artifacts up to date")

    def test_drift_is_structured_negative_verdict_exit_1(self, mocker: MockerFixture, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        """Drift is a produced negative verdict: exit 1 with the drifting artifacts enumerated in the envelope."""
        report = CodegenCheckReport(
            lock_found=True,
            drifts=[CodegenDrift(path="models.py", category=DriftCategory.HAND_EDITED, detail="Body was edited below the stamp.")],
        )
        mocker.patch(f"{CMD_MODULE}.run_codegen_check", return_value=report)

        with pytest.raises(typer.Exit) as exc_info:
            agent_codegen_check_cmd(root=str(tmp_path), output_format=CliOutputFormat.JSON, error_format=None)

        assert exc_info.value.exit_code == 1
        error = json.loads(capsys.readouterr().err)
        assert error["error_type"] == "CodegenDriftError"
        assert error["is_current"] is False
        assert error["drifts"] == [{"path": "models.py", "category": "hand-edited", "detail": "Body was edited below the stamp."}]

    def test_no_lock_is_no_verdict_exit_2(self, mocker: MockerFixture, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        mocker.patch(f"{CMD_MODULE}.run_codegen_check", return_value=CodegenCheckReport(lock_found=False))

        with pytest.raises(typer.Exit) as exc_info:
            agent_codegen_check_cmd(root=str(tmp_path), output_format=CliOutputFormat.JSON, error_format=None)

        assert exc_info.value.exit_code == 2
        error = json.loads(capsys.readouterr().err)
        assert error["error_type"] == "CodegenLockNotFoundError"

    def test_unreadable_lock_is_no_verdict_exit_2(self, mocker: MockerFixture, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        mocker.patch(f"{CMD_MODULE}.run_codegen_check", side_effect=CodegenLockError("codegen.lock is not valid TOML"))

        with pytest.raises(typer.Exit) as exc_info:
            agent_codegen_check_cmd(root=str(tmp_path), output_format=CliOutputFormat.JSON, error_format=None)

        assert exc_info.value.exit_code == 2
        error = json.loads(capsys.readouterr().err)
        assert error["error_type"] == "CodegenLockError"
        assert "not valid TOML" in error["message"]
        assert "remove it, then regenerate" in error["hint"]
