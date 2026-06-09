# `/temporal-e2e-validate` — prompt menu

Operator cheat-sheet of prompts for the `/temporal-e2e-validate` skill. Sibling of [`temporal-e2e-validate-skill.md`](temporal-e2e-validate-skill.md) (what the skill validates + current-state record). The cost-reporting slice has its own deeper cheat-sheet: [`../runtime-bridge/cost-reporting-validation-prompts.md`](../runtime-bridge/cost-reporting-validation-prompts.md).

Convention below: `$` marks prompts that spend real money (live inference / live image-gen / live extract). Everything else is free — dry-run or `--mock-inference`. A few of the live tiers (4, 5, 12) also *run* in dry mode for structural coverage but only catch real payload / cost bugs when run live; those are marked `$ (dry-capable)`.

## Run it ALL in one go

### Complete sweep, real spend authorized ($)

```text
/temporal-e2e-validate run the COMPLETE sweep with real spend authorized — do NOT skip the opt-in batteries or the live arms. Mode 1 pytest dry then live. Mode 2 every tier: 1/2/2b/3 core, 4 & 5 live (image payload), Step 4 graph tracing, Step 5 concurrent isolation, Tier 8 usage emission, Tier 8b cost reporting FULL (arms A–G), Tier 9 object-gen, Tier 11 extract, Tier 12 CV batch live, Tiers 13–16 error propagation, Tiers 6/7 codec. Then Step 8 routing battery (10a–10c) and Step 9 queue-options + worker-runtime-profile battery (Scenarios A–F). Finish with the master results table — PASS/FAIL per tier/scenario — and stop-and-report on any failure.
```

### Complete sweep, no spend (full structural pass)

```text
/temporal-e2e-validate run the full sweep DRY/mock only — no real spend. Mode 1 dry, Mode 2 all tiers in dry/mock (Tier 8b cost reporting via --mock-inference, arms A–B), Step 5 isolation, Tiers 6/7 codec, plus Scenario C (pytest) and Scenario F (CLI typo). Skip the live-only arms: image payload (4/5), CV batch live (12), routing battery (10a–10c), queue-options live scenarios (A/B/D/E), and the live cost arms (E–G). Master results table at the end.
```

Recommended order: run the **no-spend** sweep first to confirm the plumbing cheaply, then the **real-spend** sweep once it's green. The all-in-one is long and runs tiers sequentially (reporting after each); if a live backend isn't configured, that arm stops-and-reports rather than silently passing — see Prerequisites.

## By area

### Broad (skill's own recognized triggers)

```text
/temporal-e2e-validate                       # full regression; offers the two batteries as opt-in extras
/temporal-e2e-validate full temporal test    # same, explicit
```

### Mode 1 — fast pytest (real server, in-process worker)

```text
/temporal-e2e-validate run the Mode 1 pytest suite, dry      # library_crate: crate, hydration, isolation, controllers
/temporal-e2e-validate Mode 1 pytest, live LLM           # $ same suite with real inference
```

### Core distributed execution (Mode 2, free)

```text
/temporal-e2e-validate validate core distributed execution — LibraryCrate, deferred hydration, parallel child workflows
/temporal-e2e-validate validate concurrent isolation (concept / pipe / multi-concept)    # Step 5
/temporal-e2e-validate validate cross-process registry                                   # Tier 2b
```

### Validation sweep stays in-process — Temporal-leak guard (free)

Guards the `/validate` dry-run leak (nested controller sub-pipes dispatching to Temporal → HTTP 422 on a standalone `PipeBatch`). Two layers, both free; the contract is "the validation sweep never dispatches to Temporal, even under a Temporal-enabled boot".

```text
/temporal-e2e-validate validate the dry-run sweep stays in-process under a Temporal-enabled boot   # Mode 2 Tier 2c
```

- **Mode-1 pytest** (real `TemporalPipeRouter` as hub default, spies `WorkflowExecutor.execute_workflow`, asserts never called). It lives *outside* `library_crate/`, so the generic "Mode 1 pytest suite" prompt above does **not** pick it up — run it by path:

  ```text
  timeout 180 .venv/bin/pytest tests/integration/pipelex/temporal/test_validate_sweep_stays_in_process.py -m temporal --temporal-server local --timeout=60
  ```

  (Self-contained — GREEN never dispatches, so no live server is actually required; `--temporal-server none` works too.)

- **Mode-2 Tier 2c** (deployment-faithful: `validate bundle --temporal` over a standalone `PipeBatch` → exit 0 **and** worker idle / no `WfPipeRouter` dispatch). Reached via the prompt above; full GREEN/RED procedure in `references/mode-2-tiers.md` Step 3, Tier 2c.

### Graph tracing (free)

```text
/temporal-e2e-validate validate cross-worker graph tracing / GraphSpec assembly          # Step 4
```

### Images ($ — dry-capable, but run live to catch payload bugs)

```text
/temporal-e2e-validate image temporal        # Tiers 4–5: image gen + image-to-LLM flow, payload storage
```

### Object generation / extract / batch

```text
/temporal-e2e-validate validate object generation cross-process                  # Tier 9, free
/temporal-e2e-validate validate make_extract_pages two-activity cross-process     # Tier 11, free
/temporal-e2e-validate validate the CV batch deeply-nested controller stack       # Tier 12, $ (dry-capable)
```

### Error propagation

```text
/temporal-e2e-validate validate error handling      # Mode 1 Step 2b + Tiers 13–16
/temporal-e2e-validate error report propagation across the activity → workflow → submitter boundary
```

Covers LLM, extract, image-gen, and fanned-out child-workflow (PipeBatch) failures carrying a structured `ErrorReport`. Free — failures are mocked or forced via a bad-credential worker (401), no successful inference billed.

### Payload codec (free)

```text
/temporal-e2e-validate validate the StoragePayloadCodec — transparency + large-payload stress   # Tiers 6–7
```

### Routing — v1 `activity_queues` ($)

```text
/temporal-e2e-validate routing               # Tiers 10a–10c: multi-activity isolation, per-handle routing, two-activities-one-route
```

### Queue options + worker-runtime profiles — v2 (mixed)

```text
/temporal-e2e-validate queue options         # Scenarios A–F
/temporal-e2e-validate runtime profile       # named worker-runtime profiles via --profile
```

Scenarios: A multi-class routing, B per-queue timeout, D queue rate-limit, E missing-worker negative (all live `$`); C per-handle override (pytest, free); F the `--task-queue` CLI typo check with "did you mean?" (CLI startup, free).

### Cost reporting

```text
/temporal-e2e-validate cost reporting        # free: mock arms A–B
/temporal-e2e-validate cost reporting full   # $ every arm A–G
```

Full detail (arm-by-arm assertions, aliases, ask-first behavior) in [`../runtime-bridge/cost-reporting-validation-prompts.md`](../runtime-bridge/cost-reporting-validation-prompts.md).

## Recognized triggers vs descriptive prompts

Some prompts hit **explicit routes** in the skill (`full temporal test`, `validate error handling`, `cost report`, `queue options` / `runtime profile` / `routing`, `image temporal`). The per-tier ones (Tier 9, 11, 12, codec, graph tracing…) are not separate routes — the agent reads `references/mode-2-tiers.md` and runs the named tier, so a descriptive prompt naming the concern is enough.

## Prerequisites

- `tmux` and the `temporal` CLI installed; the Temporal dev server reachable (the skill starts one if needed).
- Mode 2 stands up split router+runner worker processes (see `references/mode-2-setup.md`).
- Live arms need credentials: LLM inference (or the Pipelex Gateway), real image-gen, and extract = Azure Doc Intel via the gateway. Missing a backend makes that arm fail at the **run** step, not the assertion — the skill reports which arm and why.
