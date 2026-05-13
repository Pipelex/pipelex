---
title: "PipeLLM Operator"
description: "PipeLLM is Pipelex's core operator for calling LLMs — supports text generation, summarization, classification, structured outputs, vision models, and document processing."
---

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

```toml
[pipe.describe_image]
type = "PipeLLM"
description = "Describe an image"
inputs = { image = "Image" }
output = "VisualDescription"
prompt = """
Describe the provided image in great detail: $image
"""
```

!!! important "Image Variable Tagging"
    It is necessary to tag image variables with `@image` or `$image`, just like with regular objects. This works in both `prompt` and `system_prompt`.

**Flexible Image Inputs**

You can use any concept that refines `Image` as an input, and choose descriptive variable names that fit your use case:

```toml
[pipe.analyze_wedding]
type = "PipeLLM"
description = "Analyze wedding photo"
inputs = { wedding_photo = "Photo" }
output = "PhotoAnalysis"
prompt = """
Analyze this wedding photo and describe the key moments captured: $wedding_photo
"""
```

### Images as Sub-attributes of Structured Content

When working with structured content that contains image fields (like `PageContent` which has a `page_view` field), you need to specify the full path to the image attribute in the `inputs` section:

```toml
[pipe.analyze_page_view]
type = "PipeLLM"
description = "Analyze the visual layout of a page"
inputs = { "page_content.page_view" = "Image" }
output = "LayoutAnalysis"
prompt = """
Analyze the visual layout and design elements of this page: $page_content.page_view
Focus on typography, spacing, and overall composition.
"""
```

In this example:

- `page_content` is the input variable containing a `PageContent` object
- `page_view` is the `ImageContent` field within the `PageContent` structure
- The dot notation `page_content.page_view` tells Pipelex to extract the image from that specific field

### Multiple Images

You can include multiple images in a single prompt by listing them in the inputs:

```toml
[pipe.compare_images]
type = "PipeLLM"
description = "Compare two images"
inputs = { 
    first_image = "Image",
    second_image = "Image"
}
output = "ImageComparison"
prompt = """
Compare these two images and describe their similarities and differences: $first_image and $second_image
"""
```

### Combining Text and Image Inputs

You can mix any stuff and image inputs in the same pipe:

```toml
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

Analyze the document page shown in the image and explain how it relates to the provided context: $document.page_view
"""
```

## Working with Documents

`PipeLLM` supports including documents (PDFs, etc.) in prompts. Documents are passed to the LLM along with your text prompt, allowing the model to analyze their content.

### Basic Document Input

Documents must be declared in the `inputs` section of your pipe definition. The document will be automatically passed to the LLM along with your text prompt.

```toml
[pipe.summarize_document]
type = "PipeLLM"
description = "Summarize a document"
inputs = { document = "Document" }
output = "DocumentSummary"
prompt = """
Summarize the key points from this document: @document
"""
```

!!! important "Document Variable Tagging"
    It is necessary to tag document variables with `@document` or `$document`, just like with regular objects. This works in both `prompt` and `system_prompt`.

**Flexible Document Inputs**

You can use any concept that refines `Document` as an input, and choose descriptive variable names that fit your use case:

```toml
[concept.FinancialReport]
description = "A financial report"
refines = "Document"

[pipe.analyze_report]
type = "PipeLLM"
description = "Analyze financial report"
inputs = { financial_report = "FinancialReport" }
output = "ReportAnalysis"
prompt = """
Analyze this financial report and extract the key metrics: $financial_report
"""
```

### Multiple Documents

You can include multiple documents in a single prompt by listing them in the inputs:

```toml
[pipe.compare_documents]
type = "PipeLLM"
description = "Compare two documents"
inputs = { first_doc = "Document", second_doc = "Document" }
output = "DocumentComparison"
prompt = """
Compare these two documents and describe their similarities and differences: $first_doc and $second_doc
"""
```

For a variable number of documents, use the list syntax:

```toml
[pipe.merge_documents]
type = "PipeLLM"
description = "Merge multiple documents"
inputs = { documents = "Document[]" }
output = "MergedContent"
prompt = """
Combine the information from all these documents into a single coherent summary: $documents
"""
```

### Combining Text, Images, and Documents

You can mix text, image, and document inputs in the same pipe:

```toml
[pipe.analyze_with_context]
type = "PipeLLM"
description = "Analyze a document with context"
inputs = {
    context = "Text",
    screenshot = "Image",
    reference_doc = "Document"
}
output = "ContextualAnalysis"
prompt = """
Given this context: $context

And this screenshot for reference: $screenshot

Analyze the document and explain how it relates to the context: $reference_doc
"""
```

## Configuration

`PipeLLM` is configured in your pipeline's `.mthds` file.

### MTHDS Parameters

| Parameter                   | Type                | Description                                                                                                                                                                  | Required |
| --------------------------- | ------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | -------- |
| `type`                      | string              | The type of the pipe: `PipeLLM`                                                                          | Yes      |
| `description`               | string              | A description of the LLM operation.                                                                           | Yes      |
| `inputs`                    | dictionary          | The input concept(s) for the LLM operation, as a dictionary mapping input names to concept codes. For images within structured content, use dot notation (e.g., `"page.image_argurment"`)
| `output`                    | string              | The output concept produced by the LLM operation with multiplicity notation using brackets (e.g., `"Text"`, `"Text[]"`, `"Text[3]"`).                                                | Yes      |
| `model`                       | string or table     | Specifies the LLM choice by name, setting, or preset to use.              | No       |
| `model_to_structure`                       | string or table     | Specifies the LLM choice by name, setting, or preset to use for structuring after preliminary text generation.              | No       |
| `system_prompt`             | string              | A system-level prompt to guide the LLM's behavior (e.g., "You are a helpful assistant"). Supports the same variable syntax as `prompt`, including image and document references.  | No       |
| `prompt`           | string              | A template for the user prompt. Use `$` for inline variables (e.g., `$topic`) and `@` to insert the content of an entire input (e.g., `@text_to_summarize`). Image and document variables should also be tagged with `$` or `@`. Escape with `@@` or `$$` to emit a literal `@` or `$` (e.g., `@@font-face` inside a `<style>` block). | No       |
| `structuring_method`        | string              | The method for generating structured output. Can be `direct` or `preliminary_text`. Defaults to the global configuration.                                                      | No       |

### LLM Setting Fields

When `model` is specified as a table (inline LLM setting), it accepts the following fields:

| Field | Type | Description |
|-------|------|-------------|
| `model` | string | Model name or alias (e.g., `"claude-4.5-sonnet"`, `"@default-premium"`) |
| `temperature` | float | Sampling temperature (0.0 – 1.0) |
| `max_tokens` | integer | Maximum output tokens |
| `reasoning_effort` | string | Reasoning depth: `"none"`, `"minimal"`, `"low"`, `"medium"`, `"high"`, `"max"`. Not supported for structured generation. |
| `reasoning_budget` | integer | Explicit token budget for reasoning. Mutually exclusive with `reasoning_effort`. Supported by Anthropic and Google only. |
| `description` | string | Human-readable description (for presets) |

!!! tip "More on Reasoning"
    For provider-specific behavior and model-specific examples, see [Reasoning Controls](../../../under-the-hood/reasoning-controls.md).

### Output Multiplicity

Specify output multiplicity using bracket notation in the `output` field:

- **Single output** (default): `output = "Text"` - generates exactly one item
- **Variable output**: `output = "Text[]"` - lets the LLM decide how many items to generate
- **Fixed output**: `output = "Text[5]"` - generates exactly 5 items

Examples:

```toml
# Single output (default)
output = "Summary"

# Variable - extract all keywords found
output = "Keyword[]"

# Fixed - generate exactly 3 alternatives
output = "Headline[3]"
```

!!! info "Learn More About Multiplicity"
    For a comprehensive guide on output multiplicity, input multiplicity, and the philosophy behind how Pipelex handles single items versus collections, see [Understanding Multiplicity](../understanding-multiplicity.md).

## Examples

### Simple Text Generation Example

This pipe takes no input and writes a poem.

```toml
[pipe.write_poem]
type = "PipeLLM"
description = "Write a short poem"
output = "Text"
model = "$writing-creative"
prompt = """
Write a four-line poem about pipes.
"""
```

### Text-to-Text Example

This pipe summarizes an input text, using a `prompt` to inject the input.

```toml
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

```toml
[pipe.extract_table_from_image]
type = "PipeLLM"
description = "Extract table data from an image"
inputs = { image = "TableScreenshot" }
output = "TableData"
prompt = """
Extract the table data from this image and format it as a structured table: $image
"""
```

### Structured Data Extraction Example

This pipe extracts a list of `Expense` items from a block of text.

```toml
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

### Reasoning Example

This pipe uses extended reasoning to analyze a complex topic in depth:

```toml
[pipe.deep_analysis]
type = "PipeLLM"
description = "Analyze a complex topic with extended reasoning"
inputs = { topic = "Text" }
output = "Analysis"
model = { model = "claude-4.5-sonnet", temperature = 0.1, reasoning_effort = "high" }
prompt = """
Analyze the following topic in depth, considering multiple perspectives:

@topic
"""
```

You can also reference a reasoning preset:

```toml
[pipe.deep_analysis]
type = "PipeLLM"
description = "Analyze a complex topic with extended reasoning"
inputs = { topic = "Text" }
output = "Analysis"
model = "$deep-analysis"
prompt = """
Analyze the following topic in depth, considering multiple perspectives:

@topic
"""
```

## Related Documentation

- [Hello World Example](../../../cookbook/hello-world.md) - Simple introductory example using PipeLLM
- [Invoice Extraction Example](../../../cookbook/extract-invoice.md) - Complete invoice processing pipeline
- [Write Tweet Example](../../../cookbook/write-tweet.md) - Multi-step tweet generation workflow
- [Table Extraction Example](../../../cookbook/extract-table.md) - Extract and correct tables from images
- [Gantt Extraction Example](../../../cookbook/extract-gantt.md) - Extract Gantt chart data from documents