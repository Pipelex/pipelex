# Plan: unify the codegen/build underpinnings (without merging the routes)

Status: **Phases 1–4 shipped. CHECKPOINT 3 (end-to-end) is DONE.** Only Phase 5 (final sweep) and the follow-ups remain. This plan spans `pipelex-api/` (main), `pipelex/` (engine — one small typing fix landed in Phase 2; nothing further needed), the workspace spec (`Pipelex/docs/specs/pipelex-codegen.md`), and three JS consumers. No backward compatibility is owed anywhere — breaking wire changes are fine, noted in changelogs.

## Working setup — read this before touching code (cold start)

### Branch state, per repo (verified 2026-07-13)

| Repo | Branch | State |
| --- | --- | --- |
| `pipelex-api` | **`feat/build-routes-files-envelope`** | Phases 1–5. Open as **PR #39 → `feature/Codegen`** (`1facfc7`), pushed, **CI fully green + MERGEABLE**. Phase 1 already merged into `feature/Codegen` as PR #38 (`770956a`). |
| `mthds-js` | `feature/Codegen` | **Phase 4 done, pushed** (`9e19d99`). No PR yet. Re-verified green. |
| `pipelex-sdk-js` | `feature/Support-new-endpoints` | **Phase 4 done, pushed** (`7226da2`). No PR yet. Re-verified green. |
| `pipelex-app` | `feature/Codegen` | **Phase 4 done, pushed** (`73d699c` + `f13199c`). No PR yet. `f13199c` is the prettier fix — **`73d699c` alone fails `format:check`**; see the Phase 5 re-verification note. |

✅ **All four branches are pushed.** The remaining step is opening the three JS PRs. **Base them on `dev`, not `main`** — `dev` is the integration branch in all three repos (decisive in `pipelex-app`: the branch is 2 commits ahead of `dev` but 12 ahead of `main`).

| Repo | Open the PR | What it carries beyond `dev` |
| --- | --- | --- |
| `mthds-js` | [`dev...feature/Codegen`](https://github.com/mthds-ai/mthds-js/compare/dev...feature/Codegen?expand=1) | ⚠️ 4 commits — the Phase-4 one (`9e19d99`) **plus three pre-existing** agent/codegen commits (`05f9267` merge, `338f3dd`, `9ac093c`) that are not part of this plan. |
| `pipelex-sdk-js` | [`dev...feature/Support-new-endpoints`](https://github.com/Pipelex/pipelex-sdk-js/compare/dev...feature/Support-new-endpoints?expand=1) | ⚠️ 2 commits — the Phase-4 one (`7226da2`) **plus** the pre-existing E2E-suite commit (`9b0dea3`). |
| `pipelex-app` | [`dev...feature/Codegen`](https://github.com/Pipelex/pipelex-app/compare/dev...feature/Codegen?expand=1) | Exactly the Phase-4 work (`73d699c` + `f13199c`) — a clean PR. |

⚠️ **CI flakiness, not our code.** GitHub's action registry was 500ing / `Service Unavailable` throughout this session, failing jobs inside `Set up job` before any step ran (`Internal Server Error occurred while resolving "actions/checkout@v4"`). It hit PR #39's Lint, CLAAssistant, and Tests(3.12) on separate runs. If a JS PR's CI comes back red, **read the failing step before believing it** — re-running cleared it every time.

⚠️ **`pipelex-app` installs with `pnpm`, not `npm`.** `npm install` fails on an unrelated pre-existing peer-dep conflict (`@pipelex/mthds-ui` peer-wants `shiki@^3.22.0`; the root pins `^4.0.2`) and leaves a half-populated `node_modules` that makes `typecheck` report phantom "cannot find module" errors for `next-intl` etc. Use `pnpm install`. If `typecheck` reports errors inside `.next/dev/types/validator.ts`, that is a stale Next cache — `rm -rf .next`.

⚠️ Note the `pipelex-api` branch is **`feat/build-routes-files-envelope`, not `feature/Codegen`** — an earlier version of this doc said otherwise. `feature/Codegen` is the *integration base* every PR in this plan targets; it is not where the work happens. Open Phase-4 PRs against each repo's own base, not `main`.

**Nothing in Phase 4 requires the server to change.** The wire shapes are already captured verbatim below ("The new wire shapes"), so a cold start does not need to re-read the server or re-run it just to learn the contract. You only need a running server for CHECKPOINT 3's end-to-end pass.

**The engine is pinned by git rev — you do NOT need a local editable `pipelex`.** `pyproject.toml` has:

```toml
[tool.uv.sources]
pipelex = { git = "https://github.com/Pipelex/pipelex.git", rev = "4519ae3d7ef6bc0ffe1d7d6eeed364171b87e1a3" }
```

That rev is the tip of the `pipelex` repo's **`feature/Stabilize`** branch, which is checked out locally in the **`../_stable` worktree** (`../pipelex` itself is on `dev` and must stay clean — do not work there). The pin replaced a local editable path (`path = "../pipelex", editable = true`) that **could never install in CI** — a GitHub runner has no sibling checkout, so `uv sync` failed before any test ran. Keep the git pin: it is what makes CI green.

**Phase 4 needs no engine change** (it is JS/TS consumers only). Phases 2–3 needed exactly one, and it landed — see below.

**The one engine change Phases 2–3 did need** (the plan predicted none; this was the miss): `validate_bundle`'s `mthds_sources` param was annotated `list[str] | None`, while its sibling `resolve_crate_from_contents` takes `Sequence[str | None] | None` — and `validate_bundle`'s own **body already handled `None` entries**. The annotation was just narrower than the implementation, and it blocked `/build/runner` (the one build route that must keep `validate_bundle`) from threading the `files[]` envelope's optional per-file `source` labels. Widened to match the sibling; strictly widening, so no caller could break and no runtime behavior changed. Landed on `feature/Stabilize` as **`4519ae3`**, and the pin above was bumped to it.

**If a further engine change turns out to be needed** (only then), the loop is:

1. Iterate locally without touching the committed pin: `uv pip install -e ../_stable` into `pipelex-api`'s venv. This does *not* modify `pyproject.toml` / `uv.lock`, so CI stays green while you experiment. ⚠️ Any `make install` / `uv sync` re-pins the venv back to the git rev and silently undoes this — re-run the `uv pip install -e` after one.
2. When the engine change is settled: commit it in `../_stable`, push to `feature/Stabilize`, then **bump `rev` in `pyproject.toml` and re-run `uv lock`**. Skipping the bump means `pipelex-api` CI silently tests against stale engine code.
3. **Never commit an editable path pin.** At release this all reverts to a plain `pipelex[...]==<version>` PyPI pin once a `pipelex` release ships `codegen`.

## Background — read this first on a cold start

The question that triggered this plan: *should `POST /v1/codegen` and `POST /v1/build/inputs` be united into one route?* The answer is **no — but they must share more of their underpinnings than they do today.** The full reasoning:

**The dividing line is tracked-artifact vs editable scaffold, not codegen vs build.** The engine draws it explicitly in `pipelex/pipelex/codegen/emission.py` (module docstring): "Input templates (`codegen inputs`) are deliberately *not* stamped or locked: they are user-editable scaffolds, not tracked generated code." `/codegen`'s whole contract is the stamp/lock/offline-check trust chain (`CodegenValidReport.lock` is required; the docstring promises byte-identical materialization and a passing offline `codegen check`). An `inputs` kind cannot honor that, and the axes don't align either: `target` (ts-zod / python-pydantic / python-structures) is meaningless for inputs, while inputs' own axes (json/toml format, `--explicit`) are meaningless for types. Merging would fork the request and response contracts per kind — unification in name only.

**The durable route-membership rule** (this is the principle every change below serves): *a projection that rides the stamp/lock trust chain lives on `/codegen` (per-pipe kinds select via the already-reserved `pipe_ref` field); an editable scaffold lives on `/build`.* Future per-pipe kinds from the spec (`docs`, `tools`, `tests`) will be stamped generated code → they land on `/codegen`. Inputs stays on `/build` for a reason that won't age.

**Drift discovered while answering the question** (these are the things to fix):

1. **Stated rationale is incidental, not principled.** `CodegenRouteKind`'s docstring (`api/routes/pipelex/codegen.py`) justifies the split as "mirroring the agent CLI's deliberate absence of a `codegen inputs` mirror" — which wobbles the moment you notice the *bare* CLI **does** have `pipelex codegen inputs` (`pipelex/pipelex/cli/commands/codegen/inputs_cmd.py`). Replace with the trust-chain rule.
2. **Engine docstring contradiction.** `CodegenKind`'s docstring (`pipelex/pipelex/codegen/emitters/target.py`) claims "Only the kinds that emit tracked artifacts today are listed: `types` … and `inputs`", directly contradicting `emission.py`'s "inputs deliberately not stamped or locked". `emission.py` is authoritative — the CLI writes inputs via plain `save_text_to_path`, bypassing the stamping layer entirely.
3. **Request-envelope drift.** `/resolve` and `/codegen` ride `MthdsFilesRequest` (`files[]` with per-file `source` labels XOR `method_ref`, 501 until the method registry lands) — `api/schemas/models.py`. The `/build/*` routes still ride the older `MthdsContentsRequest` (bare `mthds_contents` strings + `allow_signatures`). Consequences: build diagnostics can't carry a `source`, and when `method_ref` resolution lands, `/build/*` needs a second breaking migration.
4. **Verdict-vocabulary divergence.** The bare CLI's `pipelex codegen inputs` is **static** (crate loader, no dry-run), while `/build/inputs` and `/build/output` **dry-run** the requested pipe via `validate_bundle(dry_run_pipe_codes=[...])`. Same projection, two verdict semantics. The engine treats template rendering as a static read of declared inputs; runnability is `/validate`'s vocabulary. `/build/runner` is different: it genuinely needs the dry-run (a pipe recorded SKIPPED by the sweep → honest 422, per spec).

**Key plumbing fact enabling the fix:** `resolve_requested_crate()` in `api/routes/pipelex/crate_ops.py` inherits the engine's loaded-on-success contract — on success the library is loaded + current so a route can read live pipes from it (its docstring literally names "input templates" as the use case), and the route owns teardown via `teardown_current_library()`. So `/build/inputs` and `/build/output` can become thin per-pipe reads over the *same* core `/codegen` uses: shared closure selector, shared static resolution, shared `CrateInvalidReport` invalid arm — two presentations of one engine. That is the real unification.

**Consumers of `/build/inputs` today** (all post `{mthds_contents, pipe_code}`):

- `mthds-js/src/runners/api/client.ts` — `buildInputs()` (posts to `build/inputs`)
- `pipelex-sdk-js/src/client.ts` — `buildInputs()` (same shape)
- `pipelex-app/src/actions/build-inputs.ts` — `buildInputsTemplate()` server action → `src/components/deploy/deploy-dialog.tsx` (+ its `__tests__`), `src/lib/deploy-snippets.ts`
- `pipelex-api/.claude/skills/postman-bundle/` — request templates for the build routes (**done in Phase 3** — it lives in this repo, so it shipped with the server change rather than waiting for Phase 4)
- `n8n-nodes-pipelex/` — checked: does **not** call `build/inputs`

**Reference implementations to mirror:** `pipelex/pipelex/cli/commands/codegen/inputs_cmd.py` (per-pipe selection over a loaded crate: qualified `--pipe` ref, defaults to the closure's `main_pipe`) and `api/routes/pipelex/codegen.py` (the `resolve_requested_crate` → work → `teardown_current_library()` in `finally` pattern).

**Spec anchor:** `Pipelex/docs/specs/pipelex-codegen.md` — sections "Two axes", the HTTP request-envelope paragraph, and the paragraph describing the `/v1/build/*` migration onto the verdict discipline. Spec edits ride the same phase as the code they describe; run `make check-spec-links` in `conformance/` after spec edits.

## Decisions

All decisions are taken (conversation of 2026-07-13). None remain pending.

- **Do not merge** `/codegen` and `/build/inputs`. Adopt the trust-chain rule as the stated route-membership criterion.
- **Migrate `/build/*` onto the `MthdsFilesRequest` selector** (`files[]` XOR `method_ref`), breaking the wire shape.
- **Make `/build/inputs` and `/build/output` static** (ride `resolve_requested_crate`, drop the dry-run). `/build/runner` keeps its dry-run (SKIPPED detection is load-bearing).
- `allow_signatures` disappears from `/build/inputs` and `/build/output` (it only parameterized the dry-run sweep). `/build/runner` keeps it.
- **D1 — pipe selector:** `pipe_ref` — qualified `domain.pipe_code`, **optional**, defaulting to the closure's declared `main_pipe` (422 when omitted and the closure declares none). Replaces `pipe_code` on all three build routes. Matches `pipelex codegen inputs --pipe` and the field `/codegen` reserves. Mirror `inputs_cmd.py` for the default-resolution semantics.
- **D2 — `CodegenKind.INPUTS`:** **remove it** from the engine enum; the enum is the stamped-kind vocabulary and nothing can ever stamp an inputs file. The Phase-1 grep is a verification step, not a decision gate — if it turns up a live reference (stamp parsing, telemetry), surface it before proceeding rather than silently keeping the member.
- **D3 — CLI parity on `/build/inputs`: FULL parity** (user chose this over the light-JSON-only recommendation). The request gains `format` (`json` | `toml`, default `json` — reuse `InputsTemplateFormat` from `pipelex.pipe_machinery.rendering.input_renderer`) and `explicit` (bool, default false — the ceremonial `{concept, content}` envelope). Render via the same `render_inputs` / `render_inputs_toml` the CLI uses, and mirror the CLI's semantics exactly, including which `format`×`explicit` combos it allows or rejects. **Response-shape consequence:** TOML cannot ride as a parsed dict — the valid arm must carry the template as a parsed `dict` for `format=json` but a raw string for `format=toml`. Design this deliberately in Phase 2 (e.g. echoed `format` + a single content field whose JSON type follows it, or two mutually exclusive fields with a model validator) — do not silently stringify the JSON case, since the dict shape is what the deploy dialog and SDKs consume.
- **D4 — sequencing:** Phase 1 ships as **its own PR** (non-breaking hygiene lands immediately); the breaking migration (Phases 2–4) follows as a coherent breaking change.

## Phase 1 — rationale & engine hygiene (non-breaking, shippable as its own PR per D4) — ✅ DONE

- [x] `pipelex/`: grep usages of `CodegenKind.INPUTS`, then **remove it** per D2. **Outcome: it was dead.** Every construction site in the repo (stamp writer, emission, both CLIs, agent CLI, `build runner`, all tests) passes `CodegenKind.TYPES`; nothing anywhere referenced `.INPUTS`. Removed with no call-site changes.
- [x] `pipelex/`: fix the `CodegenKind` docstring in `pipelex/codegen/emitters/target.py` — now states the trust-chain rule ("a kind is a member exactly when its artifacts ride the stamp/lock/offline-check trust chain"), names input templates as the standing counter-example, and points at `emission.py`. The module docstring's `kind`-axis parenthetical no longer names `inputs` as an enum value.
- [x] `pipelex/`: spec adjusted — new **"Tracked artifact vs editable scaffold"** paragraph in `Pipelex/docs/specs/pipelex-codegen.md` → "Two axes". `make check-spec-links` in `conformance/`: **OK** (no headings renamed, so all `> Verified by:` links hold).
- [x] `pipelex-api/`: `CodegenRouteKind` docstring in `api/routes/pipelex/codegen.py` rewritten to the trust-chain rule; `docs/codegen.md` `kind` bullet rewritten to match.
- [x] Changelogs — see the **deviation** recorded at the checkpoint below: no standalone `pipelex/` entry (the enum is unreleased); `pipelex-api/`'s existing `[Unreleased]` `/v1/codegen` bullet reworded to carry the trust-chain rationale. The docstring **is** wire-visible → `make openapi-export` run, artifact committed (diff is the `CodegenRouteKind.description` only; the enum's served values were already just `types`).
- [x] `make agent-check` + `make agent-test` in both repos — all green. Also `make openapi-check` in `pipelex-api`: artifact up to date.

**CHECKPOINT 1** — reached 2026-07-13. Phase 1 is self-contained and non-breaking; Phase 2 can start in a fresh session.

**D2 outcome (settled, no surprise).** `CodegenKind.INPUTS` was a dead member. Beyond the grep: `pipelex/codegen/` **does not exist at the latest tag (`v0.38.0`)** — the whole codegen engine is unreleased — so its removal cannot break a released surface, and no stamp with an `inputs` projection line has ever been written by any shipped version (`stamp.py::_kind_from_value` will now simply fail to parse a hand-forged one, which is correct). The trust-chain rule is confirmed *in code*, not just in prose: `pipelex/cli/commands/codegen/inputs_cmd.py` writes templates with a plain `save_text_to_path`, never touching `apply_stamp` or the lock.

**Deviation from the plan (deliberate): no standalone `pipelex/` changelog entry.** The plan called for one ("docstring/enum hygiene"), but `CodegenKind` ships for the *first* time in the same `[Unreleased]` block — a "removed `CodegenKind.INPUTS`" bullet would document the removal of something that same release introduces, i.e. pure churn for the reader. Verified instead that the existing `[Unreleased]` text is already accurate and already states the rule ("Input templates (`codegen inputs`) are deliberately not stamped or locked — they are user-editable scaffolds, not tracked generated code"). `pipelex-api` is the same case (the `/v1/codegen` route is also unreleased), so its `[Unreleased]` bullet was **reworded in place** rather than given a new entry.

**Extra fix, same drift, not in the original box list.** Drift #1 (the incidental "mirroring the agent CLI" rationale) was *also* present in the spec's "Route envelopes" section, i.e. in the most authoritative document. Fixed there too — it now defers to the trust-chain rule. Left deliberately alone: the spec's *agent-CLI* sentence ("there is deliberately no `pipelex-agent codegen inputs` — the existing `pipelex-agent inputs` group already surfaces that projection"). That statement is about the agent CLI's own surface and is true on its own terms; the drift was only ever in *borrowing* it as the route-membership reason.

**Everything in Phase 1 is committed, pushed, and merged** (see "Working setup" at the top for the resulting branch/pin state):

- `pipelex-api/`: `api/routes/pipelex/codegen.py`, `docs/codegen.md`, `CHANGELOG.md`, `docs/openapi/pipelex-api.openapi.yaml`, `pyproject.toml` + `uv.lock` (the git pin), `TODOS.md` — **PR #38, merged into `feature/Codegen` as `770956a`.** CI green on 3.11/3.12/3.13.
- `pipelex/`: `pipelex/codegen/emitters/target.py` — pushed on **`feature/Stabilize`** as `27e6f3e` (worked in the `../_stable` worktree). That push also carries a second, pre-existing commit found uncommitted in the worktree and included with the user's approval: `e464c428` `fix(codegen): emit class docstrings as real triple-quoted strings` (`codegen/emitters/python_common.py` + its test) — `class_docstring` was returning a single-quoted literal from `escape_py_string` instead of a real triple-quoted docstring.
- workspace: `docs/specs/pipelex-codegen.md` — pushed on **`feature/Follow-ups`** as `428c20f`.

**The dependency pin was the load-bearing surprise of Phase 1.** `pipelex-api` CI had been failing at the install step on every run: the pin was a local editable path that cannot exist on a runner. Fixed by the git-rev pin. Full detail in "Working setup" above — read it before Phase 2.

**Carried into Phase 2 (found while reading, saves a re-read).** `inputs_cmd.py::_default_main_pipe_ref` is the reference semantics for D1's optional `pipe_ref`: it collects `f"{domain_code}.{domain.main_pipe}"` over every domain in the crate that declares one, then errors on **zero** candidates *and* on **more than one** (ambiguous closure). The route must mirror both arms — the plan's D1 only names the zero case ("422 when omitted and the closure declares none"); **the ambiguous case needs a 422 too.** Pipe lookup itself is `get_required_pipe(pipe_code=<qualified ref>)`, raising `PipeLibraryError` on a bad ref (→ 422, a request-shape error, not an invalid-crate verdict).

## Phase 2 — server: `/build/inputs` + `/build/output` → files[] envelope + static core — ✅ DONE

- [x] New request base `MthdsPipeRequest(MthdsFilesRequest)` in `api/schemas/models.py`: adds optional qualified `pipe_ref` (bounded by `MAX_PIPE_CODE_LEN`). `allow_signatures` dropped from the static routes; the shared description moved to an `ALLOW_SIGNATURES_DESCRIPTION` constant so `/validate` and `/build/runner` cannot drift apart on it.
- [x] `/build/inputs` gains `format` (`InputsTemplateFormat`, default json) + `explicit` (default false), per D3. **All four `format`×`explicit` combos are served** — verified against `inputs_cmd.py::_render`, which rejects none of them.
- [x] Valid arms designed for the dict-or-string consequence: **two mutually exclusive fields + a `model_validator`**, chosen over a `dict | str` union so the JSON case stays a real object for the deploy dialog and SDKs. Dumped with `exclude_none=True`, so the field the format did not select is **absent** from the body, not `null`.
- [x] `inputs.py` and `output.py` rewritten over `resolve_requested_crate` → `resolve_requested_pipe` → render → `teardown_current_library()` in `finally`. Both declare `501: PROBLEM_501_METHOD_REF`.
- [x] Valid arms echo `pipe_ref` (resolved) + `requested_pipe_ref` (as submitted; absent when defaulted).
- [x] Tests: new `tests/unit/test_build_routes_envelope.py` (the migration's pin — selector defaulting incl. both un-defaultable arms, source-label threading, format×field mapping, 501, library conservation); `test_build_and_agent_routes.py` + `test_allow_signatures.py` updated. `test_openapi_contract.py` unchanged and still green (these routes were never tagged).
- [x] Docs: `docs/pipe-builder.md` rewritten (shared envelope + static-vs-runner semantics + the format→field rule); `docs/index.md` catalog refreshed. `docs/codegen.md` needed no change (its trust-chain bullet already pointed at `/build/inputs`).
- [x] Spec: `Pipelex/docs/specs/pipelex-codegen.md` → "Route envelopes" gains three paragraphs (shared envelope + pipe selector; static projection vs. runnable promise; the format axis deciding the payload's JSON type). `make check-spec-links` in `conformance/`: **OK**.
- [x] `make openapi-export` + artifact committed; CHANGELOG entries. `make agent-check` + `make agent-test` + `make openapi-check` — all green **against the pinned engine** (not just the editable one).

**Two pre-existing bugs found and fixed while here** (workspace rule: flag and fix):

1. **`/v1/build/output` with `format=python` was a hard 500.** The route ran `json.loads` on *every* format and typed the field `dict`, so the Python-source representation crashed on arrival. Confirmed live before touching it (`schema`→200, `json`→200, `python`→**500**). The dict-or-string design D3 forced for inputs+TOML is exactly the fix, so `output` (object, for `schema`/`json`) and `output_python` (text) now split the same way. **This is why `/build/output` did NOT keep its `output: dict` shape unchanged, as the plan's Phase-2 box assumed** — that box was written before the bug was known.
2. **`render_output`'s bare `ValueError`** (a `native.Anything` output with no determinable options — documented in its docstring) escaped as an unhandled 500. Now a request-shape 422: it is a fact about the requested *pipe*, not an invalid-closure verdict.

## Phase 3 — server: `/build/runner` → files[] envelope (keeps its dry-run) — ✅ DONE

- [x] **Assessment (the plan said "assess, don't force"): `/build/runner` cannot use `resolve_requested_crate` — do not try.** It must ride `validate_bundle` for the dry-run sweep, and `validate_bundle` already leaves its own library loaded + current; calling `resolve_requested_crate` would open a **second** library and orphan the first (the exact leak `test_build_routes_envelope.py::test_routes_open_exactly_one_library_and_tear_it_down` pins). Its crate still comes from `library_manager.get_crate(library_id)` + `normalize_crate`. What it *does* now share: `selected_files` (the `method_ref`→501 guard, extracted for it), `resolve_requested_pipe`, `teardown_current_library`, `invalid_crate_report_response`.
- [x] `BuildRunnerRequest(MthdsPipeRequest)` + `allow_signatures` (kept — the sweep needs it).
- [x] SKIPPED → 422 carve-out and the stamped structures projection kept exactly as spec'd (the guard is now keyed by the resolved qualified `pipe_ref`).
- [x] Tests, docs, spec, `make openapi-export`, CHANGELOG, `make agent-check` + `make agent-test`.

**Two contract bugs the PR review caught (both fixed, both now pinned by regression tests that fail without the fix):**

- **The echoed `pipe_ref` was the *submitted* string, not the resolved one.** The engine's pipe lookup accepts a bare code (falling back across domains), so a caller sending `pipe_ref: "echo"` got `pipe_ref: "echo"` back — unqualified, breaking the valid arm's own promise. The resolved ref is now read off the live pipe (`the_pipe.pipe_ref`), never echoed from the request.
- **`/build/runner` could read the wrong pipe's output multiplicity.** A blueprint's `pipe` map is keyed by *bare* code, and `_output_is_list` scanned by bare code alone — so in a closure where two domains declare the same pipe name, it matched whichever blueprint came first and could emit a scalar runner for a list-output pipe. It now compares the owning domain too.

**Three sharp edges found in Phase 3 — read before touching `runner.py` again:**

- **`dry_run_pipe_codes` cannot be scoped when `pipe_ref` is omitted.** The default resolves off the *crate*, which only exists after `validate_bundle` has run — chicken-and-egg. So an omitted `pipe_ref` sweeps the **whole closure** (`dry_run_pipe_codes=None`) and then defaults to `main_pipe`. That is a stricter verdict than the scoped path (a broken *sibling* pipe can now sink the request), which is the honest answer for a caller who did not say which pipe they meant. Documented in the route docstring, the spec, and `docs/pipe-builder.md`.
- **`_output_is_list` needs BOTH halves of the qualified ref.** It looks the pipe up in `blueprint.pipe`, which is a per-bundle map keyed by *bare* code — so it must split the qualified ref and match the blueprint's `domain` as well. Feeding it the qualified ref whole silently returns `False` for every pipe; feeding it the bare code alone silently matches a same-named pipe in another domain (the bug the review caught). (`_reject_if_requested_pipe_skipped` is more forgiving — it matches on *either* spelling, so the qualified ref is fine there.)
- **`PipeNotFoundError` escapes `validate_bundle` untranslated, deliberately** — the engine's `translate_to_validate_bundle_error` has an explicit `except PipeNotFoundError:` arm that re-raises so callers can own it. The route now catches it → **422** (a pipe ref naming nothing in the closure is a request-shape error, not an invalid-closure verdict), matching what `resolve_requested_pipe` does on the static routes. Before this it would have surfaced as a generic PipelexError problem document.

**CHECKPOINT 2** — reached 2026-07-13. Server surface fully migrated; the OpenAPI artifact is regenerated and committed. Consumers are now broken against a locally-run server — that is Phase 4.

### The new wire shapes (captured live from the running server — Phase 4 needs no server re-read)

**Shared request envelope** (all three): `files[]` (each `{content, source?}`) **XOR** `method_ref` (→ 501), plus optional qualified `pipe_ref` (defaults to the closure's `main_pipe`; 422 when the closure declares none, or several).

```jsonc
// POST /v1/build/inputs  — request
{ "files": [{ "content": "<mthds text>", "source": "smoke.mthds" }],
  "pipe_ref": "smoke.echo",           // optional
  "format": "json",                   // "json" (default) | "toml"
  "explicit": false }                 // default false
// 200 valid arm (format=json)
{ "is_valid": true, "pipe_ref": "smoke.echo", "requested_pipe_ref": "smoke.echo",
  "format": "json", "explicit": false,
  "inputs": { "text": "text_value" },
  "message": "Inputs template generated successfully" }
// 200 valid arm (format=toml) — note `inputs` is ABSENT, and the concept comment is
// precisely what a parsed-dict shape would have destroyed. This is D3's whole point.
{ "is_valid": true, "pipe_ref": "smoke.echo",   // requested_pipe_ref absent = it was defaulted
  "format": "toml", "explicit": false,
  "inputs_toml": "# concept: native.Text\ntext = \"text_value\"\n",
  "message": "Inputs template generated successfully" }
```

```jsonc
// POST /v1/build/output  — request
{ "files": [{ "content": "<mthds text>" }],
  "pipe_ref": "smoke.echo",           // optional
  "format": "schema" }                // "schema" (default) | "json" | "python"
// 200 valid arm (schema|json → parsed object in `output`)
{ "is_valid": true, "pipe_ref": "smoke.echo", "requested_pipe_ref": "smoke.echo",
  "format": "schema",
  "output": { "concept": "native.Text",
              "content": { "type": "object", "title": "TextContent",
                           "properties": { "text": { "type": "string", "title": "Text", "description": "The text" } },
                           "required": ["text"] } },
  "message": "Output representation generated successfully" }
// 200 valid arm (python → source text in `output_python`; `output` ABSENT)
{ "is_valid": true, "pipe_ref": "smoke.echo", "format": "python",
  "output_python": "<python source>", "message": "..." }
```

```jsonc
// POST /v1/build/runner  — request
{ "files": [{ "content": "<mthds text>" }],
  "pipe_ref": "smoke.echo",           // optional
  "allow_signatures": false }         // ONLY this build route still takes it
// 200 valid arm (unchanged apart from the selector fields)
{ "is_valid": true, "pipe_ref": "smoke.echo", "requested_pipe_ref": "smoke.echo",
  "python_code": "<python source>",
  "structures": { "directory": "structures",
                  "artifacts": [{ "path": "structures.py", "content": "# >>> pipelex-codegen-stamp >>>\n..." }],
                  "lock": "<toml>", "lock_filename": "codegen.lock" },
  "message": "Runner code generated successfully" }
```

**Invalid arm (all three, 200):** unchanged — `{ "is_valid": false, "validation_errors": [...], "message": "..." }`, and `validation_errors[].source` now carries the submitted per-file label.

**Non-2xx (all three):** 422 for an unknown `pipe_ref`, an omitted `pipe_ref` on a closure with no/several `main_pipe`, a malformed selector, an unrenderable `native.Anything` output (`/build/output`), or a SKIPPED requested pipe (`/build/runner`); 501 for `method_ref`; auth 401/403; 5xx server fault. All RFC 7807 `problem+json`.

**Renamed/removed fields Phase 4 must chase:** `mthds_contents[]` → `files[]`; `pipe_code` → `pipe_ref` (**and it is now qualified** — `smoke.echo`, not `echo`); `allow_signatures` gone from `/build/{inputs,output}`; valid arms echo `pipe_ref`/`requested_pipe_ref` instead of `pipe_code`.

## Phase 4 — consumers

**Do these in dependency order: `mthds-js` → `pipelex-sdk-js` → `pipelex-app`.** (One-way dep: `@pipelex/sdk → mthds`.)

- [x] **`mthds-js` — DONE.** Committed on `feature/Codegen` as **`9e19d99`** (not pushed, no PR). `npm run check` (lint, format, both typechecks, build, depcruise) + all tests green. Scope was **wider than this box predicted** — see "What Phase 4 found in `mthds-js`" below before starting the next repo; it is the most useful thing in this file right now.
- [x] **`pipelex-sdk-js` — DONE.** Committed on `feature/Support-new-endpoints` as **`7226da2`**. `npm run check` + 134 unit tests + 24 e2e tests (live server) all green. The `mthds-js` type set was mirrored almost verbatim into `src/models.ts`, the three client methods typed, and the new types re-exported from `src/index.ts`.
  - **Extra, beyond the box (deliberate — flag-and-fix):** the build routes were the **only `/v1` routes still throwing a bare `Error`** on non-2xx (they rode `requestJson`, whose docstring claimed they were "surfaces that don't need the protocol's structured error taxonomy"). That was true when they returned untyped payloads and is false now that they have a real no-verdict taxonomy — a caller cannot tell a 422 (bad `pipe_ref`) from a 501 (`method_ref`) from a 5xx by matching on a message string. They now ride the same problem-aware helper as `lint`/`format` (renamed `requestTool` → `requestExtension`) and throw the typed `ApiResponseError`. `concept`/`pipeSpec` moved over too, which left `postApi` dead — removed. `requestJson` survives only for the origin-level `/health` probe.
  - **Confirmed while here:** the build types really are SDK-local (no `mthds/protocol` change needed), and `MthdsFile {content, uri?}` (the `validateFiles()` adapter) really is a different type from the build envelope's `MthdsFileItem {content, source?}`. Both kept distinct, as planned.
- [x] **`pipelex-app` — DONE.** Committed on `feature/Codegen` as **`73d699c`**. 1011 tests + typecheck + lint + format all green. Both predicted bugs were real and are fixed (`buildInputsTemplate` returned the whole envelope as the template, and its `!res.ok` guard never fired on the 200 invalid arm). `selectMainPipeRef()` added as the qualified sibling; `SnippetSource.pipeCode` → `.pipeRef`; `selectMainPipe` left alone for `/execute`. As predicted, `src/lib/deploy-snippets.ts` needed **no change**.
  - **Reused rather than re-derived:** `src/lib/pipe-io-contracts.ts` already exported `buildPipeRef(domain, pipeCode)` — the existing single source of truth for the `domain.pipe_code` convention. `selectMainPipeRef` calls it.
  - New `src/lib/__tests__/pipe-selection.test.ts` pins why the two selectors stay separate (the bare code feeds `/execute`; the qualified one feeds `/build/*`) and that the first-pipe fallback survives qualification — the case the server's `main_pipe` default cannot serve.
- [x] `pipelex-api/.claude/skills/postman-bundle/`: done in Phase 3 (in-repo, so it could not be left broken behind the server change). `build_postman_query.py::build_build_body` now emits the `files[]` envelope + a qualified `pipe_ref` (built from the bundle's `domain` + `main_pipe`), and sends `allow_signatures` **only** for `build-runner`. Smoke-tested against `postman/sample-bundles/fashion_moodboard.mthds`. ⚠️ Still to do: run `/update-postman` if the **live Postman collection** carries the old shapes.
- [x] Each repo: its own test suite + changelog + docs. `mthds-js` (`9e19d99`, adds `docs/build-routes.md`), `pipelex-sdk-js` (`7226da2`, adds `docs/build-routes.md`), `pipelex-app` (`73d699c`, updates `docs/method-deploy.md`).

### What Phase 4 found in `mthds-js` (read before starting `pipelex-sdk-js` / `pipelex-app`)

**The consumer surface is bigger than "a client method".** `mthds-js` needed all of: the request/response types (`src/runners/types.ts`), the API client (`src/runners/api/client.ts`), **a second `Runner` implementation** (`src/runners/pipelex/runner.ts` — shells out to the local CLI), the **user CLI** (`src/cli/commands/build.ts` + the option declarations in `src/cli.ts`), and the **agent CLI** (`src/agent/commands/api-commands.ts`). Expect the same for `pipelex-app`: the server action is not the only thing that moves.

**Design call — the build request types stay WIRE DTOs.** They are posted verbatim (`postApi(path, request)`), so they keep snake_case and the literal `files: [{content, source?}]` shape rather than being wrapped in an ergonomic client type. This is why they do NOT reuse the existing `MthdsFile { content, uri? }` (whose `uri` maps to `/validate`'s `mthds_sources`): `/validate` and `/build/*` genuinely spell the label differently on the wire today. When `/validate` migrates to `files[]` (the follow-up below), the two collapse into one — until then, keeping them distinct is honest and keeps "the request type IS the body" true. **Mirror this choice in `pipelex-sdk-js`.**

**Three bugs the typed union exposed** (all fixed in `mthds-js`, all worth checking for in the other consumers):

1. **The two runners disagreed about `buildInputs`'s return.** The API runner returned the bare template; the local runner returned the agent CLI's `{success, pipe_code, inputs}` envelope. Both sat behind one interface typed `Promise<unknown>` — which is precisely what let the divergence hide for so long. Typing the union forced it out. Both now return the template under `inputs`.
2. **The local runner defaulted `buildOutput`'s `format` to `json`; the API defaults to `schema`.** One interface, two meanings. Aligned on `schema`.
3. **The local runner echoed an unresolved pipe ref** — the same class of bug the PR review caught server-side in Phase 3. It now resolves the qualified ref itself (`src/runners/pipe-ref.ts`, mirroring `inputs_cmd.py::_default_main_pipe_ref`'s zero/ambiguous arms) and passes it to `--pipe` explicitly, so what it echoes is what it asked for.

**The invalid arm is the easy thing to get wrong in a consumer.** A bad closure comes back as a **200** with `is_valid: false`, so any consumer that only catches throws will render a success over an unusable result. `mthds-js`'s CLI needed an explicit `reportIfInvalid` and the agent CLI an explicit verdict branch.

**The TS type set to mirror in `pipelex-sdk-js`** (from `mthds-js/src/runners/types.ts` — copy it, don't re-derive it):

```ts
interface MthdsFileItem { content: string; source?: string }
interface BuildRequestBase { files?: MthdsFileItem[]; method_ref?: string; pipe_ref?: string }
type InputsTemplateFormat = "json" | "toml";
type ConceptRepresentationFormat = "json" | "python" | "schema";

interface BuildInputsRequest extends BuildRequestBase { format?: InputsTemplateFormat; explicit?: boolean }
interface BuildOutputRequest extends BuildRequestBase { format?: ConceptRepresentationFormat }
interface BuildRunnerRequest extends BuildRequestBase { allow_signatures?: boolean }  // only this one keeps the flag

interface CrateInvalidReport { is_valid: false; validation_errors: ValidationErrorItem[]; message: string }
interface BuildValidReportBase { is_valid: true; pipe_ref: string; requested_pipe_ref?: string; message: string }

// The payload field follows `format`; the unused one is ABSENT from the body, not null.
interface BuildInputsValidReport extends BuildValidReportBase { format: InputsTemplateFormat; explicit: boolean; inputs?: Record<string, unknown>; inputs_toml?: string }
interface BuildOutputValidReport extends BuildValidReportBase { format: ConceptRepresentationFormat; output?: Record<string, unknown>; output_python?: string }
interface BuildRunnerValidReport extends BuildValidReportBase { python_code: string; structures: RunnerStructures }
interface RunnerStructures { directory: string; artifacts: { path: string; content: string }[]; lock: string; lock_filename: string }

type BuildInputsResponse = BuildInputsValidReport | CrateInvalidReport;   // and the two siblings
```

### `pipelex-app` — the concrete work (scope is NARROWER than the original box claimed)

**`src/lib/deploy-snippets.ts` needs no change.** It only consumes the resolved inputs *object* and renders `/v1/execute` snippets keyed by `method_id`; it never touches the build wire shape. (It matched the plan's original grep only via a doc comment and its own `buildCurlSnippet`/`buildPythonSnippet`/… function names — a false positive. Its line-5 comment "from `POST /v1/build/inputs`" stays true.)

**`src/actions/build-inputs.ts` has a bug that this migration makes live.** It ends with `const data = (await res.json()) as InputsTemplate; return success(data);` — i.e. it treats the whole response body as the template. Post-migration the body is the *report envelope*, so the deploy dialog would embed `{is_valid, pipe_ref, format, explicit, inputs, message}` into the user-facing snippets instead of the inputs. It must:
  1. post the new payload (`files: [{content}]` + a qualified `pipe_ref`; no more `mthds_contents`/`pipe_code`),
  2. branch on `is_valid` — the invalid arm is a **200**, so `res.ok` is true and today's `!res.ok` guard never fires,
  3. return `data.inputs` (the `format=json` field), not `data`.

**The pipe selector needs qualifying — the app cannot lean on server defaulting.** `selectMainPipe()` (`src/lib/pipe-selection.ts`) returns a **bare** code, and when the blueprint declares no `main_pipe` it falls back to *the first pipe key*. Omitting `pipe_ref` would therefore 422 on exactly the methods that have no `main_pipe` — the case that fallback exists to serve. The blueprint carries `domain` (`src/types/core/pipelex-bundle-blueprint.ts:6`), so qualify with it. **Leave `selectMainPipe` alone** — it also feeds `/execute` (`method-run-workspace.tsx:195`), which still takes a bare `pipe_code` — and add a qualified sibling for the build call.

**`SnippetSource.pipeCode` becomes a qualified ref.** It is defined in `deploy-dialog.tsx` and produced by three call sites: `playground/toolbar.tsx:144` (has the blueprint → can qualify), `method-run/run-header.tsx` (takes it as a prop from its page), and `deploy/deploy-button.stories.tsx`. The dialog consumes it only for the build fetch and its `sourceKey` cache key, so renaming it to `pipeRef` is clean.

### Commands (per repo)

```bash
# mthds-js / pipelex-sdk-js  (npm)
npm run check     # lint + format:check + typecheck + typecheck:test + build + depcruise
npm test          # vitest
npm run format    # prettier --write (run before `check`; it will fail on format drift otherwise)
npm run test:e2e  # pipelex-sdk-js only — drives a LIVE server (PIPELEX_E2E_BASE_URL, default :8081)

# pipelex-app  (pnpm — NOT npm; see the cold-start warning above)
pnpm install && pnpm run typecheck && pnpm run lint:check && pnpm run format:check && pnpm test

# pipelex-api (needed for the e2e / live runs)
make run          # uvicorn on :8081, hot reload
```

**CHECKPOINT 3** — reached 2026-07-13. **All three consumers were driven against a live `make run` server, and all three pass.** The end-to-end pass this checkpoint existed to force is done.

What was run, and how it is now pinned:

| Consumer | How it was exercised live | Left behind as a regression net |
| --- | --- | --- |
| `pipelex-sdk-js` | `npm run test:e2e` — a new **`tests/e2e/build.e2e.ts`** driving all three routes against `localhost:8081`. | ✅ Permanent (24 e2e tests; excluded from `make test` so CI never needs a server). |
| `mthds-js` | Scratch script over `MthdsApiClient` (all three routes + the invalid arm). All checks passed, **including both bugs its migration fixed** (`buildOutput` defaults to `schema`; the echoed `pipe_ref` is resolved). | ❌ Scratch only — see follow-ups. |
| `pipelex-app` | Scratch script replaying `buildInputsTemplate`'s **exact** body + response handling. Confirmed the template resolves, an unresolvable method is caught as invalid rather than rendered as a success, and an unknown `pipe_ref` is a 422. | Unit tests cover the dialog → action → wire chain; the wire contract itself is scratch-verified. |

**The checkpoint paid for itself immediately: the very first live run failed.** The e2e suite's source-label assertion came back empty against a real server while the *server's own unit test for the same thing passed*. The cause was neither a server bug nor a client bug — it was the **fixture**. The server's `INVALID_MAIN_PIPE_MTHDS` uses `main_pipe = "Not A Valid Pipe Code!"` (a *syntax* violation), and I had written `main_pipe = "does_not_exist"` (syntactically valid, absent). Those take different engine paths, and only the syntax arm populates the structured locators. **This is a real engine gap, recorded in the follow-ups below** — and it is exactly the class of thing no mock would ever have surfaced, because every mock in a repo agrees with the client that wrote it.

**Not done: driving the actual webapp UI** (`pnpm dev` + WorkOS auth + a real method in the deploy dialog). Standing up the authed app was judged not worth it against what it would add: the React plumbing is covered by `deploy-dialog.test.tsx`, the pipe-ref derivation by `pipe-selection.test.ts`, and the only genuinely untested link — the wire body — is what the scratch script verified against the live server. Worth a manual dogfood before the app ships, but it is not blocking Phase 5.

## Phase 5 — final sweep

- [x] Re-read this file top to bottom; every box is now either checked or explicitly moved to the follow-ups below with a reason. The only work this plan named and did **not** do is listed there.
- [x] `pipelex-api`: `make openapi-check` **clean** (artifact up to date — Phases 2–3 already regenerated it; Phase 4 touched no server code), `make agent-check` + `make agent-test` **green**. Per-consumer: `pipelex-sdk-js` `npm run check` + 134 unit + 24 e2e green; `pipelex-app` typecheck + lint + format + 1011 tests green; `mthds-js` was green at `9e19d99` and Phase 4 did not reopen it.
- [x] `make check-spec-links` in `conformance/`: **OK.** (Phase 4 changed no spec text — the spec edits rode Phases 2–3, where the routes they describe actually changed.)

### Phase 5 re-verification (2026-07-13, second pass) — one box above was WRONG

Re-running every check from scratch rather than trusting the boxes turned up one false claim and two red herrings.

**`pipelex-app` was NOT green — `format:check` failed on a clean tree at `73d699c`.** The box above says "typecheck + lint + format + 1011 tests green"; the format half was never true. Prettier wants `_emphasis_` where the commit wrote `*emphasis*`, in the two markdown files it touched (`CHANGELOG.md`, `docs/method-deploy.md`). Confirmed as *introduced by that commit* — the parent's (`a5b9f5c`) versions of both files pass. Fixed in **`f13199c`**; `pipelex-app` now genuinely passes typecheck + lint + format + tests. Content is unchanged (prose only, no rewrapping — `proseWrap` defaults to `preserve`, so this does not collide with the workspace's don't-hard-wrap-markdown rule).

**Lesson worth keeping: verify the exit code, not the log tail.** The first re-run reported "exit 0" because the command ended in `; echo "exit=$?"` — the shell reports *echo's* status, which is always 0. A suite can fail while the wrapper says success. Assert on the real exit code (`exit $code`).

**PR #39's red CI was a GitHub infra flake, not our code.** Lint (3.12/3.13/all) and CLAAssistant all failed inside `Set up job` with `Internal Server Error occurred while resolving "actions/checkout@v4"` / `Unable to resolve action ... unable to find version v1` — GitHub's action registry 500ing. The lint step never ran. Re-ran the failed jobs; **PR #39 is now fully green and MERGEABLE** (doc-check, Lint 3.11/3.12/3.13/all, Tests 3.11/3.12/3.13, CLAAssistant).

**The two open cubic findings on `.claude/skills/postman-bundle/` were already fixed — they are stale, not open.** Both were raised against `63441a0` and closed by `00efee5`/`5028e00`: `--inputs-format` + `--explicit` are exposed in argparse and threaded into `build_build_body`; and a user-supplied `--pipe` now passes through **unqualified** (only `main_pipe`, which is guaranteed to live in the main file's domain, gets qualified with it). They are simply unreplied-to on the PR.

**Phase 5 is done. The plan is complete**, modulo the follow-ups below and the push/PR step: **none of the three JS Phase-4 commits are pushed** (`pipelex-api` `feat/build-routes-files-envelope` → PR #39 is open and green; `mthds-js` `9e19d99`, `pipelex-sdk-js` `7226da2`, `pipelex-app` `73d699c`+`f13199c` are local-only). All three are verified green locally at those commits.

## Out of scope / follow-ups (deliberately not in this plan)

- **`/validate`'s envelope** stays on `MthdsContentsRequest`: it is an MTHDS Protocol route, so moving it to `files[]`-with-sources (which would benefit its diagnostics most of all) is a protocol-level change owned by the `mthds/` spec — raise separately.
- **Hosted deploy dance** (bump `API_VERSION` in `pipelex-api-hosted/`, `api_image_tag` in `pipelex-api-infra/`) happens at release time, not in this plan.
- **Future `/codegen` kinds** (`docs`, `tools`, `tests`): when they arrive they take `pipe_ref` on `/codegen` per the trust-chain rule; the reserved-field validator in `codegen.py` already documents how an arm gets added.

### Raised by Phase 4 / CHECKPOINT 3 (new — none of these block Phase 5)

- **ENGINE: a missing `main_pipe` target reports its source in prose only.** When `main_pipe` names a pipe that does not exist, the resulting `blueprint_validation` item carries **no structured `source` / `error_type` / `domain_code`** — the engine interpolates the source into the message text (`"…could not be found in pipelex bundle at source 'broken.mthds' and domain 'broken'"`) while leaving the fields it demonstrably knows unset. The *syntax*-invalid arm (`main_pipe = "Not A Valid Pipe Code!"`) populates all three. A consumer that wants to highlight the offending file has to regex the prose. Reproduce: `POST /v1/build/output` with `{"files":[{"content":"domain=\"broken\"\nmain_pipe=\"does_not_exist\"\n…","source":"broken.mthds"}]}`. Not a regression from this plan (pre-existing engine behavior, and the routes thread the label correctly — it reaches the engine, which is what puts it in the message). Fixing it is a `pipelex` change → `../_stable` → push `feature/Stabilize` → bump the `rev` pin in `pyproject.toml` + re-lock, which is exactly the round-trip Phase 4 was scoped to avoid.
- **`mthds-js` still throws a bare `Error` on the build routes' non-2xx.** The same wart I fixed in `pipelex-sdk-js` (`7226da2`): its `postApi` → `requestJson` throws `new Error(...)` rather than mapping the RFC 7807 body to `ApiResponseError`, so a 422 (bad `pipe_ref`) and a 501 (`method_ref`) are indistinguishable except by message text. Deliberately **not** fixed in the same pass: the SDK's consumer (`pipelex-app`) genuinely branches on `status`, while `mthds-js`'s consumers are CLIs that print the message — so the value is real but much lower, and `mthds-js`'s Phase-4 commit was already closed. Small change (`~10 lines`), worth doing next time that repo is open.
- **`mthds-js` has no live-server test.** Its whole suite mocks `fetch`. The SDK now has `tests/e2e/build.e2e.ts`; `mthds-js` was verified live only by a scratch script that leaves nothing behind. Porting the e2e suite across is the obvious fix and would have caught its two runner-divergence bugs earlier.
- **Manual dogfood of the webapp Deploy dialog** against a local runner (`pnpm dev` + auth + open the dialog on a real method). Everything under it is verified — see CHECKPOINT 3 — but no human has watched the actual snippets render post-migration.
- **The live Postman collection may still carry the old build-route shapes.** `build_postman_query.py` was fixed in Phase 3, but `/update-postman` has not been run against the hosted collection.
