---
description: "Working memory enables data flow between pipes during pipeline execution. Learn how Pipelex stores and passes typed data across steps."
---

# Working Memory

!!! tip "MTHDS Standard Reference"
    Working memory is part of the MTHDS open standard. For the authoritative language specification, see [Working Memory](https://mthds.ai/latest/language/working-memory/) on mthds.ai. This page documents Pipelex-specific behavior and usage.

The **Working Memory** is the mechanism that enables data flow between pipes in your pipeline. It acts as a **temporary** storage space that exists for the duration of a single pipeline run.

## How Data Flows Between Pipes

When you compose pipes together with [PipeControllers](./pipe-controllers/index.md), you need a way to pass data from one pipe to another. This is where the Working Memory comes in.

Consider our marketing pipeline example from the [Designing Pipelines](index.md) guide:

```toml
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

## In memory and on the wire

A stuff has two shapes, and which one you are looking at depends on which side of the runtime you stand.

*   **In memory**, a `Stuff` holds a resolved `Concept`: the runtime's own concept model, carrying the definition it needs to work — the description, the `structure_class_name` that names the content class, and what the concept `refines`. That definition is the library's: it comes from the bundle the method loaded.
*   **On the wire**, a stuff *names* its concept and carries no definition. Every dump of a working memory — the `working_memory.json` a run saves, the agent CLI's `--with-memory` envelope, the runner's response — spells each stuff as `{"stuff_code": …, "stuff_name": …, "concept": "<domain>.<Code>", "content": …}`, which is the form the MTHDS [CLI I/O contract](https://mthds.ai/latest/spec/cli-io-contract/) requires.

A dump is therefore one-way: a stuff cannot be rebuilt from its own dump alone. A reader that needs the definition resolves the ref through the library the method loads — exactly how an input envelope's `"concept": "my_domain.Invoice"` is resolved when a run starts (see [Providing Inputs](provide-inputs.md#the-explicit-format-escape-hatch)), which is why the `--with-memory` envelope of one run can be piped straight into the next.

### The limit of `<domain>.<Code>`, and what this runtime does about it

The MTHDS standard defines two spellings for a concept on the wire: `<domain>.<Code>` for a concept the running method's own bundles declare (and for the native set), and `<package_address>::<domain>.<Code>` for a concept a **dependency package** contributes. **This runtime emits only the first, and resolves only the first** — it neither writes nor accepts the `::` form.

That is enough in the ordinary case, because the library a reader resolves against knows which package contributed each concept: a dependency's concept is held under its package address internally, so a bare `<domain>.<Code>` arriving from the wire finds it. What the bare form cannot express is a *collision* — when the running method's own bundle and one of its dependencies both declare, say, `scoring.WeightedScore`, the ref names both and nothing on the wire says which was meant. Rather than pick one and bind the wrong definition to your data, the runtime refuses the hydration and names every candidate it found. Two ways out: rename one of the two concepts, or keep them in methods that do not run together.

## Best Practices

*   **Meaningful Names**: Use descriptive names for your `result` values to make your pipeline easier to understand.
*   **Clear Contracts**: Each pipe's `inputs` field clearly declares what data it needs from the Working Memory.
*   **Fail Fast**: If a required input is missing from the Working Memory, the pipeline will fail immediately with a clear error message before the pipe executes.

For more information on how to execute pipelines and provide initial inputs to the Working Memory, see [Executing Pipelines](executing-pipelines.md).

