"""Browser-based CLI authentication for Pipelex Gateway."""

from __future__ import annotations

import threading
import webbrowser
from functools import partial
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlparse

from typing_extensions import override

from pipelex.cli.commands.init.credentials import get_global_env_path, read_env_file, write_env_file
from pipelex.service_hub import get_console
from pipelex.urls import URLs

LOGIN_TIMEOUT_SECONDS = 120
PIPELEX_GATEWAY_API_KEY_VAR = "PIPELEX_GATEWAY_API_KEY"


class CallbackHandler(BaseHTTPRequestHandler):
    """HTTP handler that receives the API key callback from the browser."""

    def __init__(self, result: dict[str, str | None], *args: object, **kwargs: object) -> None:
        self._result = result
        super().__init__(*args, **kwargs)  # type: ignore[arg-type]

    def do_GET(self) -> None:  # pylint: disable=invalid-name
        """Handle GET /callback?api_key=xxx."""
        parsed = urlparse(self.path)
        params = parse_qs(parsed.query)
        api_key_list = params.get("api_key", [])

        if parsed.path == "/callback" and api_key_list:
            self._result["api_key"] = api_key_list[0]
            self._send_success_page()
        else:
            self._send_error_page()

    def _send_success_page(self) -> None:
        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.end_headers()
        html = (
            "<html><body style='font-family:system-ui;text-align:center;padding:60px'>"
            "<h1>Logged in successfully!</h1>"
            "<p>You can close this tab and return to your terminal.</p>"
            "</body></html>"
        )
        self.wfile.write(html.encode())

    def _send_error_page(self) -> None:
        self.send_response(400)
        self.send_header("Content-Type", "text/html")
        self.end_headers()
        html = (
            "<html><body style='font-family:system-ui;text-align:center;padding:60px'>"
            "<h1>Authentication failed</h1>"
            "<p>Missing API key parameter. Please try again.</p>"
            "</body></html>"
        )
        self.wfile.write(html.encode())

    @override
    def log_message(self, format: str, *args: object) -> None:
        """Suppress default HTTP server logging."""


def login_cmd() -> None:
    """Open the browser for Pipelex Gateway login and save the API key."""
    console = get_console()

    result: dict[str, str | None] = {"api_key": None}
    handler_cls = partial(CallbackHandler, result)

    server = HTTPServer(("127.0.0.1", 0), handler_cls)  # type: ignore[arg-type]
    port = server.server_address[1]

    auth_url = f"{URLs.app_cli_auth}?callback_port={port}"

    console.print("\n[bold]Opening browser for login...[/bold]")
    console.print(f"[dim]If it doesn't open, visit: {auth_url}[/dim]\n")

    webbrowser.open(auth_url)

    server.timeout = LOGIN_TIMEOUT_SECONDS
    server_thread = threading.Thread(target=serve_until_callback, args=(server,), kwargs={"result": result}, daemon=True)
    server_thread.start()
    server_thread.join(timeout=LOGIN_TIMEOUT_SECONDS)

    server.server_close()

    if result["api_key"]:
        save_api_key(result["api_key"])
        console.print("[bold green]Logged in successfully![/bold green]")
        console.print(f"[dim]API key saved to {get_global_env_path()}[/dim]\n")
    else:
        console.print("[bold red]Login timed out.[/bold red]")
        console.print(f"[dim]No response received within {LOGIN_TIMEOUT_SECONDS}s.[/dim]")
        console.print("[dim]You can try again with: pipelex login[/dim]")
        console.print(f"[dim]Or visit {URLs.app_cli_auth} to generate your API key manually.[/dim]\n")
        raise SystemExit(1)


def serve_until_callback(server: HTTPServer, *, result: dict[str, str | None]) -> None:
    """Handle requests until we get the API key or timeout."""
    try:
        while result["api_key"] is None:
            server.handle_request()
    except OSError:
        # Socket closed by main thread after timeout — expected during shutdown.
        pass


def save_api_key(api_key: str) -> None:
    """Write the API key to ~/.pipelex/.env."""
    env_path = get_global_env_path()
    entries = read_env_file(env_path)
    entries[PIPELEX_GATEWAY_API_KEY_VAR] = api_key
    write_env_file(env_path, entries=entries)
