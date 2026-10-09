from __future__ import annotations

import io
from typing import TYPE_CHECKING

import pytest
from rich.console import Console

from pipelex.base_exceptions import PipelexError
from pipelex.cli.dev_cli.commands import generate_projection_corpus_cmd as corpus_mod
from pipelex.cli.dev_cli.commands import trace_input_semantics_cmd as trace_mod
from pipelex.pipeline.exceptions import ValidateBundleError

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path
    from types import ModuleType

    from pytest_mock import MockerFixture

#: Wide enough that no assertion below depends on where Rich decides to wrap.
CONSOLE_WIDTH = 400

#: A style tag Rich would apply and drop, and a closing tag its markup parser would refuse with a MarkupError.
BRACKETED_TEXT = "the [bold]compact[/bold] shape of list[int] ends at [/closing]"


def _corpus_cmd(*, bundle_paths: list[Path], output_dir: Path) -> None:
    corpus_mod.generate_projection_corpus_cmd(bundle_paths=bundle_paths, output_dir=output_dir)


def _trace_cmd(*, bundle_paths: list[Path], output_dir: Path) -> None:
    trace_mod.trace_input_semantics_cmd(bundle_paths=bundle_paths, output_dir=output_dir)


class TestDevCliFailurePrints:
    @pytest.fixture
    def console_buffer(self, mocker: MockerFixture) -> io.StringIO:
        """Route both command modules' consoles to one StringIO-backed console, and keep Pipelex from booting."""
        buffer = io.StringIO()
        console = Console(file=buffer, force_terminal=False, width=CONSOLE_WIDTH)
        for module in (corpus_mod, trace_mod):
            mocker.patch.object(module, "get_console", return_value=console)
            mocker.patch.object(module, "make_pipelex_for_cli")
            mocker.patch.object(module.Pipelex, "teardown_if_needed")
        return buffer

    @pytest.mark.parametrize(
        ("module", "run_command", "work_function_name", "failure", "heading"),
        [
            pytest.param(
                corpus_mod,
                _corpus_cmd,
                "generate_projection_corpus",
                ValidateBundleError(message=BRACKETED_TEXT),
                "Bundle validation failed — the corpus requires valid bundles:",
                id="corpus-validation",
            ),
            pytest.param(
                corpus_mod,
                _corpus_cmd,
                "generate_projection_corpus",
                ValueError(BRACKETED_TEXT),
                "The corpus's own record is out of date:",
                id="corpus-record",
            ),
            pytest.param(
                corpus_mod,
                _corpus_cmd,
                "generate_projection_corpus",
                PipelexError(BRACKETED_TEXT),
                "Corpus generation failed:",
                id="corpus-generation",
            ),
            pytest.param(
                trace_mod,
                _trace_cmd,
                "trace_input_semantics",
                ValidateBundleError(message=BRACKETED_TEXT),
                "Bundle validation failed — the trace requires a valid bundle:",
                id="trace-validation",
            ),
            pytest.param(
                trace_mod,
                _trace_cmd,
                "trace_input_semantics",
                PipelexError(BRACKETED_TEXT),
                "Trace failed:",
                id="trace-failure",
            ),
        ],
    )
    def test_a_failure_prints_its_bracketed_text_as_written(
        self,
        mocker: MockerFixture,
        console_buffer: io.StringIO,
        tmp_path: Path,
        module: ModuleType,
        run_command: Callable[..., None],
        work_function_name: str,
        failure: Exception,
        heading: str,
    ) -> None:
        """The failure's text follows its markup heading as written: no tag in it is applied, dropped or refused."""
        bundle_path = tmp_path / "bundle.mthds"
        bundle_path.write_text("", encoding="utf-8")
        mocker.patch.object(module, work_function_name, side_effect=failure)

        with pytest.raises(SystemExit) as exit_info:
            run_command(bundle_paths=[bundle_path], output_dir=tmp_path / "out")

        assert exit_info.value.code == 1
        assert console_buffer.getvalue() == f"{heading}\n{BRACKETED_TEXT}\n"

    @pytest.mark.parametrize("run_command", [pytest.param(_corpus_cmd, id="corpus"), pytest.param(_trace_cmd, id="trace")])
    def test_a_missing_bundle_is_named_with_its_brackets(self, console_buffer: io.StringIO, tmp_path: Path, run_command: Callable[..., None]) -> None:
        """A bundle path holding brackets is named as it stands when the file is missing."""
        missing_bundle = tmp_path / "[bold]draft[/bold]" / "bundle.mthds"

        with pytest.raises(SystemExit) as exit_info:
            run_command(bundle_paths=[missing_bundle], output_dir=tmp_path / "out")

        assert exit_info.value.code == 2
        assert console_buffer.getvalue() == f"Bundle file not found: {missing_bundle}\n"
