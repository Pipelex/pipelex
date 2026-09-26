"""The batch validation service (D1) — the explicit home for the validation sweep.

A validation sweep is **not** a run: it is a batch *policy* that *uses* runs. So
``BundleValidator`` owns the sweep semantics (strict-mode signature exclusion, the
``validate_with_libraries`` wiring check, the per-pipe tolerant
``SUCCESS / FAILURE / SKIPPED`` aggregation, ``allowed_to_fail`` policy) and
**composes** the shared execution seams (``acquire_library`` /
``prepare_pipe_job``) plus a direct, in-process ``PipeRun`` — the same execution
core ``PipelexMTHDSProtocol`` reaches for a single run. It never forks the runner and
never threads validation-only flags through it.

Two lifecycles (D6):

- :meth:`BundleValidator.acquire_and_validate` — *acquire-and-sweep*: opens a
  fresh library, loads dirs + contents, sweeps **all** loaded pipes, and owns
  teardown in a ``finally``. This is the standalone ``validate --all`` lifecycle.
- :meth:`BundleValidator.validate_pipes` — *public inner sweep*: classifies a
  caller-supplied list of pipes against the caller's **already-open** library and
  **never tears it down**, preserving the loaded-on-success contract that callers
  like ``validate_bundle`` and the build CLIs depend on.

The per-pipe execution primitive is a **locally-constructed** ``PipeRun`` —
explicitly **not** the hub's ``get_pipe_run()``, which under a Temporal hub would
spawn a workflow per pipe (and is illegal from inside an activity). Keeping it
direct and in-process is what lets the whole sweep be hosted in one Temporal
activity later (D5).
"""

import time
from contextvars import ContextVar
from enum import StrEnum
from typing import TYPE_CHECKING

from polyfactory.exceptions import FactoryException
from pydantic import BaseModel, ValidationError
from typing_extensions import override

from pipelex import log
from pipelex.base_exceptions import PipelexError, iter_cause_chain
from pipelex.cogt.content_generation.content_generator import ContentGenerator
from pipelex.config import get_config
from pipelex.core.exceptions import DryRunFailureErrorData
from pipelex.core.pipes.exceptions import caller_facing_refusal_text
from pipelex.core.pipes.pipe_output import PipeOutput
from pipelex.interpreter_hub import (
    clear_current_library,
    get_current_library,
    get_current_library_id_or_none,
    get_library_manager,
    get_pipe_library,
    scoped_pipe_router,
    set_current_library,
)
from pipelex.libraries.pipe.exceptions import PipeNotFoundError
from pipelex.observer.observer_protocol import ObserverNoOp
from pipelex.pipe_machinery.pipe_abstract import PipeAbstract
from pipelex.pipe_run.exceptions import DryRunError
from pipelex.pipe_run.pipe_job import PipeJob
from pipelex.pipe_run.pipe_router import PipeRouter
from pipelex.pipe_run.pipe_run import PipeRun
from pipelex.pipeline.execution_seams import acquire_library, prepare_pipe_job
from pipelex.pipeline.pipeline_factory import PipelineFactory
from pipelex.runtime_hub import get_telemetry_manager, scoped_content_generator
from pipelex.system.caller_identity import CallerIdentity, scoped_caller_identity
from pipelex.system.configuration.configs import PipelineExecutionConfig
from pipelex.system.pipe_run_mode import PipeRunMode
from pipelex.system.storage_scope import DRY_RUN_STORAGE_SCOPE, DRY_RUN_USER_ID
from pipelex.system.telemetry.events import EventName, EventProperty
from pipelex.tools.typing.pydantic_utils import format_pydantic_validation_error

if TYPE_CHECKING:
    from pipelex.pipe_run.pipe_run_protocol import PipeRunProtocol


class DryRunStatus(StrEnum):
    SUCCESS = "SUCCESS"
    FAILURE = "FAILURE"
    SKIPPED = "SKIPPED"

    @property
    def is_failure(self) -> bool:
        match self:
            case DryRunStatus.FAILURE:
                return True
            case DryRunStatus.SUCCESS | DryRunStatus.SKIPPED:
                return False

    @property
    def is_success(self) -> bool:
        match self:
            case DryRunStatus.SUCCESS:
                return True
            case DryRunStatus.FAILURE | DryRunStatus.SKIPPED:
                return False


class DryRunOutput(BaseModel):
    pipe_code: str
    # Namespaced ``domain.pipe_code`` ref — what ``allowed_to_fail_pipes`` matching keys off, so
    # one allowed code can no longer silently match pipes from multiple domains (closes the
    # bare-code collision the old config carried).
    pipe_ref: str
    status: DryRunStatus
    error_message: str | None = None
    # On a FAILURE, the failure located at the innermost pipe that failed, which is this pipe or one
    # it runs, with a message the disclosure rule allows onto a verdict item.
    failure: DryRunFailureErrorData | None = None


# The foreign shapes a dry run can fail with (pydantic and polyfactory, while mock data is built) carry no
# caller-facing flag, so their item names what failed rather than repeating their text.
_MOCK_DATA_FAILURE_TEXT = "The dry run could not generate mock data for this pipe"


class _FailingPipeRecorder:
    """The pipes that failed during one pipe's dry run, each with the exception it left with."""

    def __init__(self) -> None:
        self._failures: list[tuple[BaseException, PipeAbstract]] = []

    def record(self, *, error: BaseException, pipe: PipeAbstract) -> None:
        """Remember ``pipe`` as where ``error`` happened, unless a pipe it ran already failed with it."""
        if self.find_failing_pipe(error=error) is None:
            self._failures.append((error, pipe))

    def find_failing_pipe(self, *, error: BaseException) -> PipeAbstract | None:
        """The innermost pipe that failed with ``error`` or with an error on its cause or context chain."""
        failing_pipes = {id(recorded_error): pipe for recorded_error, pipe in self._failures}
        seen: set[int] = set()
        stack: list[BaseException] = [error]
        while stack:
            current = stack.pop()
            if id(current) in seen:
                continue
            seen.add(id(current))
            failing_pipe = failing_pipes.get(id(current))
            if failing_pipe is not None:
                return failing_pipe
            for linked in (current.__cause__, current.__context__):
                if linked is not None:
                    stack.append(linked)
        return None


# Scoped to one pipe's dry run by ``BundleValidator._classify_pipe``. A context variable rather than router
# state, so the asyncio tasks a controller's fan-out spawns inherit it, and so concurrent sweeps never mix.
_failing_pipe_recorder: ContextVar[_FailingPipeRecorder | None] = ContextVar("dry_run_failing_pipe_recorder", default=None)


class _DryRunSweepRouter(PipeRouter):
    """The sweep's in-process router: it runs pipes as ``PipeRouter`` does, and notes where each failure happened.

    Every pipe a dry run reaches, the swept pipe and each sub-pipe a controller dispatches, goes through
    this router, so the first pipe a failure leaves is the innermost one that failed. The sweep reports
    the failure there, once, rather than once more for every controller it made fail on its way out.
    """

    @override
    async def run(self, pipe_job: PipeJob) -> PipeOutput:
        try:
            return await super().run(pipe_job)
        except Exception as exc:
            recorder = _failing_pipe_recorder.get()
            if recorder is not None:
                recorder.record(error=exc, pipe=pipe_job.pipe)
            raise


def _dry_run_failure_text(*, error: Exception) -> str:
    """The text a dry-run failure puts on its verdict item: the failure's own message only when it is caller-facing.

    The text is its root fault's, the innermost ``PipelexError`` on the cause chain, since a wrapper
    around it neither knows more nor authors caller-facing copy of its own. A message that is not
    caller-facing is replaced by the fault's title, because the verdict is caller-facing as a whole
    and would otherwise carry a configuration or storage failure's internals past STRICT disclosure.
    """
    root_fault: PipelexError | None = None
    for node in iter_cause_chain(error):
        if not isinstance(node, PipelexError):
            break
        root_fault = node
    if root_fault is None:
        return _MOCK_DATA_FAILURE_TEXT
    return caller_facing_refusal_text(refusal=root_fault)


class BundleValidator:
    """Owns the validation sweep; composes the shared seams + a direct in-process ``PipeRun``."""

    def __init__(self) -> None:
        # Locally-constructed, direct execution primitive — NOT get_pipe_run() (see module docstring).
        # The ObserverNoOp keeps the sweep observation-silent; validation surfaces its own report.
        # Keep the router instance (don't discard it inside PipeRun): the sweep installs it as the active
        # router via scoped_pipe_router (see validate_pipes) so nested controller sub-pipes — which
        # dispatch through get_pipe_router() — resolve THIS in-process router instead of the hub default.
        # Mirrors runtime_bridge.direct_orchestrator.DirectOrchestrator.execute. Being the sweep's own
        # router, it also notes the innermost pipe each failure left (see `_DryRunSweepRouter`).
        self._pipe_router = _DryRunSweepRouter(observer=ObserverNoOp())
        self._pipe_run: PipeRunProtocol = PipeRun(pipe_router=self._pipe_router)

    async def acquire_and_validate(
        self,
        *,
        library_dirs: list[str] | None = None,
        mthds_contents: list[str] | None = None,
        bundle_uris: list[str] | None = None,
        library_id: str = "",
        allow_signatures: bool = False,
        caller_identity: CallerIdentity | None = None,
    ) -> dict[str, DryRunOutput]:
        """Acquire a fresh library, load dirs + contents, sweep **all** loaded pipes, tear down.

        The standalone ``validate --all`` lifecycle (D6): owns acquire + teardown. Always tears
        the acquired library down (unlike ``validate_bundle``'s teardown-on-failure-only), restoring
        the caller's outer current-library first so the guarantee survives a teardown raise.

        Callers that must keep the library loaded after validation (``validate_bundle``, the build
        CLIs) own their library and use :meth:`validate_pipes` instead.
        """
        prev_library_id = get_current_library_id_or_none()
        acquired_id, _ = acquire_library(
            library_id=library_id,
            library_dirs=library_dirs,
            mthds_contents=mthds_contents,
            bundle_uris=bundle_uris,
        )
        try:
            # acquire_library left the freshly-acquired library current, so the inner sweep over the
            # current library targets exactly acquired_id (it filters signatures in strict mode itself).
            return await self.validate_current_library(allow_signatures=allow_signatures, caller_identity=caller_identity)
        finally:
            # Restore the caller's outer current-library FIRST (so the guarantee survives a teardown
            # raise), then tear the acquired library down — mirroring validate_bundle / acquire_library.
            # set_current_library cannot take None, so route the "no outer was set" case through
            # clear_current_library.
            if prev_library_id is not None:
                set_current_library(library_id=prev_library_id)
            else:
                clear_current_library()
            get_library_manager().teardown(library_id=acquired_id)

    async def validate_current_library(
        self, *, allow_signatures: bool = False, caller_identity: CallerIdentity | None = None
    ) -> dict[str, DryRunOutput]:
        """Sweep every pipe in the already-open **current** library, **without** tearing it down.

        The public inner sweep over the active library (D6): the caller owns the library lifecycle —
        this borrows the current library, classifies its pipes, and leaves it loaded. Signature
        filtering is delegated to :meth:`validate_pipes` (the single sweep entry): in strict mode
        signature pipes are excluded from the sweep; in lenient mode they stay (they dry-run trivially
        by minting a mock). This is the loaded-library twin of :meth:`acquire_and_validate` (which
        acquires + tears down) and the shared core both the ``validate --all`` CLI and downstream
        consumers (e.g. cocode) build on instead of re-deriving ``get_pipes`` + ``validate_pipes`` by hand.
        """
        return await self.validate_pipes(
            get_pipe_library().get_pipes(),
            library_id=get_current_library(),
            allow_signatures=allow_signatures,
            caller_identity=caller_identity,
        )

    async def validate_pipes(
        self,
        pipes: list[PipeAbstract],
        *,
        library_id: str,
        allow_signatures: bool = False,
        caller_identity: CallerIdentity | None = None,
    ) -> dict[str, DryRunOutput]:
        """Classify each pipe ``SUCCESS / FAILURE / SKIPPED`` against an already-open library.

        Borrows the caller's open library and **never tears it down** (D6). Order:

        1. ``validate_with_libraries`` wiring pass. A controller referencing an unloaded
           cross-package sub-pipe is recorded SKIPPED and dropped from the remaining steps rather
           than aborting the sweep.
        2. One ``PIPE_DRY_RUN`` telemetry event for the whole sweep.
        3. The per-pipe dry-run sweep, classifying each outcome.
        4. Aggregation: a single ``allowed_to_fail`` match on the namespaced ``pipe_ref`` collecting
           **all** unexpected failures into one ``DryRunError`` (never a per-pipe early abort).

        Signatures are **never an error** (D-B): ``allow_signatures`` is a sweep-mechanics flag, not a
        verdict. In strict mode (``allow_signatures=False``) signature pipes are excluded from the
        sweep up front — not mock-run, absent from the returned status map (and so from
        ``validated_pipes``). In lenient mode they stay and dry-run trivially by minting a mock. Either
        way the unsatisfied set is reported library-wide via ``pending_signatures`` + ``is_runnable``
        by the caller, and the "is this a failure?" decision is the consumer's (the CLI exit-code gate;
        the HTTP caller reading ``is_runnable``). A non-signature pipe that *reaches* a signature
        dry-runs trivially in both modes (the signature mints a mock), so it is never a failure here.

        ``caller_identity`` is who asked for the sweep, when a host knows it (the hosted
        ``/validate`` route does). It is made the ambient caller for the sweep, so the
        ``PIPE_DRY_RUN`` event and every dry run's job metadata are attributed to that caller
        rather than to the telemetry stream's configured fallback. ``None`` inherits whatever
        caller is already in scope, and with none — a local CLI sweep — the dry runs state
        ``DRY_RUN_USER_ID`` and the event goes out under the fallback, as before.

        Returns the per-pipe status map (carrying allowed failures + skips). Raises ``DryRunError``
        on ≥1 unexpected failure.
        """
        with scoped_caller_identity(caller_identity=caller_identity) as effective_caller_identity:
            return await self._validate_pipes_for_caller(
                pipes=pipes,
                library_id=library_id,
                allow_signatures=allow_signatures,
                caller_identity=effective_caller_identity,
            )

    async def _validate_pipes_for_caller(
        self,
        *,
        pipes: list[PipeAbstract],
        library_id: str,
        allow_signatures: bool,
        caller_identity: CallerIdentity | None,
    ) -> dict[str, DryRunOutput]:
        """The body of :meth:`validate_pipes`, run inside the caller's scope."""
        start_time = time.time()

        # allow_signatures is the sweep-mechanics flag (D-B): in strict mode signature pipes are
        # excluded from the sweep entirely (not mock-run, absent from validated_pipes); in lenient
        # mode they stay and dry-run trivially. Filter up front so a signature pipe is dropped from
        # BOTH the wiring check and the dry-run sweep — never raised on, never an error.
        sweep_candidates = pipes if allow_signatures else [pipe for pipe in pipes if not pipe.is_signature]

        # 1. Static library-wiring check. This is *more* than a dry run (the runner's DRY path does
        #    not perform it) — keeping it here preserves coverage and removes the old redundancy where
        #    both `validate --all` and the per-pipe dry run called it. A controller whose branch
        #    references an UNLOADED cross-package sub-pipe (PipeParallel / PipeBatch / PipeCondition
        #    resolve their sub-pipes with an unguarded get_required_pipe) raises PipeNotFoundError here.
        #    Same-package gaps already hard-fail earlier at library load, so the only case reaching this
        #    catch is the intended cross-package one — record it SKIPPED and drop it from the sweep,
        #    matching the old per-pipe dry-run's PipeNotFoundError tolerance instead of aborting the sweep.
        sweepable_pipes: list[PipeAbstract] = []
        results: dict[str, DryRunOutput] = {}
        for pipe in sweep_candidates:
            try:
                pipe.validate_with_libraries()
            except PipeNotFoundError as not_found_error:
                error_message = f"Skipped dry run for pipe '{pipe.pipe_ref}': unresolved dependency: {not_found_error}"
                log.verbose(error_message)
                results[pipe.pipe_ref] = DryRunOutput(
                    pipe_code=pipe.code, pipe_ref=pipe.pipe_ref, status=DryRunStatus.SKIPPED, error_message=error_message
                )
                continue
            sweepable_pipes.append(pipe)

        # 2. One validation telemetry event per sweep (relocated from the CLI's _validate_core).
        #    It has no run to hand over — the sweep is not a run — so it is attributed to the
        #    caller `validate_pipes` put in scope, and to the stream's fallback only when none is.
        get_telemetry_manager().track_event(event_name=EventName.PIPE_DRY_RUN, properties={EventProperty.NB_PIPES: len(sweepable_pipes)})

        # 3. The dry-run sweep. Each pipe is dry-run under a UNIQUE per-sweep pipeline run id (a
        #    `dry_run_`-prefixed uuid, not a constant — self-describing if it ever surfaces in a log).
        #    The DRY leaf emits a synthetic zero-token LLM report; with the live registry gone (usage now
        #    rides on PipeOutput) the sweep accumulates no per-run state on the process-global reporting
        #    manager, so overlapping sweeps (e.g. concurrent `/validate` API requests) cannot collide.
        #    Mock inputs are built by prepare_pipe_job from this DRY + is_mock_inputs config.
        execution_config = get_config().interpreter.pipeline_execution.with_execution_overrides(
            generate_graph=False,
            mock_inputs=True,
        )
        dry_run_pipeline_id = f"dry_run_{PipelineFactory.make_pipeline_run_id()}"
        # Install the in-process router as the active router for the WHOLE sweep so nested controller
        # sub-pipes — which dispatch through get_pipe_router() — resolve THIS router instead of falling
        # back to the hub default. Under a Temporal-enabled hub the default is the Temporal router, so
        # without the scope a controller (a PipeBatch/PipeParallel fan-out, or any PipeSequence step)
        # would leak its nested pipes to Temporal — turning a no-cost in-process dry run into real
        # top-level workflow dispatches (HTTP 422). Mirrors runtime_bridge.direct_orchestrator.DirectOrchestrator.execute. The
        # scope is contextvar-based, so concurrent /validate sweeps don't cross-contaminate, and the
        # asyncio tasks a batch fan-out spawns copy the context at creation (inside this scope) so they
        # inherit the override too.
        # scoped_content_generator: the sweep is always DRY and must stay in-process, so its
        # inference leaves resolve an inline ContentGenerator even under a Temporal-enabled hub
        # (where get_content_generator() is ContentGeneratorInWorkflow) — same rationale as the
        # router scope above. The DRY mock lives at the cogt leaf (Part B), so the inline
        # generator's leaves mock without dispatching and without touching storage.
        with scoped_pipe_router(self._pipe_router), scoped_content_generator(ContentGenerator.make_inline()):
            for pipe in sweepable_pipes:
                results[pipe.pipe_ref] = await self._classify_pipe(
                    pipe=pipe,
                    library_id=library_id,
                    execution_config=execution_config,
                    dry_run_pipeline_id=dry_run_pipeline_id,
                    caller_identity=caller_identity,
                )

        # 4. Aggregate + report.
        return self._aggregate(results=results, start_time=start_time)

    async def _classify_pipe(
        self,
        *,
        pipe: PipeAbstract,
        library_id: str,
        execution_config: PipelineExecutionConfig,
        dry_run_pipeline_id: str,
        caller_identity: CallerIdentity | None,
    ) -> DryRunOutput:
        """Build the mock job and run the pipe DRY through the direct primitive; classify the outcome.

        Wraps **both** the mock-input build (``prepare_pipe_job``) and the run in one try, catching the
        project base ``PipelexError`` (a legitimately broad domain-failure surface — *not* ``Exception``)
        plus pydantic ``ValidationError`` and polyfactory ``FactoryException`` (the third-party shapes a
        ``PipeSignature`` mint can raise). The per-pipe step classifies **only** — no ``allowed_to_fail``
        check and no early raise; those live at the aggregate step.

        The dry run is done for ``caller_identity`` when one is known, so its job metadata states
        that caller — the pipe run opens its caller scope from it — and ``DRY_RUN_USER_ID`` only
        when the sweep belongs to nobody. It stores nothing either way: ``storage_scope`` stays
        ``DRY_RUN_STORAGE_SCOPE``.

        A FAILURE carries its ``failure``, located at the innermost pipe that failed: the sweep's router
        notes where each failure happened, so a controller failing because a pipe it runs failed reports
        that pipe, and ``_aggregate`` keeps the failure once.
        """
        recorder = _FailingPipeRecorder()
        recorder_token = _failing_pipe_recorder.set(recorder)
        try:
            return await self._run_and_classify(
                pipe=pipe,
                library_id=library_id,
                execution_config=execution_config,
                dry_run_pipeline_id=dry_run_pipeline_id,
                caller_identity=caller_identity,
                recorder=recorder,
            )
        finally:
            _failing_pipe_recorder.reset(recorder_token)

    async def _run_and_classify(
        self,
        *,
        pipe: PipeAbstract,
        library_id: str,
        execution_config: PipelineExecutionConfig,
        dry_run_pipeline_id: str,
        caller_identity: CallerIdentity | None,
        recorder: _FailingPipeRecorder,
    ) -> DryRunOutput:
        """The body of :meth:`_classify_pipe`, run while ``recorder`` notes where failures happen."""
        try:
            pipe_job = await prepare_pipe_job(
                pipe=pipe,
                library_id=library_id,
                execution_config=execution_config,
                pipe_run_mode=PipeRunMode.DRY,
                pipeline_run_id=dry_run_pipeline_id,
                user_id=caller_identity.user_id if caller_identity is not None else DRY_RUN_USER_ID,
                extras=caller_identity.extras if caller_identity is not None else None,
                # A dry run provably stores nothing, but `storage_scope` is
                # required — so it says so, loudly and greppably, instead of
                # inheriting a default. A silent default on this field is
                # exactly how the shared `anonymous/` namespace grew: a
                # placeholder never meant to reach storage became the key
                # prefix for every run. If `dry-run-no-storage` ever appears as
                # an S3 prefix, a dry run stored something and that is the bug.
                storage_scope=DRY_RUN_STORAGE_SCOPE,
            )
            await self._pipe_run.run(pipe_job)
        except (PipelexError, ValidationError, FactoryException) as exc:
            # SKIPPED = a cross-package unresolved dependency. Routing through PipeRun.run no longer
            # surfaces a bare PipeNotFoundError: the run layer re-raises the original and the router may
            # wrap it (PipeNotFoundError is a PipelexError, so the base catch reaches it). Walk the whole
            # cause/context chain — testing exc itself first — to reclassify it as SKIPPED.
            if self._root_cause_is(exc=exc, exc_type=PipeNotFoundError):
                error_message = f"Skipped dry run for pipe '{pipe.pipe_ref}': unresolved dependency: {exc}"
                log.verbose(error_message)
                return DryRunOutput(pipe_code=pipe.code, pipe_ref=pipe.pipe_ref, status=DryRunStatus.SKIPPED, error_message=error_message)
            formatted_error = format_pydantic_validation_error(exc) if isinstance(exc, ValidationError) else str(exc)
            error_message = f"Dry run failed for pipe '{pipe.pipe_ref}': {formatted_error}"
            # A failure raised outside any routed pipe run (the mock-input build) is the swept pipe's own.
            failing_pipe = recorder.find_failing_pipe(error=exc) or pipe
            failure = DryRunFailureErrorData(
                pipe_code=failing_pipe.code,
                domain_code=failing_pipe.domain_code,
                source=get_library_manager().get_pipe_source(failing_pipe.pipe_ref),
                message=f"Pipe '{failing_pipe.code}' failed its dry run: {_dry_run_failure_text(error=exc)}",
            )
            return DryRunOutput(
                pipe_code=pipe.code, pipe_ref=pipe.pipe_ref, status=DryRunStatus.FAILURE, error_message=error_message, failure=failure
            )
        log.verbose(f"✅ Pipe '{pipe.pipe_ref}' dry run completed successfully")
        return DryRunOutput(pipe_code=pipe.code, pipe_ref=pipe.pipe_ref, status=DryRunStatus.SUCCESS)

    @classmethod
    def _aggregate(cls, *, results: dict[str, DryRunOutput], start_time: float) -> dict[str, DryRunOutput]:
        """Tally outcomes; raise one ``DryRunError`` listing **every** unexpected failure, else return.

        A single ``allowed_to_fail`` match on the namespaced ``pipe_ref`` (the dict key). Collect-all,
        not first-failure-abort: every non-allowed failure is reported in one error, as one located
        failure per failing pipe (see :meth:`_located_failures`).
        """
        allowed_to_fail_pipes = get_config().inference.dry_run.allowed_to_fail_pipes

        # Only the failed refs feed logic (the allowed_to_fail match); success/skipped counts are
        # log-only, so derive them inline rather than accumulating dead lists.
        success_count = 0
        failed_pipes: list[str] = []
        skipped_count = 0
        for pipe_ref, dry_run_output in results.items():
            match dry_run_output.status:
                case DryRunStatus.SUCCESS:
                    success_count += 1
                case DryRunStatus.FAILURE:
                    failed_pipes.append(pipe_ref)
                case DryRunStatus.SKIPPED:
                    skipped_count += 1

        # The dict key IS the namespaced pipe_ref, so matching on it keys allowed_to_fail off the
        # qualified ref (C-7) rather than the bare code.
        unexpected_failures = {pipe_ref: results[pipe_ref] for pipe_ref in failed_pipes if pipe_ref not in allowed_to_fail_pipes}

        log.verbose(
            f"Dry run completed: {success_count} successful, {len(failed_pipes)} failed, "
            f"{skipped_count} skipped, {len(allowed_to_fail_pipes)} allowed to fail, in {time.time() - start_time:.2f} seconds",
        )
        if unexpected_failures:
            failures = cls._located_failures(unexpected_failures=unexpected_failures)
            details = "\n".join(f"- {failure.message}" for failure in failures)
            msg = f"Dry run failed for {len(failures)} pipe(s):\n{details}"
            raise DryRunError(msg, failures=failures)
        return results

    @classmethod
    def _located_failures(cls, *, unexpected_failures: dict[str, DryRunOutput]) -> list[DryRunFailureErrorData]:
        """One failure per failing pipe, in sweep order.

        Each failure is located at the innermost pipe that failed, so a controller that failed because
        a pipe it runs failed carries that pipe's failure; the failures are then kept once per pipe.
        When a pipe's failure reaches the list both through its own dry run and through a controller's,
        its own is kept, since it names the failure as that pipe met it.
        """
        failures_by_pipe_ref: dict[str, DryRunFailureErrorData] = {}
        for swept_pipe_ref, dry_run_output in unexpected_failures.items():
            failure = dry_run_output.failure or DryRunFailureErrorData(
                pipe_code=dry_run_output.pipe_code,
                message=f"Pipe '{dry_run_output.pipe_code}' failed its dry run",
            )
            failing_pipe_ref = f"{failure.domain_code}.{failure.pipe_code}" if failure.domain_code else swept_pipe_ref
            is_own_failure = failing_pipe_ref == swept_pipe_ref
            if failing_pipe_ref not in failures_by_pipe_ref or is_own_failure:
                failures_by_pipe_ref[failing_pipe_ref] = failure
        return list(failures_by_pipe_ref.values())

    @classmethod
    def _root_cause_is(cls, *, exc: BaseException, exc_type: type[BaseException]) -> bool:
        """Return True if ``exc`` itself, or any link in its ``__cause__`` / ``__context__`` chain, is ``exc_type``.

        Walks both chains (a tree, not a line) with a seen-set guard so a cyclic ``__context__`` cannot
        loop forever.
        """
        seen: set[int] = set()
        stack: list[BaseException] = [exc]
        while stack:
            current = stack.pop()
            if id(current) in seen:
                continue
            seen.add(id(current))
            if isinstance(current, exc_type):
                return True
            for linked in (current.__cause__, current.__context__):
                if linked is not None:
                    stack.append(linked)
        return False
