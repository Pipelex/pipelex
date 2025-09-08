Concatenation
# Coding Standards & Best Practices

This document outlines the core coding standards, best practices, and quality control procedures for the codebase.

## Type Hints

1. **Always Use Type Hints**
   - Every function parameter must be typed
   - Every function return must be typed
   - Use type hints for all variables where type is not obvious
   - Use types with Uppercase first letter (Dict[], List[], etc.)

2. **StrEnum**
   - Import from `pipelex.types`:
   ```python
   from pipelex.types import StrEnum
   ```

## BaseModel Standards

- Respect Pydantic v2 standards
- Keep models focused and single-purpose
- Use descriptive field names
- Use type hints for all fields
- Document complex validations
- Use Optional[] for nullable fields
- Use Field(default_factory=...) for mutable defaults

## Factory Pattern

- Use Factory Pattern for object creation when dealing with multiple implementations

## Documentation

1. **Docstring Format**
   ```python
   def process_image(image_path: str, size: Tuple[int, int]) -> bytes:
       """Process and resize an image.
       
       Args:
           image_path: Path to the source image
           size: Tuple of (width, height) for resizing
           
       Returns:
           Processed image as bytes
       """
       pass
   ```

2. **Class Documentation**
   ```python
   class ImageProcessor:
       """Handles image processing operations.
       
       Provides methods for resizing, converting, and optimizing images.
       """
   ```

## Error Handling

1. **Graceful Error Handling**
   - Use try/except blocks with specific exceptions
   - Convert third-party exceptions to custom ones
   ```python
   try:
       from fal_client import AsyncClient as FalAsyncClient
   except ImportError as exc:
       raise MissingDependencyError(
           "fal-client", "fal", 
           "The fal-client SDK is required to use FAL models."
       ) from exc
   ```

## Code Quality Checks

### Linting and Type Checking

Before finalizing a task, run:
```bash
make fix-unused-imports
make check
```

This runs multiple code quality tools:
- Pyright: Static type checking
- Ruff: Fast Python linter  
- Mypy: Static type checker

Always fix any issues reported by these tools before proceeding.

### Running Tests

1. **Quick Test Run** (no LLM/image generation):
   ```bash
   make tp
   ```
   Runs tests with markers: `(dry_runnable or not (inference or llm or imgg or ocr)) and not (needs_output or pipelex_api)`

2. **Specific Tests**:
   ```bash
   make tp TEST=TestClassName
   # or
   make tp TEST=test_function_name
   ```
   Note: Matches names starting with the provided string.

**Important**: Never run `make ti`, `make test-inference`, `make to`, `make test-ocr`, `make tg`, or `make test-imgg` - these use costly inference.

## Pipelines

- All pipeline definitions go in `pipelex/libraries/pipelines/`
- Always validate pipelines after creation/edit with `make validate`.
  Iterate if there are errors.

## Project Structure

- **Pipelines**: `pipelex/libraries/pipelines/`
- **Tests**: `tests/` directory
- **Documentation**: `docs/` directory
 # Pipeline Guide

- Always first write your "plan" in natural langage, then transcribe it in pipelex.
- You should ALWAYS RUN the terminal command `make validate` when you are writing a `.plx` file. It will ensure the pipe is runnable. If not, iterate.
- Please use POSIX standard for files. (enmpty lines, no trailing whitespaces, etc.)

# Pipeline Structure Guide

## Pipeline File Naming
- Files must be `.plx` for pipelines (Always add an empty line at the end of the file, and do not add trailing whitespaces to PLX files at all)
- Files must be `.py` for structures
- Use descriptive names in `snake_case`

## Pipeline File Structure
A pipeline file has three main sections:
1. Domain statement
2. Concept definitions
3. Pipe definitions

### Domain Statement
```plx
domain = "domain_name"
definition = "Description of the domain" # Optional
```
Note: The domain name usually matches the plx filename for single-file domains. For multi-file domains, use the subdirectory name.

### Concept Definitions
```plx
[concept]
ConceptName = "Description of the concept" # Should be the same name as the Structure ClassName you want to output
```

Important Rules:
- Use PascalCase for concept names
- Never use plurals (no "Stories", use "Story")
- Avoid adjectives (no "LargeText", use "Text")
- Don't redefine native concepts (Text, Image, PDF, TextAndImages, Number)
yes 
### Pipe Definitions

## Pipe Base Structure

```plx
[pipe.your_pipe_name]
type = "PipeLLM"
definition = "A description of what your pipe does"
inputs = { input_1 = "ConceptName1", input_2 = "ConceptName2" }
output = "ConceptName"
```

DO NOT WRITE:
```plx
[pipe.your_pipe_name]
type = "pipe_sequence"
```

But it should be:

```plx
[pipe.your_pipe_name]
type = "PipeSequence"
definition = "....."
```

The pipes will all have at least this base structure. 
- `inputs`: Dictionnary of key behing the variable used in the prompts, and the value behing the ConceptName. It should ALSO LIST THE INPUTS OF THE INTERMEDIATE STEPS (if pipeSequence) or of the conditionnal pipes (if pipeCondition).
So If you have this error:
`StaticValidationError: missing_input_variable • domain='expense_validator' • pipe='validate_expense' • 
variable='['ocr_input']'``
That means that the pipe validate_expense is missing the input `ocr_input` because one of the subpipe is needing it.

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

# Structured Models Rules

## Model Location and Registration

- Create models for structured generations related to "some_domain" in `pipelex_libraries/pipelines/<some_domain>.py`
- Models must inherit from `StructuredContent` or appropriate content type

## Model Structure

Concepts and their structure classes are meant to indicate an idea.
A Concept MUST NEVER be a plural noun and you should never create a SomeConceptList: lists and arrays are implicitly handled by Pipelex according to the context. Just define SomeConcept.

**IMPORTANT: Never create unnecessary structure classes that only refine native concepts without adding fields.**

DO NOT create structures like:
```python
class Joke(TextContent):
    """A humorous text that makes people laugh."""
    pass
```

If a concept only refines a native concept (like Text, Image, etc.) without adding new fields, simply declare it in the .plx file:
```plx
[concept]
Joke = "A humorous text that makes people laugh."
```
If you simply need to refine another native concept, construct it like this:
```plx
[concept.Landscape]
refines = "Image"
```

Only create a Python structure class when you need to add specific fields:

```python
from datetime import datetime
from typing import List, Optional
from pydantic import Field

from pipelex.core.stuffs.stuff_content import StructuredContent

# IMPORTANT: THE CLASS MUST BE A SUBCLASS OF StructuredContent
class YourModel(StructuredContent): # Always be a subclass of StructuredContent
    # Required fields
    field1: str
    field2: int

    # Optional fields with defaults
    field3: Optional[str] = Field(None, "Description of field3")
    field4: List[str] = Field(default_factory=list)

    # Date fields should remove timezone
    date_field: Optional[datetime] = None
```
## Usage

Structures are meant to indicate what class to use for a particular Concept. In general they use the same name as the concept.

Structure classes defined within `pipelex_libraries/pipelines/` are automatically loaded into the class_registry when setting up Pipelex, no need to do it manually.


## Best Practices for structures

- Respect Pydantic v2 standards
- Use type hints for all fields
- Use `Field` declaration and write the description


## Pipe Controllers and Pipe Operator

Look at the Pipes we have in order to adapt it. Pipes are organized in two categories:

1. **Controllers** - For flow control:
   - `PipeSequence` - For creating a sequence of multiple steps
   - `PipeCondition` - If the next pipe depends of the expression of a stuff in the working memory
   - `PipeParallel` - For parallelizing pipes
   - `PipeBatch` - For running pipes in Batch over a ListContent

2. **Operators** - For specific tasks:
   - `PipeLLM` - Generate Text and Objects (include Vision LLM)
   - `PipeOcr` - OCR Pipe
   - `PipeImgGen` - Generate Images
   - `PipeFunc` - For running classic python scripts

# PipeSequence Guide

## Purpose
PipeSequence executes multiple pipes in a defined order, where each step can use results from previous steps.

## Basic Structure
```plx
[pipe.your_sequence_name]
type = "PipeSequence"
definition = "Description of what this sequence does"
inputs = { input_name = "InputType" } # All the inputs of the sub pipes, except the ones generated by intermediate steps
output = "OutputType"
steps = [
    { pipe = "first_pipe", result = "first_result" },
    { pipe = "second_pipe", result = "second_result" },
    { pipe = "final_pipe", result = "final_result" }
]
```

## Key Components

1. **Steps Array**: List of pipes to execute in sequence
   - `pipe`: Name of the pipe to execute
   - `result`: Name to assign to the pipe's output that will be in the working memory

## Using PipeBatch in Steps

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

# PipeCondition Controller

The PipeCondition controller allows you to implement conditional logic in your pipeline, choosing which pipe to execute based on an evaluated expression. It supports both direct expressions and expression templates.

## Usage in PLX Configuration

### Basic Usage with Direct Expression

```plx
[pipe.conditional_operation]
type = "PipeCondition"
definition = "A conditonal pipe to decide wheter..."
inputs = { input_data = "CategoryInput" }
output = "native.Text"
expression = "input_data.category"

[pipe.conditional_operation.pipe_map]
small = "process_small"
medium = "process_medium"
large = "process_large"
```
or
```plx
[pipe.conditional_operation]
type = "PipeCondition"
definition = "A conditonal pipe to decide wheter..."
inputs = { input_data = "CategoryInput" }
output = "native.Text"
expression_template = "{{ input_data.category }}" # Jinja2 code

[pipe.conditional_operation.pipe_map]
small = "process_small"
medium = "process_medium"
large = "process_large"
```

## Key Parameters

- `expression`: Direct boolean or string expression (mutually exclusive with expression_template)
- `expression_template`: Jinja2 template for more complex conditional logic (mutually exclusive with expression)
- `pipe_map`: Dictionary mapping expression results to pipe codes : 
1 - The key on the left (`small`, `medium`) is the result of `expression` or `expression_template`.
2 - The value on the right (`process_small`, `process_medium`, ..) is the name of the pipce to trigger

# PipeBatch Controller

The PipeBatch controller allows you to apply a pipe operation to each element in a list of inputs in parallele. It is created via a PipeSequence.

## Usage in PLX Configuration

```plx
[pipe.sequence_with_batch]
type = "PipeSequence"
definition = "A Sequence of pipes"
inputs = { input_data = "ConceptName" }
output = "OutputConceptName"
steps = [
    { pipe = "pipe_to_apply", batch_over = "input_list", batch_as = "current_item", result = "batch_results" }
]
```

## Key Parameters

- `pipe`: The pipe operation to apply to each element in the batch
- `batch_over`: The name of the list in the context to iterate over
- `batch_as`: The name to use for the current element in the pipe's context
- `result`: Where to store the results of the batch operation

# PipeLLM Guide

## Purpose

PipeLLM is used to:
1. Generate text or objects with LLMs
2. Process images with Vision LLMs

## Basic Usage

### Simple Text Generation
```plx
[pipe.write_story]
type = "PipeLLM"
definition = "Write a short story"
output = "Text"
prompt_template = """
Write a short story about a programmer.
"""
```

### Structured Data Extraction
```plx
[pipe.extract_info]
type = "PipeLLM"
definition = "Extract information"
inputs = { text = "Text" }
output = "PersonInfo"
prompt_template = """
Extract person information from this text:
@text
"""
```

### System Prompts
Add system-level instructions:
```plx
[pipe.expert_analysis]
type = "PipeLLM"
definition = "Expert analysis"
output = "Analysis"
system_prompt = "You are a data analysis expert"
prompt_template = "Analyze this data"
```

### Multiple Outputs
Generate multiple results:
```plx
[pipe.generate_ideas]
type = "PipeLLM"
definition = "Generate ideas"
output = "Idea"
nb_output = 3  # Generate exactly 3 ideas
# OR
multiple_output = true  # Let the LLM decide how many to generate
```

### Vision Tasks
Process images with VLMs:
```plx
[pipe.analyze_image]
type = "PipeLLM"
definition = "Analyze image"
inputs = { image = "Image" } # `image` is the name of the stuff that contains the Image. If its in a stuff, you can add something like `{ "page.image": "Image" }
output = "ImageAnalysis"
prompt_template = "Describe what you see in this image"
```

# PipeOCR Guide

## Purpose

Extract text and images from an image or a PDF

## Basic Usage

### Simple Text Generation
```plx
[pipe.extract_info]
type = "PipeOcr"
definition = "extract the information"
inputs = { ocr_input = "PDF" } # or { ocr_input = "Image" } if its an image. This is the only input
output = "Page"
```

The input ALWAYS HAS TO BE `ocr_input` and the value is either of concept `Image` or `Pdf`.

The output concept `Page` is a native concept, with the structure `PageContent`:
It corresponds to 1 page. Therefore, the PipeOcr is outputing a `ListContent` of `Page`

```python
class TextAndImagesContent(StuffContent):
    text: Optional[TextContent]
    images: Optional[List[ImageContent]]

class PageContent(StructuredContent): # CONCEPT IS "Page"
    text_and_images: TextAndImagesContent
    page_view: Optional[ImageContent] = None
```
- `text_and_images` are the text, and the related images found in the input image or PDF.
- `page_view` is the screenshot of the whole pdf page/image.

This rule explains how to write prompt templates in PipeLLM definitions.

## Insert stuff inside a tagged block

If the inserted text is supposedly long text, made of several lines or paragraphs, you want it inserted inside a block, possibly a block tagged and delimlited with proper syntax as one would do in a markdown documentation. To include stuff as a block, use the "@" prefix.

Example template:
```plx
prompt_template = """
Match the expense with its corresponding invoice:

@expense

@invoices
"""
```
In this example, the expense data and the invoices data are obviously made of several lines each, that's why it makes sense to use the "@" prefix in order to have them delimited inside a block. Note that our preprocessor will automatically include the block's title, so it doens't need to be explictly written in the prompt template.

**DO NOT write things like "Here is the expense: @expense".**
**DO write simply "@expense" alone in an isolated line.**

## Insert stuff inline

If the inserted text is short text and it makes sense to have it inserted directly into a sentence, you want it inserted inline. To insert stuff inline, use the "$" prefix. This will insert the stuff without delimiters and the content will be rendered as plain text.

Example template:
```plx
prompt_template = """
Your goal is to summarize everything related to $topic in the provided text:

@text

Please provide only the summary, with no additional text or explanations.
Your summary should not be longer than 2 sentences.
"""
```

Here, $topic will be inserted inline, whereas @text will be a a delimited block.
Be sure to make the proper choice of prefix for each insertion.

**DO NOT write "$topic" alone in an isolated line.**
**DO write things like "Write an essay about $topic" included in an actual sentence.**

# Example to execute a pipeline

```python
import asyncio

from pipelex import pretty_print
from pipelex.hub import get_pipeline_tracker, get_report_delegate
from pipelex.pipelex import Pipelex
from pipelex.pipeline.execute import execute_pipeline

from pipelex.libraries.pipelines.examples.extract_gantt.gantt import GanttChart

SAMPLE_NAME = "extract_gantt"
IMAGE_URL = "assets/gantt/gantt_tree_house.png"


async def extract_gantt(image_url: str) -> GanttChart:
    # Run the pipe
    pipe_output = await execute_pipeline(
        pipe_code="extract_gantt_by_steps",
        input_memory={
            "gantt_chart_image": {
                "concept": "gantt.GanttImage",
                "content": ImageContent(url=image_url),
            }
        },
    )
    # Output the result
    return pipe_output.main_stuff_as(content_type=GanttChart)


# start Pipelex
Pipelex.make()

# run sample using asyncio
gantt_chart = asyncio.run(extract_gantt(IMAGE_URL))

# Display cost report (tokens used and cost)
get_report_delegate().generate_report()
# output results
pretty_print(gantt_chart, title="Gantt Chart")
get_pipeline_tracker().output_flowchart()
```

The input memory is a dictionary of key-value pairs, where the key is the name of the input variable and the value provides details to make it a stuff object. The relevant definitions are:
```python
StuffContentOrData = Dict[str, Any] | StuffContent | List[Any] | str
ImplicitMemory = Dict[str, StuffContentOrData]
```
As you can seen, we made it so different ways can be used to define that stuff using structured content or data.

So here are a few concrete examples of calls to execute_pipeline with various ways to set up the input memory:

```python
# Here we have a single input and it's a Text.
# If you assign a string, by default it will be considered as a TextContent.
    pipe_output = await execute_pipeline(
        pipe_code="master_advisory_orchestrator",
        input_memory={
            "user_input": problem_description,
        },
    )

# Here we have a single input and it's a PDF.
# Because PDFContent is a native concept, we can use it directly as a value,
# the system knows what content it corresponds to:
    pipe_output = await execute_pipeline(
        pipe_code="power_extractor_dpe",
        input_memory={
            "ocr_input": PDFContent(url=pdf_url),
        },
    )

# Here we have a single input and it's an Image.
# Because ImageContent is a native concept, we can use it directly as a value:
    pipe_output = await execute_pipeline(
        pipe_code="fashion_variation_pipeline",
        input_memory={
            "fashion_photo": ImageContent(url=image_url),
        },
    )

# Here we have a single input, it's an image but
# its actually a more specific concept gantt.GanttImage which refines Image,
# so we must provide it using a dict with the concept and the content:
    pipe_output = await execute_pipeline(
        pipe_code="extract_gantt_by_steps",
        input_memory={
            "gantt_chart_image": {
                "concept": "gantt.GanttImage",
                "content": ImageContent(url=image_url),
            }
        },
    )

# Here is a more complex example with multiple inputs assigned using different ways:
    pipe_output = await execute_pipeline(
        pipe_code="retrieve_then_answer",
        dynamic_output_concept_code="contracts.Fees",
        input_memory={
            "text": load_text_from_path(path=text_path),
            "question": {
                "concept": "answer.Question",
                "content": question,
            },
            "client_instructions": client_instructions,
        },
    )
```

ALWAYS RUN `make validate` when you are finished writing pipelines: This checks for errors. If there are errors, iterate until it works.
Then, create an example file to run the pipeline in the `examples` folder.
But don't write documentation unless asked explicitly to.

# Rules to choose LLM models used in PipeLLMs.

## LLM Handles

In order to use it in a pipe, an LLM is referenced by its llm_handle and possibly by an llm_preset.
Both llm_handles and llm_presets are defined in this toml config file: [base_llm_deck.toml](mdc:pipelex/libraries/llm_deck/base_llm_deck.toml)

## LLM Handles

An llm_handle matches the handle (an id of sorts) with the full specification of the LLM to use, i.e.:
- llm_name
- llm_version
- llm_platform_choice

The declaration of llm_handles looks like this in toml syntax:
```toml
[llm_handles]
gpt-4o-2024-11-20 = { llm_name = "gpt-4o", llm_version = "2024-11-20" }
```

In mosty cases, we only want to use version "latest" and llm_platform_choice "default" in which case the declaration is simply a match of the llm_handle to the llm_name, like this:
```toml
best-claude = "claude-4-opus"
best-gemini = "gemini-2.5-pro"
best-mistral = "mistral-large"
```

And of course, llm_handles are automatically assigned for all models by their name, with version "latest" and llm_platform_choice "default".

## Using an LLM Handle in a PipeLLM

Here is an example of using an llm_handle to specify which LLM to use in a PipeLLM:

```plx
[pipe.hello_world]
type = "PipeLLM"
definition = "Write text about Hello World."
output = "Text"
llm = { llm_handle = "gpt-4o-mini", temperature = 0.9, max_tokens = "auto" }
prompt_template = """
Write a haiku about Hello World.
"""
```

As you can see, to use the LLM, you must also indicate the temperature (float between 0 and 1) and max_tokens (either an int or the string "auto").

## LLM Presets

Presets are meant to record the choice of an llm with its hyper parameters (temperature and max_tokens) if it's good for a particular task. LLM Presets are skill-oriented.

Examples:
```toml
llm_to_reason = { llm_handle = "o4-mini", temperature = 1, max_tokens = "auto" }
llm_to_extract_invoice = { llm_handle = "claude-3-7-sonnet", temperature = 0.1, max_tokens = "auto" }
```

The interest is that these presets can be used to set the LLM choice in a PipeLLM, like this:

```plx
[pipe.extract_invoice]
type = "PipeLLM"
definition = "Extract invoice information from an invoice text transcript"
inputs = { invoice_text = "InvoiceText" }
output = "Invoice"
llm = "llm_to_extract_invoice"
prompt_template = """
Extract invoice information from this invoice:

The category of this invoice is: $invoice_details.category.

@invoice_text
"""
```

The setting here `llm = "llm_to_extract_invoice"` works because "llm_to_extract_invoice" has been declared as an llm_preset in the deck.
You must not use an LLM preset in a PipeLLM that does not exist in the deck. If needed, you can add llm presets.


You can override the predefined llm presets in [overrides.toml](../../pipelex/libraries/llm_deck/overrides.toml).

These rules apply when writing unit tests.
- Always use pytest

## Test file structure

- Name test files with `test_` prefix
- Use descriptive names that match the functionality being tested
- Place test files in the appropriate test category directory:
    - `tests/unit/` - for unit tests that test individual functions/classes in isolation
    - `tests/integration/` - for integration tests that test component interactions
    - `tests/e2e/` - for end-to-end tests that test complete workflows
    - `tests/test_pipelines/` - for test pipeline definitions (PLX files and their structuring python files)
- Fixtures are defined in conftest.py modules at different levels of the hierarchy, their scope is handled by pytest
- Test data is placed inside test_data.py at different levels of the hierarchy, they must be imported with package paths from the root like `tests.pipelex.test_data`. Their content is all constants, regrouped inside classes to keep things tidy.
- Always put test inside Test classes.
- The pipelex pipelines should be stored in `tests/test_pipelines` as well as the related structured Output classes that inherit from `StructuredContent`

## Markers

Apply the appropriate markers:
- "llm: uses an LLM to generate text or objects"
- "imgg: uses an image generation AI"
- "inference: uses either an LLM or an image generation AI"
- "gha_disabled: will not be able to run properly on GitHub Actions"

Several markers may be applied. For instance, if the test uses an LLM, then it uses inference, so you must mark with both `inference`and `llm`.

## Tips

- Never use the unittest.mock. Use pytest-mock

## Test Class Structure

Always group the tests of a module into a test class:

```python
@pytest.mark.llm
@pytest.mark.inference
@pytest.mark.asyncio(loop_scope="class")
class TestFooBar:
    @pytest.mark.parametrize(
        "topic test_case_blueprint",
        [
            TestCases.CASE_1,
            TestCases.CASE_2,
        ],
    )
    async def test_pipe_processing(
        self,
        request: FixtureRequest,
        topic: str,
        test_case_blueprint: StuffBlueprint,
    ):
        # Test implementation
```

Sometimes it can be convenient to access the test's name in its body, for instance to include into a job_id. To achieve that, add the argument `request: FixtureRequest` into the signature and then you can get the test name using `cast(str, request.node.originalname),  # type: ignore`. 

# Pipe tests

## Required imports for pipe tests

```python
import pytest
from pytest import FixtureRequest
from pipelex import log, pretty_print
from pipelex.core.stuffs.stuff_factory import StuffBlueprint, StuffFactory
from pipelex.core.memory.working_memory_factory import WorkingMemoryFactory
from pipelex.hub import get_report_delegate
from pipelex.libraries.pipelines.base_library.retrieve import RetrievedExcerpt
from pipelex.config_pipelex import get_config

from pipelex.core.pipe import PipeAbstract, update_job_metadata_for_pipe
from pipelex.core.pipes.pipe_output import PipeOutput, PipeOutputType
from pipelex.core.pipes.pipe_run_params import PipeRunParams
from pipelex.core.pipes.pipe_run_params import PipeRunParams
from pipelex.pipe_works.pipe_router_protocol import PipeRouterProtocol
```

## Pipe test implementation steps

1. Create Stuff from blueprint:

```python
stuff = StuffFactory.make_stuff(
    concept_code="RetrievedExcerpt",
    domain="retrieve",
    content=RetrievedExcerpt(text="<Some retrieved text>", justification="<Some justification>")
    name="retrieved_text",
)
```

2. Create Working Memory:

```python
working_memory = WorkingMemoryFactory.make_from_single_stuff(stuff=stuff)
```

3. Run the pipe:

```python
pipe_output: PipeOutput = await pipe_router.run_pipe(
    pipe_code="pipe_name",
    pipe_run_params=PipeRunParamsFactory.make_run_params(),
    working_memory=working_memory,
    job_metadata=JobMetadata(),
)
```

4. Log output and generate report:

```python
pretty_print(pipe_output, title=f"Pipe output")
get_report_delegate().generate_report()
```

5. Basic assertions:

```python
assert pipe_output is not None
assert pipe_output.working_memory is not None
assert pipe_output.main_stuff is not None
```

## Test Data Organization

- If it's not already there, create a `test_data.py` file in the test directory
- Define test cases using `StuffBlueprint`:

```python
class TestCases:
    CASE_BLUEPRINT_1 = StuffBlueprint(
        name="test_case_1",
        concept_code="domain.ConceptName1",
        value="test_value"
    )
    CASE_BLUEPRINT_2 = StuffBlueprint(
        name="test_case_2",
        concept_code="domain.ConceptName2",
        value="test_value"
    )

    CASE_BLUEPRINTS: ClassVar[List[Tuple[str, str]]] = [  # topic, blueprint"
        ("topic1", CASE_BLUEPRINT_1),
        ("topic2", CASE_BLUEPRINT_2),
    ]
```

Note how we avoid initializing a default mutable value within a class instance, instead we use ClassVar.
Also note that we provide a topic for the test case, which is purely for convenience.

## Best Practices for Testing

- Use parametrize for multiple test cases
- Test both success and failure cases
- Verify working memory state
- Check output structure and content
- Use meaningful test case names
- Include docstrings explaining test purpose
- Log outputs for debugging
- Generate reports for cost tracking

# Test-Driven Development Guide

This document outlines our test-driven development (TDD) process and the tools available for testing.

## TDD Cycle

1. **Write a Test First**
[pytest.mdc](pytest.mdc)

2. **Write the Code**
   - Implement the minimum amount of code needed to pass the test
   - Follow the project's coding standards
   - Keep it simple - don't write more than needed

3. **Run Linting and Type Checking**
[coding_standards.mdc](coding_standards.mdc)

4. **Refactor if needed**
If the code needs refactoring, with the best practices [coding_standards.mdc](coding_standards.mdc)

5. **Validate tests**

Remember: The key to TDD is writing the test first and letting it drive your implementation. Always run the full test suite and quality checks before considering a feature complete.

