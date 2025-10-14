# Guide to write or edit pipelines using the Pipelex language in .plx files

- Always first write your "plan" in natural language, then transcribe it in pipelex.
- You should ALWAYS RUN the terminal command `make validate` when you are writing or editing a `.plx` file. It will ensure the pipe is runnable. If not, iterate.
- Please use POSIX standard for files. (empty lines, no trailing whitespaces, etc.)

## Pipeline File Naming
- Files must be `.plx` for pipelines (Always add an empty line at the end of the file, and do not add trailing whitespaces to PLX files at all)
- Files must be `.py` for code defining the data structures
- Use descriptive names in `snake_case`

## Pipeline File Outline
A pipeline file has three main sections:
1. Domain statement
2. Concept definitions
3. Pipe definitions

### Domain Statement
```plx
domain = "domain_name"
description = "Description of the domain" # Optional
```
Note: The domain name usually matches the plx filename for single-file domains. For multi-file domains, use the subdirectory name.

### Concept Definitions

Concepts represent ideas and semantic entities in your pipeline. They define what something *is*, not how it's structured.

```plx
[concept]
ConceptName = "Description of the concept"
```

**Naming Rules:**
- Use PascalCase for concept names
- Never use plurals (no "Stories", use "Story") - lists are handled implicitly by Pipelex
- Avoid circumstantial adjectives (no "LargeText", use "Text") - focus on the essence of what the concept represents
- Don't redefine native concepts (Text, Image, PDF, TextAndImages, Number, Page)

**Native Concepts:**
Pipelex provides built-in native concepts: `Text`, `Image`, `PDF`, `TextAndImages`, `Number`, `Page`. Use these directly or refine them when appropriate.

**Refining Native Concepts:**
To create a concept that specializes a native concept without adding fields:

```plx
[concept.Landscape]
description = "A scenic outdoor photograph"
refines = "Image"
```

For details on how to structure concepts with fields, see the "Structuring Models" section below.

### Pipe Definitions

## Pipe Base Definition

```plx
[pipe.your_pipe_name]
type = "PipeLLM"
description = "A description of what your pipe does"
inputs = { input_1 = "ConceptName1", input_2 = "ConceptName2" }
output = "ConceptName"
```

The pipes will all have at least this base definition. 
- `inputs`: Dictionary of key being the variable used in the prompts, and the value being the ConceptName. It should ALSO LIST THE INPUTS OF THE INTERMEDIATE STEPS (if PipeSequence) or of the conditional pipes (if PipeCondition).
So If you have this error:
`StaticValidationError: missing_input_variable • domain='expense_validator' • pipe='validate_expense' • 
variable='['invoice']'``
That means that the pipe validate_expense is missing the input `invoice` because one of the subpipe is needing it.

NEVER WRITE THE INPUTS BY BREAKING THE LINE LIKE THIS:
<NEVER DO THIS>
```plx
inputs = {
    input_1 = "ConceptName1",
    input_2 = "ConceptName2"
}
```
</NEVER DO THIS>

- `output`: The name of the concept to output. The `ConceptName` should have the same name as the python class if you want structured output:

## Structuring Models

Once you've defined your concepts semantically (see "Concept Definitions" above), you need to specify their structure if they have fields.

### Three Ways to Structure Concepts

**1. No Structure Needed**

If a concept only refines a native concept without adding fields, use the TOML table syntax shown in "Concept Definitions" above. No structure section is needed.

**2. Inline Structure Definition (RECOMMENDED for most cases)**

For concepts with structured fields, define them inline using TOML syntax:

```plx
[concept.Invoice]
description = "A commercial document issued by a seller to a buyer"

[concept.Invoice.structure]
invoice_number = "The unique invoice identifier"
issue_date = { type = "date", description = "The date the invoice was issued", required = true }
total_amount = { type = "number", description = "The total invoice amount", required = true }
vendor_name = "The name of the vendor"
line_items = { type = "list", item_type = "text", description = "List of items", required = false }
```

**Supported inline field types:** `text`, `integer`, `boolean`, `number`, `date`, `list`, `dict`

**Field properties:** `type`, `description`, `required` (default: true), `default_value`, `choices`, `item_type` (for lists), `key_type` and `value_type` (for dicts)

**Simple syntax** (creates required text field):
```plx
field_name = "Field description"
```

**Detailed syntax** (with explicit properties):
```plx
field_name = { type = "text", description = "Field description", required = false, default_value = "default" }
```

**3. Python StructuredContent Class (For Advanced Features)**

Create a Python class when you need:
- Custom validation logic (@field_validator, @model_validator)
- Computed properties (@property methods)
- Custom methods or class methods
- Complex cross-field validation
- Reusable structures across multiple domains

```python
from pipelex.core.stuffs.structured_content import StructuredContent
from pydantic import Field, field_validator

class Invoice(StructuredContent):
    """A commercial invoice with validation."""
    
    invoice_number: str = Field(description="The unique invoice identifier")
    total_amount: float = Field(ge=0, description="The total invoice amount")
    tax_amount: float = Field(ge=0, description="Tax amount")
    
    @field_validator('tax_amount')
    @classmethod
    def validate_tax(cls, v, info):
        """Ensure tax doesn't exceed total."""
        total = info.data.get('total_amount', 0)
        if v > total:
            raise ValueError('Tax amount cannot exceed total amount')
        return v
```

**Location:** Create models in `my_project/some_domain/some_domain_struct.py`. Classes inheriting from `StructuredContent` are automatically discovered.

### Decision Rules for Agents

**If concept already exists:**
- If it's already inline → KEEP IT INLINE unless user explicitly asks to convert or features require Python class
- If it's already a Python class → KEEP IT as Python class

**If creating new concept:**
1. Does it only refine a native concept without adding fields? → Use concept-only declaration
2. Does it need custom validation, computed properties, or methods? → Use Python class
3. Otherwise → Use inline structure (fastest and simplest)

**When to suggest conversion to Python class:**
- User needs validation logic beyond type checking
- User needs computed properties or custom methods
- Structure needs to be reused across multiple domains
- Complex type relationships or inheritance required

### Inline Structure Limitations

Inline structures:
- ✅ Support all common field types (text, number, date, list, dict, etc.)
- ✅ Support required/optional fields, defaults, choices
- ✅ Generate full Pydantic models with validation
- ❌ Cannot have custom validators or complex validation logic
- ❌ Cannot have computed properties or custom methods
- ❌ Cannot refine custom (non-native) concepts
- ❌ Limited IDE autocomplete compared to explicit Python classes


## Pipe Controllers and Pipe Operators

Look at the Pipes we have in order to adapt it. Pipes are organized in two categories:

1. **Controllers** - For flow control:
   - `PipeSequence` - For creating a sequence of multiple steps
   - `PipeCondition` - If the next pipe depends of the expression of a stuff in the working memory
   - `PipeParallel` - For parallelizing pipes

2. **Operators** - For specific tasks:
   - `PipeLLM` - Generate Text and Objects (include Vision LLM)
   - `PipeExtract` - Extract text and images from an image or a PDF
   - `PipeCompose` - For composing text using Jinja2 templates: supports html, markdown, mermaid, etc.
   - `PipeImgGen` - Generate Images
   - `PipeFunc` - For running classic python scripts

## PipeSequence controller

Purpose: PipeSequence executes multiple pipes in a defined order, where each step can use results from original inputs or from previous steps.

### Basic Definition
```plx
[pipe.your_sequence_name]
type = "PipeSequence"
description = "Description of what this sequence does"
inputs = { input_name = "InputType" } # All the inputs of the sub pipes, except the ones generated by intermediate steps
output = "OutputType"
steps = [
    { pipe = "first_pipe", result = "first_result" },
    { pipe = "second_pipe", result = "second_result" },
    { pipe = "final_pipe", result = "final_result" }
]
```

### Key Components

1. **Steps Array**: List of pipes to execute in sequence
   - `pipe`: Name of the pipe to execute
   - `result`: Name to assign to the pipe's output that will be in the working memory

### Using PipeBatch in Steps

You can use PipeBatch functionality within steps using `batch_over` and `batch_as`:

```plx
steps = [
    { pipe = "process_items", batch_over = "input_list", batch_as = "current_item", result = "processed_items"
    }
]
```

1. **batch_over**: Specifies a `ListContent` field to iterate over. Each item in the list will be processed individually and IN PARALLEL by the pipe.
   - Must be a `ListContent` type containing the items to process
   - Can reference inputs or results from previous steps

2. **batch_as**: Defines the name that will be used to reference the current item being processed
   - This name can be used in the pipe's input mappings
   - Makes each item from the batch available as a single element

The result of a batched step will be a `ListContent` containing the outputs from processing each item.

## PipeCondition controller

The PipeCondition controller allows you to implement conditional logic in your pipeline, choosing which pipe to execute based on an evaluated expression. It supports both direct expressions and expression templates.

### Basic usage

```plx
[pipe.conditional_operation]
type = "PipeCondition"
description = "A conditional pipe to decide whether..."
inputs = { input_data = "CategoryInput" }
output = "native.Text"
expression = "input_data.category"
default_outcome = "process_medium"

[pipe.conditional_operation.outcomes]
small = "process_small"
medium = "process_medium"
large = "process_large"
```
or
```plx
[pipe.conditional_operation]
type = "PipeCondition"
description = "A conditional pipe to decide whether..."
inputs = { input_data = "CategoryInput" }
output = "native.Text"
expression_template = "{{ input_data.category }}" # Jinja2 code
default_outcome = "process_medium"

[pipe.conditional_operation.outcomes]
small = "process_small"
medium = "process_medium"
large = "process_large"
```

### Key Parameters

- `expression`: Direct boolean or string expression (mutually exclusive with expression_template)
- `expression_template`: Jinja2 template for more complex conditional logic (mutually exclusive with expression)
- `outcomes`: Dictionary mapping expression results to pipe codes:
  1. The key on the left (`small`, `medium`) is the result of `expression` or `expression_template`
  2. The value on the right (`process_small`, `process_medium`, etc.) is the name of the pipe to trigger
- `default_outcome`: **Required** - The pipe to execute if the expression doesn't match any key in outcomes. Use `"fail"` if you want the pipeline to fail when no match is found

Example with fail as default:
```plx
[pipe.strict_validation]
type = "PipeCondition"
description = "Validate with strict matching"
inputs = { status = "Status" }
output = "Text"
expression = "status.value"
default_outcome = "fail"

[pipe.strict_validation.outcomes]
approved = "process_approved"
rejected = "process_rejected"
```

## PipeLLM operator

PipeLLM is used to:
1. Generate text or objects with LLMs
2. Process images with Vision LLMs

### Basic Usage

Simple Text Generation:
```plx
[pipe.write_story]
type = "PipeLLM"
description = "Write a short story"
output = "Text"
prompt = """
Write a short story about a programmer.
"""
```

Structured Data Extraction:
```plx
[pipe.extract_info]
type = "PipeLLM"
description = "Extract information"
inputs = { text = "Text" }
output = "PersonInfo"
prompt = """
Extract person information from this text:
@text
"""
```

Supports system instructions:
```plx
[pipe.expert_analysis]
type = "PipeLLM"
description = "Expert analysis"
output = "Analysis"
system_prompt = "You are a data analysis expert"
prompt = "Analyze this data"
```

### Multiple Outputs

Generate multiple outputs (fixed number):
```plx
[pipe.generate_ideas]
type = "PipeLLM"
description = "Generate ideas"
output = "Idea"
nb_output = 3  # Generate exactly 3 ideas
```

Generate multiple outputs (variable number):
```plx
[pipe.generate_ideas]
type = "PipeLLM"
description = "Generate ideas"
output = "Idea"
multiple_output = true  # Let the LLM decide how many to generate
```

### Vision

Process images with VLMs (image inputs must be tagged in the prompt):
```plx
[pipe.analyze_image]
type = "PipeLLM"
description = "Analyze image"
inputs = { image = "Image" }
output = "ImageAnalysis"
prompt = """
Describe what you see in this image:

$image
"""
```

You can also reference images inline in meaningful sentences to guide the Visual LLM:
```plx
[pipe.compare_images]
type = "PipeLLM"
description = "Compare two images"
inputs = { photo = "Image", painting = "Image" }
output = "Analysis"
prompt = "Analyze the colors in $photo and the shapes in $painting."
```

### Writing prompts for PipeLLM

**Insert stuff inside a tagged block**

If the inserted text is supposedly a long text, made of several lines or paragraphs, you want it inserted inside a block, possibly a block tagged and delimlited with proper syntax as one would do in a markdown documentation. To include stuff as a block, use the "@" prefix.

Example template:
```plx
prompt = """
Match the expense with its corresponding invoice:

@expense

@invoices
"""
```
In the example above, the expense data and the invoices data are obviously made of several lines each, that's why it makes sense to use the "@" prefix in order to have them delimited inside a block. Note that our preprocessor will automatically include the block's title, so it doesn't need to be explicitly written in the prompt.

DO NOT write things like "Here is the expense: @expense".
DO write simply "@expense" alone in an isolated line.

**Insert stuff inline**

If the inserted text is short text and it makes sense to have it inserted directly into a sentence, you want it inserted inline. To insert stuff inline, use the "$" prefix. This will insert the stuff without delimiters and the content will be rendered as plain text.

Example template:
```plx
prompt = """
Your goal is to summarize everything related to $topic in the provided text:

@text

Please provide only the summary, with no additional text or explanations.
Your summary should not be longer than 2 sentences.
"""
```

In the example above, $topic will be inserted inline, whereas @text will be a a delimited block.
Be sure to make the proper choice of prefix for each insertion.

DO NOT write "$topic" alone in an isolated line.
DO write things like "Write an essay about $topic" to include text into an actual sentence.


## PipeExtract operator

The PipeExtract operator is used to extract text and images from an image or a PDF

### Simple Text Extraction
```plx
[pipe.extract_info]
type = "PipeExtract"
description = "extract the information"
inputs = { document = "PDF" } # or { image = "Image" } if it's an image. This is the only input.
output = "Page"
```

Using Extract Model Settings:
```plx
[pipe.extract_with_model]
type = "PipeExtract"
description = "Extract with specific model"
inputs = { document = "PDF" }
output = "Page"
model = "base_extract_mistral"  # Use predefined extract preset or model alias
```

Only one input is allowed and it must either be an `Image` or a `PDF`. The input can be named anything.

The output concept `Page` is a native concept, with the structure `PageContent`:
It corresponds to 1 page. Therefore, the PipeExtract is outputing a `ListContent` of `Page`

```python
class TextAndImagesContent(StuffContent):
    text: TextContent | None
    images: list[ImageContent] | None

class PageContent(StructuredContent): # CONCEPT IS "Page"
    text_and_images: TextAndImagesContent
    page_view: ImageContent | None = None
```
- `text_and_images` are the text, and the related images found in the input image or PDF.
- `page_view` is the screenshot of the whole pdf page/image.

## PipeCompose operator

The PipeCompose operator is used to compose text using Jinja2 templates. It supports various output formats including HTML, Markdown, Mermaid diagrams, and more.

### Basic Usage

Simple Template Composition:
```plx
[pipe.compose_report]
type = "PipeCompose"
description = "Compose a report using template"
inputs = { data = "ReportData" }
output = "Text"
template = """
# Report Summary

Based on the analysis:
$data

Generated on: {{ current_date }}
"""
```

Using Named Templates:
```plx
[pipe.use_template]
type = "PipeCompose"
description = "Use a predefined template"
inputs = { content = "Text" }
output = "Text"
template_name = "standard_report_template"
```

Using Nested Template Section (for more control):
```plx
[pipe.advanced_template]
type = "PipeCompose"
description = "Use advanced template settings"
inputs = { data = "ReportData" }
output = "Text"

[pipe.advanced_template.template]
template = "Report: $data"
category = "html"
templating_style = { tag_style = "square_brackets", text_format = "html" }
```

CRM Email Template:
```plx
[pipe.compose_follow_up_email]
type = "PipeCompose"
description = "Compose a personalized follow-up email for CRM"
inputs = { customer = "Customer", deal = "Deal", sales_rep = "SalesRep" }
output = "Text"
template_category = "html"
templating_style = { tag_style = "square_brackets", text_format = "html" }
template = """
Subject: Following up on our $deal.product_name discussion

Hi $customer.first_name,

I hope this email finds you well! I wanted to follow up on our conversation about $deal.product_name from $deal.last_contact_date.

Based on our discussion, I understand that your key requirements are: $deal.customer_requirements

I'm excited to let you know that we can definitely help you achieve your goals. Here's what I'd like to propose:

**Next Steps:**
- Schedule a demo tailored to your specific needs
- Provide you with a customized quote based on your requirements  
- Connect you with our implementation team

Would you be available for a 30-minute call this week? I have openings on:
{% for slot in available_slots %}
- {{ slot }}
{% endfor %}

Looking forward to moving this forward together!

Best regards,
$sales_rep.name
$sales_rep.title
$sales_rep.phone | $sales_rep.email
"""
```

### Key Parameters

- `template`: Inline template string (mutually exclusive with template_name)
- `template_name`: Name of a predefined template (mutually exclusive with template)
- `template_category`: Template type ("llm_prompt", "html", "markdown", "mermaid", etc.)
- `templating_style`: Styling options for template rendering
- `extra_context`: Additional context variables for template

For more control, you can use a nested `template` section instead of the `template` field:
- `template.template`: The template string
- `template.category`: Template type
- `template.templating_style`: Styling options

### Template Variables

Use the same variable insertion rules as PipeLLM:
- `@variable` for block insertion (multi-line content)
- `$variable` for inline insertion (short text)

## PipeImgGen operator

The PipeImgGen operator is used to generate images using AI image generation models.

### Basic Usage

Simple Image Generation:
```plx
[pipe.generate_image]
type = "PipeImgGen"
description = "Generate an image from prompt"
inputs = { prompt = "ImgGenPrompt" }
output = "Image"
```

Using Image Generation Settings:
```plx
[pipe.generate_photo]
type = "PipeImgGen"
description = "Generate a high-quality photo"
inputs = { prompt = "ImgGenPrompt" }
output = "Photo"
model = { model = "fast-img-gen" }
aspect_ratio = "16:9"
quality = "hd"
```

Multiple Image Generation:
```plx
[pipe.generate_variations]
type = "PipeImgGen"
description = "Generate multiple image variations"
inputs = { prompt = "ImgGenPrompt" }
output = "Image"
nb_output = 3
seed = "auto"
```

Advanced Configuration:
```plx
[pipe.generate_custom]
type = "PipeImgGen"
description = "Generate image with custom settings"
inputs = { prompt = "ImgGenPrompt" }
output = "Image"
model = "img_gen_preset_name"  # Use predefined preset
aspect_ratio = "1:1"
quality = "hd"
background = "transparent"
output_format = "png"
is_raw = false
safety_tolerance = 3
```

### Key Parameters

**Image Generation Settings:**
- `model`: Model choice (preset name or inline settings with model name)
- `quality`: Image quality ("standard", "hd")

**Output Configuration:**
- `nb_output`: Number of images to generate
- `aspect_ratio`: Image dimensions ("1:1", "16:9", "9:16", etc.)
- `output_format`: File format ("png", "jpeg", "webp")
- `background`: Background type ("default", "transparent")

**Generation Control:**
- `seed`: Random seed (integer or "auto")
- `is_raw`: Whether to apply post-processing
- `is_moderated`: Enable content moderation
- `safety_tolerance`: Content safety level (1-6)

### Input Requirements

PipeImgGen requires exactly one input that must be either:
- An `ImgGenPrompt` concept
- A concept that refines `ImgGenPrompt`

The input can be named anything but must contain the prompt text for image generation.

## PipeFunc operator

The PipeFunc operator is used to run custom Python functions within a pipeline. This allows integration of classic Python scripts and custom logic.

### Basic Usage

Simple Function Call:
```plx
[pipe.process_data]
type = "PipeFunc"
description = "Process data using custom function"
inputs = { input_data = "DataType" }
output = "ProcessedData"
function_name = "process_data_function"
```

File Processing Example:
```plx
[pipe.read_file]
type = "PipeFunc"
description = "Read file content"
inputs = { file_path = "FilePath" }
output = "FileContent"
function_name = "read_file_content"
```

### Key Parameters

- `function_name`: Name of the Python function to call (must be registered in func_registry)

### Function Requirements

The Python function must:

1. **Be registered** in the `func_registry`
2. **Accept `working_memory`** as a parameter:
   ```python
   async def my_function(working_memory: WorkingMemory) -> StuffContent | list[StuffContent] | str:
       # Function implementation
       pass
   ```

3. **Return appropriate types**:
   - `StuffContent`: Single content object
   - `list[StuffContent]`: Multiple content objects (becomes ListContent)
   - `str`: Simple string (becomes TextContent)

### Function Registration

Functions must be registered in the function registry before use:

```python
from pipelex.system.registries.func_registry import func_registry

@func_registry.register("my_function_name")
async def my_custom_function(working_memory: WorkingMemory) -> StuffContent:
    # Access inputs from working memory
    input_data = working_memory.get_stuff("input_name")
    
    # Process data
    result = process_logic(input_data.content)
    
    # Return result
    return MyResultContent(data=result)
```

### Working Memory Access

Inside the function, access pipeline inputs through working memory:

```python
async def process_function(working_memory: WorkingMemory) -> TextContent:
    # Get input stuff by name
    input_stuff = working_memory.get_stuff("input_name")
    
    # Access the content
    input_content = input_stuff.content
    
    # Process and return
    processed_text = f"Processed: {input_content.text}"
    return TextContent(text=processed_text)
```

---

## Rules to choose LLM models used in PipeLLMs.

### LLM Configuration System

In order to use it in a pipe, an LLM is referenced by its llm_handle (alias) and possibly by an llm_preset.
LLM configurations are managed through the new inference backend system with files located in `.pipelex/inference/`:

- **Model Deck**: `.pipelex/inference/deck/base_deck.toml` and `.pipelex/inference/deck/overrides.toml`
- **Backends**: `.pipelex/inference/backends.toml` and `.pipelex/inference/backends/*.toml`
- **Routing**: `.pipelex/inference/routing_profiles.toml`

### LLM Handles

An llm_handle can be either:
1. **A direct model name** (like "gpt-4o-mini", "claude-3-sonnet") - automatically available for all models loaded by the inference backend system
2. **An alias** - user-defined shortcuts that map to model names, defined in the `[aliases]` section:

```toml
[aliases]
base-claude = "claude-4.5-sonnet"
base-gpt = "gpt-5"
base-gemini = "gemini-2.5-flash"
base-mistral = "mistral-medium"
```

The system first looks for direct model names, then checks aliases if no direct match is found. The system handles model routing through backends automatically.

### Using an LLM Handle in a PipeLLM

Here is an example of using a model to specify which LLM to use in a PipeLLM:

```plx
[pipe.hello_world]
type = "PipeLLM"
description = "Write text about Hello World."
output = "Text"
model = { model = "gpt-5", temperature = 0.9 }
prompt = """
Write a haiku about Hello World.
"""
```

As you can see, to use the LLM, you must also indicate the temperature (float between 0 and 1) and max_tokens (either an int or the string "auto").

### LLM Presets

Presets are meant to record the choice of an llm with its hyper parameters (temperature and max_tokens) if it's good for a particular task. LLM Presets are skill-oriented.

Examples:
```toml
llm_to_reason = { model = "base-claude", temperature = 1 }
llm_to_extract_invoice = { model = "claude-3-7-sonnet", temperature = 0.1, max_tokens = "auto" }
```

The interest is that these presets can be used to set the LLM choice in a PipeLLM, like this:

```plx
[pipe.extract_invoice]
type = "PipeLLM"
description = "Extract invoice information from an invoice text transcript"
inputs = { invoice_text = "InvoiceText" }
output = "Invoice"
model = "llm_to_extract_invoice"
prompt = """
Extract invoice information from this invoice:

The category of this invoice is: $invoice_details.category.

@invoice_text
"""
```

The setting here `model = "llm_to_extract_invoice"` works because "llm_to_extract_invoice" has been declared as an llm_preset in the deck.
You must not use an LLM preset in a PipeLLM that does not exist in the deck. If needed, you can add llm presets.

You can override the predefined llm presets by setting them in `.pipelex/inference/deck/overrides.toml`.

---

ALWAYS RUN `make validate` when you are finished writing pipelines: This checks for errors. If there are errors, iterate until it works.
Then, create an example file to run the pipeline in the `examples` folder.
But don't write documentation unless asked explicitly to.
