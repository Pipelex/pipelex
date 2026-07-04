---
description: "Execute multiple pipes concurrently with PipeParallel. Speed up independent tasks while keeping each branch isolated in its own memory, then deliver their combined results as one output."
---

# PipeParallel

The `PipeParallel` controller executes multiple pipes simultaneously, then combines their results into a single output. This is highly effective for running independent tasks concurrently in isolated branches.

## How it works

`PipeParallel` runs a list of sub-pipes in concurrent branches.

1.  **Isolation**: Before execution, `PipeParallel` creates a deep copy of the current `WorkingMemory` for each branch. This means every parallel pipe starts with the exact same state, but they run in complete isolation—a change in one branch will not affect another.
2.  **Concurrent Execution**: All specified pipes are executed at the same time using `asyncio.gather`.
3.  **Combination**: After all branches have finished, their results are always combined into a single object of the pipe's declared `output` concept, keyed by each branch's `result` name. That combined object is the pipe's main output.
4.  **Optional branch exposure**: If `add_each_output` is `true`, each branch's individual result is also added to the working memory under the name specified in its `result` key, so downstream pipes can consume branches directly.

## The output concept

The declared `output` of a `PipeParallel` is the concept the branch results are combined into. It must be one of:

-   **`Composite`** — the native untyped composition: the combined object simply holds each branch result under its `result` name. Use this when you don't want to declare a bespoke concept.
-   **A structured concept** whose fields correspond to the branch `result` names: every required field of the structure must match a branch `result` name, and every `result` name must match a declared field. Branch output *types* are checked too: when a field is typed with a content class, the branch feeding it must produce that concept or one refining it (e.g. a concept that refines `Text` fits a `TextContent` field).

Anything else is rejected at validation time: scalar native concepts (`Text`, `Image`, ...), `Dynamic`, `Anything`, and multiplicity suffixes (`Foo[]`, `Foo[3]`) are all invalid — a parallel combination is a named composite, never a scalar or a list (a list aggregation is [`PipeBatch`](PipeBatch.md)'s shape).

### Combining under absence

A branch result may legitimately be **absent** at run time: the branch pipe declares an optional output (`?`), or the branch is lifted (skipped) because a plain input is fed by one of the parallel's own optional (`?`) inputs. The combine handles absence by output kind:

-   **`Composite` output**: the absent component is simply omitted from the combined object (an absence note is kept in the ledger for observability).
-   **Structured output, non-required field**: the absence is absorbed as the field's default (`null` unless the field declares another default).
-   **Structured output, required field**: this is rejected **statically** at validation time (`optional_branch_required_field`) — a required field cannot be fed by a maybe-absent branch. Make the field non-required, or sink the absence upstream with a `?` input on the branch path.

## Configuration

`PipeParallel` is configured in your pipeline's `.mthds` file.

### MTHDS Parameters

| Parameter         | Type          | Description                                                                                                                                                                    | Required |
| ----------------- | ------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | -------- |
| `type`            | string        | The type of the pipe: `PipeParallel`                                                                          | Yes      |
| `description`     | string        | A description of the parallel operation.                                                                           | Yes      |
| `inputs`    | dictionary  | The input concept(s) for the parallel operation, as a dictionary mapping input names to concept codes.                                                     | Yes       |
| `output`   | string          | The concept the branch results are combined into: `Composite` or a structured concept whose fields match the branch `result` names.                                                | Yes      |
| `branches`        | array of tables| An array defining the pipes to run in parallel. Each table is a sub-pipe definition.                                                                                           | Yes      |
| `add_each_output` | boolean       | If `true`, also adds the output of each parallel pipe to the working memory individually under its `result` name. Defaults to `false`.                                                                       | No       |

### Parallel Step Configuration

Each entry in the `branches` array is a table with the following keys:

| Key      | Type   | Description                                                                              | Required |
| -------- | ------ | ---------------------------------------------------------------------------------------- | -------- |
| `pipe`   | string | The name of the pipe to execute for this branch.                                         | Yes      |
| `result` | string | The name for this branch's output. Must be unique within the `PipeParallel` definition. | Yes      |

### Example: Extracting different details from a text

Imagine you have a product description and you want to extract the product features and the product sentiment at the same time.

```toml
[concept.ProductAnalysis]
description = "Combined product analysis"

[concept.ProductAnalysis.structure]
features  = { type = "text", description = "Product features", required = true }
sentiment = { type = "text", description = "Product sentiment", required = true }

[pipe.extract_features]
type = "PipeLLM"
description = "Extract features from text"
inputs = { description = "ProductDescription" }
output = "ProductFeatures"

[pipe.analyze_sentiment]
type = "PipeLLM"
description = "Analyze sentiment of text"
inputs = { description = "ProductDescription" }
output = "ProductSentiment"

# The PipeParallel definition
[pipe.analyze_product_in_parallel]
type = "PipeParallel"
description = "Extract features and sentiment at the same time"
inputs = { description = "ProductDescription" }
output = "ProductAnalysis" # The concept the branch results are combined into
add_each_output = true
branches = [
    { pipe = "extract_features", result = "features" },
    { pipe = "analyze_sentiment", result = "sentiment" },
]
```

How this works:

1.  The `analyze_product_in_parallel` pipe starts. It receives a `ProductDescription`.
2.  Two parallel branches are created, both with access to the `ProductDescription`.
3.  The `extract_features` pipe runs in one branch, and the `analyze_sentiment` pipe runs in the other, simultaneously.
4.  After both complete, `PipeParallel` collects the results. The output from `extract_features` is named `features`, and the output from `analyze_sentiment` is named `sentiment`.
5.  A new structured object of type `ProductAnalysis` is created and populated with the results, like `{"features": ..., "sentiment": ...}`. This object becomes the main output of the `analyze_product_in_parallel` pipe.
6.  Because `add_each_output` is `true`, `features` and `sentiment` are also available individually in the working memory for downstream pipes.

If you don't want to declare a `ProductAnalysis` concept, set `output = "Composite"` instead: the combined object then holds the same `{"features": ..., "sentiment": ...}` shape as an untyped composition.

## Related Documentation

- [Pipeline Orchestration](../../../features/pipeline-orchestration.md) - Overview of pipeline orchestration capabilities
- [Native Concepts](../../concepts/native-concepts.md) - Includes the `Composite` concept
