# Kernel layer: named, layer-gated plugins, and its own distribution

**Goal.** Two staged moves that turn the kernel/interpreter boundary from a convention into a mechanism and then into enforced structure — plus a third that is deliberately left hypothetical: **Part A** splits plugin discovery by layer under kernel-branded entry-point groups (`pipelex.plugins.kernel` / `pipelex.plugins.interpreter`), with a coherent rename of the layer vocabulary from "runtime layer" to "kernel layer". **Part B** moves the kernel layer into its own top-level package `pipelex_kernel/` at the repo root, beside `pipelex/` — same repo, same single distribution, **not** published separately — making the one-way dependency statically checkable in one line. **Part C is a hypothetical, not a commitment**: it *would* ship `pipelex_kernel` as its own PyPI distribution `pipelex-kernel`, so a kernel-only consumer's venue physically could not contain the interpreter — but it proceeds only on an explicit greenlight (C0), and this plan commits to nothing beyond Part B.

**Why.** The kernel trust-base story ("this code imports only the kernel") is a per-venue claim: measurement showed that merely *installing* the Temporal plugin dragged the whole interpreter into every pipelex process in the venv, because plugin discovery imports every installed plugin's module. The plugin-side violation was fixed at pipelex-temporal HEAD ("Keep the interpreter out of an import-light register, and gate it", 2026-08-09) — but that fix protects only plugins we author. Part A makes a kernel-only boot never even `load()` interpreter-side entry points; Part B makes a kernel→interpreter import impossible to merge (a static ban over `pipelex_kernel/`); a greenlighted Part C would make the interpreter uninstallable in a kernel-only venue, closing the hole for plugins nobody vetted — and would make the story self-evidencing: `pip install pipelex-kernel`, drop in your kernel-consuming code, run.

**Why B is the plan's end-state and C stays hypothetical.** The big mechanical churn (every kernel-layer import repoints) lands without touching the release surface — the `pipelex` wheel simply ships two top-level packages, and PyPI sees nothing new. The irreversible step (registering and committing to a public `pipelex-kernel` distribution) is deliberately **not decided by this plan** — it is a distinct future decision, to be taken with B's measured footprint in hand. And consumers churn once either way: imports move to `pipelex_kernel.*` at B, and a later C would change only install metadata. Precedent: the Temporal externalization deliberately separated the reversible local cut-over from the publish gate.

## Status

| Part | Phase | State |
| --- | --- | --- |
| A | A0 naming ruling + inventory | **done** — see [A0 as built](#a0--as-built) |
| A | A1 group-split mechanism | **done** — see [A1 as built](#a1--as-built) |
| A | A2 external-plugin migration | **done** — three planned repos + the cookbook example (D-A3-1), verified against the A1 core; local commits, none pushed. See [A2 as built](#a2--as-built) |
| A | A3 gates + checkpoint | **done** — 🛑 [CHECKPOINT A](#a3--as-built) reached; Part A complete and green, nothing pushed |
| B | B0 footprint measurement | not started |
| B | B1 decisions | not started |
| B | B2 the move + gates | not started |
| C | C0 the greenlight | hypothetical — no decision taken |
| C | C1 the distribution split | hypothetical |
| C | C2 physical gate + proof | hypothetical |

## The naming ruling (Louis, 2026-08-10)

The layer formerly called the "runtime layer" is the **kernel layer**. Rationale: "runtime" is overloaded three ways in this workspace — the whole `pipelex/` engine (the workspace-docs sense), the orchestration venue ("boot as a Temporal runtime", the `runtime_bridge`/`boot_orchestrator` sense), and the sub-interpreter layer — and once Part B exists, the layer boundary *is* the `pipelex_kernel` package boundary, so the layer should carry the package's name. The Linux precedent holds: drivers are "kernel modules" without extending the syscall façade, so "kernel plugin" reads naturally for an inference backend or storage provider. "Kernel" is correctly Pipelex-branded per the workspace brand-boundary rule (a runtime/implementation concept, not a language one).

**Rename scope — three buckets.** The sweep must be coherent (one name for one boundary) but must not cross repo-boundary pins prematurely:

| Bucket | Contents | When |
| --- | --- | --- |
| Rename in Part A | `RUNTIME_BUILTIN_PLUGINS` → `KERNEL_BUILTIN_PLUGINS`, `RUNTIME_CORE_UNCONDITIONAL_PLUGIN_NAMES` → `KERNEL_CORE_UNCONDITIONAL_PLUGIN_NAMES` (both in `pipelex/providers/builtins.py`, consumed by `runtime_boot.py` and `interpreter_plugins/builtins.py`); "runtime-layer" prose in `plugins/contract.py`, `plugins/discovery.py`, provider docstrings, and the under-the-hood SPI docs; `tests/unit/pipelex/test_runtime_layer_import_closure.py` → `test_kernel_layer_import_closure.py` (and the reference to it in pipelex-temporal's `test_plugin_interpreter_import_closure.py` docstring — that copy's canonical-list pointer must follow in the same window, it is the drift hazard its own docstring warns about) | A0 |
| Rename in Part B | Module paths whose names are pinned across repo boundaries or that move anyway: `runtime_boot.py`/`RuntimeBoot` → `kernel_boot`/`KernelBoot`, `pipelex.runtime_hub` → the kernel package's hub. `pipelex.runtime_hub` is named in the pipelex-transport ALLOWED_SURFACE and spec, so renaming it means re-pinning `docs/specs/pipelex-transport-boundary.md` + `conformance/tests/pipelex_transport/test_data.py` + the pipelex-transport repo — fold that into B2, where every one of these module paths changes anyway (they move into `pipelex_kernel/`), so the transport boundary churns once, not twice | B2 |
| Never rename | `runtime_bridge/` (the orchestration-venue sense of "runtime", and interpreter-layer anyway), `boot_orchestrator` semantics and its "boot as a Temporal runtime" prose, any runner-API "runtime" usage | — |

## Part A — layer-gated plugin discovery

### A0 — naming inventory + sweep

Grep-driven inventory of every "runtime" occurrence in `pipelex/plugins/`, `pipelex/providers/`, `pipelex/interpreter_plugins/`, the closure tests, and the SPI docs; classify each hit into the three buckets above (the bucket table is the ruling; the inventory verifies it found everything and nothing extra). Apply the Part-A bucket as one mechanical commit. `make agent-check` + the renamed closure test green.

#### A0 — as built

Done. One commit, no behavior change — identifier and prose renames plus two test-module renames.

**What the inventory found beyond the ruling's Part-A row**, and why each was folded in rather than deferred (the ruling's test is "one name for one boundary"; leaving any of these behind would have left the canonical statement of the boundary contradicting the code that enforces it):

| Found | Bucket | Rename |
| --- | --- | --- |
| `hub_layering_guard.py`'s layer vocabulary | A — pure internal identifiers, pinned by no repo boundary | `RUNTIME_LAYER_PACKAGES` → `KERNEL_LAYER_PACKAGES`, `is_runtime_layer` → `is_kernel_layer` |
| `docs/contribute/hub-layering.md` | A — the canonical human-readable definition of the layer | all layer prose; plus one new paragraph recording that `runtime_hub` / `runtime_boot` still carry the layer's former name and why they wait for Part B |
| `tests/unit/pipelex/test_runtime_layer_exceptions_aggregate_gate.py` | A — a closure test, same row as the import-closure one | file + `TestRuntimeLayerExceptionsAggregateGate` → `…Kernel…` |
| `KERNEL_LAYER_ENTRY_POINTS`, `TestBootedRuntimeLayer`, and ~8 layer-named test functions | A — layer vocabulary in test names | mechanical |
| layer-sense prose outside the five inventoried areas (`runtime_hub.py`, `runtime_boot.py`, `pipelex.py`, `core/`, `cogt/`, `kernel/`, `architecture-overview.md`, `pipelex-kernel.md`) | A — same vocabulary, same boundary | "runtime layer/-layer", "runtime half", "runtime closure", "runtime-only boot", "runtime adapters", "runtime-contributed" → kernel forms |
| `.test_durations` — the CI shard-balancing snapshot keys on pytest node IDs, so a renamed file, class or test function makes it stale | A — data, but it names the renamed things | keys rewritten in place |

**Left alone deliberately** (verified hit-by-hit, not by pattern): `runtime_bridge` and every "runtime" meaning the orchestration venue ("boot the process as its runtime", "a host runtime", "the Temporal worker runtime"); `RuntimeError` / `runtime_checkable` / `at runtime` / "an ordinary runtime condition"; `system/runtime.py` and `runtime_manager`; `setup_doctor_runtime`; `docs/under-the-hood/orchestrator-plugins.md`'s host-runtime prose; `CHANGELOG.md`'s released entries and everything under `wip/` (historical records — only the still-`[Unreleased]` kernel entries were re-worded, since they ship describing current reality).

**Decisions taken**

- **D-A0-1 — `runtime_hub` / `runtime_boot` keep their module names through Part A.** They are pinned across repo boundaries (`pipelex.runtime_hub` is in pipelex-transport's `ALLOWED_SURFACE` and its spec) and they move anyway in B2, so renaming them now would churn the transport boundary twice. `hub-layering.md` and `runtime_boot.py`'s header both say so out loud, so the mismatch reads as staged rather than as drift.
- **D-A0-2 — the pipelex-temporal pointer rides A2's commit.** `pipelex-temporal/tests/unit/pipelex_temporal/test_plugin_interpreter_import_closure.py` names the canonical list's file twice (its `#:` comment and its failure message). That repo gets exactly one commit in Part A (A2), so the pointer fix lands there rather than as a stray commit — same window, per the ruling. ⚠ It is stale between A0 landing and A2 landing.

**Verification** — `make check` green (ruff, plxt, pyright, mypy, pylint 10.00, keyword-only, hub-layering, drift). Full `make agent-test` green. Three drift contracts re-acked in the same commit — `cli-docs`, `hub-layering-convention`, `pipelex-kernel-docs`. The `/code-review` fan-out over A0 was skipped on Louis' instruction; CHECKPOINT A's review covers the whole of Part A.

**Two traps the sweep hit, worth repeating in A1**

- A bulk `runtime layer` → `kernel layer` rewrite also matches *inside* other words: it turned `doctor_cmd.py`'s "mirror runtime **layered** resolution" (the layered *config* resolution, nothing to do with the layer) into "kernel layered". Caught only because that file is a drift trigger and the plan forced a hit-by-hit read. Re-grep for `kernel layered|kernel-layered` after any further bulk pass.
- **A rename is not done when the tree type-checks — `.test_durations` keys on node IDs.** `make check` and every targeted suite were green with the file still naming `test_runtime_layer_import_closure.py`; only the full `make agent-test` caught it, through `tests/unit/repo/test_test_durations_paths.py`, whose whole job is to notice that CI shards are being balanced against tests that cannot run. Fixed by rewriting the stale keys in place, each new key asserted present in a fresh collection first — regenerating would have rewritten the whole snapshot with fresh timings for a rename. Any A1–A3 rename of a test file, class or function owes the same pass.

**Open** — none.

### A1 — the group-split mechanism

- Two entry-point groups replace the single `pipelex.plugins`: **`pipelex.plugins.kernel`** (inference backends, model listers, storage providers, secrets providers, HTTP-error mappers) and **`pipelex.plugins.interpreter`** (orchestrators, bundle validators, PipeFunc executors, interpreter-side hub-slot claims).
- `build_registrar` gains an injected `entry_point_groups` parameter, symmetric with the existing `builtin_plugins` injection: the kernel-only boot passes the kernel group alone; the interpreter boot passes both. The discovery module itself keeps naming no layer-welding constant — the composed defaults live where the builtin lists live today.
- **Menu-tier cross-check.** Classify each registrar menu method by tier (kernel-tier: `add_inference_backend`, `add_model_lister`, `add_storage_provider`, `add_secrets_provider`, `add_http_error_mapper`; interpreter-tier: `add_orchestrator`, `add_bundle_validator`, `add_pipe_func_executor`; slot claims classified per-slot). Discovery records which group a plugin arrived under, and the registrar fails loud when a kernel-group plugin calls an interpreter-tier menu method. This catches a plugin lying about its layer at register time — the import-contamination half is caught by the per-plugin guard tests (Part A world) and, in a greenlighted Part C world, by physics.
- **Legacy-group probe, fail-loud.** Discovery also reads the retired `pipelex.plugins` group; any entry point found there raises with a migration message naming the plugin and the two new groups. Silent nondiscovery is the quiet failure mode this probe exists to prevent.
- `PLUGIN_API_VERSION` bumps (breaking change to the plugin contract); `pipelex plugins list` gains the layer/group column.

#### A1 — as built

Done. One commit, tests first (the module was red on a missing `PluginGroup` before any mechanism existed), then the mechanism.

`PluginGroup` is a `StrEnum` in its own module `pipelex/plugins/plugin_group.py` rather than in `contract.py`, because the registrar needs it at runtime (it is a `PluginDiscovery` field) while `contract.py` names the registrar back — pyright's `reportImportCycles` is an error here, and a third module is the honest break. `build_registrar` takes `entry_point_groups` as a required parameter, symmetric with `builtin_plugins`; the composed defaults are `KERNEL_ENTRY_POINT_GROUPS` in `providers/builtins.py` and `ENTRY_POINT_GROUPS` in `interpreter_plugins/builtins.py`, each beside the built-in manifest it belongs with.

**Decisions taken**

- **D-A1-1 — the cross-check is one-directional, and the Temporal plugin is what settles it.** A kernel-group plugin may not reach the interpreter tier; an interpreter-group plugin may contribute kernel-tier capabilities freely. A symmetric rule reads tidier but would reject our own Temporal plugin, which is interpreter-side (it contributes an orchestrator) *and* contributes an `add_http_error_mapper` — a kernel-tier capability by the plan's own classification. It would also be rejecting nothing dangerous: the risk is an interpreter-layer object being constructed in a kernel-only boot, and a kernel-only boot never loads the interpreter group at all. Pinned by a test that names the reason.
- **D-A1-2 — hub-slot tiering is a property of the slot, not a flag at the call site.** `HubSlot.is_interpreter_layer` uses an exhaustive match, so a newly added slot cannot be merged without classifying it. The classification tracks where each claim is *applied* — `PIPE_ROUTER` / `PIPE_RUN` / `PIPE_FUNC_EXECUTOR` in `Pipelex.setup`, the rest in the kernel boot.
- **D-A1-3 — built-ins carry no group and are exempt from the cross-check.** They are handed in as a list and filed by layer in-tree, where the hub-layering guard polices them statically; a kernel-only boot simply never passes the interpreter half. `PluginDiscovery.group` is `None` for them and `plugins list` shows `—`.
- **D-A1-4 — `begin_plugin(group=...)` is required, not defaulted.** It costs a mechanical `group=None` at ~30 test call sites that construct a registrar directly, and it buys the guarantee that a future discovery path cannot silently mislabel an external plugin as a built-in and skip the cross-check.
- **D-A1-5 — the retired-group probe runs on every build, whichever groups were asked for.** A plugin left under `pipelex.plugins` is broken in both boots, and the symptom without the probe — a capability simply absent, no error — is the expensive one to diagnose.

**Verification** — `make agent-check` green end to end. The plugins/providers/cli unit suites, both closure tests and the plugin integration suites: all green. The three new gates were mutation-tested: neutering the tier cross-check killed all six violation cases, ignoring the requested groups killed both kernel-only-boot cases, and neutering the retired probe killed its own case — each restored green after.

~~⚠ Owed at A3~~ — **discharged at A3**, see [A3 as built](#a3--as-built). Every doc telling a plugin author to publish under `[project.entry-points."pipelex.plugins"]` now names the right group.

### A2 — migrate the external plugins

Every currently-published external plugin is interpreter-layer, so all of them move to `pipelex.plugins.interpreter` and bump `targets_api`, each in one commit in its own repo: **pipelex-temporal** (orchestrator + bundle validator + slot claims), **pipelex-mistralai-workflows** (orchestrator), **pipelex-daytona-sandbox** (PipeFunc executor). The `pipelex.plugins.kernel` group starts with no external members — the future `pipelex-secrets-<backend>` / storage / inference-backend plugins are its intended population. Version pairing: each plugin repo's pipelex pin floor becomes the release that carries the new discovery; an older core will not see the new groups, which is acceptable under no-backward-compat but must be stated in each plugin's changelog.

#### A2 — as built

All three repos migrated, one commit each, all on a branch named `refactor/plugin-layer-groups`, **none pushed**:

- **pipelex-mistralai-workflows** — `029b476`, off `dev`. Entry-point group in `pyproject.toml`, the plugin docstring, `docs/reference-activities.md`, and `tests/integration/test_plugin_discovery.py` (which asserts the declared group, so it is the migration's own gate). Changelog entry.
- **pipelex-daytona-sandbox** — `a08d566`, off `dev`. Entry-point group in `pyproject.toml` and the plugin docstring. Changelog entry.
- **pipelex-temporal** — `1ed047a`, off `refactor/Topology` per Louis' call (see D-A2-2). Entry-point group, the plugin docstring, `begin_plugin(group=…)` at both call sites in `test_temporal_plugin_http_error_mapper.py` (one of them inside the import-light subprocess script), the D-A0-2 pointer fix, the prose sweep (`README.md`, `AGENTS.md`, `CLAUDE.md`, `docs/index.md`, `docs/installation-and-activation.md`), and a changelog entry.

`targets_api` needed no edit anywhere: all three plugins write `targets_api = PLUGIN_API_VERSION`, so the v4 bump follows the constant.

**Verification** — each repo's suite was run against the A1 core, by installing this worktree editable into that repo's venv (`uv pip install --no-deps -e ../_kernel`) plus a `-e .` reinstall so the dist metadata picks up the new entry-point group, then restoring the pinned pipelex afterwards. pipelex-temporal: full unit suite green, including both subprocess arms (the import-light register and the cold-import closure) — the parts no linter can see. pipelex-mistralai-workflows: full suite green, including the entry-point assertion and the tests that boot pipelex, so the retired-group probe is satisfied by the new metadata. pipelex-daytona-sandbox: suite green, but it never exercises discovery, so its layer claim was checked directly instead (below).

Each plugin's layer classification was also mutation-checked from the consumer side — registering under `PluginGroup.KERNEL` must fail: pipelex-temporal is refused on `orchestrator temporal`, pipelex-daytona-sandbox on `pipe_func executor daytona`. Both register cleanly under the interpreter group, and Temporal does so *while also* contributing its HTTP error mapper — the one-directional rule (D-A1-1) demonstrated end to end rather than argued.

⚠ **Each plugin repo's venv is now red on its migration branch**, and correctly so: the working tree declares the new group while the pinned pipelex reads only the retired one. That is the release gate showing through, not breakage — `uv sync` in each repo once the release lands.

**Decisions taken**

- **D-A2-1 — the commits stay local until the pipelex release lands.** These plugins are now undiscoverable by *released* pipelex (0.42.0 reads only the retired group), so a pushed PR's CI would install 0.42.0 and go red for a reason no code change can fix. Same for the pipelex pin floor the plan asks for: the release that carries layer-split discovery does not exist yet, so `pipelex>=0.41.0` / `>=0.42.0` stay as they are and the floor bump is owed at release time, together with the push and the PRs.
- **D-A2-2 — pipelex-temporal's commit is based on `refactor/Topology`** (Louis, 2026-08-10), resolving the question recorded in [`a2-pipelex-temporal-branch-question.md`](a2-pipelex-temporal-branch-question.md). It sits on its **own** `refactor/plugin-layer-groups` branch stacked on that base rather than being added to PR #18 itself: the base is what makes the D-A0-2 pointer fix possible at all (the file it corrects exists only there), while the separate branch keeps PR #18 untouched and preserves the one-Part-A-commit-per-repo property. Since the commit is release-gated anyway and cannot ship before #18, the entanglement costs nothing in practice. Once #18 merges to `dev`, this branch retargets to `dev` cleanly.
- **D-A2-3 — no new entry-point-declaration test in pipelex-temporal or pipelex-daytona-sandbox.** Only pipelex-mistralai-workflows had one to update. Adding the other two would duplicate what A3's core-side fake-dist gate covers mechanically; the per-repo claim that matters (this plugin is interpreter-layer) is enforced by pipelex at register time, which the mutation check above confirms is live.

### A3 — gates and checkpoint

- **The mechanical gate:** a subprocess test with a fake interpreter-group plugin dist (entry-point fixture; its module raises or writes a sentinel on import) asserting a kernel-groups-only discovery never imports it, while a both-groups discovery does. Mutation-test it: point the kernel boot at both groups and watch it go red before trusting it.
- Menu-tier cross-check tests (kernel-group plugin calling `add_orchestrator` → the structured error), legacy-probe test, and the existing suites: `make agent-check`, full `make agent-test`. *(The three plugin repos' own suites against an editable core were already run at A2 — see A2 as built.)*
- Changelog entry for **core** — the three plugin repos already have theirs. Update the SPI docs and `plugins list` docs: `docs/under-the-hood/{inference-backend,orchestrator,storage-provider,secrets-provider}-plugins.md` and `docs/cookbook/using-inference-plugins.md` all still instruct authors to publish under the now-fatal `pipelex.plugins` group.

#### A3 — as built

- **The mechanical gate**: `tests/unit/pipelex/plugins/test_installed_plugin_group_isolation.py`. It writes a real `*.dist-info/` with an `entry_points.txt` declaring an interpreter-group plugin, puts it on `sys.path`, and runs discovery in a **cold subprocess**; the plugin module writes a sentinel file when its body executes. A kernel-only boot must leave the sentinel absent and discover nothing; a both-groups boot must produce the sentinel *and* register the plugin. Mutation-tested both ways: making `_external_entry_points` ignore its `groups` argument fails on the kernel-only arm (exit 2), and declaring the fixture under a group nobody queries fails on the vacuity arm (exit 4).
- **Menu-tier cross-check tests, the legacy-probe test, and the group-filtering test already landed with A1** — the A3 checklist listed them, but building the mechanism without its tests was never on the table. A3 added only the gate A1 could not give: the one that uses real installed metadata instead of a patched `importlib.metadata`.
- **Docs swept.** Each SPI page now names the group its capability belongs to — kernel for inference backends, storage and secrets; interpreter for orchestrators. `inference-backend-plugins.md` carries the full explanation (what each group means, what a wrong choice costs in each direction, that the retired group is a startup error) and the other pages link to it rather than repeat it. `orchestrator-plugins.md` additionally states the one-directional rule and why Temporal is the case that settles it. The three `pipelex plugins list` references now mention the Group column and that it is the first thing to read when a plugin is missing. The seam diagrams stopped naming the retired group.
- **Changelog**: nothing owed. A1's entry already describes the split, the enforcement, its direction, the retired-group error and the Group column; A3 added a test and doc corrections, neither of which is release-facing on its own.

**Decisions taken**

- **D-A3-1 — the cookbook example plugin was migrated too, and it was not on the plan's list.** A workspace-wide sweep for `entry-points."pipelex.plugins"` (enumerating every sibling directory rather than trusting the plan's three-repo list) turned up a fourth consumer: `pipelex-cookbook`'s `hello-inference-plugin`. Migrated to `pipelex.plugins.kernel` — an inference backend is kernel-layer — as commit `87c6800` on a `refactor/plugin-layer-groups` branch off `dev`, **not pushed**, release-gated like the others (D-A2-1). Leaving it would also have made the `using-inference-plugins.md` page A3 just corrected describe an example that contradicts it.
- **D-A3-2 — `pipelex.plugins` the *package* was deliberately left alone.** The retired entry-point group and the kernel-layer Python package share a spelling, and `docs/contribute/hub-layering.md` refers to the package repeatedly (the transitive-breach worked example). A blind sweep would have corrupted that page. Historical `CHANGELOG.md` entries were left alone for the same reason: they record what shipped at the time.
- **D-A3-4 — pipelex-api was a fifth consumer, and the A2/A3 sweep predicate could not see it.** Both sweeps searched for `entry-points."pipelex.plugins"` *declarations*, which is what found the cookbook. pipelex-api declares no entry point — it **calls `build_registrar`**, and that function gained a required parameter. Its call site resolves at module scope (`HTTP_ERROR_MAPPERS = _resolve_http_error_mappers()`), so the omission is an import-time `TypeError` that takes the whole runner down, not a degraded feature. Verified red-green against the in-flight core: reverted, `import api.main` raises; restored, it imports and its full suite passes. A second instance of the same break lived in its test helper (`begin_plugin` also gained a required `group`), which only running that suite surfaced. **Lesson for any future entry-point or SPI-signature change: sweep for *callers of the changed function*, not only for declarations of the changed group — they are different populations and only one of them was covered.**
- **D-A3-3 — no new `plugins list` reference page.** The command has never had one; the three SPI pages mention it in prose. Adding a CLI reference page is a real gap but a separate concern (it was already recorded against the `cli-docs` drift contract at A1), and inventing one here would have widened Part A past its subject.

**Verification** — `make agent-check`, `make drift-check` (staged, since it reads the index) and the **full `make agent-test`** all green on the A3 tip.

🛑 **CHECKPOINT A — reached 2026-08-10. Part A is complete and green; nothing is pushed.**

**State.** Core: commits on `refactor/Kernel-4` in the `_kernel` worktree — A0 (`283abd7d2`), A1 (`529ca483f`), the A2 record (`47b21887e`, preceded by `b5da2c1fb`), A3 (`f6672b2d1`), plus the checkpoint-review fixes. **Five** downstream repos each hold one unpushed commit on a `refactor/plugin-layer-groups` branch: pipelex-mistralai-workflows `029b476`, pipelex-daytona-sandbox `a08d566`, pipelex-temporal `1ed047a` (based on `refactor/Topology`, D-A2-2), pipelex-cookbook `87c6800` (D-A3-1), pipelex-api `d5acdfb` (D-A3-4).

**What ships together.** Part A is one core PR plus **five** downstream PRs, and they **cannot go first**: released pipelex reads only the retired group, so their CI would install it and go red for a reason no code change fixes (D-A2-1). Order: land the core PR, cut the pipelex release, then push the five branches, open their PRs, and bump each repo's pipelex pin in the same window. pipelex-temporal additionally waits on PR #18 (its base), which the release gate makes free.

**Open at this checkpoint.**

- The pipelex pin bumps in all five downstream repos — owed at release, deliberately not done now (D-A2-1). pipelex-api pins exactly (`==`), so it is a hard bump, not a floor.
- Each downstream repo's venv is red on its migration branch until that release; `uv sync` after.
- No `pipelex plugins list` CLI reference page exists (D-A3-3).
- Review-deferred items and three open questions for Louis: [`plugin-group-split-deferred-items.md`](plugin-group-split-deferred-items.md).
- Part B's open questions are unchanged and still Louis' — see [Open questions](#open-questions-louis). B is *not* started.

## Part B — the in-repo `pipelex_kernel` package (unpublished)

The kernel layer moves out of `pipelex/` into a top-level `pipelex_kernel/` package at the repo root, beside `pipelex/`. One repo, one distribution: the `pipelex` wheel ships both top-level packages, PyPI's surface is unchanged, and nothing new is published. What this buys on its own: the layer boundary becomes visible in the tree and in every import statement, and the one-way dependency becomes a one-line static rule — **nothing under `pipelex_kernel/` may import `pipelex`** — which is impossible to state that cleanly while the kernel lives inside the `pipelex` package.

### B0 — footprint measurement (read-only, can start any time)

Compute what the kernel package would actually contain and require: the kernel layer's module set (seeded by the kernel-layer import-closure test and the kernel boot contract's `sys.modules` sweep), its third-party dependency closure, and an install-size estimate. Deliverable: `wip/kernel/kernel-distribution-footprint.md`. This drives B1's content line now, and would inform a Part C greenlight and its extras design later: if the hard dependency set is small, the eventual headline ("look how little you need") is an asset; if provider plumbing drags heavy deps, extras (`pipelex-kernel[<backend>]`) would get designed before any publish, not after.

### B1 — decisions

- **D-B1 package layout:** top-level package `pipelex_kernel/` at the repo root, beside `pipelex/`. A `pipelex.kernel` namespace stitch is rejected — `pipelex` is a regular package, two wheels cannot co-own it (which would matter the moment a Part C split the dist), and the family convention (pipelex_temporal precedent, decision D8 of the plugin externalization) is top-level packages.
- **D-B2 the content line:** which packages move (kernel façade, plugin mechanism + registries, providers, boot, config/system, base exceptions, urls, the tools subset the closure actually reaches, telemetry) — driven by B0's measurement, not by intuition. Anything the kernel-layer closure does not reach stays in `pipelex`.
- **D-B3 kernel-consumer import surface:** code written against the kernel imports `pipelex_kernel.*` from B2 onward. Any tooling that generates such code, and any existing kernel-consuming code, re-targets its imports in one window after B2 (see Sequencing). A greenlighted Part C would change nothing about imports.
- **D-B4 CLI:** the kernel package ships no user CLI (the kernel is a library surface; `pipelex` keeps the CLI). Revisit only if B0 surfaces a real need.
- **D-B5 the layering ban's form:** a static AST scan over `pipelex_kernel/**` rejecting any `import pipelex` / `from pipelex` (deterministic and total), plus a cold-import closure check (importing any `pipelex_kernel` module in a fresh subprocess never brings a `pipelex.*` module into `sys.modules`). Both run in `make agent-check`-adjacent gates and CI.

### B2 — the move + gates

`git mv` the kernel-layer packages into `pipelex_kernel/` and repoint every import, folding in the Part-B rename bucket (`RuntimeBoot` → `KernelBoot`, the runtime hub under its kernel name). Known move-consequence classes to work through deliberately (the kernel-extraction plan's "What Phase 1 taught Phase 2" applies):

- **Transport boundary:** any module named in `docs/specs/pipelex-transport-boundary.md` / the conformance `ALLOWED_SURFACE` that moves gets re-pinned in the same change — spec, conformance test data, the pipelex-transport repo, and the two commercial plugins that import it; run `make check-spec-links` in conformance.
- **Path-scoped tooling must widen or it goes quiet:** every gate whose scope is a path list silently stops policing moved code unless extended to `pipelex_kernel/` — the keyword-only guard, the hub-layering guard, the error-class location/uniqueness tooling and doc generators, import-light tests, coverage config, ruff/pyright/mypy/isort package settings, Makefile targets. Enumerate them as part of the move, don't discover them by absence.
- **Packaging config:** the `pipelex` wheel explicitly ships both top-level packages; `py.typed` in the new package; verify the built wheel installs and imports cleanly from a scratch venv.
- **Subject grants:** `subject_grants.toml` keys on file paths — re-key every grant whose def moved (the kernel façade itself is zero-grants; the moved tools/config modules are not).
- **Drift contracts:** `drift.toml` triggers referencing moved paths; stage before `drift-ack` (the digest reads the git index).
- **Error identity:** regenerate error pages and the error-identity snapshot after the move; class names don't change, so the wire `error_type` is stable — verify the snapshot diff is paths-only.
- **Test-tree reconciliation:** tests for moved modules move to a parallel `pipelex_kernel` test tree (Phase-5 temporal reconciliation is the precedent, including the shared-fixture split).
- **Downstream import sweeps:** enumerate the workspace directory for consumers (do not work from a remembered list) — the three plugin repos repoint `pipelex.<kernel-layer>` imports to `pipelex_kernel.*` when they bump their pins past B2, and update their copied interpreter-package guard lists; sweep every other `pipelex` importer for moved-path imports.
- The layering ban (D-B5) lands in the same change as the move and is mutation-tested (add a forbidden import, watch it go red).

🛑 **CHECKPOINT B** — shippable as a normal `pipelex` release: breaking import paths (minor bump), wheel ships two top-level packages, PyPI surface unchanged. Record status, the as-built content line, and B0's measured numbers (by pointing at the footprint doc, not inlining them). **This is the plan's committed end-state** — anything beyond it is Part C, which needs its own greenlight.

## Part C — the `pipelex-kernel` distribution (HYPOTHETICAL — needs an explicit greenlight)

**Nothing in this part is decided.** It is written down so the option is concrete when the greenlight question is asked; no phase here starts without Louis' explicit go, and Part B stands complete without it. If greenlighted, it would be packaging-only: no code moves, no import statements change — `pipelex_kernel` would get its own pyproject and become the published distribution `pipelex-kernel`, with `pipelex` depending on it in lockstep.

### C0 — the greenlight

The decision this plan does not make: registering the public `pipelex-kernel` name is a commitment. A greenlight resolves OQ-1 (supported public surface vs documented internal substrate) and OQ-2 (extras at first publish, from B0's numbers), with Louis. Absent it, Part B remains the end-state indefinitely.

### C1 — the distribution split

- Two pyprojects under a uv workspace (exact member layout decided here; any directory shuffle is packaging-only — imports are already `pipelex_kernel.*`); lockstep version, `pipelex` depends on `pipelex-kernel==<same version>`; wheel-metadata check that no editable/path pin leaks into `Requires-Dist` (the pipelex-temporal Phase-5 verification is the template).
- Release flow: one release cut publishes `pipelex-kernel` first, then `pipelex`; the release skill gains the two-dist ordering.

### C2 — the physical gate + proof

- **The physical gate:** a CI job that syncs a venv with *only* `pipelex-kernel` and its test deps — where `import pipelex` is a `ModuleNotFoundError` — and runs the kernel test suite plus the keyless boot contract there. This supersedes the static ban and closure tests as the primary boundary enforcement (they remain as fast in-repo guards).
- **The proof, in a clean venue:** fresh venv, install `pipelex-kernel` (wheel or index), run a kernel-only consumer, sweep `sys.modules` — the interpreter count is structurally zero because the interpreter is not installed. Any trust-base measurement is re-run there; never quote a closure number taken in a venv that also has full `pipelex` (the lesson that started all this).
- Docs: `docs/under-the-hood/pipelex-kernel.md` gains the distribution story; public docs get the install surface; changelogs across every touched repo. Downstream installs are otherwise unaffected — `pipelex` still pulls everything in; kernel-only consumers may now thin their install.

🛑 **CHECKPOINT C** — record the published versions, the clean-venue proof, and any support-surface decisions.

## Sequencing and gates

- **Part A is unblocked now** and lands on `dev` independently. The kernel stack is merged; nothing in A waits on anything.
- **B0 can run any time** (read-only measurement); **B1/B2 start after Checkpoint A** so the group split and naming are settled before module paths churn.
- **Part B is a normal release and the plan's committed end-state** — a legitimate place to stop indefinitely. Only the clean-venue story and the install headline would wait on a greenlighted C; nothing else downstream blocks on it.
- **Part C is hypothetical until explicitly greenlighted (C0)** — it is the irreversible step, which is exactly why B exists as its own stage and why this plan commits to nothing beyond B.
- **The kernel-consumer churn window:** anything written against the kernel API re-targets its imports to `pipelex_kernel.*` when it bumps its pipelex pin past B2. Consumers with their own pending sweeps should schedule the pin bump so all their kernel-facing churn lands in one window; a consumer that must move sooner sweeps twice — acceptable, but say so out loud when it happens.
- **`refactor/Topology` (PR #1008)** is the one branch in flight on top of dev. Overlap checked (2026-08-10): none of Part A's code footprint is touched by it; the only shared file is `docs/under-the-hood/orchestrator-plugins.md` (its prose is in A0's sweep). Land #1008 before starting A0 and the overlap disappears entirely; if A0 goes first, expect one trivial doc conflict there.
- Version semantics: Part A is breaking on the plugin contract → minor bump (pre-1.0 convention). Part B is breaking on import paths everywhere → minor bump, and the release that carries it should carry nothing else surprising. A greenlighted Part C would publish a new dist and re-shape `pipelex`'s dependency metadata → minor bump.

## Enforcement model across the parts

| Threat | Before | After A | After B | After C (if greenlighted) |
| --- | --- | --- | --- | --- |
| Our plugin imports the interpreter at module scope | per-plugin guard test (subprocess cold-import) | same, plus never loaded by a kernel boot | same | import fails in a kernel-only venv |
| Third-party plugin drags the interpreter | nothing (discovery loads every installed plugin) | not loaded by a kernel boot (wrong group); fail-loud if it lies via menu calls | same (a venv with full `pipelex` still carries the interpreter) | uninstallable in a kernel-only venv (its dep on `pipelex` cannot resolve) |
| Plugin declares the wrong layer | n/a (no layer axis for externals) | menu-tier cross-check fails loud at register | same | same, plus physics |
| Kernel code quietly imports the interpreter | closure tests + boot-contract sweep (per-function, has missed an entry point before) | same, under the kernel-layer name | statically impossible to merge (the one-line ban over `pipelex_kernel/`) + cold-import closure | the kernel-only CI venv makes it a hard ImportError |

## Risks and traps

- **Silent nondiscovery** is the failure mode of retiring an entry-point group — the legacy probe exists to convert it to a loud error; don't drop the probe as "cleanup" later without a deliberate decision.
- **Path-scoped gates go quieter on omission** — a guard whose path list doesn't include `pipelex_kernel/` reports nothing about it, which reads as clean. B2's tooling-widening bullet is the antidote; verify each widened gate by mutation, not by green.
- **Copied guard lists drift quietly** (pipelex-temporal's interpreter-package list is a copy of the canonical one) — every rename in this plan that touches the canonical list or its filename must update the copies and their pointers in the same window.
- **Stale `*.egg-info` shadows entry points** during editable development — if entry points are "not discovered" locally, remove stale root egg-info before debugging anything else.
- **Any module move must grep pipelex-transport and its spec/conformance pair** (workspace rule) — B2's biggest cross-repo obligation.
- **Sweeps enumerate the directory, not a remembered repo list**, and workspace-root recursive greps silently return nothing across sibling repos — loop over the repos explicitly.
- **Closure numbers are per-venue** — Part B does not change what a full-`pipelex` venv contains; the only quotable measurement remains one taken in a kernel-only venv, which would exist only after a greenlighted C.

## Open questions (Louis)

1. **OQ-1 public commitment (this IS the Part C greenlight):** publishing `pipelex-kernel` to PyPI invites third parties to build on the kernel API directly. Is the kernel a supported public surface, or primarily an internal substrate (documented as such)? Part B proceeds without answering this, and Part C does not exist until it is answered with a yes.
2. **OQ-2 extras design (only if Part C is greenlighted):** if B0 shows provider plumbing dragging heavy optional deps, do we want per-backend extras on `pipelex-kernel` at first publish, or a minimal core with extras added on demand?
3. **OQ-3 timing vs kernel-consumer tracks:** for work in flight that consumes the kernel API, should B2 land first (so new consumers are born targeting `pipelex_kernel.*`), or should those tracks proceed on the current import surface and sweep later?
