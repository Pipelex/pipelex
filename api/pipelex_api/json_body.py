"""JSON request bodies, bounded in nesting depth before any parser reads them.

`json.loads` recurses once per nested array or object. Up to Python 3.13 a deeply nested body made it
raise `RecursionError` at a fixed count; from Python 3.14 the guard is the thread's actual stack size,
so the same body overflows on a small stack and parses on a large one, to be refused later for some
other reason or accepted. The server therefore bounds the nesting itself, before parsing: a body nested
deeper than `MAX_JSON_NESTING_DEPTH` answers the same 422 `request.malformed` on every interpreter and stack.

Every JSON body the server parses goes through `ensure_json_nesting_within_limit`, by one of two doors:

- A route that declares a typed body is built with `route_class=JsonBodyRoute`, which checks the body and parses it
  before FastAPI validates it, and `tests/unit/test_json_body.py` fails when a body-declaring route of the app is not
  one. FastAPI's own parse turns any failure but a `JSONDecodeError` into a bare 400, which the error handlers could
  only read as a fault of the server; parsing it here first answers each one as the caller's `request.malformed`.
- A route that reads its raw body, as the run routes do, parses it with `decode_json_body`.

Both doors refuse a body in the same words: one nested too deeply (`too_deeply_nested`), one whose bytes do not decode
(`not_utf8`), one that is not JSON (`not_json`), and one holding an integer longer than Python reads from a string
(`integer_too_long`, past `sys.get_int_max_str_digits()`), each a 422 `request.malformed`.
"""

import email.message
import json
import re
from collections.abc import Callable, Coroutine
from itertools import accumulate, cycle
from operator import mul
from typing import Any

from fastapi import Request, Response, params
from fastapi.datastructures import DefaultPlaceholder
from fastapi.routing import APIRoute
from mthds.protocol.problem.registry import CoreCode, RequestMalformedReason
from starlette.types import Receive, Scope
from typing_extensions import override

from pipelex_api.exceptions import RunnerRequestError
from pipelex_api.limits import MAX_JSON_NESTING_DEPTH
from pipelex_api.run_extras_binding import bind_run_extras

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


# The reason a body nested past the limit is malformed. The code's reasons name no nesting depth, and its reason takes
# any string beside them, so the runner names this one itself: no size limit of the registry counts levels.
TOO_DEEPLY_NESTED_REASON = "too_deeply_nested"

# The reason a body holding an integer literal longer than Python converts from a string is malformed: JSON sets no bound
# on a number's digits, the parser refuses past `sys.get_int_max_str_digits()`, and none of the code's reasons names it.
INTEGER_TOO_LONG_REASON = "integer_too_long"


def ensure_json_nesting_within_limit(body: bytes) -> None:
    """Refuse a request body nested deeper than `MAX_JSON_NESTING_DEPTH` with a 422 `request.malformed`."""
    if json_nesting_exceeds(body, max_depth=MAX_JSON_NESTING_DEPTH):
        msg = f"Request body is nested too deeply: its JSON arrays and objects may nest at most {MAX_JSON_NESTING_DEPTH} levels"
        raise RunnerRequestError(msg).with_error_code(CoreCode.REQUEST_MALFORMED).with_params(reason=TOO_DEEPLY_NESTED_REASON)


def _malformed(*, message: str, reason: str) -> RunnerRequestError:
    return RunnerRequestError(message).with_error_code(CoreCode.REQUEST_MALFORMED).with_params(reason=reason)


def _loads_json_text(text: str) -> Any:
    """Parse a decoded body as JSON, refusing it with a 422 `request.malformed` naming why it cannot be.

    - `json.JSONDecodeError`: the text is not JSON;
    - any other `ValueError`, which `json.loads` given a string raises only for an integer literal longer than
      `sys.get_int_max_str_digits()`: the integer is too long to read;
    - `RecursionError`: the depth check leaves the parser nothing deep enough to raise it, so this only stands as a
      second line of defence.
    """
    try:
        return json.loads(text)
    except (json.JSONDecodeError, RecursionError) as exc:
        msg = f"Request body is not valid JSON: {exc!s}"
        raise _malformed(message=msg, reason=RequestMalformedReason.NOT_JSON) from exc
    except ValueError as exc:
        msg = f"Request body holds an integer too long to read: {exc!s}"
        raise _malformed(message=msg, reason=INTEGER_TOO_LONG_REASON) from exc


def decode_json_body(body: bytes) -> Any:
    """Parse a raw request body as plain JSON, refusing it with a 422 `request.malformed` when it cannot be.

    For a route that reads its body itself rather than declaring a typed one. The refusals are caller
    mistakes, never a sanitized 500: a body nested deeper than `MAX_JSON_NESTING_DEPTH`, checked before parsing;
    bytes that are not valid UTF-8; and the parse's own refusals (`_loads_json_text`).
    """
    ensure_json_nesting_within_limit(body)
    try:
        text = body.decode("utf-8")
    except UnicodeDecodeError as exc:
        msg = f"Request body is not valid UTF-8: {exc!s}"
        raise _malformed(message=msg, reason=RequestMalformedReason.NOT_UTF8) from exc
    return _loads_json_text(text)


def parse_typed_json_body(body: bytes) -> Any:
    """Parse a typed route's body as FastAPI would, refusing what FastAPI could only answer with a bare 400.

    The bytes are decoded the way `json.loads` decodes bytes, which FastAPI hands them to: in the UTF-8, UTF-16 or
    UTF-32 the body's first bytes spell, a BOM dropped. A body that does not decode is `not_utf8`, the encoding JSON
    exchanged between systems must use; the parse's own refusals are `_loads_json_text`'s.
    """
    try:
        text = body.decode(json.detect_encoding(body), "surrogatepass")
    except UnicodeDecodeError as exc:
        msg = f"Request body does not decode as JSON text: {exc!s}"
        raise _malformed(message=msg, reason=RequestMalformedReason.NOT_UTF8) from exc
    return _loads_json_text(text)


class _ParsedJsonRequest(Request):
    """A request whose body was parsed before FastAPI asked for it, so FastAPI reads that value rather than parse again."""

    def __init__(self, scope: Scope, receive: Receive) -> None:
        super().__init__(scope, receive)
        self._parsed_body: Any = None
        self._is_body_parsed = False

    def hold_parsed_body(self, parsed: Any) -> None:
        self._parsed_body = parsed
        self._is_body_parsed = True

    @override
    async def json(self) -> Any:
        if self._is_body_parsed:
            return self._parsed_body
        return await super().json()


class JsonBodyRoute(APIRoute):
    """An `APIRoute` that checks and parses a declared JSON body before FastAPI validates it.

    FastAPI parses a typed body with `json.loads` and turns any failure but a `JSONDecodeError` into a
    bare 400, an `HTTPException` the error handlers cannot tell from a fault of the server: bytes that do not decode,
    an integer past Python's digit limit, a parser recursing out of stack. This route reads the body, checks its nesting
    depth and parses it in front of FastAPI's own handler, so each of those is the caller's 422 `request.malformed`
    reaching the API's exception handlers like any other `PipelexError`. The handler receives a request built from the
    same connection that holds the body and its parsed value, so FastAPI neither reads nor parses the body again. A
    route that declares no body, or a form body, is left as it is: one that reads its raw body parses it with
    `decode_json_body`.

    The body is parsed only where FastAPI would parse it, a body with bytes whose content type is JSON (`_reads_as_json`):
    FastAPI hands any other body to the model as raw bytes, which the model refuses field by field, and so does this route.
    A parsed body's `analytics_groups` are bound on the request before FastAPI validates any field
    (`pipelex_api.run_extras_binding`), so the security event of a refusal of the request names whose request it was.
    """

    @override
    def get_route_handler(self) -> Callable[[Request], Coroutine[Any, Any, Response]]:
        handler = super().get_route_handler()
        if self.body_field is None or isinstance(self.body_field.field_info, params.Form):
            # No body, or a form body, which FastAPI never hands to `json.loads`.
            return handler
        is_strict = holds_content_type_strictly(self)

        async def parsing_handler(request: Request) -> Response:
            parsed_request = _ParsedJsonRequest(request.scope, request.receive)
            body = await parsed_request.body()
            ensure_json_nesting_within_limit(body)
            if body and _reads_as_json(content_type=parsed_request.headers.get("content-type"), is_strict=is_strict):
                parsed_body = parse_typed_json_body(body)
                # Before FastAPI validates a field, so a refusal of this request names whose request it was.
                bind_run_extras(request=parsed_request, body=parsed_body)
                parsed_request.hold_parsed_body(parsed_body)
            return await handler(parsed_request)

        return parsing_handler


# FastAPI 0.132.0 added a route's `strict_content_type`, which defaults to `True`. The releases before it, which the
# dependency floor still admits, have no such attribute and parse a body that declares no content type as JSON, as a
# route that does not hold to its content type does: this is the value they behave by.
_STRICT_CONTENT_TYPE_BEFORE_FASTAPI_0_132 = False


def holds_content_type_strictly(route: APIRoute) -> bool:
    """Whether FastAPI refuses to parse a body that declares no content type as JSON on this route.

    Read from the route's `strict_content_type`, the setting FastAPI's own parse reads, a default it was given unwrapped
    to its value. A FastAPI release older than 0.132.0 has no such setting and always parses that body as JSON, so a
    route of one reads as not strict.
    """
    strict_content_type = getattr(route, "strict_content_type", _STRICT_CONTENT_TYPE_BEFORE_FASTAPI_0_132)
    if isinstance(strict_content_type, DefaultPlaceholder):
        return bool(strict_content_type.value)
    return bool(strict_content_type)


def _reads_as_json(*, content_type: str | None, is_strict: bool) -> bool:
    """Whether FastAPI parses a typed body of this content type as JSON, by its own rule.

    A JSON media type, `application/json` or `application/<anything>+json`, is parsed; a body that declares no content
    type is parsed only on a route that does not hold to its content type strictly; any other body is not.
    """
    if not content_type:
        return not is_strict
    message = email.message.Message()
    message["content-type"] = content_type
    if message.get_content_maintype() != "application":
        return False
    subtype = message.get_content_subtype()
    return subtype == "json" or subtype.endswith("+json")
