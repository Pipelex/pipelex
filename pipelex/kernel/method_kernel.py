"""The kernel façade: per-run state, so a caller does not thread it through every call.

The semantics live in the module-level ops functions beside this one; the interpreter's operator
classes call those directly, because they already hold everything the façade would supply. This
class exists for the *other* caller — the programmatic one, embedding the runtime — and it holds
exactly two things, both of them run-scoped identity:

- ``job_metadata`` — the **run-level** metadata. It is not what a step runs under: each call mints
  a per-step copy via :meth:`make_step_metadata`, mirroring the interpreter's pass-down-a-modified-copy
  pattern, so trace and usage attribution stay per-step.
- ``cogt_run_params`` — the execution-mode contract (``run_mode``, ``is_mock_usage``) every cogt
  leaf reads off the assignment it is handed.

What it deliberately does **not** hold is anything derived from config or the model deck — resolved
LLM settings, prompting style. Those are computed per call and never cached here, exactly as
``pipe_llm.py`` derives them per run today: cached derived state is hidden shared state, it makes a
later config or deck change invisible to a live kernel, and it breaks per-call variation.
"""

from typing import Self
from uuid import uuid4

from pipelex.cogt.content_generation.cogt_run_params import CogtRunParams
from pipelex.system.job_metadata import JobMetadata
from pipelex.system.pipe_run_mode import PipeRunMode


class MethodKernel:
    """Façade over the module-level kernel ops; holds per-run state."""

    def __init__(self, *, job_metadata: JobMetadata, cogt_run_params: CogtRunParams) -> None:
        self.job_metadata = job_metadata
        self.cogt_run_params = cogt_run_params

    @classmethod
    def make(cls, *, run_mode: PipeRunMode = PipeRunMode.LIVE, user_id: str) -> Self:
        """Mint a kernel for one run: a fresh run id, and the execution-mode contract for it."""
        return cls(
            job_metadata=JobMetadata(user_id=user_id, pipeline_run_id=str(uuid4())),
            cogt_run_params=CogtRunParams(run_mode=run_mode),
        )

    def make_step_metadata(self) -> JobMetadata:
        """A per-step copy of the run-level metadata, carrying its own ``pipe_run_id``.

        ``otel_context`` is passed explicitly as ``None`` rather than left to inherit, which is the
        contract ``copy_with_update`` states: the field is computed fresh per step by whoever opens
        the span, and a kernel call opens none. Span and trace-context wiring for a kernel-driven
        run is a separate concern from minting the identity, and is not wired here.
        """
        return self.job_metadata.copy_with_update(otel_context=None, pipe_run_id=str(uuid4()))
