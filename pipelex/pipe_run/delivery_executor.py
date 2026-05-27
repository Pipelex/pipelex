from __future__ import annotations

import html
from typing import TYPE_CHECKING, Any, Awaitable, NamedTuple, cast

import httpx
from kajson.exceptions import KajsonException
from pydantic import ValidationError

from pipelex import log
from pipelex.base_exceptions import DisclosureMode, ErrorReport
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


class ResultFile(NamedTuple):
    """A generated result file with its bytes and MIME type, ready to store."""

    data: bytes
    content_type: str


class DeliveryExecutor:
    """Handles the full delivery lifecycle: generate result files, store them, notify webhooks."""

    async def execute(
        self,
        pipe_output: PipeOutput | None,
        user_id: str,
        pipeline_run_id: str,
        delivery_assignment: DeliveryAssignment,
        status: DeliveryStatus,
        error_report: ErrorReport | None = None,
        request_id: str | None = None,
    ) -> None:
        """Execute a full delivery: generate result files, store them, then notify webhooks.

        ``request_id`` is the originating API request id (when set). It is threaded
        into the storage / webhook completion log lines so the delivery phase can be
        correlated with the workflow logs and the inbound request.
        """
        # Step 1: Persist the result files to storage (only on success with output)
        result_url: str | None = None
        if delivery_assignment.storage is not None and pipe_output is not None:
            result_url = await self._store_results(pipe_output, user_id, pipeline_run_id, delivery_assignment.storage, request_id=request_id)

        # Step 2: Notify webhooks with status + result_url (always, even on failure)
        for webhook in delivery_assignment.webhooks:
            await self._notify_webhook(pipeline_run_id, status, result_url, webhook, error_report, request_id=request_id)

    # ---- Result file generation ----

    async def generate_result_files(self, pipe_output: PipeOutput) -> dict[str, ResultFile]:
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
        files: dict[str, ResultFile] = {}

        if pipe_output.working_memory_raw is not None:
            files["working_memory.json"] = ResultFile(
                data=clean_json_dumps(pipe_output.working_memory_raw, indent=2).encode("utf-8"),
                content_type="application/json",
            )
            raw_main_stuff = self._get_raw_main_stuff_dict(pipe_output.working_memory_raw)
            main_stuff = self.try_local_hydrate_stuff(raw_main_stuff) if raw_main_stuff is not None else None
            if main_stuff is not None:
                await self._generate_main_stuff_files(main_stuff, files)
            elif raw_main_stuff is not None:
                self._generate_main_stuff_files_from_raw(raw_main_stuff, files)
        else:
            files["working_memory.json"] = ResultFile(
                data=clean_json_dumps(pipe_output.working_memory.smart_dump(), indent=2).encode("utf-8"),
                content_type="application/json",
            )
            main_stuff = pipe_output.working_memory.get_optional_main_stuff()
            if main_stuff is not None:
                await self._generate_main_stuff_files(main_stuff, files)

        graph_spec = pipe_output.graph_spec
        if graph_spec:
            await self._generate_graph_files(graph_spec, files)

        return files

    @classmethod
    def _get_raw_main_stuff_dict(cls, working_memory_raw: dict[str, Any]) -> dict[str, Any] | None:
        """Extract the main stuff dict from a raw working_memory, following aliases."""
        root: dict[str, Any] = working_memory_raw.get("root", {})
        aliases: dict[str, str] = working_memory_raw.get("aliases", {})
        target_name = aliases.get(MAIN_STUFF_NAME, MAIN_STUFF_NAME)
        candidate = root.get(target_name)
        if isinstance(candidate, dict):
            return cast("dict[str, Any]", candidate)
        return None

    @classmethod
    def try_local_hydrate_stuff(cls, stuff_raw: dict[str, Any]) -> Stuff | None:
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
        except (PipeJobError, ValidationError, KajsonException, KeyError, TypeError) as exc:
            log.warning(f"Local hydration failed for delivery main stuff, falling back to raw render: {exc}")
            return None

    @classmethod
    def _generate_main_stuff_files_from_raw(cls, raw_main_stuff: dict[str, Any], files: dict[str, ResultFile]) -> None:
        """Generic fallback rendering of a main stuff that we couldn't locally hydrate.

        Produces JSON-in-markdown and `<pre>`-in-HTML so the user still gets
        readable output for dynamic concepts the activity worker doesn't know about.
        """
        content_dict = raw_main_stuff.get("content", raw_main_stuff)
        json_text = clean_json_dumps(content_dict, indent=2)
        files["main_stuff.json"] = ResultFile(data=json_text.encode("utf-8"), content_type="application/json")
        files["main_stuff.md"] = ResultFile(data=f"```json\n{json_text}\n```\n".encode(), content_type="text/markdown")
        # Escape HTML-special chars: json.dumps does not escape <, >, &, so embedding
        # raw user-controlled JSON inside <pre> would allow stored XSS via strings
        # like "</pre><script>...</script>" in pipeline outputs.
        files["main_stuff.html"] = ResultFile(data=f"<pre>{html.escape(json_text)}</pre>".encode(), content_type="text/html")

    async def _generate_main_stuff_files(self, main_stuff: Stuff, files: dict[str, ResultFile]) -> None:
        content = main_stuff.content
        await self._try_add_rendered_file(files, "main_stuff.json", content.rendered_json_async(), "application/json")
        await self._try_add_rendered_file(files, "main_stuff.md", content.rendered_markdown_async(), "text/markdown")
        await self._try_add_rendered_file(files, "main_stuff.html", content.rendered_html_async(), "text/html")
        await self._try_add_rendered_file(files, "main_stuff_viewer.html", render_stuff_viewer(main_stuff), "text/html")

    async def _generate_graph_files(self, graph_spec: Any, files: dict[str, ResultFile]) -> None:
        try:
            graph_config = get_config().pipelex.pipeline_execution_config.graph_config
            graph_outputs = await generate_graph_outputs(
                graph_spec=graph_spec,
                graph_config=graph_config,
            )
            self._add_optional_text_file(files, "graphspec.json", graph_outputs.graphspec_json, "application/json")
            self._add_optional_text_file(files, "mermaidflow.mmd", graph_outputs.mermaidflow_mmd, "text/plain")
            self._add_optional_text_file(files, "mermaidflow.html", graph_outputs.mermaidflow_html, "text/html")
            self._add_optional_text_file(files, "reactflow.html", graph_outputs.reactflow_html, "text/html")
        except Exception:  # noqa: BLE001
            # Best-effort: graph generation spans a deep mermaid/reactflow render tree; a graph failure must never fail result delivery.
            log.warning("Failed to generate graph outputs")

    @classmethod
    async def _try_add_rendered_file(
        cls,
        files: dict[str, ResultFile],
        filename: str,
        render: Awaitable[str],
        content_type: str,
    ) -> None:
        """Await a render coroutine and store the encoded result; log a warning on failure."""
        try:
            text = await render
        except Exception:  # noqa: BLE001
            # Best-effort: per-format rendering (incl. jinja2 viewer); a single render failure must not drop the other result files.
            log.warning(f"Failed to render {filename}")
            return
        files[filename] = ResultFile(data=text.encode("utf-8"), content_type=content_type)

    @classmethod
    def _add_optional_text_file(cls, files: dict[str, ResultFile], filename: str, text: str | None, content_type: str) -> None:
        """Encode `text` and store it under `filename`. No-op when `text` is None."""
        if text is not None:
            files[filename] = ResultFile(data=text.encode("utf-8"), content_type=content_type)

    # ---- Storage ----

    async def _store_results(
        self,
        pipe_output: PipeOutput,
        user_id: str,
        pipeline_run_id: str,
        storage: StorageTarget,
        request_id: str | None = None,
    ) -> str:
        """Generate all result files and store them. Returns the base result URL."""
        try:
            storage_provider = get_storage_provider()
            prefix: str = storage.key_prefix or ""
            base_key: str = f"{user_id}/{prefix}{pipeline_run_id}"

            result_files = await self.generate_result_files(pipe_output)

            for filename, result_file in result_files.items():
                key: str = f"{base_key}/{filename}"
                await storage_provider.store(data=result_file.data, key=key, content_type=result_file.content_type)
                log.debug(f"Stored: {key}")

            # TODO: include the full S3 URI (s3://bucket/key/) so result_url is
            # self-contained and doesn't depend on knowing the bucket externally.
            result_url: str = f"{base_key}/"
            request_id_suffix = f", request_id={request_id}" if request_id is not None else ""
            log.info(f"Storage delivery completed: pipeline_run_id={pipeline_run_id}, files={len(result_files)}{request_id_suffix}")
            return result_url
        except Exception as exc:
            # Delivery boundary: any failure across result-file generation or storage is converted to StorageDeliveryError. Re-raises, never swallows.
            msg = f"Storage delivery failed for pipeline_run_id={pipeline_run_id}"
            raise StorageDeliveryError(msg) from exc

    # ---- Webhooks ----

    async def _notify_webhook(
        self,
        pipeline_run_id: str,
        status: DeliveryStatus,
        result_url: str | None,
        webhook: WebhookTarget,
        error_report: ErrorReport | None = None,
        request_id: str | None = None,
    ) -> None:
        """POST status, optional result_url, and optional VERBOSE error report to a webhook URL.

        VERBOSE on the wire is deliberate: the receiver decides what to re-expose
        downstream (it can render STRICT via :meth:`ErrorReport.to_problem_document`).
        """
        try:
            payload: dict[str, Any] = dict(webhook.payload)
            payload["pipeline_run_id"] = pipeline_run_id
            payload["status"] = status
            if result_url is not None:
                payload["result_url"] = result_url
            if error_report is not None:
                payload["error"] = error_report.to_dict(disclosure_mode=DisclosureMode.VERBOSE)

            async with httpx.AsyncClient() as client:
                response = await client.post(
                    webhook.url,
                    json=payload,
                    headers=webhook.headers,
                    timeout=30.0,
                )
                response.raise_for_status()
            request_id_suffix = f", request_id={request_id}" if request_id is not None else ""
            log.info(f"Webhook delivery completed: pipeline_run_id={pipeline_run_id}, url={webhook.url}{request_id_suffix}")
        except httpx.HTTPStatusError as exc:
            msg = f"Webhook delivery failed for pipeline_run_id={pipeline_run_id}: HTTP {exc.response.status_code}"
            raise WebhookDeliveryError(msg) from exc
        except httpx.RequestError as exc:
            msg = f"Webhook delivery failed for pipeline_run_id={pipeline_run_id}: {exc}"
            raise WebhookDeliveryError(msg) from exc
