"""Tests for `POST /v1/pipe-io` — a method's three I/O artifacts off the resolved crate, with no dry run.

Pins `docs/specs/pipelex-codegen.md#the-pipe-io-route` (workspace root): the route resolves the
closure through the crate routes' static core, selects a pipe with the per-pipe routes' chain, and
returns `pipe_io_contracts`, `input_form` and `output_form` keyed by qualified `pipe_ref`, beside
`pipe_ref`, `default_pipe_ref`, `pending_signatures`, `is_runnable` and, on request, the closure's
files. The pinning cases hold each artifact equal to `/v1/validate`'s same-named view for the same
closure and pipe; the teardown cases hold the loaded-on-success contract on every exit.
"""

from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pipelex.interpreter_hub import get_library_manager
from pipelex.pipeline.exceptions import PipeIOContractError
from pytest_mock import MockerFixture

from api.exception_handlers import register_exception_handlers
from api.routes import router as api_router
from tests.unit._constants import (
    COLLIDING_ECHO_LIST_MTHDS,
    HEADER_AND_DEFINITION_BATCH,
    INVALID_MAIN_PIPE_MTHDS,
    NO_MAIN_PIPE_MTHDS,
    SECOND_MAIN_PIPE_MTHDS,
    SHAPES_MTHDS,
    SIBLING_MTHDS,
    SIGNATURE_MTHDS,
    SIGNATURE_ONLY_BATCH,
    STUB_METHOD_ADDRESS,
    STUB_METHOD_MANIFEST_MAIN_PIPE_SHOUT,
    STUB_METHOD_MANIFEST_NOMAIN_ENTRY,
    VALID_MTHDS,
)

PIPE_IO_PATH = "/v1/pipe-io"

# The address-form reference the stubbed clone (`install_method_package`) answers to.
STUB_METHOD_REF = f"{STUB_METHOD_ADDRESS}@v0.1.0"

# The three artifact maps the valid arm carries, sharing one key set.
ARTIFACT_FIELDS = ("pipe_io_contracts", "input_form", "output_form")

# The `error_type`s of a no-verdict 422: a malformed request, and the two pipe-selection refusals,
# which carry the pipelex entry-lookup class names the run routes answer for the same failure.
REQUEST_SHAPE_ERROR = "ValidationError"
PIPE_NOT_FOUND_ERROR = "EntryPipeNotFoundError"
PIPE_AMBIGUOUS_ERROR = "EntryPipeAmbiguousError"

# Every field only the valid arm carries: the invalid arm is the crate verdict alone.
VALID_ARM_ONLY_FIELDS = ("pipe_ref", "default_pipe_ref", *ARTIFACT_FIELDS, "pending_signatures", "is_runnable", "files")


def _build_client() -> TestClient:
    app = FastAPI()
    app.include_router(api_router, prefix="/v1")
    register_exception_handlers(app)
    return TestClient(app)


def _files(*contents: str) -> list[dict[str, str]]:
    """Inline `files[]` items, each with a distinct `source` so `/v1/validate` can be sent the same labels."""
    return [{"content": content, "source": f"bundle_{index}.mthds"} for index, content in enumerate(contents)]


def _valid_arm(client: TestClient, payload: dict[str, Any]) -> dict[str, Any]:
    response = client.post(PIPE_IO_PATH, json=payload)
    assert response.status_code == 200, response.text
    body: dict[str, Any] = response.json()
    assert body["is_valid"] is True, response.text
    assert "validation_errors" not in body
    return body


def _assert_keys(body: dict[str, Any], expected: set[str]) -> None:
    for field_name in ARTIFACT_FIELDS:
        assert set(body[field_name]) == expected, f"`{field_name}` keyed by {sorted(body[field_name])}, expected {sorted(expected)}"


def _assert_input_422(response: Any, *, error_type: str) -> str:
    """Assert a no-verdict input 422 of the given `error_type`, and return its detail."""
    assert response.status_code == 422, response.text
    assert response.headers["content-type"] == "application/problem+json"
    problem = response.json()
    assert problem["error_type"] == error_type, response.text
    assert problem["error_domain"] == "input"
    assert "is_valid" not in problem
    detail: str = problem["detail"]
    return detail


class TestPipeIoRoute:
    def test_one_pipe_by_default(self):
        client = _build_client()
        body = _valid_arm(client, {"files": _files(VALID_MTHDS, SIBLING_MTHDS)})
        assert body["pipe_ref"] == "smoke.echo"
        assert body["default_pipe_ref"] == "smoke.echo", "an omitted pipe_ref always answers pipe_ref == default_pipe_ref"
        _assert_keys(body, {"smoke.echo"})
        assert body["pending_signatures"] == []
        assert body["is_runnable"] is True
        assert "files" not in body, "files is absent, not empty, without include_files"

    def test_a_named_pipe_is_described_beside_the_methods_own_entry_pipe(self):
        client = _build_client()
        body = _valid_arm(client, {"files": _files(VALID_MTHDS, SIBLING_MTHDS), "pipe_ref": "smoke.wrap_echo"})
        assert body["pipe_ref"] == "smoke.wrap_echo"
        assert body["default_pipe_ref"] == "smoke.echo"
        _assert_keys(body, {"smoke.wrap_echo"})

    def test_the_dump_keeps_null_members(self):
        # Never `exclude_none`: the contracts' `item_count: null` must survive, or the maps stop
        # equalling `/v1/validate`'s, which keeps it.
        client = _build_client()
        body = _valid_arm(client, {"files": _files(VALID_MTHDS)})
        output_contract = body["pipe_io_contracts"]["smoke.echo"]["output"]
        assert "item_count" in output_contract
        assert output_contract["item_count"] is None

    @pytest.mark.parametrize(
        ("contents", "request_fields", "expected_pipe_ref", "expected_default", "expected_keys"),
        [
            pytest.param(
                (VALID_MTHDS, SIBLING_MTHDS),
                {},
                "smoke.echo",
                "smoke.echo",
                {"smoke.echo", "smoke.wrap_echo"},
                id="with-entry-pipe",
            ),
            pytest.param(
                (VALID_MTHDS, SIBLING_MTHDS),
                {"pipe_ref": "smoke.wrap_echo"},
                "smoke.wrap_echo",
                "smoke.echo",
                {"smoke.echo", "smoke.wrap_echo"},
                id="with-entry-pipe-and-named-pipe",
            ),
            pytest.param((NO_MAIN_PIPE_MTHDS,), {}, None, None, {"nomain.echo"}, id="without-entry-pipe"),
            pytest.param((VALID_MTHDS, SECOND_MAIN_PIPE_MTHDS), {}, None, None, {"smoke.echo", "other.shout"}, id="with-several-entry-pipes"),
            pytest.param(
                (VALID_MTHDS, SECOND_MAIN_PIPE_MTHDS),
                {"pipe_ref": "other.shout"},
                "other.shout",
                None,
                {"smoke.echo", "other.shout"},
                id="with-several-entry-pipes-and-named-pipe",
            ),
        ],
    )
    def test_all_pipes_describes_every_pipe_and_never_demands_an_entry_pipe(
        self,
        contents: tuple[str, ...],
        request_fields: dict[str, Any],
        expected_pipe_ref: str | None,
        expected_default: str | None,
        expected_keys: set[str],
    ):
        client = _build_client()
        body = _valid_arm(client, {"files": _files(*contents), "all_pipes": True, **request_fields})
        assert "pipe_ref" in body
        assert body["pipe_ref"] == expected_pipe_ref
        assert "default_pipe_ref" in body
        assert body["default_pipe_ref"] == expected_default
        _assert_keys(body, expected_keys)

    @pytest.mark.parametrize(
        ("contents", "pipe_ref"),
        [
            pytest.param((NO_MAIN_PIPE_MTHDS,), "nomain.echo", id="no-main-pipe"),
            pytest.param((VALID_MTHDS, SECOND_MAIN_PIPE_MTHDS), "other.shout", id="several-main-pipes"),
        ],
    )
    def test_default_pipe_ref_is_a_stated_null_without_one_entry_pipe(self, contents: tuple[str, ...], pipe_ref: str):
        # Where several domains declare a `main_pipe`, `/v1/validate`'s run default names the first;
        # this route's chain refuses to choose, so its field is null rather than a guess.
        client = _build_client()
        body = _valid_arm(client, {"files": _files(*contents), "pipe_ref": pipe_ref})
        assert body["pipe_ref"] == pipe_ref
        assert "default_pipe_ref" in body
        assert body["default_pipe_ref"] is None
        _assert_keys(body, {pipe_ref})

    def test_default_pipe_ref_is_the_manifest_main_pipe(self, install_method_package: Callable[..., Path]):
        # The package's bundle declares no main_pipe; only its manifest names the entry pipe.
        install_method_package(files={"documents.mthds": NO_MAIN_PIPE_MTHDS}, manifest_toml=STUB_METHOD_MANIFEST_NOMAIN_ENTRY)
        client = _build_client()
        body = _valid_arm(client, {"method_ref": STUB_METHOD_REF})
        assert body["pipe_ref"] == "nomain.echo"
        assert body["default_pipe_ref"] == "nomain.echo"
        _assert_keys(body, {"nomain.echo"})

    def test_the_manifest_main_pipe_outranks_the_closures_declarations(self, install_method_package: Callable[..., Path]):
        # Two declaring domains would leave the closure without a default; the manifest settles it,
        # and it stays the default when the caller names another pipe.
        install_method_package(
            files={"smoke.mthds": VALID_MTHDS, "other.mthds": SECOND_MAIN_PIPE_MTHDS},
            manifest_toml=STUB_METHOD_MANIFEST_MAIN_PIPE_SHOUT,
        )
        client = _build_client()
        defaulted = _valid_arm(client, {"method_ref": STUB_METHOD_REF})
        assert defaulted["pipe_ref"] == "other.shout"
        assert defaulted["default_pipe_ref"] == "other.shout"
        named = _valid_arm(client, {"method_ref": STUB_METHOD_REF, "pipe_ref": "smoke.echo"})
        assert named["pipe_ref"] == "smoke.echo"
        assert named["default_pipe_ref"] == "other.shout"

    def test_a_manifest_main_pipe_the_closure_lacks_is_no_default_even_beside_a_declaration(self, install_method_package: Callable[..., Path]):
        # The chain stops at the manifest link: `echo` is not in the closure, and `other`'s own
        # declared `main_pipe` is not a fall-through. A whole-method request still answers.
        install_method_package(files={"other.mthds": SECOND_MAIN_PIPE_MTHDS})
        client = _build_client()
        body = _valid_arm(client, {"method_ref": STUB_METHOD_REF, "all_pipes": True})
        assert body["pipe_ref"] is None
        assert body["default_pipe_ref"] is None
        _assert_keys(body, {"other.shout"})
        detail = _assert_input_422(client.post(PIPE_IO_PATH, json={"method_ref": STUB_METHOD_REF}), error_type=PIPE_NOT_FOUND_ERROR)
        assert "manifest" in detail
        assert "not found" in detail

    def test_an_ambiguous_manifest_main_pipe_says_ambiguous(self, install_method_package: Callable[..., Path]):
        # The manifest names `echo`, declared by both `smoke` and `twin`: the selection refuses it as
        # ambiguous, naming both candidates, and a whole-method request states no default.
        install_method_package(files={"smoke.mthds": VALID_MTHDS, "twin.mthds": COLLIDING_ECHO_LIST_MTHDS})
        client = _build_client()
        detail = _assert_input_422(client.post(PIPE_IO_PATH, json={"method_ref": STUB_METHOD_REF}), error_type=PIPE_AMBIGUOUS_ERROR)
        assert "manifest" in detail
        assert "several domains" in detail
        assert "smoke.echo" in detail
        assert "twin.echo" in detail
        assert "not found" not in detail, f"an ambiguous selector must not read as a missing pipe: {detail}"
        body = _valid_arm(client, {"method_ref": STUB_METHOD_REF, "all_pipes": True})
        assert body["pipe_ref"] is None
        assert body["default_pipe_ref"] is None

    @pytest.mark.parametrize("all_pipes", [False, True], ids=["one-pipe", "all-pipes"])
    def test_an_ambiguous_pipe_ref_says_ambiguous(self, all_pipes: bool):
        client = _build_client()
        payload = {"files": _files(VALID_MTHDS, COLLIDING_ECHO_LIST_MTHDS), "pipe_ref": "echo", "all_pipes": all_pipes}
        detail = _assert_input_422(client.post(PIPE_IO_PATH, json=payload), error_type=PIPE_AMBIGUOUS_ERROR)
        assert "Pipe 'echo'" in detail
        assert "several domains" in detail
        assert "smoke.echo" in detail
        assert "twin.echo" in detail
        assert "not found" not in detail, f"an ambiguous selector must not read as a missing pipe: {detail}"

    def test_runnability_facts_match_validate(self):
        client = _build_client()
        body = _valid_arm(client, {"files": _files(SIGNATURE_MTHDS)})
        assert body["pipe_ref"] == "sig_api.caller_seq"
        assert body["pending_signatures"] == ["sig_api.summary_sig"]
        assert body["is_runnable"] is False

        validate_response = client.post("/v1/validate", json={"mthds_contents": [SIGNATURE_MTHDS], "allow_signatures": True})
        assert validate_response.status_code == 200, validate_response.text
        validate_body = validate_response.json()
        assert body["pending_signatures"] == validate_body["pending_signatures"]
        assert body["is_runnable"] == validate_body["is_runnable"]

    @pytest.mark.parametrize("include_files", [False, None], ids=["declined", "omitted"])
    def test_files_are_absent_unless_requested(self, include_files: bool | None):
        client = _build_client()
        payload: dict[str, Any] = {"files": _files(VALID_MTHDS)}
        if include_files is not None:
            payload["include_files"] = include_files
        body = _valid_arm(client, payload)
        assert "files" not in body

    def test_include_files_echoes_the_inline_files_in_the_request_shape(self):
        # A `source` the request omitted stays omitted: the echo is the request's own shape.
        client = _build_client()
        files = [{"content": VALID_MTHDS, "source": "main.mthds"}, {"content": SIBLING_MTHDS}]
        body = _valid_arm(client, {"files": files, "include_files": True})
        assert body["files"] == files

    def test_include_files_echoes_a_method_refs_mthds_files_with_relative_paths(self, install_method_package: Callable[..., Path]):
        # Only the package's `.mthds` files travel, each under its path relative to the package root.
        install_method_package(files={"documents.mthds": VALID_MTHDS, "steps/wrap.mthds": SIBLING_MTHDS, "README.md": "# Not a bundle\n"})
        client = _build_client()
        body = _valid_arm(client, {"method_ref": STUB_METHOD_REF, "include_files": True})
        assert sorted(body["files"], key=lambda item: item["source"]) == [
            {"content": VALID_MTHDS, "source": "documents.mthds"},
            {"content": SIBLING_MTHDS, "source": "steps/wrap.mthds"},
        ]

    @pytest.mark.parametrize(
        "request_fields",
        [
            pytest.param({}, id="default-selection"),
            pytest.param({"pipe_ref": "broken.not_a_pipe", "include_files": True}, id="unknown-ref-and-files"),
            pytest.param({"all_pipes": True, "include_files": True}, id="all-pipes-and-files"),
        ],
    )
    def test_invalid_closure_is_the_crate_verdict_carrying_nothing_else(self, request_fields: dict[str, Any]):
        # The closure is resolved before any pipe is selected, so even a pipe_ref naming nothing
        # answers the invalid verdict rather than a 422.
        client = _build_client()
        response = client.post(PIPE_IO_PATH, json={"files": [{"content": INVALID_MAIN_PIPE_MTHDS, "source": "broken.mthds"}], **request_fields})
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["is_valid"] is False
        assert body["validation_errors"]
        assert body["validation_errors"][0]["source"] == "broken.mthds"
        assert body["message"]
        for field_name in VALID_ARM_ONLY_FIELDS:
            assert field_name not in body, f"the invalid arm never carries `{field_name}`"

    @pytest.mark.parametrize(
        ("contents", "request_fields", "error_type", "detail_fragment", "fix_fragment"),
        [
            pytest.param(
                (VALID_MTHDS,), {"pipe_ref": "smoke.not_a_pipe"}, PIPE_NOT_FOUND_ERROR, "not found", "Check the pipe code", id="unknown-ref"
            ),
            pytest.param(
                (VALID_MTHDS,),
                {"pipe_ref": "smoke.not_a_pipe", "all_pipes": True},
                PIPE_NOT_FOUND_ERROR,
                "not found",
                "Check the pipe code",
                id="unknown-ref-under-all-pipes",
            ),
            pytest.param(
                (NO_MAIN_PIPE_MTHDS,),
                {},
                PIPE_NOT_FOUND_ERROR,
                "declares no `main_pipe`",
                "Send a `pipe_ref` naming the pipe to select",
                id="no-entry-pipe",
            ),
            pytest.param(
                (VALID_MTHDS, SECOND_MAIN_PIPE_MTHDS),
                {},
                PIPE_AMBIGUOUS_ERROR,
                "several `main_pipe`s",
                "one of the declared `main_pipe`s",
                id="several-entry-pipes",
            ),
        ],
    )
    def test_selection_refusals_carry_the_entry_lookup_error_type(
        self, contents: tuple[str, ...], request_fields: dict[str, Any], error_type: str, detail_fragment: str, fix_fragment: str
    ):
        # A selection refusal is an input 422 like a malformed request, but its `error_type` is the
        # pipelex entry-lookup class that names the failure, so a client branches on it; its problem
        # `type` names the selection too, and its `user_action` names the fix for this very miss —
        # a default chain that finds no entry pipe, or several, is no pipe-code typo.
        client = _build_client()
        response = client.post(PIPE_IO_PATH, json={"files": _files(*contents), **request_fields})
        detail = _assert_input_422(response, error_type=error_type)
        assert detail_fragment in detail
        problem = response.json()
        assert problem["type"] != client.post(PIPE_IO_PATH, json={}).json()["type"], "a selection refusal must not share the request-shape type"
        assert problem["user_action"]["kind"] == "change_input"
        assert fix_fragment in problem["user_action"]["detail"]

    @pytest.mark.parametrize(
        "payload",
        [
            pytest.param({}, id="neither"),
            pytest.param({"pipe_ref": "smoke.echo"}, id="neither-with-pipe-ref"),
            pytest.param({"files": [{"content": VALID_MTHDS}], "method_ref": STUB_METHOD_REF}, id="both"),
        ],
    )
    def test_closure_selector_xor_is_a_request_shape_422(self, payload: dict[str, Any]):
        client = _build_client()
        _assert_input_422(client.post(PIPE_IO_PATH, json=payload), error_type=REQUEST_SHAPE_ERROR)

    @pytest.mark.parametrize(
        ("contents", "request_fields"),
        [
            pytest.param((VALID_MTHDS,), {}, id="entry-pipe"),
            pytest.param((VALID_MTHDS, SIBLING_MTHDS), {"pipe_ref": "smoke.wrap_echo"}, id="named-pipe"),
            pytest.param((VALID_MTHDS, SIBLING_MTHDS), {"all_pipes": True}, id="all-pipes"),
            pytest.param((VALID_MTHDS, SECOND_MAIN_PIPE_MTHDS), {"all_pipes": True}, id="several-main-pipes"),
            pytest.param((NO_MAIN_PIPE_MTHDS,), {"pipe_ref": "nomain.echo"}, id="no-main-pipe"),
            pytest.param((SHAPES_MTHDS,), {}, id="multiplicity-and-structure"),
            pytest.param((SIGNATURE_MTHDS,), {"all_pipes": True}, id="pending-signature"),
            pytest.param(tuple(SIGNATURE_ONLY_BATCH), {"all_pipes": True}, id="signature-only-batch"),
            pytest.param(tuple(HEADER_AND_DEFINITION_BATCH), {"all_pipes": True}, id="header-and-definition"),
        ],
    )
    def test_artifacts_equal_validate_views(self, contents: tuple[str, ...], request_fields: dict[str, Any]):
        # The pinning test: each map equals `/v1/validate`'s same-named view restricted to the same
        # keys. Validate is asked first, so a closure it would refuse fails here rather than passing
        # vacuously; `allow_signatures` lets it accept the signature closures this route accepts.
        files = _files(*contents)
        client = _build_client()
        validate_response = client.post(
            "/v1/validate",
            json={
                "mthds_contents": [item["content"] for item in files],
                "mthds_sources": [item["source"] for item in files],
                "views": ["input_form", "output_form"],
                "allow_signatures": True,
            },
        )
        assert validate_response.status_code == 200, validate_response.text
        validate_body = validate_response.json()
        assert validate_body["is_valid"] is True, validate_response.text

        body = _valid_arm(client, {"files": files, **request_fields})
        self._assert_maps_equal_validate(body, validate_body)

    def test_artifacts_equal_validate_views_by_method_ref(self, install_method_package: Callable[..., Path]):
        # The stub package holds `.mthds` files alone, so validate by `method_ref` loads exactly the
        # closure this route reads (validate would also load a package's other files).
        install_method_package(files={"documents.mthds": VALID_MTHDS, "steps/wrap.mthds": SIBLING_MTHDS})
        client = _build_client()
        validate_response = client.post("/v1/validate", json={"method_ref": STUB_METHOD_REF, "views": ["input_form", "output_form"]})
        assert validate_response.status_code == 200, validate_response.text
        validate_body = validate_response.json()
        assert validate_body["is_valid"] is True, validate_response.text

        body = _valid_arm(client, {"method_ref": STUB_METHOD_REF, "all_pipes": True})
        _assert_keys(body, {"smoke.echo", "smoke.wrap_echo"})
        self._assert_maps_equal_validate(body, validate_body)

    def _assert_maps_equal_validate(self, body: dict[str, Any], validate_body: dict[str, Any]) -> None:
        keys = set(body["pipe_io_contracts"])
        assert keys, "the valid arm describes at least one pipe"
        _assert_keys(body, keys)
        for field_name in ARTIFACT_FIELDS:
            validate_map = validate_body[field_name]
            assert keys <= set(validate_map), f"`{field_name}` names pipes /v1/validate does not: {sorted(keys - set(validate_map))}"
            assert body[field_name] == {ref: validate_map[ref] for ref in keys}, f"`{field_name}` diverges from /v1/validate's view"

    @pytest.mark.parametrize(
        ("payload", "expected_status"),
        [
            pytest.param({"files": [{"content": VALID_MTHDS}]}, 200, id="valid-arm"),
            pytest.param({"files": [{"content": NO_MAIN_PIPE_MTHDS}], "all_pipes": True, "include_files": True}, 200, id="all-pipes"),
            pytest.param({"files": [{"content": VALID_MTHDS}], "pipe_ref": "smoke.not_a_pipe"}, 422, id="selection-422"),
            pytest.param({"files": [{"content": NO_MAIN_PIPE_MTHDS}]}, 422, id="no-entry-pipe-422"),
        ],
    )
    def test_every_exit_tears_its_library_down(self, mocker: MockerFixture, payload: dict[str, Any], expected_status: int):
        # The engine core leaves the library loaded + current on success; the route owns teardown on
        # every exit after it, a selection refusal included. Conservation: opens == teardowns.
        library_manager = get_library_manager()
        open_spy = mocker.spy(library_manager, "open_library")
        teardown_spy = mocker.spy(library_manager, "teardown")

        client = _build_client()
        response = client.post(PIPE_IO_PATH, json=payload)

        assert response.status_code == expected_status, response.text
        assert open_spy.call_count == 1
        created_library_id, _ = open_spy.spy_return
        teardown_spy.assert_called_once_with(library_id=created_library_id)

    def test_an_underivable_artifact_is_a_no_verdict_500_and_still_tears_down(self, mocker: MockerFixture):
        # `PipeIOContractError` is left to the global handler, exactly as on `/v1/validate`: a fault of
        # the tool, not a verdict about the method. The library is still torn down.
        mocker.patch(
            "api.routes.pipelex.pipe_io.build_pipe_io_artifacts",
            side_effect=PipeIOContractError(message="Failed to render the JSON Schema for the output of pipe 'smoke.echo'"),
        )
        library_manager = get_library_manager()
        open_spy = mocker.spy(library_manager, "open_library")
        teardown_spy = mocker.spy(library_manager, "teardown")

        client = _build_client()
        response = client.post(PIPE_IO_PATH, json={"files": [{"content": VALID_MTHDS}]})

        assert response.status_code == 500, response.text
        assert response.headers["content-type"] == "application/problem+json"
        assert "is_valid" not in response.json()
        assert open_spy.call_count == 1
        assert teardown_spy.call_count == 1
