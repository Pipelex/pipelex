# PipeSequence

The `PipeSequence` controller is used to execute a series of pipes one after another. It is the fundamental building block for creating linear methods where the output of one step becomes the input for the next.

## How it works

A `PipeSequence` defines a list of `steps`. Each step calls another pipe and gives a name to its output. The working memory is passed from one step to the next, accumulating results along the way.

-   The `input` of the `PipeSequence` is passed to the first pipe in the sequence.
-   The `output` of each intermediate step is named via the `result` key and becomes available in the working memory for all subsequent steps.
-   The final `output` of the `PipeSequence` is the output produced by the very last step in the sequence.

## Configuration

`PipeSequence` is configured in your pipeline's `.mthds` file.

### MTHDS Parameters

| Parameter  | Type            | Description                                                                                                    | Required |
| ---------- | --------------- | -------------------------------------------------------------------------------------------------------------- | -------- |
| `type`      | string          | The type of the pipe: `PipeSequence`                                                                          | Yes      |
| `description` | string          | A description of the sequence operation.                                                                          | Yes      |
| `inputs`    | dictionary  | The input concept(s) for the *first* pipe in the sequence, as a dictionary mapping input names to concept codes.                                                     | No       |
| `output`   | string          | The output concept produced by the *last* pipe in the sequence.                                                | Yes      |
| `steps`    | array of tables | An ordered list of the pipes to execute. Each table in the array defines a single step.                          | Yes      |

### Step Configuration

Each entry in the `steps` array is a table with the following keys:

| Key      | Type   | Description                                                        | Required |
| -------- | ------ | ------------------------------------------------------------------ | -------- |
| `pipe`   | string | The name of the pipe to execute for this step.                     | Yes      |
| `result` | string | The name to give to this step's output in the working memory. When omitted, the output is stored only in the unnamed `main_stuff` slot (the default output), so later steps can pick it up as their implicit input but cannot reference it by a dedicated name. | No       |
| `nb_output` | integer | Request a fixed number of outputs from this step's pipe. Cannot be combined with `multiple_output`. | No       |
| `multiple_output` | boolean | Request a variable number of outputs from this step's pipe (the model decides how many). Cannot be combined with `nb_output`. | No       |
| `batch_over` | string | The name of a list in the working memory to batch this step over, running the pipe once per item. Must be provided together with `batch_as`. See [Understanding Multiplicity](../understanding-multiplicity.md). | No       |
| `batch_as` | string | The name each item takes in the working memory during a `batch_over` run. Must differ from `batch_over` (e.g. `batch_over = "items"`, `batch_as = "item"`). | No       |

!!! important "Output Concept Matching"
    The output concept of the `PipeSequence` has to match the output of the last pipe in the sequence.

### Example

Let's imagine a pipeline that first extracts text from an image, then summarizes that text, and finally translates the summary into French.

```toml
[pipe.extract_text_from_image]
type = "PipeExtract"
description = "Extract text from an image"
inputs = { image = "Image" }
output = "Page[]"
model = "@default-extract-image"

[pipe.summarize_text]
type = "PipeLLM"
description = "Summarize text"
inputs = { extracted_text = "Page[]" }
output = "Text"

[pipe.translate_to_french]
type = "PipeLLM"
description = "Translate text to French"
inputs = { english_summary = "Text" }
output = "Text"


[pipe.image_to_french_summary]
type = "PipeSequence"
description = "Extract, summarize, and translate text from an image"
inputs = { image = "Image" }
output = "Text"
steps = [
    { pipe = "extract_text_from_image", result = "extracted_text" },
    { pipe = "summarize_text", result = "english_summary" },
    { pipe = "translate_to_french", result = "french_summary" },
]
```

## Related Documentation

- [Invoice Extraction Example](../../../cookbook/extract-invoice.md) - Complete invoice processing pipeline using PipeSequence
- [Write Tweet Example](../../../cookbook/write-tweet.md) - Multi-step tweet generation workflow
- [Table Extraction Example](../../../cookbook/extract-table.md) - Extract and correct tables from images
- [Gantt Extraction Example](../../../cookbook/extract-gantt.md) - Extract Gantt chart data from documents