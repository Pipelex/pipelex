"""Unit tests for agent CLI `inputs pipe --format toml` (raw TOML template on stdout)."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

import tomli

from pipelex.cli.agent_cli.commands.inputs._inputs_core import emit_inputs_result
from pipelex.cli.agent_cli.commands.inputs.pipe_cmd import inputs_pipe_cmd
from pipelex.core.pipes.inputs.exceptions import NoInputsRequiredError
from pipelex.pipe_machinery.rendering.input_renderer import InputsTemplateFormat

if TYPE_CHECKING:
    import pytest
    from pytest_mock import MockerFixture

PIPE_CMD_MODULE = "pipelex.cli.agent_cli.commands.inputs.pipe_cmd"

INPUTS_TEMPLATE: dict[str, Any] = {
    "topic": {
        "concept": "demo.Topic",
        "content": {"text": "line one\nline two"},
    },
}


class TestAgentInputsTemplateFormatToml:
    def _patch_inputs(self, mocker: MockerFixture, *, result: dict[str, Any] | None = None, error: Exception | None = None) -> None:
        """Patch the pipe command's dependencies; inputs_core returns result or raises error."""
        mocker.patch(f"{PIPE_CMD_MODULE}.make_pipelex_for_agent_cli")
        mocker.patch(f"{PIPE_CMD_MODULE}.Pipelex.teardown_if_needed")
        mocker.patch(f"{PIPE_CMD_MODULE}.resolve_pipe_from_exports", return_value=[])
        if error is not None:
            mocker.patch(f"{PIPE_CMD_MODULE}.inputs_core", new=mocker.AsyncMock(side_effect=error))
        else:
            mocker.patch(f"{PIPE_CMD_MODULE}.inputs_core", new=mocker.AsyncMock(return_value=result))

    def test_toml_format_prints_raw_toml(self, mocker: MockerFixture, capsys: pytest.CaptureFixture[str]) -> None:
        """--format toml prints the raw TOML template, not the JSON envelope."""
        self._patch_inputs(mocker, result={"success": True, "pipe_code": "demo.my_pipe", "inputs": INPUTS_TEMPLATE})

        inputs_pipe_cmd("my_pipe", template_format=InputsTemplateFormat.TOML)

        captured = capsys.readouterr()
        assert not captured.out.lstrip().startswith("{")
        assert tomli.loads(captured.out) == INPUTS_TEMPLATE

    def test_json_default_keeps_envelope(self, mocker: MockerFixture, capsys: pytest.CaptureFixture[str]) -> None:
        """The default format keeps the structured JSON success envelope."""
        self._patch_inputs(mocker, result={"success": True, "pipe_code": "demo.my_pipe", "inputs": INPUTS_TEMPLATE})

        inputs_pipe_cmd("my_pipe")

        envelope = json.loads(capsys.readouterr().out)
        assert envelope["success"] is True
        assert envelope["inputs"] == INPUTS_TEMPLATE

    def test_no_inputs_in_toml_mode_prints_comment(self, mocker: MockerFixture, capsys: pytest.CaptureFixture[str]) -> None:
        """A pipe without inputs yields a TOML comment line — valid TOML that loads as an empty dict."""
        self._patch_inputs(mocker, error=NoInputsRequiredError("No inputs required for pipe 'demo.my_pipe'."))

        inputs_pipe_cmd("my_pipe", template_format=InputsTemplateFormat.TOML)

        captured = capsys.readouterr()
        assert captured.out.startswith("# No inputs required")
        assert tomli.loads(captured.out) == {}

    def test_no_inputs_in_json_mode_keeps_envelope(self, mocker: MockerFixture, capsys: pytest.CaptureFixture[str]) -> None:
        """A pipe without inputs keeps the structured envelope in JSON mode."""
        self._patch_inputs(mocker, error=NoInputsRequiredError("No inputs required for pipe 'demo.my_pipe'."))

        inputs_pipe_cmd("my_pipe")

        envelope = json.loads(capsys.readouterr().out)
        assert envelope["success"] is True
        assert envelope["inputs"] == {}
        assert "No inputs required" in envelope["message"]

    def test_light_toml_carries_concept_comments(self, capsys: pytest.CaptureFixture[str]) -> None:
        """The agent-CLI TOML surface carries the same `# concept:` hints the human build inputs does."""
        result: dict[str, Any] = {
            "success": True,
            "pipe_code": "demo.my_pipe",
            "inputs": {"question": "text_value", "invoice": {"invoice_number": "INV-1"}},
            "concept_comments": {"question": "concept: demo.Question", "invoice": "concept: demo.Invoice"},
        }

        emit_inputs_result(result, template_format=InputsTemplateFormat.TOML)

        out = capsys.readouterr().out
        assert "# concept: demo.Question" in out
        assert "# concept: demo.Invoice" in out
        assert tomli.loads(out) == {"question": "text_value", "invoice": {"invoice_number": "INV-1"}}

    def test_json_mode_strips_internal_concept_comments(self, capsys: pytest.CaptureFixture[str]) -> None:
        """concept_comments is internal plumbing — it must not leak into the JSON envelope."""
        result: dict[str, Any] = {
            "success": True,
            "pipe_code": "demo.my_pipe",
            "inputs": {"question": "text_value"},
            "concept_comments": {"question": "concept: demo.Question"},
        }

        emit_inputs_result(result, template_format=InputsTemplateFormat.JSON)

        envelope = json.loads(capsys.readouterr().out)
        assert "concept_comments" not in envelope
        assert envelope["inputs"] == {"question": "text_value"}
