# STRICT disclosure — INPUT-domain passthrough gap

> **Landed 2026-05-22** on `feature/API-readiness-2` (Phase 1 of `_for_api/TODOS.md`). Fixed via **Option 1**: a per-class `PipelexError._authors_caller_facing_message` `ClassVar` — default `False`, set `True` on `PipelexInterpreterError` and `ValidateBundleError` (the two INPUT-domain classes whose messages describe the caller's own input). It is carried onto a new `ErrorReport.caller_facing_message` field at report construction, is *not* inherited up the `__cause__` chain (so a domain-less wrapper over an INPUT cause does not pick it up), and gates the STRICT `message` passthrough — replacing the old `error_domain == INPUT` check. **Gap 2 closed too:** `provider` / `model` / `provider_metadata` are now stripped from the STRICT passthrough branch as well, so STRICT never emits provider metadata for any `error_domain`. The `DisclosureMode` docstring matches the implemented redaction set. The rest of this doc is the original analysis, kept for context.

Follow-up surfaced during the /review pass on the Stage 2 disclosure-mode work (Item C). Not a blocker for the error-handling refactor — STRICT redaction is correct for `CONFIG` / `RUNTIME` reports, which is the path the API exercises today — but the `INPUT`-domain passthrough has two soft spots that should be tightened before the API starts rendering STRICT for caller-facing surfaces.

## What

`DisclosureMode.STRICT` is documented as a *classification-projection for server-side errors*: `CONFIG` / `RUNTIME` reports get `message` replaced and `provider` / `model` / `provider_metadata` / `user_action` dropped, while `INPUT`-domain reports pass through unchanged because their `message` is caller-influenced. Two cases let that `INPUT` exemption cover more than it should.

### Gap 1 — a domain-less wrapper inherits `INPUT` and leaks its own message

`ErrorReport.to_dict(STRICT)` keys the passthrough on the report's final `error_domain == ErrorDomain.INPUT`. But `PipelexError._enrich_error_report_from_cause` fills `error_domain` from the `__cause__` chain:

```python
error_domain=report.error_domain or cause_report.error_domain,
```

A wrapper whose own class declares no domain (`PipelexError` base, `PipelexUnexpectedError` — both `error_domain = None`) raised `from` an `INPUT`-domain cause produces a report classified `error_domain=INPUT` **while keeping the wrapper's own `message`**. That wrapper message was authored as internal / "unexpected" text, not as caller-facing `INPUT` copy — so STRICT reflects it back verbatim to any surface that asked for STRICT.

The redaction decision is keyed on an *inherited classification* rather than on the *provenance of the message it is protecting*.

### Gap 2 — `to_problem_document` echoes provider/model for `INPUT` reports in STRICT

Because STRICT returns `INPUT` reports unchanged, `to_problem_document` then copies every non-RFC-7807-mapped key onto the envelope — including `provider`, `model`, `provider_metadata`, `user_action` — when an `INPUT` report's cause-enrichment pulled them from an inference-layer `__cause__`. The `DisclosureMode` docstring states these fields are "dropped" in STRICT; that is true only on the `CONFIG` / `RUNTIME` branch, not the `INPUT` passthrough.

## Why this is a follow-up, not an immediate fix

- STRICT is correct and complete for `CONFIG` / `RUNTIME` reports — the only path the API renders today.
- Both gaps need a real chain to bite: a domain-less wrapper raised `from` an `INPUT` cause, carrying a sensitive message / provider metadata. Whether such chains exist in practice needs an audit, not a guess (medium confidence, 6/10).
- The fix is a design choice (see Options) that deserves its own focused change rather than riding the refactor PR.

## Options

### Option 1 — gate STRICT passthrough on message provenance, not inherited domain (preferred)

Add an explicit per-class `ClassVar` marking which error classes genuinely author caller-facing messages (e.g. `PipelexInterpreterError`, bundle-validation errors), and gate the STRICT passthrough on that flag instead of on `error_domain == INPUT`. A domain-less wrapper over an `INPUT` cause then redacts normally.

### Option 2 — don't inherit `error_domain` onto a domain-less wrapper

In `_enrich_error_report_from_cause`, stop inheriting `error_domain` when the wrapper's own class declares none. Smaller change, but it also changes `http_status` for those wrappers (they'd fall back to 500 instead of the cause's status) — needs a sweep of the status-mapping tests.

### Either option, plus

Strip `provider` / `model` / `provider_metadata` from the `INPUT` passthrough branch of `to_dict(STRICT)` — an input-classification error has no business carrying provider metadata onto an external surface — and align the `DisclosureMode` docstring with whatever the final behavior is.

## Acceptance — all met (2026-05-22)

- [x] A domain-less wrapper (`PipelexUnexpectedError`) raised `from` an `INPUT`-domain cause does not leak the wrapper's `message` through `to_dict(STRICT)`.
- [x] `to_problem_document(disclosure_mode=STRICT)` never emits `provider` / `model` / `provider_metadata` regardless of `error_domain`.
- [x] The `DisclosureMode` STRICT docstring matches the implemented redaction set.
