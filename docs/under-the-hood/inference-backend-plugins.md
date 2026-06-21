---
title: "Inference Backend Plugins"
description: "How Pipelex discovers inference backends through the plugin seam, the Inference SPI a backend plugin compiles against, and how to author one."
---

# Inference Backend Plugins

Every model call in Pipelex — an LLM completion, an image generation, a document extraction, a web search — is served by an **inference worker**. Which worker handles a given model is decided entirely by data: a model's `sdk` field selects a backend, and a **backend plugin** is what teaches Pipelex how to build the worker for that `sdk`.

Core names no backend by import or by string. The built-in drivers (OpenAI, Gateway, Anthropic, Mistral, Bedrock, Google, FAL, HuggingFace, Docling, …) are plugins too — they ride the exact same seam an out-of-tree plugin would. This page documents that seam, the **Inference SPI** a plugin compiles against, and how to write one.

---

## The seam in one view

```
boot (Pipelex.setup)
  └─ build_registrar(config)            # pure, import-light
       ├─ for each plugin in BUILTIN_PLUGINS
       └─ for each installed "pipelex.plugins" entry point
            └─ plugin.register(registrar)        # side-effect-free
                 └─ registrar.add_inference_backend(family=…, sdk=…, make_worker=…)
  └─ InferenceBackendRegistry(registrar.inference_backends)   # stored on the hub

run time (e.g. LLMWorkerFactory.make_llm_worker)
  └─ model_handle = ModelHandle.make_for_inference_model(...)
  └─ make_worker = get_inference_backend_registry().lookup(family=LLM, sdk=model_handle.sdk)
  └─ worker = make_worker(inference_model=…, backend=…, sdk_clients=…, reporting_delegate=…)
```

The worker factories (`LLMWorkerFactory`, `ImgGenWorkerFactory`, `ExtractWorkerFactory`, `SearchWorkerFactory`) hold **no** `match` over SDK strings. They build a `ModelHandle`, resolve the `InferenceBackend` config, look up the backend's `make_worker` by `(family, sdk)`, and call it. A lookup miss raises a friendly `NotImplementedError` ("… Is its plugin installed?").

---

## The contract: `PipelexPlugin`

A plugin is any object satisfying the `@runtime_checkable` `PipelexPlugin` protocol:

```python
class PipelexPlugin(Protocol):
    name: str            # unique, lowercase identifier (e.g. "openai")
    targets_api: int     # must equal PLUGIN_API_VERSION
    def register(self, registrar: PluginRegistrar) -> None: ...
```

`register` is the **only** method core calls, and it is **side-effect-free**: it may call the registrar's menu methods and nothing else — no hub access, no I/O, no client/SDK construction. This is what makes `build_registrar` safe to run more than once (it runs at boot, and again at CLI-build to harvest plugin-contributed commands).

`targets_api` is checked against `PLUGIN_API_VERSION`. A mismatch fails loud with `PluginApiVersionMismatchError` — a single coarse integer gate, not semver-range matching.

---

## Registering an inference backend

A backend plugin's `register` calls one menu method per `(family, sdk)` it serves:

```python
registrar.add_inference_backend(
    family=InferenceFamily.LLM,         # LLM | IMG_GEN | EXTRACT | SEARCH
    sdk="acme",                          # the model's `sdk` string
    make_worker=_make_acme_worker,       # a MakeWorkerFn (a plain callable)
)
```

A registry key is `(family, sdk)`. The same `sdk` string may appear in two families (e.g. `google` serves both `LLM` and `IMG_GEN`); they are distinct keys. A duplicate `(family, sdk)` fails loud with `DuplicateInferenceBackendError` naming **both** contributing plugins.

One plugin may register across several families from a single `register` — the built-in `gateway` plugin serves all four, `mistral` serves `LLM` + `EXTRACT`, `linkup` serves `EXTRACT` + `SEARCH`. This is the cross-family-vendor coordination point: one plugin, many backends.

---

## `MakeWorkerFn` — the locked call shape

A backend is a typed **callable**, not a one-method object. Its signature is the contract:

```python
def _make_acme_worker(
    *,
    inference_model: InferenceModelSpec,
    backend: InferenceBackend,
    sdk_clients: SdkClientRegistry,
    reporting_delegate: ReportingProtocol | None,
) -> InferenceWorkerAbstract:
    ...
```

The factory always passes all four keyword arguments. A stateless backend simply ignores the ones it doesn't need (`# noqa: ARG001` on the unused parameter — see the built-in `pypdfium2` and `azure_rest` plugins).

Two invariants shape what goes *inside* the closure:

- **Import-light.** The plugin module must import no backend SDK at module load. Do the SDK import **inside** the closure (`# noqa: PLC0415`), so merely discovering the plugin never pulls a heavy/optional dependency. Booting Pipelex with the built-ins registered imports none of `anthropic`, `mistralai`, `google.genai`, `boto3`, `fal_client`, `huggingface_hub`, `docling`, `linkup`, … — enforced by a subprocess import-blocker guard.
- **Fail at use, not at boot.** Guard an optional dependency with `require_sdk(...)` *inside* the closure. A missing extra then raises `MissingDependencyError` (naming the package and the `pipelex[<extra>]` install hint) only when the backend is actually used.

Client memoization goes through `sdk_clients.get_or_create(handle=…, build=lambda: …)` — the registry caches one SDK client per `ModelHandle`, so repeated worker construction reuses the connection.

---

## Listing models — an optional capability

Alongside its worker factory, a backend plugin **may** register a model lister — the callable behind `pipelex show models <backend>`. It is optional: a backend that cannot enumerate its models simply never calls `add_model_lister`, and the listing command reports that SDK as unsupported-for-listing. The contract grows by one *optional* method, so progressive disclosure is preserved.

```python
registrar.add_model_lister(sdk="acme", lister=_list_acme_models)
```

A `ListModelsFn` mirrors `MakeWorkerFn` — import-light to reference, lazy inside. It is always `async` (the listing loop awaits it) and is keyed by `sdk` alone (listing is per-SDK, not per-`(family, sdk)`):

```python
async def _list_acme_models(
    *,
    sdk: str,
    backend_name: str,
    backend: InferenceBackend,
    flat: bool,
    any_listed: bool,
) -> None:
    from my_pkg.acme_list import list_acme_models  # noqa: PLC0415

    await list_acme_models(sdk=sdk, backend_name=backend_name, backend=backend, flat=flat, any_listed=any_listed)
```

The same import-light / fail-at-use rules apply: a missing optional extra must raise `MissingDependencyError` only when the backend is actually listed — use the `require_sdk(...)` helper, or an equivalent `find_spec` guard inside the function the lister delegates to (the built-in listers do the latter, reusing the guard already in their `list_*_models` functions). If a registered lister's client variant cannot enumerate models at runtime (e.g. a Bedrock-backed Anthropic client), raise `ModelListingUnsupportedError(sdk=…)`: the loop treats that as the same soft "unsupported for listing" outcome as a missing lister — never a hard failure. A duplicate `sdk` lister fails loud with `DuplicateModelListerError` naming both plugins.

---

## Authoring a backend plugin (minimal example)

A complete LLM backend plugin for a hypothetical `acme` SDK:

```python
# acme_plugin.py
from pipelex.cogt.inference.inference_worker_abstract import InferenceWorkerAbstract
from pipelex.cogt.model_backends.backend import InferenceBackend
from pipelex.cogt.model_backends.model_spec import InferenceModelSpec
from pipelex.plugins.contract import PLUGIN_API_VERSION
from pipelex.plugins.inference_backend_registry import InferenceFamily, require_sdk
from pipelex.plugins.model_handle import ModelHandle
from pipelex.plugins.registrar import PluginRegistrar
from pipelex.plugins.sdk_client_registry import SdkClientRegistry
from pipelex.reporting.reporting_protocol import ReportingProtocol

_ACME_MISSING_MSG = "The acme SDK is required in order to use Acme models."


def _make_acme_worker(
    *,
    inference_model: InferenceModelSpec,
    backend: InferenceBackend,
    sdk_clients: SdkClientRegistry,
    reporting_delegate: ReportingProtocol | None,
) -> InferenceWorkerAbstract:
    require_sdk(spec="acme", extra="acme", msg=_ACME_MISSING_MSG)

    from acme import AcmeClient  # noqa: PLC0415

    from my_pkg.acme_llm_worker import AcmeLLMWorker  # noqa: PLC0415

    model_handle = ModelHandle.make_for_inference_model(inference_model=inference_model)
    sdk_instance = sdk_clients.get_or_create(
        handle=model_handle,
        build=lambda: AcmeClient(api_key=backend.api_key),
    )
    return AcmeLLMWorker(
        sdk_instance=sdk_instance,
        inference_model=inference_model,
        reporting_delegate=reporting_delegate,
    )


class AcmePlugin:
    name = "acme"
    targets_api = PLUGIN_API_VERSION

    def register(self, registrar: PluginRegistrar) -> None:
        registrar.add_inference_backend(family=InferenceFamily.LLM, sdk="acme", make_worker=_make_acme_worker)
```

### Shipping it as an out-of-tree plugin

Declare an entry point in the `pipelex.plugins` group; discovery finds it automatically once the distribution is installed (no central enable-list — *presence* is the source of truth):

```toml
# pyproject.toml of your plugin package
[project.entry-points."pipelex.plugins"]
acme = "my_pkg.acme_plugin:AcmePlugin"
```

The entry point may resolve to a plugin instance or a zero-argument factory. A broken entry point is isolated and reported as `BrokenPluginError`, never a silent skip.

### Disabling a discovered plugin

`build_registrar` skips (and logs) any plugin whose `name` appears in the core-owned `plugins.disabled` denylist:

```toml
# .pipelex/pipelex.toml
[plugins]
disabled = ["acme"]
```

For external entry points the denylist is matched against the **entry-point name** *before* the plugin is loaded, so a broken or dependency-missing installed plugin can still be disabled to recover startup (it would otherwise raise `BrokenPluginError` at load). A working external plugin that sets a `name` different from its entry-point name is denylistable by **either** name.

Disabling a core-unconditional plugin (`openai`) is a configuration error, not a no-op — it raises `CoreUnconditionalPluginDisabledError`. There is intentionally **no** allowlist: a plugin's presence (built-in or installed entry point) is what enables it.

Use `pipelex plugins list` to see every discovered plugin, what each contributed, and its denylist state.

---

## The Inference SPI

What an out-of-tree backend plugin imports *is* the contract. The published surface:

| Symbol | Module | Role |
|--------|--------|------|
| `PipelexPlugin`, `PLUGIN_API_VERSION` | `pipelex.plugins.contract` | the plugin protocol + version gate |
| `PluginRegistrar` | `pipelex.plugins.registrar` | the accumulator `register` writes into |
| `InferenceFamily`, `MakeWorkerFn`, `require_sdk` | `pipelex.plugins.inference_backend_registry` | family enum, callable type, dependency guard |
| `ListModelsFn` | `pipelex.plugins.model_lister_registry` | the optional model-listing callable type |
| `ModelListingUnsupportedError` | `pipelex.cogt.exceptions` | soft signal a lister raises when its client variant cannot list |
| `ModelHandle` | `pipelex.plugins.model_handle` | the backend selector derived from a model spec |
| `SdkClientRegistry` | `pipelex.plugins.sdk_client_registry` | per-handle client memoization |
| `InferenceModelSpec` | `pipelex.cogt.model_backends.model_spec` | the resolved model record |
| `InferenceBackend` | `pipelex.cogt.model_backends.backend` | the backend config record (api key, extras) |
| `InferenceWorkerAbstract` and the `{LLM,ImgGen,Extract,Search}WorkerAbstract` subclasses | `pipelex.cogt.…` | the worker contracts a plugin returns |
| `MissingDependencyError` | `pipelex.exceptions` | raised by `require_sdk` |

The SPI is a documented, versioned **module/symbol list** gated by `PLUGIN_API_VERSION` — not an `__init__.py` re-export shim (the repo bans re-exports; import by full path). Anything a plugin needs to import outside this surface is a design gap to resolve, not an accident to live with.

---

## Fail-loud guarantees

| Condition | Error |
|-----------|-------|
| `targets_api` ≠ `PLUGIN_API_VERSION` | `PluginApiVersionMismatchError` |
| duplicate `(family, sdk)` | `DuplicateInferenceBackendError` (names both plugins) |
| duplicate `sdk` model lister | `DuplicateModelListerError` (names both plugins) |
| `name` in `plugins.disabled` but core-unconditional | `CoreUnconditionalPluginDisabledError` |
| entry point raises while loading/registering | `BrokenPluginError` |
| lookup for an unregistered `(family, sdk)` | `InferenceBackendNotFoundError` ("… Is its plugin installed and enabled?") |
| optional SDK missing at use | `MissingDependencyError` (package + `pipelex[<extra>]` hint) |

---

## Related

- [Pipe Routing & Execution](pipe-routing-and-execution.md) — where worker construction sits in the run path
- [Error Model](error-model.md) — how these errors render and dereference
- [Architecture Overview](architecture-overview.md)
