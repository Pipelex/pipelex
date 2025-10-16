# PipeLLM

`PipeLLM` is the core operator in Pipelex for leveraging Large Language Models (LLMs). It can be used for a wide range of tasks, including text generation, summarization, classification, and structured data extraction.

## How it works

At its core, `PipeLLM` constructs a detailed prompt from various inputs and templates, sends it to a specified LLM, and processes the output. It can produce simple text or complex structured data (in the form of Pydantic models).

For structured data output, `PipeLLM` employs two main strategies:

1.  **Direct Mode**: The LLM is prompted to directly generate a JSON object that conforms to the target Pydantic model's schema. This is fast but relies on the LLM's ability to generate well-formed JSON.
2.  **Preliminary Text Mode**: This is a more robust two-step process:
    a. First, the LLM generates a free-form text based on the initial prompt.
    b. Second, another LLM call is made with a specific prompt designed to extract and structure the information from the generated text into the target Pydantic model.

## Working with Images (Vision Language Models)

`PipeLLM` supports Vision Language Models (VLMs) that can process both text and images. To use images in your prompts:

### Basic Image Input

Images must be declared in the `inputs` section of your pipe definition. The image will be automatically passed to the VLM along with your text prompt.

```plx
[pipe.describe_image]
type = "PipeLLM"
description = "Describe an image"
inputs = { image = "Image" }
output = "VisualDescription"
prompt = """
Describe the provided image in great detail.
"""
```

**Important**: Do NOT reference image variables in your prompt template using `@image` or `$image`. Images are automatically passed to vision-enabled LLMs and should not be treated as text variables.

**Flexible Image Inputs**

You can use any concept that refines `Image` as an input, and choose descriptive variable names that fit your use case:

```plx
[pipe.analyze_wedding]
type = "PipeLLM"
description = "Analyze wedding photo"
inputs = { wedding_photo = "Photo" }
output = "PhotoAnalysis"
prompt = """
Analyze this wedding photo and describe the key moments captured.
"""
```

### Images as Sub-attributes of Structured Content

When working with structured content that contains image fields (like `PageContent` which has a `page_view` field), you need to specify the full path to the image attribute in the `inputs` section:

```plx
[pipe.analyze_page_view]
type = "PipeLLM"
description = "Analyze the visual layout of a page"
inputs = { "page_content.page_view" = "Image" }
output = "LayoutAnalysis"
prompt = """
Analyze the visual layout and design elements of this page.
Focus on typography, spacing, and overall composition.
"""
```

In this example:
- `page_content` is the input variable containing a `PageContent` object
- `page_view` is the `ImageContent` field within the `PageContent` structure
- The dot notation `page_content.page_view` tells Pipelex to extract the image from that specific field

### Multiple Images

You can include multiple images in a single prompt by listing them in the inputs:

```plx
[pipe.compare_images]
type = "PipeLLM"
description = "Compare two images"
inputs = { 
    first_image = "Image",
    second_image = "Image"
}
output = "ImageComparison"
prompt = """
Compare these two images and describe their similarities and differences.
"""
```

### Combining Text and Image Inputs

You can mix any stuff and image inputs in the same pipe:

```plx
[pipe.analyze_document_with_context]
type = "PipeLLM"
description = "Analyze a document page with additional context"
inputs = { 
    context = "Text",
    document.page_view = "Image"
}
output = "DocumentAnalysis"
prompt = """
Given this context: $context

Analyze the document page shown in the image and explain how it relates to the provided context.
"""
```

## Configuration

`PipeLLM` is configured in your pipeline's `.plx` file.

### PLX Parameters

| Parameter                   | Type                | Description                                                                                                                                                                  | Required |
| --------------------------- | ------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | -------- |
| `type`                      | string              | The type of the pipe: `PipeLLM`                                                                          | Yes      |
| `description`               | string              | A description of the LLM operation.                                                                           | Yes      |
| `inputs`                    | dictionary          | The input concept(s) for the LLM operation, as a dictionary mapping input names to concept codes. For images within structured content, use dot notation (e.g., `"page.image_argurment"`)
| `output`                    | string              | The output concept produced by the LLM operation.                                                | Yes      |
| `llm`                       | string or table     | Specifies the LLM preset(s) to use. Can be a single preset or a table mapping different presets for different generation modes (e.g., `main`, `object_direct`).              | No       |
| `system_prompt`             | string              | A system-level prompt to guide the LLM's behavior (e.g., "You are a helpful assistant"). Can be inline text or a reference to a template file (`"file:path/to/prompt.md"`).  | No       |
| `prompt`                    | string              | A simple, static user prompt. Use this when you don't need to inject any variables.                                                                                          | No       |
| `prompt_template`           | string              | A template for the user prompt. Use `$` for inline variables (e.g., `$topic`) and `@` to insert the content of an entire input (e.g., `@text_to_summarize`). **Note**: Do not use `@` or `$` for image variables.                 | No       |
| `images`                    | list of strings     | **Deprecated**: Use the `inputs` section to declare image inputs instead.                                                                                               | No       |
| `structuring_method`        | string              | The method for generating structured output. Can be `direct` or `preliminary_text`. Defaults to the global configuration.                                                      | No       |
| `nb_output`                 | integer             | Specifies exactly how many outputs to generate (e.g., `nb_output = 3` for exactly 3 outputs). Use when you need a fixed number of results. Mutually exclusive with `multiple_output`.  | No       |
| `multiple_output`           | boolean             | Controls output generation mode. Default is `false` (single output). Set to `true` for variable-length list generation when you need an indeterminate number of outputs. Mutually exclusive with `nb_output`. | No       |

### Output Generation Modes

`PipeLLM` supports three different output generation modes:

1. **Single Output** (default): Don't specify `nb_output` or `multiple_output`, or set `multiple_output = false`. The LLM generates exactly one result.

2. **Fixed Multiple Outputs**: Use `nb_output = N` (where N is a positive integer) when you need exactly N outputs. For example, `nb_output = 3` will try to generate 3 results. The parameter `_nb_output` will be available in the prompt template, e.g. "Give me the names of $_nb_output flowers".

3. **Variable Multiple Outputs**: Use `multiple_output = true` when you need a variable-length list where the LLM determines how many outputs to generate based on the content and context.

## Examples

### Simple Text Generation Example

This pipe takes no input and writes a poem.

```plx
[pipe.write_poem]
type = "PipeLLM"
description = "Write a short poem"
output = "Text"
model = "llm_for_creative_writing"
prompt = """
Write a four-line poem about pipes.
"""
```

### Text-to-Text Example

This pipe summarizes an input text, using a `prompt_template` to inject the input.

```plx
[pipe.summarize_text]
type = "PipeLLM"
description = "Summarize a text"
inputs = { text = "TextToSummarize" }
output = "TextSummary"
prompt = """
Please provide a concise summary of the following text:

@text

The summary should be no longer than 3 sentences.
"""
```

### Vision (VLM) Example

This pipe takes an image of a table and uses a VLM to extract the content as an HTML table.

```plx
[pipe.extract_table_from_image]
type = "PipeLLM"
description = "Extract table data from an image"
inputs = { image = "TableScreenshot" }
output = "TableData"
prompt = """
Extract the table data from this image and format it as a structured table.
"""
```

### Structured Data Extraction Example

This pipe extracts a list of `Expense` items from a block of text.

```plx
[concept.Expense]
structure = "Expense" # Assumes a Pydantic model 'Expense' is defined

[pipe.process_expense_report]
type = "PipeLLM"
description = "Process an expense report"
inputs = { report = "ExpenseReport" }
output = "ProcessedExpenseReport"
prompt = """
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