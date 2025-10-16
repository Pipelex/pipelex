# Designing and Running Pipelines

In Pipelex, a pipeline is not just a rigid sequence of steps; it's a dynamic and intelligent workflow built by composing individual, reusable components called **pipes**. This approach allows you to break down complex AI tasks into manageable, testable, and reliable units.

This guide provides an overview of how to design your pipelines and execute them.

## The Building Blocks: Pipes

A pipeline is composed of pipes. There are two fundamental types of pipes you will use to build your workflows:

*   **[Pipe Operators](pipe-operators/index.md)**: These are the "workers" of your pipeline. They perform concrete actions like calling an LLM (`PipeLLM`), extracting text from a document (`PipeExtract`), or running a Python function (`PipeFunc`). Each operator is a specialized tool designed for a specific task.
*   **[Pipe Controllers](pipe-controllers/index.md)**: These are the "managers" of your pipeline. They don't perform tasks themselves but orchestrate the execution flow of other pipes. They define the logic of your workflow, such as running pipes in sequence (`PipeSequence`), in parallel (`PipeParallel`), or based on a condition (`PipeCondition`).

## Designing a Pipeline: Composition in PLX

The most common way to design a pipeline is by defining and composing pipes in a `.plx` configuration file. This provides a clear, declarative way to see the structure of your workflow.

Each pipe, whether it's an operator or a controller, is defined in its own `[pipe.<pipe_name>]` table. The `<pipe_name>` becomes the unique identifier for that pipe.

Let's look at a simple example. Imagine we want a workflow that:
1.  Takes a product description.
2.  Generates a short, catchy marketing tagline for it.

We can achieve this with a `PipeLLM` operator.

```plx
# Filename: marketing_pipeline.plx

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
prompt = """
Product Description:
@description

Generate a catchy tagline based on the above description.
The tagline should be memorable, concise, and highlight the key benefit.
"""
```

This defines a single-step pipeline. The pipe `generate_tagline` takes a `ProductDescription` as input and outputs a `Tagline`.

To create a multi-step workflow, you use a controller. The `PipeSequence` controller is the most common one. It executes a series of pipes in a specific order.

The inputs specified will be required before the pipe is executed. Those inputs should be stored in the Working Memory.

The output concept is very important. Indeed, the output of your pipe wille be corresponding to the concept you specify. If the concept is structured, the output will be a structured object. If the concept is native, the output will be a string.

```plx
# Filename: marketing_pipeline.plx

domain = "marketing"
description = "Marketing content generation domain"

# 1. Define concepts
[concept]
ProductDescription = "A description of a product's features and benefits"
Keyword = "A keyword extracted from a text"
Tagline = "A catchy marketing tagline"

# 2. Define operator pipes
[pipe.extract_keywords]
type = "PipeLLM"
description = "Extract keywords from a product description"
inputs = { description = "ProductDescription" }
output = "Keyword"
multiple_output = true
prompt = """
Please extract the most relevant keywords from the following product description:

@description

Focus on features, benefits, and unique selling points.
"""
```

!!! note "Multiple Outputs"
    The `multiple_output = true` setting allows the LLM to generate as many keywords as it finds relevant. For a comprehensive guide on controlling how many items pipes produce or accept, see [Understanding Multiplicity](understanding-multiplicity.md).

```plx
[pipe.generate_tagline_from_keywords]
type = "PipeLLM"
description = "Generate a tagline from keywords"
inputs = { keywords = "Keyword" }
output = "Tagline"
prompt = """
Here are the key product keywords:
@keywords

Generate a catchy marketing tagline based on these keywords.
The tagline should be memorable, concise (under 10 words), and highlight the main benefit.
"""

# 3. This controller pipe defines the two-step pipeline
[pipe.description_to_tagline]
type = "PipeSequence"
description = "From product description to tagline"
inputs = { description = "ProductDescription" }
output = "Tagline"
steps = [
    { pipe = "extract_keywords", result = "extracted_keywords" },
    { pipe = "generate_tagline_from_keywords", result = "tagline" },
]
```

## Data Flow: The Working Memory

How does data get from `extract_keywords` to `generate_tagline_from_keywords`? This is handled by the **Working Memory**.

The Working Memory is a temporary storage space that exists for the duration of a single pipeline run.

1.  When a pipe in a sequence executes, its output is given a name using the `result` key (e.g., `result = "extracted_keywords"`).
2.  This named result is placed into the Working Memory.
3.  Subsequent pipes can then reference this data by its name in their `inputs` field (e.g., `inputs = { keywords = "Keyword" }`).

This mechanism allows you to chain pipes together, creating a flow of information through your pipeline.

## Running a Pipeline

Once your pipes are defined, you can execute them from your Python code. Pipelex provides two main functions for this: `start_pipeline` and `execute_pipeline`.

To run the `description_to_tagline` pipeline we defined above, you would call it by its unique name:

```python
import asyncio

from pipelex.pipelex import Pipelex
from pipelex.pipeline.execute import execute_pipeline

async def main():
    # First, initialize Pipelex (this loads all pipeline definitions)
    Pipelex.make()

    # Execute the pipeline and wait for the result
    pipe_output = await execute_pipeline(
        pipe_code="description_to_tagline",
        input_memory={
            "description": {
                "concept": "ProductDescription",
                "content": "EcoClean Pro is a revolutionary biodegradable cleaning solution that removes 99.9% of germs while being completely safe for children and pets. Made from plant-based ingredients.",
            },
        },
    )

    # Get the final output
    tagline = pipe_output.main_stuff_as_str
    print(f"Generated tagline: {tagline}")

if __name__ == "__main__":
    asyncio.run(main())
```

-   `execute_pipeline`: Runs the specified pipe and waits for it to complete, returning the final output. This is useful for simple, synchronous-style interactions.
-   `start_pipeline`: Immediately returns a `pipeline_run_id` and an `asyncio.Task`. This allows you to run pipelines in the background and manage them asynchronously, which is essential for complex, long-running, or parallel workflows.

By combining declarative PLX definitions with a powerful Python execution model, Pipelex gives you a robust framework for building and running reliable AI workflows.
