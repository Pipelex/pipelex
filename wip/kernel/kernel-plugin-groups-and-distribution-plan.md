# Kernel layer: named, layer-gated plugins, and its own distribution

**Goal.** Two staged moves that turn the kernel/interpreter boundary from a convention into a mechanism and then into enforced structure — plus a third that is deliberately left hypothetical: **Part A** splits plugin discovery by layer under kernel-branded entry-point groups (`pipelex.plugins.kernel` / `pipelex.plugins.interpreter`), with a coherent rename of the layer vocabulary from "runtime layer" to "kernel layer". **Part B** moves the kernel layer into its own top-level package `pipelex_kernel/` at the repo root, beside `pipelex/` — same repo, same single distribution, **not** published separately — making the one-way dependency statically checkable in one line. **Part C is a hypothetical, not a commitment**: it *would* ship `pipelex_kernel` as its own PyPI distribution `pipelex-kernel`, so a kernel-only consumer's venue physically could not contain the interpreter — but it proceeds only on an explicit greenlight (C0), and this plan commits to nothing beyond Part B.

**Why.** The kernel trust-base story ("this code imports only the kernel") is a per-venue claim: measurement showed that merely *installing* the Temporal plugin dragged the whole interpreter into every pipelex process in the venv, because plugin discovery imports every installed plugin's module. The plugin-side violation was fixed at pipelex-temporal HEAD ("Keep the interpreter out of an import-light register, and gate it", 2026-08-09) — but that fix protects only plugins we author. Part A makes a kernel-only boot never even `load()` interpreter-side entry points; Part B makes a kernel→interpreter import impossible to merge (a static ban over `pipelex_kernel/`); a greenlighted Part C would make the interpreter uninstallable in a kernel-only venue, closing the hole for plugins nobody vetted — and would make the story self-evidencing: `pip install pipelex-kernel`, drop in your kernel-consuming code, run.

**Why B is the plan's end-state and C stays hypothetical.** The big mechanical churn (every kernel-layer import repoints) lands without touching the release surface — the `pipelex` wheel simply ships two top-level packages, and PyPI sees nothing new. The irreversible step (registering and committing to a public `pipelex-kernel` distribution) is deliberately **not decided by this plan** — it is a distinct future decision, to be taken with B's measured footprint in hand. And consumers churn once either way: imports move to `pipelex_kernel.*` at B, and a later C would change only install metadata. Precedent: the Temporal externalization deliberately separated the reversible local cut-over from the publish gate.

## Status

| Part | Phase | State |
| --- | --- | --- |
| A | A0 naming ruling + inventory | not started |
| A | A1 group-split mechanism | not started |
| A | A2 external-plugin migration | not started |
| A | A3 gates + checkpoint | not started |
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

### A1 — the group-split mechanism

- Two entry-point groups replace the single `pipelex.plugins`: **`pipelex.plugins.kernel`** (inference backends, model listers, storage providers, secrets providers, HTTP-error mappers) and **`pipelex.plugins.interpreter`** (orchestrators, bundle validators, PipeFunc executors, interpreter-side hub-slot claims).
- `build_registrar` gains an injected `entry_point_groups` parameter, symmetric with the existing `builtin_plugins` injection: the kernel-only boot passes the kernel group alone; the interpreter boot passes both. The discovery module itself keeps naming no layer-welding constant — the composed defaults live where the builtin lists live today.
- **Menu-tier cross-check.** Classify each registrar menu method by tier (kernel-tier: `add_inference_backend`, `add_model_lister`, `add_storage_provider`, `add_secrets_provider`, `add_http_error_mapper`; interpreter-tier: `add_orchestrator`, `add_bundle_validator`, `add_pipe_func_executor`; slot claims classified per-slot). Discovery records which group a plugin arrived under, and the registrar fails loud when a kernel-group plugin calls an interpreter-tier menu method. This catches a plugin lying about its layer at register time — the import-contamination half is caught by the per-plugin guard tests (Part A world) and, in a greenlighted Part C world, by physics.
- **Legacy-group probe, fail-loud.** Discovery also reads the retired `pipelex.plugins` group; any entry point found there raises with a migration message naming the plugin and the two new groups. Silent nondiscovery is the quiet failure mode this probe exists to prevent.
- `PLUGIN_API_VERSION` bumps (breaking change to the plugin contract); `pipelex plugins list` gains the layer/group column.

### A2 — migrate the external plugins

Every currently-published external plugin is interpreter-layer, so all of them move to `pipelex.plugins.interpreter` and bump `targets_api`, each in one commit in its own repo: **pipelex-temporal** (orchestrator + bundle validator + slot claims), **pipelex-mistralai-workflows** (orchestrator), **pipelex-daytona-sandbox** (PipeFunc executor). The `pipelex.plugins.kernel` group starts with no external members — the future `pipelex-secrets-<backend>` / storage / inference-backend plugins are its intended population. Version pairing: each plugin repo's pipelex pin floor becomes the release that carries the new discovery; an older core will not see the new groups, which is acceptable under no-backward-compat but must be stated in each plugin's changelog.

### A3 — gates and checkpoint

- **The mechanical gate:** a subprocess test with a fake interpreter-group plugin dist (entry-point fixture; its module raises or writes a sentinel on import) asserting a kernel-groups-only discovery never imports it, while a both-groups discovery does. Mutation-test it: point the kernel boot at both groups and watch it go red before trusting it.
- Menu-tier cross-check tests (kernel-group plugin calling `add_orchestrator` → the structured error), legacy-probe test, and the existing suites: `make agent-check`, full `make agent-test`, pipelex-temporal's own gates against an editable core.
- Changelog entries (core + the three plugin repos). Update the SPI docs and `plugins list` docs.

🛑 **CHECKPOINT A** — Part A is independently shippable on `dev` as one PR (core) plus one commit per plugin repo. Record status, decisions, and open questions here before starting Part B.

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
