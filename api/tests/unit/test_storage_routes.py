"""The storage routes a self-hosted runner serves: `POST /v1/resolve-storage-url/bulk` and `GET /v1/storage/{key}`.

A client turns a `pipelex-storage://` reference back into bytes by resolving it to a short-lived link and fetching the
link without its credential. These pin the wire against the hosted platform's, field for field and bound for bound; the
scope each authentication mode resolves under; the absence of both routes when the runner trusts forwarded identity;
the signed link's refusals; downloads of a stored text, an image and a document under the local provider; and a round
trip through the Python SDK's `load_stored_texts`, the composition every template's blocking path runs.
"""

import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, quote, urlsplit

import httpx
import jwt
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pipelex.tools.storage.exceptions import StorageInvalidUriError, StorageS3Error
from pipelex.tools.storage.in_memory_storage_provider import InMemoryStorageProvider
from pipelex.tools.storage.local_storage_provider import LocalStorageProvider
from pipelex.tools.storage.storage_provider_abstract import PIPELEX_STORAGE_SCHEME, StoredData
from pipelex_sdk.artifact_models import BulkResolvedStorageUrls
from pipelex_sdk.artifacts import load_stored_texts
from pipelex_sdk.runs import RunResults
from pytest_mock import MockerFixture

from pipelex_api.exception_handlers import register_exception_handlers
from pipelex_api.exceptions import ApiBootConfigError
from pipelex_api.limits import DEFAULT_STORAGE_LINK_TTL_SECONDS, MAX_SIGNED_LINK_TTL_SECONDS, signed_link_ttl_seconds
from pipelex_api.routes.storage import MAX_BULK_RESOLVE_URIS, STORAGE_URI_MAX_CHARS, mount_storage_routes
from pipelex_api.security import AUTH_MODE_ENV_VAR, TRUST_FORWARDED_IDENTITY_HEADERS_ENV, AuthMode, get_auth_dependency
from pipelex_api.signed_links import LinkPurpose, link_signature
from tests.unit._problems import ClientResponse, assert_problem
from tests.unit.cases import StorageRouteCases

_REPO_ROOT = Path(__file__).resolve().parents[3]
# What the local provider stores in its test: the key, the bytes and the content type stored with them. Every answer but
# the PDF's is sandboxed, an HTML page's and an SVG image's above all, since either could run a script.
_STORED_FILES = {
    "text": (StorageRouteCases.TEXT_KEY, StorageRouteCases.LONG_TEXT.encode(), "text/plain"),
    "image": (StorageRouteCases.IMAGE_KEY, (_REPO_ROOT / "tests" / "data" / "images" / "logo-tiny.png").read_bytes(), "image/png"),
    "document": (
        StorageRouteCases.DOCUMENT_KEY,
        (_REPO_ROOT / "tests" / "data" / "documents" / "solar_system.pdf").read_bytes(),
        "application/pdf",
    ),
    "html": ("single-tenant/generated/0123456789abcdef/value.html", b"<html><script>alert(1)</script></html>", "text/html"),
    "svg": (
        "single-tenant/generated/0123456789abcdef.svg",
        b'<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>',
        "image/svg+xml",
    ),
}
_RESOLVE_PATH = "/v1/resolve-storage-url/bulk"


def _uri(key: str) -> str:
    return f"{PIPELEX_STORAGE_SCHEME}{key}"


def _build_client(*, monkeypatch: pytest.MonkeyPatch, auth_mode: AuthMode = AuthMode.NONE, trusts_forwarding: bool = False) -> TestClient:
    """A runner app holding only the storage routes, mounted as `pipelex_api.main` mounts them, under one auth mode."""
    monkeypatch.setenv(AUTH_MODE_ENV_VAR, auth_mode)
    monkeypatch.setenv("API_KEY", StorageRouteCases.SYNTHETIC_API_KEY)
    monkeypatch.setenv("JWT_SECRET_KEY", StorageRouteCases.SYNTHETIC_JWT_SECRET)
    if trusts_forwarding:
        monkeypatch.setenv(TRUST_FORWARDED_IDENTITY_HEADERS_ENV, "true")
    else:
        monkeypatch.delenv(TRUST_FORWARDED_IDENTITY_HEADERS_ENV, raising=False)
    app = FastAPI()
    mount_storage_routes(app=app, auth_dependency=get_auth_dependency())
    register_exception_handlers(app)
    return TestClient(app)


def _headers(*, auth_mode: AuthMode, user_id: str = StorageRouteCases.JWT_USER_ID) -> dict[str, str]:
    match auth_mode:
        case AuthMode.NONE:
            return {}
        case AuthMode.API_KEY:
            return {"Authorization": f"Bearer {StorageRouteCases.SYNTHETIC_API_KEY}"}
        case AuthMode.JWT:
            token = jwt.encode({"user_id": user_id}, StorageRouteCases.SYNTHETIC_JWT_SECRET, algorithm="HS256")
            return {"Authorization": f"Bearer {token}"}


def _resolve(client: TestClient, *uris: str, headers: dict[str, str] | None = None) -> list[dict[str, Any]]:
    response = client.post(_RESOLVE_PATH, json={"uris": list(uris)}, headers=headers or {})
    assert response.status_code == 200, response.text
    items: list[dict[str, Any]] = response.json()["items"]
    return items


def _download(client: TestClient, url: str) -> Any:
    """Fetch a resolved link through the test client, by its path and query, with no credential."""
    parts = urlsplit(url)
    return client.get(f"{parts.path}?{parts.query}")


def _assert_refused_link(response: ClientResponse) -> None:
    problem = assert_problem(response, status=403, code="auth.forbidden")
    assert problem["params"] == {"requirement": "signed_storage_link"}


@pytest.fixture(name="storage")
def storage_fixture(blob_storage: InMemoryStorageProvider, mocker: MockerFixture) -> InMemoryStorageProvider:
    """The in-memory storage the conftest installs, read by the download route too."""
    mocker.patch("pipelex_api.routes.storage.get_storage_provider", return_value=blob_storage)
    return blob_storage


class TestStorageRoutes:
    def test_a_reference_under_the_single_tenant_scope_resolves_to_a_link_that_downloads_it(
        self, monkeypatch: pytest.MonkeyPatch, storage: InMemoryStorageProvider
    ) -> None:
        storage.root[StorageRouteCases.TEXT_KEY] = StorageRouteCases.LONG_TEXT.encode()
        client = _build_client(monkeypatch=monkeypatch)
        before = datetime.now(tz=UTC)

        (item,) = _resolve(client, _uri(StorageRouteCases.TEXT_KEY))

        assert item["uri"] == _uri(StorageRouteCases.TEXT_KEY)
        assert item["error"] is None
        assert item["content_type"] == "text/plain"
        url_text: str = item["url"]
        url = urlsplit(url_text)
        assert (url.scheme, url.netloc, url.path) == ("http", "testserver", f"/v1/storage/{StorageRouteCases.TEXT_KEY}")
        assert set(parse_qs(url.query)) == {"expires", "signature"}
        expires_at = datetime.fromisoformat(item["expires_at"])
        assert 0 < (expires_at - before).total_seconds() <= DEFAULT_STORAGE_LINK_TTL_SECONDS + 1
        downloaded = _download(client, item["url"])
        assert downloaded.status_code == 200, downloaded.text
        assert downloaded.text == StorageRouteCases.LONG_TEXT
        assert downloaded.headers["content-type"].startswith("text/plain")
        assert downloaded.headers["x-content-type-options"] == "nosniff"
        assert downloaded.headers["content-security-policy"] == "sandbox"

    def test_the_answer_has_the_platform_s_shape_field_for_field(self, monkeypatch: pytest.MonkeyPatch, storage: InMemoryStorageProvider) -> None:
        client = _build_client(monkeypatch=monkeypatch)

        response = client.post(_RESOLVE_PATH, json={"uris": [_uri(StorageRouteCases.TEXT_KEY), "s3://elsewhere/value.txt"]})

        assert response.status_code == 200, response.text
        body = response.json()
        assert set(body) == StorageRouteCases.PLATFORM_RESPONSE_FIELDS
        resolved, refused = body["items"]
        assert set(resolved) == StorageRouteCases.PLATFORM_ITEM_FIELDS
        assert set(refused) == StorageRouteCases.PLATFORM_ITEM_FIELDS
        assert (refused["url"], refused["expires_at"], refused["content_type"]) == (None, None, None)
        assert set(refused["error"]) == StorageRouteCases.PLATFORM_REFUSAL_FIELDS
        assert (MAX_BULK_RESOLVE_URIS, STORAGE_URI_MAX_CHARS) == (
            StorageRouteCases.PLATFORM_MAX_BULK_RESOLVE_URIS,
            StorageRouteCases.PLATFORM_STORAGE_URI_MAX_CHARS,
        )
        assert not storage.root

    def test_each_reference_gets_its_verdict_in_request_order(self, monkeypatch: pytest.MonkeyPatch, storage: InMemoryStorageProvider) -> None:
        client = _build_client(monkeypatch=monkeypatch, auth_mode=AuthMode.JWT)
        own_key = f"{StorageRouteCases.JWT_USER_ID}/generated/0123456789abcdef.png"
        uris = [
            _uri(own_key),
            _uri(f"{StorageRouteCases.OTHER_USER_ID}/generated/0123456789abcdef.png"),
            *StorageRouteCases.MALFORMED_URIS,
            _uri(own_key),
        ]

        items = _resolve(client, *uris, headers=_headers(auth_mode=AuthMode.JWT))

        assert [item["uri"] for item in items] == uris
        assert items[0]["error"] is None
        assert items[0]["content_type"] == "image/png"
        assert items[-1]["error"] is None
        assert items[1]["url"] is None
        assert items[1]["error"]["code"] == "auth.forbidden"
        assert items[1]["error"]["params"] == {"requirement": "read_scope_under_caller"}
        for item in items[2:-1]:
            assert item["url"] is None, item
            assert item["error"]["code"] == "pipelex.storage.uri_invalid", item
            assert item["error"]["params"] is None, item
            assert item["error"]["detail"] == "A storage address in the request cannot be parsed.", item
        assert not storage.root

    @pytest.mark.parametrize("foreign_scope", ["single-tenant", StorageRouteCases.OTHER_USER_ID, f"{StorageRouteCases.JWT_USER_ID}x"])
    def test_a_jwt_caller_resolves_only_under_its_own_id(
        self, monkeypatch: pytest.MonkeyPatch, storage: InMemoryStorageProvider, foreign_scope: str
    ) -> None:
        """The reserved single-tenant scope, another caller's, and an id the caller's is a prefix of are all another scope."""
        own_key = f"{StorageRouteCases.JWT_USER_ID}/generated/value.txt"
        storage.root[own_key] = b"mine"
        storage.root[f"{foreign_scope}/generated/value.txt"] = b"theirs"
        client = _build_client(monkeypatch=monkeypatch, auth_mode=AuthMode.JWT)
        headers = _headers(auth_mode=AuthMode.JWT)

        own, foreign = _resolve(client, _uri(own_key), _uri(f"{foreign_scope}/generated/value.txt"), headers=headers)

        assert own["error"] is None, own
        assert _download(client, own["url"]).content == b"mine"
        assert foreign["url"] is None, foreign
        assert foreign["error"] == {
            "code": "auth.forbidden",
            "detail": "The request's identity lacks 'read_scope_under_caller', which this operation needs.",
            "params": {"requirement": "read_scope_under_caller"},
        }
        (bare_scope,) = _resolve(client, _uri(StorageRouteCases.JWT_USER_ID), headers=headers)
        assert bare_scope["error"]["code"] == "pipelex.storage.uri_invalid"

    @pytest.mark.parametrize("auth_mode", [AuthMode.NONE, AuthMode.API_KEY])
    def test_a_deployment_that_identifies_no_caller_resolves_any_reference_that_parses(
        self, monkeypatch: pytest.MonkeyPatch, storage: InMemoryStorageProvider, auth_mode: AuthMode
    ) -> None:
        """Its one tenant's runs may write under any `storage_scope` and read under any `read_scope`, so it reads them all back."""
        keys = [
            "single-tenant/generated/value.txt",
            "a-run-s-own-storage-scope/generated/value.txt",
            f"{StorageRouteCases.OTHER_USER_ID}/assets/value.txt",
        ]
        for key in keys:
            storage.root[key] = key.encode()
        client = _build_client(monkeypatch=monkeypatch, auth_mode=auth_mode)

        items = _resolve(client, *[_uri(key) for key in keys], headers=_headers(auth_mode=auth_mode))

        assert [item["error"] for item in items] == [None, None, None]
        assert [_download(client, item["url"]).content for item in items] == [key.encode() for key in keys]

    @pytest.mark.parametrize("auth_mode", [AuthMode.API_KEY, AuthMode.JWT])
    def test_resolving_needs_the_deployment_s_credential(self, monkeypatch: pytest.MonkeyPatch, auth_mode: AuthMode) -> None:
        client = _build_client(monkeypatch=monkeypatch, auth_mode=auth_mode)

        response = client.post(_RESOLVE_PATH, json={"uris": [_uri(StorageRouteCases.TEXT_KEY)]})

        assert_problem(response, status=401, code="auth.missing_credential")

    def test_neither_route_is_served_when_the_runner_trusts_forwarded_identity(
        self, monkeypatch: pytest.MonkeyPatch, storage: InMemoryStorageProvider
    ) -> None:
        storage.root[StorageRouteCases.TEXT_KEY] = b"a text"
        (item,) = _resolve(_build_client(monkeypatch=monkeypatch), _uri(StorageRouteCases.TEXT_KEY))
        client = _build_client(monkeypatch=monkeypatch, trusts_forwarding=True)

        resolved = client.post(_RESOLVE_PATH, json={"uris": [_uri(StorageRouteCases.TEXT_KEY)]}, headers={"X-User-Id": "single-tenant"})
        downloaded = _download(client, item["url"])

        assert_problem(resolved, status=404, code="request.not_found")
        assert_problem(downloaded, status=404, code="request.not_found")

    @pytest.mark.parametrize("auth_mode", [AuthMode.JWT, AuthMode.API_KEY])
    def test_the_routes_are_served_whatever_the_forwarding_flag_says_when_the_mode_reads_a_credential(
        self, monkeypatch: pytest.MonkeyPatch, storage: InMemoryStorageProvider, auth_mode: AuthMode
    ) -> None:
        """Only `AUTH_MODE=none` reads a forwarded identity, so the flag beside another mode changes nothing."""
        client = _build_client(monkeypatch=monkeypatch, auth_mode=auth_mode, trusts_forwarding=True)

        response = client.post(_RESOLVE_PATH, json={"uris": []}, headers=_headers(auth_mode=auth_mode))

        assert response.status_code == 200, response.text
        assert response.json() == {"items": []}
        assert not storage.root

    @pytest.mark.parametrize(
        "body",
        [
            {"uris": [_uri(f"single-tenant/generated/{index}.txt") for index in range(MAX_BULK_RESOLVE_URIS + 1)]},
            {"uris": [_uri("single-tenant/" + "a" * STORAGE_URI_MAX_CHARS + ".txt")]},
            {"uris": [], "read_scope": "someone-else"},
            {},
        ],
        ids=["too_many_references", "reference_too_long", "unknown_field", "no_references"],
    )
    def test_a_request_past_the_platform_s_bounds_is_refused_whole(self, monkeypatch: pytest.MonkeyPatch, body: dict[str, Any]) -> None:
        response = _build_client(monkeypatch=monkeypatch).post(_RESOLVE_PATH, json=body)

        assert_problem(response, status=422, code="request.invalid")

    @pytest.mark.parametrize(
        "tampering", ["no_query", "forged_signature", "another_key", "not_a_number", "too_many_digits", "expired", "upload_signature"]
    )
    def test_a_download_without_a_valid_link_is_refused(
        self, monkeypatch: pytest.MonkeyPatch, storage: InMemoryStorageProvider, mocker: MockerFixture, tampering: str
    ) -> None:
        storage.root[StorageRouteCases.TEXT_KEY] = b"a text"
        storage.root[StorageRouteCases.MISSING_KEY] = b"another text"
        client = _build_client(monkeypatch=monkeypatch)
        if tampering == "expired":
            mocker.patch("pipelex_api.storage_links.STORAGE_LINK_TTL_SECONDS", -60)
        (item,) = _resolve(client, _uri(StorageRouteCases.TEXT_KEY))
        url_text: str = item["url"]
        url = urlsplit(url_text)
        query: dict[str, str] = {name: values[0] for name, values in parse_qs(url.query).items()}
        path: str = url.path
        match tampering:
            case "no_query":
                query = {}
            case "forged_signature":
                query["signature"] = "0" * 64
            case "another_key":
                path = f"/v1/storage/{StorageRouteCases.MISSING_KEY}"
            case "not_a_number":
                query["expires"] = "１２３４５６７８９０"
            case "too_many_digits":
                # Past the digits Python's `int()` reads by default: a refused link, never a server error.
                query["expires"] = "9" * 5000
            case "expired":
                pass
            case "upload_signature":
                # A signature made for an upload target never holds for a download, even over the very message it binds.
                message = f"{StorageRouteCases.TEXT_KEY}\n{query['expires']}"
                query["signature"] = link_signature(purpose=LinkPurpose.BLOB_UPLOAD, message=message)
            case _:
                pytest.fail(f"unknown tampering {tampering}")

        _assert_refused_link(client.get(path, params=query))

    def test_a_link_to_an_address_holding_no_file_is_a_404(self, monkeypatch: pytest.MonkeyPatch, storage: InMemoryStorageProvider) -> None:
        client = _build_client(monkeypatch=monkeypatch)
        (item,) = _resolve(client, _uri(StorageRouteCases.MISSING_KEY))

        assert item["error"] is None
        problem = assert_problem(_download(client, item["url"]), status=404, code="pipelex.storage.object_missing")
        assert problem["detail"] == "No file is stored at the storage address this link names."
        assert not storage.root

    @pytest.mark.parametrize(
        ("key", "expected"),
        [
            pytest.param("single-tenant/generated", (404, "pipelex.storage.object_missing"), id="a_directory"),
            pytest.param("single-tenant/generated/value.txt/inner.txt", (404, "pipelex.storage.object_missing"), id="through_a_file"),
            pytest.param("single-tenant/" + "a" * 300 + ".txt", (403, "auth.forbidden"), id="a_segment_no_filesystem_holds"),
        ],
    )
    @pytest.mark.asyncio(loop_scope="class")
    async def test_a_signed_link_naming_no_stored_file_is_never_a_server_error(
        self, monkeypatch: pytest.MonkeyPatch, mocker: MockerFixture, tmp_path: Path, key: str, expected: tuple[int, str]
    ) -> None:
        """Whatever key a validly signed link names, the local provider answers a refusal of the caller's, never a 500."""
        local = LocalStorageProvider(root_path=tmp_path)
        mocker.patch("pipelex_api.routes.storage.get_storage_provider", return_value=local)
        await local.store(b"a text", key="single-tenant/generated/value.txt", content_type="text/plain")
        client = _build_client(monkeypatch=monkeypatch)
        expires = str(int(time.time()) + 60)
        signature = link_signature(purpose=LinkPurpose.STORAGE_DOWNLOAD, message=f"{key}\n{expires}")

        response = client.get(f"/v1/storage/{quote(key, safe='/')}", params={"expires": expires, "signature": signature})

        status, code = expected
        assert_problem(response, status=status, code=code)

    @pytest.mark.asyncio(loop_scope="class")
    async def test_a_metadata_sidecar_is_never_resolved_nor_downloaded(
        self, monkeypatch: pytest.MonkeyPatch, mocker: MockerFixture, tmp_path: Path
    ) -> None:
        """The file the local provider keeps a stored file's metadata in is not a stored object of its own."""
        local = LocalStorageProvider(root_path=tmp_path)
        mocker.patch("pipelex_api.routes.storage.get_storage_provider", return_value=local)
        await local.store(b"a text", key="single-tenant/generated/value.txt", content_type="text/plain", metadata={"origin": "test"})
        sidecar_key = "single-tenant/generated/.value.txt.metadata.json"
        assert (tmp_path / sidecar_key).is_file()
        client = _build_client(monkeypatch=monkeypatch)

        (item,) = _resolve(client, _uri(sidecar_key))
        expires = str(int(time.time()) + 60)
        signature = link_signature(purpose=LinkPurpose.STORAGE_DOWNLOAD, message=f"{sidecar_key}\n{expires}")
        downloaded = client.get(f"/v1/storage/{sidecar_key}", params={"expires": expires, "signature": signature})

        assert item["url"] is None
        assert item["error"]["code"] == "pipelex.storage.uri_invalid"
        _assert_refused_link(downloaded)

    def test_a_signed_link_to_an_address_the_provider_refuses_is_a_404(self, monkeypatch: pytest.MonkeyPatch, mocker: MockerFixture) -> None:
        provider = mocker.Mock(storage_kind="local")
        provider.load_with_metadata = mocker.AsyncMock(side_effect=StorageInvalidUriError("Invalid key: refused by the provider"))
        mocker.patch("pipelex_api.routes.storage.get_storage_provider", return_value=provider)
        client = _build_client(monkeypatch=monkeypatch)

        (item,) = _resolve(client, _uri(StorageRouteCases.TEXT_KEY))

        assert_problem(_download(client, item["url"]), status=404, code="pipelex.storage.object_missing")

    def test_a_storage_backend_failing_the_read_is_a_503(self, monkeypatch: pytest.MonkeyPatch, mocker: MockerFixture) -> None:
        provider = mocker.Mock(storage_kind="s3")
        provider.load_with_metadata = mocker.AsyncMock(side_effect=StorageS3Error("The S3 read failed"))
        mocker.patch("pipelex_api.routes.storage.get_storage_provider", return_value=provider)
        client = _build_client(monkeypatch=monkeypatch)

        (item,) = _resolve(client, _uri(StorageRouteCases.TEXT_KEY))

        problem = assert_problem(_download(client, item["url"]), status=503, code="pipelex.storage.unavailable")
        assert problem["params"] == {"scheme": "s3"}

    @pytest.mark.parametrize("env_var", ["STORAGE_LINK_TTL_SECONDS", "BLOB_UPLOAD_URL_TTL_SECONDS"])
    def test_a_signed_link_lifetime_past_seven_days_refuses_to_boot(self, monkeypatch: pytest.MonkeyPatch, env_var: str) -> None:
        monkeypatch.setenv(env_var, str(MAX_SIGNED_LINK_TTL_SECONDS))
        assert signed_link_ttl_seconds(env_var=env_var, default=60) == MAX_SIGNED_LINK_TTL_SECONDS
        assert MAX_SIGNED_LINK_TTL_SECONDS == 7 * 24 * 3600

        monkeypatch.setenv(env_var, str(MAX_SIGNED_LINK_TTL_SECONDS + 1))
        with pytest.raises(ApiBootConfigError, match=f"{env_var} is {MAX_SIGNED_LINK_TTL_SECONDS + 1} seconds"):
            signed_link_ttl_seconds(env_var=env_var, default=60)

        monkeypatch.setenv(env_var, "9" * 40)
        with pytest.raises(ApiBootConfigError):
            signed_link_ttl_seconds(env_var=env_var, default=60)

    def test_a_link_at_the_longest_lifetime_still_downloads(
        self, monkeypatch: pytest.MonkeyPatch, mocker: MockerFixture, storage: InMemoryStorageProvider
    ) -> None:
        storage.root[StorageRouteCases.TEXT_KEY] = b"a text"
        mocker.patch("pipelex_api.storage_links.STORAGE_LINK_TTL_SECONDS", MAX_SIGNED_LINK_TTL_SECONDS)
        client = _build_client(monkeypatch=monkeypatch)

        (item,) = _resolve(client, _uri(StorageRouteCases.TEXT_KEY))

        assert _download(client, item["url"]).content == b"a text"

    def test_links_start_with_the_configured_public_base_url(self, monkeypatch: pytest.MonkeyPatch, storage: InMemoryStorageProvider) -> None:
        storage.root[StorageRouteCases.TEXT_KEY] = b"a text"
        monkeypatch.setenv("PUBLIC_BASE_URL", StorageRouteCases.PUBLIC_BASE_URL)
        client = _build_client(monkeypatch=monkeypatch)

        (item,) = _resolve(client, _uri(StorageRouteCases.TEXT_KEY))

        assert str(item["url"]).startswith(f"https://runner.example.com/api/v1/storage/{StorageRouteCases.TEXT_KEY}?")
        url_text: str = item["url"]
        url = urlsplit(url_text)
        downloaded = client.get(f"{url.path.removeprefix('/api')}?{url.query}")
        assert downloaded.content == b"a text"

    def test_a_key_holding_characters_a_path_escapes_round_trips(self, monkeypatch: pytest.MonkeyPatch, storage: InMemoryStorageProvider) -> None:
        # No `%` in the key: the test client decodes a request's path twice, which a server such as uvicorn does not.
        key = "single-tenant/generated/a b?d#e/value.txt"
        storage.root[key] = b"escaped"
        client = _build_client(monkeypatch=monkeypatch)

        (item,) = _resolve(client, _uri(key))

        assert "/a%20b%3Fd%23e/" in item["url"]
        assert _download(client, item["url"]).content == b"escaped"

    @pytest.mark.parametrize("stored_file", list(_STORED_FILES))
    @pytest.mark.asyncio(loop_scope="class")
    async def test_the_local_provider_serves_each_stored_file_sandboxed_unless_a_pdf(
        self, monkeypatch: pytest.MonkeyPatch, mocker: MockerFixture, tmp_path: Path, stored_file: str
    ) -> None:
        key, data, media_type = _STORED_FILES[stored_file]
        local = LocalStorageProvider(root_path=tmp_path)
        mocker.patch("pipelex_api.routes.storage.get_storage_provider", return_value=local)
        await local.store(data, key=key, content_type=media_type)
        client = _build_client(monkeypatch=monkeypatch)

        (item,) = _resolve(client, _uri(key))
        downloaded = _download(client, item["url"])

        assert item["content_type"] == media_type
        assert downloaded.status_code == 200, downloaded.text
        assert downloaded.content == data
        assert downloaded.headers["content-type"].split(";")[0] == media_type
        assert downloaded.headers["x-content-type-options"] == "nosniff"
        if stored_file == "document":
            # A sandbox keeps Chromium's PDF viewer from displaying the document (crbug 413851).
            assert "content-security-policy" not in downloaded.headers
        else:
            assert downloaded.headers["content-security-policy"] == "sandbox"

    @pytest.mark.parametrize(
        ("key", "provider_type", "expected"),
        [
            pytest.param("single-tenant/assets/report.pdf", "application/pdf; charset=binary", ("application/pdf", False), id="parameters_dropped"),
            pytest.param("single-tenant/assets/report.pdf", "Application/PDF", ("application/pdf", False), id="lowercased"),
            pytest.param("single-tenant/assets/report.bin", "image/png", ("image/png", True), id="stored_type_kept"),
            pytest.param("single-tenant/assets/report", "application/pdf;,text/html", ("application/octet-stream", True), id="comma_no_name_type"),
            pytest.param("single-tenant/assets/report.png", "application/pdf;,text/html", ("image/png", True), id="comma_name_type"),
            pytest.param("single-tenant/assets/report.pdf", "application/pdf;,text/html", ("application/pdf", False), id="comma_falls_back_to_name"),
            pytest.param("single-tenant/assets/report", "application/pdf,text/html", ("application/octet-stream", True), id="comma_in_essence"),
            pytest.param("single-tenant/assets/report", "application/pdf/html", ("application/octet-stream", True), id="two_slashes"),
            pytest.param("single-tenant/assets/report", "application", ("application/octet-stream", True), id="no_subtype"),
            pytest.param("single-tenant/assets/report", "/pdf", ("application/octet-stream", True), id="no_type"),
            pytest.param("single-tenant/assets/report", "application/p df", ("application/octet-stream", True), id="space_in_subtype"),
            pytest.param("single-tenant/assets/report", "applicatio\u212a/pdf", ("application/octet-stream", True), id="non_ascii"),
            pytest.param("single-tenant/assets/report.txt", None, ("text/plain", True), id="no_stored_type"),
        ],
    )
    def test_the_download_route_serves_a_validated_bare_media_type(
        self,
        monkeypatch: pytest.MonkeyPatch,
        mocker: MockerFixture,
        key: str,
        provider_type: str | None,
        expected: tuple[str, bool],
    ) -> None:
        """Whatever type a provider that keeps stored types answers, the route serves a bare `type/subtype` it validated."""
        provider = mocker.Mock(storage_kind="s3")
        provider.load_with_metadata = mocker.AsyncMock(return_value=StoredData(data=b"stored bytes", mime_type=provider_type))
        mocker.patch("pipelex_api.routes.storage.get_storage_provider", return_value=provider)
        client = _build_client(monkeypatch=monkeypatch)

        (item,) = _resolve(client, _uri(key))
        downloaded = _download(client, item["url"])

        served, sandboxed = expected
        assert downloaded.status_code == 200, downloaded.text
        # The framework names the charset of a text type; the type itself is the bare one, with nothing the provider sent.
        assert downloaded.headers["content-type"].removesuffix("; charset=utf-8") == served
        assert ("content-security-policy" in downloaded.headers) is sandboxed
        if sandboxed:
            assert downloaded.headers["content-security-policy"] == "sandbox"

    @pytest.mark.parametrize("head", [b"BM", b"MZ", b"ID3", b"GIF89a", b"%PDF-1.4"])
    @pytest.mark.parametrize("provider_kind", ["local", "memory"])
    @pytest.mark.asyncio(loop_scope="class")
    async def test_a_provider_keeping_no_stored_type_serves_the_type_the_name_implies(
        self, monkeypatch: pytest.MonkeyPatch, mocker: MockerFixture, tmp_path: Path, provider_kind: str, head: bytes
    ) -> None:
        """A text whose first bytes look like another format is served as the text the resolve route reported."""
        provider: LocalStorageProvider | InMemoryStorageProvider
        match provider_kind:
            case "local":
                provider = LocalStorageProvider(root_path=tmp_path)
            case "memory":
                provider = InMemoryStorageProvider(root={})
            case _:
                pytest.fail(f"unknown provider kind {provider_kind}")
        mocker.patch("pipelex_api.routes.storage.get_storage_provider", return_value=provider)
        data = head + b" is how this stored text starts"
        await provider.store(data, key=StorageRouteCases.TEXT_KEY, content_type="text/plain")
        client = _build_client(monkeypatch=monkeypatch)

        (item,) = _resolve(client, _uri(StorageRouteCases.TEXT_KEY))
        downloaded = _download(client, item["url"])

        assert item["content_type"] == "text/plain"
        assert downloaded.status_code == 200, downloaded.text
        assert downloaded.content == data
        assert downloaded.headers["content-type"] == "text/plain; charset=utf-8"
        assert downloaded.headers["content-security-policy"] == "sandbox"

    @pytest.mark.asyncio(loop_scope="class")
    async def test_a_provider_keeping_no_stored_type_sniffs_an_object_whose_name_implies_none(
        self, monkeypatch: pytest.MonkeyPatch, mocker: MockerFixture, tmp_path: Path
    ) -> None:
        local = LocalStorageProvider(root_path=tmp_path)
        mocker.patch("pipelex_api.routes.storage.get_storage_provider", return_value=local)
        key = "single-tenant/assets/no-extension"
        await local.store(_STORED_FILES["image"][1], key=key, content_type="image/png")
        client = _build_client(monkeypatch=monkeypatch)

        (item,) = _resolve(client, _uri(key))
        downloaded = _download(client, item["url"])

        assert item["content_type"] is None
        assert downloaded.headers["content-type"] == "image/png"

    @pytest.mark.asyncio(loop_scope="class")
    async def test_the_python_sdk_loads_a_stored_text_through_the_runner(
        self, monkeypatch: pytest.MonkeyPatch, storage: InMemoryStorageProvider
    ) -> None:
        """The composition every template's blocking path runs: resolve through the bulk route, fetch the link."""
        storage.root[StorageRouteCases.TEXT_KEY] = StorageRouteCases.LONG_TEXT.encode()
        client = _build_client(monkeypatch=monkeypatch)
        reference = {
            "url": _uri(StorageRouteCases.TEXT_KEY),
            "size": len(StorageRouteCases.LONG_TEXT),
            "mime_type": "text/plain",
            "preview": StorageRouteCases.LONG_TEXT[:40],
        }
        results = RunResults.model_validate(
            {
                "pipeline_run_id": "run_storage_round_trip",
                "main_stuff": reference,
                "working_memory": {"root": {"main_stuff": {"concept": "native.Text", "content": reference}}, "aliases": {}},
            }
        )
        asgi_app = client.app

        class _RunnerBulkResolveClient:
            # The runner's own origin: its storage route hands back plain-http links there, which pipelex-sdk fetches
            # without `allow_http`, as it does for a self-hosted runner listening on plain http.
            @property
            def origin_url(self) -> str:
                return "http://testserver"

            async def resolve_storage_urls_bulk(self, uris: list[str]) -> BulkResolvedStorageUrls:
                async with httpx.AsyncClient(transport=httpx.ASGITransport(app=asgi_app), base_url="http://testserver") as http:
                    answer = await http.post(_RESOLVE_PATH, json={"uris": uris})
                assert answer.status_code == 200, answer.text
                return BulkResolvedStorageUrls.model_validate(answer.json())

        def _storage_client(timeout_seconds: float) -> httpx.AsyncClient:
            return httpx.AsyncClient(transport=httpx.ASGITransport(app=asgi_app), timeout=timeout_seconds, follow_redirects=False)

        monkeypatch.setattr("pipelex_sdk.artifacts._new_storage_client", _storage_client)

        loaded = await load_stored_texts(_RunnerBulkResolveClient(), results)

        assert loaded.main_stuff == {"text": StorageRouteCases.LONG_TEXT}
