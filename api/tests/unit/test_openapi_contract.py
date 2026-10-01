"""The published error contract — every `/v1` operation documents RFC 7807, with real schemas.

Guards what the committed artifact (`docs/api-server/openapi/pipelex-api.openapi.yaml` at the repository root,
regenerated from this same `fastapi_app.openapi()`) tells a client about failures:

- Every failure this server can emit is an `application/problem+json` problem document
  (`pipelex_api.exception_handlers`), so every documented 4xx/5xx must say so — with a `$ref` to the
  typed `ProblemDocument`, not FastAPI's default `HTTPValidationError` on `application/json`.
- The statuses a given route can additionally produce (`/execute`'s provider-429, `/start`'s
  409 duplicate run, `/resolve`'s 501 `method_ref`, …) are documented on that route.
- The `suggested_fix` surface pipelex's codegen work added reaches the wire: a client reading
  the artifact can find it from a problem document, not just from `/validate`'s 200 arm.
- `x-mthds-protocol` marks exactly the MTHDS Protocol operations and nothing else — the flag is
  how a conformance suite or a third-party runner extracts the portable subset of this artifact,
  so a Pipelex extension wearing it would misrepresent the standard.

`pipelex_api.main` is imported inside the fixture rather than at module scope so a bad env var fails
THESE tests rather than the collection of every module that transitively imports the app.
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from pipelex_api.problem_document import PROBLEM_JSON_MEDIA_TYPE

# Methods that carry an operation object in an OpenAPI path item.
_OPERATION_KEYS = frozenset({"get", "put", "post", "delete", "options", "head", "patch", "trace"})

# Documented on EVERY auth-wrapped `/v1` operation, via the composite router in `pipelex_api.routes`:
# the auth dependency (401), the body-size middleware (413), request-shape / input-domain
# rejections (422), and the server-fault floor (500).
COMMON_STATUSES = (401, 413, 422, 500)

# `GET /v1/version` is the public protocol handshake: `pipelex_api.main` mounts it OUTSIDE the composite
# router (and outside the auth dependency), so it inherits none of the shared responses.
PUBLIC_PATHS = ("/v1/version",)

# The MTHDS Protocol operations — and nothing else — carry `x-mthds-protocol: true`. This is the
# standard's five-operation surface (`execute`, `start`, `validate`, `models`, `version`; see the
# normative `mthds/docs/spec/openapi/mthds-protocol.openapi.yaml`), NOT everything this server
# serves. `/resolve` and `/codegen` are deliberately absent: they are Pipelex API extensions. The
# crate `/resolve` emits is standard-owned (the MTHDS Library Crate Format), but the route serving
# it is ours, and the standard specifies no type projection at all.
MTHDS_PROTOCOL_OPERATIONS = {
    ("/v1/execute", "post"),
    ("/v1/start", "post"),
    ("/v1/validate", "post"),
    ("/v1/models", "get"),
    ("/v1/version", "get"),
}

# The extra statuses each route can produce on top of COMMON_STATUSES.
ROUTE_EXTRA_STATUSES = {
    ("/v1/execute", "post"): (403, 429),
    ("/v1/start", "post"): (400, 403, 409, 501),
    ("/v1/validate", "post"): (403,),
    ("/v1/resolve", "post"): (404, 501),
    ("/v1/pipe-io", "post"): (404, 501),
    ("/v1/codegen", "post"): (501,),
}


@pytest.fixture(scope="class")
def openapi_schema() -> dict[str, Any]:
    from pipelex_api.main import fastapi_app  # noqa: PLC0415 — see the module docstring

    return fastapi_app.openapi()


class TestOpenApiErrorContract:
    def _operations(self, schema: dict[str, Any], *, prefix: str = "") -> list[tuple[str, str, dict[str, Any]]]:
        """Every (path, method, operation) in the schema, optionally filtered by path prefix."""
        return [
            (path, method, operation)
            for path, path_item in schema["paths"].items()
            if path.startswith(prefix)
            for method, operation in path_item.items()
            if method in _OPERATION_KEYS
        ]

    def test_no_operation_documents_fastapi_default_validation_error(self, openapi_schema: dict[str, Any]):
        """FastAPI's automatic `HTTPValidationError` 422 contradicts the RFC 7807 wire — declaring
        our own 422 must suppress it everywhere, and the component must not even be generated.
        """
        assert "HTTPValidationError" not in openapi_schema["components"]["schemas"]
        for path, method, operation in self._operations(openapi_schema):
            for status_code, response in operation["responses"].items():
                content = response.get("content", {})
                for media_type, body in content.items():
                    ref = body.get("schema", {}).get("$ref", "")
                    assert "HTTPValidationError" not in ref, f"{method.upper()} {path} {status_code} ({media_type}) still refs HTTPValidationError"

    def test_every_v1_operation_documents_the_common_problem_responses(self, openapi_schema: dict[str, Any]):
        """Auth (401), payload cap (413), request shape (422), server fault (500) — on every
        auth-wrapped `/v1` route, each an `application/problem+json` `ProblemDocument`.
        """
        operations = [
            (path, method, operation) for path, method, operation in self._operations(openapi_schema, prefix="/v1") if path not in PUBLIC_PATHS
        ]
        assert operations, "no /v1 operations found — the schema or the path filter is wrong"
        for path, method, operation in operations:
            for status in COMMON_STATUSES:
                response = operation["responses"].get(str(status))
                assert response is not None, f"{method.upper()} {path} does not document {status}"
                content = response.get("content", {})
                assert list(content) == [PROBLEM_JSON_MEDIA_TYPE], f"{method.upper()} {path} {status} media type is {list(content)}"
                assert content[PROBLEM_JSON_MEDIA_TYPE]["schema"]["$ref"] == "#/components/schemas/ProblemDocument"

    def test_public_version_route_has_no_auth_response(self, openapi_schema: dict[str, Any]):
        """`GET /v1/version` is the pre-credential handshake: it must never advertise a 401."""
        responses = openapi_schema["paths"]["/v1/version"]["get"]["responses"]
        assert "401" not in responses
        assert responses["500"]["content"][PROBLEM_JSON_MEDIA_TYPE]["schema"]["$ref"] == "#/components/schemas/ProblemDocument"

    @pytest.mark.parametrize(
        ("path", "method", "extra_statuses"), [(path, method, extras) for (path, method), extras in ROUTE_EXTRA_STATUSES.items()]
    )
    def test_route_documents_its_own_extra_statuses(self, openapi_schema: dict[str, Any], path: str, method: str, extra_statuses: tuple[int, ...]):
        """The failures a specific route alone can produce ride that route's operation."""
        responses = openapi_schema["paths"][path][method]["responses"]
        for status in extra_statuses:
            response = responses.get(str(status))
            assert response is not None, f"{method.upper()} {path} does not document {status}"
            assert list(response.get("content", {})) == [PROBLEM_JSON_MEDIA_TYPE]

    def test_x_mthds_protocol_tags_exactly_the_protocol_operations(self, openapi_schema: dict[str, Any]):
        """The flag is how a conformance suite extracts the portable subset of this artifact, so it
        must mark the standard's operations and nothing else. Asserted as an exact set — a route that
        silently joins OR leaves the protocol surface fails here, in both directions.
        """
        tagged = {(path, method) for path, method, operation in self._operations(openapi_schema) if operation.get("x-mthds-protocol")}
        assert tagged == MTHDS_PROTOCOL_OPERATIONS

    def test_resolve_codegen_and_pipe_io_are_pipelex_extensions(self, openapi_schema: dict[str, Any]):
        """Spelled out separately from the set assertion above, because this is the easy mistake:
        `/resolve`, `/codegen` and `/pipe-io` look protocol-shaped (they speak the `/validate` verdict
        discipline and emit the standard's crate or I/O artifacts) but they are Pipelex API extensions
        and must not be tagged.
        """
        for path in ("/v1/resolve", "/v1/codegen", "/v1/pipe-io"):
            assert "x-mthds-protocol" not in openapi_schema["paths"][path]["post"]

    def test_the_document_never_names_the_hosted_selector(self, openapi_schema: dict[str, Any]):
        """The runner declares nothing of the hosted layer, not even in prose: `method_id` is the hosted
        catalog selector, which the platform replaces with `files` before a request reaches the runner,
        so the name appears nowhere in the document — no field, no description, no example.
        """
        assert "method_id" not in json.dumps(openapi_schema)

    def test_pipe_io_request_declares_no_hosted_selector_and_no_views(self, openapi_schema: dict[str, Any]):
        """The platform resolves the hosted `method_id` into `files[]` before forwarding, so the runner
        never declares it; and the route always carries all three artifacts, so it takes no `views`.
        """
        schemas = openapi_schema["components"]["schemas"]
        body_ref = openapi_schema["paths"]["/v1/pipe-io"]["post"]["requestBody"]["content"]["application/json"]["schema"]["$ref"]
        properties = set(schemas[body_ref.rsplit("/", 1)[-1]]["properties"])
        assert properties >= {"files", "method_ref", "pipe_ref", "all_pipes", "include_files"}
        assert "method_id" not in properties
        assert "views" not in properties

    def test_auth_challenge_and_retry_hint_headers_are_documented(self, openapi_schema: dict[str, Any]):
        """A 401 carries `WWW-Authenticate: Bearer`; the provider-429 passthrough carries `Retry-After`."""
        unauthenticated = openapi_schema["paths"]["/v1/validate"]["post"]["responses"]["401"]
        assert "WWW-Authenticate" in unauthenticated["headers"]
        rate_limited = openapi_schema["paths"]["/v1/execute"]["post"]["responses"]["429"]
        assert "Retry-After" in rate_limited["headers"]

    def test_problem_document_carries_the_structured_validation_errors(self, openapi_schema: dict[str, Any]):
        """A problem document publishes `validation_errors[]` of the SAME `ValidationErrorItem`
        the 200 invalid arms publish — so `suggested_fix` reaches every surface that carries the
        items, and the two can never drift into separate schemas.
        """
        schemas = openapi_schema["components"]["schemas"]
        validation_errors = schemas["ProblemDocument"]["properties"]["validation_errors"]
        item_refs = [option["items"]["$ref"] for option in validation_errors["anyOf"] if option.get("type") == "array"]
        assert item_refs == ["#/components/schemas/ValidationErrorItem"]

    def test_suggested_fix_surface_is_published(self, openapi_schema: dict[str, Any]):
        """The codegen fix planner's output is part of the published contract: a `ValidationErrorItem`
        may carry a `SuggestedFix`, whose `ops[]` are the machine contract (the rendered diff is not).

        An op is a union discriminated on `kind`, one member model per kind — so a client picks the
        member off the wire value rather than reading a single open shape whose fields depend on a
        `kind` enum beside them. The whole vocabulary is published here: this is the `.mthds` fix
        path, which carries every kind (a ledger carries only the structural subset).
        """
        schemas = openapi_schema["components"]["schemas"]
        suggested_fix = schemas["ValidationErrorItem"]["properties"]["suggested_fix"]
        assert any(option.get("$ref") == "#/components/schemas/SuggestedFix" for option in suggested_fix["anyOf"])
        fix_properties = schemas["SuggestedFix"]["properties"]
        assert {"fix_code", "description", "safety", "ops"} <= set(fix_properties)

        op_schema = fix_properties["ops"]["items"]
        assert op_schema["discriminator"]["propertyName"] == "kind"
        kind_mapping = op_schema["discriminator"]["mapping"]
        assert set(kind_mapping) == {"set_key", "ensure_table", "delete_key", "delete_table", "rename_table_key", "move_key", "remap_value"}
        # Every member the discriminator names is a `oneOf` option AND a published schema, so a
        # client that resolves a `kind` off the wire always lands on a shape the artifact defines.
        member_refs = {option["$ref"] for option in op_schema["oneOf"]}
        assert set(kind_mapping.values()) == member_refs
        assert all(ref.rsplit("/", 1)[-1] in schemas for ref in member_refs)

        assert set(schemas["FixSafety"]["enum"]) == {"safe", "unsafe"}

    def test_execute_publishes_the_tokens_usage_wire_records(self, openapi_schema: dict[str, Any]):
        """`/execute` returns a `JSONResponse` built from a trimmed dump, so FastAPI never validates
        the body against `response_model` — nothing but this test keeps the published 200 schema
        honest about what `apply_tokens_usage_wire_shape` actually emits. The runtime guard in
        `test_pipeline_routes.py` pins the body; this pins the artifact, so the two fail together.
        """
        schemas = openapi_schema["components"]["schemas"]
        body_ref = openapi_schema["paths"]["/v1/execute"]["post"]["responses"]["200"]["content"]["application/json"]["schema"]["$ref"]
        assert body_ref == "#/components/schemas/PipelexApiExecuteResponse"

        pipe_output_ref = schemas["PipelexApiExecuteResponse"]["properties"]["pipe_output"]["$ref"]
        tokens_usages = schemas[pipe_output_ref.rsplit("/", 1)[-1]]["properties"]["tokens_usages"]
        item_refs = [option["items"]["$ref"] for option in tokens_usages["anyOf"] if option.get("type") == "array"]
        assert item_refs == ["#/components/schemas/TokensUsageRecord"]

        record_properties = set(schemas["TokensUsageRecord"]["properties"])
        assert {"model_type", "pipe_code", "nb_tokens_by_category", "cost"} <= record_properties
        # The runtime internals the wire shape drops must not reappear in the published record.
        assert {"job_metadata", "unit_costs"}.isdisjoint(record_properties)

        # Nothing else references the internal usage models, so they leave the artifact entirely.
        assert {"LLMTokensUsage", "ImgGenTokensUsage", "JobMetadata"}.isdisjoint(schemas)

    def test_input_form_fields_are_a_kind_discriminated_union_of_closed_shapes(self, openapi_schema: dict[str, Any]):
        """`PipeInputFormDescriptor.fields` publishes the standard's per-kind field models as a
        union discriminated on `kind` — one member model per kind, the flat `InputFormField`
        gone. The arms must stay closed shapes with real properties: the standard's field models
        share a wrap serializer, and an imprecise return annotation on it silently erases every
        arm to an open `{"additionalProperties": true}` object (validation-mode schemas and
        `model_dump()` both stay correct, so nothing else notices). This is what would catch an
        upstream regression to the flat or opaque shape.
        """
        schemas = openapi_schema["components"]["schemas"]
        field_schema = schemas["PipeInputFormDescriptor"]["properties"]["fields"]["items"]
        assert field_schema["discriminator"]["propertyName"] == "kind"
        kind_mapping = field_schema["discriminator"]["mapping"]
        assert set(kind_mapping) == {"text", "prose", "date", "number", "boolean", "enum", "document", "image", "object", "list", "unknown"}
        member_refs = {option["$ref"] for option in field_schema["oneOf"]}
        assert set(kind_mapping.values()) == member_refs

        for ref in member_refs:
            member = schemas[ref.rsplit("/", 1)[-1]]
            assert member["additionalProperties"] is False
            assert {"kind", "name", "required"} <= set(member["properties"])

        # The flat pre-union models must not resurface beside the per-kind ones.
        assert {"InputFormField", "FieldKind"}.isdisjoint(schemas)
