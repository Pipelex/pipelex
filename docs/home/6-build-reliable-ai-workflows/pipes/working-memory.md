# Working Memory

The **Working Memory** is the mechanism that enables data flow between pipes in your pipeline. It acts as a **temporary** storage space that exists for the duration of a single pipeline run.

## How Data Flows Between Pipes

When you compose pipes together with [PipeControllers](./pipe-controllers/index.md), you need a way to pass data from one pipe to another. This is where the Working Memory comes in.

Consider our marketing pipeline example from the [Designing Pipelines](index.md) guide:

```plx
[pipe.description_to_tagline]
type = "PipeSequence"
description = "From product description to tagline"
inputs = { description = "ProductDescription" }
output = "Tagline"
steps = [
    { pipe = "generate_tagline", result = "tagline" },
    { pipe = "extract_keywords_from_tagline", result = "keywords" },
]
```

How does data get from `generate_tagline` to `extract_keywords_from_tagline`? This is handled by the Working Memory:

1.  When a pipe in a sequence executes, its output is given a name using the `result` key (e.g., `result = "tagline"`).
2.  This named result is placed into the Working Memory as a `Stuff`.
3.  Subsequent pipes can then reference this data by its name in their `inputs` field (e.g., `inputs = { tagline = "Tagline" }`).

This mechanism allows you to chain pipes together, creating a flow of information through your pipeline.

## Working Memory Lifecycle

*   **Creation**: The Working Memory is created at the start of a pipeline run.
*   **Population**: Initial inputs are placed in the Working Memory before the first pipe executes.
*   **Updates**: As each pipe completes, its output (named via the `result` field) is added to the Working Memory.
*   **Access**: Any pipe can access data from the Working Memory by declaring it in their `inputs` field.
*   **Disposal**: The Working Memory is cleared when the pipeline run completes.

## Best Practices

*   **Meaningful Names**: Use descriptive names for your `result` values to make your pipeline easier to understand.
*   **Clear Contracts**: Each pipe's `inputs` field clearly declares what data it needs from the Working Memory.
*   **Fail Fast**: If a required input is missing from the Working Memory, the pipeline will fail immediately with a clear error message before the pipe executes.

For more information on how to execute pipelines and provide initial inputs to the Working Memory, see [Executing Pipelines](executing-pipelines.md).

