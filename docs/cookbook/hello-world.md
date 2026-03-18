---
title: "Hello World Example"
description: "The Hello World of Pipelex — a simple pipeline demonstrating basic concepts. Verify your installation and get a first taste of how Pipelex works."
---

# Example: Hello World

This is the "Hello World" of Pipelex, a simple pipeline that demonstrates the basic concepts of Pipelex.

It's the perfect starting point to verify your installation and get a first taste of how Pipelex works.

## Get the code

[![GitHub](https://img.shields.io/badge/View_on_GitHub-5a0dad?logo=github&logoColor=white&style=flat)](https://github.com/Pipelex/pipelex-cookbook/blob/main/examples/a_quick_start/hello_world.mthds)

## What it demonstrates

- Minimal Pipelex setup with a single `PipeLLM` pipe
- The `main_pipe` field to designate the entry point
- Running a method bundle from the CLI

## The Method: `hello_world.mthds`

The method definition is extremely simple — a single LLM call that generates a haiku:

```toml
domain    = "quick_start"
main_pipe = "hello_world"

[pipe]
[pipe.hello_world]
type = "PipeLLM"
description = "Write text about Hello World."
output = "Text"
prompt = """
Write a haiku about Hello World.
"""
```

## How to run

1. Clone the cookbook repository and install dependencies:

    ```bash
    git clone https://github.com/Pipelex/pipelex-cookbook.git
    cd pipelex-cookbook
    pip install .
    ```

2. Set up your environment variables by copying `.env.example` to `.env` and adding your API keys.

3. Run the example:

    ```bash
    pipelex run bundle examples/a_quick_start/hello_world.mthds
    ```

Expected output: A haiku about "Hello World" displayed with pretty formatting.

## Related Documentation

- [PipeLLM Operator](../building-methods/pipes/pipe-operators/PipeLLM.md) - The core operator for LLM interactions
- [Define Your Concepts](../building-methods/concepts/define_your_concepts.md) - How to define custom data types for your methods
