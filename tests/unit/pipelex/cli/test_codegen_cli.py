"""The `pipelex codegen types` / `codegen inputs` CLI: file writing, pipe selection, and exit codes.

Boot/teardown and the crate loader are mocked out so no real Pipelex is made; the emitter and the
input renderer are stubbed so these tests pin the CLI wiring (targets, output paths, main_pipe
defaulting, and the resolve-verdict exit codes), not the projection engines (covered by their own
unit tests). End-to-end behavior against the binary is pinned by the conformance suite.
"""

from __future__ import annotations

import contextlib
from typing import TYPE_CHECKING

import pytest
import typer

from pipelex.cli.commands.codegen.inputs_cmd import codegen_inputs_cmd
from pipelex.cli.commands.codegen.types_cmd import codegen_types_cmd
from pipelex.codegen.emitters.target import CodegenTarget, EmittedFile
from pipelex.codegen.lock import CODEGEN_LOCK_FILENAME
from pipelex.core.domains.domain_blueprint import DomainBlueprint
from pipelex.core.pipes.inputs.input_renderer import InputsTemplateFormat
from pipelex.libraries.library_crate import LibraryCrate
from pipelex.libraries.pipe.exceptions import PipeLibraryError

if TYPE_CHECKING:
    from pathlib import Path
    from unittest.mock import MagicMock

    from pytest_mock import MockerFixture

TYPES = "pipelex.cli.commands.codegen.types_cmd"
INPUTS = "pipelex.cli.commands.codegen.inputs_cmd"


class TestCodegenCli:
    """The two Phase-1 codegen commands, with boot/teardown and the crate loader mocked out."""

    def _neutralize_boot(self, mocker: MockerFixture, *, module: str) -> MagicMock:
        boot = mocker.patch(f"{module}.make_pipelex_for_cli")
        mocker.patch(f"{module}.Pipelex.teardown_if_needed")
        mocker.patch(f"{module}.tag")
        telemetry_manager = mocker.patch(f"{module}.get_telemetry_manager").return_value
        telemetry_manager.telemetry_context.return_value = contextlib.nullcontext()
        return boot

    def test_types_writes_every_emitted_stamped_and_locked_exit_0(self, mocker: MockerFixture, tmp_path: Path) -> None:
        self._neutralize_boot(mocker, module=TYPES)
        crate = LibraryCrate(fingerprint="deadbeef")
        mocker.patch(f"{TYPES}.load_normalized_crate_or_exit", return_value=crate)
        mocker.patch(
            f"{TYPES}.emit_types",
            return_value=[EmittedFile(filename="types.ts", content="// types\n"), EmittedFile(filename="binder.ts", content="// binder\n")],
        )
        codegen_types_cmd(target=CodegenTarget.TS_ZOD, paths=None, output_dir=str(tmp_path), library_dir=None)
        # Each file is stamped (self-describing) with the body preserved below the stamp, and locked.
        types_text = (tmp_path / "types.ts").read_text(encoding="utf-8")
        assert types_text.startswith("// >>> pipelex-codegen-stamp >>>")
        assert "crate_fingerprint: deadbeef" in types_text
        assert types_text.endswith("// types\n")
        assert (tmp_path / "binder.ts").read_text(encoding="utf-8").endswith("// binder\n")
        assert (tmp_path / CODEGEN_LOCK_FILENAME).is_file()

    @pytest.mark.parametrize("module", [TYPES, INPUTS])
    def test_boot_loads_model_specs_for_offline_validation(self, mocker: MockerFixture, tmp_path: Path, module: str) -> None:
        """Codegen boots offline but WITH model specs (like `validate`): library validation checks
        pipe model pins (`model = "gpt-4o-mini"`) against the deck, so a spec-less boot would reject
        any bundle that pins a model — the drift this test guards against.
        """
        boot = self._neutralize_boot(mocker, module=module)
        if module == TYPES:
            mocker.patch(f"{TYPES}.load_normalized_crate_or_exit", return_value=LibraryCrate(fingerprint="deadbeef"))
            mocker.patch(f"{TYPES}.emit_types", return_value=[EmittedFile(filename="types.ts", content="// types\n")])
            codegen_types_cmd(target=CodegenTarget.TS_ZOD, paths=None, output_dir=str(tmp_path), library_dir=None)
        else:
            crate = LibraryCrate(domains={"scoring": DomainBlueprint(code="scoring", description="d", main_pipe="run_scoring")})
            mocker.patch(f"{INPUTS}.load_normalized_crate_or_exit", return_value=crate)
            mocker.patch(f"{INPUTS}.get_required_pipe")
            mocker.patch(f"{INPUTS}.render_inputs", return_value="{}")
            codegen_inputs_cmd(
                pipe=None,
                paths=None,
                template_format=InputsTemplateFormat.JSON,
                explicit=False,
                output=str(tmp_path / "inputs.json"),
                library_dir=None,
            )
        assert boot.call_args.kwargs["needs_inference"] is False
        assert boot.call_args.kwargs["needs_model_specs"] is True

    def test_types_invalid_library_verdict_propagates(self, mocker: MockerFixture, tmp_path: Path) -> None:
        self._neutralize_boot(mocker, module=TYPES)
        mocker.patch(f"{TYPES}.load_normalized_crate_or_exit", side_effect=typer.Exit(1))
        with pytest.raises(typer.Exit) as exc_info:
            codegen_types_cmd(target=CodegenTarget.TS_ZOD, paths=None, output_dir=str(tmp_path), library_dir=None)
        assert exc_info.value.exit_code == 1

    def test_inputs_defaults_to_the_single_main_pipe(self, mocker: MockerFixture, tmp_path: Path) -> None:
        self._neutralize_boot(mocker, module=INPUTS)
        crate = LibraryCrate(domains={"scoring": DomainBlueprint(code="scoring", description="d", main_pipe="run_scoring")})
        mocker.patch(f"{INPUTS}.load_normalized_crate_or_exit", return_value=crate)
        get_required_pipe = mocker.patch(f"{INPUTS}.get_required_pipe")
        mocker.patch(f"{INPUTS}.render_inputs", return_value='{"topic": "x"}')
        destination = tmp_path / "inputs.json"
        codegen_inputs_cmd(
            pipe=None, paths=None, template_format=InputsTemplateFormat.JSON, explicit=False, output=str(destination), library_dir=None
        )
        # The single declared main_pipe was selected (qualified) and rendered to the output file.
        assert get_required_pipe.call_args.kwargs["pipe_code"] == "scoring.run_scoring"
        assert destination.read_text(encoding="utf-8") == '{"topic": "x"}'

    def test_inputs_no_main_pipe_is_exit_1(self, mocker: MockerFixture) -> None:
        self._neutralize_boot(mocker, module=INPUTS)
        crate = LibraryCrate(domains={"scoring": DomainBlueprint(code="scoring", description="d", main_pipe=None)})
        mocker.patch(f"{INPUTS}.load_normalized_crate_or_exit", return_value=crate)
        with pytest.raises(typer.Exit) as exc_info:
            codegen_inputs_cmd(pipe=None, paths=None, template_format=InputsTemplateFormat.JSON, explicit=False, output=None, library_dir=None)
        assert exc_info.value.exit_code == 1

    def test_inputs_ambiguous_main_pipe_is_exit_1(self, mocker: MockerFixture) -> None:
        self._neutralize_boot(mocker, module=INPUTS)
        crate = LibraryCrate(
            domains={
                "a": DomainBlueprint(code="a", description="d", main_pipe="run_a"),
                "b": DomainBlueprint(code="b", description="d", main_pipe="run_b"),
            }
        )
        mocker.patch(f"{INPUTS}.load_normalized_crate_or_exit", return_value=crate)
        with pytest.raises(typer.Exit) as exc_info:
            codegen_inputs_cmd(pipe=None, paths=None, template_format=InputsTemplateFormat.JSON, explicit=False, output=None, library_dir=None)
        assert exc_info.value.exit_code == 1

    def test_inputs_unknown_explicit_pipe_is_exit_1(self, mocker: MockerFixture) -> None:
        self._neutralize_boot(mocker, module=INPUTS)
        mocker.patch(f"{INPUTS}.load_normalized_crate_or_exit", return_value=LibraryCrate())
        mocker.patch(f"{INPUTS}.get_required_pipe", side_effect=PipeLibraryError("no such pipe"))
        with pytest.raises(typer.Exit) as exc_info:
            codegen_inputs_cmd(
                pipe="scoring.missing", paths=None, template_format=InputsTemplateFormat.JSON, explicit=False, output=None, library_dir=None
            )
        assert exc_info.value.exit_code == 1
