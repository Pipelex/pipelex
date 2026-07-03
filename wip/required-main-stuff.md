# Required main stuff — PipeParallel always combines

**Branch:** `feature/Required-main-stuff` · **Status:** Phases 1–2 COMPLETE (Checkpoint 2 cleared — invariant enforced at every in-repo post-run boundary: wire `main_stuff_name` required, delivery always writes `main_stuff.*`, defensive branches gone, `final_stuff_code` honored on the parallel's combined stuff; decisions & audit in `TODOS.md` → Checkpoint log). Next: Phase 3 (cross-repo sweep, GATED on merge to `main` + version cut).

## 1. Problem

A pipeline is the language's function abstraction, and every pipe already declares `output` in its blueprint — yet the runtime sometimes finishes a run without delivering a main stuff. The result is that `main_stuff` is optional everywhere, and every consumer pays for it with defensive code. The symptom that triggered this design: `pipelex-starter-python/my_project/run_output.py` needs a page of isinstance-walking heuristics just to read a pipeline's result.

### Verified mechanics (current state)

- Every operator (`PipeLLM`, `PipeCompose`, `PipeExtract`, `PipeImgGen`, `PipeSearch`, `PipeStructure`, `PipeFunc`, `PipeSignature`) unconditionally stamps its result via `WorkingMemory.set_new_main_stuff`.
- Among controllers: `PipeSequence` threads one evolving memory so the last step's stamp wins; `PipeBatch` stamps its aggregated `ListContent`; `PipeCondition` delegates to the chosen branch, which stamps.
- The **only** non-stamping path in the runtime is `PipeParallel` without `combined_output` (`pipe_parallel.py` — the `set_new_main_stuff` call sits inside `if self.combined_output`). The blueprint validator explicitly allows `add_each_output = true` alone, so this is a legal terminal step.
- `pipe_abstract.py` acknowledges the hole in a comment: *"main_stuff may not exist for pipes like PipeParallel with add_each_output=true"*.

### The three concrete failure modes

1. **Stale main stuff (silent wrong data).** Inside a `PipeSequence`, the parallel adds branch outputs by name into the shared memory but never touches the `main_stuff` alias. A pipeline ending in an `add_each`-only parallel silently reports the *previous* step's output (or even an input — `make_from_single_stuff` / `make_from_multiple_stuffs` alias an input as main stuff at construction) as its main result.
2. **Truly missing main stuff.** When such a parallel is the top-level `main_pipe` and memory came from `make_from_pipeline_inputs` (the API path — which sets no main-stuff alias), the run completes with no main stuff at all: `main_stuff_name` serializes as `None`, `PipeOutput.main_stuff` raises.
3. **Empty delivery envelope.** On the `/start` → delivery path, delivery always writes `working_memory.json`, but the `main_stuff.json/md/html/viewer` artifacts are only generated when a main stuff exists. An `add_each`-terminal method started via `POST /v1/start` completes "successfully" and `GET /v1/runs/{pipeline_run_id}/results` relays `main_stuff: null` — consumers are left digging through the raw `working_memory` render (which the SDKs don't even name — see below).

### Blast radius of the optionality

Defensive `get_optional_main_stuff` branches exist in the CLI pretty-printer, the CLI file/CSV writers, the agent CLI, OTel telemetry, the graph tracer, and the delivery executor. On the wire, `main_stuff_name: str | None` (bridge payloads, `PipelexRunResultExecute`), `RunResults.main_stuff: Any = None` in both SDKs, and downstream user projects re-implement the same heuristics.

### Related but out of scope

The starter's `run_output.py` ugliness has a second, independent cause: the **result-shape divergence** between the two execution surfaces. Both carry the same information, including the working memory — delivery writes a full artifact folder (`working_memory.json`, `main_stuff.{json,md,html}`, `main_stuff_viewer.html`, `graphspec.json`, mermaid/reactflow views) and `GET /v1/runs/{pipeline_run_id}/results` relays `main_stuff` + `graph_spec` + `working_memory` as flat fields — but the shapes differ on three axes:

- **Envelope**: `/execute` nests everything under `pipe_output`; `/results` returns flat top-level fields.
- **Main-stuff addressing**: `/results` pre-extracts the main stuff's *content* into `main_stuff`; on `/execute` the caller follows the `main_stuff_name` pointer into `working_memory.root` and unwraps `.content`.
- **Memory encoding**: `/execute` returns the `dump_for_transport()` shape (`__pipelex_class__` metadata, `ListContent` flattened — built for rehydration, not reading); delivery writes a clean `smart_dump()` render — except on the cross-process Temporal path, where it writes the raw transport dump it received (`working_memory_raw`), so even the delivered `working_memory.json` is not one stable shape today.

On top of that, the SDKs only *name* `main_stuff`, `graph_spec`, and `pipe_output` on their `RunResults`; the relayed `working_memory` rides along as an unnamed `extra="allow"` field. This refactor removes the optionality and the heuristic root-walk; unifying the shapes is a companion API/SDK change tracked separately (see §9, cross-repo follow-ups).

## 2. The decision

> **A pipe run always delivers a main stuff. Consequently, a pipeline always delivers a main stuff.**

This is enforced at the leaf cause, not the pipeline boundary: `PipeParallel` — the single non-stamping pipe — now **always combines its branch outputs into its declared `output` concept and stamps the combination as main stuff**. Composition (sequences, conditions, nesting) then gives the pipeline-level invariant for free, and the stale-stamp hazard disappears because the parallel always overwrites the alias.

`combined_output` **is deleted as a field**. It was redundant with `output`: in our own fixtures, pipes declare `output = "PgcCombinedResult"` and `combined_output = "PgcCombinedResult"` — the same value twice. Meanwhile `add_each`-only parallels declare an `output` that is a lie (e.g. `output = "Text"` for a pipe that produces named summaries). Killing the field makes `output` truthful and unique.

No backward compatibility, per house policy. Breaking changes are noted in the changelog; existing `.mthds` files migrate.

## 3. New PipeParallel semantics

### Field changes

| Field | Before | After |
|---|---|---|
| `output` | Required but meaningless when only `add_each_output` is set | Required and truthful: the concept the branch outputs are combined into |
| `combined_output` | Optional concept ref; triggers combination when set | **Deleted** |
| `add_each_output` | One of the two must be set (model validator) | Unchanged meaning ("also expose branch outputs by name in memory"), default `false`, no more one-of-two validator |
| `branches` | Each branch must declare a unique `result` name | Unchanged |

### Runtime behavior (live and dry run identically)

1. Run all branches on deep copies of the memory, as today.
2. If `add_each_output`, add each branch's main stuff into the parent memory under its `result` name, as today.
3. **Always** build the combination: `{result_name: branch_main_stuff.content}` → validate into the declared `output` concept's structure class via `StuffFactory.combine_stuffs` → `set_new_main_stuff(stuff=combined, name=output_name)`. This is today's `combined_output` code path made unconditional, with the concept taken from `output`.
4. Graph tracer registration (branch outputs, parallel-combine edges) as today, except the combine edges are now always registered.

### Typing rules for the declared `output`

- **Structured concept** (bespoke, with a structure class): the combination validates into it — today's typed `combined_output` path, unchanged. The structure's fields must correspond to the branch `result` names.
- **`native.Composite`** (new native concept, see §4): the untyped escape hatch — a named composition holding the branch contents as-is, the `dict[str, Any]`-shaped developer experience for authors who don't want to declare a bespoke concept.
- **Anything else is a static validation error**: native non-composite concepts (`Text`, `Image`, …), `Dynamic`, `Anything`, and any multiplicity suffix (`Foo[]`, `Foo[N]`) are rejected — a parallel combination is a named composite, never a scalar or a bare list (a list aggregation is `PipeBatch`'s shape).

### New static validation (bundle/library validation time)

- The declared `output` of a `PipeParallel` must be `Composite` or a structured concept whose declared fields are compatible with the branch `result` names (required fields ⊆ result names; result names ⊆ declared fields). This turns today's runtime `StuffFactoryError` from `combine_stuffs` into an author-time error, which the builder and `/validate` can surface.
- The one-of-two (`add_each_output` / `combined_output`) validators in both the blueprint and the spec are removed.

### Example migration

Before (`add_each`-only, lying output):

```toml
[pipe.parallel_summarize]
type = "PipeParallel"
description = "Generate short and detailed summaries in parallel"
inputs = { input_text = "Text" }
output = "Text"                     # never produced — a lie
add_each_output = true
branches = [
  { pipe = "summarize_short", result = "short_summary" },
  { pipe = "summarize_detailed", result = "detailed_summary" },
]
```

After (untyped composite — minimal migration):

```toml
[pipe.parallel_summarize]
type = "PipeParallel"
description = "Generate short and detailed summaries in parallel"
inputs = { input_text = "Text" }
output = "Composite"                # truthful: named composition of the branch results
add_each_output = true              # still exposes short_summary / detailed_summary by name
branches = [
  { pipe = "summarize_short", result = "short_summary" },
  { pipe = "summarize_detailed", result = "detailed_summary" },
]
```

Before (combined, redundant declaration):

```toml
output          = "PgcCombinedResult"
add_each_output = true
combined_output = "PgcCombinedResult"
```

After — delete the `combined_output` line; nothing else changes.

## 4. The `Composite` native concept

The untyped fallback needs a real vehicle. Verified: `DynamicContent` cannot serve as-is — `StuffContent`/`CustomBaseModel` use default pydantic config, so `model_validate({"short_summary": ..., ...})` silently *drops* unknown fields. Silent data loss is disqualifying; overloading `Dynamic` (whose meaning is "concept resolved at runtime", used by `PipeFunc`) would also blur two distinct semantics.

Proposal: add `COMPOSITE = "Composite"` to `NativeConceptCode` with a `CompositeContent(StuffContent)` structure class that holds the named branch contents as top-level fields (pydantic `extra="allow"` so the branch names surface at the top level of the serialized content, exactly like the typed path — not nested under a wrapper key). It must support the full content surface: `smart_dump`, kajson round-trip (`dump_for_transport` / rehydration), `rendered_markdown`/`rendered_html` (iterate named sub-contents), so `main_stuff.json/md/html/viewer` delivery works unchanged.

Brand note: this is MTHDS-language semantics, not a Pipelex runtime detail. The concept is `native.Composite` (no `pipelex_` anything), and the change belongs in the MTHDS spec (`mthds/` repo) in the same motion as killing `combined_output`.

Alternatives considered for the vehicle:

- `DynamicContent` with `extra="allow"` — rejected: `Dynamic` already means something else, and changing its config affects unrelated `PipeFunc` paths.
- `CompositeContent` with an explicit `composed: dict[str, StuffContent]` field — rejected: nests the payload under a wrapper key, so the wire shape of the untyped path would differ from the typed path.
- Runtime-synthesized anonymous pydantic model per parallel — rejected: the class wouldn't exist in the class registry on the other side of a process boundary, breaking rehydration.

## 5. What the invariant unlocks (follow-through tightening)

Once every pipe stamps, "a completed run has a main stuff" is guaranteed, and the following tighten from defensive to direct (in-repo):

- Graph tracer output-spec branch in `pipe_abstract.py` (and its apologetic comment).
- Delivery executor: always writes the `main_stuff.*` artifact files for completed runs.
- CLI run cores (bare + agent): drop the "no main output produced" branches for live runs.
- OTel telemetry attribute extraction.
- `resolve_main_stuff_root_key` / bridge payloads / `PipelexRunResultExecute.main_stuff_name`: producer-side always set; the field types can go non-optional (Temporal payload history is not a concern — never shipped to prod).

`WorkingMemory.get_optional_main_stuff` itself stays — a *pre-run* or empty memory legitimately has no main stuff; it's the post-run boundary accessors that tighten.

Cross-repo (flagged, not done here): SDKs can drop `main_stuff`-absent handling for completed runs, and the starter's `find_main_content` shrinks; full cleanup of the two-branch shape additionally needs the `/execute`-vs-`/start`→delivery result-shape unification (companion track).

## 6. Rejected alternatives (for the record)

- **Auto-stamp at the pipeline boundary** ("if no main stuff at the end, synthesize one"): papers over the stale-stamp bug inside sequences and needs an ill-defined generic aggregation rule. Fixing the one non-stamping pipe is strictly better.
- **Validation-error-only** ("a terminal pipe must deliver; force authors to add `combined_output` or a final step"): position-dependent validity (valid as sub-pipe, invalid as `main_pipe`) is confusing, and it makes casual fan-out methods annoying to author.
- **Raw `dict[str, Any]` main stuff with no concept**: escapes the concept system entirely — no rendering, no typed access, no static checks. The `Composite` concept gives the same developer experience while staying a first-class stuff.
- **Keep `combined_output` optional, defaulting to `output`**: keeps a redundant field alive with subtle precedence rules; deleting it is simpler and the migration is mechanical.
- **SDK-only ergonomics fix**: treats the symptom; every consumer stays defensive; the empty-delivery hole remains.

## 7. Open questions (resolve during implementation)

- **`final_stuff_code`**: the parallel currently clears it on entry (with a copy-pasted `PipeBatch` log line). Now that the parallel stamps a final stuff, it should presumably honor `final_stuff_code` on the combined stuff like operators do. Confirm what `final_stuff_code` drives (graph/trace identity) and wire it through.
- **Graph `execution_data` key `combined_output_concept`**: under the new semantics it is always set and equals the declared output concept. Keep the key name for `mthds-ui` compatibility in phase 1; consider renaming in the next coordinated `mthds-ui` bump.
- **`add_each_output` naming**: semantics unchanged, but with combination always on, a name like `expose_branches` might read better. Recommendation: keep the name — pure churn across skills/docs otherwise. Revisit only if the MTHDS spec editors want it.
- **`PipeOutputAbstract` (mthds-python protocol layer)**: check whether the protocol shape encodes main-stuff optionality that should tighten in the same motion (cross-repo).

## 8. Implementation plan

### Phase 1 — runtime + language surface (this repo)

- `pipe_parallel.py`: unconditional combine in `_live_run_controller_pipe` and `_dry_run_controller_pipe` (shared helper — the existing TODO already asks for it); concept from `self.output`; always register parallel-combine graph edges.
- `pipe_parallel_blueprint.py` / `pipe_parallel_factory.py`: delete `combined_output` + one-of-two validator; factory stops resolving the combined concept separately.
- `builder/pipe/pipe_parallel_spec.py`: delete `combined_output` + validators; `to_blueprint()` simplifies; update pretty-render; `builder/operations/pipe_ops.py` + `cli/agent_cli/commands/pipe_cmd.py` display code.
- `core/bundles/pipelex_bundle_blueprint.py`: drop the `combined_output` concept-ref collection; add the new static structure-compatibility check (§3).
- New native concept `Composite` + `CompositeContent` (§4): `concept_native.py`, new `composite_content.py`, class registry, concept factory.
- Tests (TDD: write the red tests first): regression test for the stale-stamp bug (sequence ending in `add_each`-only parallel must deliver the composite, not the previous step's stuff); terminal-parallel-delivers-main-stuff; static validation accept/reject cases; `CompositeContent` serialization + rendering round-trip; dry-run parity. Migrate existing fixtures (`pipe_parallel_1.mthds`, `parallel_graph_*.mthds`, unit/builder test data, mermaidflow test, bundle-validator + agent-validate tests).
- Regenerate the MTHDS JSON Schema (`pipelex-dev generate-mthds-schema`).
- Docs: rewrite `docs/building-methods/pipes/pipe-controllers/PipeParallel.md` to the new semantics (current reality only, no history); changelog entry under `[Unreleased]`, marked breaking.
- Gates: `make agent-check`, targeted pipes tests, then full `make agent-test`.

**CHECKPOINT 1** — parallel always combines; `combined_output` gone; all gates green. Update this doc: status, decisions taken, deviations. Natural handoff point before touching the delivery/telemetry surfaces.

### Phase 2 — enforce the invariant across in-repo surfaces

- Tighten the boundary consumers listed in §5 (graph tracer, delivery executor, CLI run cores, OTel, serialization payload types → `main_stuff_name: str`).
- Keep `WorkingMemory.get_optional_main_stuff` for pre-run memories; audit each remaining call site and either justify or tighten.
- Resolve the `final_stuff_code` open question.
- Gates: full `make agent-test`.

**CHECKPOINT 2** — invariant enforced in-repo; doc updated with the final call-site audit results. Cross-repo work starts fresh from here.

### Phase 3 — cross-repo sweep (gated, coordinate releases)

Do not start before phases 1–2 are merged and a pipelex version is cut.

| Repo | Change |
|---|---|
| `mthds/` | Spec: `mthds-format.md`, `pipes-controllers.md`, `validation-rules.md`, `namespace-resolution.md`, `cross-package-references.md`, `docs/mthds_schema.json` — remove `combined_output`, define always-combine + `native.Composite` |
| `vscode-pipelex/` | Pinned `mthds_schema.json` in taplo-common (plxt lint/format must accept the new shape and reject `combined_output`) |
| `conformance/` | `tests/pipelex/test_validate_subcommands.py` fixture updates; keep spec ↔ test links (`make check-spec-links`) |
| `mthds-plugins/` | Skills references: `mthds-reference.md`, `build-phases.md`, `recursive-cheat-sheet.md`, `mthds-run/SKILL.md` across plugin variants |
| `pipelex-app/` | `src/types/core/pipes/pipe_controllers/pipe-parallel.ts` |
| `mthds-ui/` | `src/graph/types.ts` (`combined_output_concept` exec-data key — see open question); graph-spec data fixtures |
| `cocode/` | `ai_instruction_update.mthds`, `swe_docs.mthds` migration |
| `pipelex-website/` | `docs/mthds-doc.md` |
| demo/workshop repos | `illustration_generator/bundle.mthds` copies |
| SDKs + starter | Tighten `main_stuff` handling for completed runs; pair with the result-shape unification companion track |

**CHECKPOINT 3** — cross-repo consumers aligned; close this doc or fold residual items into follow-up trackers.

## 9. Companion track (separate design)

Result-shape unification between `/execute` and `/start` → delivery. Both surfaces already carry the same information, working memory included; what differs is the envelope, the main-stuff addressing, and the memory encoding (see §1). Converge on one shape: e.g. `/execute` also pre-extracts `main_stuff` at top level, one canonical working-memory render on both surfaces (the transport dump stays an internal format), and the SDKs naming `working_memory` on the results surface instead of leaving it an unnamed extra. This is what deletes the *second* half of the starter's `find_main_content`. Belongs to `pipelex-api` / `pipelex-platform` / SDK repos; design separately once the invariant lands.
