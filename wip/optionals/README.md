# Optionals (`?` / `!`) — track folder

## Where things stand

**Phase 1 (the language core) is COMPLETE** — all steps A–F landed, final checkpoint cleared. The authoritative record is [optionals-phase1-tracker.md](optionals-phase1-tracker.md) (archived from the worktree-root `TODOS.md`; checkpoint log, decisions/deviations, hand-off notes). PR #1021 → dev is merge-ready; Louis merges.

**Decided:** `??` coalescing is pulled forward from phase 3 into phase 2 — it is the ergonomic replacement for the `continue` pass-through that phase 1 broke (design doc §13 migration note, §17 phasing).

## What comes next — three streams

1. **Release + conformance de-gate — DONE (pipelex 0.38.0 / pipelex-api 0.8.0).** The gate-removal checklist in [deferred-step-f-notes.md](deferred-step-f-notes.md) was run against the released runtimes: `OPTIONALS_PENDING_FEATURE` removed, six QA cases generated, probe-skips dropped, whole optionals conformance surface green on both arms. The same pin bump also required reconciling the (separate) PipeSignature-tag retirement in the conformance signature fixtures — see the deferred-step-f note for that + the follow-ups it surfaced (plxt schema propagation, the stale `pipelex#996` gate, the `-L`-path static-pass categorization bug).
2. **Cross-repo optionals wave — plan to write.** Scope: mthds spec pages, mthds-python `absences` ledger on `DictWorkingMemoryAbstract` (un-gates the `_run_core_api.py` absent arm back here), mthds-js type mirrors, mthds-ui (skipped nodes, optional edges, `skip_reason`, the `conceptRefs.ts` parse-to-null bug), vscode-pipelex (grammar, semantic tokens, the Rust `strip_concept_qualifiers` bug), pipelex-api response models (`warnings` + contract `optional` flags), mthds-plugins skills. **Gated:** lands after the Required-main-stuff Phase 3 sweep (same mthds spec pages) and the release — except the two syntax-highlighting handoffs, which are ungated and already written up (workspace root `../wip/optionals/`).
3. **Phase 2 — plan to write, in-repo and ungated.** The PipeLLM/`Text?` maybe-wrapper with reasons + `??` coalescing (per the decision above). Candidate rider: the PipeBatch ledger-parity observability question from the Step F notes.

## Documents

- [optionals-design.md](optionals-design.md) — the design reference: decisions D1–D11, phasing (§17), decision summary. Still authoritative for future phases.
- [optionals-plan.md](optionals-plan.md) — the phase-1 narrative plan (steps A–F). CLOSED; kept as the record the tracker implements.
- [optionals-phase1-tracker.md](optionals-phase1-tracker.md) — the phase-1 tracker (checkpoint log, decisions/deviations log, cold-start context). CLOSED; archived here from the worktree-root `TODOS.md` now that phase 1 is done.
- [deferred-step-f-notes.md](deferred-step-f-notes.md) — **live follow-ups**: the conformance gate-removal checklist for the release, the hosted-wire absence-records pin, PipeBatch ledger-parity question, a pre-existing template-variable detection quirk.
- [deferred-absence-handling-dedup.md](deferred-absence-handling-dedup.md), [deferred-step-d-review-tradeoffs.md](deferred-step-d-review-tradeoffs.md), [deferred-step-e-review-tradeoffs.md](deferred-step-e-review-tradeoffs.md) — design-tradeoff findings from the checkpoint cold reviews, deliberately not applied; triage on demand.
- [optionals-phase1-highlights.html](optionals-phase1-highlights.html) — presentation artifact summarizing phase 1.

Cross-repo hand-off docs (vscode-pipelex + mthds-ui marker highlighting) live at the workspace root: `../wip/optionals/`.
