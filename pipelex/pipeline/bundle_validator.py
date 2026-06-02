"""The batch validation service (D1) — the explicit home for the validation sweep.

A validation sweep is **not** a run: it is a batch *policy* that *uses* runs. So
``BundleValidator`` owns the sweep semantics (signature pre-pass, the
``validate_with_libraries`` wiring check, the per-pipe tolerant
``SUCCESS / FAILURE / SKIPPED`` aggregation, ``allowed_to_fail`` policy) and
**composes** the shared execution seams (``acquire_library`` /
``prepare_pipe_job``) plus a direct, in-process ``PipeRun`` — the same execution
core ``PipelexRunner`` reaches for a single run. It never forks the runner and
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
from typing import TYPE_CHECKING

from polyfactory.exceptions import FactoryException
from pydantic import BaseModel, ValidationError

from pipelex import log
from pipelex.base_exceptions import PipelexError
from pipelex.config import get_config
from pipelex.core.pipes.pipe_abstract import PipeAbstract
from pipelex.hub import (
    clear_current_library,
    get_current_library_id_or_none,
    get_library_manager,
    get_pipe_library,
    get_report_delegate,
    get_telemetry_manager,
    set_current_library,
)
from pipelex.libraries.pipe.exceptions import PipeNotFoundError
from pipelex.observer.observer_protocol import ObserverNoOp
from pipelex.pipe_run.exceptions import DryRunError
from pipelex.pipe_run.pipe_router import PipeRouter
from pipelex.pipe_run.pipe_run import PipeRun
from pipelex.pipe_run.pipe_run_mode import PipeRunMode
from pipelex.pipe_signature.exceptions import SignaturesNotAllowedError
from pipelex.pipe_signature.signature_walk import collect_signature_paths, collect_signature_refs
from pipelex.pipeline.execution_seams import acquire_library, prepare_pipe_job
from pipelex.pipeline.pipeline_models import SpecialPipelineId
from pipelex.system.configuration.configs import PipelineExecutionConfig
from pipelex.system.telemetry.events import EventName, EventProperty
from pipelex.system.telemetry.otel_constants import OTelConstants
from pipelex.tools.typing.pydantic_utils import format_pydantic_validation_error
from pipelex.types import StrEnum

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


class BundleValidator:
    """Owns the validation sweep; composes the shared seams + a direct in-process ``PipeRun``."""

    def __init__(self) -> None:
        # Locally-constructed, direct execution primitive — NOT get_pipe_run() (see module docstring).
        # The ObserverNoOp keeps the sweep observation-silent; validation surfaces its own report.
        self._pipe_run: PipeRunProtocol = PipeRun(pipe_router=PipeRouter(observer=ObserverNoOp()))

    async def acquire_and_validate(
        self,
        *,
        library_dirs: list[str] | None = None,
        mthds_contents: list[str] | None = None,
        bundle_uris: list[str] | None = None,
        library_id: str = "",
        allow_signatures: bool = False,
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
            all_pipes = get_pipe_library().get_pipes()
            # In strict mode, signatures themselves are excluded (validating one directly would always
            # trip the pre-check); in lenient mode they stay (they dry-run trivially by minting a mock).
            pipes = all_pipes if allow_signatures else [pipe for pipe in all_pipes if not pipe.is_signature]
            return await self.validate_pipes(pipes, library_id=acquired_id, allow_signatures=allow_signatures)
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

    async def validate_pipes(
        self,
        pipes: list[PipeAbstract],
        *,
        library_id: str,
        allow_signatures: bool = False,
    ) -> dict[str, DryRunOutput]:
        """Classify each pipe ``SUCCESS / FAILURE / SKIPPED`` against an already-open library.

        Borrows the caller's open library and **never tears it down** (D6). Order (D7):

        1. ``validate_with_libraries`` wiring pass (before the signature pre-pass, preserving
           today's error precedence — a wiring error surfaces ahead of a signature error). A
           controller referencing an unloaded cross-package sub-pipe is recorded SKIPPED and dropped
           from the remaining steps rather than aborting the sweep.
        2. Aggregated signature pre-pass (strict mode): one ``SignaturesNotAllowedError`` listing
           every reached signature, never short-circuiting on the first.
        3. One ``PIPE_DRY_RUN`` telemetry event for the whole sweep.
        4. The per-pipe dry-run sweep, classifying each outcome.
        5. Aggregation: a single ``allowed_to_fail`` match on the namespaced ``pipe_ref`` collecting
           **all** unexpected failures into one ``DryRunError`` (never a per-pipe early abort).

        Returns the per-pipe status map (carrying allowed failures + skips). Raises
        ``SignaturesNotAllowedError`` (strict mode) or ``DryRunError`` (≥1 unexpected failure).
        """
        start_time = time.time()

        # 1. Static library-wiring check. This is *more* than a dry run (the runner's DRY path does
        #    not perform it) — keeping it here preserves coverage and removes the old redundancy where
        #    both `validate --all` and the per-pipe dry run called it. A controller whose branch
        #    references an UNLOADED cross-package sub-pipe (PipeParallel / PipeBatch / PipeCondition
        #    resolve their sub-pipes with an unguarded get_required_pipe) raises PipeNotFoundError here.
        #    Same-package gaps already hard-fail earlier at library load, so the only case reaching this
        #    catch is the intended cross-package one — record it SKIPPED and drop it from BOTH the
        #    signature pre-pass and the sweep, matching the old per-pipe dry-run's PipeNotFoundError
        #    tolerance instead of aborting the whole sweep (preserves the D7 wiring-before-signature order).
        sweepable_pipes: list[PipeAbstract] = []
        results: dict[str, DryRunOutput] = {}
        for pipe in pipes:
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

        # 2. Aggregated signature pre-pass (strict mode only).
        if not allow_signatures:
            self._signature_pre_pass(pipes=sweepable_pipes)

        # 3. One validation telemetry event per sweep (relocated from the CLI's _validate_core).
        get_telemetry_manager().track_event(event_name=EventName.PIPE_DRY_RUN, properties={EventProperty.NB_PIPES: len(sweepable_pipes)})

        # 4. The dry-run sweep. The DRY leaf emits a synthetic zero-token LLM report, so open ONE
        #    report registry for the whole sweep and close it in `finally`: the registry is keyed by
        #    the constant DRY_RUN_UNTITLED id, which would collide ("already exists") on a second sweep
        #    if left open. Mock inputs are built by prepare_pipe_job from this DRY + is_mock_inputs config.
        execution_config = get_config().pipelex.pipeline_execution_config.with_graph_config_overrides(
            generate_graph=False,
            mock_inputs=True,
        )
        get_report_delegate().open_registry(pipeline_run_id=SpecialPipelineId.DRY_RUN_UNTITLED)
        try:
            for pipe in sweepable_pipes:
                results[pipe.pipe_ref] = await self._classify_pipe(pipe=pipe, library_id=library_id, execution_config=execution_config)
        finally:
            get_report_delegate().close_registry(pipeline_run_id=SpecialPipelineId.DRY_RUN_UNTITLED)

        # 5. Aggregate + report.
        return self._aggregate(results=results, start_time=start_time)

    @classmethod
    def _signature_pre_pass(cls, pipes: list[PipeAbstract]) -> None:
        """Walk the selected pipes; raise one aggregated ``SignaturesNotAllowedError`` if any reached.

        Aggregates across all pipes so the user sees every offender (and the longest, most informative
        dep chain per signature) in a single error, rather than only the first one to fail.
        """
        all_signature_refs: set[str] = set()
        all_dep_paths: dict[str, list[str]] = {}
        offending_pipe_refs: set[str] = set()
        for pipe in pipes:
            sig_refs = collect_signature_refs(pipe=pipe)
            if not sig_refs:
                continue
            # A signature is the placeholder itself, not an offender that "depends on" one.
            if not pipe.is_signature:
                offending_pipe_refs.add(pipe.pipe_ref)
            all_signature_refs.update(sig_refs)
            for sig_ref, path in collect_signature_paths(pipe=pipe).items():
                # Prefer the longest known dep chain so the error shows the most informative path
                # (a chain rooted at a controller beats an empty chain rooted at the signature itself).
                existing = all_dep_paths.get(sig_ref)
                if existing is None or len(path) > len(existing):
                    all_dep_paths[sig_ref] = path
        if all_signature_refs:
            raise SignaturesNotAllowedError(
                offending_pipe_refs=offending_pipe_refs,
                signature_refs=all_signature_refs,
                dep_paths=all_dep_paths,
            )

    async def _classify_pipe(self, *, pipe: PipeAbstract, library_id: str, execution_config: PipelineExecutionConfig) -> DryRunOutput:
        """Build the mock job and run the pipe DRY through the direct primitive; classify the outcome.

        Wraps **both** the mock-input build (``prepare_pipe_job``) and the run in one try, catching the
        project base ``PipelexError`` (a legitimately broad domain-failure surface — *not* ``Exception``)
        plus pydantic ``ValidationError`` and polyfactory ``FactoryException`` (the third-party shapes a
        ``PipeSignature`` mint can raise). The per-pipe step classifies **only** — no ``allowed_to_fail``
        check and no early raise; those live at the aggregate step.
        """
        try:
            pipe_job = await prepare_pipe_job(
                pipe=pipe,
                library_id=library_id,
                execution_config=execution_config,
                pipe_run_mode=PipeRunMode.DRY,
                pipeline_run_id=SpecialPipelineId.DRY_RUN_UNTITLED,
                user_id=OTelConstants.DEFAULT_USER_ID,
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
            return DryRunOutput(pipe_code=pipe.code, pipe_ref=pipe.pipe_ref, status=DryRunStatus.FAILURE, error_message=error_message)
        log.verbose(f"✅ Pipe '{pipe.pipe_ref}' dry run completed successfully")
        return DryRunOutput(pipe_code=pipe.code, pipe_ref=pipe.pipe_ref, status=DryRunStatus.SUCCESS)

    @classmethod
    def _aggregate(cls, *, results: dict[str, DryRunOutput], start_time: float) -> dict[str, DryRunOutput]:
        """Tally outcomes; raise one ``DryRunError`` listing **every** unexpected failure, else return.

        A single ``allowed_to_fail`` match on the namespaced ``pipe_ref`` (the dict key). Collect-all,
        not first-failure-abort: every non-allowed failure is reported in one error.
        """
        allowed_to_fail_pipes = get_config().pipelex.dry_run_config.allowed_to_fail_pipes

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
            details = "\n".join(f"'{pipe_ref}': {results[pipe_ref]}" for pipe_ref in unexpected_failures)
            msg = f"Dry run failed with {len(unexpected_failures)} unexpected pipe failure(s):\n{details}"
            raise DryRunError(msg)
        return results

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
