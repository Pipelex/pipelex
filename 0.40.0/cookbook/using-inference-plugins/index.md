# Example: Using Inference Plugins

This example shows how Pipelex discovers **inference-backend plugins**: installable Python packages that teach Pipelex how to serve models for a given `sdk` token. The cookbook ships a complete, minimal plugin — a deterministic "LLM" that always answers with the same haiku — so the whole flow runs anywhere with no API key and no network.

## Get the code

[![GitHub](https://img.shields.io/badge/View_on_GitHub-5a0dad?logo=github&logoColor=white&style=flat)](https://github.com/Pipelex/pipelex-cookbook/tree/main/examples/c_advanced/using_inference_plugins)

## What it demonstrates

- What a plugin **is**: a package exposing a `pipelex.plugins` entry point that resolves to a `PipelexPlugin` — an object with a `name`, a `targets_api` version, and a side-effect-free `register(registrar)` method
- Registration through the registrar: `register` contributes an inference backend for `(family="llm", sdk="hello")`, plus an optional model lister
- Discovery by presence: installing the package is the whole integration — no enable-list, no config switch
- The model-config side: how a model handle in a `.mthds` file resolves to the plugin's worker through `.pipelex/inference/`
- The failure mode when the plugin is missing — a loud, friendly error, not a silent fallback

## The plugin package

The plugin lives inside the example directory as its own installable package:

```
examples/c_advanced/using_inference_plugins/
├── hello_plugin.mthds                  # the method that uses the plugin-served model
└── hello_inference_plugin/             # the plugin package
    ├── pyproject.toml                  # declares the `pipelex.plugins` entry point
    └── hello_inference_plugin/
        ├── hello_plugin.py             # HelloInferencePlugin: name, targets_api, register()
        ├── hello_llm_worker.py         # HelloLLMWorker(LLMWorkerAbstract): the actual "model"
        └── hello_list.py               # optional lister behind `pipelex show models hello`
```

The entry point in `pyproject.toml` is the single line that wires everything:

```toml
[project.entry-points."pipelex.plugins"]
hello_inference = "hello_inference_plugin.hello_plugin:HelloInferencePlugin"
```

The plugin class registers what it serves — and nothing else happens at registration time (no I/O, no client construction; heavy work belongs inside the worker factory):

```python
class HelloInferencePlugin:
    name = "hello_inference"
    targets_api = PLUGIN_API_VERSION

    def register(self, registrar: PluginRegistrar) -> None:
        registrar.add_inference_backend(family=InferenceFamily.LLM, sdk="hello", make_worker=_make_hello_llm_worker)
        registrar.add_model_lister(sdk="hello", lister=_list_hello_models)
```

The worker subclasses `LLMWorkerAbstract` and only implements the generation itself — the base class owns the job lifecycle, capability checks, usage reporting, and telemetry. Here it deterministically returns a haiku; a real plugin would call a remote model at this exact spot.

## The model-config side

Model configuration lives in the project's `.pipelex/inference/` directory (not in `.pipelex/pipelex.toml`). Three pieces connect a `.mthds` model handle to the plugin:

- `backends.toml` declares the `[hello]` backend (enabled, no API key)
- `backends/hello.toml` declares model `hello-1` with `sdk = "hello"` — the token that selects the plugin's worker factory
- `routing_profiles.toml` routes `hello-1` to the `hello` backend via an `optional_routes` entry, which only applies while the target backend is enabled

## The Method: `hello_plugin.mthds`

```toml
domain      = "hello_plugin"
description = "Using a model served by an inference-backend plugin"
main_pipe   = "hello_plugin"

[pipe]
[pipe.hello_plugin]
type = "PipeLLM"
description = "Write text about Hello World."
output = "Text"
model = { model = "hello-1", temperature = 0.5 }
prompt = """
Write a haiku about Hello World.
"""
```

The only difference from the standard [Hello World](./hello-world.md) example is the `model` field: `hello-1` is served by the plugin instead of a gateway backend.

## How to run

1. Install the plugin package (this is the step being demonstrated):

    ```bash
    uv pip install -e examples/c_advanced/using_inference_plugins/hello_inference_plugin
    ```

2. Check that Pipelex discovered it:

    ```bash
    pipelex plugins list        # hello_inference | external | registered
    pipelex show models hello   # lists hello-1
    ```

3. Run the method — no credentials needed:

    ```bash
    pipelex run bundle examples/c_advanced/using_inference_plugins/hello_plugin.mthds
    ```

    The output is the plugin's deterministic haiku.

## The failure mode

Uninstall the package and run again:

```bash
uv pip uninstall hello-inference-plugin
pipelex run bundle examples/c_advanced/using_inference_plugins/hello_plugin.mthds
```

Pipelex fails loud at worker-creation time: `No inference backend registered for sdk 'hello' in the llm family. Is its plugin installed and enabled?` — the model config still resolves; only the worker factory is missing. A dry run still passes without the plugin, because worker creation is lazy.

## Related Documentation

- [Inference Backend Plugins](../under-the-hood/inference-backend-plugins.md) - The plugin seam and the Inference SPI, including how to wrap a real SDK (dependency guards, client memoization)
- [Configuration System](../features/configuration.md) - How `.pipelex/` project configuration works
- [Pipelex Gateway & Model Access](../features/gateway.md) - Default model access through the gateway
