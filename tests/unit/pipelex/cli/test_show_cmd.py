"""Unit tests for the `pipelex show` report logic (pipelex/cli/commands/show_cmd.py).

Covers the do_* functions directly with mocked hub getters — the Typer wrappers
(arg parsing, --help) are owned by the conformance suite.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import TYPE_CHECKING, Any

import pytest
from rich.console import Console

from pipelex.base_exceptions import PipelexConfigError
from pipelex.cli.commands.show_cmd import do_list_pipes, do_show_backends, do_show_config, do_show_pipe
from pipelex.cli.exceptions import PipelexCLIError
from pipelex.tools.misc.exceptions import TomlError

if TYPE_CHECKING:
    from pathlib import Path

    from pytest_mock import MockerFixture


def _make_backend(name: str, enabled: bool, endpoint: str | None = None, model_count: int = 0) -> SimpleNamespace:
    return SimpleNamespace(
        name=name,
        enabled=enabled,
        endpoint=endpoint,
        model_specs={f"model_{model_index}": object() for model_index in range(model_count)},
    )


def _make_routing_profile(
    name: str = "standard",
    description: str | None = "The standard profile",
    default: str | None = "openai",
    routes: dict[str, str] | None = None,
) -> SimpleNamespace:
    return SimpleNamespace(name=name, description=description, default=default, routes=routes or {})


class TestShowCmd:
    @pytest.fixture
    def console(self, mocker: MockerFixture) -> Console:
        recorded_console = Console(width=120, record=True, color_system=None)
        mocker.patch("pipelex.cli.commands.show_cmd.get_console", return_value=recorded_console)
        return recorded_console

    @pytest.fixture
    def telemetry(self, mocker: MockerFixture) -> Any:
        telemetry_manager = mocker.Mock()
        mocker.patch("pipelex.cli.commands.show_cmd.get_telemetry_manager", return_value=telemetry_manager)
        return telemetry_manager

    def _mock_backend_setup(
        self,
        mocker: MockerFixture,
        backends: list[SimpleNamespace],
        routing_profile: SimpleNamespace,
    ) -> None:
        mocker.patch("pipelex.cli.commands.show_cmd.get_secrets_provider")
        models_manager = SimpleNamespace(
            inference_backend_library=SimpleNamespace(root={backend.name: backend for backend in backends}),
            routing_profile=routing_profile,
        )
        mocker.patch("pipelex.cli.commands.show_cmd.get_models_manager", return_value=models_manager)

    def test_do_show_config_pretty_prints_loaded_config(self, mocker: MockerFixture) -> None:
        """The loaded config is pretty-printed under the expected title."""
        fake_config = {"pipelex": "config"}
        mocked_manager = mocker.patch("pipelex.cli.commands.show_cmd.config_manager")
        mocked_manager.load_config.return_value = fake_config
        pretty_print_mock = mocker.patch("pipelex.cli.commands.show_cmd.pretty_print")

        do_show_config()

        pretty_print_mock.assert_called_once_with(fake_config, title="Pipelex configuration")

    def test_do_show_config_wraps_toml_error(self, mocker: MockerFixture) -> None:
        """A TOML load failure surfaces as PipelexConfigError with context."""
        mocked_manager = mocker.patch("pipelex.cli.commands.show_cmd.config_manager")
        mocked_manager.load_config.side_effect = TomlError(message="bad toml", doc="", pos=0, lineno=1, colno=1)

        with pytest.raises(PipelexConfigError, match="Error loading configuration: bad toml"):
            do_show_config()

    def test_do_list_pipes_tracks_pipe_count(self, mocker: MockerFixture, telemetry: Any) -> None:
        """Listing pipes delegates to the library and reports the count to telemetry."""
        pipe_library = mocker.Mock()
        pipe_library.pretty_list_pipes.return_value = 7
        mocker.patch("pipelex.cli.commands.show_cmd.get_pipe_library", return_value=pipe_library)

        do_list_pipes()

        pipe_library.pretty_list_pipes.assert_called_once()
        telemetry.track_event.assert_called_once()
        _, call_kwargs = telemetry.track_event.call_args
        assert call_kwargs["properties"] == {"nb_pipes": 7}

    def test_do_show_pipe_pretty_prints_pipe(self, mocker: MockerFixture, telemetry: Any) -> None:
        """Showing a pipe fetches it from the hub and pretty-prints it."""
        fake_pipe = SimpleNamespace(type="PipeLLM")
        get_required_entry_pipe_mock = mocker.patch("pipelex.cli.commands.show_cmd.get_required_entry_pipe", return_value=fake_pipe)
        pretty_print_mock = mocker.patch("pipelex.cli.commands.show_cmd.pretty_print")

        do_show_pipe(pipe_code="my_pipe")

        get_required_entry_pipe_mock.assert_called_once_with(pipe_code="my_pipe")
        pretty_print_mock.assert_called_once_with(fake_pipe, title="Pipe 'my_pipe'")
        telemetry.track_event.assert_called_once()

    def test_do_show_backends_no_backends(self, mocker: MockerFixture, console: Console, telemetry: Any) -> None:
        """An empty backend library prints a warning and stops."""
        self._mock_backend_setup(mocker, backends=[], routing_profile=_make_routing_profile())

        do_show_backends()

        output = console.export_text()
        assert "No backends configured." in output
        telemetry.track_event.assert_not_called()

    def test_do_show_backends_enabled_only_hides_disabled(self, mocker: MockerFixture, console: Console, telemetry: Any) -> None:
        """Default mode lists only enabled backends and hints at the hidden ones."""
        backends = [
            _make_backend("openai", enabled=True, endpoint="https://api.openai.com", model_count=2),
            _make_backend("anthropic", enabled=False, endpoint="https://api.anthropic.com", model_count=1),
        ]
        self._mock_backend_setup(mocker, backends=backends, routing_profile=_make_routing_profile(routes={"gpt-*": "openai"}))

        do_show_backends(show_all=False)

        output = console.export_text()
        assert "Enabled Backends" in output
        assert "openai" in output
        assert "https://api.openai.com" in output
        assert "anthropic" not in output.split("Active Routing Profile")[0]
        assert "1 disabled backend(s) hidden" in output
        assert "pipelex show backends --all" in output
        assert "Active Routing Profile: standard" in output
        assert "Default Backend: openai" in output
        assert "Routing Rules:" in output
        assert "gpt-*" in output
        telemetry.track_event.assert_called_once()
        _, call_kwargs = telemetry.track_event.call_args
        assert call_kwargs["properties"] == {"nb_backends": 2}

    @pytest.mark.usefixtures("telemetry")
    def test_do_show_backends_show_all_includes_status_column(self, mocker: MockerFixture, console: Console, tmp_path: Path) -> None:
        """--all loads the library leniently and shows Enabled/Disabled status."""
        backends = [
            _make_backend("openai", enabled=True, model_count=1),
            _make_backend("anthropic", enabled=False, model_count=1),
        ]
        mocker.patch("pipelex.cli.commands.show_cmd.get_secrets_provider")
        models_manager = SimpleNamespace(
            inference_backend_library=SimpleNamespace(root={}),
            routing_profile=_make_routing_profile(routes={}),
        )
        mocker.patch("pipelex.cli.commands.show_cmd.get_models_manager", return_value=models_manager)
        mocked_config_manager = mocker.patch("pipelex.cli.commands.show_cmd.config_manager")
        mocked_config_manager.backends_file_path = tmp_path / "backends.toml"
        mocked_config_manager.backends_dir_path = tmp_path / "backends"
        lenient_library = SimpleNamespace(root={backend.name: backend for backend in backends}, load=mocker.Mock())
        library_class_mock = mocker.patch("pipelex.cli.commands.show_cmd.InferenceBackendLibrary", return_value=lenient_library)

        do_show_backends(show_all=True)

        library_class_mock.assert_called_once()
        load_kwargs = lenient_library.load.call_args.kwargs
        assert load_kwargs["include_disabled"] is True
        assert load_kwargs["lenient"] is True
        output = console.export_text()
        assert "All Configured Backends" in output
        assert "Status" in output
        assert "Enabled" in output
        assert "Disabled" in output
        assert "anthropic" in output
        assert "disabled backend(s) hidden" not in output

    @pytest.mark.usefixtures("telemetry")
    def test_do_show_backends_no_routes_prints_placeholder(self, mocker: MockerFixture, console: Console) -> None:
        """A routing profile without rules prints the no-rules placeholder."""
        backends = [_make_backend("openai", enabled=True)]
        self._mock_backend_setup(mocker, backends=backends, routing_profile=_make_routing_profile(description=None, default=None, routes={}))

        do_show_backends()

        output = console.export_text()
        assert "No specific routing rules defined." in output
        assert "Default Backend:" not in output

    @pytest.mark.usefixtures("telemetry")
    def test_do_show_backends_markup_error_in_routing_profile(self, mocker: MockerFixture, console: Console) -> None:
        """Bad markup in routing profile data degrades to a warning, not a crash."""
        backends = [_make_backend("openai", enabled=True)]
        bad_profile = _make_routing_profile(name="bad[/bold]name", description=None, default=None, routes={})
        self._mock_backend_setup(mocker, backends=backends, routing_profile=bad_profile)

        do_show_backends()

        output = console.export_text()
        assert "Warning: Could not display routing profile information:" in output

    @pytest.mark.usefixtures("console")
    def test_do_show_backends_wraps_access_errors(self, mocker: MockerFixture) -> None:
        """Failures while accessing backend config surface as PipelexCLIError."""
        mocker.patch("pipelex.cli.commands.show_cmd.get_secrets_provider", side_effect=OSError("denied"))

        with pytest.raises(PipelexCLIError, match="Error accessing backend or routing configuration: denied"):
            do_show_backends()
