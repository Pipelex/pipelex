# Optionals (`?` / `!`) — track folder

## Where things stand

**Phase 1 (the language core) is COMPLETE** — all steps A–F landed, final checkpoint cleared. The authoritative record — checkpoint log, decisions/deviations, hand-off notes — is kept at workspace level, because most of what it logs is the cross-repo landing. PR #1021 → dev is merge-ready; Louis merges.

**Decided:** `??` coalescing is pulled forward from phase 3 into phase 2 — it is the ergonomic replacement for the `continue` pass-through that phase 1 broke (design doc §13 migration note, §17 phasing).

## What comes next — three streams

1. **Release + spec-suite de-gate — DONE (pipelex 0.38.0 / pipelex-api 0.8.0).** The gate-removal checklist in [deferred-step-f-notes.md](deferred-step-f-notes.md) was run against the released runtimes: the pending-feature marker removed, six QA cases generated, probe-skips dropped, the whole optionals surface of our cross-repo spec suite green on both arms. The same pin bump also required reconciling the (separate) PipeSignature-tag retirement in that suite's signature fixtures — see the deferred-step-f note for that + the follow-ups it surfaced (plxt schema propagation, the stale `pipelex#996` gate, the `-L`-path static-pass categorization bug).
2. **Cross-repo optionals wave — plan to write.** Scope: mthds spec pages, mthds-python `absences` ledger on `DictWorkingMemoryAbstract` (un-gates the `_run_core_api.py` absent arm back here), mthds-js type mirrors, mthds-ui (skipped nodes, optional edges, `skip_reason`, the `conceptRefs.ts` parse-to-null bug), vscode-pipelex (grammar, semantic tokens, the Rust `strip_concept_qualifiers` bug), pipelex-api response models (`warnings` + contract `optional` flags), mthds-plugins skills. **Gated:** lands after the Required-main-stuff Phase 3 sweep (same mthds spec pages) and the release — except the two syntax-highlighting handoffs, which are ungated and already written up at workspace level.
3. **Phase 2 — plan to write, in-repo and ungated.** The PipeLLM/`Text?` maybe-wrapper with reasons + `??` coalescing (per the decision above). Candidate rider: the PipeBatch ledger-parity observability question from the Step F notes.

## Documents

- [optionals-design.md](optionals-design.md) — the design reference: decisions D1–D11, phasing (§17), decision summary. Still authoritative for future phases.
- [optionals-plan.md](optionals-plan.md) — the phase-1 narrative plan (steps A–F). CLOSED; kept as the record the tracker implements.
- [deferred-step-f-notes.md](deferred-step-f-notes.md) — **live follow-ups**: the spec-suite gate-removal checklist for the release, the hosted-wire absence-records pin, PipeBatch ledger-parity question, a pre-existing template-variable detection quirk.
- [deferred-absence-handling-dedup.md](deferred-absence-handling-dedup.md), [deferred-step-d-review-tradeoffs.md](deferred-step-d-review-tradeoffs.md), [deferred-step-e-review-tradeoffs.md](deferred-step-e-review-tradeoffs.md) — design-tradeoff findings from the checkpoint cold reviews, deliberately not applied; triage on demand.
- [optionals-phase1-highlights.html](optionals-phase1-highlights.html) — presentation artifact summarizing phase 1.

The phase-1 tracker and the cross-repo hand-off docs (vscode-pipelex + mthds-ui marker highlighting) are kept at workspace level.
