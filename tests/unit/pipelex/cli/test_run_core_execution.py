"""Unit tests for the core `pipelex run` execution logic (_execute_run).

The runner (PipelexMTHDSProtocol) and the rendering collaborators are mocked at the
module namespace; file outputs are asserted on real tmp_path files. The traceback
behavior of the inner except blocks is covered by test_traceback_flag_run_core.py.
"""

from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any

import pytest
import typer
from rich.console import Console

from pipelex.cli.commands.run._run_core import _execute_run  # pyright: ignore[reportPrivateUsage]
from pipelex.core.concepts.exceptions import ConceptValueError
from pipelex.core.stuffs.list_content import ListContent
from pipelex.core.stuffs.number_content import NumberContent
from pipelex.core.stuffs.text_content import TextContent
from pipelex.libraries.exceptions import LibraryError

if TYPE_CHECKING:
    from collections.abc import Coroutine
    from pathlib import Path

    from pytest_mock import MockerFixture


def _run_async(coro: Coroutine[Any, Any, Any]) -> Any:
    return asyncio.run(coro)


def _call_execute_run(**overrides: Any) -> Coroutine[Any, Any, None]:
    kwargs: dict[str, Any] = {
        "pipe_code": "test_pipe",
        "bundle_path": None,
        "inputs": None,
        "save_working_memory": False,
        "working_memory_path": None,
        "save_main_stuff": False,
        "no_pretty_print": True,
        "graph": None,
        "graph_full_data": None,
        "output_dir": "temp/test_outputs",
        "dry_run": False,
        "mock_usage": False,
        "mock_inputs": False,
        "library_dir": None,
    }
    kwargs.update(overrides)
    return _execute_run(**kwargs)


class TestRunCoreExecution:
    @pytest.fixture
    def console(self, mocker: MockerFixture) -> Console:
        recorded_console = Console(width=200, record=True, color_system=None)
        mocker.patch("pipelex.cli.commands.run._run_core.get_console", return_value=recorded_console)
        return recorded_console

    @pytest.fixture
    def config_mock(self, mocker: MockerFixture) -> Any:
        fake_config = mocker.MagicMock()
        fake_config.interpreter.pipeline_execution.with_execution_overrides.return_value = mocker.MagicMock()
        mocker.patch("pipelex.cli.commands.run._run_core.get_config", return_value=fake_config)
        return fake_config

    def _mock_runner(self, mocker: MockerFixture, pipe_output: Any) -> Any:
        """Patch the protocol runner so execute() resolves to a response with pipe_output."""
        runner_mock = mocker.MagicMock()
        runner_mock.execute = mocker.AsyncMock(return_value=SimpleNamespace(pipe_output=pipe_output))
        runner_class_mock = mocker.patch("pipelex.cli.commands.run._run_core.PipelexMTHDSProtocol", return_value=runner_mock)
        mocker.patch("pipelex.cli.commands.run._run_core.render_cost_report_for_output")
        return runner_class_mock

    def _mock_structure_class(self, mocker: MockerFixture, *, resolves_to: Any = None, raises: Exception | None = None) -> SimpleNamespace:
        """Stand in for the throwaway library reload that resolves the CSV row class on an empty result.

        Returns the reload seams (``acquire``, ``clear``, ``manager``) so a test can assert the
        throwaway library was opened with the run's own load inputs and torn down again.
        """
        concept_library_mock = mocker.MagicMock()
        if raises is not None:
            concept_library_mock.get_structure_class.side_effect = raises
        else:
            concept_library_mock.get_structure_class.return_value = resolves_to
        acquire_mock = mocker.patch("pipelex.cli.commands.run._run_core.acquire_library", return_value=("reload-library", None))
        mocker.patch("pipelex.cli.commands.run._run_core.get_concept_library", return_value=concept_library_mock)
        clear_mock = mocker.patch("pipelex.cli.commands.run._run_core.clear_current_library")
        manager_mock = mocker.patch("pipelex.cli.commands.run._run_core.get_library_manager")
        return SimpleNamespace(acquire=acquire_mock, clear=clear_mock, manager=manager_mock)

    @staticmethod
    def _assert_reload_library_torn_down(reload: SimpleNamespace) -> None:
        reload.clear.assert_called_once_with()
        reload.manager.return_value.teardown.assert_called_once_with(library_id="reload-library")

    def _make_pipe_output(
        self,
        mocker: MockerFixture,
        main_stuff: Any | None = None,
        graph_spec: Any | None = None,
    ) -> Any:
        working_memory = mocker.MagicMock()
        working_memory.get_main_stuff.return_value = main_stuff
        working_memory.resolve_main_stuff.return_value = main_stuff
        working_memory.smart_dump.return_value = {"stuff": "dump"}
        return SimpleNamespace(
            main_stuff=main_stuff,
            graph_spec=graph_spec,
            working_memory=working_memory,
        )

    def _make_absent_main_pipe_output(self) -> Any:
        """A pipe output whose main output resolved absent (real WorkingMemory, recorded absence)."""
        from pipelex.core.memory.absence import AbsenceKind, AbsenceRecord  # ruff: ignore[import-outside-top-level]
        from pipelex.core.memory.working_memory import WorkingMemory  # ruff: ignore[import-outside-top-level]

        memory = WorkingMemory()
        memory.record_new_main_absence(
            AbsenceRecord(
                variable_name="summary",
                kind=AbsenceKind.SKIPPED,
                reason="skipped because input 'analysis' is absent",
                producing_pipe="summarize",
            )
        )
        return SimpleNamespace(graph_spec=None, working_memory=memory)

    @pytest.mark.usefixtures("config_mock")
    def test_absent_main_output_prints_absence_and_saves_artifact(self, mocker: MockerFixture, console: Console, tmp_path: Path) -> None:
        """An absent main output is a success: the recap prints the absence (no crash) and
        --save-main-stuff writes an explicit absence artifact, not value files.
        """
        pipe_output = self._make_absent_main_pipe_output()
        self._mock_runner(mocker, pipe_output)

        _run_async(
            _call_execute_run(
                no_pretty_print=False,
                save_main_stuff=True,
                output_dir=str(tmp_path),
            )
        )

        output = console.export_text()
        assert "Pipeline execution completed successfully" in output
        assert "resolved absent" in output
        assert "skipped because input 'analysis' is absent" in output

        output_dirs = list(tmp_path.glob("test_pipe_output*"))
        assert len(output_dirs) == 1
        absence_json = json.loads((output_dirs[0] / "main_stuff.json").read_text(encoding="utf-8"))
        assert absence_json["absent"] is True
        assert absence_json["variable_name"] == "summary"
        assert absence_json["reason"] == "skipped because input 'analysis' is absent"
        assert (output_dirs[0] / "main_stuff.md").exists()
        # Nothing to view: the interactive viewer is not produced for an absence.
        assert not (output_dirs[0] / "main_stuff_viewer.html").exists()

    @pytest.mark.usefixtures("config_mock")
    def test_happy_path_prints_recap(self, mocker: MockerFixture, console: Console) -> None:
        """A successful run prints the completion recap and passes the pipe code to the runner."""
        pipe_output = self._make_pipe_output(mocker)
        self._mock_runner(mocker, pipe_output)

        _run_async(_call_execute_run())

        output = console.export_text()
        assert "Pipeline execution completed successfully" in output
        assert "Output saved to" not in output

    @pytest.mark.usefixtures("config_mock")
    def test_dry_run_recap(self, mocker: MockerFixture, console: Console) -> None:
        """A dry run prints the dry-run recap."""
        pipe_output = self._make_pipe_output(mocker)
        self._mock_runner(mocker, pipe_output)

        _run_async(_call_execute_run(dry_run=True))

        assert "Dry run completed successfully" in console.export_text()

    @pytest.mark.usefixtures("config_mock", "console")
    def test_bundle_main_pipe_used_when_no_pipe_code(self, mocker: MockerFixture, tmp_path: Path) -> None:
        """Without --pipe, the bundle's main_pipe is resolved and executed."""
        bundle_file = tmp_path / "demo.mthds"
        bundle_file.write_text("# bundle content\n", encoding="utf-8")
        mocker.patch(
            "pipelex.cli.commands.run._run_core.MthdsParser.make_pipelex_bundle_blueprint",
            return_value=SimpleNamespace(main_pipe="bundle_main"),
        )
        pipe_output = self._make_pipe_output(mocker)
        runner_class_mock = self._mock_runner(mocker, pipe_output)

        _run_async(_call_execute_run(pipe_code=None, bundle_path=str(bundle_file)))

        execute_kwargs = runner_class_mock.return_value.execute.call_args.kwargs
        assert execute_kwargs["pipe_code"] == "bundle_main"
        assert execute_kwargs["mthds_contents"] == ["# bundle content\n"]

    @pytest.mark.usefixtures("config_mock", "console")
    def test_bundle_without_main_pipe_exits(self, mocker: MockerFixture, tmp_path: Path) -> None:
        """A bundle with no main_pipe and no --pipe is an error."""
        bundle_file = tmp_path / "demo.mthds"
        bundle_file.write_text("# bundle content\n", encoding="utf-8")
        mocker.patch(
            "pipelex.cli.commands.run._run_core.MthdsParser.make_pipelex_bundle_blueprint",
            return_value=SimpleNamespace(main_pipe=None),
        )

        with pytest.raises(typer.Exit) as exc_info:
            _run_async(_call_execute_run(pipe_code=None, bundle_path=str(bundle_file)))

        assert exc_info.value.exit_code == 1

    def test_no_pipe_code_and_no_bundle_exits(self) -> None:
        """Neither a pipe code nor a bundle is an immediate error."""
        with pytest.raises(typer.Exit) as exc_info:
            _run_async(_call_execute_run(pipe_code=None, bundle_path=None))

        assert exc_info.value.exit_code == 1

    @pytest.mark.usefixtures("config_mock", "console")
    def test_inline_json_inputs_passed_to_runner(self, mocker: MockerFixture) -> None:
        """Inline JSON inputs are parsed and forwarded to the runner."""
        pipe_output = self._make_pipe_output(mocker)
        runner_class_mock = self._mock_runner(mocker, pipe_output)

        _run_async(_call_execute_run(inputs='{"topic": "cats"}'))

        execute_kwargs = runner_class_mock.return_value.execute.call_args.kwargs
        assert execute_kwargs["inputs"] == {"topic": "cats"}

    @pytest.mark.usefixtures("config_mock", "console")
    def test_file_inputs_loaded_and_resolved(self, mocker: MockerFixture, tmp_path: Path) -> None:
        """File inputs are loaded and run through the path resolver."""
        inputs_file = tmp_path / "inputs.json"
        inputs_file.write_text(json.dumps({"topic": "dogs"}), encoding="utf-8")
        resolver_mock = mocker.patch(
            "pipelex.cli.commands.run._run_core.resolve_inputs_paths",
            return_value={"topic": "dogs", "resolved": True},
        )
        pipe_output = self._make_pipe_output(mocker)
        runner_class_mock = self._mock_runner(mocker, pipe_output)

        _run_async(_call_execute_run(inputs=str(inputs_file)))

        resolver_mock.assert_called_once_with({"topic": "dogs"}, base_dir=tmp_path.resolve())
        execute_kwargs = runner_class_mock.return_value.execute.call_args.kwargs
        assert execute_kwargs["inputs"] == {"topic": "dogs", "resolved": True}

    @pytest.mark.usefixtures("config_mock", "console")
    def test_file_inputs_thread_base_dir_to_runner(self, mocker: MockerFixture, tmp_path: Path) -> None:
        """File-loaded inputs hand the file's parent dir to the runner as inputs_base_dir (D3)."""
        inputs_file = tmp_path / "inputs.json"
        inputs_file.write_text(json.dumps({"photo": "photo.jpg"}), encoding="utf-8")
        pipe_output = self._make_pipe_output(mocker)
        runner_class_mock = self._mock_runner(mocker, pipe_output)

        _run_async(_call_execute_run(inputs=str(inputs_file)))

        ctor_kwargs = runner_class_mock.call_args.kwargs
        assert ctor_kwargs["inputs_base_dir"] == tmp_path.resolve()

    @pytest.mark.usefixtures("config_mock", "console")
    def test_inline_json_inputs_have_no_base_dir(self, mocker: MockerFixture) -> None:
        """Inline JSON inputs come from no file — the runner gets inputs_base_dir=None."""
        pipe_output = self._make_pipe_output(mocker)
        runner_class_mock = self._mock_runner(mocker, pipe_output)

        _run_async(_call_execute_run(inputs='{"topic": "cats"}'))

        ctor_kwargs = runner_class_mock.call_args.kwargs
        assert ctor_kwargs["inputs_base_dir"] is None

    @pytest.mark.usefixtures("console")
    def test_non_dict_input_file_exits(self, tmp_path: Path) -> None:
        """An input file holding a JSON list (not a dict) is rejected."""
        inputs_file = tmp_path / "inputs.json"
        inputs_file.write_text('["not", "a", "dict"]', encoding="utf-8")

        with pytest.raises(typer.Exit) as exc_info:
            _run_async(_call_execute_run(inputs=str(inputs_file)))

        assert exc_info.value.exit_code == 1

    @pytest.mark.usefixtures("config_mock", "console")
    def test_toml_file_inputs_loaded_and_resolved(self, mocker: MockerFixture, tmp_path: Path) -> None:
        """A .toml inputs file is loaded through the TOML parser and run through the path resolver."""
        inputs_file = tmp_path / "inputs.toml"
        inputs_file.write_text('[report]\nconcept = "Text"\ncontent = """\nLine one.\nLine two.\n"""\n', encoding="utf-8")
        loaded_inputs = {"report": {"concept": "Text", "content": "Line one.\nLine two.\n"}}
        resolver_mock = mocker.patch(
            "pipelex.cli.commands.run._run_core.resolve_inputs_paths",
            return_value={**loaded_inputs, "resolved": True},
        )
        pipe_output = self._make_pipe_output(mocker)
        runner_class_mock = self._mock_runner(mocker, pipe_output)

        _run_async(_call_execute_run(inputs=str(inputs_file)))

        resolver_mock.assert_called_once_with(loaded_inputs, base_dir=tmp_path.resolve())
        execute_kwargs = runner_class_mock.return_value.execute.call_args.kwargs
        assert execute_kwargs["inputs"] == {**loaded_inputs, "resolved": True}

    @pytest.mark.usefixtures("console")
    def test_toml_syntax_error_input_file_exits(self, tmp_path: Path) -> None:
        """A .toml inputs file with invalid TOML syntax is rejected cleanly."""
        inputs_file = tmp_path / "inputs.toml"
        inputs_file.write_text("topic = \n", encoding="utf-8")

        with pytest.raises(typer.Exit) as exc_info:
            _run_async(_call_execute_run(inputs=str(inputs_file)))

        assert exc_info.value.exit_code == 1

    @pytest.mark.usefixtures("console")
    def test_invalid_json_input_file_exits(self, tmp_path: Path) -> None:
        """A .json inputs file with invalid JSON syntax is rejected cleanly."""
        inputs_file = tmp_path / "inputs.json"
        inputs_file.write_text("{not valid json", encoding="utf-8")

        with pytest.raises(typer.Exit) as exc_info:
            _run_async(_call_execute_run(inputs=str(inputs_file)))

        assert exc_info.value.exit_code == 1

    @pytest.mark.usefixtures("config_mock")
    def test_graph_outputs_saved(self, mocker: MockerFixture, console: Console, tmp_path: Path) -> None:
        """A graph spec on the output triggers graph generation into the output dir."""
        pipe_output = self._make_pipe_output(mocker, graph_spec=mocker.MagicMock())
        self._mock_runner(mocker, pipe_output)
        mocker.patch("pipelex.cli.commands.run._run_core.generate_graph_outputs", new=mocker.AsyncMock(return_value=mocker.MagicMock()))
        save_graphs_mock = mocker.patch(
            "pipelex.cli.commands.run._run_core.save_graph_outputs_to_dir",
            return_value=["mermaidflow_html", "reactflow_html"],
        )

        _run_async(_call_execute_run(output_dir=str(tmp_path)))

        save_graphs_mock.assert_called_once()
        graph_output_dir = save_graphs_mock.call_args.kwargs["output_dir"]
        assert str(graph_output_dir).startswith(str(tmp_path))
        output = console.export_text()
        assert "graphs: mermaidflow, reactflow" in output

    @pytest.mark.usefixtures("config_mock")
    def test_main_stuff_saved_in_all_formats(self, mocker: MockerFixture, console: Console, tmp_path: Path) -> None:
        """--save-main-stuff writes JSON, Markdown, HTML and the viewer file."""
        main_stuff = mocker.MagicMock()
        main_stuff.content.rendered_json_async = mocker.AsyncMock(return_value='{"answer": 42}')
        main_stuff.content.rendered_markdown_async = mocker.AsyncMock(return_value="# answer 42")
        main_stuff.content.rendered_html_async = mocker.AsyncMock(return_value="<p>42</p>")
        mocker.patch("pipelex.cli.commands.run._run_core.render_stuff_viewer", new=mocker.AsyncMock(return_value="<html>viewer</html>"))
        pipe_output = self._make_pipe_output(mocker, main_stuff=main_stuff)
        self._mock_runner(mocker, pipe_output)

        _run_async(_call_execute_run(save_main_stuff=True, output_dir=str(tmp_path)))

        output_dirs = list(tmp_path.iterdir())
        assert len(output_dirs) == 1
        saved_dir = output_dirs[0]
        assert (saved_dir / "main_stuff.json").read_text(encoding="utf-8") == '{"answer": 42}'
        assert (saved_dir / "main_stuff.md").read_text(encoding="utf-8") == "# answer 42"
        assert (saved_dir / "main_stuff.html").read_text(encoding="utf-8") == "<p>42</p>"
        assert (saved_dir / "main_stuff_viewer.html").read_text(encoding="utf-8") == "<html>viewer</html>"
        assert "main_stuff: json, md, html, html_viewer" in console.export_text()

    @pytest.mark.usefixtures("config_mock")
    def test_working_memory_saved(self, mocker: MockerFixture, console: Console, tmp_path: Path) -> None:
        """--save-working-memory dumps the working memory as JSON in the output dir."""
        pipe_output = self._make_pipe_output(mocker)
        self._mock_runner(mocker, pipe_output)

        _run_async(_call_execute_run(save_working_memory=True, output_dir=str(tmp_path)))

        output_dirs = list(tmp_path.iterdir())
        assert len(output_dirs) == 1
        memory_file = output_dirs[0] / "working_memory.json"
        assert json.loads(memory_file.read_text(encoding="utf-8")) == {"stuff": "dump"}
        assert "working_memory.json" in console.export_text()

    @pytest.mark.usefixtures("config_mock")
    def test_working_memory_saved_to_explicit_path(self, mocker: MockerFixture, console: Console, tmp_path: Path) -> None:
        """An explicit --working-memory-path wins over the output dir default."""
        pipe_output = self._make_pipe_output(mocker)
        self._mock_runner(mocker, pipe_output)
        explicit_path = tmp_path / "custom_memory.json"

        _run_async(
            _call_execute_run(
                save_working_memory=True,
                working_memory_path=str(explicit_path),
                output_dir=str(tmp_path / "outputs"),
            )
        )

        assert json.loads(explicit_path.read_text(encoding="utf-8")) == {"stuff": "dump"}
        assert f"working_memory: {explicit_path}" in console.export_text()

    def test_save_csv_empty_path_fails_fast(self) -> None:
        """An empty --save-csv path fails before anything runs."""
        with pytest.raises(typer.Exit) as exc_info:
            _run_async(_call_execute_run(save_csv="   "))

        assert exc_info.value.exit_code == 1

    def test_save_csv_bad_suffix_fails_fast(self) -> None:
        """An unsupported table suffix fails before anything runs."""
        with pytest.raises(typer.Exit) as exc_info:
            _run_async(_call_execute_run(save_csv="out.xlsx"))

        assert exc_info.value.exit_code == 1

    @pytest.mark.usefixtures("config_mock", "console")
    def test_save_csv_non_list_output_exits(self, mocker: MockerFixture, tmp_path: Path) -> None:
        """--save-csv requires the main stuff to be a list."""
        main_stuff = mocker.MagicMock()
        main_stuff.content = TextContent(text="not a list")
        pipe_output = self._make_pipe_output(mocker, main_stuff=main_stuff)
        self._mock_runner(mocker, pipe_output)

        with pytest.raises(typer.Exit) as exc_info:
            _run_async(_call_execute_run(save_csv=str(tmp_path / "out.csv")))

        assert exc_info.value.exit_code == 1

    @pytest.mark.usefixtures("config_mock")
    def test_save_csv_happy_path(self, mocker: MockerFixture, console: Console, tmp_path: Path) -> None:
        """A flat list output is written through the CSV codec to the literal path."""
        main_stuff = mocker.MagicMock()
        main_stuff.content = ListContent(items=[TextContent(text="row one")])
        pipe_output = self._make_pipe_output(mocker, main_stuff=main_stuff)
        self._mock_runner(mocker, pipe_output)
        # The row model is taken off the produced rows, not resolved by name: the run library that
        # owned the generated structure class is already torn down by the time this step runs. Point
        # the name lookup at a different class so a regression to it fails here rather than silently.
        self._mock_structure_class(mocker, resolves_to=NumberContent)
        mocker.patch("pipelex.cli.commands.run._run_core.flat_field_names", return_value=["text"])
        csv_codec_mock = mocker.patch("pipelex.cli.commands.run._run_core.csv_from_list_content")
        csv_target = tmp_path / "reports" / "out.csv"

        _run_async(_call_execute_run(save_csv=str(csv_target)))

        csv_codec_mock.assert_called_once()
        assert csv_codec_mock.call_args.kwargs["path"] == csv_target
        assert csv_codec_mock.call_args.kwargs["row_model"] is TextContent
        assert csv_target.parent.is_dir()
        assert f"CSV saved to {csv_target}" in console.export_text()

    @pytest.mark.usefixtures("config_mock", "console")
    def test_save_csv_empty_result_resolves_the_row_model_by_reloading_the_bundle(self, mocker: MockerFixture, tmp_path: Path) -> None:
        """An empty result has no row to read the class off, so the declared concept is resolved instead.

        This is what keeps a run that produced no rows writing a correct header-only file: the run's
        own library (and the registry holding its generated structure classes) is already torn down.
        """
        main_stuff = mocker.MagicMock()
        main_stuff.content = ListContent[TextContent](items=[])
        pipe_output = self._make_pipe_output(mocker, main_stuff=main_stuff)
        self._mock_runner(mocker, pipe_output)
        reload = self._mock_structure_class(mocker, resolves_to=TextContent)
        mocker.patch("pipelex.cli.commands.run._run_core.flat_field_names", return_value=["text"])
        csv_codec_mock = mocker.patch("pipelex.cli.commands.run._run_core.csv_from_list_content")

        _run_async(_call_execute_run(save_csv=str(tmp_path / "out.csv"), library_dir=["libs"]))

        csv_codec_mock.assert_called_once()
        assert csv_codec_mock.call_args.kwargs["row_model"] is TextContent
        # The reload sees exactly the load inputs the run was handed, and is torn down again.
        assert reload.acquire.call_args.kwargs == {"library_id": "", "library_dirs": ["libs"], "mthds_contents": None, "bundle_uris": None}
        self._assert_reload_library_torn_down(reload)

    @pytest.mark.usefixtures("config_mock", "console")
    def test_save_csv_concept_error_framed_as_csv_failure(self, mocker: MockerFixture, tmp_path: Path) -> None:
        """A missing structure class on the output concept is a --save-csv failure.

        An empty result is the one case with no produced row to read the model off, so it is the
        case that still falls back to resolving the concept's structure class by name.
        """
        main_stuff = mocker.MagicMock()
        main_stuff.content = ListContent[TextContent](items=[])
        pipe_output = self._make_pipe_output(mocker, main_stuff=main_stuff)
        self._mock_runner(mocker, pipe_output)
        reload = self._mock_structure_class(mocker, raises=ConceptValueError("no structure class"))

        with pytest.raises(typer.Exit) as exc_info:
            _run_async(_call_execute_run(save_csv=str(tmp_path / "out.csv")))

        assert exc_info.value.exit_code == 1
        # The throwaway library does not outlive a failed resolution either.
        self._assert_reload_library_torn_down(reload)

    @pytest.mark.usefixtures("config_mock", "console")
    def test_save_csv_reload_failure_framed_as_csv_failure(self, mocker: MockerFixture, tmp_path: Path) -> None:
        """A bundle reload that fails on an empty result is a --save-csv failure, not a pipeline failure."""
        main_stuff = mocker.MagicMock()
        main_stuff.content = ListContent[TextContent](items=[])
        pipe_output = self._make_pipe_output(mocker, main_stuff=main_stuff)
        self._mock_runner(mocker, pipe_output)
        reload = self._mock_structure_class(mocker, resolves_to=TextContent)
        reload.acquire.side_effect = LibraryError("reload failed")

        with pytest.raises(typer.Exit) as exc_info:
            _run_async(_call_execute_run(save_csv=str(tmp_path / "out.csv")))

        assert exc_info.value.exit_code == 1
        # acquire_library owns its own load-failure teardown, so nothing was left for the helper to drop.
        reload.manager.return_value.teardown.assert_not_called()
