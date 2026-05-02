from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

import httpx
from kajson.exceptions import KajsonException
from pydantic import ValidationError

from pipelex import log
from pipelex.config import get_config
from pipelex.core.concepts.concept import Concept
from pipelex.core.memory.working_memory import MAIN_STUFF_NAME
from pipelex.core.stuffs.stuff import Stuff
from pipelex.core.stuffs.stuff_content import StuffContent
from pipelex.core.stuffs.stuff_viewer import render_stuff_viewer
from pipelex.graph.graph_factory import generate_graph_outputs
from pipelex.hub import get_class_registry, get_storage_provider
from pipelex.pipe_run.exceptions import PipeJobError, StorageDeliveryError, WebhookDeliveryError
from pipelex.temporal.tprl_pipe.hydration import hydrate_content
from pipelex.tools.misc.json_utils import clean_json_dumps

if TYPE_CHECKING:
    from pipelex.core.pipes.pipe_output import PipeOutput
    from pipelex.pipe_run.delivery_assignment import DeliveryAssignment, DeliveryStatus, StorageTarget, WebhookTarget


class DeliveryExecutor:
    """Handles the full delivery lifecycle: generate result files, store them, notify webhooks."""

    async def execute(
        self,
        pipe_output: PipeOutput | None,
        user_id: str,
        pipeline_run_id: str,
        delivery_assignment: DeliveryAssignment,
        status: DeliveryStatus,
    ) -> None:
        """Execute a full delivery: generate result files, store them, then notify webhooks."""
        # Step 1: Persist the result files to storage (only on success with output)
        result_url: str | None = None
        if delivery_assignment.storage is not None and pipe_output is not None:
            result_url = await self._store_results(pipe_output, user_id, pipeline_run_id, delivery_assignment.storage)

        # Step 2: Notify webhooks with status + result_url (always, even on failure)
        for webhook in delivery_assignment.webhooks:
            await self._notify_webhook(pipeline_run_id, status, result_url, webhook)

    # ---- Result file generation ----

    async def generate_result_files(self, pipe_output: PipeOutput) -> dict[str, bytes]:
        """Generate the full set of result files from a PipeOutput.

        Produces: working_memory.json, main_stuff (json/md/html/viewer),
        graph outputs (mermaidflow, reactflow, graphspec).

        Supports two `pipe_output` shapes:
        - Typed: `working_memory` populated (in-process / same-worker path).
        - Raw: `working_memory_raw` populated (cross-process Temporal path,
          where the activity worker may not have the dynamic concept classes
          loaded). The activity tries to locally hydrate using only globally
          registered classes; on failure it falls back to a generic dict
          render so built-in content types still get typed rendering and
          dynamic concepts produce a readable JSON dump.
        """
        files: dict[str, bytes] = {}

        if pipe_output.working_memory_raw is not None:
            files["working_memory.json"] = clean_json_dumps(pipe_output.working_memory_raw, indent=2).encode("utf-8")
            raw_main_stuff = self._get_raw_main_stuff_dict(pipe_output.working_memory_raw)
            main_stuff = self.try_local_hydrate_stuff(raw_main_stuff) if raw_main_stuff is not None else None
            if main_stuff is not None:
                await self._generate_main_stuff_files(main_stuff, files)
            elif raw_main_stuff is not None:
                self._generate_main_stuff_files_from_raw(raw_main_stuff, files)
        else:
            files["working_memory.json"] = clean_json_dumps(pipe_output.working_memory.smart_dump(), indent=2).encode("utf-8")
            main_stuff = pipe_output.working_memory.get_optional_main_stuff()
            if main_stuff is not None:
                await self._generate_main_stuff_files(main_stuff, files)

        graph_spec = pipe_output.graph_spec
        if graph_spec:
            await self._generate_graph_files(graph_spec, files)

        return files

    @staticmethod
    def _get_raw_main_stuff_dict(working_memory_raw: dict[str, Any]) -> dict[str, Any] | None:
        """Extract the main stuff dict from a raw working_memory, following aliases."""
        root: dict[str, Any] = working_memory_raw.get("root", {})
        aliases: dict[str, str] = working_memory_raw.get("aliases", {})
        target_name = aliases.get(MAIN_STUFF_NAME, MAIN_STUFF_NAME)
        candidate = root.get(target_name)
        if isinstance(candidate, dict):
            return cast("dict[str, Any]", candidate)
        return None

    @staticmethod
    def try_local_hydrate_stuff(stuff_raw: dict[str, Any]) -> Stuff | None:
        """Attempt to hydrate a single Stuff dict using only globally-registered classes.

        Returns None when the structure class isn't available locally (typically
        a dynamic concept class missing from the activity worker's registry) —
        callers then fall back to a generic raw-dict render. A warning is
        emitted on the fallback path so silent regressions on built-in
        hydration surface in logs.
        """
        try:
            concept = Concept.model_validate(stuff_raw["concept"])
            registry = get_class_registry()
            item_class = registry.get_class(name=concept.structure_class_name)
            if item_class is None or not issubclass(item_class, StuffContent):
                log.warning(
                    f"Local hydration failed for delivery main stuff, falling back to raw render: "
                    f"class '{concept.structure_class_name}' not registered locally"
                )
                return None
            content = hydrate_content(concept=concept, raw_content=stuff_raw["content"])
            return Stuff(
                stuff_code=stuff_raw["stuff_code"],
                stuff_name=stuff_raw.get("stuff_name"),
                concept=concept,
                content=content,
            )
        except (PipeJobError, ValidationError, KajsonException, KeyError) as exc:
            log.warning(f"Local hydration failed for delivery main stuff, falling back to raw render: {exc}")
            return None

    @staticmethod
    def _generate_main_stuff_files_from_raw(raw_main_stuff: dict[str, Any], files: dict[str, bytes]) -> None:
        """Generic fallback rendering of a main stuff that we couldn't locally hydrate.

        Produces JSON-in-markdown and `<pre>`-in-HTML so the user still gets
        readable output for dynamic concepts the activity worker doesn't know about.
        """
        content_dict = raw_main_stuff.get("content", raw_main_stuff)
        json_text = clean_json_dumps(content_dict, indent=2)
        files["main_stuff.json"] = json_text.encode("utf-8")
        files["main_stuff.md"] = f"```json\n{json_text}\n```\n".encode()
        files["main_stuff.html"] = f"<pre>{json_text}</pre>".encode()

    async def _generate_main_stuff_files(self, main_stuff: Stuff, files: dict[str, bytes]) -> None:
        try:
            files["main_stuff.json"] = (await main_stuff.content.rendered_json_async()).encode("utf-8")
        except Exception:
            # TODO: wip - do not catch all exceptions
            log.warning("Failed to render main_stuff.json")

        try:
            files["main_stuff.md"] = (await main_stuff.content.rendered_markdown_async()).encode("utf-8")
        except Exception:
            # TODO: wip - do not catch all exceptions
            log.warning("Failed to render main_stuff.md")

        try:
            files["main_stuff.html"] = (await main_stuff.content.rendered_html_async()).encode("utf-8")
        except Exception:
            # TODO: wip - do not catch all exceptions
            log.warning("Failed to render main_stuff.html")

        try:
            files["main_stuff_viewer.html"] = (await render_stuff_viewer(main_stuff)).encode("utf-8")
        except Exception:
            # TODO: wip - do not catch all exceptions
            log.warning("Failed to render main_stuff_viewer.html")

    async def _generate_graph_files(self, graph_spec: Any, files: dict[str, bytes]) -> None:
        try:
            graph_config = get_config().pipelex.pipeline_execution_config.graph_config
            graph_outputs = await generate_graph_outputs(
                graph_spec=graph_spec,
                graph_config=graph_config,
            )

            if graph_outputs.graphspec_json is not None:
                files["graphspec.json"] = graph_outputs.graphspec_json.encode("utf-8")
            if graph_outputs.mermaidflow_mmd is not None:
                files["mermaidflow.mmd"] = graph_outputs.mermaidflow_mmd.encode("utf-8")
            if graph_outputs.mermaidflow_html is not None:
                files["mermaidflow.html"] = graph_outputs.mermaidflow_html.encode("utf-8")
            if graph_outputs.reactflow_html is not None:
                files["reactflow.html"] = graph_outputs.reactflow_html.encode("utf-8")
        except Exception:
            # TODO: wip - do not catch all exceptions
            log.warning("Failed to generate graph outputs")

    # ---- Storage ----

    async def _store_results(
        self,
        pipe_output: PipeOutput,
        user_id: str,
        pipeline_run_id: str,
        storage: StorageTarget,
    ) -> str:
        """Generate all result files and store them. Returns the base result URL."""
        try:
            storage_provider = get_storage_provider()
            prefix: str = storage.key_prefix or ""
            base_key: str = f"{user_id}/{prefix}{pipeline_run_id}"

            result_files = await self.generate_result_files(pipe_output)

            for filename, data in result_files.items():
                key: str = f"{base_key}/{filename}"
                # TODO: wip - set the content type when the files are created
                content_type: str = _content_type_for(filename)
                await storage_provider.store(data=data, key=key, content_type=content_type)
                log.debug(f"Stored: {key}")

            # TODO: include the full S3 URI (s3://bucket/key/) so result_url is
            # self-contained and doesn't depend on knowing the bucket externally.
            result_url: str = f"{base_key}/"
            log.info(f"Storage delivery completed: pipeline_run_id={pipeline_run_id}, files={len(result_files)}")
            return result_url
        except Exception as exc:
            # TODO: wip - do not catch all exceptions
            msg = f"Storage delivery failed for pipeline_run_id={pipeline_run_id}"
            raise StorageDeliveryError(msg) from exc

    # ---- Webhooks ----

    async def _notify_webhook(
        self,
        pipeline_run_id: str,
        status: DeliveryStatus,
        result_url: str | None,
        webhook: WebhookTarget,
    ) -> None:
        """POST status + result_url to a webhook URL."""
        try:
            payload: dict[str, Any] = dict(webhook.payload)
            payload["pipeline_run_id"] = pipeline_run_id
            payload["status"] = status
            if result_url is not None:
                payload["result_url"] = result_url

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
            # TODO: wip - do not catch all exceptions
            msg = f"Webhook delivery failed for pipeline_run_id={pipeline_run_id}: {exc}"
            raise WebhookDeliveryError(msg) from exc


def _content_type_for(filename: str) -> str:
    """Determine content type from filename extension."""
    if filename.endswith(".json"):
        return "application/json"
    if filename.endswith(".html"):
        return "text/html"
    if filename.endswith(".md"):
        return "text/markdown"
    if filename.endswith(".mmd"):
        return "text/plain"
    return "application/octet-stream"
