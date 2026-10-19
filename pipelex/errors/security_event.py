"""The security event: one structured record for each refusal a security rule makes, carrying no content.

A refusal for safety fails the run under a code of the ``security.`` family, or of Pipelex's own
``pipelex.security.`` family, whose domain says who caused it. Beside that failure the deployment logs one security
event, so that whoever runs it learns that someone tried to reach what a rule forbids: the hosted plane routes it to
its alerts and its digest, and an on-premises deployment receives it in its own sinks. It is a record of its own
kind, routable without reading its text: it is logged on this module's logger, ``pipelex.errors.security_event``,
with the fixed message :data:`SECURITY_EVENT_MESSAGE`, and its ``event.name`` field is :data:`SECURITY_EVENT_NAME`.

Its fields name the refusal and never its content:

- ``error.code``, ``error.domain`` and ``error.type``: the refusal's code, the code's domain, and the class of the
  error that carries or implies the code, never a wrapper above it;
- ``security.target``: the kind of thing refused, a URL, a path, a template, a schema, which the code decides;
- ``security.target_class``: the class of destination refused, a loopback or a private address, a cloud metadata
  endpoint, a scheme, when the raise site stated it (:class:`~pipelex.errors.security_target.SecurityTargetClass`);
- ``pipeline_run_id`` and ``request_id``, when there is a run or a request;
- ``run.extras.<key>``: each of the run's opaque extras, the labels a host attaches to a run, which the hosted
  plane fills with the organization. The runtime never reads one by name.

Never the URL, the path, the template, the schema, a prompt, an input value, nor the error's message, which may
quote any of them; never a traceback either, since the failure itself is logged and reported where it is handled.

A refusal is reported once per process, however many boundaries it crosses: the event marks the errors of the
chain it reported, and a boundary the same failure reaches again, wrapped, finds the refusal marked and logs nothing.
A refusal is the error that carries or implies the code its failure reports, so a wrapper chained to it with ``from``,
which takes its code, restates it, while a new refusal is reported on its own, even of the same code, even raised
while a reported one was being handled or chained to one with ``from``.
"""

from __future__ import annotations

import weakref
from typing import TYPE_CHECKING, Any

from mthds.protocol.problem.registry import CoreCode

from pipelex.base_exceptions import PipelexError, iter_cause_chain
from pipelex.errors.error_code_declaration import InheritsCause
from pipelex.errors.error_codes import ErrorCode, error_code_spec
from pipelex.errors.registry.pipelex_codes import PipelexErrorCode
from pipelex.errors.security_target import SecurityTargetClass, SecurityTargetKind
from pipelex.tools.log.error_fields import ERROR_TYPE_FIELD
from pipelex.tools.log.log import log
from pipelex.tools.log.log_context import PIPELINE_RUN_ID_FIELD, REQUEST_ID_FIELD

if TYPE_CHECKING:
    from collections.abc import Mapping

    from pipelex.system.job_metadata import RunMetadata

#: The message every security event is logged with, which a query or an alert selects the events by.
SECURITY_EVENT_MESSAGE = "A security rule refused a request"

#: The value of the event's ``event.name`` field, which names the kind of record whatever its logger.
SECURITY_EVENT_NAME = "pipelex.security.refusal"

#: The field naming the kind of record, the OpenTelemetry semantic-convention key for a log event's name.
EVENT_NAME_FIELD = "event.name"

#: The field carrying the refusal's registry code.
ERROR_CODE_FIELD = "error.code"

#: The field carrying the code's domain, who caused the refusal.
ERROR_DOMAIN_FIELD = "error.domain"

#: The field carrying the kind of thing refused.
SECURITY_TARGET_FIELD = "security.target"

#: The field carrying the class of destination refused, present only when the raise site stated it.
SECURITY_TARGET_CLASS_FIELD = "security.target_class"

#: The prefix of the fields carrying the run's extras, one field per key.
RUN_EXTRAS_FIELD_PREFIX = "run.extras."

#: The kind of thing each security code refuses. Every code of the two security families has an entry, which a test
#: checks against both registries, so a new security code cannot ship without saying what it refuses.
SECURITY_TARGET_KIND_BY_CODE: dict[ErrorCode, SecurityTargetKind] = {
    CoreCode.SECURITY_INPUT_URL_REFUSED: SecurityTargetKind.URL,
    CoreCode.SECURITY_METHOD_URL_REFUSED: SecurityTargetKind.URL,
    CoreCode.SECURITY_PROVIDER_URL_REFUSED: SecurityTargetKind.URL,
    CoreCode.SECURITY_INPUT_PATH_REFUSED: SecurityTargetKind.PATH,
    CoreCode.SECURITY_METHOD_PATH_REFUSED: SecurityTargetKind.PATH,
    CoreCode.SECURITY_TEMPLATE_REFUSED: SecurityTargetKind.TEMPLATE,
    CoreCode.SECURITY_SCHEMA_REFUSED: SecurityTargetKind.SCHEMA,
    CoreCode.SECURITY_INTEGRITY_MISMATCH: SecurityTargetKind.DEPENDENCY,
    PipelexErrorCode.SECURITY_RESERVED_KEY: SecurityTargetKind.OBJECT_KEY,
    PipelexErrorCode.SECURITY_RESULT_OUTSIDE_SCOPE: SecurityTargetKind.RESULT_LOCATION,
}

# The errors whose refusal has been reported, held weakly so the mark never keeps an error alive.
_REPORTED_ERRORS: weakref.WeakSet[PipelexError] = weakref.WeakSet()


def security_target_kind(*, code: ErrorCode) -> SecurityTargetKind | None:
    """The kind of thing a code refuses, ``None`` for a code that is no security refusal.

    Args:
        code: A registered code.

    Returns:
        The kind for a code of the ``security.`` or ``pipelex.security.`` family, else ``None``.
    """
    return SECURITY_TARGET_KIND_BY_CODE.get(code)


def is_security_refusal(*, error: BaseException) -> bool:
    """Whether a failure reports a code of the ``security.`` or ``pipelex.security.`` family, wherever it was coded.

    A refusal coded so at its raise site is a security refusal whatever its class, a ``SecurityError`` or not, so a
    handler that answers the caller's input with a domain answer, a validation verdict included, lets it through as it
    is rather than replacing its code with its own.

    Args:
        error: The failure, the outermost error of its chain.

    Returns:
        Whether its code is a security refusal's.
    """
    return isinstance(error, PipelexError) and security_target_kind(code=error.resolve_error_code()) is not None


def mark_security_event_emitted(*, error: BaseException) -> None:
    """Record that the security event of ``error``'s failure was logged, so no boundary logs it again in this process.

    :func:`emit_security_event` marks what it reports by itself. A host calls this for a failure whose event was
    logged elsewhere, such as the error a transport rebuilds from a worker's report, so that the boundary it reaches
    here does not report the same refusal a second time.

    Args:
        error: The failure, the outermost error of its chain.
    """
    for node in iter_cause_chain(error):
        if isinstance(node, PipelexError):
            _REPORTED_ERRORS.add(node)


def emit_security_event(
    *,
    error: BaseException,
    pipeline_run_id: str | None = None,
    request_id: str | None = None,
    extras: Mapping[str, str] | None = None,
) -> bool:
    """Log the security event of a failure, when its code is a security refusal and nobody reported it yet.

    The code is the one the failure reports (:meth:`~pipelex.base_exceptions.PipelexError.resolve_error_code`), so a
    refusal wrapped by every boundary it crossed is still recognized. A failure whose refusal, the error of its chain
    that carries or implies that code, was reported already logs nothing; the errors of the chain are marked once the
    event is logged.

    Args:
        error: The failure, the outermost error of its chain. One that is not a ``PipelexError`` reports no code
            and logs nothing.
        pipeline_run_id: The run the refusal failed, when there is one.
        request_id: The request the refusal answered, when there is one. Either identifier left out is taken
            from the log context bound where the event is logged, if any.
        extras: The run's opaque extras, each logged as a field of its own.

    Returns:
        Whether a security event was logged.
    """
    if not isinstance(error, PipelexError):
        return False
    code = error.resolve_error_code()
    target_kind = security_target_kind(code=code)
    if target_kind is None:
        return False
    refusal = _code_carrier(error=error)
    if refusal in _REPORTED_ERRORS:
        return False
    log_security_event(
        code=code,
        error_type=type(refusal).__name__,
        target_class=_stated_target_class(error=error),
        pipeline_run_id=pipeline_run_id,
        request_id=request_id,
        extras=extras,
    )
    mark_security_event_emitted(error=error)
    return True


def emit_security_event_for_run(*, error: BaseException, run_metadata: RunMetadata) -> bool:
    """Log the security event of a run's failure, naming the run, its request and its extras.

    Args:
        error: The run's failure, the outermost error of its chain.
        run_metadata: The run's identity.

    Returns:
        Whether a security event was logged.
    """
    return emit_security_event(
        error=error,
        pipeline_run_id=run_metadata.pipeline_run_id,
        request_id=run_metadata.request_id,
        extras=run_metadata.extras,
    )


def log_security_event(
    *,
    code: ErrorCode,
    error_type: str,
    target_class: SecurityTargetClass | None = None,
    pipeline_run_id: str | None = None,
    request_id: str | None = None,
    extras: Mapping[str, str] | None = None,
) -> None:
    """Log one security event from its parts, for a refusal that is not a ``PipelexError`` of this process.

    :func:`emit_security_event` derives the parts from a failure and calls this. A host calls it directly for a
    refusal it decides itself, such as one a gateway answered, and then owes the event's rule itself: no content in
    any part.

    Args:
        code: The refusal's code. A code outside the security families still logs, with no ``security.target``.
        error_type: The class name of the error that refused, never its message.
        target_class: The class of destination refused, when the refusing site knows it.
        pipeline_run_id: The run the refusal failed, when there is one.
        request_id: The request the refusal answered, when there is one.
        extras: The run's opaque extras, each logged as a field of its own.
    """
    fields: dict[str, Any] = {
        EVENT_NAME_FIELD: SECURITY_EVENT_NAME,
        ERROR_CODE_FIELD: code,
        ERROR_DOMAIN_FIELD: error_code_spec(code).domain,
        ERROR_TYPE_FIELD: error_type,
    }
    target_kind = security_target_kind(code=code)
    if target_kind is not None:
        fields[SECURITY_TARGET_FIELD] = target_kind
    if target_class is not None:
        fields[SECURITY_TARGET_CLASS_FIELD] = target_class
    if pipeline_run_id is not None:
        fields[PIPELINE_RUN_ID_FIELD] = pipeline_run_id
    if request_id is not None:
        fields[REQUEST_ID_FIELD] = request_id
    for extras_key, extras_value in (extras or {}).items():
        fields[f"{RUN_EXTRAS_FIELD_PREFIX}{extras_key}"] = extras_value
    log.warning(SECURITY_EVENT_MESSAGE, fields=fields)


def _code_carrier(*, error: PipelexError) -> PipelexError:
    """The error of the chain that names the code ``error`` reports, the refusal the wrappers above it report.

    It is read in the walk :meth:`~pipelex.base_exceptions.PipelexError.resolve_error_code` makes, so the two cannot
    disagree: the first error down the chain that carries a code by itself, where that walk stops; when none does, the
    deepest error that implies a code, else the deepest that names its fallback, whose code the chain then reports; and
    the outermost error when none names one. It is the refusal's identity: two failures report the same refusal when
    they name the same error here, which is how a wrapper is told from a new refusal of the same code.
    """
    implied_carrier: PipelexError | None = None
    fallback_carrier: PipelexError | None = None
    for node in iter_cause_chain(error):
        if not isinstance(node, PipelexError):
            break
        if node.own_error_code is not None:
            return node
        if node.implied_error_code is not None:
            implied_carrier = node
        if isinstance(type(node).error_code, InheritsCause):
            fallback_carrier = node
    return implied_carrier or fallback_carrier or error


def _stated_target_class(*, error: PipelexError) -> SecurityTargetClass | None:
    """The class of destination the first error down the chain states, ``None`` when none states one."""
    for node in iter_cause_chain(error):
        if not isinstance(node, PipelexError):
            break
        target_class = node.security_target_class
        if target_class is not None:
            return target_class
    return None
