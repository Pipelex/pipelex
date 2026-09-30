"""The FastAPI subclass that publishes this API's error responses under the right media type.

Every failure the API emits is an RFC 7807 `application/problem+json` document — that is the
whole contract of `api.exception_handlers`. But FastAPI renders a `responses` entry's `model`
under the **route's** response-class media type (`application/json` for every route here) and
offers no per-response override (`route_response_media_type` in `fastapi.openapi.utils`). Left
alone, the published artifact would therefore promise `application/json` on every error — a
contract the server never honors.

Hand-writing the media type into each `responses` entry would mean hand-writing a `$ref` too,
forfeiting FastAPI's component registration for `ProblemDocument` (`api.openapi_responses`). So
the schema is generated normally and the error responses are re-keyed afterwards, in
`PipelexFastAPI.openapi()` — FastAPI's documented "Extending OpenAPI" seam, and the single place
the API asserts the error media type. It holds for the live `/openapi.json` and for the committed
YAML alike: both go through `openapi()`.

Deliberately import-side-effect-free, mirroring `api.exception_handlers`: no env var reads, no app
construction, no router wiring. That is what lets a test build a production-faithful app —
one that renders the error media type the way the real server does — without dragging in
`api.main`'s startup chain (`Pipelex.make`, `get_auth_dependency`, the `ERROR_DISCLOSURE`
fail-fast), so a misconfigured env var cannot crash collection of every module that needs the
app class.
"""

from typing import Any

from fastapi import FastAPI
from typing_extensions import override

from api.problem_document import PROBLEM_JSON_MEDIA_TYPE

# HTTP methods that carry an operation object in an OpenAPI path item. A path item can also hold
# non-operation keys (`parameters`, `summary`, `servers`), so the pass below iterates this set
# rather than every key it finds.
_OPENAPI_OPERATION_KEYS = frozenset({"get", "put", "post", "delete", "options", "head", "patch", "trace"})


def _is_error_status(status_code: str) -> bool:
    """Whether an OpenAPI response key denotes a 4xx/5xx status.

    Response keys are strings, and beyond the numeric ones OpenAPI allows the wildcard forms
    (`4XX`, `5XX`) and `default`. This server declares only numeric statuses, so anything
    non-numeric is left alone rather than guessed at.
    """
    return status_code.isdigit() and int(status_code) >= 400


def use_problem_json_media_type(schema: dict[str, Any]) -> None:
    """Re-key every documented 4xx/5xx response onto `application/problem+json`, in place.

    See the module docstring for why this is a post-pass rather than a per-response declaration.
    """
    for path_item in schema.get("paths", {}).values():
        for method, operation in path_item.items():
            if method not in _OPENAPI_OPERATION_KEYS:
                continue
            for status_code, response in operation.get("responses", {}).items():
                if not _is_error_status(status_code):
                    continue
                content: dict[str, Any] | None = response.get("content")
                if content is None:
                    continue
                json_content = content.pop("application/json", None)
                if json_content is not None:
                    content[PROBLEM_JSON_MEDIA_TYPE] = json_content


class PipelexFastAPI(FastAPI):
    """The app class. Stock FastAPI, extended only to publish errors as `application/problem+json`."""

    @override
    def openapi(self) -> dict[str, Any]:
        """The OpenAPI schema, with every documented 4xx/5xx moved onto `application/problem+json`.

        The early return keeps the rewrite a one-shot: the base builds the schema and caches it on
        `self.openapi_schema`, returning that same dict, so mutating it in place fixes up the cached
        copy and every later call short-circuits here.
        """
        if self.openapi_schema is not None:
            return self.openapi_schema
        schema = super().openapi()
        use_problem_json_media_type(schema)
        return schema
