# Pipelex kernel — working notes

Extraction of operator-execution semantics out of the interpreter's operator classes into a public, hub-free `pipelex/kernel/` subpackage, with the interpreter re-pointed onto it — zero behavior change, single-sourced semantics, callable on a `RuntimeBoot`-only process with no `.mthds` loaded.

| Doc | What it holds |
| --- | --- |
| [`kernel-extraction-plan.md`](kernel-extraction-plan.md) | The execution plan: goal, doctrine, target API sketch, phases 0–3 with checkpoints, decisions, non-goals, gates. **Start here**; its status block is updated at every checkpoint. |
| [`deferred-follow-ups.md`](deferred-follow-ups.md) | Items surfaced in review and deliberately kept out of this branch's scope, with pick-up-cold context. |
| [`kernel-plugin-groups-and-distribution-plan.md`](kernel-plugin-groups-and-distribution-plan.md) | The sequel plan: the "kernel layer" naming ruling, layer-split plugin entry-point groups (Part A), and the in-repo `pipelex_kernel/` package split beside `pipelex/` (Part B, unpublished — the committed end-state). A hypothetical Part C (the published `pipelex-kernel` distribution) is sketched but requires an explicit greenlight. |
| [`plugin-group-split-deferred-items.md`](plugin-group-split-deferred-items.md) | Items raised by the Checkpoint A review of the group split and deliberately left out of Part A, plus three open questions for Louis (the `TASK_MANAGER` tier, whether the retired-group probe should be permanent, and whether `PluginGroup` belongs in the SPI list). |
| [`kernel-distribution-footprint.md`](kernel-distribution-footprint.md) | The B0 measurement: what the kernel package would contain, what it would require, and how big it would be — module set, cross-layer leak census, third-party dependency closure, install size. Drives B1's content line and the extras question a Part C would face. |
| [`a2-pipelex-temporal-branch-question.md`](a2-pipelex-temporal-branch-question.md) | **RESOLVED** — which branch takes pipelex-temporal's entry-point-group migration, given its open PR #18. Kept for the rationale trail behind decision D-A2-2. |
