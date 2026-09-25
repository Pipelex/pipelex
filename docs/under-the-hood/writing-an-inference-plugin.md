---
title: "Writing an Inference Plugin"
description: "Write, install and run a minimal Pipelex inference-backend plugin: a deterministic model that needs no API key, served to a method through the plugin seam."
---

# Writing an Inference Plugin

An inference plugin is an installable Python package that teaches the Pipelex runtime to serve models for a given `sdk` token. This page builds a complete one, `hello-inference-plugin`, whose "LLM" always answers with the same haiku, so every step runs on your own machine without an API key or a network call. It then declares a model served by the plugin, runs a method against it, and shows what happens when the plugin is missing.

[Inference Backend Plugins](inference-backend-plugins.md) is the reference for the seam this page uses: the plugin contract, the Inference SPI a plugin imports, and the errors discovery raises. This page walks through that seam once, end to end.

!!! note "A plugin extends the runtime on your machine"
    An inference plugin is loaded by the Pipelex runtime you install and run yourself, as in [Run It Yourself](../get-started/run-it-yourself.md). A method you run on the hosted Pipelex API is served by the hosted plane's own backends and cannot use a plugin installed on your machine.

## What you will build

The plugin is its own package:

```
hello-inference-plugin/
├── pyproject.toml                 # declares the pipelex.plugins.kernel entry point
└── hello_inference_plugin/
    ├── __init__.py                # empty
    ├── hello_plugin.py            # HelloInferencePlugin: name, targets_api and register()
    ├── hello_llm_worker.py        # HelloLLMWorker: the model itself
    └── hello_list.py              # an optional lister behind `pipelex show models hello`
```

Two more pieces connect a method to it: a model declared with `sdk = "hello"` in your inference configuration, and a method that names that model.

## Step 1: Declare the entry point

The package's `pyproject.toml` publishes the plugin under the `pipelex.plugins.kernel` entry-point group:

```toml
[project]
name = "hello-inference-plugin"
version = "0.1.0"
description = "Minimal Pipelex inference-backend plugin: a deterministic 'hello' LLM that needs no API key"
requires-python = ">=3.11"
dependencies = ["pipelex"]

# The whole integration: once this distribution is installed, Pipelex discovers the plugin
# through the `pipelex.plugins.kernel` entry-point group. An inference backend builds a worker,
# never a pipe, so it is a kernel-layer plugin and publishes under the kernel group.
[project.entry-points."pipelex.plugins.kernel"]
hello_inference = "hello_inference_plugin.hello_plugin:HelloInferencePlugin"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["hello_inference_plugin"]
```

That entry point is the whole integration. Pipelex has no list of enabled plugins to edit: an installed plugin is discovered at startup, and its presence is what enables it. The entry point may name the plugin class, as here, or an instance of it.

The group is not cosmetic. It declares the plugin's layer, and an inference backend belongs to the kernel layer because it builds a worker and never a pipe. A plugin published under `pipelex.plugins.interpreter` instead would be invisible to a kernel-only boot, and a plugin still published under the retired `pipelex.plugins` group stops Pipelex from starting, with an error naming the group to move to.

## Step 2: Register what the plugin serves

`hello_plugin.py` holds the plugin class and the two callables it registers:

```python
from pipelex.cogt.inference.inference_worker_abstract import InferenceWorkerAbstract
from pipelex.cogt.model_backends.backend import InferenceBackend
from pipelex.cogt.model_backends.model_spec import InferenceModelSpec
from pipelex.plugins.contract import PLUGIN_API_VERSION
from pipelex.plugins.inference_backend_registry import InferenceFamily
from pipelex.plugins.registrar import PluginRegistrar
from pipelex.plugins.sdk_client_registry import SdkClientRegistry
from pipelex.reporting.reporting_protocol import ReportingProtocol


def _make_hello_llm_worker(
    *,
    inference_model: InferenceModelSpec,
    backend: InferenceBackend,
    sdk_clients: SdkClientRegistry,
    reporting_delegate: ReportingProtocol | None,
) -> InferenceWorkerAbstract:
    # Heavy work belongs here, inside the closure, never at module import time.
    # A real plugin would call `require_sdk(...)`, then build and memoize its SDK client
    # with `sdk_clients.get_or_create(...)`. The hello worker needs neither.
    from hello_inference_plugin.hello_llm_worker import HelloLLMWorker

    return HelloLLMWorker(inference_model=inference_model, reporting_delegate=reporting_delegate)


async def _list_hello_models(
    *,
    sdk: str,
    backend_name: str,
    backend: InferenceBackend,
    flat: bool,
    any_listed: bool,
) -> None:
    from hello_inference_plugin.hello_list import list_hello_models

    list_hello_models(sdk=sdk, backend_name=backend_name, backend=backend, flat=flat, any_listed=any_listed)


class HelloInferencePlugin:
    """An out-of-tree inference-backend plugin serving the `hello` sdk token.

    `register` is the only method Pipelex calls, and it stays free of side effects:
    it calls the registrar's menu methods and nothing else.
    """

    name = "hello_inference"
    targets_api = PLUGIN_API_VERSION

    def register(self, registrar: PluginRegistrar) -> None:
        registrar.add_inference_backend(family=InferenceFamily.LLM, sdk="hello", make_worker=_make_hello_llm_worker)
        # Optional: powers `pipelex show models` for a backend serving this sdk.
        registrar.add_model_lister(sdk="hello", lister=_list_hello_models)
```

A plugin is any object with a `name`, a `targets_api` equal to the runtime's `PLUGIN_API_VERSION`, and a `register` method. Pipelex calls `register` at startup and again whenever `pipelex plugins list` rediscovers the plugins, so it must do nothing but call the registrar's menu methods: no hub access, no I/O and no client construction.

`add_inference_backend` registers a worker factory for one pair of family and `sdk` token, here the LLM family and `hello`. When a pipe first calls a model whose `sdk` is `hello`, Pipelex calls the factory with four keyword arguments: the resolved model spec, the backend's configuration, the process-wide cache of SDK clients, and the reporting delegate. The hello worker needs only the first and the last. The factory imports the worker module inside its body, so discovering the plugin imports nothing heavy.

`add_model_lister` is optional. It registers the callable behind `pipelex show models`, which Pipelex awaits when you list the models of a backend whose models use the `hello` token.

## Step 3: Write the worker

`hello_llm_worker.py` holds the model itself:

```python
from pipelex.cogt.exceptions import LLMCapabilityError
from pipelex.cogt.llm.llm_job import LLMJob
from pipelex.cogt.llm.llm_worker_abstract import LLMWorkerAbstract
from pipelex.cogt.usage.token_category import TokenCategory
from pipelex.tools.typing.pydantic_utils import BaseModelTypeVar
from typing_extensions import override

HELLO_HAIKU = """Hello, World! I am
a plugin-served model — no
keys, no clouds, just code."""


class HelloLLMWorker(LLMWorkerAbstract):
    """A deterministic LLM worker that needs no credentials: every completion is the same haiku.

    The base class owns the job lifecycle (validation, capability checks against the model spec,
    usage reporting, telemetry). A worker implements only the generation itself.
    """

    @override
    async def _gen_text(self, llm_job: LLMJob) -> str:
        completion_text = HELLO_HAIKU
        # A real worker reads the token counts from its provider's response.
        if llm_tokens_usage := llm_job.job_report.llm_tokens_usage:
            prompt_text = llm_job.llm_prompt.user_text or ""
            llm_tokens_usage.nb_tokens_by_category = {
                TokenCategory.INPUT: len(prompt_text.split()),
                TokenCategory.OUTPUT: len(completion_text.split()),
            }
        return completion_text

    @override
    async def _gen_object(
        self,
        llm_job: LLMJob,
        *,
        schema: type[BaseModelTypeVar],
    ) -> BaseModelTypeVar:
        # The model spec declares `outputs = ["text"]`, so Pipelex never routes structured
        # generation to this model. Raising keeps the worker honest if it is called directly.
        msg = f"Model '{self.inference_model.name}' does not support structured output: it only writes a haiku."
        raise LLMCapabilityError(msg)
```

`LLMWorkerAbstract` owns everything around the generation: it validates the job, checks the prompt against what the model spec says the model accepts, reports the job's usage and records its telemetry. A worker implements `_gen_text` for text and `_gen_object` for structured output. A real plugin would call its provider at the point where this one returns the haiku, and would fill the token counts from the provider's response rather than by counting words.

## Step 4: List the models (optional)

`hello_list.py` is the lister that `_list_hello_models` delegates to. The hello backend has no remote API to ask, so it prints the models declared in the backend's configuration:

```python
from pipelex.cogt.model_backends.backend import InferenceBackend
from pipelex.runtime_hub import get_console
from rich import box
from rich.table import Table


def list_hello_models(
    *,
    sdk: str,
    backend_name: str,
    backend: InferenceBackend,
    flat: bool,
    any_listed: bool,
) -> None:
    """List the models the hello backend declares.

    There is no remote API to ask, so the lister reads the model specs declared in the
    backend's configuration file.
    """
    console = get_console()
    model_names = backend.list_model_names()

    if flat:
        if not any_listed:
            console.print("model_id,sdk,backend")
        for model_name in model_names:
            model_spec = backend.get_model_spec(model_name)
            model_id = model_spec.model_id if model_spec else model_name
            console.print(f"{model_id},{sdk},{backend_name}")
        return

    table = Table(
        title=f"Available Models for Backend '{backend_name}' (SDK: {sdk})",
        show_header=True,
        header_style="bold cyan",
        box=box.SQUARE_DOUBLE_HEAD,
    )
    table.add_column("Model ID", style="green")
    table.add_column("Model Type", style="blue")
    for model_name in model_names:
        model_spec = backend.get_model_spec(model_name)
        if model_spec is None:
            continue
        table.add_row(model_spec.model_id, model_spec.model_type)
    console.print(table)
```

A backend that cannot list its models simply registers no lister, and `pipelex show models` then reports its `sdk` as one it cannot list.

## Step 5: Declare a model served by the plugin

The plugin serves the `hello` token, but a method names a model, not a token. Three entries in your inference configuration connect the two. They go in the `inference/` directory of your Pipelex configuration: `~/.pipelex/inference/`, which `pipelex init` writes, or your project's `.pipelex/inference/` if the project has one.

First, `backends/hello.toml` declares the model `hello-1`, whose `sdk = "hello"` is the token that selects the plugin's worker factory:

```toml
[defaults]
model_type = "llm"
sdk = "hello"
thinking_mode = "none"

[hello-1]
model_id = "hello-1"
inputs = ["text"]
outputs = ["text"]
costs = { input = 0, output = 0 }
```

Then `backends.toml` gains a `hello` table, which enables the backend that `backends/hello.toml` describes. It has no API key to declare:

```toml
[hello]
display_name = "Hello (plugin example)"
enabled = true
```

Finally, `routing_profiles.toml` routes the model to that backend. The file already has a table for the profile its `active` key names, here the default `[profiles.all_pipelex_gateway]`, so add one line inside that table rather than a second copy of it, which TOML refuses:

```toml
optional_routes = { "hello-1" = "hello" }
```

An optional route applies only while its backend is enabled, so turning the `hello` backend off leaves the profile valid. If you would rather not edit the tracked `backends.toml` and `routing_profiles.toml`, the same entries can go in the personal override files beside them, each under its table's header, as [Personal overrides](../configuration/config-technical/inference-backend-config.md#personal-overrides) explains.

## Step 6: Install the plugin and check that Pipelex found it

Install the package into the environment Pipelex runs in. `uv tool install` rebuilds the tool's environment from the requirements it is given, so name Pipelex exactly as you installed it: if you installed it with provider extras, such as `"pipelex[anthropic,google]"`, repeat them here, or uv removes those providers' packages.

```bash
# Pipelex installed as a uv tool, as in Run It Yourself (repeat any extras you installed it with)
uv tool install --with-editable ./hello-inference-plugin pipelex

# Pipelex installed in a project's virtual environment
uv pip install -e ./hello-inference-plugin
```

Then check that discovery registered it, and that the backend serves its model:

```bash
pipelex plugins list        # hello_inference: external, pipelex.plugins.kernel, registered
pipelex show models hello   # lists hello-1
```

In `pipelex plugins list`, the plugin's row names the group it was found under and what it contributed: `inference backend llm:hello` and `model lister hello`.

## Step 7: Run a method on the plugin's model

Save this method as `hello_plugin.mthds`. It is an ordinary one-pipe method whose `model` names `hello-1`:

```toml
domain      = "hello_plugin"
description = "Using a model served by an inference-backend plugin"
main_pipe   = "hello_plugin"

[pipe.hello_plugin]
type        = "PipeLLM"
description = "Write a haiku about Hello World."
output      = "Text"
model       = { model = "hello-1", temperature = 0.5 }
prompt      = "Write a haiku about Hello World."
```

Run it:

```bash
pipelex run bundle hello_plugin.mthds
```

The output is the plugin's haiku. The run calls no provider: the pipe resolves `hello-1` through the routing profile to the `hello` backend, and the plugin's worker writes the answer itself.

## When the plugin is missing

To see what happens without the plugin, turn it off. Naming it in the plugin denylist of your `pipelex.toml` works however you installed it, and uninstalling the package has the same effect:

```toml
[runtime.plugins]
disabled = ["hello_inference"]
```

`pipelex plugins list` now shows the plugin as `disabled`, and running the method again fails loudly when the pipe asks for its worker:

```
No inference backend registered for sdk 'hello' in the llm family. Is its plugin installed and enabled?
```

The model configuration still resolves, since `hello-1` is still declared and routed. Only the worker factory is missing, and Pipelex says so rather than falling back to another backend. A dry run of the method still passes without the plugin, because a dry run never builds a worker.

## Going further: wrapping a real SDK

A plugin that calls a real provider does three more things inside its worker factory, all described in [Inference Backend Plugins](inference-backend-plugins.md):

- it guards its optional SDK with `require_sdk(...)`, so a missing dependency raises `MissingDependencyError` when the backend is used rather than when Pipelex starts;
- it imports that SDK inside the factory, never at the top of the plugin module;
- it builds its client through `sdk_clients.get_or_create(...)`, so repeated workers share one connection per model handle.

## Related Documentation

- [Inference Backend Plugins](inference-backend-plugins.md) - The plugin seam, the Inference SPI and its fail-loud guarantees
- [LLM Providers & Models Configuration](../configuration/config-technical/inference-backend-config.md) - Backends, model specs and routing profiles
- [Run It Yourself](../get-started/run-it-yourself.md) - Installing the Pipelex runtime on your own machine
