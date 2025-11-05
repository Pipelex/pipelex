# Executing Pipelines

Once your pipes are defined in `.plx` files, you can execute them in multiple ways:

## Option 1: Using the Pipelex CLI

First you can prepare the inputs for your pipeline in a JSON file.

```bash
pipelex build inputs path/to/my_pipe.plx
```

This will create a `inputs.json` file in the `results` directory, with the needed inputs for your pipeline. You can fill in the values for the inputs in the `results/inputs.json` file.

Then you can execute the pipeline with the CLI.

```bash
pipelex run path/to/my_pipe.plx --inputs results/inputs.json
```

See more about the CLI [here](../../../home/9-tools/cli.md).

## Option 2: Using the python method `execute_pipeline`

This function executes the specified pipe and waits for it to complete, returning the final output.

There are 2 ways of using the `execute_pipeline` method:

### Option 2.1: Using the pipe code

This requires your pipelex file to be in the current directory, that means it will be loaded in the library. You can use the `pipelex show pipes` command to list all the pipes available in your project.

```python
from pipelex.pipelex import Pipelex
from pipelex.pipeline.execute import execute_pipeline

# First, initialize Pipelex (this loads all pipeline definitions)
Pipelex.make()

# Execute the pipeline and wait for the result
pipe_output = await execute_pipeline(
    pipe_code="description_to_tagline",
    inputs={
        "description": {
            "concept": "ProductDescription",
            "content": "EcoClean Pro is a revolutionary biodegradable cleaning solution that removes 99.9% of germs while being completely safe for children and pets. Made from plant-based ingredients.",
        },
    },
)
```

### Option 2.2: Using the pipelex bundle content

You can directly pass to the `execute_pipeline` method the content of your pipelex file and the necessary inputs.

```python
from pipelex.pipelex import Pipelex
from pipelex.pipeline.execute import execute_pipeline

my_pipe_content = """
domain = "marketing"
description = "Marketing content generation domain"

# 1. Define the concepts used in our pipes
[concept]
ProductDescription = "A description of a product's features and benefits"
Tagline = "A catchy marketing tagline"

# 2. Define the pipe that does the work
[pipe.generate_tagline]
type = "PipeLLM"
description = "Generate a catchy tagline for a product"
inputs = { description = "ProductDescription" }
output = "Tagline"
prompt = "Product Description: @description \n Generate a catchy tagline based on the above description. The tagline should be memorable, concise, and highlight the key benefit.
"""
pipe_output = await execute_pipeline(
    plx_content=my_pipe_content,
    pipe_code="description_to_tagline",
    inputs={
        "description": {
            "concept": "ProductDescription",
            "content": "EcoClean Pro is a revolutionary biodegradable cleaning solution that removes 99.9% of germs while being completely safe for children and pets. Made from plant-based ingredients.",
        },
    },
)
```

!!! note "Using the pipe code"
    If your `plx_content` contains a `main_pipe` property (See more about the [Pipelex Bundle Specification](../pipelex-bundle-specification.md)), there is no need to provide the `pipe_code` parameter, the pipe that will be executed will be the one defined by `main_pipe` property. However if it doesn't, you must to provide the `pipe_code` parameter.

    If you provide the `pipe_code` and your `plx_content` does contain a `main_pipe` property, the pipe_code will be the one to be executed.

## Option 3: Using the Pipelex API

Pipelex has an API, see more about it [here](https://pipelex.github.io/pipelex-api/).

# Background Execution with `start_pipeline`

For more complex scenarios where you need asynchronous control, use `start_pipeline`. This function immediately returns a `pipeline_run_id` and an `asyncio.Task`, allowing you to run pipelines in the background.

```python
from pipelex.pipelex import Pipelex
from pipelex.pipeline.start import start_pipeline

Pipelex.make()

# Start the pipeline without waiting
pipeline_run_id, task = await start_pipeline(
    pipe_code="description_to_tagline",
    inputs={
        "description": {
            "concept": "ProductDescription",
            "content": "...",
        },
    },
)

print(f"Pipeline started with ID: {pipeline_run_id}")

# Do other work while the pipeline runs...

# Wait for completion when ready
pipe_output = await task
```
