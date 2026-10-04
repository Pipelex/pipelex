"""Pin: ``pipelex-agent validate pipe`` and ``validate --all`` answer a failing dry run with its located item.

They go through the same bundle-loading cascade and item builder as ``validate bundle``, so a pipe whose
dry run fails is an invalid verdict (``is_valid: false``, exit 1) carrying one ``dry_run`` item for the
innermost failing pipe, where they used to answer it with no ``validation_errors`` at all. Validating the
sequence that runs the failing parallel reports the parallel, once.
"""

import json
from pathlib import Path
from typing import Any

import pytest
import typer
from pytest_mock import MockerFixture

from pipelex.cli.agent_cli.commands.agent_output import CliOutputFormat, set_agent_cli_error_format
from pipelex.cli.agent_cli.commands.validate.pipe_cmd import validate_pipe_cmd as agent_validate_pipe_cmd
from tests.integration.pipelex.test_data import ValidationDetailBundles

_PIPE_CMD_MODULE = "pipelex.cli.agent_cli.commands.validate.pipe_cmd"


@pytest.fixture
def library_dir(tmp_path: Path) -> Path:
    (tmp_path / "bundle.mthds").write_text(ValidationDetailBundles.NESTED_PARALLEL_MISMATCH, encoding="utf-8")
    return tmp_path


class TestAgentValidatePipeDryRunItems:
    @pytest.mark.parametrize(
        ("pipe_code", "validate_all"),
        [("analyze_topic", False), ("run_workshop", False), (None, True)],
        ids=["failing_pipe", "enclosing_pipe", "all"],
    )
    def test_a_failing_dry_run_is_an_invalid_verdict_with_the_located_item(
        self,
        mocker: MockerFixture,
        capsys: pytest.CaptureFixture[str],
        library_dir: Path,
        pipe_code: str | None,
        validate_all: bool,
    ) -> None:
        mocker.patch(f"{_PIPE_CMD_MODULE}.make_pipelex_for_agent_cli")
        mocker.patch(f"{_PIPE_CMD_MODULE}.Pipelex.teardown_if_needed")
        mocker.patch(f"{_PIPE_CMD_MODULE}.resolve_pipe_from_exports", return_value=[])
        try:
            with pytest.raises(typer.Exit) as exc_info:
                agent_validate_pipe_cmd(
                    pipe_code=pipe_code,
                    validate_all=validate_all,
                    library_dir=[str(library_dir)],
                    output_format=CliOutputFormat.JSON,
                )
        finally:
            set_agent_cli_error_format(CliOutputFormat.JSON)

        assert exc_info.value.exit_code == 1
        envelope: dict[str, Any] = json.loads(capsys.readouterr().err)
        assert envelope["is_valid"] is False
        assert envelope["error_type"] == "ValidateBundleError"
        (item,) = envelope["validation_errors"]
        assert item["category"] == "dry_run"
        assert item["error_type"] == "DryRunError"
        assert item["pipe_code"] == "analyze_topic"
        assert item["domain_code"] == ValidationDetailBundles.DOMAIN
        assert item["source"] == str(library_dir / "bundle.mthds")
        assert not any(marker in item["message"] for marker in ValidationDetailBundles.RECORD_REPR_MARKERS)
