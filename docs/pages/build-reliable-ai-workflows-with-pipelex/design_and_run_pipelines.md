# Designing and Running Pipelines

In Pipelex, a pipeline is not just a rigid sequence of steps; it's a dynamic and intelligent workflow built by composing individual, reusable components called **pipes**. This approach allows you to break down complex AI tasks into manageable, testable, and reliable units.

This guide provides an overview of how to design your pipelines and execute them.

## The Building Blocks: Pipes

A pipeline is composed of pipes. There are two fundamental types of pipes you will use to build your workflows:

*   **[Pipe Operators](pipe-operators/index.md)**: These are the "workers" of your pipeline. They perform concrete actions like calling an LLM (`PipeLLM`), extracting text from a document (`PipeOcr`), or running a Python function (`PipeFunc`). Each operator is a specialized tool designed for a specific task.
*   **[Pipe Controllers](pipe-controllers/index.md)**: These are the "managers" of your pipeline. They don't perform tasks themselves but orchestrate the execution flow of other pipes. They define the logic of your workflow, such as running pipes in sequence (`PipeSequence`), in parallel (`PipeParallel`), or based on a condition (`PipeCondition`).

## Designing a Pipeline: Composition in TOML

The most common way to design a pipeline is by defining and composing pipes in a `.toml` configuration file. This provides a clear, declarative way to see the structure of your workflow.

Each pipe, whether it's an operator or a controller, is defined in its own `[pipe.<pipe_name>]` table. The `<pipe_name>` becomes the unique identifier for that pipe.

Let's look at a simple example. Imagine we want a workflow that:
1.  Takes a product description.
2.  Generates a short, catchy marketing tagline for it.

We can achieve this with a `PipeLLM` operator.

```toml
# Filename: my_pipes.toml

# 1. Define the concepts used in our pipes
[concept.ProductDescription]
refines = "native.Text"

[concept.Tagline]
refines = "native.Text"

# 2. Define the pipe that does the work
[pipe.generate_tagline]
PipeLLM = "Generate a catchy tagline for a product."
input = "ProductDescription"
prompt_template = """
Product Description:
{{ ProductDescription }}
---
Generate a catchy tagline based on the above description.
"""
output = "Tagline"
```

This defines a single-step pipeline. The pipe `generate_tagline` takes a `ProductDescription` as input and outputs a `Tagline`.

To create a multi-step workflow, you use a controller. The `PipeSequence` controller is the most common one. It executes a series of pipes in a specific order.

```toml
# Filename: my_pipes.toml

# 1. Define concepts
[concept.Keywords]
refines = "native.Text"

[concept.Tagline]
refines = "native.Text"


# 2. Define operator pipes
[pipe.extract_keywords]
PipeLLM = "Extract keywords from a text."
input = "native.Text"
prompt_template = """
Please extract the most relevant keywords from the following text:
---
{{ native.Text }}
"""
output = "Keywords"

[pipe.generate_tagline_from_keywords]
PipeLLM = "Generate a tagline from a list of keywords."
input = "Keywords"
prompt_template = """
Here are some keywords:
{{ Keywords }}
---
Please generate a catchy marketing tagline based on these keywords.
"""
output = "Tagline"

# 3. This controller pipe defines the two-step pipeline
[pipe.text_to_tagline]
PipeSequence = "From text to tagline"
input = "native.Text"
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
3.  Subsequent pipes can then reference this data by its name in their `input` field (e.g., `input = "extracted_keywords"`).

This mechanism allows you to chain pipes together, creating a flow of information through your pipeline.

## Running a Pipeline

Once your pipes are defined, you can execute them from your Python code. Pipelex provides two main functions for this: `start_pipeline` and `execute_pipeline`.

To run the `text_to_tagline` pipeline we defined above, you would call it by its unique name:

```python
import asyncio
from pipelex.session import PipelexSession
from pipelex.pipeline.execute import execute_pipeline
from pipelex.core.working_memory import WorkingMemory

# First, initialize a Pipelex session and load your definitions
session = PipelexSession()
session.load_tome_file("my_pipes.toml")

async def main():
    # Prepare the initial working memory with the pipeline's input
    working_memory = WorkingMemory()
    working_memory.add_stuff(
        "my product is a self-cleaning water bottle",
        concept_code="native.Text"
    )

    # Execute the pipeline and wait for the result
    output_stuff = await execute_pipeline(
        pipe_code="text_to_tagline",
        working_memory=working_memory,
    )

    print(f"Generated tagline: {output_stuff.content}")

if __name__ == "__main__":
    asyncio.run(main())
```

-   `execute_pipeline`: Runs the specified pipe and waits for it to complete, returning the final output. This is useful for simple, synchronous-style interactions.
-   `start_pipeline`: Immediately returns a `pipeline_run_id` and an `asyncio.Task`. This allows you to run pipelines in the background and manage them asynchronously, which is essential for complex, long-running, or parallel workflows.

By combining declarative TOML definitions with a powerful Python execution model, Pipelex gives you a robust framework for building and running reliable AI workflows.
