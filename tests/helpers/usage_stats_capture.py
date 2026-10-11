"""A capture server on loopback standing in for PostHog's `/batch/` endpoint, for the tests that send usage statistics.

It records every request's path and JSON body and answers each with the next status of its script, `200` once the
script is spent. Tests point `PIPELEX_USAGE_STATS_ENDPOINT` at its origin, the only override the client accepts.
"""

import json
import socket
import threading
import time
from collections.abc import Generator
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, NamedTuple, cast

from typing_extensions import override


class CapturedRequest(NamedTuple):
    path: str
    content_type: str | None
    body: dict[str, Any]


class CaptureServer:
    """What the server received, and the statuses it is left to answer with."""

    def __init__(self, *, origin: str, statuses: list[int]) -> None:
        self.origin = origin
        self.statuses = statuses
        self.requests: list[CapturedRequest] = []
        self.lock = threading.Lock()

    def next_status(self) -> int:
        with self.lock:
            return self.statuses.pop(0) if self.statuses else 200

    def record(self, *, request: CapturedRequest) -> None:
        with self.lock:
            self.requests.append(request)

    @property
    def events(self) -> list[dict[str, Any]]:
        """Every event every request carried, in the order received."""
        with self.lock:
            requests = list(self.requests)
        events: list[dict[str, Any]] = []
        for request in requests:
            events.extend(cast("list[dict[str, Any]]", request.body.get("batch", [])))
        return events


@contextmanager
def capture_server(*, statuses: list[int] | None = None) -> Generator[CaptureServer, None, None]:
    """Serve on `127.0.0.1` on a free port for the duration of the block."""
    server_state: CaptureServer | None = None

    class _Handler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:
            length = int(self.headers.get("Content-Length", "0"))
            raw_body = self.rfile.read(length)
            body = cast("dict[str, Any]", json.loads(raw_body.decode("utf-8")))
            assert server_state is not None
            server_state.record(request=CapturedRequest(path=self.path, content_type=self.headers.get("Content-Type"), body=body))
            status = server_state.next_status()
            self.send_response(status)
            self.send_header("Content-Length", "2")
            self.end_headers()
            self.wfile.write(b"{}")

        @override
        def log_message(self, format: str, *args: Any) -> None:
            return

    httpd = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    server_state = CaptureServer(origin=f"http://127.0.0.1:{httpd.server_address[1]}", statuses=list(statuses or []))
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        yield server_state
    finally:
        httpd.shutdown()
        httpd.server_close()
        thread.join(timeout=5)


#: The answer a trickling server sends, one byte at a time.
_TRICKLED_ANSWER = b"HTTP/1.1 200 OK\r\nContent-Length: 2\r\nConnection: close\r\n\r\n{}"


@contextmanager
def trickling_server(*, seconds_per_byte: float) -> Generator[str, None, None]:
    """Serve on `127.0.0.1` a server that reads a request and answers `200` one byte at a time; yield its origin.

    No socket operation of the client waits long enough to time out, so only a deadline on the whole exchange ends the
    request before the answer is complete.
    """
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.bind(("127.0.0.1", 0))
    listener.listen()
    listener.settimeout(0.1)
    stopping = threading.Event()

    def serve() -> None:
        while not stopping.is_set():
            try:
                connection, _ = listener.accept()
            except OSError:
                continue
            with connection:
                try:
                    connection.settimeout(5)
                    connection.recv(65536)
                    for byte in _TRICKLED_ANSWER:
                        if stopping.is_set():
                            break
                        connection.sendall(bytes([byte]))
                        time.sleep(seconds_per_byte)
                except OSError:
                    continue

    thread = threading.Thread(target=serve, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{listener.getsockname()[1]}"
    finally:
        stopping.set()
        thread.join(timeout=5)
        listener.close()
