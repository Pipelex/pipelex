# PR #1138 review notes — deferred item

PR: <https://github.com/Pipelex/pipelex/pull/1138> (`feature/MthdsTestCorpus-p3`, "a closed registry for validation error types")

One item from the review-agent triage on this PR was deferred rather than fixed. Everything else raised on the PR was either fixed in place or answered on the thread.

## The one-TestClass-per-module rule is absolute in writing, unenforced in practice, and shipped to users

**Reporter:** `chatgpt-codex-connector` (P1), on `tests/unit/pipelex/errors/test_validation_error_types.py:51`. The specific violation it flagged was real and has been fixed in this PR — the module's two test classes were merged into one. What is deferred is the systemic question that fixing it exposed.

**The rule.** `.claude/rules/pytest-standards.md` and its shipped kit copy `pipelex/kit/agent_rules/pytest_standards.md` both state it twice, without any qualifier:

> `NEVER EVER put more than one TestClass into a test module.`

> `- Always put tests inside Test classes: 1 TestClass per module.`

It reaches contributors and agents through the generated repo-root `AGENTS.md` and `CLAUDE.md`, and it reaches *our users* through the kit rules we ship in the package.

**What the codebase actually does.** Counting top-level `^class Test` declarations per module across `tests/`, after this PR's fix: 57 modules declare more than one, out of 1073 modules that declare at least one. The heaviest are `test_concept_representation_generator.py` (12 classes), `test_structured_content_composer.py` (11), `test_uri_resolver.py` (10), `test_migrate_commands.py` (10), `test_coverage_gate.py` (9), `test_validation_report.py` (9). These are not old stragglers: several landed within days of this PR, one of them the day before the review.

**Why it drifts.** Nothing checks it. `make agent-check` runs `fix-unused-imports fix-keyword-only format lint pyright mypy check-ledger check-keyword-only check-hub-layering drift-check`; `make check` adds the config, rules, URL, gateway-model, schema and migration checks plus `pylint`. No target in either aggregate, and no guard script anywhere, inspects test-class counts. Contrast the keyword-only convention, which is comparable in kind — a readability convention with no runtime consequence — and which is mechanically enforced by an AST guard wired into `agent-check`, `check`, and CI, complete with a grant registry for justified exceptions. That is what an enforced convention looks like in this repo; this one has no equivalent, so it is enforced only by whichever reviewer happens to notice.

**Why it matters beyond tidiness.** We ship "NEVER EVER" to users in the kit rules while 5% of our own class-bearing test modules break it. That is a dogfooding defect: either the rule means what it says and we should be able to hold ourselves to it mechanically, or it is a default-with-exceptions and the wording overstates it. Both are defensible; the current state — an absolute prohibition that only a review bot ever enforces, and only on whichever PR it happens to read — is the one option that is not.

**The open question, for a human to decide.** Two coherent resolutions, and choosing between them is a judgment call about how much we want to spend on test-file shape, not something a PR-review pass should settle unilaterally:

1. **Add a guard.** A small AST check in the `check-keyword-only` mould, run in `agent-check` and CI. Because 57 modules already violate it, this needs either a one-off sweep to merge or split them, or a grandfathering allowlist analogous to `subject_grants.toml` — and an allowlist that starts with 57 entries is worth pausing over before adopting.
2. **Soften the rule** in both `.claude/rules/pytest-standards.md` and the shipped `pipelex/kit/agent_rules/pytest_standards.md`, to something that matches how we actually write tests — for instance, one class per module by default, with more permitted when a module covers genuinely distinct seams. This costs nothing and removes the false absolute, but gives up the consistency the rule was reaching for.

There is no urgency either way; nothing is broken and no gate is failing. It should be decided rather than left to erode further, since every week it goes unresolved adds more modules to whichever sweep option 1 would require.
