# A runtime-only boot accepts an external interpreter-side orchestrator, then half-applies it

**Status: RESOLVED** by the plugin entry-point group split (Part A of the kernel track). The analysis below is kept for the rationale trail; read the closing section first — its central premise no longer holds.

## The hole

`RuntimeBoot.setup` gates the requested boot orchestrator like this:

```python
requested_boot_orchestrator = get_config().plugins.boot_orchestrator
if requested_boot_orchestrator is not None and requested_boot_orchestrator not in plugin_registrar.registered_plugin_names:
    raise UnknownBootOrchestratorError(requested=requested_boot_orchestrator)
```

On a bare runtime boot, `builtin_plugins` defaults to `RUNTIME_BUILTIN_PLUGINS`, so an orchestrator contributed by an interpreter-layer **built-in** (`direct`) is never registered and the gate correctly rejects it.

But `build_registrar` discovers **external** `pipelex.plugins` entry points unconditionally — the `builtin_plugins` parameter only scopes the built-in half (`plugins/discovery.py`, the `for entry_point in _external_entry_points()` loop). So an installed external interpreter-side orchestrator — our Temporal plugin is the live example — registers its name on a runtime-only boot too, and satisfies the gate.

What follows is silent and incoherent. The six `HubSlot`s split exactly 3/3 along the layer line:

| slot | applied in |
|---|---|
| `CONTENT_GENERATOR` | `runtime_boot.py` |
| `TASK_MANAGER` | `runtime_boot.py` |
| `ISOLATED_EXECUTION_PROBE` | `runtime_boot.py` |
| `PIPE_FUNC_EXECUTOR` | `pipelex.py` |
| `PIPE_ROUTER` | `pipelex.py` |
| `PIPE_RUN` | `pipelex.py` |

So `RuntimeBoot.make(boot_orchestrator="temporal")` with the plugin installed applies the plugin's **runtime** claims — including `TASK_MANAGER`, which does the full worker wiring — never applies its `PIPE_ROUTER` / `PIPE_RUN` / `PIPE_FUNC_EXECUTOR` claims, and then sets `is_ready = True`. A process that believes it is running under an orchestrator, isn't.

## Why it was not fixed on #1073

- **Unreachable today.** It needs all three of: an external interpreter-side orchestrator plugin installed, config or an argument naming it, *and* a caller of `RuntimeBoot.make()`. There are no callers yet — the PR is explicit that the pinned test entry points are the only ones.
- **Every remedy needs a layer signal the runtime layer deliberately does not have.** A `PipelexPlugin` carries no layer field, and `docs/contribute/hub-layering.md` says so on purpose ("a plugin belongs to exactly one layer… Nothing enforces it mechanically"). Asking the runtime layer to classify plugins by layer inverts the boundary the split exists to draw.
- **The nearest clean remedy is a flag on the class pair that exists to avoid flags** — see below. On the same PR, the doctor-adoption question was declined for exactly this reason ("a flag argument added to make one caller fit is a worse outcome than two short sequences that differ honestly"), so adding one here for a path with no callers would contradict the decision taken twenty lines away.

## Candidate remedy, for whoever adds the first runtime-only caller

The invariant is expressible without classifying *plugins*, because the split is a property of the **slots**, which already live in the runtime layer:

1. Give `HubSlot` an `is_interpreter_slot` property — a `match`/`case` over the six members. Exhaustive, so adding a seventh slot forces a placement decision at the type level (this repo's StrEnum idiom, per `.claude/rules/python-standards.md`).
2. Let the boot say whether it honours those slots — a class attribute `RuntimeBoot.honours_interpreter_slots = False`, overridden `True` in `Pipelex`. This is polymorphism rather than a parameter, which is the mechanism the split already chose, so it is the least-bad shape available.
3. In `RuntimeBoot.setup`, after `build_registrar`, raise when `honours_interpreter_slots` is false and any claimed slot is an interpreter slot. Name the plugin and the slots in the message.

That check also subsumes the narrower orchestrator question: it catches *any* external plugin whose claims a runtime-only boot cannot honour, not just orchestrators, and it does not care whether the plugin is built-in or external.

**Cheaper alternative worth weighing first:** have `build_registrar` take the set of slots the caller will apply and refuse a claim outside it. That pushes the check into the one place that already knows every claim, and removes the class attribute — but it widens `build_registrar`'s signature, and that function is currently a pure discover-and-register with no policy in it, which is a property worth protecting.

## The first runtime-only caller has arrived — and the verdict is "still not now"

`tests/unit/pipelex/kernel/test_kernel_boot_contract.py` (the pipelex-kernel extraction, Phase 1) is the first thing in the tree to call `RuntimeBoot.make()` for a purpose other than measuring the boot itself: it boots runtime-only and then *runs* both kernel façade calls (`llm_object` and `llm_text`) on it. That is the caller this document deferred the decision to, so the decision is recorded here rather than left open.

**It does not trigger the hole, and not by luck.** The gate is only reached when `get_config().plugins.boot_orchestrator` is non-`None`. That test names no `boot_orchestrator` and the config sets none, so nothing is requested, nothing is matched, and no slot claim is half-applied. The same is true of every runtime-only caller the kernel work adds — the kernel's own doctrine forbids it from reading `HubSlot` at all, and Phase 2's `PipeFunc` op takes its executor as an explicit protocol-typed argument for exactly that reason.

**The remedy stays unbuilt, deliberately.** Both candidates above are real machinery — a `HubSlot.is_interpreter_slot` property plus a `honours_interpreter_slots` class attribute, or a widened `build_registrar` signature — bought for a path that *still* has no production caller. The three preconditions are unchanged: an external interpreter-side orchestrator installed, config or an argument naming it, and a runtime-only boot. A test that names no orchestrator satisfies none of the second two, so implementing the guard now would mean adding a mechanism no code can reach in order to close a hole no code can fall into. Reassess when a runtime-only boot is offered to real callers (a kernel-embedding host, an SDK entry point) — at that moment the second precondition becomes reachable for the first time and the slot-property remedy is the one to build.

## What exists today instead

The gate's comment in `runtime_boot.py` states the hole precisely and points here, so the next reader meets the reasoning rather than rediscovering the trap. Nothing silently claims to handle it.

## Resolution — the layer signal arrived, and the hole closed on its own

Everything above rests on one premise: *"every remedy needs a layer signal the runtime layer deliberately does not have."* That premise is now false. An external plugin declares its layer by the entry-point group it publishes under (`pipelex.plugins.kernel` / `pipelex.plugins.interpreter`), and discovery is scoped to the groups the caller asks for.

The consequence is that the hole closed without anyone building either candidate remedy. A kernel-only boot defaults `entry_point_groups` to `KERNEL_ENTRY_POINT_GROUPS`, so an interpreter-group orchestrator plugin is never queried, never loaded, and never registered — its name therefore fails the existing `registered_plugin_names` gate and raises `UnknownBootOrchestratorError`. Loud, at boot, with no new machinery. Note where the fix landed: not in the gate this document is about, but in *what discovery is allowed to see* one step upstream. The gate was never the defect; the unconditional discovery behind it was.

Both candidate remedies are therefore withdrawn rather than deferred:

- **`HubSlot.is_interpreter_slot` + `honours_interpreter_slots`** — half-built, under a different name and for a different job. `HubSlot.is_interpreter_layer` exists (the menu-tier cross-check reads it to decide what a kernel-group plugin may claim), but no `honours_interpreter_slots` class attribute was added and none is needed: a kernel-only boot cannot see an interpreter-group plugin's claims in the first place.
- **A widened `build_registrar` signature** — this is, in effect, what shipped, but scoped to *discovery* rather than to *policy*. `build_registrar` gained `entry_point_groups`, which says which groups to read; it did not gain a set of applicable slots, so the function stays a pure discover-and-register with no policy in it. The property that made the alternative unattractive is intact.

**One narrower gap survives, and it is a different question.** The group split constrains what a kernel-group plugin may *register*; it does not constrain what its module *imports*. A kernel-group plugin that imports the interpreter at module scope still drags it into a kernel-only boot. That is tracked as its own item — `wip/kernel/plugin-group-split-deferred-items.md`, D-2 — and is not what this document was about.
