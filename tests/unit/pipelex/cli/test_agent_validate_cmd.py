"""Unit tests for the agent CLI validate command."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

import pytest
import typer
from pipelex.cli.agent_cli.commands.validate.pipe_cmd import validate_pipe_cmd

from pipelex.pipe_run.pipe_run_mode import PipeRunMode
from pipelex.pipeline.exceptions import PipelineExecutionError

if TYPE_CHECKING:
    from pathlib import Path

    from pytest_mock import MockerFixture

VALIDATE_CMD_MODULE = "pipelex.cli.agent_cli.commands.validate.pipe_cmd"


class TestValidateCmd:
    """Tests for the validate command error handling."""

    def test_graph_generation_failure_emits_single_json_error(
        self,
        agent_ctx: Any,
        mocker: MockerFixture,
        capsys: pytest.CaptureFixture[str],
        tmp_path: Path,
    ) -> None:
        """When graph generation fails, exactly one JSON error object should appear on stderr.

        Regression test: previously, agent_error() in the inner graph-generation
        except handler raised typer.Exit(1), which was caught by the outer
        `except Exception` handler, producing a second spurious JSON error with
        message "1" and type "Exit".
        """
        mthds_file = tmp_path / "bundle.mthds"
        mthds_file.write_text('[bundle]\nmain_pipe = "my_pipe"\n[domain]\ncode = "test"')

        mocker.patch(f"{VALIDATE_CMD_MODULE}.make_pipelex_for_agent_cli")
        mocker.patch(f"{VALIDATE_CMD_MODULE}.Pipelex.teardown_if_needed")

        # Bundle validation succeeds
        validation_result: dict[str, Any] = {
            "success": True,
            "bundle_path": str(mthds_file),
            "validated_pipes": [{"pipe_code": "my_pipe", "status": "SUCCESS"}],
            "total_pipes": 1,
        }
        mocker.patch(
            f"{VALIDATE_CMD_MODULE}._validate_bundle_core",
            new=mocker.AsyncMock(return_value=validation_result),
        )

        # Graph generation fails
        graph_error = PipelineExecutionError(
            message="Graph rendering blew up",
            run_mode=PipeRunMode.DRY,
            pipe_code="my_pipe",
            output_name=None,
            pipe_stack=["my_pipe"],
        )
        mocker.patch(
            f"{VALIDATE_CMD_MODULE}.generate_graph_for_bundle",
            new=mocker.AsyncMock(side_effect=graph_error),
        )

        with pytest.raises(typer.Exit) as exc_info:
            validate_pipe_cmd(
                ctx=agent_ctx,
                target=str(mthds_file),
                graph=True,
            )

        assert exc_info.value.exit_code == 1

        stderr_text = capsys.readouterr().err
        # Parse all JSON objects from stderr — there should be exactly one
        json_objects: list[dict[str, Any]] = []
        decoder = json.JSONDecoder()
        idx = 0
        while idx < len(stderr_text):
            # Skip whitespace
            while idx < len(stderr_text) and stderr_text[idx] in " \t\n\r":
                idx += 1
            if idx >= len(stderr_text):
                break
            try:
                obj, end_idx = decoder.raw_decode(stderr_text, idx)
                json_objects.append(obj)
                idx = end_idx
            except json.JSONDecodeError:
                break

        assert len(json_objects) == 1, f"Expected exactly 1 JSON error on stderr, got {len(json_objects)}. stderr was:\n{stderr_text}"
        error_obj = json_objects[0]
        assert error_obj["error"] is True
        assert error_obj["error_type"] == "PipelineExecutionError"
        assert "graph" in error_obj["message"].lower()
