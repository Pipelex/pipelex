# Inputs track — roadmap and reading guide

This folder holds the design work for the **Smart Inputs** feature and its two prerequisite native-concept tracks. Start here on a cold session.

## Execution order (decided with Louis, 2026-07-07)

1. **`YesNo` native concept — core scope.** Enum entry, content class, structure-generator mapping, schema regen, MTHDS spec entry. Deliberately *excludes* the LLM-output ergonomics (how PipeLLM produces a `YesNo` — structured-gen wrapper, cousin of the Optionals maybe-wrapper); that ships as a follow-up off the critical path. Naming and rationale are settled — see `smart-inputs-design.md` §D9.
2. **`Datetime` native concept — core scope, time-boxed.** Retires `InputsDatetimeNotSupportedError` from the TOML-inputs feature. Open design questions to answer FIRST: one concept or three (TOML distinguishes datetime/date/time literals), timezone policy, naive vs aware. **We are ready to abandon this step if it gets too complex** — date strings degrade gracefully to Text, the Smart Inputs matrix row is purely additive later, and the TOML rejection error has shipped since v0.38.0 anyway. YesNo holds the train; Datetime rides standby.
3. **Smart Inputs** — signature-driven input shaping, implemented against the completed native family so the interpretation matrix, error taxonomy, docs rewrite, and spec section are written once. Full design (all decisions D1–D11 approved): `smart-inputs-design.md`.

Then: **one release cut, one downstream cross-repo wave** (schema sync, MTHDS spec, mthds-js/mthds-python mirrors, conformance, skills) covering all three — the sweeps are per-release, not per-feature.

Follow-ups off the critical path: YesNo LLM-output ergonomics; LLM-assisted input adaptation (design doc §8).

## Next session starts with

1. The **design for the Datetime native concept** (answer the one-vs-three question before anything else).
2. The **implementation plan for YesNo core**.

## Documents

- `smart-inputs-design.md` — the approved Smart Inputs design: problem, shape at a glance, decisions D1–D11 (D9 = the YesNo spin-off), non-goals, surfaces checklist.
