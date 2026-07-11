"""The `pipelex-agent codegen types` command: envelopes, exit codes, and boot kwargs.

Boot/teardown and the crate loader are mocked out so no real Pipelex is made; the emitter is stubbed
so these tests pin the agent-CLI wiring (the two-stream success/error envelopes and the resolve
verdict exit codes), not the projection engine (covered by its own unit tests). The stamped emission
layer runs for real against tmp_path.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
import typer

from pipelex.cli.agent_cli.commands.agent_output import CliOutputFormat
from pipelex.cli.agent_cli.commands.codegen.types_cmd import agent_codegen_types_cmd
from pipelex.codegen.emitters.target import CodegenTarget, EmittedFile
from pipelex.codegen.lock import CODEGEN_LOCK_FILENAME
from pipelex.libraries.exceptions import LibraryLoadingError
from pipelex.libraries.library_crate import LibraryCrate

if TYPE_CHECKING:
    from pytest_mock import MockerFixture

CMD_MODULE = "pipelex.cli.agent_cli.commands.codegen.types_cmd"


class TestAgentCodegenTypesCmd:
    """The agent-CLI types projection command, with boot and the crate loader mocked out."""

    def _neutralize_boot(self, mocker: MockerFixture) -> None:
        mocker.patch(f"{CMD_MODULE}.make_pipelex_for_agent_cli")
        mocker.patch(f"{CMD_MODULE}.Pipelex.teardown_if_needed")

    def test_json_success_envelope_and_stamped_files(self, mocker: MockerFixture, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        """A successful projection emits the structured JSON envelope on stdout and stamped files + lock on disk."""
        self._neutralize_boot(mocker)
        mocker.patch(f"{CMD_MODULE}.load_normalized_crate", return_value=LibraryCrate(fingerprint="deadbeef"))
        mocker.patch(f"{CMD_MODULE}.emit_types", return_value=[EmittedFile(filename="models.py", content="# models\n")])

        agent_codegen_types_cmd(
            target=CodegenTarget.PYTHON_PYDANTIC,
            paths=None,
            output_dir=str(tmp_path),
            library_dir=None,
            output_format=CliOutputFormat.JSON,
            error_format=None,
        )

        envelope = json.loads(capsys.readouterr().out)
        assert envelope["success"] is True
        assert envelope["kind"] == "types"
        assert envelope["target"] == "python-pydantic"
        assert envelope["crate_fingerprint"] == "deadbeef"
        assert envelope["written"] == ["models.py"]
        assert envelope["unchanged"] == []
        assert envelope["lock_file"].endswith(CODEGEN_LOCK_FILENAME)
        models_text = (tmp_path / "models.py").read_text(encoding="utf-8")
        assert models_text.startswith("# >>> pipelex-codegen-stamp >>>")
        assert models_text.endswith("# models\n")
        assert (tmp_path / CODEGEN_LOCK_FILENAME).is_file()

    def test_markdown_success_is_the_default(self, mocker: MockerFixture, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        self._neutralize_boot(mocker)
        mocker.patch(f"{CMD_MODULE}.load_normalized_crate", return_value=LibraryCrate(fingerprint="deadbeef"))
        mocker.patch(f"{CMD_MODULE}.emit_types", return_value=[EmittedFile(filename="models.py", content="# models\n")])

        agent_codegen_types_cmd(
            target=CodegenTarget.PYTHON_PYDANTIC,
            paths=None,
            output_dir=str(tmp_path),
            library_dir=None,
            output_format=CliOutputFormat.MARKDOWN,
            error_format=None,
        )

        stdout = capsys.readouterr().out
        assert stdout.startswith("# Codegen complete")
        assert "- Generated `models.py`" in stdout
        assert "`deadbeef`" in stdout

    def test_invalid_library_is_structured_error_exit_1(self, mocker: MockerFixture, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        """An invalid library is a negative verdict: exit 1 with the structured error envelope on stderr."""
        self._neutralize_boot(mocker)
        mocker.patch(f"{CMD_MODULE}.load_normalized_crate", side_effect=LibraryLoadingError("duplicate pipe"))

        with pytest.raises(typer.Exit) as exc_info:
            agent_codegen_types_cmd(
                target=CodegenTarget.PYTHON_PYDANTIC,
                paths=None,
                output_dir=str(tmp_path),
                library_dir=None,
                output_format=CliOutputFormat.JSON,
                error_format=None,
            )

        assert exc_info.value.exit_code == 1
        error = json.loads(capsys.readouterr().err)
        assert error["error"] is True
        assert error["error_type"] == "LibraryLoadingError"
        assert "duplicate pipe" in error["message"]

    def test_unassembled_closure_is_no_verdict_exit_2(self, mocker: MockerFixture, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        self._neutralize_boot(mocker)
        mocker.patch(f"{CMD_MODULE}.load_normalized_crate", side_effect=FileNotFoundError("no .mthds bundles found in the closure."))

        with pytest.raises(typer.Exit) as exc_info:
            agent_codegen_types_cmd(
                target=CodegenTarget.PYTHON_PYDANTIC,
                paths=None,
                output_dir=str(tmp_path),
                library_dir=None,
                output_format=CliOutputFormat.JSON,
                error_format=None,
            )

        assert exc_info.value.exit_code == 2
        error = json.loads(capsys.readouterr().err)
        assert error["error_type"] == "FileNotFoundError"

    def test_boot_loads_model_specs_for_offline_validation(self, mocker: MockerFixture, tmp_path: Path) -> None:
        """Like the bare CLI, the agent mirror boots offline but WITH model specs: library validation
        checks pipe model pins against the deck, so a spec-less boot would reject any bundle pinning
        a model — the drift this test guards against.
        """
        boot = mocker.patch(f"{CMD_MODULE}.make_pipelex_for_agent_cli")
        mocker.patch(f"{CMD_MODULE}.Pipelex.teardown_if_needed")
        mocker.patch(f"{CMD_MODULE}.load_normalized_crate", return_value=LibraryCrate(fingerprint="deadbeef"))
        mocker.patch(f"{CMD_MODULE}.emit_types", return_value=[EmittedFile(filename="models.py", content="# models\n")])

        agent_codegen_types_cmd(
            target=CodegenTarget.PYTHON_PYDANTIC,
            paths=None,
            output_dir=str(tmp_path),
            library_dir=None,
            output_format=CliOutputFormat.JSON,
            error_format=None,
        )

        assert boot.call_args.kwargs["needs_inference"] is False
        assert boot.call_args.kwargs["needs_model_specs"] is True

    def test_expands_home_relative_output(self, mocker: MockerFixture, capsys: pytest.CaptureFixture[str]) -> None:
        self._neutralize_boot(mocker)
        mocker.patch(f"{CMD_MODULE}.load_normalized_crate", return_value=LibraryCrate(fingerprint="deadbeef"))
        mocker.patch(f"{CMD_MODULE}.emit_types", return_value=[])
        write_projection = mocker.patch(f"{CMD_MODULE}.write_stamped_projection")
        write_projection.return_value.written = []
        write_projection.return_value.unchanged = []
        write_projection.return_value.removed = []
        write_projection.return_value.lock_path = CODEGEN_LOCK_FILENAME

        agent_codegen_types_cmd(
            target=CodegenTarget.PYTHON_PYDANTIC,
            paths=None,
            output_dir="~/generated",
            library_dir=None,
            output_format=CliOutputFormat.JSON,
            error_format=None,
        )

        assert write_projection.call_args.kwargs["output_dir"] == Path.home() / "generated"
        capsys.readouterr()
