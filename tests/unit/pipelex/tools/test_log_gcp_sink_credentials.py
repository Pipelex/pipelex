from __future__ import annotations

import json
import logging
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import TYPE_CHECKING, Any, ClassVar

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from google.auth import compute_engine
from google.auth import exceptions as google_auth_exceptions
from typing_extensions import override

from pipelex.tools.log.exceptions import GcpLogSinkCredentialsError
from pipelex.tools.log.gcp_log_sink import (
    GCP_WORKER_THREAD_NAME,
    GcpCredentialsCheck,
    GcpCredentialsOutcome,
    confirm_credentials_at_boot,
    make_gcp_log_sink,
)
from pipelex.tools.log.log_config import GcpLogSinkConfig

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator
    from pathlib import Path

    from pytest_mock import MockerFixture

SOURCE = "the test credentials"
REMEDY = "Renew the test credentials"


class RefusedError(Exception):
    """Stands in for the auth library's refusal type."""


class UnreachableError(Exception):
    """Stands in for the auth library's transport error type."""


class RetryableRefusalError(RefusedError):
    """A refusal that declares itself retryable, as the auth library's does for a 5xx from the token endpoint."""

    @property
    def retryable(self) -> bool:
        return True


class MetadataResponse:
    """What the auth library's metadata client reads of an HTTP response: the status, the body and the content type."""

    def __init__(self, *, status: int) -> None:
        self.status = status
        self.data = b"no service account"
        self.headers = {"content-type": "text/html"}

    @override
    def __repr__(self) -> str:
        return f"MetadataResponse(status={self.status})"


class CapturingHandler(logging.Handler):
    """Stands in for the stdlib's last-resort handler, keeping what it would have printed on stderr."""

    def __init__(self) -> None:
        super().__init__(level=logging.WARNING)
        self.records: list[logging.LogRecord] = []

    @override
    def emit(self, record: logging.LogRecord) -> None:
        self.records.append(record)


class TokenEndpointRefusingEveryGrant(BaseHTTPRequestHandler):
    """A token endpoint answering every grant as Google answers a revoked or deleted credential."""

    grant_count: ClassVar[int] = 0

    def do_POST(self) -> None:
        TokenEndpointRefusingEveryGrant.grant_count += 1
        self.rfile.read(int(self.headers.get("Content-Length", "0")))
        body = json.dumps({"error": "invalid_grant", "error_description": "Invalid JWT Signature."}).encode()
        self.send_response(400)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    @override
    def log_message(self, format: str, *args: Any) -> None:
        return None


def _check(*, refresh: Callable[[], None]) -> GcpCredentialsCheck:
    return GcpCredentialsCheck(refresh=refresh, transport_error_types=(UnreachableError,), source=SOURCE)


def _refused() -> None:
    msg = "invalid_grant: Bad Request"
    raise RefusedError(msg)


def _unreachable() -> None:
    msg = "connection refused"
    raise UnreachableError(msg)


def _refused_from_unreachable() -> None:
    """The metadata-server credentials' shape: the transport failure re-raised as a refusal."""
    try:
        _unreachable()
    except UnreachableError as exc:
        msg = "metadata server unreachable"
        raise RefusedError(msg) from exc


def _refused_from_none_while_unreachable() -> None:
    try:
        _unreachable()
    except UnreachableError:
        msg = "refused, the transport failure explicitly left out of the chain"
        raise RefusedError(msg) from None


def _retryable_refusal() -> None:
    msg = "503 from the token endpoint"
    raise RetryableRefusalError(msg)


def _unanticipated() -> None:
    msg = "a key the auth library could not parse"
    raise ValueError(msg)


def _refreshed() -> None:
    return None


def _write_service_account_key(*, path: Path, token_uri: str, project_id: str | None = "a-test-project") -> None:
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_key_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode()
    key_info = {
        "type": "service_account",
        "private_key_id": "0123456789abcdef",
        "private_key": private_key_pem,
        "client_email": "pipelex-test@a-test-project.iam.gserviceaccount.com",
        "client_id": "123456789",
        "token_uri": token_uri,
    }
    if project_id is not None:
        key_info["project_id"] = project_id
    path.write_text(json.dumps(key_info), encoding="utf-8")


class TestGcpLogSinkCredentials:
    @pytest.fixture
    def stderr(self, mocker: MockerFixture) -> CapturingHandler:
        capture = CapturingHandler()
        mocker.patch.object(logging, "lastResort", capture)
        return capture

    @pytest.fixture
    def refusing_token_endpoint(self) -> Iterator[str]:
        TokenEndpointRefusingEveryGrant.grant_count = 0
        server = HTTPServer(("127.0.0.1", 0), TokenEndpointRefusingEveryGrant)
        serving = threading.Thread(target=server.serve_forever, daemon=True)
        serving.start()
        try:
            yield f"http://127.0.0.1:{server.server_address[1]}/token"
        finally:
            server.shutdown()
            server.server_close()
            serving.join(timeout=5)

    @pytest.mark.parametrize(
        ("refresh", "outcome"),
        [
            (_refreshed, GcpCredentialsOutcome.REFRESHED),
            (_refused, GcpCredentialsOutcome.REFUSED),
            (_unreachable, GcpCredentialsOutcome.UNREACHABLE),
            (_refused_from_unreachable, GcpCredentialsOutcome.UNREACHABLE),
            (_retryable_refusal, GcpCredentialsOutcome.UNREACHABLE),
            (_refused_from_none_while_unreachable, GcpCredentialsOutcome.REFUSED),
            (_unanticipated, GcpCredentialsOutcome.REFUSED),
        ],
    )
    def test_a_refresh_is_classified_by_the_whole_chain_it_raised(self, refresh: Callable[[], None], outcome: GcpCredentialsOutcome) -> None:
        """A transport failure anywhere on the chain the traceback prints means nothing is known of the credentials themselves."""
        verdict = _check(refresh=refresh).run()

        assert verdict.outcome == outcome
        match verdict.outcome:
            case GcpCredentialsOutcome.REFRESHED:
                assert verdict.failure is None
            case GcpCredentialsOutcome.REFUSED | GcpCredentialsOutcome.UNREACHABLE | GcpCredentialsOutcome.UNANSWERED:
                assert verdict.failure is not None

    def test_a_refresh_that_outlives_its_deadline_is_unanswered_without_waiting_for_it(self, mocker: MockerFixture) -> None:
        """The auth library's own request timeout is two minutes, and a boot must not wait on it."""
        mocker.patch("pipelex.tools.log.gcp_log_sink.CREDENTIALS_CHECK_TIMEOUT_SECONDS", 0.2)
        released = threading.Event()

        def hang() -> None:
            # Bounded only so a regression fails the test instead of hanging the suite.
            released.wait(timeout=10)

        started = time.monotonic()
        try:
            verdict = _check(refresh=hang).run()
            waited = time.monotonic() - started
        finally:
            released.set()

        assert verdict.outcome == GcpCredentialsOutcome.UNANSWERED
        assert verdict.failure is None
        assert waited < 5, f"the check waited {waited:.1f}s on a refresh that never answers"

    def test_credentials_refused_at_boot_stop_it_naming_them_and_the_remedy(self, stderr: CapturingHandler) -> None:
        with pytest.raises(GcpLogSinkCredentialsError) as exc_info:
            confirm_credentials_at_boot(credentials_check=_check(refresh=_refused), remedy=REMEDY)

        message = str(exc_info.value)
        assert SOURCE in message
        assert "RefusedError: invalid_grant: Bad Request" in message
        assert REMEDY in message
        assert "'json' sink" in message
        assert isinstance(exc_info.value.__cause__, RefusedError)
        assert stderr.records == []

    @pytest.mark.parametrize(
        ("refresh", "reason"),
        [
            (_unreachable, "could not reach the credential endpoint (UnreachableError: connection refused)"),
            (_refused_from_unreachable, "could not reach the credential endpoint (RefusedError: metadata server unreachable)"),
        ],
    )
    def test_credentials_that_cannot_be_reached_at_boot_are_said_on_stderr_and_the_boot_goes_on(
        self,
        stderr: CapturingHandler,
        refresh: Callable[[], None],
        reason: str,
    ) -> None:
        confirm_credentials_at_boot(credentials_check=_check(refresh=refresh), remedy=REMEDY)

        (record,) = stderr.records
        assert record.levelno == logging.WARNING
        assert f"could not confirm at boot that Google accepts {SOURCE}: a refresh {reason}." in record.getMessage()
        assert "at the latest when the process tears the sink down" in record.getMessage()

    def test_a_refresh_that_does_not_answer_at_boot_is_said_on_stderr_and_the_boot_goes_on(
        self, stderr: CapturingHandler, mocker: MockerFixture
    ) -> None:
        mocker.patch("pipelex.tools.log.gcp_log_sink.CREDENTIALS_CHECK_TIMEOUT_SECONDS", 0.2)
        released = threading.Event()

        def hang() -> None:
            # Bounded only so a regression fails the test instead of hanging the suite.
            released.wait(timeout=10)

        try:
            confirm_credentials_at_boot(credentials_check=_check(refresh=hang), remedy=REMEDY)
        finally:
            released.set()

        (record,) = stderr.records
        assert f"could not confirm at boot that Google accepts {SOURCE}: a refresh did not answer within 0.2 seconds." in record.getMessage()

    def test_credentials_that_refresh_at_boot_say_nothing(self, stderr: CapturingHandler) -> None:
        confirm_credentials_at_boot(credentials_check=_check(refresh=_refreshed), remedy=REMEDY)

        assert stderr.records == []

    @pytest.mark.parametrize(
        ("response", "outcome"),
        [
            (None, GcpCredentialsOutcome.UNREACHABLE),
            (MetadataResponse(status=404), GcpCredentialsOutcome.REFUSED),
            (MetadataResponse(status=403), GcpCredentialsOutcome.REFUSED),
            (MetadataResponse(status=408), GcpCredentialsOutcome.UNREACHABLE),
            (MetadataResponse(status=429), GcpCredentialsOutcome.UNREACHABLE),
            (MetadataResponse(status=502), GcpCredentialsOutcome.UNREACHABLE),
        ],
    )
    def test_the_auth_librarys_metadata_server_shape_is_classified_by_the_answer_it_carries(
        self, response: MetadataResponse | None, outcome: GcpCredentialsOutcome
    ) -> None:
        """The compute-engine credentials re-raise the transport failure as a ``RefreshError``, so the outer class alone would read as a refusal.

        The transport failure carries the response when the server answered with a status the client does not retry.
        """

        def metadata_server_fails() -> None:
            try:
                msg = "Failed to retrieve the service account from the Google Compute Engine metadata service."
                if response is None:
                    raise google_auth_exceptions.TransportError(msg)
                raise google_auth_exceptions.TransportError(msg, response)
            except google_auth_exceptions.TransportError as exc:
                raise google_auth_exceptions.RefreshError(exc) from exc

        check = GcpCredentialsCheck(refresh=metadata_server_fails, transport_error_types=(google_auth_exceptions.TransportError,), source=SOURCE)

        assert check.run().outcome == outcome

    def test_a_machine_whose_metadata_server_has_no_service_account_stops_the_boot(self) -> None:
        """The reported shape end to end: the library's own compute-engine credentials, and a metadata server answering 404."""
        metadata_requests: list[str] = []

        def metadata_server(url: str, **kwargs: Any) -> MetadataResponse:
            metadata_requests.append(f"{kwargs.get('method', 'GET')} {url}")
            return MetadataResponse(status=404)

        credentials: Any = compute_engine.Credentials()
        check = GcpCredentialsCheck(
            refresh=lambda: credentials.refresh(metadata_server),
            transport_error_types=(google_auth_exceptions.TransportError,),
            source=SOURCE,
        )

        with pytest.raises(GcpLogSinkCredentialsError) as exc_info:
            confirm_credentials_at_boot(credentials_check=check, remedy=REMEDY)

        assert "Status: 404" in str(exc_info.value)
        assert isinstance(exc_info.value.__cause__, google_auth_exceptions.RefreshError)
        assert len(metadata_requests) == 1, "a final answer is not retried"

    def test_application_default_credentials_that_cannot_be_found_stop_the_boot_naming_the_remedy(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        monkeypatch.setenv("GOOGLE_APPLICATION_CREDENTIALS", str(tmp_path / "missing.json"))

        with pytest.raises(GcpLogSinkCredentialsError) as exc_info:
            make_gcp_log_sink(config=GcpLogSinkConfig(log_name="pipelex", project_id="a-test-project"))

        message = str(exc_info.value)
        assert "could not load the Application Default Credentials" in message
        assert "gcloud auth application-default login" in message
        assert isinstance(exc_info.value.__cause__, google_auth_exceptions.DefaultCredentialsError)

    @pytest.mark.parametrize(
        ("key_content", "failure_type"),
        [
            (None, FileNotFoundError),
            ("", json.JSONDecodeError),
            ("not json", json.JSONDecodeError),
            (json.dumps({"type": "service_account"}), google_auth_exceptions.MalformedError),
            (
                json.dumps(
                    {
                        "type": "service_account",
                        "private_key": "-----BEGIN PRIVATE KEY-----\nnot a key\n-----END PRIVATE KEY-----\n",
                        "client_email": "pipelex-test@a-test-project.iam.gserviceaccount.com",
                        "token_uri": "https://oauth2.googleapis.com/token",
                    }
                ),
                ValueError,
            ),
        ],
    )
    def test_a_key_file_that_cannot_be_loaded_stops_the_boot_naming_the_file(
        self, tmp_path: Path, key_content: str | None, failure_type: type[Exception]
    ) -> None:
        """A missing file, one that is not JSON, and one whose key is incomplete or not a key each raise something else from the library."""
        key_path = tmp_path / "key.json"
        if key_content is not None:
            key_path.write_text(key_content, encoding="utf-8")

        with pytest.raises(GcpLogSinkCredentialsError) as exc_info:
            make_gcp_log_sink(config=GcpLogSinkConfig(log_name="pipelex", project_id="a-test-project", credentials_file_path=str(key_path)))

        message = str(exc_info.value)
        assert f"could not load the service-account key at '{key_path}'" in message
        assert "credentials_file_path" in message
        assert "'json' sink" in message
        assert isinstance(exc_info.value.__cause__, failure_type)

    def test_a_key_file_without_a_project_is_not_a_credentials_failure(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mocker: MockerFixture
    ) -> None:
        """The client raises ``OSError`` when no project can be determined, which the key file's catch must not relabel."""
        for variable in ("GOOGLE_CLOUD_PROJECT", "GCLOUD_PROJECT"):
            monkeypatch.delenv(variable, raising=False)
        mocker.patch("google.cloud.client._determine_default_project", return_value=None)
        key_path = tmp_path / "key.json"
        _write_service_account_key(path=key_path, token_uri="http://127.0.0.1:9/token", project_id=None)

        with pytest.raises(OSError, match="Project was not passed"):
            make_gcp_log_sink(config=GcpLogSinkConfig(log_name="pipelex", credentials_file_path=str(key_path)))

    def test_a_key_google_refuses_stops_the_boot_before_the_transport_starts(self, tmp_path: Path, refusing_token_endpoint: str) -> None:
        """The reported failure end to end: the client the factory builds, the refresh of the credentials it holds, the refusal it meets."""
        key_path = tmp_path / "key.json"
        _write_service_account_key(path=key_path, token_uri=refusing_token_endpoint)
        workers_before = {thread.ident for thread in threading.enumerate() if thread.name == GCP_WORKER_THREAD_NAME}

        with pytest.raises(GcpLogSinkCredentialsError) as exc_info:
            make_gcp_log_sink(config=GcpLogSinkConfig(log_name="pipelex", project_id="a-test-project", credentials_file_path=str(key_path)))

        message = str(exc_info.value)
        assert f"a refresh of the service-account key at '{key_path}' was refused at boot" in message
        assert "invalid_grant" in message
        assert isinstance(exc_info.value.__cause__, google_auth_exceptions.RefreshError)
        assert TokenEndpointRefusingEveryGrant.grant_count == 1
        assert {thread.ident for thread in threading.enumerate() if thread.name == GCP_WORKER_THREAD_NAME} == workers_before
