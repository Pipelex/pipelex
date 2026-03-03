"""Tests for the pipelex login command."""

from __future__ import annotations

import http.client
import threading
from functools import partial
from http.server import HTTPServer
from io import StringIO
from typing import TYPE_CHECKING

from rich.console import Console

from pipelex.cli.commands.init.credentials import read_env_file, write_env_file
from pipelex.cli.commands.login.command import (
    PIPELEX_GATEWAY_API_KEY_VAR,
    CallbackHandler,
    login_cmd,
    save_api_key,
)

if TYPE_CHECKING:
    from pathlib import Path

    from pytest_mock import MockerFixture


class TestLoginCommand:
    def test_callback_handler_extracts_api_key(self) -> None:
        """The callback handler extracts the api_key param and stores it in result."""
        result: dict[str, str | None] = {"api_key": None}
        handler_cls = partial(CallbackHandler, result)
        server = HTTPServer(("127.0.0.1", 0), handler_cls)  # type: ignore[arg-type]
        port = server.server_address[1]

        server_thread = threading.Thread(target=server.handle_request, daemon=True)
        server_thread.start()

        conn = http.client.HTTPConnection("127.0.0.1", port)
        conn.request("GET", "/callback?api_key=test-key-12345")
        response = conn.getresponse()
        conn.close()
        server_thread.join(timeout=5)
        server.server_close()

        assert response.status == 200
        assert result["api_key"] == "test-key-12345"

    def test_callback_handler_returns_400_without_key(self) -> None:
        """The callback handler returns 400 when api_key param is missing."""
        result: dict[str, str | None] = {"api_key": None}
        handler_cls = partial(CallbackHandler, result)
        server = HTTPServer(("127.0.0.1", 0), handler_cls)  # type: ignore[arg-type]
        port = server.server_address[1]

        server_thread = threading.Thread(target=server.handle_request, daemon=True)
        server_thread.start()

        conn = http.client.HTTPConnection("127.0.0.1", port)
        conn.request("GET", "/callback")
        response = conn.getresponse()
        conn.close()
        server_thread.join(timeout=5)
        server.server_close()

        assert response.status == 400
        assert result["api_key"] is None

    def test_callback_handler_returns_400_for_wrong_path(self) -> None:
        """The callback handler returns 400 for paths other than /callback."""
        result: dict[str, str | None] = {"api_key": None}
        handler_cls = partial(CallbackHandler, result)
        server = HTTPServer(("127.0.0.1", 0), handler_cls)  # type: ignore[arg-type]
        port = server.server_address[1]

        server_thread = threading.Thread(target=server.handle_request, daemon=True)
        server_thread.start()

        conn = http.client.HTTPConnection("127.0.0.1", port)
        conn.request("GET", "/other?api_key=test-key")
        response = conn.getresponse()
        conn.close()
        server_thread.join(timeout=5)
        server.server_close()

        assert response.status == 400
        assert result["api_key"] is None

    def testsave_api_key_creates_env_file(self, tmp_path: Path, mocker: MockerFixture) -> None:
        """save_api_key writes the key to ~/.pipelex/.env."""
        env_path = tmp_path / ".env"
        mocker.patch(
            "pipelex.cli.commands.login.command.get_global_env_path",
            return_value=env_path,
        )
        save_api_key("pk_live_test123")

        entries = read_env_file(env_path)
        assert entries[PIPELEX_GATEWAY_API_KEY_VAR] == "pk_live_test123"

    def testsave_api_key_preserves_existing_entries(self, tmp_path: Path, mocker: MockerFixture) -> None:
        """save_api_key preserves existing .env entries when adding the API key."""
        env_path = tmp_path / ".env"
        write_env_file(env_path, {"EXISTING_KEY": "existing_value"})

        mocker.patch(
            "pipelex.cli.commands.login.command.get_global_env_path",
            return_value=env_path,
        )
        save_api_key("pk_live_test456")

        entries = read_env_file(env_path)
        assert entries["EXISTING_KEY"] == "existing_value"
        assert entries[PIPELEX_GATEWAY_API_KEY_VAR] == "pk_live_test456"

    def testsave_api_key_updates_existing_key(self, tmp_path: Path, mocker: MockerFixture) -> None:
        """save_api_key overwrites an existing PIPELEX_GATEWAY_API_KEY."""
        env_path = tmp_path / ".env"
        write_env_file(env_path, {PIPELEX_GATEWAY_API_KEY_VAR: "old_key"})

        mocker.patch(
            "pipelex.cli.commands.login.command.get_global_env_path",
            return_value=env_path,
        )
        save_api_key("new_key")

        entries = read_env_file(env_path)
        assert entries[PIPELEX_GATEWAY_API_KEY_VAR] == "new_key"

    def test_login_cmd_stdout_never_contains_api_key(self, tmp_path: Path, mocker: MockerFixture) -> None:
        """login_cmd never prints the API key to stdout."""
        env_path = tmp_path / ".env"
        mocker.patch(
            "pipelex.cli.commands.login.command.get_global_env_path",
            return_value=env_path,
        )

        output = StringIO()
        mock_console = Console(file=output)
        mocker.patch("pipelex.cli.commands.login.command.get_console", return_value=mock_console)
        mocker.patch("pipelex.cli.commands.login.command.webbrowser.open")

        # Mock serve_until_callback to immediately set the api_key in login_cmd's own result dict
        def fake_serve(_server: object, result: dict[str, str | None]) -> None:
            result["api_key"] = "secret_key_12345"

        mocker.patch("pipelex.cli.commands.login.command.serve_until_callback", side_effect=fake_serve)

        login_cmd()

        printed = output.getvalue()
        assert "secret_key_12345" not in printed
