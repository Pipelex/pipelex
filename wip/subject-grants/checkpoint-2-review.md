# CHECKPOINT 2 review — subject-grants Phase 4 (batches 1–7)

Cold no-context `/code-review` fan-out over `9f5bd54a3..227b98822` (checkpoint-1 tip → batch-7 tip). Four fresh Sonnet sub-agents, each handed only the commit range and neutral factual framing (never the plan or my conclusions), split by lens:

- **Code correctness — core/pipe_operators/pipe_controllers/pipe_signature** (41 files, ~140 signature/call-site changes)
- **Code correctness — rest of packages** (builder, cli, graph, kit, libraries, pipe_run, pipeline, reporting, runtime_bridge, system, tools, tracing, errors)
- **Registry rationale consistency** (`subject_grants.toml`: 634 SEEDED→KEEP rewrites, 94 demote deletions)
- **Test-change integrity** (6 changed test files)

Gates green throughout: `make agent-check` (pyright 0/0/0, mypy clean, `cko` passed) and full `make agent-test` both before and after the fixes below.

## Fixes applied (real defects — folded into the checkpoint-2 fix commit)

Both are the same class of latent bug this project exists to kill: an **interface more permissive than its implementations** — a positional-or-keyword signature on a Protocol/ABC whose concrete implementers were already demoted to keyword-only. Type-checker-blind (a caller typed against the interface can call positionally and crash against a real instance), and both had every actual call site already passing the arg by keyword, so nothing broke today — pure time-bombs.

1. **`TextFormatRenderable.rendered_for_template_async` incomplete spillover sweep.** Batch 7 demoted `text_format` to keyword-only on the two implementers (`StuffContent`, `StuffArtefact`) but left the `@runtime_checkable` Protocol (`pipelex/tools/jinja2/text_format_renderable.py`) positional — because `pipelex/tools/` is a not-yet-reviewed batch (grant still `seeded`). This is the exact sibling of the `ImageRenderable`/`render_with_images` case the **same batch** swept correctly. Also independently justified by case-law: `text_format` is a mode/format param (the rubric's DEMOTE list already names `rendered_for_prompt(text_format)`). Fix: `*` inserted on the Protocol method, seeded grant deleted. Completes batch 7's own intent.

2. **`ConceptLibraryAbstract.is_compatible` mis-classified keep.** Kept with rationale "Predicate subject: the concept under test." But signature is `is_compatible(self, tested_concept: Concept, *, wanted_concept: Concept, strict: bool = False)` — two same-type `Concept` operands, the rubric's near-symmetric-pair DEMOTE shape (fails the "single candidate" prong, structurally `copy_file(source, target)`). All 10 call sites already keyword `tested_concept=`, so the "self-labelling positional call" premise the grant rested on is empirically false. Fix: `tested_concept` moved after `*` on **both** the abstract and the `@override` concrete (`ConceptLibrary.is_compatible`) for interface/impl parity; grant deleted. Zero call-site changes (all already keyword).

## Deferred / noted (NOT applied — tradeoffs or out of scope)

- **`GatewayConfigMerger.merge` (`gateway_model_specs`) — low-confidence registry note, KEPT.** Same-type pair (`BackendModelSpecs`/`BackendModelSpecs`) like `is_compatible`, but the naming is defensibly asymmetric: `local_overrides` self-labels as the modifier applied on top, `gateway_model_specs` reads as the base being merged into — closer to `dict.update(other)` than to true symmetry. The registry reviewer explicitly flagged it "for awareness rather than recommending a hard demotion" (one call site, low confidence). Rationale reads as a clean verb-object ("merges the gateway model specs; merge context stays keyword"). **Left as-is; Louis spot-check on the registry diff.** If demoting, it's a one-line `*` move + grant delete + the single call site (`backend_library.py:253`) already keywords both.

- **Twin-function rubric inconsistency — action item for the `cli` batch.** `builder/operations/pipe_ops.py::add_type_specific_fields` was fully demoted (both `pipe_spec` and `pipe_table` keyword-only); its private near-duplicate `cli/agent_cli/commands/pipe_cmd.py::_add_type_specific_fields` still has `pipe_spec` positional (seeded — the `cli` batch isn't reviewed yet). Not a bug now (each is called only from its own file with matching keywords). **When grinding the `cli` batch, demote the cli twin to match** so the two structurally-identical functions don't diverge.

- **Pre-existing dead code — out of scope, flagged for separate triage.** The rest-packages reviewer noted `builder/operations/validate_ops.py::validate_all` and `graph/graph_tracer.py::GraphTracer.add_selected_outcome_edge` have no callers within `pipelex/`. Unrelated to subject-grants. Caveat: `validate_all` is on the demoted-public-surfaces list (agent-CLI/MCP plumbing, importable) — likely an **external** entry point, not truly dead; the grep only covered `pipelex/`. Verify before any removal; do not fold into this project.

- **`PipeCondition._evaluate_expression(working_memory)` demoted rather than granted.** A reviewer flagged this as a plausible verb-object candidate that could have been kept. Considered and left demoted: `working_memory` reads as an instrumental/context param (the rubric's instrumental-param DEMOTE pattern, e.g. `_evaluate_expression(working_memory)` is already in the case-law), not the direct object of "evaluate expression." No action — the demotion is correct.

## Verdict

The seeded-review grind is holding up: across ~140 code changes and 634 kept rationales, two genuine interface/impl inconsistencies and one borderline rationale. No mechanical breakage, no weakened tests, no framework-positional regressions. The two fixes remove the only real defects; the rest is on the record for the remaining batches and Louis' registry spot-check.
