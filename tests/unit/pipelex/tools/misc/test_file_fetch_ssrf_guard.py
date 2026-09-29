"""The fetch helper refuses private destinations by default, on every hop, and every caller surfaces it.

These tests reach a real HTTP server on ``127.0.0.1`` with no mock between the helper and the
socket, because the property under test is what the default path does when nobody passes
anything. A ``MockTransport`` would replace the guard and prove nothing about it.
"""

import ast
import subprocess  # ruff: ignore[suspicious-subprocess-import]
import sys
import threading
from collections.abc import Awaitable, Callable, Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import cast

import pytest
from pytest_mock import MockerFixture
from typing_extensions import override

from pipelex.cogt.content_generation.generated_content_factory import GeneratedContentFactory
from pipelex.cogt.document.prompt_document import PromptDocumentUri
from pipelex.cogt.document.prompt_document_utils import prepare_prompt_document, prepare_prompt_document_as_base64
from pipelex.cogt.file.file_preparation_utils import prepare_file_from_uri
from pipelex.cogt.image.generated_image import GeneratedImageRawDetails
from pipelex.cogt.image.prompt_image import PromptImageUri
from pipelex.cogt.image.prompt_image_utils import prepare_prompt_image, prepare_prompt_image_as_base64
from pipelex.config import get_config
from pipelex.runtime_hub import RuntimeHub
from pipelex.tools.misc.file_fetch_utils import fetch_file_and_content_type_from_url_httpx, fetch_file_from_url_httpx
from pipelex.tools.network.exceptions import SsrfBlockedError
from pipelex.tools.storage.storage_provider_abstract import StorageProviderAbstract
from pipelex.tools.uri.uri_base64 import make_base64_url_from_any_uri, make_base64_url_from_http_url

SECRET_BODY = b"internal-only-secret"
SECRET_PATH = "/secret"
REDIRECT_TO_LOCALHOST_PATH = "/redirect-to-localhost"

FETCH_FUNCTION_NAMES = frozenset({"fetch_file_from_url_httpx", "fetch_file_and_content_type_from_url_httpx"})
PIPELEX_SOURCE_ROOT = Path(__file__).resolve().parents[5] / "pipelex"
FETCH_HELPER_SOURCE = PIPELEX_SOURCE_ROOT / "tools" / "misc" / "file_fetch_utils.py"

PROXY_ENV_VARS = ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy", "all_proxy")

#: Wall-clock bound on the import-closure subprocess, so a deadlock fails instead of hanging the suite.
SUBPROCESS_TIMEOUT_SECONDS = 300


class _LoopbackServer(ThreadingHTTPServer):
    """A server on 127.0.0.1 that records the path of every request it answers."""

    hits: list[str]


class _LoopbackHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        server = cast("_LoopbackServer", self.server)
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


@pytest.fixture
def loopback_server() -> Iterator[_LoopbackServer]:
    server = _LoopbackServer(("127.0.0.1", 0), _LoopbackHandler)
    server.hits = []
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield server
    server.shutdown()
    server.server_close()
    thread.join()


def _loopback_url(server: _LoopbackServer, *, path: str) -> str:
    return f"http://127.0.0.1:{server.server_port}{path}"


def _treat_only_the_localhost_name_as_private(mocker: MockerFixture) -> None:
    """Let the first hop to 127.0.0.1 through, so that a refusal can only come from a later hop.

    The rules are patched where the guard reads them: no literal IP counts as private, and the
    only disallowed host is the name ``localhost``, which the server's redirect points at.
    """

    def is_the_localhost_name(host: str) -> bool:
        return host.rstrip(".").lower() == "localhost"

    mocker.patch("pipelex.tools.network.ssrf_guard.is_disallowed_host", side_effect=is_the_localhost_name)
    mocker.patch("pipelex.tools.network.ssrf_guard.is_disallowed_ip", return_value=False)


@pytest.mark.asyncio(loop_scope="class")
class TestFetchIsGuardedByDefault:
    async def test_a_loopback_url_is_refused_before_any_request(self, loopback_server: _LoopbackServer) -> None:
        with pytest.raises(SsrfBlockedError) as exc_info:
            await fetch_file_from_url_httpx(url=_loopback_url(loopback_server, path=SECRET_PATH))

        assert exc_info.type is SsrfBlockedError
        assert loopback_server.hits == []

    async def test_the_content_type_variant_is_guarded_too(self, loopback_server: _LoopbackServer) -> None:
        with pytest.raises(SsrfBlockedError):
            await fetch_file_and_content_type_from_url_httpx(_loopback_url(loopback_server, path=SECRET_PATH))

        assert loopback_server.hits == []

    async def test_a_process_with_no_config_loaded_is_guarded(self, mocker: MockerFixture, loopback_server: _LoopbackServer) -> None:
        mocker.patch.object(RuntimeHub, "_instance", None)

        with pytest.raises(SsrfBlockedError):
            await fetch_file_from_url_httpx(url=_loopback_url(loopback_server, path=SECRET_PATH))

        assert loopback_server.hits == []


@pytest.mark.asyncio(loop_scope="class")
class TestEveryRedirectHopIsVetted:
    async def test_a_first_hop_the_rules_allow_is_fetched(self, mocker: MockerFixture, loopback_server: _LoopbackServer) -> None:
        """The control for the next test: under the patched rules, the loopback server itself is reachable."""
        _treat_only_the_localhost_name_as_private(mocker)

        raw_bytes = await fetch_file_from_url_httpx(url=_loopback_url(loopback_server, path=SECRET_PATH))

        assert raw_bytes == SECRET_BODY

    async def test_a_redirect_to_a_private_destination_is_refused(self, mocker: MockerFixture, loopback_server: _LoopbackServer) -> None:
        _treat_only_the_localhost_name_as_private(mocker)

        with pytest.raises(SsrfBlockedError, match="localhost"):
            await fetch_file_from_url_httpx(url=_loopback_url(loopback_server, path=REDIRECT_TO_LOCALHOST_PATH))

        assert loopback_server.hits == [REDIRECT_TO_LOCALHOST_PATH]


@pytest.mark.asyncio(loop_scope="class")
class TestTheSwitchTurnsTheGuardOff:
    async def test_switch_off_fetches_a_loopback_url(
        self,
        mocker: MockerFixture,
        monkeypatch: pytest.MonkeyPatch,
        loopback_server: _LoopbackServer,
    ) -> None:
        mocker.patch.object(get_config().runtime.network, "is_fetch_ssrf_guard_enabled", False)
        for env_var in PROXY_ENV_VARS:
            monkeypatch.delenv(env_var, raising=False)

        raw_bytes = await fetch_file_from_url_httpx(url=_loopback_url(loopback_server, path=SECRET_PATH))

        assert raw_bytes == SECRET_BODY

    async def test_switch_off_follows_redirects_unvetted(
        self,
        mocker: MockerFixture,
        monkeypatch: pytest.MonkeyPatch,
        loopback_server: _LoopbackServer,
    ) -> None:
        mocker.patch.object(get_config().runtime.network, "is_fetch_ssrf_guard_enabled", False)
        for env_var in PROXY_ENV_VARS:
            monkeypatch.delenv(env_var, raising=False)

        raw_bytes = await fetch_file_from_url_httpx(url=_loopback_url(loopback_server, path=REDIRECT_TO_LOCALHOST_PATH))

        assert raw_bytes == SECRET_BODY


#: Every production entry point that fetches a value's URL, called the way its callers call it.
FETCHING_CALLERS: list[tuple[str, Callable[[str], Awaitable[object]]]] = [
    ("prepare_prompt_image", lambda url: prepare_prompt_image(PromptImageUri(uri=url), is_http_url_enabled=False)),
    ("prepare_prompt_image_as_base64", lambda url: prepare_prompt_image_as_base64(PromptImageUri(uri=url))),
    ("prepare_prompt_document", lambda url: prepare_prompt_document(PromptDocumentUri(uri=url), is_http_url_enabled=False)),
    ("prepare_prompt_document_as_base64", lambda url: prepare_prompt_document_as_base64(PromptDocumentUri(uri=url))),
    ("prepare_file_from_uri", lambda url: prepare_file_from_uri(url, keep_http_url=False, keep_local_path=False)),
    ("make_base64_url_from_any_uri", make_base64_url_from_any_uri),
    ("make_base64_url_from_http_url", make_base64_url_from_http_url),
]


@pytest.mark.asyncio(loop_scope="class")
class TestCallersSurfaceTheRefusal:
    """No caller absorbs the refusal into a fallback: it reaches the pipe as `SsrfBlockedError`."""

    @pytest.mark.parametrize(
        "call",
        [pytest.param(call, id=caller_name) for caller_name, call in FETCHING_CALLERS],
    )
    async def test_caller_raises_the_refusal(self, loopback_server: _LoopbackServer, call: Callable[[str], Awaitable[object]]) -> None:
        with pytest.raises(SsrfBlockedError) as exc_info:
            await call(_loopback_url(loopback_server, path=SECRET_PATH))

        assert exc_info.type is SsrfBlockedError
        assert loopback_server.hits == []

    async def test_a_generated_image_url_on_a_private_address_fails_instead_of_degrading(
        self,
        mocker: MockerFixture,
        loopback_server: _LoopbackServer,
    ) -> None:
        mocker.patch.object(get_config().runtime.storage, "is_fetch_remote_content_enabled", True)
        storage_provider = mocker.MagicMock(spec=StorageProviderAbstract)
        storage_provider.store = mocker.AsyncMock(return_value="pipelex-storage://stored-uri")
        factory = GeneratedContentFactory(storage_provider=storage_provider)

        with pytest.raises(SsrfBlockedError):
            await factory.make_image_content(
                storage_scope="test/scope",
                raw_details=GeneratedImageRawDetails(size=None, actual_url=_loopback_url(loopback_server, path=SECRET_PATH)),
            )

        assert loopback_server.hits == []
        storage_provider.store.assert_not_awaited()


def _fetch_calls_passing_transport(source_path: Path) -> tuple[int, list[str]]:
    """Count the calls to the fetch helpers in ``source_path``, and list those passing ``transport``."""
    tree = ast.parse(source_path.read_text(encoding="utf-8"), filename=str(source_path))
    nb_fetch_calls = 0
    offenders: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        func_name = func.id if isinstance(func, ast.Name) else func.attr if isinstance(func, ast.Attribute) else None
        if func_name not in FETCH_FUNCTION_NAMES:
            continue
        nb_fetch_calls += 1
        if any(keyword.arg in {"transport", None} for keyword in node.keywords):
            offenders.append(f"{source_path.relative_to(PIPELEX_SOURCE_ROOT.parent)}:{node.lineno}")
    return nb_fetch_calls, offenders


class TestTransportIsATestSeamOnly:
    def test_no_production_module_passes_a_transport_to_the_fetch_helpers(self) -> None:
        """Passing a transport replaces the guard, so only tests may do it.

        The helper's own forwarding from one fetch function to the other is the one exception.
        Calls with ``**kwargs`` count as passing one, since they could.
        """
        nb_fetch_calls = 0
        offenders: list[str] = []
        for source_path in sorted(PIPELEX_SOURCE_ROOT.rglob("*.py")):
            if source_path == FETCH_HELPER_SOURCE:
                continue
            nb_calls_in_file, offenders_in_file = _fetch_calls_passing_transport(source_path)
            nb_fetch_calls += nb_calls_in_file
            offenders.extend(offenders_in_file)

        assert nb_fetch_calls > 0, "found no call to the fetch helpers at all: the scan is looking in the wrong place"
        assert offenders == []


class TestTheKernelClosureHoldsNoFetch:
    def test_importing_the_runtime_hub_does_not_load_the_fetch_helper(self) -> None:
        """The helper reads the config, which imports the runtime hub: the hub must not import the helper back.

        Run in a subprocess so the closure is exactly what the import pulls in.
        """
        script = (
            "import sys\n"
            "import pipelex.runtime_hub\n"
            "loaded = [name for name in ('pipelex.tools.misc.file_fetch_utils', 'pipelex.tools.uri.uri_base64') if name in sys.modules]\n"
            "print(','.join(loaded))\n"
        )
        completed = subprocess.run(  # ruff: ignore[subprocess-without-shell-equals-true]
            [sys.executable, "-c", script],
            capture_output=True,
            text=True,
            check=True,
            timeout=SUBPROCESS_TIMEOUT_SECONDS,
        )

        assert completed.stdout.strip() == ""
