# Example: Hello World

This is the "Hello World" of Pipelex, a simple pipeline that demonstrates the basic concepts of Pipelex.

It's the perfect starting point to verify your installation and get a first taste of how Pipelex works.

## Get the code

You can find the complete code for this example in the Pipelex Cookbook repository.

[**➡️ View on GitHub: quick_start/hello_world.py**](https://github.com/Pipelex/pipelex-cookbook/blob/main/quick_start/hello_world.py)

## The Pipeline Explained

The `hello_world` function demonstrates the simplest possible Pipelex pipeline. It runs a single pipe that generates a haiku about "Hello World".

```python
import asyncio

from pipelex import pretty_print
from pipelex.pipelex import Pipelex
from pipelex.pipeline.execute import execute_pipeline


async def hello_world():
    """
    This function demonstrates the use of a super simple Pipelex pipeline to generate text.
    """
    # Run the pipe
    pipe_output = await execute_pipeline(
        pipe_code="hello_world",
    )

    # Print the output
    pretty_print(pipe_output, title="Your first Pipelex output")


# start Pipelex
Pipelex.make()
# run sample using asyncio
asyncio.run(hello_world())
```

This example shows the minimal setup needed to run a Pipelex pipeline: initialize Pipelex, execute a pipeline by its code name, and pretty-print the results.

## The Pipeline Definition: `hello_world.plx`

The pipeline definition is extremely simple - it's a single LLM call that generates a haiku:

```plx
domain = "quick_start"
description = "Discovering Pipelex"

[pipe]
[pipe.hello_world]
type = "PipeLLM"
description = "Write text about Hello World."
output = "Text"
model = { model = "gpt-4o-mini", temperature = 0.9, max_tokens = "auto" }
prompt = """
Write a haiku about Hello World.
"""
```

## How to run

1.  Clone the cookbook repository:
    ```bash
    git clone https://github.com/Pipelex/pipelex-cookbook.git
    cd pipelex-cookbook
    ```
2.  Install dependencies:
    ```bash
    make install
    ```
3.  Set up your environment variables by copying `.env.example` to `.env` and adding your API keys.
4.  Run the example:
    ```bash
    python quick_start/hello_world.py
    ```

Expected output: A haiku about "Hello World" displayed with pretty formatting.
