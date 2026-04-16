# Example: Using Inference Plugins

This example shows how to use an LLM inference plugin to route model calls through a custom provider configuration instead of the default Pipelex gateway.

## Get the code

[![GitHub](https://img.shields.io/badge/View_on_GitHub-5a0dad?logo=github&logoColor=white&style=flat)](https://github.com/Pipelex/pipelex-cookbook/blob/main/examples/c_advanced/using_inference_plugins/hello_plugin.mthds)

## What it demonstrates

- Referencing an LLM plugin by name in the `model` field
- How plugins allow you to use your own API keys and provider configuration
- Minimal change from a standard `PipeLLM` pipe

## The Method: `hello_plugin.mthds`

```toml
domain      = "hello_plugin"
main_pipe   = "hello_plugin"

[pipe]
[pipe.hello_plugin]
type = "PipeLLM"
description = "Write text about Hello World."
output = "Text"
model = { model = "llm_plugin_example_using_openai", temperature = 0.5 }
prompt = """
Write a haiku about Hello World.
"""
```

The key difference from the standard [Hello World](./hello-world.md) example is the `model` field: instead of using a default gateway model, it references `llm_plugin_example_using_openai` — a plugin defined in your project's configuration.

## How to run

1. Configure the LLM plugin in your project's `.pipelex/pipelex.toml` (see the [Configuration](../features/configuration.md) docs for details).

2. Run the example:

    ```bash
    pipelex run bundle examples/c_advanced/using_inference_plugins/hello_plugin.mthds
    ```

## Related Documentation

- [LLM Integration](../features/llm-integration.md) - Overview of LLM integration and plugins
- [Configuration System](../features/configuration.md) - How to configure providers and plugins
- [Pipelex Gateway & Model Access](../features/gateway.md) - Default model access through the gateway
