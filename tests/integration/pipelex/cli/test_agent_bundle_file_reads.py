from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest
import typer
from mthds.method_tree.models import TreeLimits

from pipelex.cli.agent_cli.commands.agent_output import CliOutputFormat, set_agent_cli_error_format
from pipelex.cli.agent_cli.commands.fix.bundle_cmd import fix_bundle_cmd
from pipelex.cli.agent_cli.commands.inputs.bundle_cmd import inputs_bundle_cmd
from pipelex.cli.agent_cli.commands.run.bundle_cmd import run_bundle_cmd
from pipelex.cli.agent_cli.commands.validate.bundle_cmd import validate_bundle_cmd

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator

    from pytest_mock import MockerFixture

_BUNDLE = """domain = "greetings"
main_pipe = "say_hello"

[pipe.say_hello]
type = "PipeLLM"
description = "Say hello"
output = "Text"
prompt = "Say hello"
"""


def _validate(path: str) -> None:
    validate_bundle_cmd(path=path, output_format=CliOutputFormat.JSON, error_format=CliOutputFormat.JSON)


def _inputs(path: str) -> None:
    inputs_bundle_cmd(path=path, error_format=CliOutputFormat.JSON)


def _fix(path: str) -> None:
    fix_bundle_cmd(path=path, output_format=CliOutputFormat.JSON, error_format=CliOutputFormat.JSON)


def _run(path: str) -> None:
    run_bundle_cmd(path=path, output_format=CliOutputFormat.JSON, error_format=CliOutputFormat.JSON)


_COMMANDS: list[tuple[str, Callable[[str], None]]] = [
    ("validate", _validate),
    ("inputs", _inputs),
    ("fix", _fix),
    ("run", _run),
]


@pytest.fixture(autouse=True)
def no_boot(mocker: MockerFixture) -> Iterator[None]:
    """The suite's session boot owns the runtime, and no run reaches its pipeline."""
    for module in ("validate", "inputs", "fix", "run"):
        mocker.patch(f"pipelex.cli.agent_cli.commands.{module}.bundle_cmd.make_pipelex_for_agent_cli")
        mocker.patch(f"pipelex.cli.agent_cli.commands.{module}.bundle_cmd.Pipelex.teardown_if_needed")
    mocker.patch("pipelex.cli.agent_cli.commands.run.bundle_cmd.run_pipeline_core", new=mocker.AsyncMock(return_value={}))
    yield
    set_agent_cli_error_format(CliOutputFormat.JSON)


def _problem_of(*, command: Callable[[str], None], path: Path, capsys: pytest.CaptureFixture[str]) -> dict[str, Any]:
    with pytest.raises(typer.Exit):
        command(str(path))
    problem: dict[str, Any] = json.loads(capsys.readouterr().err)
    return problem


class TestAgentBundleFileReads:
    @pytest.mark.skipif(sys.platform == "win32" or os.geteuid() == 0, reason="needs a file permissions can keep this user from reading")
    @pytest.mark.parametrize(("name", "command"), _COMMANDS)
    def test_a_bundle_this_machine_cannot_read_is_the_file_s_refusal(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str], name: str, command: Callable[[str], None]
    ) -> None:
        """Every bundle command refuses a bundle file the system will not let it read as `client.file_unreadable`, naming it."""
        bundle_file = tmp_path / f"{name}.mthds"
        bundle_file.write_text(_BUNDLE, encoding="utf-8")
        bundle_file.chmod(0)
        try:
            problem = _problem_of(command=command, path=bundle_file, capsys=capsys)
        finally:
            bundle_file.chmod(0o600)

        assert problem["code"] == "client.file_unreadable"
        assert problem["params"]["reason"] == "permission denied"
        assert problem["params"]["path"].endswith(f"{name}.mthds")

    @pytest.mark.parametrize(("name", "command"), _COMMANDS)
    @pytest.mark.parametrize(
        ("content", "line", "column"),
        [
            # Not UTF-8 text: located at the first byte that does not decode.
            (b'domain = "caf\xe9"\n', 1, 14),
            # UTF-8 text that is not TOML.
            (b'domain = "greetings"\nmain_pipe =\n', 2, 12),
        ],
    )
    def test_a_bundle_that_does_not_parse_is_the_method_s_syntax_fault(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
        name: str,
        command: Callable[[str], None],
        content: bytes,
        line: int,
        column: int,
    ) -> None:
        """Every bundle command refuses a bundle file that does not parse as `validate` does: the invalid verdict, its item `method.syntax`."""
        bundle_file = tmp_path / f"{name}.mthds"
        bundle_file.write_bytes(content)

        problem = _problem_of(command=command, path=bundle_file, capsys=capsys)

        assert problem["code"] == "method.invalid"
        (item,) = problem["errors"]
        assert item["code"] == "method.syntax"
        assert item["location"]["line"] == line
        assert item["location"]["column"] == column


@pytest.fixture
def bundle_never_read(mocker: MockerFixture) -> None:
    """Fail the test as soon as a command reads a `.mthds` file whole: its tree's listing must refuse the file first."""
    real_read_bytes = Path.read_bytes

    def guarded_read_bytes(self: Path) -> bytes:
        if self.suffix == ".mthds":
            msg = f"The bundle file '{self}' was read whole before its tree was listed."
            raise AssertionError(msg)
        return real_read_bytes(self)

    mocker.patch.object(Path, "read_bytes", autospec=True, side_effect=guarded_read_bytes)


@pytest.mark.usefixtures("bundle_never_read")
class TestAgentRunBundleListsTheTreeFirst:
    def test_a_bundle_file_past_this_machine_s_limits_is_refused_unread(
        self, mocker: MockerFixture, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """`run bundle` lists a bundle file's tree before reading it, so a file past the limits is refused, never read whole."""
        mocker.patch("pipelex.libraries.method_tree_listing.local_tree_limits", return_value=TreeLimits(max_file_bytes=16))
        bundle_file = tmp_path / "run.mthds"
        bundle_file.write_text(_BUNDLE, encoding="utf-8")

        problem = _problem_of(command=_run, path=bundle_file, capsys=capsys)

        assert problem["code"] == "method.invalid"
        assert "interpreter.method_tree_limits" in problem["message"]

    @pytest.mark.skipif(sys.platform == "win32", reason="needs a FIFO")
    def test_a_fifo_named_as_the_bundle_file_is_refused_unread(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        """`run bundle` refuses a FIFO named as its bundle file from its tree's listing, rather than blocking on reading it."""
        fifo = tmp_path / "run.mthds"
        os.mkfifo(fifo)

        problem = _problem_of(command=_run, path=fifo, capsys=capsys)

        assert problem["code"] == "method.invalid"
        assert "neither a regular file nor a directory" in problem["message"]

    def test_a_bundle_file_that_does_not_exist_is_the_file_s_refusal(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        """A bundle file the listing finds missing is the file the command was handed, `client.file_unreadable`, not found."""
        missing = tmp_path / "run.mthds"

        problem = _problem_of(command=_run, path=missing, capsys=capsys)

        assert problem["code"] == "client.file_unreadable"
        assert problem["params"]["reason"] == "not found"
        assert problem["params"]["path"] == str(missing)


class TestAgentBundleSystemErrorsNamingNoFile:
    @pytest.mark.parametrize(
        ("command", "core_target"),
        [
            (_validate, "pipelex.cli.agent_cli.commands.validate.bundle_cmd.validate_bundle_core"),
            (_inputs, "pipelex.cli.agent_cli.commands.inputs.bundle_cmd.inputs_core"),
            (_fix, "pipelex.cli.agent_cli.commands.fix.bundle_cmd.fix_judged_target"),
        ],
    )
    @pytest.mark.parametrize(
        "system_error",
        [
            ConnectionRefusedError(61, "Connection refused"),
            TimeoutError("timed out"),
        ],
    )
    def test_a_system_error_naming_no_file_is_no_refusal_of_the_bundle(
        self,
        mocker: MockerFixture,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
        command: Callable[[str], None],
        core_target: str,
        system_error: OSError,
    ) -> None:
        """An `OSError` naming no file, met while the command ran, is the unexpected failure it is, never `client.file_unreadable`."""
        mocker.patch(core_target, new=mocker.AsyncMock(side_effect=system_error))
        bundle_file = tmp_path / "bundle.mthds"
        bundle_file.write_text(_BUNDLE, encoding="utf-8")

        problem = _problem_of(command=command, path=bundle_file, capsys=capsys)

        assert problem["code"] == "runtime.unexpected"
        assert problem["diagnostics"]["error_class"] == type(system_error).__name__
