# PipeLLM

`PipeLLM` is the core operator in Pipelex for leveraging Large Language Models (LLMs). It can be used for a wide range of tasks, including text generation, summarization, classification, and structured data extraction.

## How it works

At its core, `PipeLLM` constructs a detailed prompt from various inputs and templates, sends it to a specified LLM, and processes the output. It can produce simple text or complex structured data (in the form of Pydantic models).

For structured data output, `PipeLLM` employs two main strategies:

1.  **Direct Mode**: The LLM is prompted to directly generate a JSON object that conforms to the target Pydantic model's schema. This is fast but relies on the LLM's ability to generate well-formed JSON.
2.  **Preliminary Text Mode**: This is a more robust two-step process:
    a. First, the LLM generates a free-form text based on the initial prompt.
    b. Second, another LLM call is made with a specific prompt designed to extract and structure the information from the generated text into the target Pydantic model.

## Configuration

`PipeLLM` is configured in your pipeline's `.toml` file.

### TOML Parameters

| Parameter                   | Type                | Description                                                                                                                                                                  | Required |
| --------------------------- | ------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | -------- |
| `PipeLLM`                   | string              | A descriptive name for the LLM operation.                                                                           | Yes      |
| `inputs`                    | dictionary          | The input concept(s) for the LLM operation, as a dictionary mapping input names to concept codes.                                                     | Yes       |
| `output`                    | string              | The output concept produced by the LLM operation.                                                | Yes      |
| `llm`                       | string or table     | Specifies the LLM preset(s) to use. Can be a single preset or a table mapping different presets for different generation modes (e.g., `main`, `object_direct`).              | No       |
| `system_prompt`             | string              | A system-level prompt to guide the LLM's behavior (e.g., "You are a helpful assistant"). Can be inline text or a reference to a template file (`"file:path/to/prompt.md"`).  | No       |
| `prompt`                    | string              | A simple, static user prompt. Use this when you don't need to inject any variables.                                                                                          | No       |
| `prompt_template`           | string              | A template for the user prompt. Use `$` for inline variables (e.g., `$topic`) and `@` to insert the content of an entire input (e.g., `@text_to_summarize`).                 | No       |
| `images`                    | list of strings     | For Vision Language Models (VLMs), specifies which input variables are images.                                                                                               | No       |
| `structuring_method`        | string              | The method for generating structured output. Can be `direct` or `preliminary_text`. Defaults to the global configuration.                                                      | No       |
| `prompt_template_to_structure` | string           | The prompt template for the second step in `preliminary_text` mode.                                                                                                            | No       |
| `output_multiplicity`       | string or integer   | Defines the number of outputs. Use `"list"` for a variable-length list, or an integer (e.g., `3`) for a fixed-size list.                                                       | No       |


### Simple Text Generation Example

This pipe takes no input and writes a poem.

```toml
[pipe.write_poem]
PipeLLM = "Write a short poem"
output = "Text"
llm = "llm_for_creative_writing"
prompt = """
Write a four-line poem about pipes.
"""
```

### Text-to-Text Example

This pipe summarizes an input text, using a `prompt_template` to inject the input.

```toml
[pipe.summarize_text]
PipeLLM = "Summarize a text"
inputs = { text = "TextToSummarize" }
output = "TextSummary"
prompt_template = """
Please provide a concise summary of the following text:

@text

The summary should be no longer than 3 sentences.
"""
```

### Vision (VLM) Example

This pipe takes an image of a table and uses a VLM to extract the content as an HTML table.

```toml
[pipe.extract_table_from_image]
PipeLLM = "Extract table data from an image"
inputs = { image = "TableScreenshot" }
output = "TableData"
images = ["image"]
prompt_template = """
Extract the table data from this image and format it as a structured table.
"""
```

### Structured Data Extraction Example

This pipe extracts a list of `Expense` items from a block of text.

```toml
[concept.Expense]
structure = "Expense" # Assumes a Pydantic model 'Expense' is defined

[pipe.process_expense_report]
PipeLLM = "Process an expense report"
inputs = { report = "ExpenseReport" }
output = "ProcessedExpenseReport"
prompt_template = """
Analyze this expense report and extract the following information:
- Total amount
- Date
- Vendor
- Category
- Line items

@report
"""
```

In this example, `Pipelex` will instruct the LLM to return a list of objects that conform to the `Expense` structure.
