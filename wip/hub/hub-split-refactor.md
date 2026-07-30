# Splitting `pipelex.hub` into a service hub and a method hub

**Status:** plan, drafted 2026-07-26 against the v0.40.0 base (`dev` at `f23fda7a0`). Nothing implemented. Every number below was measured, and the recipe to reproduce it is in this document — no external tooling required.

Branch off `dev` (e.g. `refactor/Hub-split`), normal PR back to `dev`.

## The problem, in one paragraph

`pipelex/hub.py` is a single god-object that brokers *every* cross-cutting dependency in the codebase — the config, the console, secrets, storage, the class registry, the model deck and inference workers, the plugin registries, and also the concept/domain/pipe libraries, the pipe router, the pipeline manager. Because it is one module, importing it for `get_console()` also imports the entire method-interpretation layer. Measured: `import pipelex.hub` alone loads **323 modules / 26,288 SLOC**, including all of `libraries`, `pipe_operators`, `pipe_controllers`, and `codegen`. Every path from the inference layer to the interpreter runs through it — traced, `pipelex.cogt.content_generation.content_generator` reaches `pipe_controllers`, `libraries`, `pipe_operators`, and `codegen` *only* via `pipelex.hub`, never independently.

Four module-level imports in `hub.py`, all serving type annotations on getters, are the whole cause:

```
from pipelex.libraries.library import Library                        # CONCRETE — drags concept_library, pipe_controllers, and via concept_factory → codegen
from pipelex.libraries.library_manager_abstract import ...           # → core.bundles.pipelex_bundle_blueprint → all twelve pipe blueprints
from pipelex.core.pipes.pipe_abstract import PipeAbstract            # → graph.graph_tracer_manager
from pipelex.core.concepts.concept import Concept                    # the cycle that forces three importlib string-literal hacks
```

## Why this is worth doing

1. **It removes a real import cycle and the three hacks that paper over it.** `core/concepts/concept.py`, `concept_factory.py`, and `structure_generation/generator.py` each carry an identical `importlib.import_module("pipelex.hub")` function with the comment *"Lazy import to break circular dependency with hub.py"*. All three want exactly one symbol: `get_class_registry` — a low-level one. A hub that does not import `Concept` has no cycle with `concept.py`, so all three become plain top-level imports. These hacks are also invisible to every import lint and to pyright's module graph, so they are the worst kind of coupling: real, load-bearing, and unanalyzable.

2. **It makes a layer boundary that already exists become enforceable.** Measured across all 309 files that import the hub: 134 use only low-level symbols, 139 use only high-level ones, and just **36 straddle**. Every package below `core` — `cogt`, `tools`, `system`, `plugins`, `reporting` — uses low-level symbols *exclusively*, today, with zero exceptions. The architecture is already layered; the hub is the one place the layering is not expressible, and therefore the one place it silently rots.

3. **It replaces one god-object with two objects that have genuinely different lifecycles.** The low half is process-scoped: constructed once at boot from config + plugin registration, never changes. The high half is *library-scoped* — it already has contextvar machinery for exactly that (`set_current_library`, `clear_current_library`, `scoped_current_library`). Today those two lifecycles share one container and one setup path, which is why boot interleaves `set_library_manager` between `set_secrets_provider` and `set_models_manager` with no way to tell that the ordering is meaningful.

4. **It cuts import cost for every consumer.** Anything that wants the console, a secret, or the model deck currently pays for the interpreter. That is `pipelex-api`'s health check, the CLI's `--version`, every plugin's registration module, and every test that touches `get_console`.

5. **It reduces the blast radius of changes to the interpreter.** Today a change to a pipe blueprint's module-level imports can perturb the import graph of `cogt`. After the split it structurally cannot.

## Target shape

Delete `pipelex/hub.py`. Create two modules, each with its own container class and its own module-level accessor functions:

**`pipelex/runtime_hub.py`** — process-scoped infrastructure. Config, console, secrets provider + `get_secret`, class registry, func registry, storage provider, telemetry manager + OTel tracer, models manager + model deck, SDK client manager, inference manager + the three worker getters, content generator (+ its scoped override), report delegate, the isolated-execution probe, the dry-run-forced flag, the event-log override, and the plugin registries (`inference_backend`, `model_lister`, `orchestrator`, `bundle_validator`, `storage_provider`, `secrets_provider`).

**`pipelex/interpreter_hub.py`** — library-scoped method machinery. Library manager + `Library`, the domain/concept/pipe libraries and their lookups (`get_required_pipe`, `get_native_concept`, …), the current-library contextvar family (`set_current_library`, `scoped_current_library`, `resolve_library_dirs`, `get_default_library_dirs`), the pipe router (+ scoped override), pipe run, pipeline manager, observer, and the pipe-func executor (+ its registry and scoped override).

`interpreter_hub` imports `runtime_hub`; **`runtime_hub` must never import `interpreter_hub`.** That single arrow is the whole architecture, and it is what the guard checks.

Deleting the `pipelex.hub` name entirely — rather than keeping it as an alias for either half — is deliberate: every stale import then fails loudly at import time instead of silently resolving to the wrong layer. It is also consistent with the no-backward-compatibility principle.

## Decisions to settle before coding

- **D1 — module names.** Recommended: `pipelex/runtime_hub.py` and `pipelex/interpreter_hub.py`, both flat at the package root, `pipelex/hub.py` deleted. Alternatives considered: keeping `pipelex/hub.py` for one half (rejected — a stale import would silently succeed); `library_hub` for the high one (rejected — it also holds the router, the runner, and the pipeline manager); a `pipelex/hubs/` package (workable, but `pipelex.hubs.services` reads worse than `pipelex.runtime_hub` at 300+ call sites). Note for review: `interpreter_hub` borrows MTHDS's noun for a runtime container — acceptable here because the object genuinely holds the loaded method's libraries, but worth a conscious nod given the brand-boundary rule.
- **D2 — one container or two.** Recommended: **two** (`RuntimeHub` and `InterpreterHub`, each its own singleton). One container would have to live in the low module, which forces every high-level slot to a quoted `TYPE_CHECKING` annotation — that keeps the god-object and adds a fig leaf. Two is affordable: `PipelexHub()` is constructed in exactly two production sites (`pipelex/pipelex.py:120`, `pipelex/cli/commands/doctor_cmd.py:774`) and three test sites, and `get_pipelex_hub`/`set_pipelex_hub` appear in five files total.
- **D3 — where `get_pipe_func_executor_registry` lands.** It is a plugin registry (low by kind) whose protocol lives in `pipe_operators/func/` (high by location). Recommended: **high**, with the underlying inversion — `pipelex/plugins/pipe_func_executor_registry.py` importing from `pipe_operators/` — recorded as a follow-up rather than fixed here.
- **D4 — does `core/` join the low layer in this change?** Recommended: **no, not in phase 1.** Five `core/` modules use high-hub symbols (`stuff_factory`, `memory/input_shaper`, `pipes/stuff_spec/stuff_spec_factory`, `pipes/inputs/input_stuff_specs_factory`, `pipes/output/output_renderer`); converting them means passing resolved concepts in rather than looking them up, which is design work, not mechanical. Phase 4 does it; the guard's low-layer set widens to include those modules only when it lands.

## Phases

### Phase 0 — declare the boundary

- [ ] 0.1 Settle D1–D4.
- [ ] 0.2 Take the **baseline measurement** below and record it in this file, so phase 1 has a before to compare against.
- [ ] 0.3 Write `docs/contribute/hub-layering.md` — the two hubs, what lives in each, the one-arrow rule, how the guard enforces it, and how to record an exception. Model it on `docs/contribute/keyword-only-arguments.md`, which is the repo's established shape for a mechanically-enforced convention.
- [ ] 0.4 Update `docs/under-the-hood/architecture-overview.md` to name the boundary (it currently walks `pipe_controllers` → `pipe_operators` → `core` → `cogt` → `plugins` without ever mentioning the hub).

### Phase 1 — the split

- [ ] 1.1 Create `pipelex/runtime_hub.py`: the `RuntimeHub` container + the low accessors. Verify its module-level imports name nothing from `libraries`, `pipe_operators`, `pipe_controllers`, `codegen`, `builder`, `core.bundles`, `core.concepts`, or `core.pipes`.
- [ ] 1.2 Create `pipelex/interpreter_hub.py`: the `InterpreterHub` container + the high accessors, importing `runtime_hub` for anything it needs.
- [ ] 1.3 Delete `pipelex/hub.py`.
- [ ] 1.4 Rewrite the call sites — 309 files, 29 of them with parenthesized multi-line import blocks. Script the rewrite from the symbol→module partition, then hand-review the 36 straddling files, which are the only ones that gain a second import line.
- [ ] 1.5 Re-wire boot: `Pipelex.setup` constructs and populates both hubs; the low one fully before the high one (today the setter calls interleave). Same for `doctor_cmd` and the three test sites.
- [ ] 1.6 Replace the three `importlib.import_module("pipelex.hub")` hacks in `core/concepts/` with plain `from pipelex.runtime_hub import get_class_registry`, and delete the `_get_class_registry` shims.

**CHECKPOINT H-1** — zero behavior change. Gates: `make agent-check` + **full** `make agent-test` (no test rewrites beyond import lines) + `make drift-check`. Expect the **`cli-docs` drift contract to fire** — 45 CLI files import the hub and `pipelex/cli/**/*.py` is a trigger; review `docs/tools/cli/` and `pipelex/cli/agent_cli/CLAUDE.md`, then `make drift-ack`. Re-take the measurement and record the after.

### Phase 2 — enforce it

- [ ] 2.1 Add `pipelex-dev check-hub-layering` (guard in `pipelex/cli/dev_cli/commands/hub_layering_guard.py`, command in `check_hub_layering_cmd.py`), following the `check-keyword-only` precedent exactly. Rule: a module in the declared low layer may not import `pipelex.interpreter_hub`. It must catch the string-literal `importlib.import_module("pipelex.interpreter_hub")` form too — that is precisely how the current cycle hides.
- [ ] 2.2 Declare the low layer: `pipelex/tools/**`, `pipelex/system/**`, `pipelex/cogt/**`, `pipelex/plugins/**`, `pipelex/reporting/**`. All five are 100% compliant today, so the guard hard-blocks from day one with an empty exception list.
- [ ] 2.3 Wire into `make agent-check`, the `make check` aggregate, and CI, with a `chl` alias.
- [ ] 2.4 Unit tests for the guard (positive, negative, and the `importlib` string form), mirroring `tests/unit/pipelex/cli/dev/test_keyword_only_guard_*.py`.
- [ ] 2.5 A closure regression test: import `pipelex.cogt.content_generation.content_generator` in a subprocess and assert no `pipelex.libraries.*`, `pipelex.pipe_operators.*`, `pipelex.pipe_controllers.*`, or `pipelex.codegen.*` module is in `sys.modules`. The lint guards the *rule*; this guards the *property*, which is what actually matters and which a future stray import elsewhere could break without touching a hub import.

**CHECKPOINT H-2** — boundary declared, enforced, and regression-tested.

### Phase 3 — the placement residue

Neither of these is coupling; both are types living in the wrong package, and each is independently correct.

- [ ] 3.1 **`JobMetadata`.** It lives in `pipelex/pipeline/job_metadata.py` but is an argument to essentially every cogt call — it accounts for 17 of the 18 `cogt → pipeline` import statements, and it drags `graph.trace_context` → `graph.graph_config` into every closure that touches inference. Move `job_metadata`, and decide whether `trace_context` moves with it or stops depending on `graph_config`. Also move `JobMetadataError` out of `pipeline/exceptions.py` (the sole remaining `cogt → pipeline` edge, in `llm_worker_abstract.py`).
- [ ] 3.2 **`cogt.templating.*`.** `TemplateCategory`, `TemplatingStyle`, `TextFormat`, and `TagStyle` are imported by eight `tools/jinja2/` and `tools/mermaid/` modules — they are templating primitives sitting under `cogt/`, making `tools` (the intended bottom layer) depend on `cogt`. Decide: move them down to `tools`, or accept `cogt` as below `tools` and document that.

**CHECKPOINT H-3** — placement residue resolved or explicitly deferred with a recorded rationale.

### Phase 4 — `core/` joins the low layer

- [ ] 4.1 Convert the five `core/` straddlers to take resolved concepts/pipes as arguments instead of reaching for `get_concept_library` / `get_native_concept` / `get_required_concept` / `get_required_pipe`. Callers that have a library pass the resolved value; callers that do not are, by construction, in the high layer already.
- [ ] 4.2 Widen the guard's low layer to include `pipelex/core/**`.

**CHECKPOINT H-4 = done** — update `docs/contribute/hub-layering.md` with the final layer set, and the CHANGELOG with a breaking-change note (`pipelex.hub` is gone; importers must choose `pipelex.runtime_hub` or `pipelex.interpreter_hub`).

## Exit criteria — measured, not asserted

The headline property is that the inference layer must stop importing the interpreter. Measure it directly, from the repo root on a synced venv:

```bash
.venv/bin/python - <<'PY'
import sys
from pathlib import Path

import pipelex.cogt.content_generation.content_generator  # noqa: F401

INTERPRETER = {"libraries", "pipe_operators", "pipe_controllers", "codegen", "builder"}
loaded = {name: mod for name, mod in sys.modules.items() if name.startswith("pipelex.")}
interpreter = sorted(n for n in loaded if n.split(".")[1] in INTERPRETER)
sloc = 0
for mod in loaded.values():
    file = getattr(mod, "__file__", None)
    if file:
        sloc += sum(1 for line in Path(file).read_text(encoding="utf-8").splitlines() if line.strip() and not line.strip().startswith("#"))
print(f"pipelex modules: {len(loaded)} | sloc: {sloc} | interpreter modules: {len(interpreter)}")
print("offenders:", interpreter)
PY
```

| | today | target after phase 1 |
| --- | --- | --- |
| interpreter modules loaded | 50 | **0** |
| pipelex modules loaded | 357 | ≤ 260 |
| SLOC loaded | 29,193 | ≤ 19,000 |

The module/SLOC targets come from importing exactly the types a low-only hub would annotate — 236 modules / 17,683 SLOC, with the interpreter subpackages at zero — plus headroom for cogt's own modules. If phase 1 lands and `interpreter modules` is not 0, the snippet prints the offenders: something imports the interpreter outside the hub, and the shortest import path to it is what to fix. Swap the imported module in the snippet to measure any other entry point (`pipelex.pipelex`, `pipelex.runtime_hub`, …).

## Risks and containment

- **Big mechanical diff (309 files).** Contained by: the rewrite is scriptable from a symbol→module table; `pipelex.hub` ceasing to exist means any missed site is an import error, not a silent wrong-layer resolution; and the full `make agent-test` suite is the zero-behavior-change bar.
- **Two singletons, two lifecycles, two teardowns.** Contained by the tiny construction surface (five sites total). Watch `Pipelex.teardown` / `teardown_if_needed` and the test fixtures that reset hub state — a half-reset hub between tests is the realistic failure mode, and it shows up as cross-test pollution rather than a clean failure. Worth an explicit "both hubs reset" assertion in the shared fixture.
- **Cross-repo breakage.** `pipelex.hub` is imported by our plugins and by consumers of the runtime. Grep `pipelex-api/`, `pipelex-worker/`, our orchestrator plugins, and `pipelex-mistralai-workflows/` before merging, and stage the follow-ups as a release-gated sweep. `scoped_pipe_router` / `set_pipe_router` / `teardown_current_pipe_router` are documented as depended upon by our Mistral Workflows plugin, so their new home is a published contract change.
- **`plugins/` reaching up.** `plugins/pipe_func/pipe_func_plugin.py` and `plugins/pipe_func_executor_registry.py` import from `pipe_operators/`, and `plugins/direct/direct_plugin.py` from `pipeline/`. These do not import the hub, so the guard will not flag them — but they mean "plugins is a low layer" is not yet unconditionally true. Named here so the claim in the docs stays honest; fixing them is out of scope.

## Explicitly out of scope

- **A general layering ratchet** ("no low module may import any high module", with an allowlist). The measured inversion set is real but larger than this change should carry — `tools → cogt` (15 statements), `cogt → core` (21), `system → cogt` (8), `plugins → runtime_bridge` (6), and one genuine wart, `cogt/model_backends/model_lists.py` importing `pipelex.cli.exceptions.PipelexCLIError`. Phase 3 removes the two biggest clusters; the general rule is a sequel worth considering once they are gone.
- **Eager optional-SDK imports.** `pipelex/tracing/event_log_factory.py` imports `dynamodb_event_log` at module level, which runs a module-level `try: import boto3`, so `boto3`/`botocore`/`jmespath`/`dateutil`/`six` load in every process that touches the tracing factory — including runs that will never touch DynamoDB. A three-line fix (import `DynamoDBEventLog` inside the factory branch, the pattern already used for `pypdfium2` in `cogt/content_generation/render_generate.py`), entirely independent of this plan. Note that most other heavy roots (`posthog`, `pypdfium2`, `pillow`, `polyfactory`, `datamodel-code-generator`) are **base** dependencies, not extras — so they are not the same kind of finding.
