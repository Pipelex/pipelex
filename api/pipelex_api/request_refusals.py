"""A request the route's rules refused, field by field, as the runner's refusal: one problem item per field.

FastAPI refuses a body, a query or a path parameter that fails the route's declared model with a
`RequestValidationError`, and the run routes, which validate their extras by hand, meet pydantic's own
`ValidationError`. Both list their faults the same way, each with the location of the field it refused, so both become
one `RunnerRequestError`: `request.invalid`, with one item per refused field, each naming the field as its `field`
parameter and its location, and the first field as the problem's own. A body that is not JSON at all is
`request.malformed` instead, since no field of it could be read.

Only each fault's location and pydantic's message are read. The message, which may quote what the caller sent, rides the
operator's diagnostics alone: a caller reads each item's sentence, which its code renders from the field's name.
"""

from collections.abc import Mapping, Sequence
from typing import Any

from mthds.protocol.problem.registry import CoreCode, RequestMalformedReason
from pipelex.errors.problem import make_location, make_problem_item

from pipelex_api.exceptions import CallbackUrlRefusedError, RunnerRequestError

# The first segment of the location FastAPI gives a fault, naming the part of the request it is in rather than a field.
_REQUEST_PARTS = frozenset({"body", "query", "path", "header", "cookie"})

# The field a fault of the body as a whole is about, such as a model validator's refusal, which names no field.
WHOLE_BODY_FIELD = "body"

# The type pydantic gives a body that is not JSON, which FastAPI reports as a fault of the body.
_JSON_INVALID_TYPE = "json_invalid"

# The longest path a refusal names: a path holds the keys of a mapping the caller sent, which the caller picks the length
# of, so a longer one is cut, marked by an ellipsis.
MAX_REFUSED_FIELD_PATH_LEN = 256

# The most refused fields a refusal names one by one: a list the caller sent can fail item by item, and the first ones
# are enough to start fixing it.
MAX_REFUSED_FIELDS = 50


def refused_field_path(*, loc: Sequence[Any], located_by_request_part: bool) -> str:
    """The dotted path of the field a fault refused, from its location, or `body` for a fault of the body as a whole.

    Args:
        loc: The fault's location, as pydantic gives it.
        located_by_request_part: Whether the location starts with the part of the request it is in, as FastAPI's does,
            which is left out of the path.

    Returns:
        The path, such as `callback_urls.0`, cut to `MAX_REFUSED_FIELD_PATH_LEN` characters.
    """
    parts = [str(part) for part in loc]
    if located_by_request_part and parts and parts[0] in _REQUEST_PARTS:
        parts = parts[1:]
    path = ".".join(parts) or WHOLE_BODY_FIELD
    if len(path) > MAX_REFUSED_FIELD_PATH_LEN:
        return f"{path[:MAX_REFUSED_FIELD_PATH_LEN]}…"
    return path


def _summary(*, faults: Sequence[Mapping[str, Any]], located_by_request_part: bool) -> str:
    """Every fault as `<field>: <message>`, joined: the operator's account of the refusal."""
    described: list[str] = []
    for fault in faults:
        path = refused_field_path(loc=fault.get("loc", ()), located_by_request_part=located_by_request_part)
        described.append(f"{path}: {fault.get('msg') or 'Invalid input'}")
    return "; ".join(described) or "Request validation failed"


def refused_request_error(*, faults: Sequence[Mapping[str, Any]], located_by_request_part: bool) -> RunnerRequestError:
    """The runner's refusal of a request whose fields the route's rules refused, one item per refused field.

    Args:
        faults: The faults pydantic reported, each with its `loc`, `msg` and `type`.
        located_by_request_part: Whether each location starts with the part of the request it is in, as FastAPI's do.

    Returns:
        `request.malformed` for a body that is not JSON, else `request.invalid` with one item per refused field, the
        first `MAX_REFUSED_FIELDS` of them.
    """
    message = _summary(faults=faults, located_by_request_part=located_by_request_part)
    if any(fault.get("type") == _JSON_INVALID_TYPE for fault in faults):
        return RunnerRequestError(message).with_error_code(CoreCode.REQUEST_MALFORMED).with_params(reason=RequestMalformedReason.NOT_JSON)
    paths: list[str] = []
    for fault in faults:
        path = refused_field_path(loc=fault.get("loc", ()), located_by_request_part=located_by_request_part)
        if path not in paths and len(paths) < MAX_REFUSED_FIELDS:
            paths.append(path)
    if not paths:
        paths.append(WHOLE_BODY_FIELD)
    items = [make_problem_item(code=CoreCode.REQUEST_INVALID, params={"field": path}, location=make_location(field=path)) for path in paths]
    return RunnerRequestError(message, field=paths[0]).with_items(items=items)


def callback_url_refusal_in(*, faults: Sequence[Mapping[str, Any]]) -> CallbackUrlRefusedError | None:
    """The refusal of a callback URL the SSRF rules raised among a request's faults, if there is one.

    The rule runs in the request model's validator, and a validator's error rides its fault's context, where pydantic
    keeps the exception it raised. A request that also fails on another field is still the security rule's refusal, so
    the first one found is answered, with its own code, and logs its security event, whatever else failed.
    """
    for fault in faults:
        context: Mapping[str, Any] = fault.get("ctx") or {}
        error: object = context.get("error")
        if isinstance(error, CallbackUrlRefusedError):
            return error
    return None
