# Phase 3 critical finding — the import-time CLI plugin-command harvest is an unguarded surface

> ✅ **RESOLVED BY REMOVAL (Option A).** This finding is moot: the CLI plugin-command harvest — and all four facets below — were **deleted**, not hardened. Temporal's `worker` / `setup-namespace` now ship as the standalone `pipelex-temporal` console script, so `pipelex --help` performs no config load, no entry-point scan, and no dynamic import; no plugin can shadow a core command or brick the recovery commands (`doctor` / `plugins` / `init`), because there is no longer any CLI-command contribution path. Decision + step-by-step: [`option-a-drop-cli-command-seam.md`](option-a-drop-cli-command-seam.md). Everything below is retained for historical context only.
>
> **Status:** ~~open, unsolved~~ **RESOLVED.** **Purpose (historical):** a cold-start problem statement. This doc explains *what was wrong and why it mattered* in enough depth to start a fresh session with no prior context. **It deliberately stopped short of proposing a fix** — the solution space was explored separately (and the chosen answer was to remove the surface). Surfaced by the xhigh `/code-review` over the Phase 3 checkpoint commit (`19e6ca66b` / `5f61db323`).
>
> Read the [TODOS cold-start primer](../../TODOS.md#cold-start-primer-read-this-first-if-youre-new-to-the-session) first for the plugin-seam vocabulary (registrar, `build_registrar`, `BUILTIN_PLUGINS`, slot-claims, D3) — this doc assumes it.

## TL;DR

Phase 3 (decision **D3**) harvests plugin-contributed CLI commands by running the full plugin-discovery pipeline (`build_registrar`) **at module-import time of `pipelex.cli._cli`**, on **every** `pipelex` invocation. That import path is now also doing config loading, external-plugin loading, and dynamic `import_module`/`getattr` — none of it guarded the way the boot path is, and one facet (command-name collision) has no guard *anywhere*. The net effect: a single broken/incompatible/colliding installed plugin, or an unreadable user config file, can make **every** `pipelex` command crash on import — including the very `--help` / `doctor` / `plugins` / `init` commands you would use to diagnose and disable the bad plugin. A fourth facet lets a plugin **silently shadow a core command** (`run`, `validate`, …) with no error or warning.

This is the single dominant correctness cluster of the Phase 3 review. It does not affect any in-tree-only install today (the built-ins contribute no CLI commands that collide, and a present-and-readable config parses), which is why the suite is green — but the surface is live for any external `pipelex.plugins` entry-point plugin, and that is exactly what Phase 5 ships.

## Where this lives

| Element | Location | What it does |
|---|---|---|
| The harvest entry point | `pipelex/cli/_cli.py` — `_register_discovered_cli_commands()` (~`:262`) and the module-level `_PLUGIN_COMMAND_NAMES = _register_discovered_cli_commands()` (~`:280`) | Runs at import of `_cli.py`. The `pipelex` console-script entry point is `pipelex.cli._cli:app`, so importing `app` runs this. |
| The config load for the harvest | `pipelex/cli/_cli.py` — `_config_for_cli_harvest()` (~`:246`) | Loads config without side effects; `except (TomlError, ValidationError)` → falls back to package defaults. |
| The discovery pipeline it calls | `pipelex/plugins/discovery.py` — `build_registrar()` (`:24`) | Iterates `BUILTIN_PLUGINS` then external `pipelex.plugins` entry points; **fail-loud** on every conflict (`BrokenPluginError`, `PluginApiVersionMismatchError`, `DuplicateInferenceBackendError`, `DuplicateOrchestratorError`, `HubSlotAlreadyClaimedError`, `CoreUnconditionalPluginDisabledError`). |
| The dynamic command resolve | `pipelex/cli/_cli.py` (~`:272-276`) | `module_path, _, attribute = import_path.partition(":")` → `getattr(importlib.import_module(module_path), attribute)` → `app.command(name=..., help=...)(command)`. |
| The registrar menu method with no guard | `pipelex/plugins/registrar.py` — `add_cli_command()` (`:135`) | Appends a `CliCommand` with **no** duplicate/collision check — unlike `add_orchestrator` (`:116`), `_claim` (`:145`), and the inference-backend add (`:110`), which all raise and name both contributors. |
| The command list that surfaces them | `pipelex/cli/_cli.py` — `PipelexCLI.list_commands` (~`:54`) returns `[*_CORE_COMMAND_ORDER, *_PLUGIN_COMMAND_NAMES]` | Plugin names are appended after core names. |

For contrast, the **boot** path runs the same `build_registrar` at `pipelex/pipelex.py` `setup()` (~`:390`) — but boot is allowed to fail loud; CLI startup is not.

## The contract this is supposed to honor

`_config_for_cli_harvest`'s own docstring states the intended invariant in plain words:

> "Runs on every `pipelex` invocation (including `--help` / `init`), so it must never create `~/.pipelex/` … and **must survive a broken user config** — a malformed override must not brick the very commands (`init`/`doctor`) that fix it. On any load or validation failure it falls back to the shipped package defaults, which always validate."

`build_registrar`'s docstring states the *other* intended invariant, which is in direct tension with the first:

> "is **fail-loud** on every conflict (duplicate backend/mode/slot, version mismatch, broken plugin)."

The Phase-1 boot-wiring note and the "Invariants that must survive every phase" section of TODOS both make **fail-loud** a deliberate, load-bearing property: *"installed but broken" must be loud, distinct from "not installed" (fine).* The problem is that Phase 3 moved that fail-loud pipeline onto the one path — CLI module import — where failing loud means failing *everything*, recovery commands included. The two invariants were never reconciled at this altitude.

## The problem, in four facets

All four are reachable through one surface: `_cli.py` import now performs config-load + plugin-discovery + dynamic import, none of it degraded for the "this must never brick `--help`" context.

### Facet 1 — `build_registrar()` is not wrapped; a broken external plugin bricks the whole CLI

`_register_discovered_cli_commands()` calls `build_registrar(config=...)` with no surrounding `try`/`except`. `build_registrar` is intentionally fail-loud: it raises on a broken entry point (`BrokenPluginError`), an API-version mismatch (`PluginApiVersionMismatchError`), and any duplicate `(family, sdk)` / duplicate mode / double-claimed slot across plugins. Pre-Phase-3, this pipeline ran **only inside `Pipelex.setup()`**, so a discovery failure could not touch `pipelex --help`.

**Failure scenario.** A user `pip install`s a broken / API-incompatible external pipelex plugin (or two plugins that collide on a mode/backend/slot). The exception now fires during `import pipelex.cli._cli`, before any command function runs. `pipelex --help`, `pipelex doctor`, `pipelex plugins`, and `pipelex init` all crash identically. The diagnostic commands (`doctor` / `plugins`) and the `plugins.disabled` denylist edit reachable via `init` — the documented recovery path for a broken installed plugin — are themselves unreachable. The CLI is fully bricked until the user manually `pip uninstall`s the offending dist by hand.

### Facet 2 — the config-load `except` is too narrow; an unreadable config file bricks the CLI

`_config_for_cli_harvest()` catches only `(TomlError, ValidationError)`. But the loader opens user TOML with `open(path, "rb")` (`pipelex/tools/misc/toml_utils.py:39`, `load_toml_from_path`), which catches only `tomli.TOMLDecodeError`. A file that is **present but unreadable** (wrong permissions, root-owned, on a flaky network mount) raises `PermissionError` / `OSError` from `open()` — neither is a `TomlError` nor a `ValidationError`, so it escapes the harvest's `except` uncaught and aborts the import.

**Failure scenario.** A user whose `~/.pipelex/pipelex.toml` or project `.pipelex/pipelex.toml` is present-but-unreadable gets every `pipelex` command — `--help`, `init`, `doctor` included — to abort at CLI module import with an uncaught `OSError`, instead of falling back to package defaults as the "bulletproof fallback" docstring promises. Again, the commands meant to fix config are unreachable.

> Note: the CHECKPOINT-3 review already added `test_harvest_config_falls_back_to_base_on_broken_user_config` (S1), but that test pins only the **malformed/parse** fallback (`TomlError`/`ValidationError`). The **unreadable/`OSError`** path is a distinct, still-uncovered gap — the existing test does not exercise it.

### Facet 3 — a malformed `import_path` produces an opaque crash, not a named one

`cli_command.import_path.partition(":")` on a path missing the `:attr` separator returns `("pkg.module", "", "")`, so the harvest calls `getattr(importlib.import_module("pkg.module"), "")`. There is no validation that `import_path` actually contains a `:`. `getattr(module, "")` raises an opaque `AttributeError` (or, on some objects, silently returns something unexpected) at `_cli.py` import time — again aborting the whole CLI, and without fail-loudly naming the offending plugin/command the way the rest of the registrar does.

**Failure scenario.** An external plugin registers `add_cli_command(import_path="pkg.module")` (forgetting the `:attr`). Every `pipelex` invocation crashes at import with an `AttributeError` that names neither the plugin nor the command, so the user cannot tell which installed plugin is at fault.

### Facet 4 — `add_cli_command` has no collision guard; a plugin can silently shadow a core command

This is the odd one out: it is not a crash, it is a **silent override**, and it is a correctness/trust problem rather than an availability one. Every *other* contribution type fail-loud on conflict and names both contributors: `add_orchestrator` (`:116`), `add_inference_backend` (`:110`), `_claim` (`:145`). `add_cli_command` (`:135`) performs **no** duplicate or core-name-collision detection at all. The harvest then calls `app.command(name="run", ...)(command)` at import time, registering a **second** `run` on the Typer app. Click resolves the last registration, so the plugin's callable silently wins; `list_commands` lists the name twice.

**Failure scenario.** A third-party (or buggy future in-tree) plugin advertises `add_cli_command(name="run", import_path="evil:run")`. On the next `pipelex run …`, the plugin's callable is dispatched **instead of** the core `run` command — no error, no warning — and the command appears twice in `pipelex --help`. Core execution is silently replaced by plugin code. The same applies to any core name (`validate`, `show`, `which`, `plugins`, …) and to two plugins colliding on the same custom name.

## Why this is the critical cluster (severity reasoning)

- **It defeats its own recovery path.** The defining property of all three crash facets is that the bricked commands *include the ones designed to recover from the brick* (`doctor`, `plugins`, `init` → `plugins.disabled`). A fail-loud error you cannot act on is worse than a fail-loud error you can.
- **It is live exactly where the project is heading.** It is latent for in-tree-only installs, but the entire point of the seam (Phase 5) is external `pipelex.plugins` dists. The surface becomes load-bearing precisely when externalization ships.
- **Facet 4 is a silent-override / trust hole**, which the "fail loud" invariant and the parallel guards on every sibling contribution type were specifically meant to prevent. CLI commands are the one unguarded menu, and the one that can shadow core behavior.
- **It is a regression in blast radius.** Pre-Phase-3, discovery failure was contained to boot (`Pipelex.setup()`); a user could still run `--help`/`doctor`. Phase 3 widened the blast radius to "every invocation."

## How to reproduce (write the failing tests first)

These sketch the minimal triggers; turn each into a red test before exploring fixes.

1. **Facet 1:** register a fake external `pipelex.plugins` entry point whose `register()` raises (or whose `targets_api` mismatches `PLUGIN_API_VERSION`), then invoke `pipelex --help`. Expect: today it raises at import; the desired contract is `--help` still works (core commands listed), with the breakage surfaced through `doctor`/`plugins`, not a hard crash.
2. **Facet 2:** create a `.pipelex/pipelex.toml`, `chmod 000` it (or simulate `open()` raising `PermissionError`), invoke `pipelex --help`. Expect: today it raises uncaught `PermissionError`; the contract wants a fallback to package defaults.
3. **Facet 3:** a fake plugin contributing `add_cli_command(name="x", help="…", import_path="some.module")` (no `:`). Invoke any `pipelex` command. Expect: today an opaque `AttributeError` at import; the contract wants a named, contextual error attributing the plugin/command (and ideally not bricking the rest of the CLI).
4. **Facet 4:** a fake plugin contributing `add_cli_command(name="run", help="…", import_path="…:something")`. Assert that `run` is registered twice / that core `run` is shadowed. Expect: today it silently overrides; the contract wants a fail-loud collision (parallel to `DuplicateOrchestratorError`).

The existing harvest tests to extend: `tests/.../test_plugin_cli_command_harvest.py` and `test_harvest_config_falls_back_to_base_on_broken_user_config` (the S1 test — covers Facet 2's *parse* path only).

## Solution space — open questions to explore (NOT answered here)

Listed only to map the decision space for the fresh session. Each is a genuine tension; none is pre-judged.

- **Altitude / timing.** Should the harvest run at import time at all, or be deferred to the point where the command list is actually needed (the `PipelexCLI` group already subclasses `TyperGroup` and overrides `list_commands`/`get_command`)? What does `--help` *need* vs. what does dispatching a plugin command *need*? Does shell tab-completion change the answer?
- **Reconciling the two invariants.** "Fail loud on a broken plugin" (boot) vs. "never brick the recovery commands" (CLI startup) are both deliberate. Where is the seam between them? Is the answer "fail loud, but only when the user actually invokes the broken plugin's command / a boot-requiring command, and degrade-with-a-visible-notice for `--help`/`doctor`/`init`"? What does "visible notice" mean for an LLM-facing vs. human-facing surface (see the workspace "format follows consumer" rule)?
- **Degrade vs. abort.** If discovery fails during the harvest, what is the right degraded state — core commands only, with the failure reported through `doctor`/`plugins`? Or is partial discovery (the built-ins succeeded, one external failed) meaningful?
- **Collision policy (Facet 4).** Should `add_cli_command` route through a `_claim`-style guard that refuses to shadow a core command name and refuses two plugins claiming the same name? Is "core command names are reserved" a hard rule? Is there *any* legitimate reason a plugin should override a core command? How does this interact with `_CORE_COMMAND_ORDER` being the source of truth for core names?
- **`import_path` validation.** Where should the `:`-presence (and attribute-exists) validation live — at `add_cli_command` registration time (fail-loud, names the plugin), or at harvest/dispatch time? Should `CliCommand` validate its own `import_path` shape as a pydantic model?
- **Single vs. double discovery.** Boot re-runs `build_registrar` (`pipelex.py:~390`) after the harvest already ran it, discarding the harvest result. Any fix that changes *when/whether* the harvest runs interacts with this redundancy (tracked separately in [phase-3-review-deferred.md](phase-3-review-deferred.md) under "double discovery / import-time cost"). Decide whether the two are solved together.

## Pointers

- Code: `pipelex/cli/_cli.py` (harvest), `pipelex/plugins/discovery.py` (`build_registrar`), `pipelex/plugins/registrar.py` (`add_cli_command` + the guarded siblings), `pipelex/tools/misc/toml_utils.py:39` (the `open()`).
- Decision: **D3** in [TODOS](../../TODOS.md) ("plugin CLI commands harvested by running the pure `build_registrar` at CLI-build; same fn runs again at boot").
- Invariants: TODOS "Invariants that must survive every phase" — *fail loud* on a broken plugin; "installed but broken" ≠ "not installed".
- Sibling deferred items (medium/low): [phase-3-review-deferred.md](phase-3-review-deferred.md).
