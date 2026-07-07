# Inputs track — roadmap and reading guide

This folder holds the design work for the **Smart Inputs** feature and its two prerequisite native-concept tracks. Start here on a cold session.

## Execution order (decided with Louis, 2026-07-07)

1. **`YesNo` native concept — core scope. ✅ DONE (2026-07-07).** Enum entry, content class, structure-generator mapping, envelope inputs, LLM object-path verification, schema regen (no-diff), docs, CHANGELOG, MTHDS spec draft. Deliberately *excluded* the LLM-output ergonomics (how PipeLLM produces a `YesNo` — structured-gen wrapper, cousin of the Optionals maybe-wrapper); that ships as a follow-up off the critical path. Naming and rationale are settled — see `smart-inputs-design.md` §D9. Plan + as-built: `yesno-implementation-plan.md` (all phases 1–4 complete, checkpoints 1–3 cleared; committed on `feature/Smart-inputs`, not pushed). MTHDS spec draft on `mthds` side branch `feature/native-yes-no-concept`.
2. **`Datetime` native concept — core scope. ✅ DONE (2026-07-07).** ONE native concept named `Date` (not three) — required date + optional time, offset on the time's tzinfo, fidelity-first timezone policy. Retired the wholesale `InputsDatetimeNotSupportedError` (renamed `InputsTimeOnlyNotSupportedError`, now bare-time-only). Shipped: `DateContent` + enum/factory/registry wiring, TOML date/datetime literals as inputs (loader conversion + envelope arms), LLM object-path verification, DT8 (the `date` structure-field misnomer fix — `date`→`datetime.date`, new `datetime` field type, mirrored into the spec layer), docs, CHANGELOG. Committed on `feature/Smart-inputs` (Phases 1–4, checkpoints 1–3 cleared). Plan + as-built: `datetime-implementation-plan.md`.
3. **Smart Inputs** — signature-driven input shaping, implemented against the completed native family so the interpretation matrix, error taxonomy, docs rewrite, and spec section are written once. Full design (all decisions D1–D11 approved): `smart-inputs-design.md`.

Then: **one release cut, one downstream cross-repo wave** (schema sync, MTHDS spec, mthds-js/mthds-python mirrors, conformance, skills) covering all three — the sweeps are per-release, not per-feature.

Follow-ups off the critical path: YesNo LLM-output ergonomics; LLM-assisted input adaptation (design doc §8).

## Next session starts with

1. ~~Execute `yesno-implementation-plan.md`~~ — **done.** YesNo is committed on `feature/Smart-inputs`.
2. ~~Execute `datetime-implementation-plan.md`~~ — **done.** The native `Date` concept is committed on `feature/Smart-inputs` (Phases 1–4).
3. Execute the **Smart Inputs** step: signature-driven input shaping against the completed native family (`smart-inputs-design.md`, decisions D1–D11).

## Documents

- `smart-inputs-design.md` — the approved Smart Inputs design: problem, shape at a glance, decisions D1–D11 (D9 = the YesNo spin-off), non-goals, surfaces checklist.
- `yesno-implementation-plan.md` — the phased implementation plan for `YesNo`: cold-start context (code map, verified mechanism facts, envelope-inputs scope guard), checkbox tasks, checkpoints with state lines, micro-decisions log.
- `datetime-design.md` — the APPROVED Datetime-track design: one native `Date` concept (date + optional time, fidelity-first timezone policy), decisions DT1–DT8; DT8 flags the pre-existing `date` structure-field misnomer.
- `datetime-implementation-plan.md` — the phased implementation plan for `Date`: cold-start context (code map, verified mechanism facts, cross-repo gotchas), checkbox tasks, checkpoints with state lines.
