# Deferred design tradeoffs from the Checkpoint D cold review

Findings from the Checkpoint D cold review that are deliberate scoping choices or efficiency polish, not silent bugs. Each entry records the finding, why it is deferred, and what would trigger picking it up. (Correctness findings from the same review were fixed in the checkpoint follow-up commit: the lifted `add_each_output` companion-slot gap, the guard-walker false negatives/positives, the leaking `Jinja2DetectVariablesError`, the PipeSearch/PipeImgGen lint coverage, the prose-in-`variable_names`, and the duplicated taint bookkeeping.)

## 1. `liftable_pipes` only covers pipes in the validated bundle

`build_liftable_pipes` iterates `result.pipes` — the pipes loaded from the validated bundle batch. A cross-package dependency controller (resolved through the hub during a taint walk) is not itself iterated, so ITS liftable branches don't appear as separate entries.

**Why deferred:** whether the valid report should enumerate internals of *other* packages is a real design question — the inventory is keyed to the bundle under validation, and a dependency package's flows are its own validate's concern. The D3 commitment ("every liftable pipe is visible at build time") is satisfied within the bundle; cross-package visibility overlaps with how the protocol wants to scope reports per package.

**Pick up when:** the Step E/F protocol work formalizes `liftable_pipes` on the wire — decide the scoping there (per-bundle vs per-closure) and document it in the spec either way.

## 2. Taint analyses recomputed per validate pass

A controller's taint analysis can run up to three times during one validation: its own `validate_output_with_library`, an enclosing sequence's `analyze_taint` (branch-taint sub-analysis), and `build_liftable_pipes`. Similarly, PipeLLM templates are Jinja2-parsed twice in `validate_inputs_static` (variable detection + guard-lint).

**Why deferred:** validation-time only, small ASTs/flows, no measured pain. Memoizing per-pipe analyses or sharing a parsed AST adds state/invalidation complexity to save milliseconds at author time.

**Pick up when:** validation latency on large libraries becomes a measurable complaint (profile first).

## 3. `_build_full_path` duplicated between jinja2 walkers

`jinja2_optional_guards._build_full_path` mirrors the private helper in `jinja2_required_variables`. Sharing means exporting a private helper or minting a tiny common module.

**Why deferred:** the helper is small and stable; a cross-module private import or a one-function module is more structure than the duplication costs today.

**Pick up when:** a third walker needs it, or either copy needs a behavior change (then unify first).

## 4. Guard shapes deliberately not recognized

The guard walker recognizes `{% if var %}` bodies (including `and`-combos with short-circuit awareness), `is defined` tests, and CondExpr true-arms. Still linted as unguarded, though runtime-safe in principle:

- inverted guards: `{% if not var %}fallback{% else %}{{ var.attr }}{% endif %}` (the else-arm of a negative presence test);
- the false-arm of a negated inline conditional: `{{ 'x' if not var else var.attr }}`.

**Why deferred:** the walker is documented as deliberately narrow — a conservative lint with a precise fix message beats a clever one; the positive-guard rewrite is always available and arguably clearer.

**Pick up when:** real bundles hit these shapes and the rewrite is genuinely awkward (collect examples first).
