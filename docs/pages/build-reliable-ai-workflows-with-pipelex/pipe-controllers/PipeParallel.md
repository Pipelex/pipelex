# PipeParallel

The `PipeParallel` controller executes multiple pipes simultaneously. This is highly effective for running pipes concurrently in isolated branches.

## How it works

`PipeParallel` runs a list of sub-pipes in concurrent branches.

1.  **Isolation**: Before execution, `PipeParallel` creates a deep copy of the current `WorkingMemory` for each branch. This means every parallel pipe starts with the exact same state, but they run in complete isolation—a change in one branch will not affect another.
2.  **Concurrent Execution**: All specified pipes are executed at the same time using `asyncio.gather`.
3.  **Output Handling**: After all parallel tasks have finished, their results are collected and added back to the main working memory. You can control how this happens with two parameters:
    -   `add_each_output`: If `true`, the individual result of each branch is added to the working memory under the name specified in its `result` key.
    -   `combined_output`: If you provide an output concept here, the results of all branches are bundled together into a single structured object. The field names of this object correspond to the `result` names of the branches.

You must use `add_each_output`, `combined_output`, or both.

## Configuration

`PipeParallel` is configured in your pipeline's `.plx` file.

### PLX Parameters

| Parameter         | Type          | Description                                                                                                                                                                    | Required |
| ----------------- | ------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | -------- |
| `type`            | string        | The type of the pipe: `PipeParallel`                                                                          | Yes      |
| `definition`     | string        | A description of the parallel operation.                                                                           | Yes      |
| `inputs`    | dictionary  | The input concept(s) for the parallel operation, as a dictionary mapping input names to concept codes.                                                     | Yes       |
| `output`   | string          | The output concept produced by the parallel operation.                                                | Yes      |
| `parallels`       | array of tables| An array defining the pipes to run in parallel. Each table is a sub-pipe definition.                                                                                           | Yes      |
| `add_each_output` | boolean       | If `true`, adds the output of each parallel pipe to the working memory individually. Defaults to `true`.                                                                       | No       |
| `combined_output` | string        | The name of a concept to use for a single, combined output object. The structure of this concept must have fields that match the `result` names from the `parallels` array.      | No       |

### Parallel Step Configuration

Each entry in the `parallels` array is a table with the following keys:

| Key      | Type   | Description                                                                              | Required |
| -------- | ------ | ---------------------------------------------------------------------------------------- | -------- |
| `pipe`   | string | The name of the pipe to execute for this branch.                                         | Yes      |
| `result` | string | The name for this branch's output. Must be unique within the `PipeParallel` definition. | Yes      |

### Example: Extracting different details from a text

Imagine you have a product description and you want to extract the product features and the product sentiment at the same time.

```plx
[concept.ProductAnalysis]
structure = "ProductAnalysis" # A Pydantic model with 'features' and 'sentiment' fields

[pipe.extract_features]
type = "PipeLLM"
definition = "Extract features from text"
inputs = { description = "ProductDescription" }
output = "ProductFeatures"

[pipe.analyze_sentiment]
type = "PipeLLM"
definition = "Analyze sentiment of text"
inputs = { description = "ProductDescription" }
output = "ProductSentiment"

# The PipeParallel definition
[pipe.analyze_product_in_parallel]
type = "PipeParallel"
definition = "Extract features and sentiment at the same time"
inputs = { description = "ProductDescription" }
output = "ProductAnalysis" # This name is for the combined output
add_each_output = true
combined_output = "ProductAnalysis"
parallels = [
    { pipe = "extract_features", result = "features" },
    { pipe = "analyze_sentiment", result = "sentiment" },
]
```

How this works:
1.  The `analyze_product_in_parallel` pipe starts. It receives a `ProductDescription`.
2.  Two parallel branches are created, both with access to the `ProductDescription`.
3.  The `extract_features` pipe runs in one branch, and the `analyze_sentiment` pipe runs in the other, simultaneously.
4.  After both complete, `PipeParallel` collects the results. The output from `extract_features` is named `features`, and the output from `analyze_sentiment` is named `sentiment`.
5.  Because `combined_output` is set to `ProductAnalysis`, a new structured object of type `ProductAnalysis` is created. This object is populated with the results, like `{"features": ..., "sentiment": ...}`.
6.  This single `ProductAnalysis` object becomes the final output of the `analyze_product_in_parallel` pipe. 