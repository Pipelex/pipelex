"""The blob routes of the MTHDS Protocol: `POST /v1/blobs/missing` and `PUT /v1/blobs/{sha256}`.

A sender asks which of its blobs the runner lacks, uploads each to the signed target the answer names, then sends its
method by hash. These pin the wire: the targets, the write-once upload and its refusals, the scopes that keep one
caller's blobs apart from another's, the tree digest the runner answers in one lookup once it has read that tree in
full, and the `blob_store` flag `/v1/version` declares. The blob store is the in-memory one the conftest installs.
"""

from typing import Any
from urllib.parse import parse_qs, urlsplit

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from mthds.method_tree.digest import digest_of_contents, sha256_hex, tree_files_from_contents, tree_listing
from pipelex.tools.storage.in_memory_storage_provider import InMemoryStorageProvider
from pytest_mock import MockerFixture

from pipelex_api.exception_handlers import register_exception_handlers
from pipelex_api.routes import router as api_router
from pipelex_api.routes.blob_upload import router as blob_upload_router
from pipelex_api.routes.version import router as version_router
from tests.unit._constants import VALID_MTHDS
from tests.unit._problems import assert_problem

_TEMPLATE = b"<h1>A template</h1>"
_NOTES = b"Some notes"


def _build_client() -> TestClient:
    app = FastAPI()
    app.include_router(api_router, prefix="/v1")
    app.include_router(version_router, prefix="/v1")
    app.include_router(blob_upload_router, prefix="/v1")
    register_exception_handlers(app)
    return TestClient(app)


def _blob_ref(data: bytes) -> dict[str, Any]:
    return {"sha256": sha256_hex(data), "size": len(data)}


def _missing(client: TestClient, *blobs: bytes, digest: str | None = None, read_scope: str | None = None) -> list[dict[str, Any]]:
    body: dict[str, Any] = {"blobs": [_blob_ref(data) for data in blobs]}
    if digest is not None:
        body["digest"] = digest
    params = {"read_scope": read_scope} if read_scope is not None else None
    response = client.post("/v1/blobs/missing", json=body, params=params)
    assert response.status_code == 200, response.text
    missing: list[dict[str, Any]] = response.json()["missing"]
    return missing


def _upload(client: TestClient, *, target: dict[str, Any], data: bytes) -> Any:
    upload = target["upload"]
    return client.request(upload["method"], upload["url"], content=data, headers=upload["headers"])


def _assert_not_authorized(response: Any) -> None:
    """The refusal of an upload whose target this runner did not sign: what it lacks is a signed upload target."""
    problem = assert_problem(response, status=403, code="auth.forbidden")
    assert problem["params"] == {"requirement": "signed_upload_target"}


class TestBlobRoutes:
    def test_the_version_declares_a_blob_store(self) -> None:
        response = _build_client().get("/v1/version")

        assert response.status_code == 200, response.text
        assert response.json()["blob_store"] is True

    def test_each_blob_the_runner_lacks_comes_with_a_signed_upload_target(self) -> None:
        missing = _missing(_build_client(), _TEMPLATE, _NOTES)

        assert [(blob["sha256"], blob["size"]) for blob in missing] == [(sha256_hex(_TEMPLATE), len(_TEMPLATE)), (sha256_hex(_NOTES), len(_NOTES))]
        for blob in missing:
            upload = blob["upload"]
            assert upload["method"] == "PUT"
            assert upload["headers"] == {"content-type": "application/octet-stream"}
            url_text: str = upload["url"]
            url = urlsplit(url_text)
            assert url.path == f"/v1/blobs/{blob['sha256']}"
            assert set(parse_qs(url.query)) == {"scope", "expires", "signature"}

    def test_an_uploaded_blob_is_held_and_uploading_it_again_changes_nothing(self) -> None:
        client = _build_client()
        (target,) = _missing(client, _TEMPLATE)

        first = _upload(client, target=target, data=_TEMPLATE)
        again = _upload(client, target=target, data=_TEMPLATE)

        assert first.status_code == 204, first.text
        assert again.status_code == 204, again.text
        assert [blob["sha256"] for blob in _missing(client, _TEMPLATE, _NOTES)] == [sha256_hex(_NOTES)]

    def test_a_body_whose_hash_is_not_the_paths_is_refused_and_not_stored(self) -> None:
        client = _build_client()
        (target,) = _missing(client, _TEMPLATE)

        assert_problem(_upload(client, target=target, data=_NOTES), status=422, code="request.invalid", field="body")

        assert [blob["sha256"] for blob in _missing(client, _TEMPLATE, _NOTES)] == [sha256_hex(_TEMPLATE), sha256_hex(_NOTES)]

    @pytest.mark.parametrize("tampering", ["no_query", "forged_signature", "another_scope", "another_hash"])
    def test_an_upload_without_a_valid_target_is_refused(self, tampering: str) -> None:
        client = _build_client()
        (target,) = _missing(client, _TEMPLATE)
        url_text: str = target["upload"]["url"]
        url = urlsplit(url_text)
        query: dict[str, str] = {name: values[0] for name, values in parse_qs(url.query).items()}
        path: str = url.path
        match tampering:
            case "no_query":
                query = {}
            case "forged_signature":
                query["signature"] = "0" * 64
            case "another_scope":
                query["scope"] = "someone-else"
            case "another_hash":
                path = f"/v1/blobs/{sha256_hex(_NOTES)}"
            case _:
                pytest.fail(f"unknown tampering {tampering}")
        data = _NOTES if tampering == "another_hash" else _TEMPLATE

        response = client.put(path, params=query, content=data, headers={"content-type": "application/octet-stream"})

        _assert_not_authorized(response)
        assert len(_missing(client, _TEMPLATE, _NOTES)) == 2

    def test_an_expired_target_is_refused(self, mocker: MockerFixture) -> None:
        mocker.patch("pipelex_api.blob_upload.BLOB_UPLOAD_URL_TTL_SECONDS", -60)
        client = _build_client()
        (target,) = _missing(client, _TEMPLATE)

        _assert_not_authorized(_upload(client, target=target, data=_TEMPLATE))

    def test_an_upload_past_the_per_file_limit_is_refused(self, mocker: MockerFixture) -> None:
        client = _build_client()
        (target,) = _missing(client, _TEMPLATE)
        mocker.patch("pipelex_api.routes.blob_upload.MAX_METHOD_TREE_FILE_BYTES", len(_TEMPLATE) - 1)

        problem = assert_problem(_upload(client, target=target, data=_TEMPLATE), status=413, code="request.too_large")
        assert problem["params"] == {"limit": len(_TEMPLATE) - 1, "size": len(_TEMPLATE)}

    def test_one_hash_listed_with_two_sizes_is_refused(self) -> None:
        body = {"blobs": [_blob_ref(_TEMPLATE), {"sha256": sha256_hex(_TEMPLATE), "size": len(_TEMPLATE) + 1}]}

        assert_problem(_build_client().post("/v1/blobs/missing", json=body), status=422, code="request.invalid", field="blobs")

    @pytest.mark.parametrize("size", [12.0, 12.5, "12", True])
    def test_a_size_that_is_not_a_json_integer_is_refused(self, size: Any) -> None:
        body = {"blobs": [{"sha256": sha256_hex(_TEMPLATE), "size": size}]}

        response = _build_client().post("/v1/blobs/missing", json=body)

        assert response.status_code == 422, response.text

    def test_blobs_past_the_tree_limits_are_refused_before_any_upload(self, mocker: MockerFixture) -> None:
        mocker.patch("pipelex_api.method_tree_request.MAX_METHOD_TREE_FILES", 1)

        response = _build_client().post("/v1/blobs/missing", json={"blobs": [_blob_ref(_TEMPLATE), _blob_ref(_NOTES)]})

        problem = assert_problem(response, status=422, code="method.package_invalid")
        assert problem["params"] == {"reason": "too_many_files", "limit": 1}

    def test_one_scopes_blobs_are_not_held_for_another(self) -> None:
        client = _build_client()
        (target,) = _missing(client, _TEMPLATE, read_scope="org-a")
        assert _upload(client, target=target, data=_TEMPLATE).status_code == 204

        assert _missing(client, _TEMPLATE, read_scope="org-a") == []
        assert [blob["sha256"] for blob in _missing(client, _TEMPLATE, read_scope="org-b")] == [sha256_hex(_TEMPLATE)]
        assert [blob["sha256"] for blob in _missing(client, _TEMPLATE)] == [sha256_hex(_TEMPLATE)]

    def test_a_read_scope_that_is_not_a_scope_is_refused(self) -> None:
        response = _build_client().post("/v1/blobs/missing", json={"blobs": []}, params={"read_scope": "../escape"})

        assert_problem(response, status=422, code="request.invalid", field="read_scope")

    def test_a_tree_read_in_full_is_answered_by_its_digest(self) -> None:
        """Once a request sent the tree, the runner holds its listing, and asking with the tree's digest is one lookup."""
        client = _build_client()
        contents = {"main.mthds": VALID_MTHDS.encode("utf-8"), "notes.txt": _NOTES}
        digest = digest_of_contents(contents)
        assert len(_missing(client, *contents.values(), digest=digest)) == 2

        validated = client.post("/v1/validate", json={"files": {"main.mthds": VALID_MTHDS, "notes.txt": _NOTES.decode("utf-8")}})

        assert validated.status_code == 200, validated.text
        assert validated.json()["is_valid"] is True, validated.text
        assert _missing(client, *contents.values(), digest=digest) == []
        assert _missing(client, *contents.values()) == []

    def test_an_uploaded_listing_never_records_its_tree(self) -> None:
        """Anyone can upload bytes that happen to form a listing, so an upload never stands for a tree held in full."""
        client = _build_client()
        contents = {"main.mthds": VALID_MTHDS.encode("utf-8"), "notes.txt": _NOTES}
        listing = tree_listing(tree_files_from_contents(contents))
        (target,) = _missing(client, listing)
        assert _upload(client, target=target, data=listing).status_code == 204

        missing = _missing(client, *contents.values(), digest=digest_of_contents(contents))

        assert [blob["sha256"] for blob in missing] == [sha256_hex(data) for data in contents.values()]

    @pytest.mark.parametrize(
        ("name", "value"),
        [
            pytest.param("signature", "é" * 64, id="signature_outside_ascii"),
            pytest.param("expires", "soon", id="expires_not_a_number"),
            pytest.param("expires", "١٢٣", id="expires_in_other_digits"),
            pytest.param("expires", "-5", id="expires_signed"),
        ],
    )
    def test_a_malformed_target_is_refused_as_no_valid_target(self, name: str, value: str) -> None:
        """Every part of the query is the caller's text: one no target of this runner holds is a 403, never a server error."""
        client = _build_client()
        (target,) = _missing(client, _TEMPLATE)
        url = urlsplit(str(target["upload"]["url"]))
        query: dict[str, str] = {key: values[0] for key, values in parse_qs(url.query).items()}
        query[name] = value

        response = client.put(url.path, params=query, content=_TEMPLATE, headers={"content-type": "application/octet-stream"})

        _assert_not_authorized(response)

    def test_upload_targets_start_with_the_configured_public_base_url(self, mocker: MockerFixture) -> None:
        """Behind a proxy terminating TLS, the URL a request arrived at is not the one a sender reaches."""
        mocker.patch("pipelex_api.blob_upload.get_optional_env", return_value="https://runner.example.com/api/")
        client = _build_client()

        (target,) = _missing(client, _TEMPLATE)

        url_text: str = target["upload"]["url"]
        assert url_text.startswith(f"https://runner.example.com/api/v1/blobs/{sha256_hex(_TEMPLATE)}?")
        url = urlsplit(url_text)
        query: dict[str, str] = {key: values[0] for key, values in parse_qs(url.query).items()}
        uploaded = client.put(f"/v1/blobs/{sha256_hex(_TEMPLATE)}", params=query, content=_TEMPLATE, headers=target["upload"]["headers"])
        assert uploaded.status_code == 204, uploaded.text

    def test_without_a_public_base_url_targets_start_with_the_request_s_url(self) -> None:
        (target,) = _missing(_build_client(), _TEMPLATE)

        assert str(target["upload"]["url"]).startswith(f"http://testserver/v1/blobs/{sha256_hex(_TEMPLATE)}?")

    def test_a_public_base_url_that_is_not_an_http_url_is_a_configuration_error(self, mocker: MockerFixture) -> None:
        mocker.patch("pipelex_api.blob_upload.get_optional_env", return_value="runner.example.com")

        response = _build_client().post("/v1/blobs/missing", json={"blobs": [_blob_ref(_TEMPLATE)]})

        assert_problem(response, status=500, code="runtime.misconfigured")

    def test_a_blob_held_at_another_size_is_listed_for_its_upload_to_write_over(self, blob_storage: InMemoryStorageProvider) -> None:
        """Bytes held short, as a storage that does not publish writes whole could leave them, are asked for again and repaired."""
        client = _build_client()
        blob_storage.root[f"single-tenant/blobs/{sha256_hex(_TEMPLATE)}"] = _TEMPLATE[:5]

        (target,) = _missing(client, _TEMPLATE)
        uploaded = _upload(client, target=target, data=_TEMPLATE)

        assert uploaded.status_code == 204, uploaded.text
        assert blob_storage.root[f"single-tenant/blobs/{sha256_hex(_TEMPLATE)}"] == _TEMPLATE
        assert _missing(client, _TEMPLATE) == []

    def test_a_held_digest_answers_alone_only_for_blobs_of_its_tree(self) -> None:
        """A digest the runner holds says nothing of blobs outside its tree, which are looked up one by one."""
        client = _build_client()
        contents = {"main.mthds": VALID_MTHDS.encode("utf-8"), "notes.txt": _NOTES}
        validated = client.post("/v1/validate", json={"files": {"main.mthds": VALID_MTHDS, "notes.txt": _NOTES.decode("utf-8")}})
        assert validated.status_code == 200, validated.text

        missing = _missing(client, *contents.values(), _TEMPLATE, digest=digest_of_contents(contents))

        assert [blob["sha256"] for blob in missing] == [sha256_hex(_TEMPLATE)]
