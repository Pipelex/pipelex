"""The `pipelex build structures` alias: thin delegation to `codegen types --target python-structures`.

The engine itself (crate loading, emission, stamping) is covered by the codegen unit tests; these
pin the alias wiring only — target mapping (file -> parent directory, directory -> itself), the
default output directory, and the missing-target exit code.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
import typer

from pipelex.cli.commands.build.structures_cmd import build_structures_command
from pipelex.codegen.emitters.target import CodegenTarget
from pipelex.pipeline.usage_stats_reporting import CodeGenerationReport
from pipelex.system.usage_stats.usage_stats_contract import UsageStatsCodegenArtifact

if TYPE_CHECKING:
    from pathlib import Path

    from pytest_mock import MockerFixture, MockType

MODULE = "pipelex.cli.commands.build.structures_cmd"


def _assert_reported_as_structures(*, delegate: MockType) -> None:
    """The alias reports its generation as the `structures` artifact, which `codegen types` does not."""
    generation_report = delegate.call_args.kwargs["generation_report"]
    assert isinstance(generation_report, CodeGenerationReport)
    assert generation_report.artifact == UsageStatsCodegenArtifact.STRUCTURES


class TestBuildStructuresAlias:
    def test_directory_target_delegates_with_default_output(self, mocker: MockerFixture, tmp_path: Path) -> None:
        delegate = mocker.patch(f"{MODULE}.generate_types")

        build_structures_command(target=str(tmp_path), output_dir=None, library_dir=None)

        _assert_reported_as_structures(delegate=delegate)
        delegate.assert_called_once_with(
            generation_report=mocker.ANY,
            target=CodegenTarget.PYTHON_STRUCTURES,
            paths=[tmp_path],
            output_dir=str(tmp_path / "structures"),
            library_dir=None,
        )

    def test_file_target_resolves_to_parent_directory(self, mocker: MockerFixture, tmp_path: Path) -> None:
        delegate = mocker.patch(f"{MODULE}.generate_types")
        bundle_file = tmp_path / "demo.mthds"
        bundle_file.write_text('domain = "demo"\n', encoding="utf-8")

        build_structures_command(target=str(bundle_file), output_dir=None, library_dir=None)

        _assert_reported_as_structures(delegate=delegate)
        delegate.assert_called_once_with(
            generation_report=mocker.ANY,
            target=CodegenTarget.PYTHON_STRUCTURES,
            paths=[tmp_path],
            output_dir=str(tmp_path / "structures"),
            library_dir=None,
        )

    def test_explicit_output_dir_and_library_dirs_pass_through(self, mocker: MockerFixture, tmp_path: Path) -> None:
        delegate = mocker.patch(f"{MODULE}.generate_types")
        shared_dir = tmp_path / "shared"
        shared_dir.mkdir()

        build_structures_command(target=str(tmp_path), output_dir=str(tmp_path / "generated"), library_dir=[str(shared_dir)])

        _assert_reported_as_structures(delegate=delegate)
        delegate.assert_called_once_with(
            generation_report=mocker.ANY,
            target=CodegenTarget.PYTHON_STRUCTURES,
            paths=[tmp_path],
            output_dir=str(tmp_path / "generated"),
            library_dir=[shared_dir],
        )

    def test_missing_target_is_no_verdict_exit_2(self, mocker: MockerFixture, tmp_path: Path) -> None:
        delegate = mocker.patch(f"{MODULE}.generate_types")

        with pytest.raises(typer.Exit) as exc_info:
            build_structures_command(target=str(tmp_path / "does_not_exist"), output_dir=None, library_dir=None)

        assert exc_info.value.exit_code == 2
        delegate.assert_not_called()
