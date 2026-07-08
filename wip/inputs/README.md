# Inputs track — roadmap and reading guide

This folder holds the design and as-built records for the **Smart Inputs** feature and its two prerequisite native-concept tracks (`YesNo`, `Date`). **Start here on a cold session.**

## Current state (2026-07-08)

The whole inputs track is **code-complete** on `feature/Smart-inputs-phase5` (worktree `_smart`), tip `86f358f97`, based on main at v0.38.0 (includes TOML inputs #1022 + Optionals phase 1 #1021). The branch carries all three tracks; the per-phase branches (`feature/Smart-inputs-phase2/3/5`) are checkpoint snapshots.

- **`YesNo` native concept — ✅ DONE.** As-built: `yesno-implementation-plan.md`.
- **`Date` native concept — ✅ DONE.** PR **#1029** (`feature/native-date`) merged into the track. As-built: `datetime-implementation-plan.md`.
- **Smart Inputs — signature-driven input shaping — ✅ DONE.** All phases 1–5 landed (design D1–D11). As-built: `smart-inputs-implementation-plan.md` (the archived phased plan + per-checkpoint state + micro-decisions log).

PR **#1028** (`feature/Smart-inputs` → `dev`) is the track PR — retitled to cover YesNo + Date + Smart Inputs. Its head still points at an earlier phase tip; **advance its head to the track tip (all phases) before merging**, or the diff will misrepresent what ships.

## What shipped: Smart Inputs

Caller-provided inputs are now interpreted **top-down against the pipe's declared signature** instead of bottom-up from their shape alone. A bare string becomes the *declared* concept (a `legal.Question`, not a generic `native.Text`); a bare number/boolean/date satisfies a `Number`/`YesNo`/`Date`-refining input; a bare URL/path a declared `Image`/`Document` (relative paths resolved against the inputs-file dir); a plain object validates against a structured concept; a list shapes element-wise into `ListContent[declared]` (auto-wrap single, empty legal, `[N]` count-checked); a declared structured list accepts a `.csv` path by signature. The `{concept, content}` envelope stays as a compat-checked escape hatch. Unknown input names now error (D8, the one narrowing). `build inputs` / `pipelex-agent inputs` default to the **light** template, with `--explicit` for the envelope form (D11).

The mechanism: one shaper (`pipelex/core/memory/input_shaper.py`, `InputShaper`) wired into the single seam `WorkingMemoryFactory.make_from_pipeline_inputs(input_specs=…)` that `prepare_pipe_job` feeds `pipe.inputs` — so all surfaces (validate / real-run / dry-run, CLI / Python API / hosted runner) shape through one place. Full rationale + per-phase history in `smart-inputs-implementation-plan.md`.

## What remains: one release cut, one downstream cross-repo wave

Shared across YesNo + Date + Smart Inputs, done **per-release, not per-feature**:

- **D10 protocol widening** — `mthds/protocol/pipeline_inputs.py` `StuffContentOrData` widens to admit bare scalars / lists-of-dicts / empty lists ("any JSON value | StuffContent forms"), with the interpretation semantics spec'd MTHDS-side. Release-gated (Optionals/TOML-inputs de-gate pattern). Runtime already works; this is type-honesty for typed SDK/API callers.
- **Downstream mirrors** — `mthds-python` + `mthds-js` `PipelineInputs` types, conformance rows, JSON-schema copies (`mthds-schema-sync` skill), MTHDS spec native-concept + inputs-format sections.
- **Authoring-guidance surfaces** — `mthds-plugins` skills (`mthds-inputs`, `mthds-build`), `vscode-pipelex` completion lists, and the `ConceptSpec.refines` native-list hint (derive from `NativeConceptCode` — see `refines-hint-native-list-drift.md`).
- **Off critical path** — LLM-assisted input adaptation (design §8, opt-in); the shared YesNo/Date scalar-native LLM-output ergonomics.

## Deferred notes — Phase-5 triage outcomes (2026-07-08)

Each deferred note was re-verified against the landed shaper and given an outcome:

- **Resolved by the shaper** — `case1-bare-date-arm-gap.md` (a top-level date-literal array now builds `ListContent[DateContent]` on the signature path; pinned) and `bare-file-path-cli-resolution-gap.md` (Phase-3 D3: bare Image/Document paths resolve against the inputs-file dir).
- **Partially closed** — `input-shaper-multiplicity-gaps.md`: the finalize review re-found Gap A as a *silent* behavior (an explicit `ListContent` stored into a singular slot), so the **unambiguous half of Gap A is now fixed** (`_shape_explicit` rejects list-into-singular and enforces the `[N]` count on explicit lists, via a shared `_peel_multiplicity`; pinned by new `test_explicit_forms.py` cases). Gap A's auto-wrap sub-question and Gap B (the `DYNAMIC` arm skipping multiplicity peel) stay deferred as the genuine tradeoffs.
- **Re-deferred, reasoning refreshed** — `scalar-envelope-arm-asymmetry.md` (bare path now builds the refining subclass; only the *envelope* escape hatch keeps the base-`TextContent` asymmetry, and closing it means surgery on a shared bottom-up factory arm for near-zero gain); `loader-vs-factory-date-split-duplication.md` (the shaper did not collapse the CLI-format loader — different layers).
- **Decided leave-it** — `d4-hint-still-envelope.md` (the D4 error hint keeps rendering the envelope shape; option 1, it is a valid unambiguous fallback and making it light is a layer/cycle refactor unjustified by a fallback string).
- **Still out of scope (structure-field codegen / URI-tools / release-wave authoring)** — `container-default-temporal-codegen-gap.md`, `structure-field-fidelity-guard.md` (both structure-field codegen, untouched by Smart Inputs), `uri-scheme-classification-stopgap.md` (a `tools/uri` `resolve_uri` refactor; no live bug, tested), `refines-hint-native-list-drift.md` (the release-wave authoring-guidance sweep).

## Documents

**Design (source of truth for decisions):**

- `smart-inputs-design.md` — the approved Smart Inputs design: problem, shape at a glance, decisions D1–D11, non-goals, §9 surfaces checklist.
- `datetime-design.md` — the approved Date-track design (DT1–DT8).

**Implementation plans / as-built records:**

- `smart-inputs-implementation-plan.md` — the Smart Inputs phased plan + as-built (all phases done): cold-start code map, verified mechanism facts, per-checkpoint state lines, micro-decisions log, and per-phase review rounds.
- `yesno-implementation-plan.md` — YesNo phased plan + as-built.
- `datetime-implementation-plan.md` — Date phased plan + as-built, incl. the bot rounds and the gstack `/review` finalize.

**Archived:**

- `yesno-pr-reviewers-guide.md` — the former YesNo PR reading guide. Historical.

**Deferred design notes** (triage outcomes above): `case1-bare-date-arm-gap.md`, `bare-file-path-cli-resolution-gap.md`, `scalar-envelope-arm-asymmetry.md`, `loader-vs-factory-date-split-duplication.md`, `input-shaper-multiplicity-gaps.md`, `d4-hint-still-envelope.md`, `container-default-temporal-codegen-gap.md`, `structure-field-fidelity-guard.md`, `uri-scheme-classification-stopgap.md`, `refines-hint-native-list-drift.md`.
