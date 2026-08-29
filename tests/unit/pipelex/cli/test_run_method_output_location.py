"""Unit tests: main CLI `run method` anchors a fetched method's default outputs outside the ephemeral clone."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

from pipelex.cli.commands.run.method_cmd import run_method_cmd

if TYPE_CHECKING:
    from pytest_mock import MockerFixture

RUN_METHOD_MODULE = "pipelex.cli.commands.run.method_cmd"


class TestRunMethodOutputLocation:
    """A fetched method's clone is deleted at process exit — default outputs must land somewhere durable."""

    def _patch_method_run(self, mocker: MockerFixture, *, method_dir: Path, fetched: bool) -> Any:
        """Patch method resolution and execution; return the execute_run mock."""
        method_mock = mocker.MagicMock()
        method_mock.path = method_dir
        method_mock.provenance = mocker.MagicMock() if fetched else None
        mocker.patch(
            f"{RUN_METHOD_MODULE}.resolve_method_target",
            return_value=("my_pipe", [str(method_dir)], method_mock),
        )
        return mocker.patch(f"{RUN_METHOD_MODULE}.execute_run")

    def test_fetched_method_defaults_output_to_cwd_results(self, mocker: MockerFixture, tmp_path: Path) -> None:
        """A fetched method (provenance set) defaults --output-dir to results/ under the caller's CWD, not the clone."""
        clone_dir = tmp_path / "mthds_remote_clone"
        execute_run_mock = self._patch_method_run(mocker, method_dir=clone_dir, fetched=True)

        run_method_cmd(name="github.com/test/remote-method")

        output_dir = Path(execute_run_mock.call_args.kwargs["output_dir"])
        assert output_dir == Path.cwd() / "results"
        assert not output_dir.is_relative_to(clone_dir)

    def test_installed_method_defaults_output_to_method_results(self, mocker: MockerFixture, tmp_path: Path) -> None:
        """An installed method (no provenance) keeps the results/ default inside its own directory."""
        execute_run_mock = self._patch_method_run(mocker, method_dir=tmp_path, fetched=False)

        run_method_cmd(name="my-method")

        assert execute_run_mock.call_args.kwargs["output_dir"] == str(tmp_path / "results")

    def test_explicit_output_dir_wins_for_fetched_method(self, mocker: MockerFixture, tmp_path: Path) -> None:
        """An explicit --output-dir is honored verbatim, fetched or not."""
        clone_dir = tmp_path / "mthds_remote_clone"
        execute_run_mock = self._patch_method_run(mocker, method_dir=clone_dir, fetched=True)

        run_method_cmd(name="github.com/test/remote-method", output_dir="custom_out")

        assert execute_run_mock.call_args.kwargs["output_dir"] == "custom_out"
