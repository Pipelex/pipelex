# `wip/` - Work in Progress

This folder holds active planning, design, and current-state docs for Pipelex runtime work. Finished plans, point-in-time PR recaps, and old audit artifacts are collected under [`history/`](history/).

Start with [`executive.md`](executive.md) for priorities. Then open the track README for the area you are picking up.

## Active Tracks

- [`plugins/`](plugins/) - real plugin architecture for orchestrators and inference backends. This is the major architecture track: entry-point discovery, registries, orchestrator dispatch, Temporal extraction, version gating, and cutover follow-ups.
- [`distributed-execution/`](distributed-execution/) - Temporal/distributed execution productionization. P0/P1 tracing and cost reporting shipped; open work is P0.2 follow-ons, local cross-package crates, remote dependency fetch, nondeterminism decisions, and MISTRAL_NATIVE downstream reconciliation.
- [`dry-run-refactor/`](dry-run-refactor/) - unified dry-run and validation execution. Part A shipped, Part B/unified dry run is implemented, and Part C needs release/API merge and hardening decisions.
- [`error-handling/`](error-handling/) - current-state reference and open tail for structured errors: webhook signing, metadata long tail, delivery-path request ids, and Temporal fail-safe review backlog.
- [`runtime-bridge/`](runtime-bridge/) - runtime bridge review/deferred follow-ups. Most PR review items are resolved; active value is in remaining deferred hardening and testing gaps.
- [`concurrency/`](concurrency/) - direct-mode batching/backpressure design: fan-out scheduling, rate limiting, and batch partial failure.
- [`graph/`](graph/) - graph/validation graph improvements: source-map enrichment and explicit graph target selection.
- [`observer-and-telemetry/`](observer-and-telemetry/) - telemetry/identifier visibility notes, especially hosted privacy around structural ids.
- [`recursivity/`](recursivity/) - only low-priority additive multi-file polish remains active; completed recursivity records are in history.

## Active Standalone Docs

- [`webhook-signing.md`](webhook-signing.md) - HMAC body-signing rollout for completion webhooks.
- [`init-yes-mode-handoff.md`](init-yes-mode-handoff.md) - non-interactive `pipelex init --yes` for downstream CI.
- [`structured-logging.md`](structured-logging.md) - structured log fields and contextvars.
- [`runtime-code-fixes.md`](runtime-code-fixes.md) - verified runtime fixes to pick up.
- [`structured-validation-errors-deferred-findings.md`](structured-validation-errors-deferred-findings.md) - contained follow-ups on structured validation errors.
- [`validate-parse-level-source-attribution.md`](validate-parse-level-source-attribution.md) - source attribution for malformed TOML in multi-file validation.
- [`blueprint-elaboration-directives.md`](blueprint-elaboration-directives.md) - future elaboration directive system.
- [`stuffs-as-nodespec.md`](stuffs-as-nodespec.md) - future graph model rework for stuff nodes.
- [`doctor-output-ansi-under-force-color.md`](doctor-output-ansi-under-force-color.md) - optional plain diagnostic output decision.
- [`pathlib-refactor.workflow.js`](pathlib-refactor.workflow.js) - runnable path-refactor workflow.

## History

[`history/`](history/) now holds shipped or reference-only material moved out of the active surface:

- CSV support
- keyword-only arguments
- signature-based validation
- cost-reporting registry work
- completed test-grind notes
- completed recursivity handoffs
- old `archive/` records
- point-in-time HTML recaps
