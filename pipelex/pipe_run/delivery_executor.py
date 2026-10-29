from __future__ import annotations

import html
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, Awaitable, NamedTuple, cast
from urllib.parse import urlsplit

import httpx
from kajson.exceptions import KajsonException
from mthds.protocol.problem.registry import CoreCode
from pydantic import ValidationError

from pipelex import log
from pipelex.base_exceptions import PipelexError
from pipelex.config import get_config
from pipelex.core.concepts.concept_factory import ConceptFactory
from pipelex.core.concepts.exceptions import ConceptLibraryConceptNotFoundError, ConceptRefAmbiguousError
from pipelex.core.concepts.native.concept_native import NativeConceptCode
from pipelex.core.memory.absence import AbsenceRecord
from pipelex.core.memory.absence_render import build_absence_html, build_absence_json, build_absence_markdown
from pipelex.core.memory.working_memory import MAIN_STUFF_NAME
from pipelex.core.pipes.pipe_io_artifacts import INPUT_FORM_FILE_NAME, OUTPUT_FORM_FILE_NAME, PIPE_IO_CONTRACTS_FILE_NAME
from pipelex.core.qualified_ref import QualifiedRef
from pipelex.core.qualified_ref_exceptions import QualifiedRefError
from pipelex.core.stuffs.stuff import Stuff
from pipelex.core.stuffs.stuff_content import StuffContent
from pipelex.core.stuffs.stuff_viewer import render_stuff_viewer
from pipelex.errors.problem import PipelexProblem, ProblemView, caller_view_of, make_problem
from pipelex.graph.graph_factory import generate_graph_outputs
from pipelex.interpreter_hub import get_concept_library, get_current_library_id_or_none
from pipelex.libraries.exceptions import LibraryError
from pipelex.pipe_run.caller_webhook_delivery import deliver_caller_webhooks
from pipelex.pipe_run.delivery_assignment import DeliveryStatus
from pipelex.pipe_run.exceptions import DeliveryError, PipeJobError, StorageDeliveryError, WebhookDeliveryError
from pipelex.pipe_run.located_failure import make_unexpected_failure
from pipelex.reporting.usage_records import dump_tokens_usage_records
from pipelex.runtime_bridge.primitives.hydration import hydrate_content
from pipelex.runtime_hub import get_class_registry, get_storage_provider
from pipelex.tools.log.error_fields import error_fields
from pipelex.tools.misc.json_utils import clean_json_dumps
from pipelex.tools.network.exceptions import SsrfBlockedError
from pipelex.tools.network.ssrf_guard import SsrfGuardedTransport

if TYPE_CHECKING:
    from collections.abc import Mapping

    from pipelex.core.concepts.concept import Concept
    from pipelex.core.pipes.pipe_io_artifacts import PipeIOArtifacts
    from pipelex.core.pipes.pipe_output import PipeOutput
    from pipelex.pipe_run.delivery_assignment import DeliveryAssignment, StorageTarget, WebhookTarget
    from pipelex.tools.storage.storage_provider_abstract import StorageKind


class ResultFile(NamedTuple):
    """A generated result file with its bytes and MIME type, ready to store."""

    data: bytes
    content_type: str


def _problem_wires_by_view(*, problem: PipelexProblem | None, webhooks: list[WebhookTarget]) -> dict[ProblemView, dict[str, Any]]:
    """A failed run's problem in the wire form of each view the webhooks read it in, each view built once.

    ``problem`` is in the operator's view, which an operator's webhook receives as it is, and a caller's webhook
    receives its caller view, projected once for every caller webhook rather than once per webhook.
    """
    wires: dict[ProblemView, dict[str, Any]] = {}
    if problem is None:
        return wires
    for webhook in webhooks:
        view = webhook.problem_view
        if view in wires:
            continue
        match view:
            case ProblemView.OPERATOR:
                wires[view] = problem.to_wire()
            case ProblemView.CALLER:
                wires[view] = caller_view_of(problem=problem).to_wire()
    return wires


WEBHOOK_PROBLEM_FAULT_MESSAGE = "The problem of a failed run could not be built for its webhooks"
"""The error logged when a failed run's problem raises while it is built for the run's webhooks."""


def run_problem_of(*, error: Exception, pipeline_run_id: str, request_id: str | None) -> PipelexProblem:
    """The problem of a failed run that its webhooks receive, in the operator's view, which each webhook projects to its own.

    A Pipelex error carries its own code, and a bare exception stands as a fault of ours, so a webhook still receives
    an ``error`` object. Delivery never changes how a run fails: this runs while the run's own error, or the delivery's
    that the run will fail with, is on its way, so building the problem must not raise in its place. A problem that
    cannot be built is logged as an error, and the webhooks receive ``runtime.unexpected``, as a traced node does
    (``make_node_problem``).

    Args:
        error: The error the run fails with.
        pipeline_run_id: The run's id, which the problem names.
        request_id: The originating request's id, when there was one.

    Returns:
        The problem, in the operator's view.
    """
    failure = error if isinstance(error, PipelexError) else make_unexpected_failure(error=error)
    try:
        return failure.to_problem(view=ProblemView.OPERATOR, pipeline_run_id=pipeline_run_id, request_id=request_id)
    except Exception as problem_fault:  # ruff: ignore[blind-except]
        # Unbounded code: `to_problem` reads hooks overridden across the whole error hierarchy, the errors plugins
        # define included, and walks the error's cause chain, so what it raises cannot be enumerated. The run's own
        # error is the one it fails with, so the fault is logged and the webhooks receive a fault of ours.
        log.error(
            WEBHOOK_PROBLEM_FAULT_MESSAGE,
            fields={"failed_error_type": type(error).__name__, **error_fields(exc=problem_fault)},
        )
    return make_problem(code=CoreCode.RUNTIME_UNEXPECTED, view=ProblemView.OPERATOR, pipeline_run_id=pipeline_run_id, request_id=request_id)


class RunEnding(NamedTuple):
    """How a run ended, as its caller's webhooks are told: its status, and a failed run's problem in the operator's view."""

    status: DeliveryStatus
    problem: PipelexProblem | None


def run_ending_after_host_failure(
    *,
    status: DeliveryStatus,
    problem: PipelexProblem | None,
    host_error: Exception,
    pipeline_run_id: str,
    request_id: str | None,
) -> RunEnding:
    """How a run ends once the host step of its delivery failed, which its caller's webhooks are told.

    A run that completed fails with the host step's error, a storage failure or a refused or failed notice to one of
    the host's webhooks, so its caller is told it failed, with that error's problem, never that it completed. A run
    that had failed keeps its own failure, and its own problem.

    Args:
        status: How the run ended before the delivery.
        problem: A failed run's problem, in the operator's view.
        host_error: What the host step raised.
        pipeline_run_id: The run's id.
        request_id: The originating request's id, when there was one.

    Returns:
        How the run ends.
    """
    match status:
        case DeliveryStatus.COMPLETED:
            return RunEnding(
                status=DeliveryStatus.FAILED,
                problem=run_problem_of(error=host_error, pipeline_run_id=pipeline_run_id, request_id=request_id),
            )
        case DeliveryStatus.FAILED:
            return RunEnding(status=status, problem=problem)


class DeliveryExecutor:
    """Handles a finished run's delivery, in two steps: the host's, then the caller's.

    The **host step**, :meth:`execute_host_delivery`, generates and stores the result files, then notifies the host's
    own webhooks, such as a deployment's completion target, and raises when either fails. The **caller step**,
    :meth:`execute_caller_delivery`, sends each caller webhook the signed ``run.finished`` event and never raises.

    :meth:`execute` runs both in one process, the caller step last and once, after the host step has settled, with the
    status the run ends with: when the host step fails, a completed run fails with its error, and the caller is told so
    (:func:`run_ending_after_host_failure`). A durable orchestrator that retries a failed step runs the two as separate
    steps, the caller step after the host step has settled, so that a retried host step never sends the caller's event
    again, and the event states how the run ended, the host step's failure included.
    """

    async def execute(
        self,
        pipe_output: PipeOutput | None,
        *,
        storage_scope: str,
        pipeline_run_id: str,
        delivery_assignment: DeliveryAssignment,
        status: DeliveryStatus,
        problem: PipelexProblem | None = None,
        request_id: str | None = None,
        finished_at: datetime | None = None,
        extras: Mapping[str, str] | None = None,
    ) -> None:
        """Execute a full delivery: the host step, then the caller step, last and once.

        ``problem`` is a failed run's problem in the operator's view, which each of the host's webhooks receives in its
        own view, and each caller webhook in the caller's (:mod:`pipelex.pipe_run.caller_webhook_delivery`).

        When the host step fails, the caller's webhooks are told how the run ends, and the host step's error is raised
        once they were. Their own failures never raise: each is logged. ``finished_at`` is when the run ended, the
        caller's event's ``timestamp``, and the moment the delivery starts when it is not given; ``extras`` are the
        run's opaque extras, which the security event of a caller webhook's refused destination carries.

        ``request_id`` is the originating API request id (when set). The delivery binds it
        with ``pipeline_run_id`` onto the log context, so every record the delivery emits,
        its storage and webhook completion lines included, carries both and correlates
        with the workflow logs and the inbound request, whether or not the caller bound
        them already. A ``None`` request id inherits whatever the caller bound.
        """
        run_finished_at = finished_at or datetime.now(UTC)
        with log.context(request_id=request_id, pipeline_run_id=pipeline_run_id):
            try:
                await self.execute_host_delivery(
                    pipe_output,
                    storage_scope=storage_scope,
                    pipeline_run_id=pipeline_run_id,
                    delivery_assignment=delivery_assignment,
                    status=status,
                    problem=problem,
                    request_id=request_id,
                )
            except (DeliveryError, SsrfBlockedError) as host_error:
                if delivery_assignment.caller_webhooks:
                    run_ending = run_ending_after_host_failure(
                        status=status,
                        problem=problem,
                        host_error=host_error,
                        pipeline_run_id=pipeline_run_id,
                        request_id=request_id,
                    )
                    await self.execute_caller_delivery(
                        pipeline_run_id=pipeline_run_id,
                        delivery_assignment=delivery_assignment,
                        status=run_ending.status,
                        problem=run_ending.problem,
                        finished_at=run_finished_at,
                        request_id=request_id,
                        extras=extras,
                    )
                raise
            await self.execute_caller_delivery(
                pipeline_run_id=pipeline_run_id,
                delivery_assignment=delivery_assignment,
                status=status,
                problem=problem,
                finished_at=run_finished_at,
                request_id=request_id,
                extras=extras,
            )

    async def execute_host_delivery(
        self,
        pipe_output: PipeOutput | None,
        *,
        storage_scope: str,
        pipeline_run_id: str,
        delivery_assignment: DeliveryAssignment,
        status: DeliveryStatus,
        problem: PipelexProblem | None = None,
        request_id: str | None = None,
    ) -> None:
        """The host step: store a completed run's result files, then notify each of the host's own webhooks.

        Raises:
            StorageDeliveryError: The result files could not be generated or stored; no webhook was notified.
            WebhookDeliveryError: One of the host's webhooks could not be notified.
            SsrfBlockedError: The SSRF guard refused a host webhook's destination.
        """
        with log.context(request_id=request_id, pipeline_run_id=pipeline_run_id):
            result_url: str | None = None
            if delivery_assignment.storage is not None and pipe_output is not None:
                result_url = await self._store_results(
                    pipe_output,
                    storage_scope=storage_scope,
                    pipeline_run_id=pipeline_run_id,
                    storage=delivery_assignment.storage,
                )
            problem_wires = _problem_wires_by_view(problem=problem, webhooks=delivery_assignment.webhooks)
            for webhook in delivery_assignment.webhooks:
                await self._notify_webhook(
                    pipeline_run_id=pipeline_run_id,
                    status=status,
                    result_url=result_url,
                    webhook=webhook,
                    problem_wire=problem_wires.get(webhook.problem_view),
                )

    async def execute_caller_delivery(
        self,
        *,
        pipeline_run_id: str,
        delivery_assignment: DeliveryAssignment,
        status: DeliveryStatus,
        problem: PipelexProblem | None,
        finished_at: datetime,
        request_id: str | None = None,
        extras: Mapping[str, str] | None = None,
    ) -> None:
        """The caller step: send each caller webhook the signed ``run.finished`` event, saying how the run ended.

        It never raises: a delivery that fails is logged, and changes nothing of the run. ``status`` and ``problem`` are
        how the run ends, after the host step (:func:`run_ending_after_host_failure`).
        """
        if not delivery_assignment.caller_webhooks:
            return
        with log.context(request_id=request_id, pipeline_run_id=pipeline_run_id):
            await deliver_caller_webhooks(
                targets=delivery_assignment.caller_webhooks,
                pipeline_run_id=pipeline_run_id,
                status=status,
                problem=problem,
                finished_at=finished_at,
                extras=extras,
            )

    # ---- Result file generation ----

    async def generate_result_files(self, pipe_output: PipeOutput) -> dict[str, ResultFile]:
        """Generate the full set of result files from a PipeOutput.

        Produces: working_memory.json, main_stuff (json/md/html/viewer),
        tokens_usages.json, graph outputs (mermaidflow, reactflow, graphspec).

        Supports two `pipe_output` shapes:
        - Typed: `working_memory` populated (in-process / same-worker path).
        - Raw: `working_memory_raw` populated (cross-process Temporal path,
          where the activity worker may not have the method's library loaded).
          The activity tries to locally hydrate the main stuff with the concepts
          this process knows — the current library when one is set, the native
          set otherwise — and the globally registered classes; on failure it
          falls back to a generic dict render so built-in content types still
          get typed rendering and dynamic concepts produce a readable JSON dump.

        A completed run always resolves its declared output: a value or a
        recorded absence. The main_stuff.* artifact files are always produced —
        for an absent output they are an explicit absence artifact (never an
        error: an absent result is a first-class success). A working memory
        with neither a value nor a recorded absence is a contract violation
        that fails the delivery loudly, never an "empty envelope" silently
        missing its result files.
        """
        files: dict[str, ResultFile] = {}

        if pipe_output.working_memory_raw is not None:
            files["working_memory.json"] = ResultFile(
                data=clean_json_dumps(pipe_output.working_memory_raw, indent=2).encode("utf-8"),
                content_type="application/json",
            )
            raw_main_stuff = self._get_raw_main_stuff_dict(working_memory_raw=pipe_output.working_memory_raw)
            if raw_main_stuff is None:
                main_absence = self._get_raw_main_absence(working_memory_raw=pipe_output.working_memory_raw)
                if main_absence is None:
                    msg = (
                        "Delivery of a completed run found neither a main stuff nor a recorded absence in the raw "
                        "working memory — a completed run always resolves its declared output."
                    )
                    raise PipeJobError(msg)
                self._generate_absence_files(main_absence, files=files)
            else:
                hydrated_main_stuff = self.try_local_hydrate_stuff(raw_main_stuff)
                if hydrated_main_stuff is not None:
                    await self._generate_main_stuff_files(hydrated_main_stuff, files=files)
                else:
                    self._generate_main_stuff_files_from_raw(raw_main_stuff, files=files)
        else:
            files["working_memory.json"] = ResultFile(
                data=clean_json_dumps(pipe_output.working_memory.smart_dump(), indent=2).encode("utf-8"),
                content_type="application/json",
            )
            main_resolved = pipe_output.working_memory.resolve_main_stuff()
            if isinstance(main_resolved, AbsenceRecord):
                self._generate_absence_files(main_resolved, files=files)
            else:
                await self._generate_main_stuff_files(main_resolved, files=files)

        files["tokens_usages.json"] = self._generate_usage_file(pipe_output)

        graph_spec = pipe_output.graph_spec
        if graph_spec:
            await self._generate_graph_files(graph_spec, pipe_io_artifacts=pipe_output.pipe_io_artifacts, files=files)

        return files

    @classmethod
    def _generate_usage_file(cls, pipe_output: PipeOutput) -> ResultFile:
        """Serialize the run's assembled usage onto the tokens_usages.json artifact.

        Written unconditionally, so a durable client polling the result files can tell
        "usage assembly was off for this run" (file present, ``tokens_usages`` null) from
        "run delivered before the artifact existed" (file absent). The records use the
        client wire shape (``TokensUsageRecord``) — the same shape the ``/execute``
        response carries on ``pipe_output.tokens_usages`` — never the internal
        full-fidelity usage models.

        TODO: the envelope carries no RUN TOTAL, so every consumer that wants "what did
        this run cost" sums the list itself. The number already exists as
        ``GraphSpec.usage.total`` — but only on the graph, an optional and often large
        RENDERING artifact, which is the wrong contract to read a price from (turn off
        ``is_generate_graph`` and the total disappears while this file is still written).
        Store it here instead, from the same ``compute_tokens_usage_cost`` engine the
        graph rollup and the cost report both go through, so two artifacts of one run can
        never quote different prices. Keep the three-valued semantics rather than
        flattening them: ``None`` means unrated and must never render as zero, and a
        partially rated run's total is a lower bound. Tracked as T-5 in
        ``pipelex-server/TODOS.md``.
        """
        usage_doc: dict[str, Any] = {
            "tokens_usages": dump_tokens_usage_records(pipe_output.tokens_usages),
            "usage_assembly_error": pipe_output.usage_assembly_error,
        }
        return ResultFile(data=clean_json_dumps(usage_doc, indent=2).encode("utf-8"), content_type="application/json")

    @classmethod
    def _get_raw_main_stuff_dict(cls, *, working_memory_raw: dict[str, Any]) -> dict[str, Any] | None:
        """Extract the main stuff dict from a raw working_memory, following aliases."""
        root: dict[str, Any] = working_memory_raw.get("root", {})
        aliases: dict[str, str] = working_memory_raw.get("aliases", {})
        target_name = aliases.get(MAIN_STUFF_NAME, MAIN_STUFF_NAME)
        candidate = root.get(target_name)
        if isinstance(candidate, dict):
            return cast("dict[str, Any]", candidate)
        return None

    @classmethod
    def _get_raw_main_absence(cls, *, working_memory_raw: dict[str, Any]) -> AbsenceRecord | None:
        """Extract the recorded main-output absence from a raw working_memory's ledger, if any.

        A malformed record is treated as missing (the caller then fails the delivery loudly as a
        contract violation) rather than half-rendered.
        """
        absences: dict[str, Any] = working_memory_raw.get("absences", {})
        candidate = absences.get(MAIN_STUFF_NAME)
        if not isinstance(candidate, dict):
            return None
        try:
            return AbsenceRecord.model_validate(candidate)
        except ValidationError as validation_error:
            # Treated as missing, the caller then fails the delivery: the record is lost, and this line says why. The
            # error rides as its fields, never its text or traceback, which quote the values the record held.
            log.error(
                "The absence record of the main output is malformed",
                fields=error_fields(exc=validation_error, validated_type=AbsenceRecord),
            )
            return None

    @classmethod
    def _generate_absence_files(cls, absence_record: AbsenceRecord, *, files: dict[str, ResultFile]) -> None:
        """Render the explicit absence artifact for an absent main output.

        The JSON carries an explicit ``"absent": true`` discriminator beside the record fields so
        a consumer polling ``main_stuff.json`` can tell an absence document from a value dump.
        """
        files["main_stuff.json"] = ResultFile(data=build_absence_json(absence_record).encode("utf-8"), content_type="application/json")
        files["main_stuff.md"] = ResultFile(data=build_absence_markdown(absence_record).encode("utf-8"), content_type="text/markdown")
        files["main_stuff.html"] = ResultFile(data=build_absence_html(absence_record).encode("utf-8"), content_type="text/html")

    @classmethod
    def _resolve_concept_locally(cls, *, concept_ref: str) -> Concept | None:
        """Resolve a transported stuff's concept ref with what this process holds.

        A delivery worker never loads the crate, so a dynamic concept is unknown to it by
        design. When a library is current — an in-process run delivering its own result — the
        ref goes through the shared wire-ref rule, so a concept a dependency package contributed
        resolves through its aliased entry; otherwise only the native concepts are known, and they
        are built from their pinned definitions. ``None`` means "not known here", and it means that
        for a malformed ref and for a library that has gone away as much as for an unknown one:
        this reader renders a result and must never fail a delivery, so every way of failing to
        name a concept ends in the raw render.

        A spelling the library holds more than once is "not known here" too, deliberately: the
        collision is logged by name and the caller falls back to the raw render rather than binding
        one package's definition to another package's data.
        """
        if get_current_library_id_or_none() is not None:
            try:
                return get_concept_library().resolve_wire_concept_ref(concept_ref=concept_ref)
            except ConceptRefAmbiguousError as exc:
                log.warning(
                    "A delivered result's concept ref is ambiguous and the result was rendered raw",
                    fields={"concept_ref": concept_ref, **error_fields(exc=exc)},
                )
                return None
            except (LibraryError, ConceptLibraryConceptNotFoundError):
                return None
            except RuntimeError as exc:
                # The contextvar still names a library, but the hub that held it is gone. A delivery
                # outlives the run it renders, so this is a race to survive, not a state to assert.
                log.warning("The current library is gone and a delivered result was rendered raw", fields=error_fields(exc=exc))
                return None
        try:
            is_native_ref = NativeConceptCode.is_valid_native_concept_ref(concept_ref=concept_ref)
        except QualifiedRefError as exc:
            log.warning(
                "A delivered result's concept ref is malformed and the result was rendered raw",
                fields={"concept_ref": concept_ref, **error_fields(exc=exc)},
            )
            return None
        if not is_native_ref:
            return None
        native_code = QualifiedRef.parse(concept_ref).local_code
        return ConceptFactory.make_native_concept(native_concept_code=NativeConceptCode(native_code))

    @classmethod
    def try_local_hydrate_stuff(cls, stuff_raw: dict[str, Any]) -> Stuff | None:
        """Attempt to hydrate a single Stuff dict with the concepts and classes this process holds.

        The stuff names its concept by ref (``"concept": "<domain>.<Code>"``); the ref is
        resolved locally — the current library when one is set, the native set otherwise —
        and the concept's structure class is then looked up in the class registry. Returns
        None when the concept or its class isn't available locally (typically a dynamic
        concept the activity worker never loaded) — callers then fall back to a generic
        raw-dict render. A warning is emitted on the fallback path so silent regressions
        on built-in hydration surface in logs.
        """
        # The class the content validates into, whose schema names a refusal's locations in the warning.
        structure_class: type[StuffContent] | None = None
        try:
            concept_ref = stuff_raw["concept"]
            if not isinstance(concept_ref, str):
                # A stale runtime dumped the whole concept object here: worth a redeploy, so a warning.
                log.warning("A delivered result names no concept ref string and was rendered raw")
                return None
            concept = cls._resolve_concept_locally(concept_ref=concept_ref)
            if concept is None:
                # A crate-free delivery worker does not know a method's own concepts by design, so this is the
                # expected path for most hosted results: worth a debug line, not a warning nobody can act on.
                log.debug("A delivered result's concept is not known here and was rendered raw", fields={"concept_ref": concept_ref})
                return None
            # A structureless concept (`native.Anything`) names no class to look up: its content carries its own.
            if concept.declares_a_structure_class:
                item_class = get_class_registry().get_class(name=concept.structure_class_name)
                if item_class is None or not issubclass(item_class, StuffContent):
                    log.warning(
                        "A delivered result's structure class is unregistered here and was rendered raw",
                        fields={"concept_ref": concept_ref, "structure_class_name": concept.structure_class_name},
                    )
                    return None
                structure_class = item_class
            content = hydrate_content(concept=concept, raw_content=stuff_raw["content"])
            return Stuff(
                stuff_code=stuff_raw["stuff_code"],
                stuff_name=stuff_raw.get("stuff_name"),
                concept=concept,
                content=content,
            )
        except (PipeJobError, ValidationError, KajsonException, KeyError, TypeError) as exc:
            log.warning(
                "A delivered result could not be hydrated and was rendered raw",
                fields=error_fields(exc=exc, validated_type=structure_class),
            )
            return None

    @classmethod
    def _generate_main_stuff_files_from_raw(cls, raw_main_stuff: dict[str, Any], *, files: dict[str, ResultFile]) -> None:
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

    async def _generate_main_stuff_files(self, main_stuff: Stuff, *, files: dict[str, ResultFile]) -> None:
        content = main_stuff.content
        await self._try_add_rendered_file(
            files=files, filename="main_stuff.json", render=content.rendered_json_async(), content_type="application/json"
        )
        await self._try_add_rendered_file(
            files=files, filename="main_stuff.md", render=content.rendered_markdown_async(), content_type="text/markdown"
        )
        await self._try_add_rendered_file(files=files, filename="main_stuff.html", render=content.rendered_html_async(), content_type="text/html")
        await self._try_add_rendered_file(
            files=files, filename="main_stuff_viewer.html", render=render_stuff_viewer(main_stuff), content_type="text/html"
        )

    async def _generate_graph_files(self, graph_spec: Any, *, pipe_io_artifacts: PipeIOArtifacts | None, files: dict[str, ResultFile]) -> None:
        try:
            graph_config = get_config().interpreter.pipeline_execution.graph
            graph_outputs = await generate_graph_outputs(
                graph_spec=graph_spec,
                graph_config=graph_config,
                pipe_io_artifacts=pipe_io_artifacts,
            )
            self._add_optional_text_file(files=files, filename="graphspec.json", text=graph_outputs.graphspec_json, content_type="application/json")
            # The graphspec's companions, under the standard's names beside it.
            self._add_optional_text_file(
                files=files, filename=PIPE_IO_CONTRACTS_FILE_NAME, text=graph_outputs.pipe_io_contracts_json, content_type="application/json"
            )
            self._add_optional_text_file(
                files=files, filename=INPUT_FORM_FILE_NAME, text=graph_outputs.input_form_json, content_type="application/json"
            )
            self._add_optional_text_file(
                files=files, filename=OUTPUT_FORM_FILE_NAME, text=graph_outputs.output_form_json, content_type="application/json"
            )
            self._add_optional_text_file(files=files, filename="mermaidflow.mmd", text=graph_outputs.mermaidflow_mmd, content_type="text/plain")
            self._add_optional_text_file(files=files, filename="mermaidflow.html", text=graph_outputs.mermaidflow_html, content_type="text/html")
            self._add_optional_text_file(files=files, filename="reactflow.html", text=graph_outputs.reactflow_html, content_type="text/html")
        except Exception as exc:  # ruff: ignore[blind-except]
            # Best-effort: graph generation spans a deep mermaid/reactflow render tree; a graph failure must never fail result delivery.
            log.warning("The graph outputs could not be generated", fields=error_fields(exc=exc))

    @classmethod
    async def _try_add_rendered_file(
        cls,
        *,
        files: dict[str, ResultFile],
        filename: str,
        render: Awaitable[str],
        content_type: str,
    ) -> None:
        """Await a render coroutine and store the encoded result; log a warning on failure."""
        try:
            text = await render
        except Exception as exc:  # ruff: ignore[blind-except]
            # Best-effort: per-format rendering (incl. jinja2 viewer); a single render failure must not drop the other result files.
            log.warning(
                "A result file could not be rendered and was left out of the delivery",
                fields={"file.name": filename, **error_fields(exc=exc)},
            )
            return
        files[filename] = ResultFile(data=text.encode("utf-8"), content_type=content_type)

    @classmethod
    def _add_optional_text_file(cls, *, files: dict[str, ResultFile], filename: str, text: str | None, content_type: str) -> None:
        """Encode `text` and store it under `filename`. No-op when `text` is None."""
        if text is not None:
            files[filename] = ResultFile(data=text.encode("utf-8"), content_type=content_type)

    # ---- Storage ----

    async def _store_results(
        self,
        pipe_output: PipeOutput,
        *,
        storage_scope: str,
        pipeline_run_id: str,
        storage: StorageTarget,
    ) -> str:
        """Generate all result files and store them. Returns the base result URL.

        The key is `{storage_scope}/{key_prefix}results/`. It was
        `{user_id}/{key_prefix}{pipeline_run_id}` — keyed by WHO ran the pipe,
        which is what made a run's outputs unreadable by anyone else on the same
        team. `storage_scope` already identifies the run (the host composes it
        from whatever its tenancy model is), so `pipeline_run_id` no longer
        appears in the key; it stays a parameter because the failure below
        names it.
        """
        storage_kind: StorageKind | None = None
        try:
            storage_provider = get_storage_provider()
            storage_kind = storage_provider.storage_kind
            prefix: str = storage.key_prefix or ""
            base_key: str = f"{storage_scope}/{prefix}results"

            result_files = await self.generate_result_files(pipe_output)

            for filename, result_file in result_files.items():
                key: str = f"{base_key}/{filename}"
                await storage_provider.store(data=result_file.data, key=key, content_type=result_file.content_type)
                log.debug("Stored a delivery result file", fields={"storage_key": key})

            # TODO: include the full S3 URI (s3://bucket/key/) so result_url is
            # self-contained and doesn't depend on knowing the bucket externally.
            result_url: str = f"{base_key}/"
            log.info("Storage delivery completed", fields={"file_count": len(result_files)})
            return result_url
        except Exception as exc:
            # Delivery boundary: any failure across result-file generation or storage is converted to StorageDeliveryError. Re-raises, never swallows.
            msg = f"Storage delivery failed for pipeline_run_id={pipeline_run_id}"
            # The storage's kind is what `pipelex.storage.unavailable`, the fallback of an uncoded cause, names; a coded
            # cause that names its own keeps it.
            delivery_error = StorageDeliveryError(msg)
            if storage_kind is not None:
                delivery_error = delivery_error.with_params(scheme=storage_kind)
            raise delivery_error from exc

    # ---- Webhooks ----

    async def _notify_webhook(
        self,
        *,
        pipeline_run_id: str,
        status: DeliveryStatus,
        result_url: str | None,
        webhook: WebhookTarget,
        problem_wire: dict[str, Any] | None = None,
    ) -> None:
        """POST status, optional result_url, and a failed run's problem to one of the host's own webhooks.

        ``problem_wire`` is the problem in the webhook's own view (``WebhookTarget.problem_view``),
        already in its wire form: an operator's webhook, such as a hosted plane's completion
        callback, receives the diagnostics, and a caller's receives the problem without them.

        The HTTP client uses :class:`SsrfGuardedTransport`, which re-resolves the
        callback host at connect time and refuses private/loopback/metadata
        destinations — closing the DNS-rebinding gap a request-time literal-IP
        check leaves open. A blocked destination raises
        :class:`pipelex.tools.network.exceptions.SsrfBlockedError`, which (being a
        security signal) is deliberately *not* caught and re-wrapped as a
        ``WebhookDeliveryError`` here — it propagates so the delivery aborts loudly.
        """
        try:
            payload: dict[str, Any] = dict(webhook.payload)
            # Wire fields follow the MTHDS Protocol: `pipeline_run_id` (unchanged)
            # + `state` (master D1 as revised). The legacy `status` spelling rides
            # along for one release so receivers can migrate without a
            # deploy-window gap (the hosted run-completion Lambda accepts both
            # during the Phase C skew).
            payload["pipeline_run_id"] = pipeline_run_id
            payload["state"] = status
            payload["status"] = status
            if result_url is not None:
                payload["result_url"] = result_url
            if problem_wire is not None:
                payload["error"] = problem_wire

            async with httpx.AsyncClient(transport=SsrfGuardedTransport()) as client:
                response = await client.post(
                    webhook.url,
                    json=payload,
                    headers=webhook.headers,
                    timeout=30.0,
                )
                response.raise_for_status()
            # The receiver's host and not its URL: a webhook URL is the caller's, and its path or query may carry a credential.
            log.info("Webhook delivery completed", fields={"server.address": urlsplit(webhook.url).hostname})
        except httpx.HTTPStatusError as exc:
            msg = f"Webhook delivery failed for pipeline_run_id={pipeline_run_id}: HTTP {exc.response.status_code}"
            raise WebhookDeliveryError(msg).with_params(reason="http_status", receiver_status=exc.response.status_code) from exc
        except httpx.RequestError as exc:
            # By the failure's class, never its text, which can quote the caller's webhook URL.
            msg = f"Webhook delivery failed for pipeline_run_id={pipeline_run_id}: {type(exc).__name__}"
            raise WebhookDeliveryError(msg).with_params(reason="unreachable") from exc
