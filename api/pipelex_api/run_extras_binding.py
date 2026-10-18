"""The labels a host attaches to a request, its `analytics_groups`, bound on the request before anything is refused.

The hosted plane fills them with the organization a request is made for. A refusal answered before the request's work
begins, a path leaving its tree, a callback URL aimed at a private address, a reserved object key, logs a security event
(`pipelex.errors.security_event`), which names whose request it was by those labels, as `run.extras.<key>`. So they are
read off the body as soon as it is parsed, before any field is refused: by `JsonBodyRoute` for every route declaring a
typed body, `/validate`, `/resolve`, `/codegen`, `/pipe-io` and `/v1/blobs/missing` among them, and by the run routes,
which parse their raw body themselves. The exception handlers read them back (`_run_extras_of`).

Only labels that pass the runtime's own rules on their own are bound (`pipelex.system.run_extras.validate_run_extras`),
so the event never carries a value the runtime would refuse, and a body whose labels are refused binds none: that
refusal is the request's own `request.invalid`, answered when its model is validated.
"""

from typing import Any

from fastapi import Request
from pydantic import ValidationError

from pipelex_api.schemas.models import CallerAnalyticsGroupsMixin

ANALYTICS_GROUPS_FIELD = "analytics_groups"


def validated_run_extras_or_none(*, body: Any) -> dict[str, str] | None:
    """The body's `analytics_groups` when they pass the runtime's rules on their own, else `None`.

    Args:
        body: The request's parsed JSON body, whatever its shape: a body that is not an object names no labels.

    Returns:
        The labels, or `None` when the body names none or names some the runtime refuses.
    """
    if not isinstance(body, dict):
        return None
    try:
        return CallerAnalyticsGroupsMixin.model_validate({ANALYTICS_GROUPS_FIELD: body.get(ANALYTICS_GROUPS_FIELD)}).analytics_groups
    except ValidationError:
        return None


def bind_run_extras(*, request: Request, body: Any) -> None:
    """Bind the body's valid labels on the request's state, where the exception handlers read them.

    The state lives in the request's scope, so every `Request` built from it, the one an exception handler receives
    included, reads what this one bound.

    Args:
        request: The request whose body was parsed.
        body: Its parsed JSON body.
    """
    request.state.run_extras = validated_run_extras_or_none(body=body)
