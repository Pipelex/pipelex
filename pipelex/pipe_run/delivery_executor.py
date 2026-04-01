from __future__ import annotations

from typing import TYPE_CHECKING, Any

import httpx

from pipelex import log
from pipelex.hub import get_storage_provider
from pipelex.pipe_run.exceptions import StorageDeliveryError, WebhookDeliveryError

if TYPE_CHECKING:
    from pipelex.core.pipes.pipe_output import PipeOutput
    from pipelex.pipe_run.delivery_assignment import DeliveryAssignment, DeliveryStatus, StorageTarget, WebhookTarget


async def execute_delivery(
    pipe_output: PipeOutput | None,
    pipeline_run_id: str,
    delivery_assignment: DeliveryAssignment,
    status: DeliveryStatus,
) -> None:
    """Execute a full delivery: store output first (if available), then notify webhooks."""
    # Step 1: Persist the output to storage (only on success with output)
    result_url: str | None = None
    if delivery_assignment.storage is not None and pipe_output is not None:
        result_url = await _execute_storage_delivery(pipe_output, pipeline_run_id, delivery_assignment.storage)

    # Step 2: Notify webhooks with status + result_url (always, even on failure)
    for webhook in delivery_assignment.webhooks:
        await _execute_webhook_delivery(pipeline_run_id, status, result_url, webhook)


async def _execute_storage_delivery(
    pipe_output: PipeOutput,
    pipeline_run_id: str,
    storage: StorageTarget,
) -> str:
    """Store the pipe output and return the result URL."""
    try:
        storage_provider = get_storage_provider()
        data: bytes = pipe_output.model_dump_json(serialize_as_any=True).encode("utf-8")
        prefix: str = storage.key_prefix or ""
        key: str = f"{prefix}{pipeline_run_id}/output.json"
        result_url: str = await storage_provider.store(data=data, key=key, content_type="application/json")
        log.info(f"Storage delivery completed: pipeline_run_id={pipeline_run_id}, result_url={result_url}")
        return result_url
    except Exception as exc:
        msg = f"Storage delivery failed for pipeline_run_id={pipeline_run_id}"
        raise StorageDeliveryError(msg) from exc


async def _execute_webhook_delivery(
    pipeline_run_id: str,
    status: str,
    result_url: str | None,
    webhook: WebhookTarget,
) -> None:
    """POST status + result_url to a webhook URL."""
    try:
        payload: dict[str, Any] = {
            "pipeline_run_id": pipeline_run_id,
            "status": status,
        }
        if result_url is not None:
            payload["result_url"] = result_url
        payload.update(webhook.payload)

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
