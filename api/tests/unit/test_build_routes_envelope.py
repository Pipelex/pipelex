"""Envelope tests for the migrated `/v1/build/*` projections.

Pins the Phase-2/3 migration: the three build routes ride the shared `files[]` XOR `method_ref`
closure selector (`MthdsFilesRequest`) plus an optional qualified `pipe_ref` that defaults with the
run routes' precedence — the fetched package manifest's `main_pipe` on a `method_ref` request, else
the closure's declared `main_pipe`; `/build/{inputs,output}` resolve their crate **statically** (no
dry-run sweep, so no `allow_signatures`), while `/build/runner` keeps both. Verdicts stay on the
`/validate` discipline — 200 discriminated on `is_valid`, non-2xx only for no-verdict conditions.
"""

from collections.abc import Callable
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pipelex.interpreter_hub import get_library_manager
from pytest_mock import MockerFixture

from api.exception_handlers import register_exception_handlers
from api.routes import router as api_router
from tests.unit._constants import (
    COLLIDING_ECHO_LIST_MTHDS,
    INVALID_MAIN_PIPE_MTHDS,
    NO_INPUTS_MTHDS,
    NO_MAIN_PIPE_MTHDS,
    SECOND_MAIN_PIPE_MTHDS,
    SIGNATURE_MTHDS,
    STUB_METHOD_ADDRESS,
    STUB_METHOD_MANIFEST_MAIN_PIPE_SHOUT,
    STUB_METHOD_MANIFEST_NO_MAIN_PIPE,
    VALID_MTHDS,
)

BUILD_PATHS = ["/v1/build/inputs", "/v1/build/output", "/v1/build/runner"]

# The address-form reference the stubbed clone (`install_method_package`) answers to.
STUB_METHOD_REF = f"{STUB_METHOD_ADDRESS}@v0.1.0"


def _build_client() -> TestClient:
    app = FastAPI()
    app.include_router(api_router, prefix="/v1")
    register_exception_handlers(app)
    return TestClient(app)


class TestBuildRoutesEnvelope:
    @pytest.mark.parametrize("path", BUILD_PATHS)
    def test_pipe_ref_defaults_to_the_closures_main_pipe(self, path: str):
        # D1: the selector is optional. Omitted, it resolves to the closure's declared main_pipe, and
        # the valid arm echoes BOTH the resolved ref and (absent) the requested one, so a caller can
        # see what it was defaulted to.
        client = _build_client()
        response = client.post(path, json={"files": [{"content": VALID_MTHDS}]})
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["is_valid"] is True
        assert body["pipe_ref"] == "smoke.echo"
        assert "requested_pipe_ref" not in body, "an omitted selector must not be echoed back as if it were requested"

    @pytest.mark.parametrize("path", BUILD_PATHS)
    def test_explicit_qualified_pipe_ref_is_echoed_as_requested_and_resolved(self, path: str):
        client = _build_client()
        response = client.post(path, json={"files": [{"content": VALID_MTHDS}], "pipe_ref": "smoke.echo"})
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["pipe_ref"] == "smoke.echo"
        assert body["requested_pipe_ref"] == "smoke.echo"

    @pytest.mark.parametrize("path", BUILD_PATHS)
    def test_unknown_pipe_ref_is_a_422_not_an_invalid_verdict(self, path: str):
        # Nothing about the *closure* is wrong — the caller named a pipe that isn't in it. That is a
        # no-verdict condition (422), never a 200 `is_valid: false`.
        # It carries the entry-lookup `error_type` the run routes answer for an unknown `pipe_code`, never
        # a request-shape `ValidationError` — `/build/runner` included, whose sliced sweep reaches it first.
        client = _build_client()
        response = client.post(path, json={"files": [{"content": VALID_MTHDS}], "pipe_ref": "smoke.does_not_exist"})
        assert response.status_code == 422, response.text
        assert response.headers["content-type"] == "application/problem+json"
        problem = response.json()
        assert problem["error_type"] == "EntryPipeNotFoundError"
        assert problem["error_domain"] == "input"
        assert "not found" in problem["detail"]

    @pytest.mark.parametrize("path", BUILD_PATHS)
    def test_an_ambiguous_pipe_ref_is_a_422_that_says_ambiguous_not_missing(self, path: str):
        # `echo` is declared by both `smoke` and `twin`, so the engine's entry lookup refuses to pick one.
        # The 422 must say so and name the candidates — calling the pipe "not found" beside a list of
        # the pipes it matched would contradict itself.
        client = _build_client()
        payload = {"files": [{"content": VALID_MTHDS}, {"content": COLLIDING_ECHO_LIST_MTHDS}], "pipe_ref": "echo"}
        response = client.post(path, json=payload)
        assert response.status_code == 422, response.text
        assert response.headers["content-type"] == "application/problem+json"
        assert response.json()["error_type"] == "EntryPipeAmbiguousError"
        detail = response.json()["detail"]
        assert "several domains" in detail
        assert "smoke.echo" in detail
        assert "twin.echo" in detail
        assert "not found" not in detail, detail

    @pytest.mark.parametrize("path", BUILD_PATHS)
    def test_omitted_pipe_ref_on_a_closure_with_no_main_pipe_is_422(self, path: str):
        # First of the two arms `inputs_cmd.py::_default_main_pipe_ref` rejects: nothing to default to.
        client = _build_client()
        response = client.post(path, json={"files": [{"content": NO_MAIN_PIPE_MTHDS}]})
        assert response.status_code == 422, response.text
        assert response.headers["content-type"] == "application/problem+json"
        assert response.json()["error_type"] == "EntryPipeNotFoundError"
        assert "main_pipe" in response.json()["detail"]

    @pytest.mark.parametrize("path", BUILD_PATHS)
    def test_omitted_pipe_ref_on_an_ambiguous_closure_is_422(self, path: str):
        # The second arm — the one the plan's D1 originally missed: two domains, two main_pipes, so the
        # default is ambiguous. Naming the pipe explicitly resolves it (asserted below).
        client = _build_client()
        payload = {"files": [{"content": VALID_MTHDS}, {"content": SECOND_MAIN_PIPE_MTHDS}]}
        response = client.post(path, json=payload)
        assert response.status_code == 422, response.text
        assert response.json()["error_type"] == "EntryPipeAmbiguousError"
        assert "several" in response.json()["detail"]

        named = client.post(path, json={**payload, "pipe_ref": "other.shout"})
        assert named.status_code == 200, named.text
        assert named.json()["pipe_ref"] == "other.shout"

    @pytest.mark.parametrize("path", BUILD_PATHS)
    def test_invalid_closure_is_a_200_invalid_verdict(self, path: str):
        client = _build_client()
        response = client.post(path, json={"files": [{"content": INVALID_MAIN_PIPE_MTHDS}]})
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["is_valid"] is False
        assert body["validation_errors"], "an invalid verdict must carry a non-empty validation_errors[]"

    @pytest.mark.parametrize("path", BUILD_PATHS)
    def test_method_ref_is_501_until_the_registry_exists(self, path: str):
        # The build routes inherit the closure selector whole — including the arm this server does not
        # serve yet. `/build/runner` reaches it through `selected_files` despite not using the crate core.
        client = _build_client()
        response = client.post(path, json={"method_ref": "acme/methods/x"})
        assert response.status_code == 501, response.text
        assert response.headers["content-type"] == "application/problem+json"
        assert response.json()["error_type"] == "MethodRefNotSupported"

    @pytest.mark.parametrize("path", BUILD_PATHS)
    def test_method_ref_omitted_pipe_ref_defaults_to_the_manifest_main_pipe(self, path: str, install_method_package: Callable[..., Path]):
        # The fetched package's closure declares NO main_pipe — on its own it cannot default the
        # selector (the 422 pinned above for inline files). But the package manifest declares one
        # (`STUB_METHOD_MANIFEST`: `main_pipe = "echo"`), and that is the package author's entry pipe:
        # the run routes already honor it, so an omitted `pipe_ref` here resolves to it too, and is
        # echoed qualified — a manifest `main_pipe` is a bare code riding the cross-domain fallback.
        install_method_package(files={"documents.mthds": NO_MAIN_PIPE_MTHDS})
        client = _build_client()
        response = client.post(path, json={"method_ref": STUB_METHOD_REF})
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["is_valid"] is True
        assert body["pipe_ref"] == "nomain.echo"
        assert "requested_pipe_ref" not in body, "a manifest-defaulted selector must not be echoed back as if it were requested"

    @pytest.mark.parametrize("path", BUILD_PATHS)
    def test_manifest_main_pipe_outranks_the_closures_own_declarations(self, path: str, install_method_package: Callable[..., Path]):
        # Two domains, two declared main_pipes: by the closure's own declarations the default is
        # ambiguous (the 422 pinned above for inline files). The manifest names `shout`, and it sits
        # above the closure in the chain — `pipe_ref or manifest main_pipe or closure main_pipe`, the
        # run routes' `pipe_code or fetched.main_pipe` — so it both settles the ambiguity and wins
        # over `smoke`'s own `echo`.
        install_method_package(
            files={"smoke.mthds": VALID_MTHDS, "other.mthds": SECOND_MAIN_PIPE_MTHDS},
            manifest_toml=STUB_METHOD_MANIFEST_MAIN_PIPE_SHOUT,
        )
        client = _build_client()
        response = client.post(path, json={"method_ref": STUB_METHOD_REF})
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["pipe_ref"] == "other.shout"
        assert "requested_pipe_ref" not in body

    @pytest.mark.parametrize("path", BUILD_PATHS)
    def test_explicit_pipe_ref_outranks_the_manifest_main_pipe(self, path: str, install_method_package: Callable[..., Path]):
        # The request's own selector stays first in the chain: the manifest says `echo`, the caller
        # says `other.shout`, and the caller wins — echoed as requested and resolved.
        install_method_package(files={"smoke.mthds": VALID_MTHDS, "other.mthds": SECOND_MAIN_PIPE_MTHDS})
        client = _build_client()
        response = client.post(path, json={"method_ref": STUB_METHOD_REF, "pipe_ref": "other.shout"})
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["pipe_ref"] == "other.shout"
        assert body["requested_pipe_ref"] == "other.shout"

    @pytest.mark.parametrize("path", BUILD_PATHS)
    def test_a_manifest_without_main_pipe_falls_back_to_the_closures_declaration(self, path: str, install_method_package: Callable[..., Path]):
        # A manifest may declare no `main_pipe`. Then the chain falls through to the closure's own
        # declaration — the same default inline `files[]` get — rather than refusing.
        install_method_package(files={"documents.mthds": VALID_MTHDS}, manifest_toml=STUB_METHOD_MANIFEST_NO_MAIN_PIPE)
        client = _build_client()
        response = client.post(path, json={"method_ref": STUB_METHOD_REF})
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["pipe_ref"] == "smoke.echo"
        assert "requested_pipe_ref" not in body

    @pytest.mark.parametrize("path", BUILD_PATHS)
    def test_method_ref_with_nothing_to_default_from_is_still_422(self, path: str, install_method_package: Callable[..., Path]):
        # The whole chain empty: no `pipe_ref`, a manifest with no `main_pipe`, a closure declaring
        # none. The closure-declaration arm's 422 is unchanged — the manifest only ever ADDS a default.
        install_method_package(files={"documents.mthds": NO_MAIN_PIPE_MTHDS}, manifest_toml=STUB_METHOD_MANIFEST_NO_MAIN_PIPE)
        client = _build_client()
        response = client.post(path, json={"method_ref": STUB_METHOD_REF})
        assert response.status_code == 422, response.text
        assert response.headers["content-type"] == "application/problem+json"
        assert "main_pipe" in response.json()["detail"]

    @pytest.mark.parametrize("path", BUILD_PATHS)
    def test_a_manifest_main_pipe_absent_from_the_closure_is_a_422_naming_its_origin(self, path: str, install_method_package: Callable[..., Path]):
        # The manifest names `echo` but the package's closure only contains `other.shout`. Nothing
        # about the closure is wrong, so it is the same request-shape 422 as an unknown explicit ref —
        # but the caller never spelled `echo`, so the detail must say where it came from.
        install_method_package(files={"other.mthds": SECOND_MAIN_PIPE_MTHDS})
        client = _build_client()
        response = client.post(path, json={"method_ref": STUB_METHOD_REF})
        assert response.status_code == 422, response.text
        assert response.headers["content-type"] == "application/problem+json"
        assert response.json()["error_type"] == "EntryPipeNotFoundError"
        detail = response.json()["detail"]
        assert "'echo'" in detail
        assert "manifest" in detail, f"the 422 must say the selector came from the manifest: {detail}"
        assert "not found" in detail

    @pytest.mark.parametrize("path", BUILD_PATHS)
    def test_an_ambiguous_manifest_main_pipe_is_a_422_that_says_ambiguous_not_missing(self, path: str, install_method_package: Callable[..., Path]):
        # The manifest names `echo`, which both `smoke` and `twin` declare. The caller never spelled it,
        # so the detail names the manifest as its origin, and it says the code is ambiguous, not missing.
        install_method_package(files={"smoke.mthds": VALID_MTHDS, "twin.mthds": COLLIDING_ECHO_LIST_MTHDS})
        client = _build_client()
        response = client.post(path, json={"method_ref": STUB_METHOD_REF})
        assert response.status_code == 422, response.text
        assert response.headers["content-type"] == "application/problem+json"
        assert response.json()["error_type"] == "EntryPipeAmbiguousError"
        detail = response.json()["detail"]
        assert "manifest" in detail
        assert "several domains" in detail
        assert "smoke.echo" in detail
        assert "twin.echo" in detail
        assert "not found" not in detail, detail

    @pytest.mark.parametrize("path", BUILD_PATHS)
    def test_source_labels_ride_through_to_diagnostics(self, path: str):
        # The point of the envelope migration for the build routes: a per-file `source` label reaches the
        # engine, so an invalid closure's diagnostics can name the owning file. (Before Phase 2 the build
        # routes took bare strings and could not carry one — `/build/runner` needed the widened
        # `validate_bundle(mthds_sources=...)` to get here.)
        client = _build_client()
        response = client.post(path, json={"files": [{"content": INVALID_MAIN_PIPE_MTHDS, "source": "bundles/broken.mthds"}]})
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["is_valid"] is False
        sources = [error.get("source") for error in body["validation_errors"]]
        assert "bundles/broken.mthds" in sources, f"no diagnostic carried the submitted source: {body['validation_errors']}"

    @pytest.mark.parametrize("path", ["/v1/build/inputs", "/v1/build/output"])
    def test_static_routes_ignore_allow_signatures(self, path: str):
        # `allow_signatures` only ever parameterized the dry-run sweep. The static projections dropped
        # the sweep, so the flag is gone from their request models — and since the envelope does not
        # forbid extras, a client still sending it is simply ignored rather than rejected.
        client = _build_client()
        response = client.post(path, json={"files": [{"content": VALID_MTHDS}], "allow_signatures": True})
        assert response.status_code == 200, response.text
        assert "allow_signatures" not in response.json()

    @pytest.mark.parametrize("path", ["/v1/build/inputs", "/v1/build/output"])
    @pytest.mark.parametrize("pipe_ref", ["sig_api.caller_seq", "sig_api.summary_sig"], ids=["caller", "the-signature-itself"])
    def test_static_routes_accept_a_signature_bundle_unconditionally(self, path: str, pipe_ref: str):
        # The corollary of dropping the sweep: an unimplemented `PipeSignature` is a *runnability*
        # fact, and these routes no longer speak runnability. So a signature bundle projects fine with
        # no flag to set — where `/validate` and `/build/runner` still surface it (see
        # test_allow_signatures.py, whose docstring points here for exactly this assertion).
        # Both the caller *and* the signature pipe itself: a signature declares inputs/output, so it is
        # statically projectable precisely because these routes read only the declaration.
        client = _build_client()
        response = client.post(path, json={"files": [{"content": SIGNATURE_MTHDS}], "pipe_ref": pipe_ref})
        assert response.status_code == 200, response.text
        assert response.json()["is_valid"] is True

    @pytest.mark.parametrize("path", BUILD_PATHS)
    def test_a_bare_pipe_code_still_resolves_but_is_echoed_qualified(self, path: str):
        # The engine's pipe lookup accepts a bare code, falling back across domains. A caller who leans
        # on that must still be told the QUALIFIED ref — the valid arms promise one, so echoing the
        # request's own bare spelling back would quietly break that promise. The resolved ref is read
        # off the live pipe, never off the request.
        client = _build_client()
        response = client.post(path, json={"files": [{"content": VALID_MTHDS}], "pipe_ref": "echo"})
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["pipe_ref"] == "smoke.echo", "the resolved ref must be qualified, not the bare code the caller sent"
        assert body["requested_pipe_ref"] == "echo", "the echo of the request must stay verbatim"

    @pytest.mark.parametrize("path", BUILD_PATHS)
    def test_empty_files_rejected(self, path: str):
        client = _build_client()
        response = client.post(path, json={"files": []})
        assert response.status_code == 422
        assert response.headers["content-type"] == "application/problem+json"
        assert response.json()["error_type"] == "ValidationError"

    @pytest.mark.parametrize("path", BUILD_PATHS)
    def test_routes_open_exactly_one_library_and_tear_it_down(self, path: str, mocker: MockerFixture):
        # The loaded-on-success contract: whichever core a route rides (the static
        # `resolve_requested_crate` for inputs/output, `validate_bundle` for runner), it opens exactly
        # ONE library, leaves it loaded + current, and the route owns its teardown. A second open would
        # orphan the first; a missing teardown would leak it.
        library_manager = get_library_manager()
        open_spy = mocker.spy(library_manager, "open_library")
        teardown_spy = mocker.spy(library_manager, "teardown")

        client = _build_client()
        response = client.post(path, json={"files": [{"content": VALID_MTHDS}], "pipe_ref": "smoke.echo"})

        assert response.status_code == 200, response.text
        assert open_spy.call_count == 1
        created_library_id, _ = open_spy.spy_return
        teardown_spy.assert_called_once_with(library_id=created_library_id)

    def test_inputs_json_returns_the_parsed_light_template(self):
        client = _build_client()
        response = client.post("/v1/build/inputs", json={"files": [{"content": VALID_MTHDS}]})
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["format"] == "json"
        assert body["explicit"] is False
        # The light shape: a Text-refining input is a bare string, not a {concept, content} envelope.
        assert isinstance(body["inputs"]["text"], str)
        assert "inputs_toml" not in body, "the format the caller did not ask for must be absent"

    def test_inputs_explicit_returns_the_ceremonial_envelope(self):
        client = _build_client()
        response = client.post("/v1/build/inputs", json={"files": [{"content": VALID_MTHDS}], "explicit": True})
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["explicit"] is True
        assert set(body["inputs"]["text"]) == {"concept", "content"}

    @pytest.mark.parametrize("explicit", [False, True], ids=["light", "explicit"])
    def test_inputs_toml_returns_raw_text_not_a_parsed_dict(self, explicit: bool):
        # D3's response-shape consequence: TOML cannot ride as a parsed dict (it would lose the concept
        # comments and key order that are the reason to ask for TOML), so it rides its own string field.
        client = _build_client()
        response = client.post("/v1/build/inputs", json={"files": [{"content": VALID_MTHDS}], "format": "toml", "explicit": explicit})
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["format"] == "toml"
        assert isinstance(body["inputs_toml"], str)
        assert "text" in body["inputs_toml"]
        assert "inputs" not in body, "the JSON field must be absent on a TOML request"

    @pytest.mark.parametrize("template_format", ["json", "toml"])
    def test_a_pipe_with_no_inputs_is_a_valid_verdict_with_an_empty_template(self, template_format: str):
        # NoInputsRequiredError out of the engine renderers is not a failure — it is the honest answer
        # "run this with nothing". The CLI exits 0 on it; the route answers a valid arm.
        client = _build_client()
        response = client.post("/v1/build/inputs", json={"files": [{"content": NO_INPUTS_MTHDS}], "format": template_format})
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["is_valid"] is True
        assert "no inputs" in body["message"]
        empty = body["inputs"] if template_format == "json" else body["inputs_toml"]
        assert not empty

    @pytest.mark.parametrize(
        ("output_format", "expected_field"),
        [("schema", "output"), ("json", "output"), ("python", "output_python")],
    )
    def test_output_formats_land_on_the_field_the_format_implies(self, output_format: str, expected_field: str):
        # Regression: `format=python` used to be a hard 500 — the route fed Python source to json.loads
        # and typed the field `dict`. The structured formats stay objects; python is source text.
        client = _build_client()
        response = client.post("/v1/build/output", json={"files": [{"content": VALID_MTHDS}], "format": output_format})
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["format"] == output_format
        assert expected_field in body
        if expected_field == "output":
            assert isinstance(body["output"], dict)
            assert "output_python" not in body
        else:
            assert isinstance(body["output_python"], str)
            assert "output" not in body

    @pytest.mark.parametrize(
        ("pipe_ref", "expects_list"),
        [("smoke.echo", False), ("twin.echo", True)],
        ids=["scalar-output", "list-output"],
    )
    def test_runner_reads_output_multiplicity_from_the_right_domain(self, pipe_ref: str, expects_list: bool):
        # Two domains declare a pipe with the same BARE code `echo`, with OPPOSITE output multiplicity.
        # The runner reads the requested pipe's multiplicity out of the blueprints, whose `pipe` maps are
        # keyed by bare code — so a bare-code scan returns whichever blueprint came first and can emit a
        # runner with the wrong output handling. The lookup must compare the owning domain too.
        client = _build_client()
        response = client.post(
            "/v1/build/runner",
            json={"files": [{"content": VALID_MTHDS}, {"content": COLLIDING_ECHO_LIST_MTHDS}], "pipe_ref": pipe_ref},
        )
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["pipe_ref"] == pipe_ref
        # The multiplicity decides the script's result cast: `main_stuff_as_items(item_type=...)` for a
        # list output vs `main_stuff_as(content_type=...)` for a scalar one.
        python_code = body["python_code"]
        assert ("main_stuff_as_items(" in python_code) is expects_list, f"wrong output multiplicity for {pipe_ref}:\n{python_code}"

    def test_runner_still_sweeps_and_still_takes_allow_signatures(self, mocker: MockerFixture):
        # `/build/runner` is the one projection that keeps the dry-run (a runner script is a promise the
        # pipe runs), so it alone still accepts the flag that parameterizes that sweep.
        spy = mocker.spy(get_library_manager(), "open_library")
        client = _build_client()
        response = client.post(
            "/v1/build/runner",
            json={"files": [{"content": VALID_MTHDS}], "pipe_ref": "smoke.echo", "allow_signatures": True},
        )
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["python_code"]
        assert body["structures"]["artifacts"]
        assert spy.call_count == 1
