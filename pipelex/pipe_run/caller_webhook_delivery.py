"""The delivery of a run's end to the webhooks its caller registered: one signed ``run.finished`` event per URL.

This is the self-hosted sender of the caller-webhook contract (Pipelex's conformance spec ``pipelex-caller-webhooks``):

- **The event.** The body is ``{"type": "run.finished", "timestamp": <when the run ended>, "attempt": <n>, "data":
  <the run as its caller's status read serves it>}``, written as compact JSON in UTF-8. ``data`` is the MTHDS protocol's
  ``RunRead``: the run's ``pipeline_run_id``, its ``status``, ``completed`` or ``failed``, and a failed run's problem as
  ``error``, in the caller's view, so it never carries ``diagnostics``. The event carries no result.
- **The signature.** Each call carries the Standard Webhooks headers: ``webhook-id``, the delivery's id, the same on
  every attempt of it; ``webhook-timestamp``, the attempt's send time in Unix seconds; and ``webhook-signature``, one
  ``v1,`` signature per secret the process holds (:mod:`pipelex.tools.network.standard_webhooks`). The secrets are read
  from :data:`CALLER_WEBHOOK_SECRET_ENV` when the delivery runs, in the process that delivers, so no secret and no
  signature ever travels with a run's job.
- **The delivery.** Every URL is delivered on its own and at the same time as the others, with a short retry: an attempt
  succeeds on a ``2xx`` answered within :data:`ATTEMPT_BUDGET_SECONDS`, redirects are never followed, and a failed
  attempt is tried again after each wait of :data:`RETRY_WAITS_SECONDS`. A destination the SSRF guard refuses logs its
  security event and is not tried again. A delivery that fails is logged and returned as its outcome, and never raises:
  it changes neither the run's outcome nor any other delivery.
"""

from __future__ import annotations

import asyncio
import json
from asyncio import sleep
from datetime import UTC
from enum import StrEnum
from time import time
from typing import TYPE_CHECKING, Any
from urllib.parse import urlsplit

import httpx
from mthds.protocol.problem.registry import CoreCode
from pydantic import BaseModel, ConfigDict, Field

from pipelex import log
from pipelex.errors.problem import PipelexProblem, ProblemView, caller_view_of, make_problem
from pipelex.errors.security_event import emit_security_event
from pipelex.pipe_run.delivery_assignment import DeliveryStatus
from pipelex.pipe_run.exceptions import CallerWebhookSecretError
from pipelex.system.environment import get_optional_env
from pipelex.tools.network.exceptions import SsrfBlockedError
from pipelex.tools.network.ssrf_guard import SsrfGuardedTransport
from pipelex.tools.network.standard_webhooks import decode_webhook_secret, sign_webhook

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence
    from datetime import datetime

    from pipelex.pipe_run.delivery_assignment import CallerWebhookTarget

CALLER_WEBHOOK_SECRET_ENV = "CALLER_WEBHOOK_SECRET"
"""The environment variable holding the secret a caller's webhooks are signed with.

One ``whsec_`` secret, or several separated by spaces during a rotation, the current one first: each signs every call,
so a receiver holding either verifies it.
"""

RUN_FINISHED_EVENT_TYPE = "run.finished"
"""The event's ``type``: one type for every ending, the outcome being ``data.status``."""

ATTEMPT_BUDGET_SECONDS = 15.0
"""How long an attempt may take, from the call being sent to the receiver's answer, before it counts as failed."""

RETRY_WAITS_SECONDS: tuple[float, ...] = (1.0, 5.0)
"""The waits before the second attempt and each later one: three attempts in all, within the run's delivery step."""


class EndedRunStatus(StrEnum):
    """The status of an ended run as the protocol's status read writes it."""

    COMPLETED = "completed"
    FAILED = "failed"


class CallerWebhookFailure(StrEnum):
    """Why a caller webhook's delivery failed, as its last attempt ended."""

    HTTP_STATUS = "http_status"
    """The receiver answered with a status outside ``2xx``, a redirect included."""
    TIMEOUT = "timeout"
    """The receiver did not answer within the attempt's budget."""
    UNREACHABLE = "unreachable"
    """The receiver could not be reached: its name did not resolve, or the connection or its TLS failed."""
    REFUSED_ADDRESS = "refused_address"
    """The receiver's host resolved to an address the SSRF guard refuses, a private, loopback, link-local or metadata one."""
    SECRET_UNAVAILABLE = "secret_unavailable"
    """The delivering process holds no usable signing secret, so nothing was sent."""


class CallerWebhookOutcome(BaseModel):
    """How the delivery of a run's event to one caller webhook ended.

    Attributes:
        delivery_id: The delivery's id, its calls' ``webhook-id``.
        server_address: The receiver's host, never its whole URL, which may carry a credential.
        attempt_count: How many calls were sent, none when the event could not be signed.
        failure: Why the delivery failed, or ``None`` when the receiver acknowledged it.
        receiver_status: The status the receiver answered the last attempt with, when it answered outside ``2xx``.
    """

    model_config = ConfigDict(frozen=True)

    delivery_id: str
    server_address: str | None
    attempt_count: int = Field(ge=0)
    failure: CallerWebhookFailure | None = Field(default=None, strict=False)
    receiver_status: int | None = None

    @property
    def is_delivered(self) -> bool:
        """Whether the receiver acknowledged the event with a ``2xx``."""
        return self.failure is None


def is_caller_webhook_secret_set() -> bool:
    """Whether :data:`CALLER_WEBHOOK_SECRET_ENV` holds anything but blanks, whether or not it is a valid secret."""
    configured = get_optional_env(CALLER_WEBHOOK_SECRET_ENV)
    return configured is not None and bool(configured.strip())


def caller_webhook_secret_keys() -> list[bytes]:
    """The keys of the secrets a caller's webhooks are signed with, read from :data:`CALLER_WEBHOOK_SECRET_ENV`.

    Returns:
        The key of each secret the variable holds, in its order, the current one first.

    Raises:
        CallerWebhookSecretError: The variable is unset or blank, or holds a value that is not a ``whsec_`` secret.
            The message never quotes the variable's value.
    """
    configured = get_optional_env(CALLER_WEBHOOK_SECRET_ENV)
    if configured is None or not configured.strip():
        msg = f"The environment variable '{CALLER_WEBHOOK_SECRET_ENV}' holds no secret to sign caller webhooks with."
        raise CallerWebhookSecretError(msg, setting=CALLER_WEBHOOK_SECRET_ENV)
    secret_keys: list[bytes] = []
    for position, secret in enumerate(configured.split(), start=1):
        try:
            secret_keys.append(decode_webhook_secret(secret=secret))
        except ValueError as exc:
            msg = f"The secret number {position} of the environment variable '{CALLER_WEBHOOK_SECRET_ENV}' is not a webhook signing secret: {exc}"
            raise CallerWebhookSecretError(msg, setting=CALLER_WEBHOOK_SECRET_ENV) from exc
    return secret_keys


def event_timestamp(*, moment: datetime) -> str:
    """A moment as the event writes it: an RFC 3339 date-time in UTC, to the millisecond, ending in ``Z``.

    Args:
        moment: A moment aware of its time zone.

    Returns:
        The moment's text, such as ``2026-10-22T11:59:58.250Z``.
    """
    return moment.astimezone(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def run_finished_data(*, pipeline_run_id: str, status: DeliveryStatus, problem: PipelexProblem | None) -> dict[str, Any]:
    """The event's ``data``: the run as its caller's status read serves it, the protocol's ``RunRead``.

    Args:
        pipeline_run_id: The run's id.
        status: How the run ended.
        problem: A failed run's problem, in any view; the event carries its caller view. A failed run with none, which
            no runner of this repository hands a delivery, reads as ``runtime.unexpected``, since an ended run's event
            carries the problem of every failed run.

    Returns:
        The members of the read, none of them ``null``.
    """
    match status:
        case DeliveryStatus.COMPLETED:
            return {"pipeline_run_id": pipeline_run_id, "status": EndedRunStatus.COMPLETED}
        case DeliveryStatus.FAILED:
            run_problem = problem or make_problem(code=CoreCode.RUNTIME_UNEXPECTED, view=ProblemView.OPERATOR, pipeline_run_id=pipeline_run_id)
            return {
                "pipeline_run_id": pipeline_run_id,
                "status": EndedRunStatus.FAILED,
                "error": caller_view_of(problem=run_problem).to_wire(),
            }


def run_finished_body(*, finished_at: str, attempt: int, data: Mapping[str, Any]) -> bytes:
    """The bytes of one call's body: the ``run.finished`` event as compact JSON, characters outside ASCII as UTF-8.

    Args:
        finished_at: When the run ended, as :func:`event_timestamp` writes it.
        attempt: Which attempt of the delivery the call is, from 1.
        data: The run as its caller's status read serves it (:func:`run_finished_data`).

    Returns:
        The body, which is exactly what the call's signature covers.
    """
    event = {"type": RUN_FINISHED_EVENT_TYPE, "timestamp": finished_at, "attempt": attempt, "data": data}
    return json.dumps(event, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


async def deliver_caller_webhooks(
    *,
    targets: Sequence[CallerWebhookTarget],
    pipeline_run_id: str,
    status: DeliveryStatus,
    problem: PipelexProblem | None,
    finished_at: datetime,
    extras: Mapping[str, str] | None = None,
) -> list[CallerWebhookOutcome]:
    """Send each caller webhook the run's ``run.finished`` event, each on its own, and return how each delivery ended.

    The event's ``data`` is built once, so every attempt of every delivery says the same of the run. A process holding
    no usable secret sends nothing, logs the fault once as an error, which its operator fixes, and returns every
    delivery as failed. Nothing here raises for a receiver's failure or a refused destination.

    Args:
        targets: The caller's webhooks.
        pipeline_run_id: The run's id.
        status: How the run ended.
        problem: A failed run's problem, in any view; the event carries its caller view.
        finished_at: When the run ended.
        extras: The run's opaque extras, which the security event of a refused destination carries.

    Returns:
        The outcome of each delivery, in the order of ``targets``.
    """
    if not targets:
        return []
    try:
        secret_keys = caller_webhook_secret_keys()
    except CallerWebhookSecretError as secret_error:
        log.error(
            "Caller webhooks could not be signed and were not sent",
            fields={
                "env_var": secret_error.setting,
                "delivery_count": len(targets),
                "user_action": "Set the signing secret of caller webhooks on every process that runs deliveries",
            },
        )
        return [
            CallerWebhookOutcome(
                delivery_id=target.delivery_id,
                server_address=urlsplit(target.url).hostname,
                attempt_count=0,
                failure=CallerWebhookFailure.SECRET_UNAVAILABLE,
            )
            for target in targets
        ]
    data = run_finished_data(pipeline_run_id=pipeline_run_id, status=status, problem=problem)
    finished_at_text = event_timestamp(moment=finished_at)
    # Redirects are not followed: a redirect is a failed attempt, so a receiver can never send the signed event on.
    async with httpx.AsyncClient(transport=SsrfGuardedTransport(), follow_redirects=False, timeout=ATTEMPT_BUDGET_SECONDS) as client:
        outcomes = await asyncio.gather(
            *(
                _deliver_one(client=client, target=target, data=data, finished_at=finished_at_text, secret_keys=secret_keys, extras=extras)
                for target in targets
            )
        )
    return list(outcomes)


async def _deliver_one(
    *,
    client: httpx.AsyncClient,
    target: CallerWebhookTarget,
    data: Mapping[str, Any],
    finished_at: str,
    secret_keys: Sequence[bytes],
    extras: Mapping[str, str] | None,
) -> CallerWebhookOutcome:
    """Deliver the event to one caller webhook, with the short retry, and return how the delivery ended."""
    server_address = urlsplit(target.url).hostname
    attempt_count = 0
    failure: CallerWebhookFailure | None = None
    receiver_status: int | None = None
    for wait_seconds in (0.0, *RETRY_WAITS_SECONDS):
        if wait_seconds:
            await sleep(wait_seconds)
        attempt_count += 1
        receiver_status = None
        body = run_finished_body(finished_at=finished_at, attempt=attempt_count, data=data)
        webhook_timestamp = str(int(time()))
        headers = {
            "content-type": "application/json",
            "webhook-id": target.delivery_id,
            "webhook-timestamp": webhook_timestamp,
            "webhook-signature": sign_webhook(
                secret_keys=secret_keys,
                webhook_id=target.delivery_id,
                webhook_timestamp=webhook_timestamp,
                body=body,
            ),
        }
        try:
            async with asyncio.timeout(ATTEMPT_BUDGET_SECONDS):
                response = await client.post(target.url, content=body, headers=headers)
        except SsrfBlockedError as refusal:
            # A security refusal, logged as its event with the run's identifiers from the delivery's log context, and
            # never tried again: the guard refuses the address the name resolves to, not a passing fault.
            emit_security_event(error=refusal, extras=extras)
            failure = CallerWebhookFailure.REFUSED_ADDRESS
            break
        except (TimeoutError, httpx.TimeoutException):
            failure = CallerWebhookFailure.TIMEOUT
        except (httpx.RequestError, httpx.InvalidURL):
            # By the failure's kind, never its text, which can quote the caller's webhook URL.
            failure = CallerWebhookFailure.UNREACHABLE
        else:
            if response.is_success:
                log.info(
                    "A caller webhook was delivered",
                    fields={"delivery_id": target.delivery_id, "server.address": server_address, "attempt_count": attempt_count},
                )
                return CallerWebhookOutcome(delivery_id=target.delivery_id, server_address=server_address, attempt_count=attempt_count)
            failure = CallerWebhookFailure.HTTP_STATUS
            receiver_status = response.status_code
        log.debug(
            "A caller webhook attempt failed",
            fields=_failure_fields(
                delivery_id=target.delivery_id,
                server_address=server_address,
                attempt_count=attempt_count,
                failure=failure,
                receiver_status=receiver_status,
            ),
        )
    assert failure is not None
    # A warning, not an error: the receiver is the caller's, and the run's outcome stands whatever it answered.
    log.warning(
        "A caller webhook could not be delivered",
        fields=_failure_fields(
            delivery_id=target.delivery_id,
            server_address=server_address,
            attempt_count=attempt_count,
            failure=failure,
            receiver_status=receiver_status,
        ),
    )
    return CallerWebhookOutcome(
        delivery_id=target.delivery_id,
        server_address=server_address,
        attempt_count=attempt_count,
        failure=failure,
        receiver_status=receiver_status,
    )


def _failure_fields(
    *,
    delivery_id: str,
    server_address: str | None,
    attempt_count: int,
    failure: CallerWebhookFailure,
    receiver_status: int | None,
) -> dict[str, Any]:
    """The fields of a line about a failed attempt or delivery, the receiver's status only when it answered."""
    fields: dict[str, Any] = {
        "delivery_id": delivery_id,
        "server.address": server_address,
        "attempt_count": attempt_count,
        "delivery_failure": failure,
    }
    if receiver_status is not None:
        fields["http.response.status_code"] = receiver_status
    return fields
