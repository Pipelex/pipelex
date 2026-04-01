from __future__ import annotations

from typing import TYPE_CHECKING, Any

import httpx

from pipelex import log
from pipelex.hub import get_storage_provider
from pipelex.pipe_run.exceptions import StorageDeliveryError, WebhookDeliveryError

if TYPE_CHECKING:
    from pipelex.core.pipes.pipe_output import PipeOutput
    from pipelex.pipe_run.delivery_assignment import DeliveryAssignment, StorageTarget, WebhookTarget


async def execute_delivery(
    pipe_output: PipeOutput,
    pipeline_run_id: str,
    delivery_assignment: DeliveryAssignment,
) -> None:
    """Execute a full delivery: store output first, then notify webhooks."""
    # Step 1: Persist the output to storage (if configured)
    if delivery_assignment.storage is not None:
        await _execute_storage_delivery(pipe_output, pipeline_run_id, delivery_assignment.storage)

    # Step 2: Notify webhooks (if configured)
    for webhook in delivery_assignment.webhooks:
        await _execute_webhook_delivery(pipe_output, pipeline_run_id, webhook)


async def _execute_storage_delivery(
    pipe_output: PipeOutput,
    pipeline_run_id: str,
    storage: StorageTarget,
) -> None:
    """Store the pipe output via the configured storage provider."""
    try:
        storage_provider = get_storage_provider()
        data: bytes = pipe_output.model_dump_json(serialize_as_any=True).encode("utf-8")
        prefix: str = storage.key_prefix or ""
        key: str = f"{prefix}{pipeline_run_id}/output.json"
        await storage_provider.store(data=data, key=key, content_type="application/json")
        log.info(f"Storage delivery completed: pipeline_run_id={pipeline_run_id}, key={key}")
    except Exception as exc:
        msg = f"Storage delivery failed for pipeline_run_id={pipeline_run_id}"
        raise StorageDeliveryError(msg) from exc


async def _execute_webhook_delivery(
    pipe_output: PipeOutput,
    pipeline_run_id: str,
    webhook: WebhookTarget,
) -> None:
    """POST the pipe output to a webhook URL."""
    try:
        payload: dict[str, Any] = {
            "pipeline_run_id": pipeline_run_id,
            "status": "COMPLETED",
            "pipe_output": pipe_output.model_dump(mode="json", serialize_as_any=True),
        }
        async with httpx.AsyncClient() as client:
            response = await client.post(
                webhook.url,
                json=payload,
                headers=webhook.headers,
                timeout=30.0,
            )
            response.raise_for_status()
        log.info(f"Webhook delivery completed: pipeline_run_id={pipeline_run_id}, url={webhook.url}")
    except httpx.HTTPStatusError as exc:
        msg = f"Webhook delivery failed for pipeline_run_id={pipeline_run_id}: HTTP {exc.response.status_code}"
        raise WebhookDeliveryError(msg) from exc
    except Exception as exc:
        msg = f"Webhook delivery failed for pipeline_run_id={pipeline_run_id}: {exc}"
        raise WebhookDeliveryError(msg) from exc
