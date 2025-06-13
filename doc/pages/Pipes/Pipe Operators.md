# Pipe Operators

Pipe operators are the core processing units in Pipelex. Each operator type specializes in a specific kind of task, from LLM interactions to data transformations.

## Available Operators

### PipeLLM

The most common operator, used for LLM-based text generation and processing.

```toml
domain = "story_generation"
system_prompt = "You are a creative writing assistant."

[pipe.example_llm]
PipeLLM = "Description of what this pipe does"
inputs = { context = "native.Text" }             # Optional: input parameters: { name_of_the_input: "domain.concept_code" }
output = "native.Text"                           # Required: output type: "domain.concept_code"
llm = "llm_preset_name"                          # Optional: { llm_handle = "model", temperature = 0.7, max_tokens = "auto" }
system_prompt = "Override domain prompt"         # Optional: override domain system prompt
prompt_template = """Your prompt here"""         # Required: the prompt template
```

**Key Parameters:**
- `inputs`: Dictionary of input parameters and their types.
All the inputs referenced here must be used in the prompt_template, and vice versa.
- `output`: The output type (must be a defined concept)
- `llm`: Either a preset name or direct LLM configuration. See more in our [LLM Configuration Guide](../LLM-Configuration/llm-configuration.md). The default value is defined in the config file `pipelex.toml`: `llm_handle = "gpt-4o-mini"`. 
- `prompt_template`: The prompt template to use
- `system_prompt`: Optional override of domain system prompt

### PipeSequence

Chains multiple pipes together in sequence, one step after the other.

```toml
domain = "document_processing"
description = "Document analysis and transformation"

[pipe.example_sequence]
PipeSequence = "Description of the sequence"
inputs = { input1 = "Type1", input2 = "domain.concept_code" } 
output = "domain.concept_code"
steps = [
  { pipe = "pipe_code1", result = "result_pipe_1" },
  { pipe = "pipe_code2", result = "result_pipe_2" },
]
```

Pipe sequence enables you to chain sequence of pipes, but also to batch pipes in parallel.
The batch can be applied on `ListContents` stuffs. Reference the field `my_list_field` in your structured output that is a `ListContent` stuff. And run the `pipe_code3` in parallel for each item in the list:

```toml
[pipe.example_sequence]
PipeSequence = "Description of the sequence"
inputs = { input1 = "Type1", input2 = "domain.concept_code" } 
output = "domain.concept_code"
steps = [
  { pipe = "pipe_code1", result = "result_pipe_1" },
  { pipe = "pipe_code2", result = "result_pipe_2" },
  { pipe = "pipe_code3", batch_over = "my_list", batch_as = "item", result = "result_pipe_3" },
]
```

- `batch_over`: The name of the list field you want to process
- `batch_as`: The name to use for each item in your prompt template

**Key Parameters:**
- `inputs`: Dictionary of input parameters and their types
- `output`: The output type (must be a defined concept)
- `steps`: List of steps to execute in sequence, where each step has:
  - `pipe`: (Required) The pipe_code of the pipe to execute. This references an existing pipe defined elsewhere in your library
  - `result`: (Optional) The name given to the output stuff that will be stored in the working memory. This stuff will be available for subsequent pipes to use. Defaults to "main_stuff" if not specified

See more in our [PipeSequence documentation](../Pipes/PipeSequence.md)

### PipeOcr

Processes images using Optical Character Recognition within the domain context.

```toml
[pipe.extract_page_contents_from_pdf]
PipeOcr = "Extract page contents from a PDF document"
inputs = { pdf = "native.PDF" }
output = "PageContent"
page_images = true                # Extract images found in the document
page_views = false               # Don't generate page screenshots
page_image_captions = false      # Don't generate captions for extracted images
```

PipeOcr can process images and pdf. The input needs to be a path, either locally or online. 

Fields:
- `inputs`: Can be either a PDF or an image path (local or URL)
- `output`: Always the concept `documents.PageContent`. Indeed, the output of the PipeOcr contains a list of pages, each page containing a list of images and a list of texts. See the definition of PageContent here: [documents.toml](https://github.com/Pipelex/pipelex/blob/9ca4e6b18aad67af1a2053806f4add03c2f44dd0/pipelex/core/stuff_content.py#L516)
- `page_images`: If true, the output will include any images found in the document (graphs, images etc...)
- `page_views`: If true, the output will provide screenshots of each page
- `page_image_captions`: If true, the OCR will generate descriptive captions for any images it extracts. Note: This feature may not be available for all OCR providers (for example, it's not currently implemented for Mistral OCR)
- `page_views_dpi`: The DPI (dots per inch) quality setting for page view screenshots
- `ocr_platform`: The OCR provider to use (Supports only mistral for now)
- `ocr_config`: Additional configuration options specific to the chosen OCR platform

See more in our [PipeOcr documentation](../Pipes/PipeOcr.md)

## Related Topics

- [Pipes Documentation](../Pipes/Pipes.md)
- [Concepts Documentation](../Concepts/Concepts.md)
- [Libraries Documentation](../Libraries/libraries.md)
- [Domains Guide](../Domains/domains.md)

---

"Pipelex" is a trademark of Evotis S.A.S.

© 2025 Evotis S.A.S.
