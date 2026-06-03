# Mistral Workflows — merge-to-`dev` readiness assessment

**Branch:** `feature/Mistral-workflows-merge-4` · **Assessed:** 2026-06-03 · **HEAD:** `ff15bd58` · **dev tip / merge-base:** `fa15d15c`

Cold-start reference for the decision: *is this branch safe to PR into `dev`?* Verified against the actual code. **This doc — not `../TODOS.md` — is the merge basis** (`TODOS.md` records the earlier extraction milestone; it was refreshed 2026-06-03 to match the live tree, but the decision lives here). Companion design docs: [`mistral-workflows-plugin-extract.md`](mistral-workflows-plugin-extract.md), [`mistral-workflows-sub-module.md`](mistral-workflows-sub-module.md). In-flight task notes: [`../TODOS.md`](../TODOS.md).

## TL;DR verdict

The **`runtime_bridge` extraction is genuinely solid** — clean, additive, behavior-neutral, fully green — and safe to merge to `dev` on its own. The branch's problem is that it **couples that clean work to a Mistral SDK major bump (`mistralai` 1.x → 2.x) that drags in a temporary `instructor` git-fork pin on a *core* dependency**, blocked on an upstream PR that is still open with no release path. That dependency state is **not release-grade** and is the only reason not to merge the whole branch as-is.

**Recommendation: split.** Land the bridge now; hold the `mistralai` 2.x bump + `instructor` fork pin until `instructor` ships PyPI support for mistralai 2.x. **The safe branch `feature/Runtime-bridge-extraction` was built off `dev` and is green on 2026-06-03** (`agent-check` + `agent-test` pass; mistralai held at 1.x, temporalio 1.24 included, the `message is None` guard left with the HOLD group). Details in [Recommendation](#recommendation).

## Scope reality (read this first)

The branch *looks* huge — `dev..HEAD` lists ~50 commits and `git diff --stat dev...HEAD` is 138 files / ~19k insertions — but most of that is **already in `dev`** or is docs:

- The big **Temporal-primitives + text-then-object / PipeStructure** work already landed in `dev` as the squash-merge **#891** ("Temporal merge 3: distributed execution + PipeStructure + content generation collapse"). This branch carries the *original unsquashed commits* (different SHAs), so they show in `dev..HEAD` but **net out** in the diff.
- Because the merge-base equals `dev`'s tip (`fa15d15c`), `git diff dev...HEAD` and `git diff dev HEAD` are identical — both show the true net add-on-top-of-dev.
- **Net source diff vs `dev` is small: 26 files / +717 −95 in `pipelex/`.** The rest is additive docs (`docs/`, error pages), the vendored `.claude/skills/workflows/` reference set, and `wip/` planning docs.

So this is NOT "merging the whole Temporal + TTO + Mistral epic." It is "merging the `runtime_bridge` extraction + a Mistral SDK bump + additive docs."

## What's verified green ✅

Run on HEAD `ff15bd58`, working tree clean before and after:

- **`make agent-check`** → ruff + plxt (TOML/MTHDS) + **pyright 0 errors** + **mypy clean (2007 source files)**.
- **`make agent-test`** → full non-inference suite, `-n auto`, markers `(dry_runnable or not (inference or llm or img_gen or extract or search)) and not pipelex_api` → **all passed**. This *includes* unit + every key-free integration test: the `runtime_bridge` DIRECT integration test (`tests/integration/pipelex/runtime_bridge/test_bridge_direct.py`) and the in-process Temporal tests.
- `runtime_bridge` has **no `TODO`/`FIXME`/`NotImplementedError` stubs**; ~1,124 lines of new bridge tests (unit + integration).
- **Not covered by `agent-test`** (key-gated, can't run locally): a **live Mistral inference + OCR round-trip**. The mistralai 2.x bump is verified at type/import level and by the non-inference suite, but not end-to-end against the real API. Run this with a real key before relying on it in production.

## Quality of the net change

Clean. Highlights:

- **`pipelex/runtime_bridge/`** — framework-agnostic core so any host runtime (not just Mistral Workflows) can embed Pipelex. `bridge.py` (boundary types + `run_pipe_via_bridge` dispatch), `bootstrap.py` (`ensure_pipelex_booted`), `execution_mode.py` (`PipelexExecutionMode`), `exceptions.py`, and a `primitives/` subpackage (`delivery`, `graph_assembly`, `hydration`, `pipe_classification`, `submitter_hydration`, `trace_flush`, `pipe_run_arg`). Exhaustive `match/case`, enum `@property` predicates (respects the "never `==` an enum" rule), strong docstrings.
- **Temporal activities became thin wrappers** delegating to `runtime_bridge.primitives` — e.g. `act_assemble_graph` is now a ~4-line `@activity.defn` over `assemble_graph_for_pipeline_run(...)`; the body moved verbatim into the primitive. **Behavior-neutral lift** (the CHANGELOG entry asserts the same). Touched: `temporal/tprl_pipe/{act_assemble_graph,act_deliver,act_flush_trace_events,temporal_pipe_router,temporal_pipe_run,wf_pipe_router,wf_pipe_run}.py` + `pipe_run/delivery_executor.py`.
- **`MISTRAL_NATIVE` is the safe preview shape.** Inside `pipelex` it is an additive enum value whose dispatch branch (`bridge.py::_run_mistral_native`) does a *deferred import* of `pipelex_mistralai_workflows.primitives.pipe_run` and immediately raises **`MissingMistralWorkflowsPluginError`** (with a `pip install pipelex-mistralai-workflows` hint) if the external package is absent. No Mistral-specific logic lives in `pipelex`. **Merging it does not activate any preview behavior for existing users**; the `DIRECT` / `TEMPORAL_*` paths are untouched. The actual Mistral-native decomposition lives in the separate `pipelex-mistralai-workflows` repo.

The CHANGELOG `[Unreleased]` "Changed" bullet frames this correctly as a pure extraction + promotion of `runtime_bridge` with **no behavior change**.

## The blocker: dependency coupling ⚠️

This is the "something bad" risk for `dev`. All in `pyproject.toml` / `uv.lock`:

- `mistralai>=1.12.0` → **`mistralai>=2.4.4`** — a **major bump of the live Mistral LLM + OCR provider**. Forces the import reorg across `pipelex/plugins/mistral/*` (`mistralai.models` → `mistralai.client.models`, `mistralai.client.errors`, etc.). A genuine robustness fix rides along (a `message is None` guard in `mistral_llm_worker.py` that raises a transient/retryable error).
- **`[tool.uv.sources] instructor = { git = "https://github.com/Ian321/instructor.git", rev = "4ea22d2396ca35514929f27faed866115e8b3583" }`** — marked *"Temporary."* `instructor` is a **core base dependency** (`pyproject.toml` line ~28, `instructor>=1.13`), so the fork pins the **entire lockfile**, not just the mistralai extra. `uv.lock` resolves `instructor 1.15.1` from that git rev.
- `temporalio==1.23.0` → `temporalio==1.24.0` — minor pinned bump, low-risk, independent.

Why the fork pin matters (checked 2026-06-03):

- `instructor` PR **#2298 "support mistralai v2" is OPEN, not merged** (ready-for-review since 2026-05-06). There is **no PyPI `instructor` release that works with mistralai 2.x** — it's a known-broken combo (`instructor` issue **#2137**: mistralai 2.0.0 broke `from mistralai import Mistral`, which also breaks instructor for *other* providers when mistral is installed).
- So the fork pin is **load-bearing with no near-term removal path** — it depends on an external maintainer merging and releasing.
- **Published-package knock-on:** `[tool.uv.sources]` is a uv-workspace concept and is **not** baked into the published wheel's dependency metadata. It only saves *this repo's* lockfile/CI. A PyPI consumer running `pip install pipelex[mistralai]` would get `mistralai>=2.4.4` + PyPI-`instructor` (no 2.x support) → **broken structured-output combo**. So bumping the published `mistralai` floor couples pipelex's release health to instructor's, and should not reach a release until instructor publishes 2.x support.

## Recommendation

`runtime_bridge` has **zero `import mistralai`** — it is fully decoupled from the SDK bump. Two viable paths:

### Option A — split (preferred)

**Land on `dev` now** (additive, behavior-neutral, fully green):

- `pipelex/runtime_bridge/**` (incl. `primitives/`)
- Temporal rewiring: `pipelex/temporal/tprl_pipe/{act_assemble_graph,act_deliver,act_flush_trace_events,temporal_pipe_router,temporal_pipe_run,wf_pipe_router,wf_pipe_run}.py`, `pipelex/pipe_run/delivery_executor.py`
- The `runtime_bridge` tests, the additive `docs/` (error pages + `docs/distributed-execution/mistral-workflows/`), the `.claude/skills/workflows/` reference set
- The `MISTRAL_NATIVE` enum + deferred-dispatch + `MissingMistralWorkflowsPluginError` (harmless without the SDK bump — it just fails fast)
- The CHANGELOG "Mistral Workflows extracted" bullet
- The `temporalio==1.24.0` bump (verified independent of the SDK work; carried via `uv lock --upgrade-package temporalio` off dev's lock so mistralai stays pinned at 1.12.4)

**Hold on the branch** until `instructor` ships PyPI mistralai-2.x support (track #2298):

- `pyproject.toml` lines: `mistralai>=2.4.4` and the `[tool.uv.sources] instructor` fork pin. (`temporalio==1.24.0` is separable — it landed in the safe PR.)
- the coupled `uv.lock` changes
- **Mistral provider — source AND tests** (all carry the `mistralai.client.*` import reorg, which is required by 2.x):
    - source: `pipelex/plugins/mistral/{mistral_config,mistral_extract_worker,mistral_factory,mistral_llm_worker,mistral_llms}.py`
    - tests: `tests/unit/pipelex/plugins/{test_plugin_pipelex_storage_images,test_transport_retry_wiring}.py` and `tests/unit/pipelex/plugins/mistral/{test_mistral_worker_error_handling,test_extract_mistral_metadata,test_mistral_llm_worker_object_error_handling,test_mistral_extract_worker_semantic,test_mistral_reasoning}.py`
- The **`message is None` guard** in `mistral_llm_worker.py` — see the correction below; it is 2.x-coupled and must travel with the bump.

**Separability verified, and the safe branch built ✅ (2026-06-03).** Two passes. First, a throwaway check: reverted the complete HOLD group to dev (mistralai → 1.12.4, temporalio → 1.23.0, instructor → PyPI, provider source + seven tests), re-synced, `agent-check` + `agent-test` green. Then the real deliverable: branch **`feature/Runtime-bridge-extraction`** off `dev` (soft-reset so the net diff is one staged changeset), reverted the HOLD group, kept `temporalio==1.24.0`, regenerated the lock off dev's (mistralai held at 1.12.4), and re-ran both gates → **`agent-check` 0 errors / 2007 files, `agent-test` all passed.** The safe part — `runtime_bridge` (zero `import mistralai`) + Temporal rewiring + `MISTRAL_NATIVE` deferred dispatch + additive docs/tests — is provably independent of the SDK bump and the fork pin.

**Two findings the build earned:**

1. The HOLD group is wider than the provider *source* — the seven provider *test* files above were migrated to the 2.x `mistralai.client.*` paths and fail `pyright` (`reportMissingImports`) under mistralai 1.x, so they must move with the bump too.
2. **The `message is None` guard is NOT SDK-independent** (my earlier claim was wrong). Under mistralai 1.x, `response.choices[0].message` is typed non-optional (`AssistantMessage`), so `pyright` rejects the guard as `reportUnnecessaryComparison`. It only becomes valid under 2.x, where `message` is `AssistantMessage | None`. So the guard **stays with the HOLD group** — do not cherry-pick it into the safe PR.

### Option B — merge whole, with a gate

Acceptable **only if `dev` is treated as a pure integration branch**: merge as-is, but add an explicit gate that **this must not reach `main` / a release while the `instructor` fork pin exists**, plus a tracking issue tied to instructor #2298. Given the pin is blocked on someone else's open PR with no ETA, prefer Option A.

## Housekeeping

- **`../TODOS.md` — refreshed 2026-06-03 (done).** Its "End state delivered" had predated the `runtime_bridge/primitives/` subpackage and the `MISTRAL_NATIVE` mode, and implied no mistral-missing exception existed (the old `MistralWorkflowsNotInstalledError` was deleted, but the new `MissingMistralWorkflowsPluginError` replaced it). The runtime_bridge end-state bullet + the Temporal-rewiring bullet were corrected, and a banner now points here as the merge basis. If `runtime_bridge`'s surface changes again, update both files.
- **`mistralai-workflows` companion version** lives in the separate `pipelex-mistralai-workflows` repo (TODOS notes `mistralai-workflows==3.4.0` there) — out of scope for this pipelex-side merge decision.

### Tracking issue for the `instructor` fork pin (to file)

The fork pin must not silently rot. In-repo anchors today: this doc + the `# Temporary: …` comment above `[tool.uv.sources] instructor` in `pyproject.toml` (which already references #2298). The durable external tracker is a GitHub issue — none exists yet (`gh issue list --search instructor` was empty on 2026-06-03). Draft to file against `Pipelex/pipelex`:

```
Title: chore(deps): drop temporary `instructor` git-fork pin once mistralai 2.x lands on PyPI

The `mistralai` 1.x→2.x bump (feature/Mistral-workflows-merge-4) needs `instructor` to
support mistralai v2, which is NOT yet released on PyPI. Stopgap in pyproject.toml:

    [tool.uv.sources]
    instructor = { git = "https://github.com/Ian321/instructor.git",
                   rev = "4ea22d2396ca35514929f27faed866115e8b3583" }

`instructor` is a CORE dependency, so this pins the entire lockfile (uv.lock resolves
instructor 1.15.1 from that git rev). Published-package knock-on: `[tool.uv.sources]` is
not in the wheel metadata, so `pip install pipelex[mistralai]` from PyPI gets mistralai 2.x
+ PyPI-instructor (no 2.x support) → broken structured-output combo. Must not reach a
release while the pin exists.

Blocked on:
- instructor PR #2298 "support mistralai v2" — https://github.com/567-labs/instructor/pull/2298 (open as of 2026-06-03)
- instructor issue #2137 — https://github.com/567-labs/instructor/issues/2137

Removal steps (once a PyPI instructor release supports mistralai 2.x):
1. Delete the `[tool.uv.sources] instructor = {...}` block in pyproject.toml.
2. Raise the `instructor>=…` floor to the first release with mistralai-2.x support.
3. `uv lock`; confirm instructor resolves from PyPI (not the git rev) in uv.lock.
4. `make agent-check && make agent-test`; run a live Mistral inference + OCR round-trip.

Context: wip/mistral-workflows-merge-readiness.md
```

File it by saving the body above to a file and running `gh issue create --repo Pipelex/pipelex --title '…' --body-file <path>`. Once filed, add the issue number to the `# Temporary: …` comment in `pyproject.toml` so the pin and the tracker cross-reference.

## Cold-start: re-verify in a fresh session

```bash
cd /Users/lchoquel/repos/Pipelex/_workflows
git rev-parse --short HEAD                       # expect ff15bd58 (or later)
git merge-base HEAD dev | cut -c1-8              # dev tip; == merge-base means dev fully merged in
git diff --stat dev...HEAD -- 'pipelex/**/*.py'  # the real net source diff (~26 files)
grep -n "instructor\|mistralai\|temporalio" pyproject.toml   # the dep coupling
make agent-check                                 # ruff/plxt/pyright/mypy
make agent-test                                  # full non-inference suite
```

To confirm `MISTRAL_NATIVE` is still a no-op-without-the-package boundary: `pipelex/runtime_bridge/bridge.py::_run_mistral_native` should deferred-import `pipelex_mistralai_workflows` and raise `MissingMistralWorkflowsPluginError`.

## Sources

- instructor PR #2298 — <https://github.com/567-labs/instructor/pull/2298> (open, not merged as of 2026-06-03)
- instructor issue #2137 — <https://github.com/567-labs/instructor/issues/2137>
- mistralai on PyPI — <https://pypi.org/project/mistralai/>
