"""Unit tests: agent CLI `run method` anchors a fetched method's outputs outside the ephemeral clone."""

from __future__ import annotations

import io
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest
from mthds.runners.types import RunnerType

from pipelex.cli.agent_cli.commands.agent_output import CliOutputFormat
from pipelex.cli.agent_cli.commands.run.method_cmd import run_method_cmd

if TYPE_CHECKING:
    from pytest_mock import MockerFixture

RUN_METHOD_MODULE = "pipelex.cli.agent_cli.commands.run.method_cmd"


class TestAgentRunMethodOutputLocation:
    """A fetched method's clone is deleted at process exit — its run outputs must land somewhere durable."""

    @pytest.fixture
    def tty_stdin(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Make stdin look like a TTY so parse_cli_inputs skips the stdin fallback."""
        mock_stdin = io.StringIO("")
        mock_stdin.isatty = lambda: True  # type: ignore[assignment]
        monkeypatch.setattr("sys.stdin", mock_stdin)

    def _patch_method_run(self, mocker: MockerFixture, *, method_dir: Path, fetched: bool) -> Any:
        """Patch method resolution + runner dependencies; return the run_pipeline_core mock."""
        method_mock = mocker.MagicMock()
        method_mock.mthds_files = []
        method_mock.path = method_dir
        method_mock.provenance = mocker.MagicMock() if fetched else None
        mocker.patch(
            f"{RUN_METHOD_MODULE}.resolve_method_target",
            return_value=("my_pipe", [str(method_dir)], method_mock),
        )
        mocker.patch(f"{RUN_METHOD_MODULE}.make_pipelex_for_agent_cli")
        mocker.patch(f"{RUN_METHOD_MODULE}.Pipelex.teardown_if_needed")
        return mocker.patch(f"{RUN_METHOD_MODULE}.run_pipeline_core", new=mocker.AsyncMock(return_value={"answer": "42"}))

    def _make_ctx(self, mocker: MockerFixture) -> Any:
        ctx = mocker.MagicMock()
        ctx.obj = {"runner": RunnerType.PIPELEX}
        return ctx

    @pytest.mark.usefixtures("tty_stdin")
    def test_fetched_method_overrides_output_dir_to_cwd(self, mocker: MockerFixture, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        """A fetched method (provenance set) re-anchors run outputs under the caller's CWD, not the clone."""
        clone_dir = tmp_path / "mthds_remote_clone"
        run_core_mock = self._patch_method_run(mocker, method_dir=clone_dir, fetched=True)

        run_method_cmd(ctx=self._make_ctx(mocker), name="github.com/test/remote-method", output_format=CliOutputFormat.JSON)

        capsys.readouterr()
        override = run_core_mock.call_args.kwargs["output_dir_override"]
        assert override == Path.cwd() / "results"
        assert not override.is_relative_to(clone_dir)

    @pytest.mark.usefixtures("tty_stdin")
    def test_installed_method_keeps_bundle_adjacent_default(self, mocker: MockerFixture, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        """An installed method (no provenance) keeps the bundle-adjacent default: no override is passed."""
        run_core_mock = self._patch_method_run(mocker, method_dir=tmp_path, fetched=False)

        run_method_cmd(ctx=self._make_ctx(mocker), name="my-method", output_format=CliOutputFormat.JSON)

        capsys.readouterr()
        assert run_core_mock.call_args.kwargs["output_dir_override"] is None
