# Drift contracts — Phase 3 pilot verdict (working doc)

**Status: DRAFT — awaiting Louis' rulings (decision boxes below).** This is the deferred "Phase 3 — pilot verdict" item from the Drift Hunt tracker (`TODOS.md` → Deferred drift-contracts items): the per-contract **keep / narrow / mechanize / drop** decision the design said must wait for dogfood evidence, plus the manifest-growth question that evidence now answers. Ruling on this doc formally ends the D5 dogfood freeze ("evidence now, contracts later" — the campaign is closed, the evidence is in).

Naming note: the design doc's rollout plan (`wip/drift-contracts-design.md` → Rollout plan) used "Phase 3" for *agent ergonomics, after the dogfooding verdict*; the campaign tracker uses "Phase 3" for the verdict itself. This doc is the verdict; the agent-ergonomics leftovers are folded in as agenda item E3. (The tracker's pointer to the original phase breakdown — `git show origin/docs/Update:TODOS.md` — is dead, that branch is gone; the surviving source is the design doc's Rollout plan section.)

## The question the pilot asked

From the design doc, verbatim: *"is the ack friction proportionate to the staleness it catches?"* — with the promised consequence: *"If the dogfood shows the acks catching real staleness at tolerable friction, grow the manifest; if it shows ceremony, we will have learned that cheaply."*

**Verdict: the mechanism works; grow the manifest — narrowly.** The evidence below supports keeping all three seed contracts, repairing identified trigger gaps, adding two new contracts, and adopting the campaign's top derived checks. It does not support broad trigger expansion (see B5).

## A — Evidence base

Three independent sources:

**A1 — the dogfood log** (`wip/drift-contracts/dogfood-log.md`). Every ack so far logged: one **real-catch** (keyword-only — the guard gained the subject-grant registry and the convention doc was materially stale, exactly the coupling the contract exists to enforce), the rest **clean-pass** (genuine reviews, nothing stale), and **zero friction verdicts** (no contract ever opened on changes that could not have affected its targets). Small sample, but the directional read is clean: real staleness caught, no ceremony observed. One process slip (an ack recorded without its mandatory log entry, backfilled honestly) — an argument for keeping the log mandatory, not for dropping it (see E1).

**A2 — the Drift Hunt campaign** (`wip/drift-hunt/findings/SUMMARY.md`, close-out). The campaign is the system's external validation:

- **Docs edited in the same commit as their code did not drift** — observed in the wild (`d3550330a`, `15e0a94ea`). That is the drift-contracts thesis, confirmed empirically.
- **Drift follows audience, not complexity.** Author-is-the-reader pages stay current by use; explain-it-to-someone-else pages drift at up to 2.0 findings/page. Contract budget belongs on reader-facing pages.
- **Some drift classes are provably un-mechanizable.** Part 4's repo-tooling class: every documented make target exists (an existence script scores zero), yet behavior drifted under stable names — `agent-test` grew a heartbeat weeks after a page was written on the premise it was silent. The right instrument is a review obligation. This is the campaign's strongest evidence *for* the contracts mechanism itself.
- **A green snippet check must never be read as a clean page** (F13: four bundles validate and dry-run clean while the prose beside them teaches a false rule). This bounds what the derived checks in section D can be trusted to mean.
- The ranked drift-contract shortlist handed to this verdict (SUMMARY.md → Handoff 1).

**A3 — the trigger-coverage audit** (this session, 2026-07-13). Cross-checking `drift.toml`'s trigger globs against where the documented surfaces actually live in the code found the concrete gaps itemized in section B.

## B — Verdicts on the seed contracts

| Contract | Verdict | Change |
|---|---|---|
| `config-docs` | **KEEP + repair triggers** | Add the inference-backend/routing surface (B1); adopt the coverage meta-check (section C) |
| `cli-docs` | **KEEP as-is** | None — right glob, right exclusion, right targets |
| `keyword-only-convention` | **KEEP + extend trigger** | Add `subject_grant_cmd.py` (B3) |

### B1 — `config-docs`: repair the trigger enumeration

**The hole today:** `docs/configuration/config-technical/inference-backend-config.md` documents the backend TOML layout, per-backend setup, gateway overrides, and routing profiles — whose sources of truth are `pipelex/cogt/model_backends/*.py`, `pipelex/cogt/model_routing/*.py`, and the shipped structural TOMLs under `pipelex/kit/configs/inference/`. None of those are triggers; only `config_cogt.py` is. A field added to the `Backend` model, or a restructuring of `backends.toml` / `routing_profiles.toml`, changes what that page must say without opening the contract.

**Proposed trigger additions:**

```toml
"pipelex/cogt/model_backends/**/*.py",
"pipelex/cogt/model_routing/**/*.py",
"pipelex/kit/configs/inference/backends.toml",
"pipelex/kit/configs/inference/routing_profiles.toml",
```

**Deliberately excluded:** the per-backend deck files (`pipelex/kit/configs/inference/backends/*.toml`). The add-model flow touches those routinely; making every model addition cost an ack is exactly the friction the manifest header warns against, and the docs page documents the *structure*, not the model roster. Residual risk accepted: a backend file rename could drift the doc's examples without opening the contract — the enumerations derived check (D1) is the better instrument for roster-shaped drift.

**The structural fragility:** hand-enumerating submodel files means every *new* documented submodel defined in its own package silently escapes the gate — drift of the drift manifest, the one place the system cannot see itself. The settings-model files (`llm_setting.py`, `extract_setting.py`, `img_gen_setting.py`, …) are the current long tail: some are documented via sections that live in already-triggered files, some may not be. Rather than audit them by hand once (and rot again), fix it structurally — see section C.

- [ ] **DECISION B1 (Louis):** adopt the four trigger additions? Include or exclude the per-backend deck files?

### B2 — `cli-docs`: keep as-is

The glob (`pipelex/cli/**/*.py` minus `dev_cli/`), the review targets, and the observed behavior (a clean-pass ack on a broad internal sweep that changed no command surface) are all as designed. No change proposed.

- [ ] **DECISION B2 (Louis):** confirm keep-as-is.

### B3 — `keyword-only-convention`: the trigger is one file, the convention's tooling is two

The doc specifies the grant workflow (`make sgr`), implemented in `pipelex/cli/dev_cli/commands/subject_grant_cmd.py` — not in the guard. Not hypothetical: the Signatures track deleted `--seed`/`seeded` from exactly that command and the doc had to follow (it did, by discipline).

**Proposed:** add `"pipelex/cli/dev_cli/commands/subject_grant_cmd.py"` to the contract's triggers.

- [ ] **DECISION B3 (Louis):** adopt.

### B4 — a note on the keyword-only contract's audience

The campaign's headline correlation says maintainer-facing pages stay current by use, and `keyword-only-arguments.md` is maintainer-facing — it came back clean in Stage 1. That cleanliness is confounded (the contract already existed and had produced the pilot's one real-catch), and the contract's friction is near zero (a single-file trigger that rarely changes). **Proposed: keep.** Recorded here so the "narrow or drop" question was asked on the record, not skipped.

### B5 — what NOT to do: no broad Python-surface triggers

The worst drift density was in the under-the-hood docs (renamed Python APIs, ~2.0 findings/page), and the tempting response is a contract triggered on the API surface. The trigger would be effectively `pipelex/**/*.py`, it would open on every PR, and acks would degrade into rubber stamps — the exact failure mode the design doc names ("if we observe reflexive acks, the contract is mis-scoped"). That drift class belongs to the derived checks (section D), which is also where the campaign's shortlist puts the top value-per-effort. **Proposed: no contract for the Python API docs; adopt D3 instead.**

- [ ] **DECISION B5 (Louis):** confirm.

## C — New: manifest-coverage meta-check (keeps B1 from rotting)

**Proposed:** a unit test (not a new CLI command — smallest correct surface) that walks the tree for files defining `ConfigModel` subclasses, matches each against `config-docs`' trigger globs, and fails on any file that is neither matched nor on an explicit not-user-documented allowlist (factories, internal specs, exceptions). Lives with the drift tests, runs in `make agent-test`, needs no Makefile or CI wiring. When a new documented submodel appears in its own package, the test fails until either the trigger list or the allowlist is updated — the enumeration can no longer rot silently.

The allowlist seeding is the one judgment call: it requires classifying today's `ConfigModel` files as documented-vs-internal once, which is also the audit that settles B1's long tail (the settings-model files).

- [ ] **DECISION C (Louis):** adopt the meta-check as a unit test?

## D — Derived checks to adopt (from the campaign shortlist)

Per the manifest's own rule, anything mechanizable becomes a derived check, never a contract. The shortlist, with a proposed build order (by effort, cheapest first — the shortlist's own ranking is by value-per-effort and puts D1 first; D3 is cheaper to build, so the two orderings differ only in which ships first):

**D3 — `doc-python-snippets-import`** *(build first — lowest effort)*: import-and-`getattr` smoke check on Python symbols referenced in doc snippets. Kills the campaign's #1 cross-part defect class (renamed API never propagated into docs), which produced the worst silent failure found anywhere (mis-named observer hooks that silently no-op).

**D1 — `doc-enumerations-vs-registry`** *(build second)*: diff documented **closed** lists against the code's registries (native concepts, operator roster, model deck, config files). The diff is trivial; the design cost is encoding the exhaustive-vs-illustrative rule — only hedge-free lists are checked ("such as" / "including" / a scope qualifier exempts a list; two S2-4 refutations prove skipping scoped lists is correct, not lenient).

**D2 — `validate-doc-bundle-examples`** *(build third — highest impact, most engineering)*: extract fenced bundle examples under `docs/`, inject D11 placeholders (`description`/`domain`, tolerated-omitted prompt), scaffold D19 placeholder sub-pipes for sequence sketches, run `pipelex validate bundle`. Kills the single biggest breaks-a-user class. **Carry the F13 caveat into its output and docs: a green run verifies the snippets, never the sentences beside them.**

**Deferred (weaker / harder, revisit only if their classes recur):** `doc-python-signatures-vs-live` (keyword-only drift in snippets; needs signature resolution), `doc-toml-config-vs-shipped` (diff doc-embedded `pipelex.toml` blocks against the shipped file), `operator-param-table-vs-blueprint` (needs a Markdown table parser).

Wiring, for each adopted check: a `pipelex-dev` command mirroring the existing `check_*` family, a Make target, membership in the `make check` aggregate (hence CI). Each ships as its own PR with the docs-tree fixes its first run demands (expected to be near-zero — Stage 2 just fixed everything these checks would catch, which also makes now the cheapest moment to adopt them: they start green and stay green).

- [ ] **DECISION D (Louis):** adopt D3 + D1 + D2 in that order? All three, or a subset?

## E — New contracts

### E1 — `make-targets-and-tooling` (shortlist #4 — the clearest contract case the campaign produced)

The un-mechanizable class from A2: behavior drifting under stable target names. **Proposed contract:**

```toml
[contracts.make-targets-and-tooling]
description = "Pages that describe make targets must track the Makefile — behavior drifts under stable target names."
triggers = ["Makefile"]
review = [
  "docs/agents/debugging-hanging-pytest-runs.md",
  "docs/contribute/drift-contracts.md",
  "docs/contribute/keyword-only-arguments.md",
  "CONTRIBUTING.md",
  "pipelex/kit/agent_rules/commands.md",
  "pipelex/kit/agent_rules/codex_commands.md",
]
verify_commands = []
```

Notes: the kit agent-rules templates are the *source* of the generated repo-root `CLAUDE.md`/`AGENTS.md` — review the templates, `make rules` regenerates (the S2-4 lesson). Exact review-target list to be settled at implementation by grepping for pages that *describe* targets rather than merely invoke one (the seed contracts set this precedent). Review-target overlap with other contracts (e.g. `keyword-only-arguments.md` under both this and `keyword-only-convention`) is fine — contracts are independent obligations.

**Friction, stated honestly:** the Makefile changed 13 times in the last three months (6 in the last month) — this contract opens roughly weekly in active periods. Most acks will be the one-minute "changed recipe isn't documented" kind. If the dogfood shows reflexive acks, the design doc's remedy applies: narrow (e.g. trigger only on documented target names' recipe blocks is *not* mechanically expressible — so realistically: shrink the review list, or accept and re-verdict).

- [ ] **DECISION E1 (Louis):** adopt? Confirm or trim the review-target list.

### E2 — `drift-tool-docs` (self-hosting)

`dev_cli` is excluded from `cli-docs` (correctly), and the keyword-only guard got its own carve-out contract — but the drift tool itself didn't, though `docs/contribute/drift-contracts.md` + the drift-review skill are the same "the doc is the tool's specification" shape. Phase H changed ack semantics (auto-stage, warn→fail) and updated both docs in the same change — by discipline, not obligation. The tool that enforces review obligations should carry one for its own spec. **Proposed contract:**

```toml
[contracts.drift-tool-docs]
description = "The drift-contracts doc and the drift-review skill are the tool's specification and must track its behavior."
triggers = ["pipelex/cli/dev_cli/commands/drift/**/*.py"]
review = [
  "docs/contribute/drift-contracts.md",
  ".claude/skills/drift-review/SKILL.md",
]
verify_commands = []
```

Friction: near zero (the drift subpackage changed twice in the last month, both in one hardening wave).

- [ ] **DECISION E2 (Louis):** adopt.

### E3 — standing policy items

- **Dogfood log:** keep the mandatory one-line entry per ack through the next wave — the repaired triggers and new contracts need their own evidence, and the E1 friction estimate needs confirming in practice. Revisit once the new contracts have accumulated enough acks to judge (suggested trigger for the revisit: the first friction verdict, or a quarter, whichever comes first).
- **`lint-drift` promotion to a required CI check:** stays gated (tracked in `TODOS.md`). Flip condition: every open PR against `dev` either merged or rebased past the current acks — a required check would fail every PR that predates them. Re-check the backlog after the manifest changes from this verdict land, since those add new acks and reset the clock.
- **Agent ergonomics (the design doc's original "Phase 3"):** substantially delivered — the drift-review skill exists, the kit rules describe the workflow, and the failure messages are actionable. The remaining design-doc item (`--format json` for software consumers) is deferred until a software consumer exists (clean-solid rule: no speculative surface).

- [ ] **DECISION E3 (Louis):** confirm the three policy positions.

## F — Execution plan (once rulings are in)

**Phase V1 — manifest wave (one PR).** Apply B1 + B3 trigger repairs and add the E1 + E2 contracts to `drift.toml`; perform the initial reviews *for real* (the Phase-2-seeds precedent — note the make-targets pages were just swept and fixed by the campaign, so the first reviews should be fast but must still be genuine); record the initial acks + dogfood-log entries; update `docs/contribute/drift-contracts.md`'s contract roster and the changelog.

**Phase V2 — meta-check (same PR or a small follow-up).** The section-C unit test, including the one-time documented-vs-internal classification of `ConfigModel` files that seeds its allowlist.

### CHECKPOINT V-A

Gates green (`make agent-check`, targeted drift tests, `make docs-check`); PR to `dev`; update this doc's status and the memory. Natural handoff — V3 is independent engineering a fresh session can pick up cold from section D.

**Phase V3 — derived checks (one PR each, in D's build order).** Each: `pipelex-dev` command + Make target + `make check` membership + docs; first run against the docs tree, fix or triage anything it flags.

### CHECKPOINT V-B

All adopted checks green in CI. Re-check the `lint-drift` promotion gate (E3) against the then-current PR backlog; if clear, promote in its own small PR.

## Bottom line

The pilot answered its question: acks catch real staleness (one real-catch, zero friction verdicts, zero observed rubber-stamping), and the campaign independently confirmed both the thesis (same-commit docs don't drift) and the existence of drift classes only a review obligation can cover. The proposed growth is deliberately narrow — two contracts, four trigger repairs, three derived checks, one meta-check — and everything broad stays out, per the design's own friction principle.
