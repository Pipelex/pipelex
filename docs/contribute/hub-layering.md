---
title: "Hub Layering"
description: "The service_hub / method_hub boundary — what lives in each half, the one-arrow rule, and how it is enforced."
---

# Hub layering convention

Pipelex resolves its cross-cutting dependencies through a *hub*: a singleton container plus a set of module-level accessor functions, so a component can reach the config, a worker, or the pipe library without importing the module that owns it. There are **two** hubs, and which one a symbol lives on is an architectural boundary, not a filing preference. This document is the canonical specification of that boundary.

## The one rule

> `method_hub` may import `service_hub`. **`service_hub` must never import `method_hub`.**

That single arrow is the whole architecture. Everything below is a consequence of it.

Only the *forbidden* direction is load-bearing. The permitted one is currently unused: the one low-layer thing `method_hub` needs is the class-registry scoping slot, which lives below *both* hubs (see [The class-registry exception](#the-class-registry-exception)). So today, importing either hub loads the other in neither direction — which is stronger than the rule requires, not a violation of it.

There is deliberately **no** `pipelex.hub`. It was deleted rather than kept as an alias for either half, so a stale import fails loudly at import time instead of silently resolving to the wrong layer.

## The two halves

### `pipelex/service_hub.py` — process-scoped infrastructure

`ServiceHub` holds what is configured once at boot and never varies per method:

| group | symbols |
| --- | --- |
| container | `ServiceHub`, `get_service_hub`, `set_service_hub` |
| config | `get_required_config`, `get_optional_config` |
| console | `get_console` |
| secrets | `get_secrets_provider`, `get_secret` |
| system registries | `get_class_registry`, `get_func_registry` |
| storage | `get_storage_provider` |
| telemetry | `get_telemetry_manager`, `get_otel_tracer` |
| models | `get_models_manager`, `get_model_deck`, `get_sdk_client_manager` |
| inference | `get_inference_manager`, `get_llm_worker`, `get_img_gen_worker`, `get_extract_worker` |
| content generation | `get_content_generator`, `scoped_content_generator` |
| reporting | `get_report_delegate`, `is_in_isolated_execution` |
| run mode | `is_dry_run_forced` |
| tracing | `scoped_event_log`, `get_event_log_override` |
| plugin registries | `get_inference_backend_registry`, `get_model_lister_registry`, `get_orchestrator_registry`, `get_bundle_validator_registry`, `get_storage_provider_registry`, `get_secrets_provider_registry` |

### `pipelex/method_hub.py` — library-scoped method machinery

`MethodHub` holds what belongs to the *loaded method*:

| group | symbols |
| --- | --- |
| container | `MethodHub`, `get_method_hub`, `set_method_hub` |
| library manager | `get_library_manager`, `get_library` |
| library lookups | `get_concept_library`, `get_required_concept`, `get_native_concept`, `get_required_domain`, `get_optional_domain`, `get_pipe_library`, `get_pipes`, `get_required_pipe`, `get_optional_pipe`, `get_pipe_source` |
| current-library contextvar | `set_current_library`, `get_current_library`, `get_current_library_id_or_none`, `clear_current_library`, `scoped_current_library` |
| library dirs | `resolve_library_dirs`, `get_default_library_dirs` |
| pipe router | `get_pipe_router`, `set_pipe_router`, `teardown_current_pipe_router`, `scoped_pipe_router` |
| run | `get_pipe_run`, `get_pipeline_manager`, `get_pipeline` |
| pipe func | `get_pipe_func_executor`, `scoped_pipe_func_executor`, `get_pipe_func_executor_registry` |

Setters follow their getters onto the matching container.

### Which half does a new symbol belong to?

Ask **what its lifecycle is**, not what package it happens to be typed by:

- Configured once at boot from config + plugin registration, identical for every method the process runs → `service_hub`.
- Tied to a loaded method's libraries, or varying with the current library → `method_hub`.

Placement is decided by *kind*, not by who currently imports it. Several accessors have no in-tree importer (`get_bundle_validator_registry`, `get_orchestrator_registry`, `get_default_library_dirs`, …) — they are live plugin contract and are reached through the container. Do not relocate or delete one because a grep looks empty.

`get_pipe_func_executor_registry` is the one placement worth flagging: it is a plugin registry by kind (which would put it low) but its protocol lives in `pipe_operators/func/` (which puts it high). It is **high**. See [Known inversions](#known-inversions) for the underlying wart.

## Why the boundary exists

`service_hub` must not name anything from `libraries`, `pipe_operators`, `pipe_controllers`, `codegen`, `builder`, `core.bundles`, `core.concepts`, or `core.pipes` at module level. Those module-level imports exist only to type the getters, but they are what made a single hub drag the entire method interpreter into every consumer that just wanted `get_console()`.

The property that matters is measurable: **importing the inference layer must not load the interpreter.** Verify it from the repo root on a synced venv:

```bash
.venv/bin/python - <<'PY'
import sys
from pathlib import Path

import pipelex.cogt.content_generation.content_generator  # noqa: F401

INTERPRETER = {"libraries", "pipe_operators", "pipe_controllers", "codegen", "builder"}
loaded = {name: mod for name, mod in sys.modules.items() if name.startswith("pipelex.")}
interpreter = sorted(n for n in loaded if n.split(".")[1] in INTERPRETER)
sloc = 0
for mod in loaded.values():
    file = getattr(mod, "__file__", None)
    if file:
        sloc += sum(1 for line in Path(file).read_text(encoding="utf-8").splitlines() if line.strip() and not line.strip().startswith("#"))
print(f"pipelex modules: {len(loaded)} | sloc: {sloc} | interpreter modules: {len(interpreter)}")
print("offenders:", interpreter)
PY
```

`interpreter modules` must print **0**. When it does not, the `offenders` list names the modules that leaked, and the shortest import path to one of them is what to fix. Swap the imported module to measure any other entry point.

## The class-registry exception

`get_class_registry` is the one low-layer accessor that is *not* implemented in `service_hub`. Its implementation lives in `pipelex/system/registries/class_registry_access.py`, and `pipelex.service_hub.get_class_registry` delegates to it.

The reason is a genuine cycle. `core.concepts.concept` needs the active class registry, and it sits **inside** `service_hub`'s own import closure:

```
service_hub → cogt.llm.llm_worker_abstract → system.telemetry.otel_factory
            → core.pipes.pipe_output → core.stuffs.stuff → core.concepts.concept
```

so `concept.py` cannot import `service_hub` at module level. Hosting the accessor in a module that imports nothing from `pipelex` is what lets `core/concepts/` use a plain top-level import — replacing three identical `importlib.import_module("pipelex.hub")` shims that were invisible to every import lint and to pyright's module graph.

**Use `pipelex.service_hub.get_class_registry` everywhere.** Import the leaf module directly only from inside `service_hub`'s import closure, where the public accessor is unreachable.

### Library scoping crosses downward, at install time

A run may pin a per-library `ClassRegistry` rather than the process-global Kajson one. Knowing *which* library is current is method-layer knowledge, so the low layer holds only a slot: `class_registry_scoping`, defaulting to a resolver that returns `None`. `set_method_hub` installs the real resolver, which means scoping is live exactly when a `MethodHub` exists — an invariant a caller cannot forget to wire. `Pipelex.teardown` calls `class_registry_scoping.reset()` so a torn-down library manager is never reachable through a still-pinned library id.

This is the same shape as `HubSlot.ISOLATED_EXECUTION_PROBE`: a defaulted callable a higher layer replaces at boot, never an unset attribute. A process that only ever builds a `ServiceHub` (the doctor path, most unit tests) therefore degrades to the process-global registry instead of raising.

## Enforcement

Today the boundary is enforced by three things:

1. **The import graph itself.** `pipelex.hub` no longer exists, so a stale import is an `ImportError`, not a silent wrong-layer resolution. And because `service_hub` sits inside a cycle with `core.concepts`, a module-level `method_hub` import added to the low layer will typically fail at import time rather than merely degrade.
2. **The measurement above**, which is the actual property (0 interpreter modules) rather than a proxy for it.
3. **`tests/unit/pipelex/test_hub_lifecycle.py`**, which pins that a boot installs both singletons and that the reset really releases the scoping a `MethodHub` installed.

A mechanical AST guard (`pipelex-dev check-hub-layering`) that forbids `pipelex.method_hub` imports — including the string-literal `importlib.import_module` form — from a declared low layer (`pipelex/tools/**`, `pipelex/system/**`, `pipelex/cogt/**`, `pipelex/plugins/**`, `pipelex/reporting/**`) is the next step; all five packages are compliant today, so it will hard-block from day one with an empty exception list. Until it lands, treat the rule as reviewed by hand and verified by the measurement.

## Known inversions

Named so this document stays honest. None of these import a hub, so a hub-import guard would not flag them — but they mean "`plugins` is a low layer" is not yet unconditionally true.

- `plugins/pipe_func/pipe_func_plugin.py` and `plugins/pipe_func_executor_registry.py` are typed by protocols from `pipe_operators/`; `plugins/direct/direct_plugin.py` imports from `pipeline/`. `pipe_func_executor_registry` defers its import under `TYPE_CHECKING` precisely because `pipelex.config` imports it and the inference layer imports `pipelex.config` — a module-level import there would drag the interpreter back into every inference closure. The placement itself is unfixed.
- `pipelex/core/**` is not yet in the low layer. Five `core/` modules reach for `get_concept_library` / `get_native_concept` / `get_required_concept` / `get_required_pipe`; converting them to take resolved concepts and pipes as arguments is design work, not a mechanical move. The low layer widens to include `core/` only when that lands.
- Broader measured inversions, out of scope for the hub boundary: `tools → cogt`, `cogt → core`, `system → cogt`, `plugins → runtime_bridge`, and `cogt/model_backends/model_lists.py` importing `pipelex.cli.exceptions.PipelexCLIError`.

## For consumers outside this repo

`pipelex.hub` is gone; there is no shim. Every external importer must choose a half. The symbols that crossed the repo boundary are split as follows — low ones now come from `pipelex.service_hub`, high ones from `pipelex.method_hub`, per the tables above. `get_pipelex_hub` splits into `get_service_hub` and `get_method_hub`, so each call site must pick the container it actually meant.
