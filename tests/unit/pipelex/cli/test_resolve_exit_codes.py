"""The `pipelex resolve` 0/1/2 exit-code policy (mirrors the bare `validate` group).

Policy: exit 0 = resolved (crate emitted); exit 1 = a produced NEGATIVE VERDICT (the library is
invalid, so no crate can be produced); exit 2 = NO VERDICT (empty closure, file-not-found). The
verdict cases mock the resolve internals — boot/teardown are neutralized so no real Pipelex is made.
The real end-to-end exit codes against the binary are pinned by the conformance suite.
"""

from __future__ import annotations

import contextlib
from typing import TYPE_CHECKING

import pytest
import typer

from pipelex.cli.commands.resolve_cmd import resolve_cmd
from pipelex.codegen.crate_encoding import CrateEncoding
from pipelex.libraries.exceptions import LibraryLoadingError
from pipelex.libraries.pipe.exceptions import PipeLibraryError

if TYPE_CHECKING:
    from pytest_mock import MockerFixture

MODULE = "pipelex.cli.commands.resolve_cmd"


class TestResolveExitCodes:
    """The resolve 0/1/2 exit-code policy, with boot/teardown mocked out."""

    def _neutralize_boot(self, mocker: MockerFixture) -> None:
        mocker.patch(f"{MODULE}.make_pipelex_for_cli")
        mocker.patch(f"{MODULE}.Pipelex.teardown_if_needed")
        mocker.patch(f"{MODULE}.tag")
        telemetry_manager = mocker.patch(f"{MODULE}.get_telemetry_manager").return_value
        # A real null context manager — a bare MagicMock would suppress the exception under test.
        telemetry_manager.telemetry_context.return_value = contextlib.nullcontext()

    def test_invalid_library_is_negative_verdict_exit_1(self, mocker: MockerFixture) -> None:
        self._neutralize_boot(mocker)
        mocker.patch(f"{MODULE}.load_libraries_and_activate", side_effect=LibraryLoadingError("invalid library"))
        with pytest.raises(typer.Exit) as exc_info:
            resolve_cmd(paths=None, output_format=CrateEncoding.JSON, library_dir=None)
        assert exc_info.value.exit_code == 1

    def test_pipe_conflict_is_negative_verdict_exit_1(self, mocker: MockerFixture) -> None:
        # A duplicate-pipe-across-bundles conflict surfaces as PipeLibraryError (a LibraryError sibling
        # of LibraryLoadingError, not a subclass): still an invalid-library negative verdict -> exit 1.
        self._neutralize_boot(mocker)
        mocker.patch(f"{MODULE}.load_libraries_and_activate", side_effect=PipeLibraryError("duplicate pipe across bundles"))
        with pytest.raises(typer.Exit) as exc_info:
            resolve_cmd(paths=None, output_format=CrateEncoding.JSON, library_dir=None)
        assert exc_info.value.exit_code == 1

    def test_empty_closure_is_no_verdict_exit_2(self, mocker: MockerFixture) -> None:
        self._neutralize_boot(mocker)
        mocker.patch(f"{MODULE}.load_libraries_and_activate", return_value="lib-1")
        library_manager = mocker.patch(f"{MODULE}.get_library_manager").return_value
        library_manager.get_crate.return_value = None
        with pytest.raises(typer.Exit) as exc_info:
            resolve_cmd(paths=None, output_format=CrateEncoding.JSON, library_dir=None)
        assert exc_info.value.exit_code == 2

    def test_file_not_found_is_no_verdict_exit_2(self, mocker: MockerFixture) -> None:
        self._neutralize_boot(mocker)
        mocker.patch(f"{MODULE}.load_libraries_and_activate", side_effect=FileNotFoundError("no such directory"))
        with pytest.raises(typer.Exit) as exc_info:
            resolve_cmd(paths=None, output_format=CrateEncoding.JSON, library_dir=None)
        assert exc_info.value.exit_code == 2

    def test_valid_library_emits_crate_exit_0(self, mocker: MockerFixture, capsys: pytest.CaptureFixture[str]) -> None:
        self._neutralize_boot(mocker)
        mocker.patch(f"{MODULE}.load_libraries_and_activate", return_value="lib-1")
        library_manager = mocker.patch(f"{MODULE}.get_library_manager").return_value
        library_manager.get_crate.return_value = mocker.MagicMock()
        mocker.patch(f"{MODULE}.normalize_crate", return_value=mocker.MagicMock())
        mocker.patch(f"{MODULE}.encode_crate", return_value="<<crate-body>>")
        # A resolved library emits the crate to stdout and does not raise (implicit exit 0).
        resolve_cmd(paths=None, output_format=CrateEncoding.JSON, library_dir=None)
        assert "<<crate-body>>" in capsys.readouterr().out
