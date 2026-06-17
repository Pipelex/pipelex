# Suspects — package `pipe_controllers`

Reviewed: 6 Section A + 3 primitive lone-subjects. Suspects: 3.

## High confidence

- `pipelex/pipe_controllers/parallel/pipe_parallel.py:326` — `PipeParallel._register_branch_outputs_with_graph_tracer` — `def _register_branch_outputs_with_graph_tracer(self, job_metadata: JobMetadata, *, output_stuffs: dict[str, 'Stuff']) -> None` — `job_metadata` is a trace-context carrier / lookup key, not the semantic object of the function; the function acts on `output_stuffs`. All call sites (lines 210 and 309) already pass `job_metadata=job_metadata` by keyword. Suggested fix: make fully keyword-only — `def _register_branch_outputs_with_graph_tracer(self, *, job_metadata: JobMetadata, output_stuffs: dict[str, 'Stuff']) -> None`.

- `pipelex/pipe_controllers/parallel/pipe_parallel.py:369` — `PipeParallel._register_parallel_combine_with_graph_tracer` — `def _register_parallel_combine_with_graph_tracer(self, job_metadata: JobMetadata, *, combined_stuff: 'Stuff', branch_stuffs: dict[str, 'Stuff']) -> None` — same pattern: `job_metadata` is a context/trace carrier; the function acts on `combined_stuff` and `branch_stuffs`. Both call sites (lines 203 and 302) use `job_metadata=job_metadata`. Suggested fix: move `*` before `job_metadata` — `def _register_parallel_combine_with_graph_tracer(self, *, job_metadata: JobMetadata, combined_stuff: 'Stuff', branch_stuffs: dict[str, 'Stuff']) -> None`.

- `pipelex/pipe_controllers/sub_pipe.py:34` — `SubPipe.run_pipe` — `async def run_pipe(self, calling_pipe_code: str, *, working_memory: WorkingMemory, job_metadata: JobMetadata, sub_pipe_run_params: PipeRunParams, library_crate: 'LibraryCrate | None'=None) -> PipeOutput` — `calling_pipe_code` is caller provenance/context, not the semantic object; `self` (the SubPipe) is the object being run. Both real call sites (pipe_parallel.py:152, pipe_sequence.py:195, pipe_condition.py:328) already pass `calling_pipe_code=self.code` by keyword. Suggested fix: make fully keyword-only — `async def run_pipe(self, *, calling_pipe_code: str, working_memory: WorkingMemory, job_metadata: JobMetadata, sub_pipe_run_params: PipeRunParams, library_crate: 'LibraryCrate | None'=None) -> PipeOutput`.

## Medium / low confidence

- `pipelex/pipe_controllers/pipe_controller.py:71` — `PipeController._live_run_controller_pipe` — `async def _live_run_controller_pipe(self, job_metadata: JobMetadata, *, ...)` — `job_metadata` as positional follows the same `_live_run_pipe(self, job_metadata, *, ...)` convention established on `PipeAbstract` (the base class). The single call site (pipe_controller.py:43) already uses keyword form. Medium confidence only because the `job_metadata`-as-first-non-self-param is a deliberate, codebase-wide convention on the run-pipe family; changing only the controller abstract without changing the base class `PipeAbstract` would create inconsistency. If the base family ever moves `job_metadata` to keyword-only, this should follow.

- `pipelex/pipe_controllers/pipe_controller.py:83` — `PipeController._dry_run_controller_pipe` — same reasoning as `_live_run_controller_pipe` above; treat as a pair.
