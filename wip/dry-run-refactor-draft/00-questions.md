> **Historical origin of the audit.** These are the three questions that kicked off the investigation. All three answers still hold today (see `C-synthesis.md` / `A-taxonomy.md`): `DryPipeRouter` is still dead code, the taxonomy is unchanged, the load profile is still light. One thing to note for context: the audit's *motivation* — a dry-run regression in `validate_bundle` — has since been closed by the signature-validation feature. Kept verbatim as the record of what was originally asked.

# Open questions from user

## Q1 — Is DryPipeRouter useless?
User's claim: dry-run dispatch happens at the pipe level (`PipeAbstract._run_pipe_traced`
match on `pipe_run_params.run_mode`). So a router that calls `pipe.dry_run_pipe()`
instead of `pipe.run_pipe()` adds nothing — the regular router would route to the
same dry path via the in-pipe match.

Need to verify: is `pipe.run_pipe()` the one that does the match, and does it call
`dry_run_pipe` itself when mode==DRY? If yes, DryPipeRouter is dead code.

## Q2 — Taxonomy of PipeRouter / PipeRun / WfPipeRouter / WfPipeRun
User is lost. Need a clean map:
- What is each class
- Who calls whom
- What's the swap mechanism in `Pipelex.make()` / hub when `is_temporal_enabled=True`
- Is there a way to inject DIFFERENT runners for different cases (e.g. dry-run
  stays local even when temporal is on)?

## Q3 — CPU/memory load of a dry-run in FastAPI
The use case: a FastAPI endpoint receives thousands of concurrent dry-run requests
(different workflows, different users). Question: is dry-run heavy enough that we'd
need to push it through Temporal too, or is it light enough to stay in-process in
the API?

Need to characterize:
- What does dry-run actually DO computationally
  - Parses MTHDS bundle (CPU)
  - Builds blueprints / Pydantic models (CPU + allocation)
  - Loads concept classes (CPU + import side-effects?)
  - Mocks inputs (cheap)
  - Walks the pipe graph (recursion, async coroutines)
  - At leaves: ContentGeneratorDry (returns canned text — cheap, no network)
  - Validates Jinja2 templates (CPU)
- What it does NOT do
  - LLM calls (no)
  - HTTP / external API (no, modulo ContentGeneratorDry behavior — verify)
  - File I/O for storage (no — unless DeliveryExecutor is on)
- Is it bound by:
  - Single-thread CPU? (Python GIL — yes if pure-Python computation)
  - Event loop blocking? (any sync CPU work blocks the loop)
  - Memory? (Pydantic model graphs can be heavy — bundle size matters)
  - File system? (bundle loading from disk)

## Plan
- Dispatch Agent A → Q1 + Q2 (taxonomy + DryPipeRouter verification)
- Dispatch Agent B → Q3 (load characterization)
- Synthesize findings into a recommendation
