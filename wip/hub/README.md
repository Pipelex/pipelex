# Hub layering — working docs

Working notes for the `refactor/Hub` track: splitting `pipelex.hub` into two hubs and drawing an enforced layering boundary between them.

| doc | what it is |
| --- | --- |
| [`hub-split-refactor.md`](hub-split-refactor.md) | The original design rationale — why one hub was a problem, alternatives considered, the measured argument. Written before Phase 0. Where it disagrees with `TODOS.md`, the tracker wins (it carries the settled decisions and the re-measured numbers). |
| [`layer-and-hub-renaming.md`](layer-and-hub-renaming.md) | The decision to rename the layers to *runtime* / *interpreter* and the hubs to `runtime_hub` / `interpreter_hub`, with the full rationale, the rejected alternatives, and the mechanical plan. **Landed** as its own commit after H-4. |
| [`pr-1062-review-followups.md`](pr-1062-review-followups.md) | **Pending work — start here.** The executable follow-up plan from the full `/review` pass on PR #1062: the transitive hole in the layer rule, the in-PR fixes, the test hardening, and the additions the release-gated sweep is missing. Phases A and B are applied; what is left is the F1 remedy (its own PR, after #1062 merges) and the release-gated Phase C. |

The executable tracker is [`../../TODOS.md`](../../TODOS.md) — start at its "▶ Resume here" section. The shipped specification of the boundary is [`docs/contribute/hub-layering.md`](../../docs/contribute/hub-layering.md). The earlier single-thread triage is [`../pr-1062-review-notes.md`](../pr-1062-review-notes.md).
