# Cookbook "hello plugin" → real inference-backend plugin (Option B)

Status: **CHECKPOINT B CLEARED — TRACK COMPLETE (2026-07-03).** Phases 0–4 done and ALL COMMITTED. Pipelex (`feature/More-plugins`): `2f9b7e1d9` (optional_routes fix), `dee230f46` (LLM worker fold, breaking), plus the docs+tracker commit carrying this file. Cookbook (`dev`): `ecb231c` (the whole example; root `pyproject.toml`/`uv.lock` editable pin deliberately left uncommitted — flip to `pipelex==X.Y.Z` at release, see caveat below). Only remaining action = release ordering (step 3 below). This tracker is retired.

## NEXT SESSION — start here

1. **Commit slicing first** (user to approve slices). This worktree (`_plugins`, branch `feature/More-plugins`) holds four separable concerns — do NOT mix them:
   - `optional_routes` factory fix: `pipelex/cogt/model_routing/routing_profile_factory.py` + `tests/unit/pipelex/cogt/model_routing/test_routing_profile_optional_routes.py` + its CHANGELOG "Fixed" entry.
   - LLM worker fold (breaking): `llm_worker_abstract.py` (folded), `llm_worker_internal_abstract.py` (deleted), `llm_utils.py` + `llm_generate.py` (dump gating moved), `inference_manager{,_protocol}.py` (legacy setter removed), 6 re-parented workers under `pipelex/plugins/`, reworked tests (`test_worker_error_enrichment`, `test_external_plugin`, `test_llm_gen_text`, `test_setup_inference_workers`, factory/manager types) + the two CHANGELOG "Changed" entries.
   - Orchestrator-plugins docs from a PRIOR session (unrelated to this track — `docs/under-the-hood/orchestrator-plugins.md` etc.).
   - `TODOS.md` (this tracker).
   Cookbook side = one coherent commit (example package, `.pipelex/inference/` config, `.mthds`, README×2, CHANGELOG, `test_bundles.py`, mypy exclude) — but the `[tool.uv.sources]` editable pin in `pyproject.toml`/`uv.lock` must NOT ship (see editable-pin caveat below).
2. **Phase 4 — docs rewrite** (checkboxes below). Also re-check `docs/under-the-hood/inference-backend-plugins.md`'s worker section against the folded base (constructor now takes `inference_model`; no lifecycle gotchas left to document).
3. **Release ordering**: pipelex release > 0.36.0 (breaking changelog) → flip cookbook pin to `pipelex==X.Y.Z` → cookbook release. Before the pipelex release, grep `pipelex-temporal` + `pipelex-mistralai-workflows` for LLM worker subclasses / `set_llm_worker_from_external_plugin` (expected: none — both are orchestrator-only).

All gates were green at session end (2026-07-03): pipelex `make agent-check` + `make tb` + FULL `make agent-test`; cookbook `make agent-check` + `make agent-test` + hello-plugin real run end-to-end.

## Goal

Replace the legacy cookbook example `pipelex-cookbook/examples/c_advanced/using_inference_plugins/` with a genuine entry-point plugin that demonstrates the real plugin system. Today that example is a single `.mthds` file whose `model` field references the handle `llm_plugin_example_using_openai` — a name **defined nowhere** (not in the cookbook's `.pipelex/inference/`, not in the core kit). "Plugin" in its name is pre-plugin-system vocabulary meaning "custom model config entry"; the example has only ever run as DRY RUN (see `pipelex-cookbook/.pipelex/traces/`). Decision taken with the user (2026-07-03): **Option B** — make it an actual `pipelex.plugins` entry-point plugin, not a config-only reframe.

## Background: the plugin system (cold-start summary)

The pipelex repo (this worktree, `_plugins`) has a discovery-based plugin system. Everything below is verified against the current tree:

- **Contract** (`pipelex/plugins/contract.py`): a plugin is any object satisfying the `@runtime_checkable` `PipelexPlugin` protocol — `name: str`, `targets_api: int` (must equal `PLUGIN_API_VERSION`, currently **2**), and `register(self, registrar) -> None`. `register` is **side-effect-free**: it may only call registrar menu methods — no I/O, no SDK import, no client construction. Heavy work goes inside the `make_worker` closures.
- **Discovery** (`pipelex/plugins/discovery.py`): `build_registrar` iterates `BUILTIN_PLUGINS` then external entry points in group **`pipelex.plugins`**. An entry point may resolve to a plugin instance or a zero-arg factory returning one. Denylist via `plugins.disabled` config; fail-loud on duplicates/version mismatch/broken plugin.
- **Inference seam** (`pipelex/plugins/inference_backend_registry.py`): `registrar.add_inference_backend(family=InferenceFamily.LLM, sdk="<token>", make_worker=...)`. A model's `sdk` field selects the backend factory; worker factories hold no match over SDK strings. `MakeWorkerFn` is called as `make_worker(*, inference_model: InferenceModelSpec, backend: InferenceBackend, sdk_clients: SdkClientRegistry, reporting_delegate: ReportingProtocol | None) -> InferenceWorkerAbstract`. Use `require_sdk(...)` inside `make_worker` for optional-dependency guards.
- **Minimal LLM worker**: subclass `LLMWorkerAbstract` (`pipelex/cogt/llm/llm_worker_abstract.py`); since the fold (see follow-up below) the abstract surface is just `_gen_text` + `_gen_object` — the base takes `inference_model` in `__init__`, owns the job lifecycle, and derives capability flags from the spec.
- **Optional companion**: `registrar.add_model_lister(sdk="<token>", lister=...)` — powers `pipelex show models`.
- **Reference implementations**: smallest builtin = `pipelex/plugins/blackboxai/blackboxai_plugin.py` (one `add_inference_backend`, lazy imports inside `_make_..._worker`). External entry-point precedents = `pipelex-temporal` (`pipelex_temporal/temporal_plugin.py`) and `pipelex-mistralai-workflows`.
- **Canonical authoring doc**: `docs/under-the-hood/inference-backend-plugins.md` (the "acme" walkthrough — the cookbook example should be its living counterpart).
- **Verification command**: `pipelex plugins list` prints every discovered plugin (origin builtin/external, status, API version, contributions).

Model config layer (how a `.mthds` `model` handle reaches the plugin): the cookbook's `.pipelex/inference/backends.toml` declares backends keyed by name (`[hello]`, `enabled`, `api_key`...); per-backend model files `backends/<name>.toml` declare model sections with `[defaults]` carrying `sdk = "<token>"` — the section header is the model handle referenced from `.mthds`. The `add-model` skill (in this repo's `.claude/skills/`) documents the full add-a-model procedure including routing profiles.

## Decisions

- **D1 — worker shape**: a deterministic, zero-key "hello" echo worker (returns a canned/derived completion) so the example runs everywhere with no credentials; the rewritten docs page points to `inference-backend-plugins.md` for wrapping a real SDK. Rationale: cookbook examples must be runnable; the seam being demonstrated is discovery/registration, not OpenAI usage. (Override here if we'd rather wrap the OpenAI SDK.)
- **D2 — package location**: the plugin package lives inside the example dir, e.g. `examples/c_advanced/using_inference_plugins/hello_inference_plugin/` with its own `pyproject.toml`, installed with `uv pip install -e` (cookbook already uses uv). It is NOT a dependency of the cookbook's root `pyproject.toml` — installing it is the demonstrated step.
- **D3 — naming**: retire the dangling handle `llm_plugin_example_using_openai`. New names: plugin `hello-inference` (entry-point name `hello_inference`), sdk token `hello`, backend `[hello]`, model handle e.g. `hello-1`. No `pipelex_` prefix anywhere user-facing that belongs to the example.

## Phases

### Phase 0 — Recon in the cookbook repo

- [x] Verify how a custom backend + model file wires end-to-end in the cookbook's current `.pipelex/` layout: add a scratch `[hello]` backend + `backends/hello.toml` model with `sdk = "hello"` and confirm the failure mode is `InferenceBackendNotFoundError` for `(llm, hello)` (proves config resolves and the missing piece is exactly the plugin). **DONE** — exact friendly message confirmed: "No inference backend registered for sdk 'hello' in the llm family. Is its plugin installed and enabled?".
- [x] Confirm whether routing profiles (`.pipelex/inference/routing_profiles.toml`) need an entry for a directly-referenced model handle, or whether `model = { model = "hello-1" }` in `.mthds` bypasses routing. **ANSWERED: routing is NOT bypassed.** `ModelManager.build_deck` routes every known model through the active profile; a DEFAULT match whose backend lacks the model spec **silently drops the model from the deck** (only the `internal` backend is tried as fallback). So the example needs an exact route. We use `optional_routes = { "hello-1" = "hello" }` in the active `all_pipelex_gateway` profile — optional routes only apply when the target backend is enabled, so the entry is inert if `[hello]` is disabled. **This surfaced a real core bug (fixed here, see below).**
- [x] ~~Check the cookbook's pinned `pipelex` version supports the plugin system~~ — resolved 2026-07-03: the cookbook now sources `pipelex` **editable from this worktree** (`pipelex-cookbook/pyproject.toml` `[tool.uv.sources] pipelex = { path = "../_plugins", editable = true }`), so it runs against this tree's tip. Any pipelex-side change needed for the example is made HERE and is live in the cookbook immediately.

### Phase 1 — The plugin package (in `pipelex-cookbook`) — DONE

- [x] Create `examples/c_advanced/using_inference_plugins/hello_inference_plugin/` with `pyproject.toml`: distribution name `hello-inference-plugin`, entry point `hello_inference = "hello_inference_plugin.hello_plugin:HelloInferencePlugin"` (module path deviates from the plan's `hello_inference_plugin:...` — no-re-exports rule forbids defining the class in `__init__.py`; layout mirrors the builtins' `<name>_plugin.py`), dependency on `pipelex`, hatchling build, `py.typed` marker (needed by the cookbook's mypy).
- [x] Implement `HelloInferencePlugin` in `hello_inference_plugin/hello_plugin.py`: `name = "hello_inference"`, `targets_api = PLUGIN_API_VERSION`, side-effect-free `register`, worker import deferred into the `_make_hello_llm_worker` closure.
- [x] Implement `HelloLLMWorker(LLMWorkerAbstract)` in `hello_llm_worker.py`: deterministic `_gen_text` (canned haiku + word-count token usage), `_gen_object` raises `LLMCapabilityError`; capability flags come from the model spec via the base class. (An earlier gotcha — workers had to call `llm_job.llm_job_before_start` themselves or reporting crashed on a `None` duration — was eliminated by folding `LLMWorkerInternalAbstract` into `LLMWorkerAbstract` in core, see below.)
- [x] Bonus TAKEN: `registrar.add_model_lister(sdk="hello", lister=...)` in `hello_list.py` — reads the models from the backend config (no remote API), lights up `pipelex show models hello`.

### Phase 2 — Config + method files (in `pipelex-cookbook`) — DONE

- [x] `[hello]` backend added to `.pipelex/inference/backends.toml` (enabled, no key), `backends/hello.toml` declares `hello-1` with `sdk = "hello"`, and `optional_routes = { "hello-1" = "hello" }` added to the active `all_pipelex_gateway` profile in `routing_profiles.toml`.
- [x] `hello_plugin.mthds` references `hello-1`; dangling handle `llm_plugin_example_using_openai` retired.

### Phase 3 — End-to-end verification (in `pipelex-cookbook`) — DONE

- [x] `uv pip install -e examples/c_advanced/using_inference_plugins/hello_inference_plugin` (left installed in the cookbook venv).
- [x] `pipelex plugins list` shows `hello_inference | external | registered | 2 | inference backend llm:hello + model lister hello`.
- [x] Dry run AND real run green — real run outputs the deterministic haiku, zero keys. `pipelex show models hello` lists `hello-1`.
- [x] Negative check: after uninstall, run fails with the friendly "No inference backend registered for sdk 'hello' in the llm family. Is its plugin installed and enabled?" — and the DRY RUN still passes without the plugin (worker creation is lazy), so cookbook CI needs nothing installed.
- [x] Housekeeping: example README written (install → discover → run → failure mode → docs link); cookbook CHANGELOG `[Unreleased]` entry; root README bullet under "Advanced Methods"; `tests/e2e/test_bundles.py` stale special-cases removed (`NEEDS_OPENAI_KEY` and `GHA_DISABLED` both emptied — the example no longer needs a key nor a GHA skip); cookbook `pyproject.toml` mypy `exclude` gains the nested plugin dir (module-name clash: resolve as the installed package, not via `examples/` traversal).
- Gates: cookbook `make agent-check` + `make agent-test` green; all `tests/e2e/test_bundles.py` dry-run cases pass (hello_plugin auto-discovered, no special-casing). Pipelex-side `make agent-check` green + targeted cogt tests pass.

**CHECKPOINT A — CLEARED 2026-07-03.** Working end-to-end in the cookbook. NOT committed yet in either repo (user to arbitrate commit slicing; this worktree also has unrelated uncommitted orchestrator-plugins docs).

#### Follow-up DONE (in this worktree): LLM worker family symmetry (fold `LLMWorkerInternalAbstract` → `LLMWorkerAbstract`)

Decided with the user right after Checkpoint A: `LLMWorkerInternalAbstract` was a remnant of the pre-plugin-system "fake plugin" era, and the base `LLMWorkerAbstract` had a hole in its template method (external workers had to call `llm_job_before_start` themselves or reporting crashed). Fixed structurally, matching the other three families:

- `LLMWorkerAbstract.__init__` now takes `inference_model`; the base owns the lifecycle (`llm_job_before_start`, spec-driven capability checks, constraints, spec-based OTel names). `LLMWorkerInternalAbstract` deleted; all builtin LLM workers re-parented.
- Legacy `set_llm_worker_from_external_plugin` (manager + protocol) removed — pre-plugin-system path registering spec-less worker classes by handle; its test reworked to drive an out-of-tree `LLMWorkerAbstract` subclass with a real spec.
- Import-cycle lesson (user cares): `pipelex/hub.py` imports the worker ABCs at module level, and `pipelex.config.get_config` imports the hub — so **nothing in hub's import closure may import `pipelex.config` at module level**. The dump gating that caused this moved to the `llm_generate` funnel; `dump_prompt`/`dump_response_from_text_gen` in `llm_utils` are config-gated internally (llm_utils left hub's closure when the ABC dropped it). NO lazy imports. Pre-existing deeper inversion flagged, not fixed: `config.py → hub` and `configs.py → aws_config.py → hub` mean the config layer sits ON TOP of the hub — a future refactor could move the config singleton below the hub and dissolve this class of cycle for good.
- Cookbook side: `HelloLLMWorker` shrank to `_gen_text` + `_gen_object` only (the teaching outcome we wanted); breaking changelog entries added in pipelex CHANGELOG `[Unreleased]`.

#### Core bug found & fixed during Phase 0 (in this worktree)

`RoutingProfileFactory.make_routing_profile` (`pipelex/cogt/model_routing/routing_profile_factory.py`) parsed + validated `optional_routes` from `routing_profiles.toml` but never passed it to the built `RoutingProfile` — TOML optional routes silently did nothing (nothing in the tree used them; zero test coverage). Fixed (one-line pass-through), new test module `tests/unit/pipelex/cogt/model_routing/test_routing_profile_optional_routes.py` (factory pass-through + enabled/disabled gating), CHANGELOG `[Unreleased]` entry added. **Consequence for the cookbook:** its `[Unreleased]` note says the example requires `pipelex` > 0.36.0 — the cookbook-side release must wait for (or pin past) the pipelex release carrying this fix. Related pre-existing wart spotted, NOT fixed: `RoutingProfile.get_backend_match_for_model` mutates `self.routes` in place when merging optional routes (`possible_routes = self.routes` without copy) — harmless today (idempotent merge), flag if it ever bites.

### Phase 4 — Docs rewrite (in the pipelex repo, this worktree) — DONE 2026-07-03

- [x] Rewrote `docs/cookbook/using-inference-plugins.md`: what a plugin is (entry point + `PipelexPlugin` + registrar), package layout, model-config side (`.pipelex/inference/`, optional route), install + `pipelex plugins list` + run walkthrough, failure mode, links to `under-the-hood/inference-backend-plugins.md`. Stale `.pipelex/pipelex.toml` claim gone; GitHub badge now points at the example dir. Also updated the stale blurb in `docs/cookbook/index.md`.
- [x] Audited `docs/features/llm-integration.md` — contains no plugin terminology at all (nothing to fix); the stale "plugins" mention was the cookbook page's own link text, now rewritten. Workspace-wide grep: no other legacy "plugin = config entry" language in docs (remaining "plugin" hits are the unrelated Claude Code skills plugin page).
- [x] Re-checked `docs/under-the-hood/inference-backend-plugins.md` worker section against the folded base: acme example already passes `inference_model` to the worker, no lifecycle gotchas documented — one stale bit found & fixed: lookup-miss error is `InferenceBackendNotFoundError`, not `NotImplementedError` (the doc's own fail-loud table already had it right).
- [x] `make docs-check` (strict mkdocs build) green.
- [x] Changelog entry under `[Unreleased]` (brief docs entry under "Changed").

**CHECKPOINT B (final)** — Phase 4 work all done; **only the commits remain** (user to approve the slices from "NEXT SESSION" step 1, plus these Phase 4 docs edits which ride with the tracker/docs concern or their own docs slice). Once committed in both repos, note the commit SHAs here and retire/archive this tracker. Release ordering reminder (step 3 above) still applies before shipping either side.

## Cross-repo map

| Repo | Work |
|---|---|
| `pipelex-cookbook` | plugin package, backend/model config, `.mthds`, run verification (Phases 0–3) |
| `pipelex` (this worktree `_plugins`) | docs page rewrite + terminology audit (Phase 4), plus any core change the example surfaces |

**Editable-pin caveat**: the cookbook's `[tool.uv.sources]` editable pin on `../_plugins` is a local dev convenience (set by the user 2026-07-03) and must NOT ship: before merging/releasing the cookbook side, flip back to a PyPI `pipelex==X.Y.Z` pin carrying whatever core changes this work needed (same playbook as the pipelex-api editable-pin precedent — editable local paths break CI). If the example needs no core change, the flip-back is to the current release.

## Gotchas for a cold start

- `register` must stay side-effect-free and import-light; anything heavy goes inside `make_worker`. Discovery runs `build_registrar` at boot AND in `pipelex plugins list`.
- `targets_api` must equal `PLUGIN_API_VERSION` (2) or discovery fails loud with `PluginApiVersionMismatchError`.
- The keyword-only-arguments convention is enforced on `pipelex/` source only, but the example package should follow it anyway — it's teaching material.
- Worker subclass signatures must match `LLMWorkerAbstract` exactly (use `@override`); the reporting/telemetry plumbing is inherited, don't reimplement it.
- Don't edit `docs/errors/` pages by hand (generated); nothing here should need new error classes anyway.
- Stale-terminology precedent: on 2026-07-03 we already fixed "CLI-build command harvest" leftovers in `contract.py`, `discovery.py`, and `inference-backend-plugins.md` — same spirit applies to any old "LLM plugin" config-speak found during Phase 4.
