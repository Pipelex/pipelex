# Inputs track — roadmap and reading guide

This folder holds the design work for the **Smart Inputs** feature and its two prerequisite native-concept tracks. **Start here on a cold session.**

## Current state (2026-07-07)

Branch `feature/Smart-inputs` (worktree `_smart`), tip `420c8269c`, **23 commits ahead of `origin/dev`**, based on main at v0.38.0 (includes TOML inputs #1022 + Optionals phase 1 #1021). The branch now carries **both** native-concept prerequisites:

- **`YesNo` native concept — ✅ DONE & landed.** PR **#1028** (`feature/Smart-inputs` → `dev`) is still **OPEN**. Its title still reads "Add native YesNo concept" but the branch now also carries Date (see below) — retitle/redescribe #1028 before merging it to `dev`, or it will misrepresent the diff. As-built: `yesno-implementation-plan.md`.
- **`Date` native concept — ✅ DONE & landed.** PR **#1029** (`feature/native-date` → `feature/Smart-inputs`) is **MERGED** into this branch. Went through two bot-review rounds + a gstack `/review` finalize (which fixed a stale CLI test and added coverage). As-built: `datetime-implementation-plan.md`.

Both concepts ship together in the one release wave. `feature/Smart-inputs` is the accumulation branch for the whole track.

## What remains: the Smart Inputs system itself

The two native concepts were prerequisites. The **actual Smart Inputs feature** — signature-driven input shaping, decisions **D1–D11** — is not started. Its design is **fully approved** (`smart-inputs-design.md`); no design decisions are open.

### Next session's job: write `smart-inputs-implementation-plan.md`, then execute it

Write a phased implementation plan that **mirrors the two precedent plan docs** (`yesno-implementation-plan.md`, `datetime-implementation-plan.md`): a cold-start code map, verified mechanism facts (re-checked against current code — line numbers have shifted since those plans were written), checkbox phases, per-checkpoint state lines, and a micro-decisions log. Then execute it (the /goal loop worked well for YesNo and Date). If a genuine design gap surfaces, raise it — do **not** relitigate D1–D11.

### Cold-start facts for writing that plan

Reference symbols, not line numbers (they shift; re-grep each before citing):

- **The signature-blind chokepoint.** `StuffFactory.make_stuff_from_stuff_content_or_data` (`pipelex/core/stuffs/stuff_factory.py`) shapes each input value bottom-up from its *shape alone*, with no view of the declared concept. Today: a bare string silently becomes `native.Text` (there is no runtime concept check — `validate_before_run` is presence-only); a bare number / dict / list-of-dicts / empty list hard-errors. Smart Inputs makes this **top-down**: interpret each value against the pipe's declared `InputStuffSpecs`.
- **The seam that must carry the signature down.** `prepare_pipe_job` (`pipelex/pipeline/execution_seams.py`) holds `pipe.inputs` but never passes it to the factory. The existing entrypoint to hook is `WorkingMemoryFactory.make_from_pipeline_inputs` (`pipelex/core/memory/working_memory_factory.py`) — D7 adds `make_from_pipeline_inputs(input_specs=...)` and shapes against `pipe.inputs` (the boundary contract, **not** `needed_inputs()`).
- **The new module.** D7 puts the shaper in a new `pipelex/core/.../input_shaper.py` (`InputShaper`). It does not exist yet — it's the deliverable.
- **The core mechanism = the D5 interpretation matrix.** Dispatch on the *declared concept's nature* (Text / Number / YesNo / Date / Image·Document file-ish / structured / list). Guardrails already decided: bool is excluded from the Number arm (Python `bool ⊑ int` trap); a bare string is a URL/path for Image/Document-refining concepts (D3); auto-wrap single→list + element-wise shaping + empty lists legal, `[N]` count-checked (D2); failure = a hard typed error rendering the expected template (D4, no bottom-up fallback).
- **Explicit forms (D6).** The envelope form `{concept, content}` (exactly those two keys) and other explicit forms are **compat-checked** against the declaration; explicit wins when compatible. YesNo and Date already added their envelope arms to `stuff_factory.py` case 2 — Smart Inputs generalizes this.
- **D8 typo detector.** Unknown input names become errors — the *only* place Smart Inputs narrows existing behavior (everything else widens).
- **D10 protocol widening is release-gated.** Admitting bare scalars (number/bool/date) into `mthds/protocol/pipeline_inputs.py`'s `StuffContentOrData` lives in the external `mthds` package and rides the downstream release wave, like Optionals ([[project-optionals-design]] precedent). Core-scope Smart Inputs shapes *before* that seam where it can.
- **Design source of truth:** `smart-inputs-design.md` — problem, shape-at-a-glance, D1–D11 with rationale, non-goals, and **§9 "Surfaces impacted (checklist for the future plan)"** — start the plan's phase breakdown from §9.

### Deferred notes the Smart Inputs plan should triage

Several gaps were deferred *specifically* to be resolved when Smart Inputs unifies the input paths — fold them into the plan:

- `scalar-envelope-arm-asymmetry.md` — Case 2 bool-arm preserves the refining subclass, str-arm flattens to Text; revisit when the shaper generalizes envelope handling.
- `loader-vs-factory-date-split-duplication.md` — the date/datetime split written in both the loader and the factory; the shared shaper is where to unify it.
- `case1-bare-date-arm-gap.md` — a top-level array of date literals errors instead of building `ListContent[DateContent]`; ties to D2 (multiplicity) + D10 (protocol widening for scalar sequences).
- `container-default-temporal-codegen-gap.md`, `structure-field-fidelity-guard.md` — structure-field-codegen tradeoffs surfaced by the Date `/review`; not Smart-Inputs-specific but worth a decision when temporal handling is next touched.
- `refines-hint-native-list-drift.md` — a spec-layer authoring hint list omits newer natives; real fix = derive it from `NativeConceptCode` in the release-wave sweep.

## Then: one release cut, one downstream cross-repo wave

Schema sync (`mthds-schema-sync` skill), MTHDS spec native-concept tables, `mthds-js`/`mthds-python` mirrors (incl. the D10 protocol widening), conformance rows, skills, editor completion lists — all shared across YesNo + Date + Smart Inputs, done **per-release, not per-feature**. YesNo's MTHDS spec rows are drafted on the sibling `mthds` repo branch `feature/native-yes-no-concept` (not pushed); Date's spec rows still to draft.

Follow-ups off the critical path: the shared **YesNo/Date LLM-output ergonomics** (a leaner scalar-native generation form, cousin of the Optionals maybe-wrapper); LLM-assisted input adaptation (design doc §8).

## Documents

**Design (source of truth for decisions):**

- `smart-inputs-design.md` — the approved Smart Inputs design: problem, shape at a glance, decisions D1–D11 (D9 = the YesNo spin-off, D10 = protocol widening, D11 = template `--explicit` flag), non-goals, §9 surfaces checklist. **Read this before writing the plan.**
- `datetime-design.md` — the approved Date-track design: one native `Date` concept (date + optional time, fidelity-first timezone policy), DT1–DT8.

**Implementation plans / as-built records:**

- `yesno-implementation-plan.md` — YesNo phased plan + as-built (all phases done, landed). **A template for the Smart Inputs plan.**
- `datetime-implementation-plan.md` — Date phased plan + as-built, incl. the bot rounds and the gstack `/review` finalize round. **The best template for the Smart Inputs plan** (richest cold-start + review history).

**Archived:**

- `yesno-pr-reviewers-guide.md` — the former repo-root `TODOS.md`, the YesNo PR reading guide. Historical (YesNo + Date both landed); kept for the PR narrative.

**Deferred design notes:** `scalar-envelope-arm-asymmetry.md`, `loader-vs-factory-date-split-duplication.md`, `case1-bare-date-arm-gap.md`, `container-default-temporal-codegen-gap.md`, `structure-field-fidelity-guard.md`, `refines-hint-native-list-drift.md` (triage list above).
