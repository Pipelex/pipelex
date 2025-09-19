# PipeSequence

The `PipeSequence` controller is used to execute a series of pipes one after another. It is the fundamental building block for creating linear workflows where the output of one step becomes the input for the next.

## How it works

A `PipeSequence` defines a list of `steps`. Each step calls another pipe and gives a name to its output. The working memory is passed from one step to the next, accumulating results along the way.

-   The `input` of the `PipeSequence` is passed to the first pipe in the sequence.
-   The `output` of each intermediate step is named via the `result` key and becomes available in the working memory for all subsequent steps.
-   The final `output` of the `PipeSequence` is the output produced by the very last step in the sequence.

## Configuration

`PipeSequence` is configured in your pipeline's `.plx` file.

### PLX Parameters

| Parameter  | Type            | Description                                                                                                    | Required |
| ---------- | --------------- | -------------------------------------------------------------------------------------------------------------- | -------- |
| `type`      | string          | The type of the pipe: `PipeSequence`                                                                          | Yes      |
| `definition` | string          | A description of the sequence operation.                                                                          | Yes      |
| `inputs`    | dictionary  | The input concept(s) for the *first* pipe in the sequence, as a dictionary mapping input names to concept codes.                                                     | No       |
| `output`   | string          | The output concept produced by the *last* pipe in the sequence.                                                | Yes      |
| `steps`    | array of tables | An ordered list of the pipes to execute. Each table in the array defines a single step.                          | Yes      |

### Step Configuration

Each entry in the `steps` array is a table with the following keys:

| Key      | Type   | Description                                                        | Required |
| -------- | ------ | ------------------------------------------------------------------ | -------- |
| `pipe`   | string | The name of the pipe to execute for this step.                     | Yes      |
| `result` | string | The name to give to the output of this step in the working memory. | Yes      |

**Important**: The output concept of the `PipeSequence` has to match the output of the last pipe in the sequence.

### Example

Let's imagine a pipeline that first extracts text from an image, then summarizes that text, and finally translates the summary into French.

```plx
[pipe.extract_text_from_image]
type = "PipeOcr"
definition = "Extract text from an image"
output = "Text"
ocr_model = "mistral-ocr"

[pipe.summarize_text]
type = "PipeLLM"
definition = "Summarize text"
inputs = { text = "Text" }
output = "Text"

[pipe.translate_to_french]
type = "PipeLLM"
definition = "Translate text to French"
inputs = { text = "Text" }
output = "Text"


[pipe.image_to_french_summary]
type = "PipeSequence"
definition = "Extract, summarize, and translate text from an image"
inputs = { image = "source.Image" }
output = "target.FrenchText"
steps = [
    { pipe = "extract_text_from_image", result = "extracted_text" },
    { pipe = "summarize_text", result = "english_summary" },
    { pipe = "translate_to_french", result = "french_summary" },
]
```