from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, field_validator

from pipelex.tools.typing.pydantic_utils import empty_list_factory_of
from pipelex.types import StrEnum


class DeliveryStatus(StrEnum):
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


# Keys that Pipelex assigns per delivery onto the outgoing webhook body
# (see ``DeliveryExecutor._notify_webhook``). A caller's static ``payload``
# must not declare any of them — otherwise the value would shift silently
# with delivery status. Enforced at construction by ``_reject_reserved_keys``.
_RESERVED_WEBHOOK_PAYLOAD_KEYS: frozenset[str] = frozenset({"run_id", "state", "pipeline_run_id", "status", "result_url", "error"})


class WebhookTarget(BaseModel):
    """A webhook endpoint to notify on delivery."""

    url: str
    headers: dict[str, str] = Field(default_factory=dict)
    payload: dict[str, Any] = Field(default_factory=dict)

    @field_validator("payload", mode="after")
    @classmethod
    def _reject_reserved_keys(cls, value: dict[str, Any]) -> dict[str, Any]:
        """Reject caller payload keys that Pipelex assigns per delivery.

        ``DeliveryExecutor._notify_webhook`` writes ``run_id`` / ``state``
        (protocol spellings) plus the transitional ``pipeline_run_id`` /
        ``status`` aliases, ``result_url`` and ``error`` onto the outgoing body. A static
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

    Execution order: storage first (persist output), then webhooks (notify consumers).
    The result_url from storage is automatically injected into webhook payloads.
    """

    storage: StorageTarget | None = None
    webhooks: list[WebhookTarget] = Field(default_factory=empty_list_factory_of(WebhookTarget))

    @property
    def has_delivery_target(self) -> bool:
        """True when at least one real delivery target (storage or a webhook) is configured.

        A ``DeliveryAssignment`` with no storage and no webhooks is a no-op: it would
        persist nothing and notify no one, so a fire-and-forget completion would be
        silently dropped.
        """
        return self.storage is not None or bool(self.webhooks)
