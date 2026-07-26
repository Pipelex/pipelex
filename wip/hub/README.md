# Hub layering — working docs

Working notes for the `refactor/Hub` track: splitting `pipelex.hub` into two hubs and drawing an enforced layering boundary between them.

| doc | what it is |
| --- | --- |
| [`hub-split-refactor.md`](hub-split-refactor.md) | The original design rationale — why one hub was a problem, alternatives considered, the measured argument. Written before Phase 0. Where it disagrees with `TODOS.md`, the tracker wins (it carries the settled decisions and the re-measured numbers). |
| [`layer-and-hub-renaming.md`](layer-and-hub-renaming.md) | **Pending work.** The decision to rename the layers to *runtime* / *interpreter* and the hubs to `runtime_hub` / `interpreter_hub`, with the full rationale, the rejected alternatives, and the mechanical plan. Execute **after** H-4 lands green and **before** the release and the cross-repo sweep. |

The executable tracker is [`../../TODOS.md`](../../TODOS.md) — start at its "⏸ Resume here" section. The shipped specification of the boundary is [`docs/contribute/hub-layering.md`](../../docs/contribute/hub-layering.md).
