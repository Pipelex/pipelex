"""A real HTTP server on ``127.0.0.1``, which the fetch-guard tests aim the fetch helper at.

The tests reach it with no mock between the helper and the socket, because the property under
test is what the default path does when nobody passes anything. A ``MockTransport`` would
replace the guard and prove nothing about it.
"""

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import cast

from pytest_mock import MockerFixture
from typing_extensions import override

SECRET_BODY = b"internal-only-secret"
SECRET_PATH = "/secret"
REDIRECT_TO_LOCALHOST_PATH = "/redirect-to-localhost"

PROXY_ENV_VARS = ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy", "all_proxy")


class LoopbackServer(ThreadingHTTPServer):
    """A server on 127.0.0.1 that records the path of every request it answers."""

    hits: list[str]


class LoopbackHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        server = cast("LoopbackServer", self.server)
        server.hits.append(self.path)
        if self.path == SECRET_PATH:
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.send_header("Content-Length", str(len(SECRET_BODY)))
            self.end_headers()
            self.wfile.write(SECRET_BODY)
        elif self.path == REDIRECT_TO_LOCALHOST_PATH:
            self.send_response(302)
            self.send_header("Location", f"http://localhost:{server.server_port}{SECRET_PATH}")
            self.send_header("Content-Length", "0")
            self.end_headers()
        else:
            self.send_response(404)
            self.send_header("Content-Length", "0")
            self.end_headers()

    @override
    def log_message(self, format: str, *args: object) -> None:
        pass


def loopback_url(server: LoopbackServer, *, path: str) -> str:
    return f"http://127.0.0.1:{server.server_port}{path}"


def treat_only_the_localhost_name_as_private(mocker: MockerFixture) -> None:
    """Let the first hop to 127.0.0.1 through, so that a refusal can only come from a later hop.

    The rules are patched where the guard reads them: no literal IP counts as private, and the
    only disallowed host is the name ``localhost``, which the server's redirect points at.
    """

    def is_the_localhost_name(host: str) -> bool:
        return host.rstrip(".").lower() == "localhost"

    mocker.patch("pipelex.tools.network.ssrf_guard.is_disallowed_host", side_effect=is_the_localhost_name)
    mocker.patch("pipelex.tools.network.ssrf_guard.is_disallowed_ip", return_value=False)
