# Who consumes normalized-crate output

**Status.** Inventoried 2026-08-11 for Phase 1 of [implementation-plan.md](implementation-plan.md). The plan asks for this before the Phase 2 rule flip, because the flip changes what a normalized in-body ref *says*: a bare `present_as_markdown` that today normalizes to the sibling domain's `presentation.present_as_markdown` will normalize to the owner's `orchestrator.present_as_markdown`. Anything that persists, stamps, or compares that output moves with it.

## The headline: nothing writes a normalized crate back to `.mthds`

This was the plan's stated worry — "if formatting persists a qualified ref into a user's source file, the flip rewrites their code, not just its in-memory form". It does not happen. No code path encodes a crate into `.mthds` and writes it over a source file. The crate encoder is used for stdout only (`pipelex resolve`); the codegen projections consume a normalized crate but encode a **lock**, not a crate.

The one command that *does* rewrite user `.mthds` files is `pipelex fix`, and it does not go through a crate at all: `fix_loop` edits a tomlkit DOM of the user's own file, applying ops planned from validation-error data. Two properties keep it clear of this change:

- The ops that write a ref (`SET_KEY` into `["pipe", <code>, "inputs"]`) write **concept** refs, which are already qualified at build time today and are unaffected by Phase 2.
- **No fix op writes an *in-body* pipe ref.** `RENAME_TABLE_KEY` renames a pipe's own table key; nothing sets a `steps[].pipe`, a branch, an outcome, or a `branch_pipe_code`. One fix op *does* write a pipe ref, and it is worth naming rather than glossing: `strip-namespace` plans a root `SET_KEY` of `main_pipe`. That is an **entry-point** ref, not an in-body one, and it *strips* a same-domain prefix rather than adding one — so it cannot rewrite an author's bare in-body spelling into a qualified one, which is the hazard this section is actually about. (`planner.py`'s `_plan_strip_namespace` says so in its own docstring: only the declaration key and `main_pipe` are ever stripped, because internal refs keep resolving without a rewrite.)

That second property is load-bearing and worth restating in Phase 2: it holds today, and a new fix kind that writes a pipe ref would newly rewrite an author's bare spelling into a qualified one. It is a property to re-check, not an invariant to assume.

## The consumers

Three entry points call `normalize_crate`; everything else is downstream of them.

| Call site | What it feeds | What the flip does to it |
| --- | --- | --- |
| `pipelex/cli/commands/crate_loading.py` → `load_normalized_crate` | `pipelex resolve` (encodes to stdout), the `pipelex codegen` family (`types`, `inputs`), and their agent-CLI twins | `resolve` prints qualified refs where the author wrote bare — already true today for concept refs and for cross-domain pipe refs; the flip changes *which* domain a bare pipe ref prints as |
| `pipelex/pipeline/resolve_bundle.py` → `resolve_crate_from_contents` | the `/resolve` API route and the agent-CLI resolve path | same, over the wire |
| `pipelex/cli/commands/build/runner/_runner_core.py` | `emit_types` → `write_stamped_projection` into `structures/` | the stamp is the concern, see below |

## The stamped artifacts are the thing that actually churns

`write_stamped_projection` records `crate_fingerprint` (the normalized, D2-scope digest) into `codegen.lock` beside the emitted `structures.py`. Qualification is part of the hashed content, so **every** stamped projection in the repo and in downstream repos gets a new fingerprint the moment the rule flips — even for a library whose emitted Python is byte-identical, because the digest covers pipes and domains, not just the concepts the types projection reads.

Practical consequence for Phase 2: expect lock-file churn wherever a stamped projection is committed, and regenerate rather than hand-edit. This is also the mechanism by which the flip reaches `pipelex-cookbook` and any starter repo carrying a committed `codegen.lock`.

## What the corpus says about all this

Measured while proving the Phase 1 extraction behavior-identical: applying the Phase 2 rule to all 54 crates buildable from this repo's `.mthds` files changes **nothing** — every normalized output is byte-identical under both rules. Every bare in-body pipe ref in this repo already resolves within its own domain.

That is a useful de-risking result for the *repo's* artifacts, and simultaneously the sharpest possible argument for the plan's two-domain fixture requirement: a test suite grounded in this corpus cannot tell the two rules apart, so it would pass just as happily under the rule being deleted. The discriminating cases have to be built by hand.
