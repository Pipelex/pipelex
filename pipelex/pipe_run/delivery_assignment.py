from __future__ import annotations

from pydantic import BaseModel, Field

from pipelex.tools.typing.pydantic_utils import empty_list_factory_of


class WebhookTarget(BaseModel):
    """A webhook endpoint to notify on delivery."""

    url: str
    headers: dict[str, str] = Field(default_factory=dict)


class StorageTarget(BaseModel):
    """Storage configuration for persisting pipe output."""

    key_prefix: str | None = None


class DeliveryAssignment(BaseModel):
    """Configures the full delivery behavior for a pipe run.

    A delivery assignment can include both storage and webhook targets.
    Storage runs first (persist the output), then webhooks (notify consumers).
    """

    storage: StorageTarget | None = None
    webhooks: list[WebhookTarget] = Field(default_factory=empty_list_factory_of(WebhookTarget))
