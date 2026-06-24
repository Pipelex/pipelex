# Executive Priorities

This is the top-level decision sheet for the current `wip/` tree. It intentionally favors what to do next over full historical context.

## Strategic Priorities

1. **Finish the plugin/orchestrator architecture.**
   The plugin track is the highest-leverage architecture work: it removes core vendor coupling, gives Temporal and MISTRAL_NATIVE a proper seam, and makes installed integrations discoverable instead of hard-coded. Close the execution-mode/delivery split, version-gating semantics, Temporal extraction, and downstream MISTRAL_NATIVE reconciliation before expanding the plugin surface further.

2. **Productionize distributed execution.**
   P0/P1 tracing and cross-worker cost reporting shipped, so the remaining value is operational: local cross-package dependencies in the crate, remote dependencies from GitHub, nondeterminism decisions, request-scoped tracing state, and the split-worker test coverage gaps. This is what makes worker pools stateless enough to scale.

3. **Land the dry-run/validation API path cleanly.**
   The unified dry-run work is mostly built, but Part C still needs the pipelex release/API pin flip, old graph-path retirement decisions, and hardening around cancellation, config drift, source-map scoping, and queue tuning. This is the main developer-experience path for validation and hosted dry-run.

4. **Close the API/error-handling security tail.**
   Webhook body signing is the clearest security item. After that, finish the structured error long tail: class-level metadata for remaining errors, request ids on delivery failures, and the parked Temporal fail-safe review backlog when Temporal productionization resumes.

5. **Make batch execution harder to overwhelm.**
   The concurrency work is not urgent until batch-at-scale pain returns, but the diagnosis is solid: fan-out scheduling and partial failure should be decided together; rate limiting is separate and needs mode-specific design for direct vs Temporal.

6. **Improve validation and graph ergonomics for tools.**
   The next useful tooling lifts are explicit validation graph targets, registry source paths in `GraphSpec`, parse-level source attribution for malformed TOML, and eventually stuffs as first-class `NodeSpec`s.

## Quick Wins

- **Add `pipelex init --yes`.** The handoff is scoped and mostly plumbing: short-circuit existing prompts to defaults, avoid silently accepting Gateway terms, and unblock downstream CI without vendored `.pipelex/`.
- **Thread `request_id` into delivery failure logs.** Small error-handling tail item; closes an observability asymmetry on webhook/storage failure paths.
- **Categorize missing pipe `type`.** Add `union_tag_not_found` beside `union_tag_invalid` in structured validation error categorization and test a `[pipe.foo]` block without `type`.
- **Add parse-level source attribution test/fix.** More involved than the previous item, but contained and important for editor diagnostics on multi-file validation.
- **Clean up additive multi-file polish.** The recursivity review notes are P3-only but cheap when nearby: soften an overclaiming docstring, comment the `or ""` coercion, and add one populated `LibraryLoadingError` forwarding test if touching validation.
- **Fix/retire runtime-bridge small leftovers.** Decide whether to consume or remove unused execution-mode property helpers; fix the dev helper that glob-selects the latest cost CSV instead of the current run.
- **Tidy plugin follow-ups.** Drop the dead `bedrock` model-lister key with its exact-set test update, and make plugin API version gating use a literal built-against version plus a semver compatibility rule.
- **Patch `temporal-e2e-validate` stale notes.** Remove the vestigial `act_jinja2_gen_text` reference and stale Mode 1 known-xfail text.
- **Add optional `doctor --plain` only if needed.** Current ANSI behavior is standard; a flag is a small ergonomics win for captured diagnostics if this bites again.

## Lower Priority / Parked

- CSV `.xlsx`, formula escaping, delimiter/encoding config, and remote tabular URLs are all feature expansion, not active debt.
- Structured logging is worth doing after the error-handling stack stops moving.
- `stuffs-as-nodespec`, blueprint elaboration directives, and the pathlib workflow are future-shaping tracks; pick them up only with a concrete product/tooling need.
- Historical records live in [`history/`](history/). Do not promote them back into active `wip/` unless they contain a concrete unowned follow-up.
