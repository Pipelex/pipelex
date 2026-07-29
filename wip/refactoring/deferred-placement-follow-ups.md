# Deferred placement follow-ups

Findings from the M1 checkpoint review round that are **placement or naming accuracy, not silent bugs**. Nothing here is broken, nothing here breaches the layer boundary, and no gate is failing because of any of it. Each is recorded rather than fixed because the fix is a rename-and-rewrite wave whose churn is not justified by the defect, and because two of the three are better folded into a later modularity commit than done alone.

## 1. `mthds_parsing/` holds three modules that are not parsing

The package is named for what most of it does, but three tenants do something else:

- **`pipe_sorter.py`** — its only production caller is `pipelex/builder/bundle_spec.py`, the builder's *specs → blueprint* direction. The parser never sorts. It arrived here because it lived in `core/bundles/`, which M1a hoisted wholesale.
- **`helpers.py`** — mixes two unrelated things. `MTHDS_EXTENSION` and `is_pipelex_file` are a generic file-extension predicate imported across `cli/`, `libraries/` and `builder/`; the rest is parse-error scoping used only inside this package. The generic half has no business behind a parser-named import path.
- **`handle_pipe_errors.py`** — the M1b changelog says it followed "its importers" into `mthds_parsing`, which is half true: one of its two importers is `pipeline/validate_bundle.py`.

**Why deferred.** None of this is a layering problem — all three are leaves or interpreter-layer consumers, so the closure test and the guard are both indifferent. Fixing it well means splitting the generic extension predicate out (a good candidate for `core/` or `tools/`, touching every one of its importers) and finding `pipe_sorter` a home nearer the builder. That is a coherent commit of its own, not a review-fix.

**Worth noting for contrast:** `pipe_machinery/` was checked module by module in the same review and is accurately named throughout, `validation.py` and `template_guard_lint.py` included.

## 2. Parser test fixtures stayed under `tests/unit/pipelex/core/`

`tests/unit/pipelex/core/test_data/` holds the parser's fixture corpus — `interpreter_test_cases.py` exporting `InterpreterTestCases`, plus the `complex/`, `concepts/`, `domain/`, `errors/`, `pipes/` subtrees. Its consumers are now `tests/unit/pipelex/mthds_parsing/test_parser.py` and `tests/integration/pipelex/language/test_mthds_factory.py`; nothing under `tests/unit/pipelex/core/` uses it any more.

It resolves fine — this is filing, not breakage. Moving it means rewriting the nested `from tests.unit.pipelex.core.test_data.…` imports throughout the subtree and renaming `interpreter_test_cases` / `InterpreterTestCases` to match the `MthdsParser` rename, which is exactly the kind of churn that should ride along with the next commit that touches those tests rather than land on its own.

## 3. The `pipeline` / `pipe_run` leak is now referenced from four places

`core.pipes.pipe_output` reaches `pipeline.pipeline_models` for a single leaf constant, and `runtime_hub` reaches `pipe_run.pipe_run_mode`. Because of that, neither package can be named in the closure test's `INTERPRETER_PACKAGES` — naming them would fail every entry point on a placement wart rather than on a broken hub arrow.

The M1 review round found that the *statement* of the property had quietly dropped this qualification in three places (the guard's `RUNTIME_LAYER_PACKAGES` note, and two spots in `hub-layering.md`), which is fixed. The underlying wart is not, and the qualification now has to be repeated wherever the property is stated: `runtime_hub`'s docstring, the guard note, `hub-layering.md` "Why the boundary exists", and `hub-layering.md` "Where core splits".

**The remedy is known and is the one `mthds_parsing` already used** (D-M1-8): move the leaf models to a runtime-layer home, *then* widen the predicate. `SpecialPipelineId` and `PipeRunMode` are the two leaves. Doing it would let all four qualifications collapse back to the unqualified claim — which is the real argument for doing it, since a caveat repeated in four places is a caveat that will go stale in at least one.

See also `wip/pr-1062-review-notes.md`, where this leak was first recorded.
