from __future__ import annotations

import uuid
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field, field_validator

from pipelex.errors.problem import ProblemView
from pipelex.tools.typing.pydantic_utils import empty_list_factory_of


class DeliveryStatus(StrEnum):
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


# Keys that Pipelex assigns per delivery onto the outgoing webhook body
# (see ``DeliveryExecutor._notify_webhook``). A caller's static ``payload``
# must not declare any of them — otherwise the value would shift silently
# with delivery status. Enforced at construction by ``_reject_reserved_keys``.
_RESERVED_WEBHOOK_PAYLOAD_KEYS: frozenset[str] = frozenset({"state", "pipeline_run_id", "status", "result_url", "error"})


class WebhookTarget(BaseModel):
    """A webhook of the host's own, such as a deployment's completion receiver, notified with the completion notice.

    The notice carries the run's id, its delivery state, the stored results' prefix and a failed run's problem, with
    the headers the host gives, such as its own signature. A failure to deliver it raises, so a durable orchestrator
    retries the delivery step. A webhook a run's caller registered is a :class:`CallerWebhookTarget` instead.

    ``problem_view`` is the view the failed run's problem reaches the webhook in, the view of whoever the host built
    the target for: an operator's receiver reads the operator's view, and a target built with none receives the
    caller's view, which carries no diagnostics.
    """

    url: str
    headers: dict[str, str] = Field(default_factory=dict)
    payload: dict[str, Any] = Field(default_factory=dict)
    problem_view: ProblemView = Field(default=ProblemView.CALLER, strict=False)

    @field_validator("payload", mode="after")
    @classmethod
    def _reject_reserved_keys(cls, value: dict[str, Any]) -> dict[str, Any]:
        """Reject caller payload keys that Pipelex assigns per delivery.

        ``DeliveryExecutor._notify_webhook`` writes ``pipeline_run_id`` /
        ``state`` (protocol spellings) plus the transitional ``status`` alias,
        ``result_url`` and ``error`` onto the outgoing body. A static
        payload that declares any of them would have its meaning shift with
        delivery status — fail loudly at construction instead of silently at
        delivery time.
        """
        collisions = set(value) & _RESERVED_WEBHOOK_PAYLOAD_KEYS
        if collisions:
            msg = (
                f"WebhookTarget.payload contains reserved keys: {sorted(collisions)}. "
                "Pipelex owns these keys (assigned per delivery); choose different names."
            )
            raise ValueError(msg)
        return value


DELIVERY_ID_PREFIX = "whd_"
"""The prefix of a caller webhook's delivery id, the value its calls carry as their ``webhook-id`` header."""

DELIVERY_ID_PATTERN = r"^whd_[A-Za-z0-9_]{1,60}$"
"""A delivery id: ``whd_`` then ASCII letters, digits and underscores, at most 64 characters in all."""


def new_delivery_id() -> str:
    """A delivery id of its own: ``whd_`` and a random UUID's 32 hexadecimal digits."""
    return f"{DELIVERY_ID_PREFIX}{uuid.uuid4().hex}"


class CallerWebhookTarget(BaseModel):
    """A URL a run's caller registered, which receives the signed ``run.finished`` event when the run ends.

    Unlike a :class:`WebhookTarget`, the deployment's own hop, a caller's webhook carries no header, payload or view
    of its host's choosing: the delivery sends the event the caller-webhook contract specifies, the run as its caller's
    status read serves it, with a failed run's problem in the caller's view, signed in the Standard Webhooks format
    under the secret the delivering process holds. ``delivery_id`` is the id every attempt of the delivery carries as
    its ``webhook-id``; it is fixed when the target is built, so a delivery repeated from the same assignment, by a
    durable orchestrator retrying the delivery step, keeps it.
    """

    url: str
    delivery_id: str = Field(default_factory=new_delivery_id, pattern=DELIVERY_ID_PATTERN)


class StorageTarget(BaseModel):
    """Storage configuration for persisting pipe output."""

    key_prefix: str | None = None

    @field_validator("key_prefix", mode="after")
    @classmethod
    def normalize_key_prefix(cls, value: str | None) -> str | None:
        if value is not None and value != "" and not value.endswith("/"):
            return f"{value}/"
        return value


class DeliveryAssignment(BaseModel):
    """Configures the full delivery behavior for a pipe run.

    Execution order: storage first (persist output), then the deployment's own webhooks (``webhooks``), then the
    caller's (``caller_webhooks``), which are delivered even when one of the deployment's failed.
    The result_url from storage is automatically injected into the deployment's webhook payloads; a caller's event
    carries no result, which its receiver reads from the run.
    """

    storage: StorageTarget | None = None
    webhooks: list[WebhookTarget] = Field(default_factory=empty_list_factory_of(WebhookTarget))
    caller_webhooks: list[CallerWebhookTarget] = Field(default_factory=empty_list_factory_of(CallerWebhookTarget))

    @property
    def has_delivery_target(self) -> bool:
        """True when at least one real delivery target (storage or a webhook) is configured.

        A ``DeliveryAssignment`` with no storage and no webhooks is a no-op: it would
        persist nothing and notify no one, so a fire-and-forget completion would be
        silently dropped.
        """
        return self.storage is not None or bool(self.webhooks) or bool(self.caller_webhooks)

    @property
    def needs_run_problem(self) -> bool:
        """Whether a failed run's problem has a webhook to reach, the deployment's or a caller's."""
        return bool(self.webhooks) or bool(self.caller_webhooks)
