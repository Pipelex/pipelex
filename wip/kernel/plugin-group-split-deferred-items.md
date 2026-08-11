# Plugin group split — deferred items

Raised by the Checkpoint A review of the entry-point group split (Part A of the kernel track). Each item below was verified against the code and judged **not** worth fixing inside Part A — either because it is a design question that is Louis' to rule on, or because the remedy is machinery bought for a path nothing can reach yet. Items the review raised that *were* fixed in Part A are not listed here.

One review finding was checked and **rejected**: the claim that `PluginGroup` could live in `contract.py` because `contract.py`'s import of `PluginRegistrar` is `TYPE_CHECKING`-only. pyright's `reportImportCycles` (an error in this repo) flags `TYPE_CHECKING` cycles too — verified empirically by adding a runtime `contract` import to `registrar.py` and running pyright, which reported `Cycle detected in import chain`. The separate `plugin_group.py` module and its stated rationale are correct as they stand.

---

## D-1 — The retired-group probe pre-empts the `plugins.disabled` denylist

**What.** `build_registrar` runs `_reject_retired_entry_point_group()` as its first statement, before it reads `config.plugins.disabled`. So the documented recovery path — "denylisted by their entry-point name *before* `load()`, so a broken installed plugin can still be disabled to recover startup" — does not cover this one failure class.

**Why it matters.** An operator with some third-party plugin still published under `pipelex.plugins` gets `RetiredPluginEntryPointGroupError` on every pipelex process in that venv, and `plugins.disabled` cannot quiet it. `pipelex plugins list` — the tool the docs point at when a plugin is missing — also calls `build_registrar`, so the diagnostic is dead too. Recovery is uninstall or upgrade.

**Why not fixed here.** It is a deliberate ordering, not an oversight: the probe exists precisely because silent nondiscovery is the expensive failure, and honouring the denylist would let an operator re-create that silence. But the asymmetry with a promise made in three SPI doc pages deserves an explicit ruling rather than an implicit one. The error message was widened in Part A to name the two actions actually available to an operator (upgrade, uninstall).

**If revisited.** Filtering the probe's straggler list through `plugins.disabled` is a two-line change. The question is whether "I disabled it, let me boot" should beat "you have an unmigrated plugin and would otherwise not notice".

---

## D-2 — The split governs registration, not imports

**What.** The group split guarantees that a kernel-only boot does not *query* the interpreter group, plus a menu-tier check on what a kernel-group plugin may register. Nothing constrains what a **kernel-group** plugin's module *imports*.

**Why it matters.** A third-party plugin published under `pipelex.plugins.kernel` that registers only an inference backend, but has `from pipelex.pipe_run import ...` at module scope, is loaded by a kernel-only boot and drags the interpreter in — the exact shape of the contamination that motivated this track. The plan is honest about this ("that fix protects only plugins we author"); Part A softened the CHANGELOG wording to match, so no shipped text now claims more than is enforced.

**Why not fixed here.** Closing it means an import-closure rule over third-party code — a fundamentally different mechanism from a declaration, with real cost (importing the plugin to inspect its closure is itself the thing being prevented, so it needs a subprocess or a static walk). That is Part C territory and is explicitly gated on Louis' greenlight.

---

## D-3 — The menu-tier cross-check is attribution-based

**What.** `_require_interpreter_layer` reads `self._active.group`, and `_active` is whatever `begin_plugin` last set. A plugin that stashes the registrar during `register` and calls a menu method *later* — from a `make_worker` closure, or a factory thunk invoked at a boot apply-point — is checked against whichever plugin registered last.

**Consequence.** The deferred call passes if the last-registered plugin was interpreter-group, and names the wrong plugin in the error if not.

**Why not fixed here.** This requires the plugin to violate the documented "`register` is side-effect-free" invariant, which is stated in every SPI page. It is a hardening note, not a live bug. If revisited, binding the check to the discovery object handed to the plugin (rather than to registrar state) removes the ordering dependence entirely.

---

## D-4 — A plugin published under both groups produces a self-referential duplicate error

**What.** `_external_entry_points` iterates groups and yields an entry point once per group, so a distribution declaring itself in both is discovered twice. The second registration hits `_add` and raises e.g. `DuplicateInferenceBackendError(first_plugin="acme", second_plugin="acme")` — *"registered by both plugin 'acme' and plugin 'acme'"*.

**Why not fixed here.** It is loud, so nothing silently misbehaves; only the message misleads. A dedupe by entry-point name, or a distinct `PluginPublishedUnderBothGroupsError`, would be clearer. Untested either way today.

---

## D-5 — `PluginDiscovery.group is None` is an unenforced invariant

**What.** `group: PluginGroup | None` encodes "built-in", which `origin` already encodes. Nothing asserts `group is None ⟺ origin is BUILTIN`, and `_require_interpreter_layer` silently skips when `group is None`.

**Why it matters.** Not reachable through `build_registrar` today — every external path passes a group. But a future refactor that forgets to thread `group` degrades the cross-check to a no-op *silently* rather than loudly. Several tests construct `origin=EXTERNAL, group=None`, a state production cannot produce.

**If revisited.** Either derive the group from origin at construction, or assert the pairing in `begin_plugin`. Both are small; the question is whether two fields should encode one fact at all.

---

## D-6 — `INTERPRETER_TIER_CALLS` has no mechanical link to the menu

**What.** The `claim_*` half of the cross-check is mechanical (the guard lives in `_claim`, so a new slot is covered automatically and the exhaustive match forces a classification). The `add_*` half is three hand-placed `_require_interpreter_layer` calls.

**Consequence.** Adding a new interpreter-tier menu method without the guard call is caught by nothing — the test dict simply does not grow.

**Why not fixed here.** The mechanical remedy (walking the registrar's public methods in a test) is more machinery than the exposure justifies for three call sites. A comment on the three `add_*` methods pointing at the dict would carry most of the value.

---

## D-7 — The plugins unit tests are coupled to the developer's installed environment

**What.** The retired-group probe reads the real venv and is not stubbable at the seam the tests patch (`_external_entry_points`). And `test_installed_plugin_group_isolation` asserts a both-groups discovery registers **exactly** the synthetic fixture.

**Consequence, and it is live during this change window.** A developer with an unmigrated plugin editable-installed sees the whole plugins test tree fail with `RetiredPluginEntryPointGroupError`; one with a *migrated* plugin installed sees the isolation test fail on an exit code whose message does not say "you have a plugin installed". The paired-branch release ordering makes both states normal until the plugin repos land.

**If revisited.** Asserting the fixture is *among* the discoveries rather than the sole one removes half of it; making the probe injectable removes the rest.

---

## D-8 — `PluginLayerViolationError`'s "before anything it contributed is wired"

The docstring claims the violation is caught before any contribution is wired. The test asserts the exception and its message fragments, not the ordering — moving `_require_interpreter_layer` after `_add` in all three methods would stay green. Low practical impact (the registrar is discarded when `build_registrar` raises), but the docstring makes a claim nothing holds up.

---

## Open questions — Louis' to rule on

### OQ-1 — Is `TASK_MANAGER` correctly classified as kernel-tier? — **RESOLVED: yes, and the docstring was what was wrong**

`HubSlot.is_interpreter_layer` gave two criteria and presented them as coinciding: *"whether claiming this slot means handing back a `Pipe`-aware object"* and *"which is also where the claim is applied"*. For `TASK_MANAGER` they arguably did not. The claim is applied in the kernel boot, which says kernel-tier; but the only real claimant stands up a Temporal worker registering workflows over pipes, which reads Pipe-aware.

The question was: whether any conceivable task-manager implementation can be built without naming an interpreter type. It can, and one already ships. Three findings:

- **`TASK_MANAGER` is the only slot whose return core discards.** The kernel boot's apply-point invokes the thunk and drops the result; every other slot flows its value back into core (four through `_resolve_hub_slot`, `ISOLATED_EXECUTION_PROBE` through `set_isolated_execution_probe`). So the "hands back a `Pipe`-aware object" criterion is not False for this slot — it is *inapplicable*. There is no returned object to classify.
- **Kernel-only worker scopes already exist.** Our Temporal plugin's per-backend runner scopes each disable all workflows, require no task pack, and name only leaf content-generation activities. That is a task manager standing up a worker serving purely kernel-tier work — the one-worker-pool-per-backend-class deployment.
- **Those activities name only kernel-layer modules** — `pipelex.cogt.content_generation.*`, `pipelex.core.stuffs.image_content`, `pipelex.runtime_hub`. No `Pipe` type on that path.

**Ruling:** `TASK_MANAGER` stays kernel-tier. No code change, no SPI change, nothing release-gated — a kernel-group plugin claiming it to stand up a specialized runner pool is coherent, and a kernel-only boot applying that claim serves real work.

The remedy inverts what this entry proposed. The first criterion cannot govern, because for this slot there is nothing handed back; the apply-point is the only criterion every slot has. The `is_interpreter_layer` docstring now leads with the apply-point and names `TASK_MANAGER` as the reason the returned-type reading corroborates but cannot decide. What made the slot read Pipe-aware is that our plugin's *catalog* names pipe workflows at module import — that is the catalog handed to the task manager, not the slot's contract, and that plugin is interpreter-group anyway.

### OQ-2 — Should the retired-group probe be permanent?

The repo rule is "no backward compatibility — just change it". The probe is a permanent, un-disableable, per-boot metadata scan whose only job is to catch a migration that completes when the paired releases land. For: fail-loud beats silent nondiscovery, and the cost is one cached `entry_points()` call. Against: it is a compat artifact with no expiry, it adds a third metadata scan to every `build_registrar` (which the runner API executes at import), and it creates the unrecoverable state in D-1.

**What would settle it:** whether any *published* distribution outside this workspace declares `pipelex.plugins`. If it is only ours — all migrated in the same window — the probe could carry a "remove after vX.Y" marker rather than living forever.

### OQ-3 — Does `pipelex.plugins.plugin_group` belong in the documented SPI symbol list?

Plugin authors declare their group in `pyproject.toml` and never import the enum. But a plugin that unit-tests its own `register` must construct a registrar, and `begin_plugin` now requires `group=` — so the enum is a de-facto *test-surface* dependency for any plugin with its own tests. Our own Temporal plugin imports it for exactly that reason. Whether a test-surface dependency belongs in the versioned SPI list is a policy call.
