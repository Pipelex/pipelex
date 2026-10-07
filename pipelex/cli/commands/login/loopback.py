"""The one-shot loopback listener `pipelex login` waits on for the browser to hand back a Pipelex API key.

The listener binds `127.0.0.1` on a port the system picks and accepts one thing: `GET /callback` carrying an `api_key`
and the `state` value this login generated. Any other request is answered and ignored, and the wait goes on: a callback
whose `state` is missing or different did not come from the page this login opened (any page open in the browser can
send a request to a local port), so its key is discarded, never saved. The pages it serves tell the browser not to
cache them nor send them on as a referrer, since the callback's URL carries the key.
"""

import secrets
import socketserver
import time
from collections.abc import Callable
from enum import StrEnum
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, HTTPServer
from types import TracebackType
from typing import cast
from urllib.parse import parse_qs, urlsplit

from typing_extensions import Self, override

#: The interface the listener binds: the loopback address itself, not `localhost`, which can resolve elsewhere (RFC 8252 §7.3).
LOOPBACK_HOST = "127.0.0.1"
#: The one path the listener accepts.
CALLBACK_PATH = "/callback"
#: The query parameter carrying the key.
API_KEY_PARAM = "api_key"
#: The query parameter carrying the value this login generated, which the app echoes back.
STATE_PARAM = "state"
# How long one connection may take to send its request: a client that connects and sends nothing must not hold the
# listener past the login's own deadline.
_REQUEST_READ_TIMEOUT_SECONDS = 10

_PAGE_TEMPLATE = (
    "<!doctype html><html><head><meta charset='utf-8'><title>Pipelex login</title></head>"
    "<body style='font-family:system-ui,sans-serif;text-align:center;padding:60px'>"
    "<h1>{heading}</h1><p>{body}</p></body></html>"
)


def generate_state() -> str:
    """A fresh unguessable value for one login, which only the page this login opened can echo back."""
    return secrets.token_urlsafe(32)


class CallbackRefusal(StrEnum):
    """Why the listener turned a `/callback` request away."""

    STATE_MISMATCH = "state_mismatch"
    NO_API_KEY = "no_api_key"


#: Called with each refusal while the listener waits, so the terminal can say what the browser was told.
RefusalCallback = Callable[[CallbackRefusal], None]


class _LoopbackServer(HTTPServer):
    """The listener's socket server, holding what this login expects and what it received."""

    def __init__(self, *, expected_state: str) -> None:
        self.expected_state = expected_state
        self.api_key: str | None = None
        self.refusals: list[CallbackRefusal] = []
        super().__init__((LOOPBACK_HOST, 0), _CallbackHandler)

    @override
    def server_bind(self) -> None:
        # `HTTPServer.server_bind` resolves the host's fully qualified name, a reverse lookup that can stall for seconds
        # on some networks and tells a loopback listener nothing.
        socketserver.TCPServer.server_bind(self)
        self.server_name = LOOPBACK_HOST
        self.server_port = int(self.server_address[1])


class _CallbackHandler(BaseHTTPRequestHandler):
    """Answers each request the listener receives, recording a key only from a callback carrying this login's `state`."""

    timeout = _REQUEST_READ_TIMEOUT_SECONDS

    def do_GET(self) -> None:
        server = cast("_LoopbackServer", self.server)
        parsed = urlsplit(self.path)
        if parsed.path != CALLBACK_PATH:
            self._send_page(status=HTTPStatus.NOT_FOUND, heading="Not found", body="This address only answers the Pipelex login callback.")
            return
        params = parse_qs(parsed.query)
        states = params.get(STATE_PARAM, [])
        if len(states) != 1 or not secrets.compare_digest(states[0].encode(), server.expected_state.encode()):
            server.refusals.append(CallbackRefusal.STATE_MISMATCH)
            self._send_page(
                status=HTTPStatus.BAD_REQUEST,
                heading="Login refused",
                body="This sign-in did not come from the page pipelex login opened, so its key was discarded. Use the link your terminal printed.",
            )
            return
        api_keys = params.get(API_KEY_PARAM, [])
        if len(api_keys) != 1 or not api_keys[0]:
            server.refusals.append(CallbackRefusal.NO_API_KEY)
            self._send_page(
                status=HTTPStatus.BAD_REQUEST,
                heading="No key received",
                body="The sign-in came back without an API key. Try again from the link your terminal printed.",
            )
            return
        server.api_key = api_keys[0]
        self._send_page(
            status=HTTPStatus.OK,
            heading="Logged in",
            body="pipelex login received your key. You can close this tab and return to your terminal.",
        )

    def _send_page(self, *, status: HTTPStatus, heading: str, body: str) -> None:
        content = _PAGE_TEMPLATE.format(heading=heading, body=body).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(content)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(content)

    @override
    def log_message(self, format: str, *args: object) -> None:
        """Keep the listener silent: the default writes every request line, key included, to stderr."""


class LoopbackListener:
    """A one-shot listener on `127.0.0.1`, open from construction until `close()` or the end of a `with` block.

    Construct it, send the browser to a URL naming `port` and `state`, then `wait_for_api_key`.
    """

    def __init__(self) -> None:
        self.state = generate_state()
        self._server = _LoopbackServer(expected_state=self.state)

    @property
    def port(self) -> int:
        """The port the system gave the listener."""
        return self._server.server_port

    def wait_for_api_key(self, *, timeout_seconds: float, on_refusal: RefusalCallback | None = None) -> str | None:
        """Answer requests until a callback carrying this login's `state` hands over a key, or the time runs out.

        Args:
            timeout_seconds: How long to wait in all.
            on_refusal: Called with each refused callback, as it is refused.

        Returns:
            The key, or `None` when none arrived in time.
        """
        deadline = time.monotonic() + timeout_seconds
        while self._server.api_key is None:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return None
            self._server.timeout = remaining
            refusals_before = len(self._server.refusals)
            self._server.handle_request()
            if on_refusal is not None:
                for refusal in self._server.refusals[refusals_before:]:
                    on_refusal(refusal)
        return self._server.api_key

    def close(self) -> None:
        """Stop listening."""
        self._server.server_close()

    def __enter__(self) -> Self:
        return self

    def __exit__(self, exc_type: type[BaseException] | None, exc_value: BaseException | None, traceback: TracebackType | None) -> None:
        self.close()
