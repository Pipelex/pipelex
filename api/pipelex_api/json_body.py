"""JSON request bodies, bounded in nesting depth before any parser reads them.

`json.loads` recurses once per nested array or object. Up to Python 3.13 a deeply nested body made it
raise `RecursionError` at a fixed count; from Python 3.14 the guard is the thread's actual stack size,
so the same body overflows on a small stack and parses on a large one, to be refused later for some
other reason or accepted. The server therefore bounds the nesting itself, before parsing: a body nested
deeper than `MAX_JSON_NESTING_DEPTH` answers the same 422 `InvalidJSON` on every interpreter and stack.

Every JSON body the server parses goes through `ensure_json_nesting_within_limit`, by one of two doors:

- A route that declares a typed body has it parsed by FastAPI. Its router is built with
  `route_class=JsonBodyRoute`, which checks the body before FastAPI parses it, and
  `tests/unit/test_json_body.py` fails when a body-declaring route of the app is not one.
- A route that reads its raw body, as the run routes do, parses it with `decode_json_body`.
"""

import json
import re
from collections.abc import Callable, Coroutine
from itertools import accumulate, cycle
from operator import mul
from typing import Any

from fastapi import Request, Response, params
from fastapi.routing import APIRoute
from typing_extensions import override

from pipelex_api.error_types import ErrorType
from pipelex_api.errors import raise_validation_error
from pipelex_api.limits import MAX_JSON_NESTING_DEPTH

# The two escape sequences that can hide a quote. Once they are gone, every quote left delimits a string.
_ESCAPED_BACKSLASH = b"\\\\"
_ESCAPED_QUOTE = b'\\"'
# Only quotes and brackets matter to nesting, and an object nests like an array.
_NOT_STRUCTURAL = bytes(byte for byte in range(256) if byte not in b'"[]{}')
_BRACES_AS_BRACKETS = bytes.maketrans(b"{}", b"[]")
_ADJACENT_QUOTES = b'""'
_QUOTE = b'"'
_INNERMOST_PAIR = b"[]"
_OPEN_BRACKET = ord("[")
_BRACKET_RUN = re.compile(rb"\[+|\]+")
# Peeling stops once a pass removes less than this fraction of the brackets the scan started with.
_PEEL_STOP_DIVISOR = 8
# The stages that build a list per piece, splitting at quotes and measuring runs, work a chunk at a time,
# so no list grows with the body and its memory stays bounded however the body is shaped.
_CHUNK_BYTES = 1 << 20


def _as_utf8(body: bytes) -> bytes:
    """Return the body in UTF-8, the encoding the scan reads.

    `json.loads` given bytes also accepts UTF-16 and UTF-32, which FastAPI passes it as they come, and in
    which a quote or an escape is not the single byte the scan looks for. Such a body is transcoded the way
    `json.loads` decodes it. A body that does not decode is answered empty: the parser fails on the same
    bytes before it reads a single bracket.
    """
    encoding = json.detect_encoding(body)
    if encoding in {"utf-8", "utf-8-sig"}:
        return body
    try:
        return body.decode(encoding, "surrogatepass").encode("utf-8", "surrogatepass")
    except UnicodeError:
        return b""


def _brackets_outside_strings(body: bytes) -> bytes:
    r"""Return the body's brackets that lie outside strings, in order, with every brace written as a bracket.

    The escapes that can hide a quote are dropped first: removing every `\\` and then every `\"`, each
    left to right, pairs a run of backslashes the way a parser does. The body is then cut down to its quotes
    and brackets. Adjacent quotes enclose no bracket, whether they open and close one string or close one and
    open the next, so dropping them changes nothing and spares the split below a piece per short string.
    With every quote left a delimiter, the pieces between quotes alternate outside and inside strings,
    starting outside, and the outside ones hold the brackets that nest. The skeleton is split a chunk at a
    time, each chunk starting inside a string when the quotes before it are odd in number. An unterminated
    string runs to the end, as it does for a parser.
    """
    unescaped = body.replace(_ESCAPED_BACKSLASH, b"").replace(_ESCAPED_QUOTE, b"")
    skeleton = unescaped.translate(_BRACES_AS_BRACKETS, _NOT_STRUCTURAL).replace(_ADJACENT_QUOTES, b"")
    outside: list[bytes] = []
    in_string = False
    for start in range(0, len(skeleton), _CHUNK_BYTES):
        pieces = skeleton[start : start + _CHUNK_BYTES].split(_QUOTE)
        outside.append(b"".join(pieces[1 if in_string else 0 :: 2]))
        # A chunk split into an even number of pieces holds an odd number of quotes.
        in_string ^= len(pieces) % 2 == 0
    return b"".join(outside)


def json_nesting_exceeds(body: bytes, *, max_depth: int) -> bool:
    """Tell whether a JSON body nests its arrays and objects more than `max_depth` levels deep, without parsing it.

    The answer is exact for a valid JSON document. For an invalid one it is never lower than the depth a
    parser reaches before it stops, so no body this lets through makes `json.loads` recurse past `max_depth`.

    It costs time linear in the body and never loops in Python over its bytes: a multi-megabyte body is
    mostly strings, which `bytes` operations skip at C speed, and the brackets left are measured in two
    stages. First, each pass of `replace(b"[]", b"")` removes the innermost level of every array and object
    at once, which leaves the depth of every remaining bracket unchanged and lowers the deepest point by
    exactly one. Passes continue while they remove much, which settles flat and shallow documents
    outright. Then the runs of opening and closing brackets that remain, few by then, are summed in turn,
    and the deepest running total plus the levels peeled is the body's depth.
    """
    brackets = _brackets_outside_strings(_as_utf8(body))
    stop_below = len(brackets) // _PEEL_STOP_DIVISOR
    peeled = 0
    while brackets:
        shorter = brackets.replace(_INNERMOST_PAIR, b"")
        removed = len(brackets) - len(shorter)
        if not removed:
            break
        brackets = shorter
        peeled += 1
        if peeled > max_depth:
            return True
        if removed < stop_below:
            break
    depth = 0
    for start in range(0, len(brackets), _CHUNK_BYTES):
        chunk = brackets[start : start + _CHUNK_BYTES]
        # Maximal runs alternate between opening and closing brackets, so their signs alternate too.
        signs = cycle((1, -1) if chunk[0] == _OPEN_BRACKET else (-1, 1))
        running = list(accumulate(map(mul, map(len, _BRACKET_RUN.findall(chunk)), signs), initial=depth))
        if max(running) + peeled > max_depth:
            return True
        depth = running[-1]
    return False


def ensure_json_nesting_within_limit(body: bytes) -> None:
    """Refuse a request body nested deeper than `MAX_JSON_NESTING_DEPTH` with a 422 `InvalidJSON`."""
    if json_nesting_exceeds(body, max_depth=MAX_JSON_NESTING_DEPTH):
        raise_validation_error(
            message=f"Request body is nested too deeply: its JSON arrays and objects may nest at most {MAX_JSON_NESTING_DEPTH} levels.",
            error_type=ErrorType.INVALID_JSON,
        )


def decode_json_body(body: bytes) -> Any:
    """Parse a raw request body as plain JSON, refusing it with a 422 `InvalidJSON` when it cannot be.

    For a route that reads its body itself rather than declaring a typed one. The refusals are caller
    mistakes, never a sanitized 500:
      - a body nested deeper than `MAX_JSON_NESTING_DEPTH`, checked before parsing;
      - `UnicodeDecodeError`: the bytes are not valid UTF-8;
      - `ValueError`: `json.JSONDecodeError`, which subclasses it;
      - `RecursionError`: the depth check leaves the parser nothing deep enough to raise it, so this only
        stands as a second line of defence.
    """
    ensure_json_nesting_within_limit(body)
    try:
        return json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, ValueError, RecursionError) as exc:
        raise_validation_error(
            message=f"Request body is not valid JSON: {exc!s}",
            error_type=ErrorType.INVALID_JSON,
        )


class JsonBodyRoute(APIRoute):
    """An `APIRoute` that checks a declared JSON body's nesting depth before FastAPI parses it.

    FastAPI parses a typed body with `json.loads` and turns any failure but a `JSONDecodeError` into a
    bare 400, so the check runs in front of FastAPI's own handler, where its 422 reaches the API's
    exception handlers like any other `ApiError`. The body it reads is cached on the request, so FastAPI
    does not read it twice. A route that declares no body, or a form body, is left as it is: one that
    reads its raw body parses it with `decode_json_body`.
    """

    @override
    def get_route_handler(self) -> Callable[[Request], Coroutine[Any, Any, Response]]:
        handler = super().get_route_handler()
        if self.body_field is None or isinstance(self.body_field.field_info, params.Form):
            # No body, or a form body, which FastAPI never hands to `json.loads`.
            return handler

        async def bounded_handler(request: Request) -> Response:
            ensure_json_nesting_within_limit(await request.body())
            return await handler(request)

        return bounded_handler
