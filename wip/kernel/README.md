# Method kernel — working notes

Extraction of operator-execution semantics out of the interpreter's operator classes into a public, hub-free `pipelex/kernel/` subpackage, with the interpreter re-pointed onto it — zero behavior change, single-sourced semantics, callable on a `RuntimeBoot`-only process with no `.mthds` loaded.

| Doc | What it holds |
| --- | --- |
| [`kernel-extraction-plan.md`](kernel-extraction-plan.md) | The execution plan: goal, doctrine, target API sketch, phases 0–3 with checkpoints, open decisions, non-goals, gates. **Start here**; its status block is updated at every checkpoint. |
