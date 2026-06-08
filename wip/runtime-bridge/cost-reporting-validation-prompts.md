# Cost-reporting validation — prompts for `/temporal-e2e-validate`

Operator cheat-sheet for driving the distributed cost-reporting validation through the `/temporal-e2e-validate` skill. The skill's cost route is **scope-aware**: a bare cost request runs only the free deterministic arms; an explicit spend opt-in runs every arm including the live (real-money) ones. The arms (A–G) and their numeric assertions are defined in the skill's scope manifest at `.claude/skills/temporal-e2e-validate/references/mode-2-tiers.md` (Step 5b', Tier 8b). The gap audit that motivated them is the sibling [`distributed-cost-reporting-test-coverage.md`](distributed-cost-reporting-test-coverage.md).

## Prompt menu

### Full thorough run — real spend (arms A–G)

```text
/temporal-e2e-validate cost reporting full
```

Routes to Tier 8b and runs every arm: mock primary + cross-child fan-out + CSV cross-check + `--no-costs` negative gate + live LLM + live img-gen + live extract — each asserted numerically with `assert_cross_worker_cost.py`, PASS/FAIL surfaced per arm. `thorough`, `every`, and `with-spend` are aliases of `full`:

```text
/temporal-e2e-validate distributed cost — every arm
```

### Free, deterministic pass — no spend (arms A–B)

```text
/temporal-e2e-validate cost reporting
```

Mock primary + cross-child fan-out only (`--mock-inference`). The quick regression to run before committing or before paying for the live arms.

### Spend, but ask first

```text
/temporal-e2e-validate validate distributed cost on a live run
```

`live` / `all` are deliberately **not** treated as a spend opt-in (too easily incidental; `live` also collides with the default mock arm already running in LIVE mode). When that's the only signal, the agent runs the free arms and **confirms with you before** the real-money arms.

### Full run, LLM cost path only

```text
/temporal-e2e-validate cost reporting full, LLM arms only (skip img-gen/extract)
```

Use when only LLM inference is wired up in your env (see caveat below).

## Caveat — live non-LLM arms need backends

Arms F (img-gen) and G (extract) are **live-only** — `--mock-inference` can't reach them (their mock leaves raise `MockInferenceUnsupportedError`), so they're the sole proof that non-LLM usage crosses the runner fallback and aggregates into the cost report. They need real img-gen and extract backends configured (extract = Azure Doc Intel via the Pipelex Gateway). If those aren't set up, the two arms fail at the **run** step, not the assertion — and the manifest's "stop and report" rule means you'll see exactly which arm and why.

## Recommended sequence

1. `/temporal-e2e-validate cost reporting` — free, fast, confirms the capture → emit → fallback → aggregate → render plumbing.
2. `/temporal-e2e-validate cost reporting full` — spend on the live arms once the cheap ones are green.
