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
from pipelex.tools.storage.in_memory_storage_provider import InMemoryStorageProvider
from pipelex.tools.storage.local_storage_provider import LocalStorageProvider
from pipelex.tools.storage.storage_provider_abstract import PIPELEX_STORAGE_SCHEME
from pipelex_sdk.artifact_models import BulkResolvedStorageUrls, LoadStoredTextsOptions
from pipelex_sdk.artifacts import load_stored_texts
from pipelex_sdk.runs import RunResults
from pytest_mock import MockerFixture

from pipelex_api.exception_handlers import register_exception_handlers
from pipelex_api.limits import DEFAULT_STORAGE_LINK_TTL_SECONDS
from pipelex_api.routes.storage import MAX_BULK_RESOLVE_URIS, STORAGE_URI_MAX_CHARS, mount_storage_routes
from pipelex_api.security import AUTH_MODE_ENV_VAR, TRUST_FORWARDED_IDENTITY_HEADERS_ENV, AuthMode, get_auth_dependency
from pipelex_api.signed_links import LinkPurpose, link_signature
from tests.unit._problems import ClientResponse, assert_problem
from tests.unit.test_data import StorageRouteTestData

_REPO_ROOT = Path(__file__).resolve().parents[3]
# What the local provider stores in its test: the key, the bytes and the content type stored with them.
_STORED_FILES = {
    "text": (StorageRouteTestData.TEXT_KEY, StorageRouteTestData.LONG_TEXT.encode(), "text/plain"),
    "image": (StorageRouteTestData.IMAGE_KEY, (_REPO_ROOT / "tests" / "data" / "images" / "logo-tiny.png").read_bytes(), "image/png"),
    "document": (
        StorageRouteTestData.DOCUMENT_KEY,
        (_REPO_ROOT / "tests" / "data" / "documents" / "solar_system.pdf").read_bytes(),
        "application/pdf",
    ),
}
_RESOLVE_PATH = "/v1/resolve-storage-url/bulk"


def _uri(key: str) -> str:
    return f"{PIPELEX_STORAGE_SCHEME}{key}"


def _build_client(*, monkeypatch: pytest.MonkeyPatch, auth_mode: AuthMode = AuthMode.NONE, trusts_forwarding: bool = False) -> TestClient:
    """A runner app holding only the storage routes, mounted as `pipelex_api.main` mounts them, under one auth mode."""
    monkeypatch.setenv(AUTH_MODE_ENV_VAR, auth_mode)
    monkeypatch.setenv("API_KEY", StorageRouteTestData.SYNTHETIC_API_KEY)
    monkeypatch.setenv("JWT_SECRET_KEY", StorageRouteTestData.SYNTHETIC_JWT_SECRET)
    if trusts_forwarding:
        monkeypatch.setenv(TRUST_FORWARDED_IDENTITY_HEADERS_ENV, "true")
    else:
        monkeypatch.delenv(TRUST_FORWARDED_IDENTITY_HEADERS_ENV, raising=False)
    app = FastAPI()
    mount_storage_routes(app=app, auth_dependency=get_auth_dependency())
    register_exception_handlers(app)
    return TestClient(app)


def _headers(*, auth_mode: AuthMode, user_id: str = StorageRouteTestData.JWT_USER_ID) -> dict[str, str]:
    match auth_mode:
        case AuthMode.NONE:
            return {}
        case AuthMode.API_KEY:
            return {"Authorization": f"Bearer {StorageRouteTestData.SYNTHETIC_API_KEY}"}
        case AuthMode.JWT:
            token = jwt.encode({"user_id": user_id}, StorageRouteTestData.SYNTHETIC_JWT_SECRET, algorithm="HS256")
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
        storage.root[StorageRouteTestData.TEXT_KEY] = StorageRouteTestData.LONG_TEXT.encode()
        client = _build_client(monkeypatch=monkeypatch)
        before = datetime.now(tz=UTC)

        (item,) = _resolve(client, _uri(StorageRouteTestData.TEXT_KEY))

        assert item["uri"] == _uri(StorageRouteTestData.TEXT_KEY)
        assert item["error"] is None
        assert item["content_type"] == "text/plain"
        url_text: str = item["url"]
        url = urlsplit(url_text)
        assert (url.scheme, url.netloc, url.path) == ("http", "testserver", f"/v1/storage/{StorageRouteTestData.TEXT_KEY}")
        assert set(parse_qs(url.query)) == {"expires", "signature"}
        expires_at = datetime.fromisoformat(item["expires_at"])
        assert 0 < (expires_at - before).total_seconds() <= DEFAULT_STORAGE_LINK_TTL_SECONDS + 1
        downloaded = _download(client, item["url"])
        assert downloaded.status_code == 200, downloaded.text
        assert downloaded.text == StorageRouteTestData.LONG_TEXT
        assert downloaded.headers["content-type"].startswith("text/plain")
        assert downloaded.headers["x-content-type-options"] == "nosniff"
        assert downloaded.headers["content-security-policy"] == "sandbox"

    def test_the_answer_has_the_platform_s_shape_field_for_field(self, monkeypatch: pytest.MonkeyPatch, storage: InMemoryStorageProvider) -> None:
        client = _build_client(monkeypatch=monkeypatch)

        response = client.post(_RESOLVE_PATH, json={"uris": [_uri(StorageRouteTestData.TEXT_KEY), "s3://elsewhere/value.txt"]})

        assert response.status_code == 200, response.text
        body = response.json()
        assert set(body) == StorageRouteTestData.PLATFORM_RESPONSE_FIELDS
        resolved, refused = body["items"]
        assert set(resolved) == StorageRouteTestData.PLATFORM_ITEM_FIELDS
        assert set(refused) == StorageRouteTestData.PLATFORM_ITEM_FIELDS
        assert (refused["url"], refused["expires_at"], refused["content_type"]) == (None, None, None)
        assert set(refused["error"]) == StorageRouteTestData.PLATFORM_REFUSAL_FIELDS
        assert (MAX_BULK_RESOLVE_URIS, STORAGE_URI_MAX_CHARS) == (
            StorageRouteTestData.PLATFORM_MAX_BULK_RESOLVE_URIS,
            StorageRouteTestData.PLATFORM_STORAGE_URI_MAX_CHARS,
        )
        assert not storage.root

    def test_each_reference_gets_its_verdict_in_request_order(self, monkeypatch: pytest.MonkeyPatch, storage: InMemoryStorageProvider) -> None:
        client = _build_client(monkeypatch=monkeypatch)
        uris = [
            _uri(StorageRouteTestData.IMAGE_KEY),
            _uri(f"{StorageRouteTestData.OTHER_USER_ID}/generated/0123456789abcdef.png"),
            *StorageRouteTestData.MALFORMED_URIS,
            _uri(StorageRouteTestData.IMAGE_KEY),
        ]

        items = _resolve(client, *uris)

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

    @pytest.mark.parametrize(
        ("auth_mode", "readable_scope", "foreign_scope"),
        [
            (AuthMode.NONE, "single-tenant", StorageRouteTestData.JWT_USER_ID),
            (AuthMode.API_KEY, "single-tenant", StorageRouteTestData.JWT_USER_ID),
            (AuthMode.JWT, StorageRouteTestData.JWT_USER_ID, "single-tenant"),
            (AuthMode.JWT, StorageRouteTestData.JWT_USER_ID, StorageRouteTestData.OTHER_USER_ID),
        ],
    )
    def test_each_auth_mode_resolves_only_under_its_caller_s_scope(
        self, monkeypatch: pytest.MonkeyPatch, storage: InMemoryStorageProvider, auth_mode: AuthMode, readable_scope: str, foreign_scope: str
    ) -> None:
        storage.root[f"{readable_scope}/generated/value.txt"] = b"mine"
        client = _build_client(monkeypatch=monkeypatch, auth_mode=auth_mode)
        own_reference = _uri(f"{readable_scope}/generated/value.txt")
        foreign_reference = _uri(f"{foreign_scope}/generated/value.txt")
        # A key equal to the scope names no object inside it, and a prefix of the scope's id is another scope.
        scope_itself = _uri(f"{readable_scope}/value.txt").rsplit("/", 1)[0]
        prefixed_scope = _uri(f"{readable_scope}x/generated/value.txt")

        own, foreign, prefixed = _resolve(client, own_reference, foreign_reference, prefixed_scope, headers=_headers(auth_mode=auth_mode))

        assert own["error"] is None, own
        assert _download(client, own["url"]).content == b"mine"
        for refused in (foreign, prefixed):
            assert refused["url"] is None, refused
            assert refused["error"] == {
                "code": "auth.forbidden",
                "detail": "The request's identity lacks 'read_scope_under_caller', which this operation needs.",
                "params": {"requirement": "read_scope_under_caller"},
            }
        (bare_scope,) = _resolve(client, scope_itself, headers=_headers(auth_mode=auth_mode))
        assert bare_scope["error"]["code"] == "pipelex.storage.uri_invalid"

    @pytest.mark.parametrize("auth_mode", [AuthMode.API_KEY, AuthMode.JWT])
    def test_resolving_needs_the_deployment_s_credential(self, monkeypatch: pytest.MonkeyPatch, auth_mode: AuthMode) -> None:
        client = _build_client(monkeypatch=monkeypatch, auth_mode=auth_mode)

        response = client.post(_RESOLVE_PATH, json={"uris": [_uri(StorageRouteTestData.TEXT_KEY)]})

        assert_problem(response, status=401, code="auth.missing_credential")

    def test_neither_route_is_served_when_the_runner_trusts_forwarded_identity(
        self, monkeypatch: pytest.MonkeyPatch, storage: InMemoryStorageProvider
    ) -> None:
        storage.root[StorageRouteTestData.TEXT_KEY] = b"a text"
        (item,) = _resolve(_build_client(monkeypatch=monkeypatch), _uri(StorageRouteTestData.TEXT_KEY))
        client = _build_client(monkeypatch=monkeypatch, trusts_forwarding=True)

        resolved = client.post(_RESOLVE_PATH, json={"uris": [_uri(StorageRouteTestData.TEXT_KEY)]}, headers={"X-User-Id": "single-tenant"})
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
        storage.root[StorageRouteTestData.TEXT_KEY] = b"a text"
        storage.root[StorageRouteTestData.MISSING_KEY] = b"another text"
        client = _build_client(monkeypatch=monkeypatch)
        if tampering == "expired":
            mocker.patch("pipelex_api.storage_links.STORAGE_LINK_TTL_SECONDS", -60)
        (item,) = _resolve(client, _uri(StorageRouteTestData.TEXT_KEY))
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
                path = f"/v1/storage/{StorageRouteTestData.MISSING_KEY}"
            case "not_a_number":
                query["expires"] = "１２３４５６７８９０"
            case "too_many_digits":
                # Past the digits Python's `int()` reads by default: a refused link, never a server error.
                query["expires"] = "9" * 5000
            case "expired":
                pass
            case "upload_signature":
                # A signature made for an upload target never holds for a download, even over the very message it binds.
                message = f"{StorageRouteTestData.TEXT_KEY}\n{query['expires']}"
                query["signature"] = link_signature(purpose=LinkPurpose.BLOB_UPLOAD, message=message)
            case _:
                pytest.fail(f"unknown tampering {tampering}")

        _assert_refused_link(client.get(path, params=query))

    def test_a_link_to_an_address_holding_no_file_is_a_404(self, monkeypatch: pytest.MonkeyPatch, storage: InMemoryStorageProvider) -> None:
        client = _build_client(monkeypatch=monkeypatch)
        (item,) = _resolve(client, _uri(StorageRouteTestData.MISSING_KEY))

        assert item["error"] is None
        problem = assert_problem(_download(client, item["url"]), status=404, code="pipelex.storage.object_missing")
        assert problem["detail"] == "No file is stored at the storage address this link names."
        assert not storage.root

    @pytest.mark.parametrize(
        ("key", "status", "code"),
        [
            pytest.param("single-tenant/generated", 404, "pipelex.storage.object_missing", id="a_directory"),
            pytest.param("single-tenant/generated/value.txt/inner.txt", 404, "pipelex.storage.object_missing", id="through_a_file"),
            pytest.param("single-tenant/" + "a" * 300 + ".txt", 403, "auth.forbidden", id="a_segment_no_filesystem_holds"),
        ],
    )
    @pytest.mark.asyncio(loop_scope="class")
    async def test_a_signed_link_naming_no_stored_file_is_never_a_server_error(
        self, monkeypatch: pytest.MonkeyPatch, mocker: MockerFixture, tmp_path: Path, key: str, status: int, code: str
    ) -> None:
        """Whatever key a validly signed link names, the local provider answers a refusal of the caller's, never a 500."""
        local = LocalStorageProvider(root_path=tmp_path)
        mocker.patch("pipelex_api.routes.storage.get_storage_provider", return_value=local)
        await local.store(b"a text", key="single-tenant/generated/value.txt", content_type="text/plain")
        client = _build_client(monkeypatch=monkeypatch)
        expires = str(int(time.time()) + 60)
        signature = link_signature(purpose=LinkPurpose.STORAGE_DOWNLOAD, message=f"{key}\n{expires}")

        response = client.get(f"/v1/storage/{quote(key, safe='/')}", params={"expires": expires, "signature": signature})

        assert_problem(response, status=status, code=code)

    def test_links_start_with_the_configured_public_base_url(self, monkeypatch: pytest.MonkeyPatch, storage: InMemoryStorageProvider) -> None:
        storage.root[StorageRouteTestData.TEXT_KEY] = b"a text"
        monkeypatch.setenv("PUBLIC_BASE_URL", StorageRouteTestData.PUBLIC_BASE_URL)
        client = _build_client(monkeypatch=monkeypatch)

        (item,) = _resolve(client, _uri(StorageRouteTestData.TEXT_KEY))

        assert str(item["url"]).startswith(f"https://runner.example.com/api/v1/storage/{StorageRouteTestData.TEXT_KEY}?")
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
    async def test_the_local_provider_serves_a_stored_text_an_image_and_a_document(
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

    @pytest.mark.asyncio(loop_scope="class")
    async def test_the_python_sdk_loads_a_stored_text_through_the_runner(
        self, monkeypatch: pytest.MonkeyPatch, storage: InMemoryStorageProvider
    ) -> None:
        """The composition every template's blocking path runs: resolve through the bulk route, fetch the link."""
        storage.root[StorageRouteTestData.TEXT_KEY] = StorageRouteTestData.LONG_TEXT.encode()
        client = _build_client(monkeypatch=monkeypatch)
        reference = {
            "url": _uri(StorageRouteTestData.TEXT_KEY),
            "size": len(StorageRouteTestData.LONG_TEXT),
            "mime_type": "text/plain",
            "preview": StorageRouteTestData.LONG_TEXT[:40],
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
            async def resolve_storage_urls_bulk(self, uris: list[str]) -> BulkResolvedStorageUrls:
                async with httpx.AsyncClient(transport=httpx.ASGITransport(app=asgi_app), base_url="http://testserver") as http:
                    answer = await http.post(_RESOLVE_PATH, json={"uris": uris})
                assert answer.status_code == 200, answer.text
                return BulkResolvedStorageUrls.model_validate(answer.json())

        def _storage_client(timeout_seconds: float) -> httpx.AsyncClient:
            return httpx.AsyncClient(transport=httpx.ASGITransport(app=asgi_app), timeout=timeout_seconds, follow_redirects=False)

        monkeypatch.setattr("pipelex_sdk.artifacts._new_storage_client", _storage_client)

        loaded = await load_stored_texts(_RunnerBulkResolveClient(), results, LoadStoredTextsOptions(allow_http=True))

        assert loaded.main_stuff == {"text": StorageRouteTestData.LONG_TEXT}
