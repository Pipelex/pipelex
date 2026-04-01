from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from pipelex.tools.typing.pydantic_utils import empty_list_factory_of
from pipelex.types import StrEnum


class DeliveryStatus(StrEnum):
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class WebhookTarget(BaseModel):
    """A webhook endpoint to notify on delivery."""

    url: str
    headers: dict[str, str] = Field(default_factory=dict)
    payload: dict[str, Any] = Field(default_factory=dict)


class StorageTarget(BaseModel):
    """Storage configuration for persisting pipe output."""

    key_prefix: str | None = None


class DeliveryAssignment(BaseModel):
    """Configures the full delivery behavior for a pipe run.

    Execution order: storage first (persist output), then webhooks (notify consumers).
    The result_url from storage is automatically injected into webhook payloads.
    """

    storage: StorageTarget | None = None
    webhooks: list[WebhookTarget] = Field(default_factory=empty_list_factory_of(WebhookTarget))
