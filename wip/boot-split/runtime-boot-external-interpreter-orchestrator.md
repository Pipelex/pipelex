# A runtime-only boot accepts an external interpreter-side orchestrator, then half-applies it

**Status:** deferred, deliberately. Found by Codex on PR #1073 (the boot split), verified real, not fixed there.

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

## What exists today instead

The gate's comment in `runtime_boot.py` states the hole precisely and points here, so the next reader meets the reasoning rather than rediscovering the trap. Nothing silently claims to handle it.
