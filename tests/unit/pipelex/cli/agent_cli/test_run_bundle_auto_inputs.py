"""Unit tests for agent CLI `run bundle <dir>` inputs auto-detection (inputs.json / inputs.toml)."""

from __future__ import annotations

import io
import json
from typing import TYPE_CHECKING, Any

import pytest
import typer

from pipelex.cli.agent_cli.commands.agent_output import CliOutputFormat, set_agent_cli_error_format
from pipelex.cli.agent_cli.commands.run.bundle_cmd import run_bundle_cmd

if TYPE_CHECKING:
    from pathlib import Path

    from pytest_mock import MockerFixture

RUN_BUNDLE_MODULE = "pipelex.cli.agent_cli.commands.run.bundle_cmd"


class TestAgentRunBundleAutoInputs:
    @pytest.fixture
    def bundle_dir(self, tmp_path: Path) -> Path:
        """A pipeline directory holding a default bundle file (never interpreted: --pipe is passed)."""
        (tmp_path / "bundle.mthds").write_text("# bundle\n", encoding="utf-8")
        return tmp_path

    @pytest.fixture
    def tty_stdin(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Make stdin look like a TTY so parse_cli_inputs skips the stdin fallback."""
        mock_stdin = io.StringIO("")
        mock_stdin.isatty = lambda: True  # type: ignore[assignment]
        monkeypatch.setattr("sys.stdin", mock_stdin)

    def _patch_run(self, mocker: MockerFixture, result: dict[str, Any]) -> Any:
        """Patch the run bundle command's runner dependencies; return the run_pipeline_core mock."""
        mocker.patch(f"{RUN_BUNDLE_MODULE}.make_pipelex_for_agent_cli")
        mocker.patch(f"{RUN_BUNDLE_MODULE}.Pipelex.teardown_if_needed")
        return mocker.patch(f"{RUN_BUNDLE_MODULE}.run_pipeline_core", new=mocker.AsyncMock(return_value=result))

    @pytest.mark.usefixtures("tty_stdin")
    def test_auto_detects_inputs_toml(self, mocker: MockerFixture, bundle_dir: Path, capsys: pytest.CaptureFixture[str]) -> None:
        """With only inputs.toml in the directory, it is auto-detected and loaded through the TOML parser."""
        run_core_mock = self._patch_run(mocker, {"answer": "42"})
        (bundle_dir / "inputs.toml").write_text('topic = "cats"\n', encoding="utf-8")

        run_bundle_cmd(path=str(bundle_dir), pipe="my_pipe", output_format=CliOutputFormat.JSON)

        capsys.readouterr()
        assert run_core_mock.call_args.kwargs["inputs"] == {"topic": "cats"}

    @pytest.mark.usefixtures("tty_stdin")
    def test_both_inputs_files_error_envelope(self, mocker: MockerFixture, bundle_dir: Path, capsys: pytest.CaptureFixture[str]) -> None:
        """With both default inputs files present, the command emits the ambiguity envelope and exits."""
        set_agent_cli_error_format(CliOutputFormat.JSON)
        run_core_mock = self._patch_run(mocker, {"answer": "42"})
        (bundle_dir / "inputs.json").write_text('{"topic": "cats"}', encoding="utf-8")
        (bundle_dir / "inputs.toml").write_text('topic = "cats"\n', encoding="utf-8")

        with pytest.raises(typer.Exit) as exc_info:
            run_bundle_cmd(path=str(bundle_dir), pipe="my_pipe", output_format=CliOutputFormat.JSON)

        assert exc_info.value.exit_code == 1
        envelope = json.loads(capsys.readouterr().err)
        assert envelope["error_type"] == "AmbiguousInputsFilesError"
        assert envelope["error_domain"] == "input"
        assert "--inputs" in envelope["hint"]
        run_core_mock.assert_not_called()

    def test_piped_stdin_preempts_ambiguous_auto_detect(
        self, mocker: MockerFixture, bundle_dir: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Piped stdin supplies inputs and outranks auto-detect, so an ambiguous dir does NOT error."""
        set_agent_cli_error_format(CliOutputFormat.JSON)
        run_core_mock = self._patch_run(mocker, {"answer": "42"})
        (bundle_dir / "inputs.json").write_text('{"topic": "fromjson"}', encoding="utf-8")
        (bundle_dir / "inputs.toml").write_text('topic = "fromtoml"\n', encoding="utf-8")
        piped_stdin = io.StringIO('{"topic": "fromstdin"}')
        piped_stdin.isatty = lambda: False  # type: ignore[assignment]
        monkeypatch.setattr("sys.stdin", piped_stdin)

        run_bundle_cmd(path=str(bundle_dir), pipe="my_pipe", output_format=CliOutputFormat.JSON)

        capsys.readouterr()
        assert run_core_mock.call_args.kwargs["inputs"] == {"topic": "fromstdin"}

    @pytest.mark.usefixtures("tty_stdin")
    def test_explicit_inputs_bypasses_ambiguity(self, mocker: MockerFixture, bundle_dir: Path, capsys: pytest.CaptureFixture[str]) -> None:
        """An explicit --inputs skips the probe entirely, even with both default files present."""
        run_core_mock = self._patch_run(mocker, {"answer": "42"})
        (bundle_dir / "inputs.json").write_text('{"topic": "json"}', encoding="utf-8")
        (bundle_dir / "inputs.toml").write_text('topic = "toml"\n', encoding="utf-8")

        run_bundle_cmd(
            path=str(bundle_dir),
            pipe="my_pipe",
            inputs=str(bundle_dir / "inputs.toml"),
            output_format=CliOutputFormat.JSON,
        )

        capsys.readouterr()
        assert run_core_mock.call_args.kwargs["inputs"] == {"topic": "toml"}

    @pytest.mark.usefixtures("tty_stdin")
    def test_an_auto_detected_link_is_refused(self, mocker: MockerFixture, bundle_dir: Path, capsys: pytest.CaptureFixture[str]) -> None:
        """A link named inputs.json is never followed: the command emits the refusal envelope pointing to --inputs and runs nothing."""
        set_agent_cli_error_format(CliOutputFormat.JSON)
        run_core_mock = self._patch_run(mocker, {"answer": "42"})
        outside = bundle_dir.parent / f"{bundle_dir.name}-outside.json"
        outside.write_text('{"topic": "outside-sentinel"}', encoding="utf-8")
        # The folder ignores its inputs file, as a checked-out method may, so its tree never holds the link and the
        # auto-detection alone judges it.
        (bundle_dir / ".gitignore").write_text("inputs.json\n", encoding="utf-8")
        (bundle_dir / "inputs.json").symlink_to(outside)

        with pytest.raises(typer.Exit) as exc_info:
            run_bundle_cmd(path=str(bundle_dir), pipe="my_pipe", output_format=CliOutputFormat.JSON)

        assert exc_info.value.exit_code == 1
        envelope = json.loads(capsys.readouterr().err)
        assert envelope["error_type"] == "AutoDetectedInputsFileError"
        assert envelope["error_domain"] == "input"
        assert "symbolic link" in envelope["message"]
        assert "--inputs" in envelope["hint"]
        assert "outside-sentinel" not in json.dumps(envelope)
        run_core_mock.assert_not_called()

    @pytest.mark.usefixtures("tty_stdin")
    def test_an_explicit_inputs_link_is_followed(self, mocker: MockerFixture, bundle_dir: Path, capsys: pytest.CaptureFixture[str]) -> None:
        """An inputs file the caller names with --inputs is read as given, through a link."""
        run_core_mock = self._patch_run(mocker, {"answer": "42"})
        outside = bundle_dir.parent / f"{bundle_dir.name}-outside.json"
        outside.write_text('{"topic": "outside-sentinel"}', encoding="utf-8")
        # The folder ignores its inputs file, as a checked-out method may, so its tree never holds the link and the
        # auto-detection alone judges it.
        (bundle_dir / ".gitignore").write_text("inputs.json\n", encoding="utf-8")
        link = bundle_dir / "inputs.json"
        link.symlink_to(outside)

        run_bundle_cmd(path=str(bundle_dir), pipe="my_pipe", inputs=str(link), output_format=CliOutputFormat.JSON)

        capsys.readouterr()
        assert run_core_mock.call_args.kwargs["inputs"] == {"topic": "outside-sentinel"}
