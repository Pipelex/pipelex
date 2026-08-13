"""The validate 0/1/2 exit-code policy on both CLIs (bare ``pipelex validate`` + ``pipelex-agent validate``).

Policy: exit 0 = valid; exit 1 = a produced NEGATIVE VERDICT (invalid bundle, or
valid-but-not-runnable without ``--allow-signatures``); exit 2 = NO VERDICT (bad
args, unresolvable target, file-not-found, unexpected). See the
validation-API spec (CLI exit-code policy) and the MTHDS protocol spec
(Agent-CLI validate envelope).

The pre-boot argument/target-resolution cases are pure (they raise before any
Pipelex boot); the negative-verdict / no-verdict / signature-gate cases mock the
validate core (mirroring ``test_agent_validate_cmd.py``). The real end-to-end
exit codes against the binary are pinned by our cross-repo spec suite.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest
import typer

from pipelex.cli.agent_cli.commands.agent_output import CliOutputFormat
from pipelex.cli.agent_cli.commands.validate.bundle_cmd import validate_bundle_cmd as agent_validate_bundle_cmd
from pipelex.cli.agent_cli.commands.validate.pipe_cmd import validate_pipe_cmd as agent_validate_pipe_cmd
from pipelex.cli.commands.validate.bundle_cmd import validate_bundle_cmd as bare_validate_bundle_cmd
from pipelex.cli.commands.validate.pipe_cmd import validate_pipe_cmd as bare_validate_pipe_cmd
from pipelex.libraries.pipe.exceptions import PipeLibraryError
from pipelex.pipe_run.exceptions import DryRunError
from pipelex.pipeline.exceptions import ValidateBundleError

if TYPE_CHECKING:
    from pathlib import Path

    from pytest_mock import MockerFixture

AGENT_BUNDLE_MODULE = "pipelex.cli.agent_cli.commands.validate.bundle_cmd"
AGENT_PIPE_MODULE = "pipelex.cli.agent_cli.commands.validate.pipe_cmd"
BARE_VALIDATE_CORE = "pipelex.cli.commands.validate._validate_core"


def _make_dir(tmp_path: Path, name: str, mthds_files: list[str]) -> Path:
    """Create a directory containing the given .mthds filenames (empty content)."""
    directory = tmp_path / name
    directory.mkdir()
    for filename in mthds_files:
        (directory / filename).write_text('[domain]\ncode = "test"\n')
    return directory


class TestValidateExitCodes:
    """The validate 0/1/2 exit-code policy on both CLIs.

    ``bare_*`` cover the bare ``pipelex validate`` group; ``agent_*`` cover
    ``pipelex-agent validate``. The pre-boot bad-args / target-resolution cases
    exit 2 before any Pipelex boot; the verdict cases mock the validate core.
    """

    # --- bare CLI: bad args / unresolvable targets exit 2 (no verdict), pre-boot ---

    def test_bare_bundle_directory_without_mthds_exits_2(self, tmp_path: Path) -> None:
        empty_dir = _make_dir(tmp_path, "empty", [])
        with pytest.raises(typer.Exit) as exc_info:
            bare_validate_bundle_cmd(path=str(empty_dir))
        assert exc_info.value.exit_code == 2

    def test_bare_bundle_directory_with_multiple_mthds_and_no_default_exits_2(self, tmp_path: Path) -> None:
        multi_dir = _make_dir(tmp_path, "multi", ["a.mthds", "b.mthds"])
        with pytest.raises(typer.Exit) as exc_info:
            bare_validate_bundle_cmd(path=str(multi_dir))
        assert exc_info.value.exit_code == 2

    def test_bare_bundle_path_that_is_neither_file_nor_dir_exits_2(self, tmp_path: Path) -> None:
        with pytest.raises(typer.Exit) as exc_info:
            bare_validate_bundle_cmd(path=str(tmp_path / "nope"))
        assert exc_info.value.exit_code == 2

    def test_bare_pipe_all_combined_with_code_exits_2(self) -> None:
        with pytest.raises(typer.Exit) as exc_info:
            bare_validate_pipe_cmd(pipe_code="some_pipe", validate_all=True)
        assert exc_info.value.exit_code == 2

    def test_bare_pipe_without_code_or_all_exits_2(self) -> None:
        with pytest.raises(typer.Exit) as exc_info:
            bare_validate_pipe_cmd(pipe_code=None)
        assert exc_info.value.exit_code == 2

    def test_bare_pipe_code_that_looks_like_a_path_exits_2(self) -> None:
        with pytest.raises(typer.Exit) as exc_info:
            bare_validate_pipe_cmd(pipe_code="my_bundle.mthds")
        assert exc_info.value.exit_code == 2

    def test_bare_pipe_ambiguous_code_is_no_verdict_exit_2(self, mocker: MockerFixture) -> None:
        """A bare code declared by several domains is an unresolvable target: clean exit 2, not a traceback."""
        mocker.patch("pipelex.cli.commands.validate.pipe_cmd.resolve_pipe_from_exports", return_value=[])
        mocker.patch(f"{BARE_VALIDATE_CORE}.make_pipelex_for_cli")
        mocker.patch(f"{BARE_VALIDATE_CORE}.Pipelex.teardown_if_needed")
        library_manager = mocker.Mock()
        library_manager.open_library.return_value = ("lib-id", mocker.Mock())
        mocker.patch(f"{BARE_VALIDATE_CORE}.get_library_manager", return_value=library_manager)
        mocker.patch(f"{BARE_VALIDATE_CORE}.set_current_library")
        mocker.patch(f"{BARE_VALIDATE_CORE}.resolve_library_dirs", return_value=([], "defaults"))
        mocker.patch(
            f"{BARE_VALIDATE_CORE}.get_required_entry_pipe",
            side_effect=PipeLibraryError("Pipe code 'my_pipe' is ambiguous: declared by ['a.my_pipe', 'b.my_pipe']"),
        )
        with pytest.raises(typer.Exit) as exc_info:
            bare_validate_pipe_cmd(pipe_code="my_pipe")
        assert exc_info.value.exit_code == 2

    # --- agent CLI: bad args / unresolvable targets exit 2 (no verdict), pre-boot ---

    def test_agent_bundle_directory_without_mthds_exits_2(self, tmp_path: Path) -> None:
        empty_dir = _make_dir(tmp_path, "empty", [])
        with pytest.raises(typer.Exit) as exc_info:
            agent_validate_bundle_cmd(path=str(empty_dir), output_format=CliOutputFormat.JSON)
        assert exc_info.value.exit_code == 2

    def test_agent_bundle_directory_with_multiple_mthds_exits_2(self, tmp_path: Path) -> None:
        multi_dir = _make_dir(tmp_path, "multi", ["a.mthds", "b.mthds"])
        with pytest.raises(typer.Exit) as exc_info:
            agent_validate_bundle_cmd(path=str(multi_dir), output_format=CliOutputFormat.JSON)
        assert exc_info.value.exit_code == 2

    def test_agent_bundle_path_that_is_neither_file_nor_dir_exits_2(self, tmp_path: Path) -> None:
        with pytest.raises(typer.Exit) as exc_info:
            agent_validate_bundle_cmd(path=str(tmp_path / "nope"), output_format=CliOutputFormat.JSON)
        assert exc_info.value.exit_code == 2

    def test_agent_pipe_all_combined_with_code_exits_2(self) -> None:
        with pytest.raises(typer.Exit) as exc_info:
            agent_validate_pipe_cmd(pipe_code="some_pipe", validate_all=True, output_format=CliOutputFormat.JSON)
        assert exc_info.value.exit_code == 2

    def test_agent_pipe_without_code_or_all_exits_2(self) -> None:
        with pytest.raises(typer.Exit) as exc_info:
            agent_validate_pipe_cmd(pipe_code=None, output_format=CliOutputFormat.JSON)
        assert exc_info.value.exit_code == 2

    def test_agent_pipe_code_that_looks_like_a_path_exits_2(self) -> None:
        with pytest.raises(typer.Exit) as exc_info:
            agent_validate_pipe_cmd(pipe_code="my_bundle.mthds", output_format=CliOutputFormat.JSON)
        assert exc_info.value.exit_code == 2

    # --- agent CLI bundle: negative verdict (1), no verdict (2), signature gate, valid (0) ---

    def _bundle_file(self, tmp_path: Path) -> Path:
        mthds_file = tmp_path / "bundle.mthds"
        mthds_file.write_text('[bundle]\nmain_pipe = "my_pipe"\n[domain]\ncode = "test"\n')
        return mthds_file

    def _patch_boot(self, mocker: MockerFixture) -> None:
        mocker.patch(f"{AGENT_BUNDLE_MODULE}.make_pipelex_for_agent_cli")
        mocker.patch(f"{AGENT_BUNDLE_MODULE}.Pipelex.teardown_if_needed")

    def test_invalid_bundle_is_negative_verdict_exit_1(self, mocker: MockerFixture, tmp_path: Path) -> None:
        self._patch_boot(mocker)
        mocker.patch(
            f"{AGENT_BUNDLE_MODULE}.validate_bundle_core",
            new=mocker.AsyncMock(side_effect=ValidateBundleError("Bundle is invalid", dry_run_error_message="boom")),
        )
        with pytest.raises(typer.Exit) as exc_info:
            agent_validate_bundle_cmd(path=str(self._bundle_file(tmp_path)), output_format=CliOutputFormat.JSON)
        assert exc_info.value.exit_code == 1

    def test_bundle_file_not_found_is_no_verdict_exit_2(self, mocker: MockerFixture, tmp_path: Path) -> None:
        self._patch_boot(mocker)
        mocker.patch(
            f"{AGENT_BUNDLE_MODULE}.validate_bundle_core",
            new=mocker.AsyncMock(side_effect=FileNotFoundError("missing")),
        )
        with pytest.raises(typer.Exit) as exc_info:
            agent_validate_bundle_cmd(path=str(self._bundle_file(tmp_path)), output_format=CliOutputFormat.JSON)
        assert exc_info.value.exit_code == 2

    def test_not_runnable_without_allow_signatures_is_negative_verdict_exit_1(self, mocker: MockerFixture, tmp_path: Path) -> None:
        self._patch_boot(mocker)
        not_runnable: dict[str, Any] = {
            "success": True,
            "is_valid": True,
            "bundle_path": str(self._bundle_file(tmp_path)),
            "validated_pipes": [{"pipe_ref": "test.my_pipe", "status": "SUCCESS"}],
            "total_pipes": 1,
            "pending_signatures": ["test.todo"],
            "is_runnable": False,
        }
        mocker.patch(f"{AGENT_BUNDLE_MODULE}.validate_bundle_core", new=mocker.AsyncMock(return_value=not_runnable))
        with pytest.raises(typer.Exit) as exc_info:
            agent_validate_bundle_cmd(path=str(self._bundle_file(tmp_path)), output_format=CliOutputFormat.JSON, allow_signatures=False)
        assert exc_info.value.exit_code == 1

    def test_not_runnable_with_allow_signatures_exits_0(self, mocker: MockerFixture, tmp_path: Path) -> None:
        self._patch_boot(mocker)
        not_runnable: dict[str, Any] = {
            "success": True,
            "is_valid": True,
            "bundle_path": str(self._bundle_file(tmp_path)),
            "validated_pipes": [{"pipe_ref": "test.my_pipe", "status": "SUCCESS"}],
            "total_pipes": 1,
            "pending_signatures": ["test.todo"],
            "is_runnable": False,
        }
        mocker.patch(f"{AGENT_BUNDLE_MODULE}.validate_bundle_core", new=mocker.AsyncMock(return_value=not_runnable))
        # --allow-signatures tolerates the placeholders: the command returns normally (exit 0), no typer.Exit.
        agent_validate_bundle_cmd(path=str(self._bundle_file(tmp_path)), output_format=CliOutputFormat.JSON, allow_signatures=True)

    def test_valid_runnable_bundle_exits_0(self, mocker: MockerFixture, tmp_path: Path) -> None:
        self._patch_boot(mocker)
        runnable: dict[str, Any] = {
            "success": True,
            "is_valid": True,
            "bundle_path": str(self._bundle_file(tmp_path)),
            "validated_pipes": [{"pipe_ref": "test.my_pipe", "status": "SUCCESS"}],
            "total_pipes": 1,
            "pending_signatures": [],
            "is_runnable": True,
        }
        mocker.patch(f"{AGENT_BUNDLE_MODULE}.validate_bundle_core", new=mocker.AsyncMock(return_value=runnable))
        # Valid and runnable: returns normally (exit 0), no typer.Exit raised.
        agent_validate_bundle_cmd(path=str(self._bundle_file(tmp_path)), output_format=CliOutputFormat.JSON)

    def _patch_pipe_boot(self, mocker: MockerFixture) -> None:
        mocker.patch(f"{AGENT_PIPE_MODULE}.make_pipelex_for_agent_cli")
        mocker.patch(f"{AGENT_PIPE_MODULE}.Pipelex.teardown_if_needed")

    def test_agent_validate_all_dry_run_failure_is_negative_verdict_exit_1(self, mocker: MockerFixture) -> None:
        # `validate --all` sweeps via validate_all_core → validate_current_library, which raises
        # DryRunError directly. A dry-run failure is a produced negative verdict → exit 1, NOT the
        # catch-all's no-verdict 2.
        self._patch_pipe_boot(mocker)
        mocker.patch(f"{AGENT_PIPE_MODULE}.validate_all_core", new=mocker.AsyncMock(side_effect=DryRunError("pipe dry-run failed")))
        with pytest.raises(typer.Exit) as exc_info:
            agent_validate_pipe_cmd(pipe_code=None, validate_all=True, output_format=CliOutputFormat.JSON)
        assert exc_info.value.exit_code == 1

    def test_agent_validate_pipe_dry_run_failure_is_negative_verdict_exit_1(self, mocker: MockerFixture) -> None:
        # Single-pipe validate_pipe_core sweeps via validate_pipes, which raises DryRunError directly.
        self._patch_pipe_boot(mocker)
        mocker.patch(f"{AGENT_PIPE_MODULE}.resolve_pipe_from_exports", new=mocker.Mock(return_value=[]))
        mocker.patch(f"{AGENT_PIPE_MODULE}.validate_pipe_core", new=mocker.AsyncMock(side_effect=DryRunError("pipe dry-run failed")))
        with pytest.raises(typer.Exit) as exc_info:
            agent_validate_pipe_cmd(pipe_code="my_pipe", output_format=CliOutputFormat.JSON)
        assert exc_info.value.exit_code == 1
