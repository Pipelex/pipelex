"""The nesting-depth bound on JSON request bodies (`pipelex_api.json_body`).

Up to Python 3.13 `json.loads` raised `RecursionError` on a deeply nested body at a fixed count; from 3.14
it raises only when the thread's stack runs out, so the same body was refused on one host and parsed on
another. The server now bounds the depth itself, before parsing. These tests pin the scan (exact on valid
JSON, blind to brackets inside strings, linear at the body cap), the 422 `request.malformed` a body past the
limit gets on a route with a typed body, and the invariant that every such route of the app is checked.
The run routes, which parse their raw body, are covered in `test_pipeline_routes.py`.
"""

import json
import random
import sys
from collections.abc import Callable
from typing import cast

import pytest
from fastapi import FastAPI, Request, Response
from fastapi.datastructures import Default, DefaultPlaceholder
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient
from pydantic import BaseModel
from pytest_mock import MockerFixture
from starlette.types import Message, Scope

from pipelex_api.exception_handlers import register_exception_handlers
from pipelex_api.exceptions import RunnerRequestError
from pipelex_api.json_body import (
    INTEGER_TOO_LONG_REASON,
    TOO_DEEPLY_NESTED_REASON,
    JsonBodyRoute,
    decode_json_body,
    holds_content_type_strictly,
    json_nesting_exceeds,
)
from pipelex_api.limits import MAX_JSON_NESTING_DEPTH, MAX_REQUEST_BODY_BYTES
from pipelex_api.routes import router as api_router
from tests.unit._constants import VALID_MTHDS
from tests.unit._problems import assert_problem, problem_of

# Deep enough to exhaust the parser's recursion budget on Python 3.13 and earlier.
RECURSION_DEEP = 100_000

# Strings full of what the scan must not count: brackets, braces, escaped quotes and backslashes.
TRICKY_STRINGS = ["", "[", "]]", "{[", '"', '\\"', "\\", "\\\\", '"]', '[\\"{', "é[", " ", "\\u0022["]


def _nested_arrays(depth: int) -> bytes:
    return b"[" * depth + b"]" * depth


def _nested_objects(depth: int) -> bytes:
    return b'{"k":' * depth + b"null" + b"}" * depth if depth else b"null"


def _nested_mixed(depth: int) -> bytes:
    opening = b"".join(b'{"k":' if level % 2 else b"[" for level in range(depth))
    closing = b"".join(b"}" if level % 2 else b"]" for level in reversed(range(depth)))
    return opening + b"0" + closing


def _parsed_depth(value: object) -> int:
    """Return how deep a parsed JSON value nests its lists and dicts, walked without recursion."""
    deepest = 0
    stack: list[tuple[object, int]] = [(value, 1)]
    while stack:
        current, level = stack.pop()
        children: list[object]
        if isinstance(current, dict):
            children = list(cast("dict[str, object]", current).values())
        elif isinstance(current, list):
            children = cast("list[object]", current)
        else:
            continue
        deepest = max(deepest, level)
        stack.extend((child, level + 1) for child in children)
    return deepest


def _random_value(rng: random.Random, *, budget: int) -> object:
    roll = rng.random()
    if budget > 0 and roll < 0.4:
        return [_random_value(rng, budget=budget - 1) for _ in range(rng.randint(0, 3))]
    if budget > 0 and roll < 0.8:
        return {rng.choice(TRICKY_STRINGS): _random_value(rng, budget=budget - 1) for _ in range(rng.randint(0, 3))}
    return rng.choice([*TRICKY_STRINGS, 0, 1.5, True, None])


def _client() -> TestClient:
    app = FastAPI()
    app.include_router(api_router, prefix="/v1")
    register_exception_handlers(app)
    return TestClient(app)


class TestJsonBodyNesting:
    @pytest.mark.parametrize("nested", [_nested_arrays, _nested_objects, _nested_mixed])
    def test_counts_arrays_and_objects_up_to_the_limit(self, nested: Callable[[int], bytes]):
        at_limit = nested(MAX_JSON_NESTING_DEPTH)
        past_limit = nested(MAX_JSON_NESTING_DEPTH + 1)
        assert _parsed_depth(json.loads(at_limit)) == MAX_JSON_NESTING_DEPTH
        assert not json_nesting_exceeds(at_limit, max_depth=MAX_JSON_NESTING_DEPTH)
        assert json_nesting_exceeds(past_limit, max_depth=MAX_JSON_NESTING_DEPTH)

    @pytest.mark.parametrize(
        ("body", "depth"),
        [
            (b'["' + b"[" * 1000 + b'"]', 1),
            (b'["\\"' + b"[{" * 1000 + b'"]', 1),
            (b'{"\\"[[[": "]]]\\\\", "k": [["\\"\\\\\\"[[["]]}', 3),
            (b'["\\u0022' + b"[" * 1000 + b'"]', 1),
            (b'["\\\\", ' + _nested_arrays(MAX_JSON_NESTING_DEPTH) + b"]", MAX_JSON_NESTING_DEPTH + 1),
            (b'{"\\\\\\\\": "\\\\\\"", "k": ' + _nested_objects(MAX_JSON_NESTING_DEPTH) + b"}", MAX_JSON_NESTING_DEPTH + 1),
        ],
        ids=[
            "brackets-in-a-string",
            "brackets-after-an-escaped-quote",
            "keys-and-values-with-escapes",
            "brackets-after-a-unicode-escaped-quote",
            "nesting-after-an-escaped-backslash",
            "nesting-after-escaped-backslashes-and-quotes",
        ],
    )
    def test_brackets_inside_strings_do_not_count(self, body: bytes, depth: int):
        # Each body is valid JSON, so the parser states its true depth. An escaped quote leaves its string
        # open, while a quote after an escaped backslash closes it.
        assert _parsed_depth(json.loads(body)) == depth
        assert not json_nesting_exceeds(body, max_depth=depth)
        assert json_nesting_exceeds(body, max_depth=depth - 1)

    def test_matches_the_parsed_depth_of_random_documents(self):
        rng = random.Random(20261001)
        for _ in range(300):
            document = _random_value(rng, budget=rng.randint(0, 10))
            body = json.dumps(document, ensure_ascii=rng.random() < 0.5).encode("utf-8")
            depth = _parsed_depth(document)
            for max_depth in range(12):
                assert json_nesting_exceeds(body, max_depth=max_depth) == (depth > max_depth), (body, max_depth)

    @pytest.mark.parametrize("chunk_bytes", [1, 2, 3, 7, 64])
    def test_chunk_boundaries_do_not_change_the_answer(self, mocker: MockerFixture, chunk_bytes: int):
        # The scan splits at quotes and measures runs a chunk at a time; tiny chunks cut strings, escapes
        # and runs at every possible point, and the answer must stay the parsed depth.
        mocker.patch("pipelex_api.json_body._CHUNK_BYTES", chunk_bytes)
        rng = random.Random(chunk_bytes)
        for _ in range(60):
            document = _random_value(rng, budget=rng.randint(0, 8))
            body = json.dumps(document).encode("utf-8")
            depth = _parsed_depth(document)
            for max_depth in range(10):
                assert json_nesting_exceeds(body, max_depth=max_depth) == (depth > max_depth), (body, max_depth)

    @pytest.mark.parametrize(
        "body",
        [
            b"[" * RECURSION_DEEP,
            b'{"inputs": ' + b"[" * RECURSION_DEEP,
            b"[" * RECURSION_DEEP + b"}" * RECURSION_DEEP,
            b'{"a": "an escaped quote \\" then ' + b"]" * 10 + b'", ' + b"[" * RECURSION_DEEP,
        ],
        ids=["unclosed-arrays", "unclosed-inside-an-object", "mismatched-closers", "unclosed-after-a-string"],
    )
    def test_refuses_a_deep_body_that_is_not_valid_json(self, body: bytes):
        # A parser recurses through an unclosed body before it finds the end, so the scan reports the
        # depth it would reach whether or not the brackets ever close.
        assert json_nesting_exceeds(body, max_depth=MAX_JSON_NESTING_DEPTH)

    @pytest.mark.parametrize("encoding", ["utf-16", "utf-16-le", "utf-16-be", "utf-32", "utf-8-sig"])
    def test_reads_every_encoding_the_parser_accepts(self, encoding: str):
        # FastAPI hands a typed body's bytes to `json.loads`, which also accepts UTF-16 and UTF-32: the scan
        # must see the brackets those encodings spell, and their escaped quotes.
        within = '["\\"[[[", ' + "[" * (MAX_JSON_NESTING_DEPTH - 1) + "]" * (MAX_JSON_NESTING_DEPTH - 1) + "]"
        past = '["\\"]]]", ' + "[" * MAX_JSON_NESTING_DEPTH + "]" * MAX_JSON_NESTING_DEPTH + "]"
        assert _parsed_depth(json.loads(within.encode(encoding))) == MAX_JSON_NESTING_DEPTH
        assert not json_nesting_exceeds(within.encode(encoding), max_depth=MAX_JSON_NESTING_DEPTH)
        assert json_nesting_exceeds(past.encode(encoding), max_depth=MAX_JSON_NESTING_DEPTH)

    def test_scans_bodies_at_the_size_cap(self):
        # No timing is asserted; a body as large as the server accepts must simply be answered, exactly.
        # One is mostly a string full of brackets, the other is nothing but small arrays.
        string_heavy_head = b'{"doc": "'
        string_heavy_tail = b'", "deep": ' + _nested_arrays(MAX_JSON_NESTING_DEPTH) + b"}"
        filler = b'[{\\"' * ((MAX_REQUEST_BODY_BYTES - len(string_heavy_head) - len(string_heavy_tail)) // 4)
        assert json_nesting_exceeds(string_heavy_head + filler + string_heavy_tail, max_depth=MAX_JSON_NESTING_DEPTH)
        assert not json_nesting_exceeds(string_heavy_head + filler + string_heavy_tail, max_depth=MAX_JSON_NESTING_DEPTH + 1)

        flat = b"[" + b"[]," * ((MAX_REQUEST_BODY_BYTES - 4) // 3) + b"[]]"
        assert not json_nesting_exceeds(flat, max_depth=2)
        assert json_nesting_exceeds(flat, max_depth=1)

    def test_typed_route_refuses_a_body_past_the_limit(self):
        # The lint route declares its body, so FastAPI parses it: the check runs in front of FastAPI.
        response = _client().post(
            "/v1/lint",
            content=b'{"content": ' + json.dumps(VALID_MTHDS).encode() + b', "padding": ' + _nested_arrays(MAX_JSON_NESTING_DEPTH) + b"}",
            headers={"content-type": "application/json"},
        )

        problem = assert_problem(response, status=422, code="request.malformed")
        assert problem["domain"] == "input"
        assert problem["params"] == {"reason": TOO_DEEPLY_NESTED_REASON}

    def test_typed_route_accepts_a_body_at_the_limit(self):
        response = _client().post(
            "/v1/lint",
            content=b'{"content": ' + json.dumps(VALID_MTHDS).encode() + b', "padding": ' + _nested_arrays(MAX_JSON_NESTING_DEPTH - 1) + b"}",
            headers={"content-type": "application/json"},
        )

        assert response.status_code == 200, response.text
        assert response.json() == {"diagnostics": []}

    def test_typed_route_refuses_a_body_deep_enough_to_overflow_the_parser(self):
        # FastAPI used to turn the parser's `RecursionError` into a bare 400, and on Python 3.14 a large
        # stack let the body through: either way, it is now the 422 every other route answers.
        response = _client().post(
            "/v1/lint",
            content=b'{"content": "", "padding": ' + _nested_arrays(RECURSION_DEEP) + b"}",
            headers={"content-type": "application/json"},
        )

        problem = assert_problem(response, status=422, code="request.malformed")
        assert problem["params"] == {"reason": TOO_DEEPLY_NESTED_REASON}

    @pytest.mark.parametrize("route", ["/v1/format", "/v1/validate"])
    def test_typed_route_refuses_a_body_that_is_not_utf8_as_the_caller_s(self, route: str):
        # FastAPI's own parse turned the decode error into a bare 400 the handlers could only read as a fault of the
        # server, a 500; the route now parses first and names the reason.
        response = _client().post(route, content=b"\xff{}", headers={"content-type": "application/json"})

        problem = assert_problem(response, status=422, code="request.malformed")
        assert problem["params"] == {"reason": "not_utf8"}

    @pytest.mark.parametrize("route", ["/v1/format", "/v1/validate"])
    def test_typed_route_refuses_an_integer_past_the_digit_limit_as_the_caller_s(self, route: str):
        # `json.loads` refuses an integer literal longer than `sys.get_int_max_str_digits()` with a plain `ValueError`.
        too_long = "1" * (sys.get_int_max_str_digits() + 1)
        response = _client().post(route, content=f'{{"content": "", "padding": {too_long}}}'.encode(), headers={"content-type": "application/json"})

        problem = assert_problem(response, status=422, code="request.malformed")
        assert problem["params"] == {"reason": INTEGER_TOO_LONG_REASON}

    def test_typed_route_reads_a_body_that_is_not_json_as_fastapi_does(self):
        # A body whose content type is not JSON is handed to the model as raw bytes, which it refuses field by field:
        # the route parses only what FastAPI would.
        response = _client().post("/v1/format", content=b"\xff{}", headers={"content-type": "text/plain"})

        assert_problem(response, status=422, code="request.invalid")

    def test_typed_route_reads_a_utf16_body_as_fastapi_does(self):
        body = json.dumps({"content": VALID_MTHDS}).encode("utf-16")
        response = _client().post("/v1/lint", content=body, headers={"content-type": "application/json"})

        assert response.status_code == 200, response.text

    def test_every_route_with_a_json_body_is_bounded(self):
        # Imported here, as in `test_openapi_contract.py`, so a bad env var fails this test rather than the collection.
        from pipelex_api.main import fastapi_app  # noqa: PLC0415

        body_routes = [route for route in fastapi_app.routes if isinstance(route, APIRoute) and route.body_field is not None]
        assert body_routes, "the app declares no route with a body: the invariant below would hold vacuously"
        unbounded = [route.path for route in body_routes if not isinstance(route, JsonBodyRoute)]
        assert not unbounded, f"build these routes' router with route_class=JsonBodyRoute: {unbounded}"

    def test_recursion_error_is_still_refused_as_invalid_json(self, mocker: MockerFixture):
        # The depth check leaves the parser nothing deep enough to raise `RecursionError`; the catch
        # behind it stays, and answers the same 422.
        mocker.patch("pipelex_api.json_body.json_nesting_exceeds", return_value=False)
        mocker.patch("pipelex_api.json_body.json.loads", side_effect=RecursionError("maximum recursion depth exceeded"))

        with pytest.raises(RunnerRequestError) as raised:
            decode_json_body(b'{"inputs": []}')

        # The patch replaces `json.loads` module-wide, and rendering the problem parses JSON too.
        mocker.stopall()
        problem = problem_of(raised.value)
        assert problem["status"] == 422
        assert problem["code"] == "request.malformed"
        assert problem["params"] == {"reason": "not_json"}
        assert isinstance(raised.value.__cause__, RecursionError)


class _TypedBody(BaseModel):
    content: str


async def _typed_endpoint(body: _TypedBody) -> dict[str, str]:
    return {"content": body.content}


def _typed_route() -> JsonBodyRoute:
    return JsonBodyRoute("/typed", _typed_endpoint, methods=["POST"])


def _request_declaring_no_content_type(body: bytes) -> Request:
    """A request to the typed route whose body declares no content type."""

    async def receive() -> Message:
        return {"type": "http.request", "body": body, "more_body": False}

    scope: Scope = {"type": "http", "method": "POST", "path": "/typed", "raw_path": b"/typed", "query_string": b"", "headers": []}
    return Request(scope, receive)


class TestStrictContentType:
    """A body that declares no content type is parsed as JSON exactly where FastAPI's own parse would parse it.

    FastAPI 0.132.0 added a route's `strict_content_type`, which the dependency floor (`fastapi>=0.118.0`) does not
    require, so a release without it must still build and serve the routes, parsing such a body as JSON as it does.
    """

    @pytest.mark.parametrize(
        ("setting", "is_strict"),
        [(Default(True), True), (Default(False), False), (True, True), (False, False)],
    )
    def test_reads_the_route_s_setting(self, mocker: MockerFixture, setting: bool | DefaultPlaceholder, is_strict: bool):
        route = _typed_route()
        mocker.patch.object(route, "strict_content_type", setting)
        assert holds_content_type_strictly(route) is is_strict

    def test_a_route_of_a_fastapi_without_the_setting_does_not_hold_to_its_content_type(self):
        route = _typed_route()
        del route.strict_content_type  # A route as a FastAPI release older than 0.132.0 builds it.
        assert holds_content_type_strictly(route) is False

    @pytest.mark.asyncio
    async def test_a_fastapi_without_the_setting_parses_a_body_declaring_no_content_type(self, mocker: MockerFixture):
        # Its own parse reads such a body as JSON, so the route parses it first, and refuses one that is not UTF-8 as
        # the caller's malformed request, never as the bare 400 FastAPI would raise.
        route = _typed_route()
        del route.strict_content_type
        framework_handler = mocker.AsyncMock(return_value=Response())
        # FastAPI's own handler, which a release without the setting builds without reading it.
        mocker.patch.object(APIRoute, "get_route_handler", return_value=framework_handler)
        handler = route.get_route_handler()

        with pytest.raises(RunnerRequestError) as raised:
            await handler(_request_declaring_no_content_type(b"\xff{}"))

        assert problem_of(raised.value)["params"] == {"reason": "not_utf8"}
        framework_handler.assert_not_awaited()

    @pytest.mark.asyncio
    @pytest.mark.parametrize(("setting", "parses"), [(Default(True), False), (True, False), (Default(False), True), (False, True)])
    async def test_a_fastapi_with_the_setting_parses_as_the_setting_says(
        self, mocker: MockerFixture, setting: bool | DefaultPlaceholder, parses: bool
    ):
        route = _typed_route()
        mocker.patch.object(route, "strict_content_type", setting)
        framework_handler = mocker.AsyncMock(return_value=Response())
        mocker.patch.object(APIRoute, "get_route_handler", return_value=framework_handler)
        handler = route.get_route_handler()
        request = _request_declaring_no_content_type(b"\xff{}")

        if parses:
            with pytest.raises(RunnerRequestError):
                await handler(request)
            framework_handler.assert_not_awaited()
        else:
            # A strict route leaves the body to FastAPI, which reads it as raw bytes the model refuses field by field.
            await handler(request)
            framework_handler.assert_awaited_once()
