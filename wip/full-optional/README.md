# Full-optional track — a required input whose concept demands nothing

The track behind the **vacuous presence lint**: an advisory `warnings` item, emitted at validate time, when an entry pipe's gating input names a concept whose structure declares no required field — so an empty object satisfies the declaration and no form, gate or caller can tell what "supplied" means.

- [`design.md`](design.md) — the settled design: the rule, its decision table, the decisions (entry-pipe scope, descriptor substrate, one composition point for every advisory warning), the wire shape and message, the blast radius, what is deliberately out of scope, and the cross-repo follow-ups to file at close.
- [`../../TODOS.md`](../../TODOS.md) — the implementation tracker, at the repo root while the work is live.

Origin: [`wip/inbox/2026-08-25-pipelex-warn-required-input-all-optional-concept.md`](../../../wip/inbox/2026-08-25-pipelex-warn-required-input-all-optional-concept.md) (workspace inbox, filed from `mthds-form`), itself the author-side half of the form kernel's 2026-08-24 readiness-versus-gate disagreement.
