# Migration Guide - Breaking Changes

This guide will help you migrate your Pipelex pipelines and configurations to the latest version.

## Overview

This release introduces several breaking changes to make the Pipelex language more declarative, intuitive, and consistent. The changes affect:
- Project structure and organization
- Pipeline definitions (.plx files)
- Configuration files (.pipelex/ directory)
- Python code initialization
- Python import paths (module refactoring)
- Test markers

## Migration Checklist

- [ ] **Migrate from pipelex_libraries system (CRITICAL)**
- [ ] Move .plx files to appropriate locations in your project
- [ ] Update Pipelex.make() calls (remove config path parameters)
- [ ] Add @pipe_func() decorators to custom functions used in PipeFunc operators
- [ ] Update PipeCompose (formerly PipeJinja2)
- [ ] Update PipeExtract (formerly PipeOCR)
- [ ] Update PipeLLM prompts and fields
- [ ] Update PipeImgGen fields
- [ ] Update PipeCondition fields
- [ ] Update configuration files
- [ ] Update test markers
- [ ] **Update Python imports for StuffContent subclasses**
- [ ] **Update imports for core module relocations (pipe_works, pipe_input, etc.)**
- [ ] **Update all OCR-related imports to Extract equivalents**
- [ ] **Update Provider → Library class names and hub method calls**
- [ ] Run validation

## 1. Library System Removal (CRITICAL)

The centralized `pipelex_libraries` folder system has been removed in favor of automatic pipeline discovery throughout your project.

### Key Changes

1. **No more `pipelex init libraries` command**
2. **No centralized `pipelex_libraries` directory required**
3. **Pipelines are auto-discovered** from anywhere in your project
4. **No config path parameters** needed in commands or code
5. **Custom functions require `@pipe_func()` decorator**
6. **Structure classes are auto-discovered**

### Step 1: Move Pipeline Files (Flexible Organization)

**The key change:** `.plx` files can now live ANYWHERE in your project. No special directory required!

**Recommendation:** Put `.plx` files with related code. If you have topic-based organization, keep pipelines with their topics.

**Example Migration Patterns:**

**Pattern A: Topic-Based (Recommended if you have domain modules)**
```
Before:
pipelex_libraries/pipelines/
├── finance.plx
├── finance.py
├── legal.plx
└── legal.py

After - Keep with related code:
my_project/
├── finance/
│   ├── models.py
│   ├── services.py
│   ├── invoices.plx          # Pipeline with finance code
│   └── invoices_struct.py    # Structure classes
└── legal/
    ├── models.py
    ├── services.py
    ├── contracts.plx         # Pipeline with legal code
    └── contracts_struct.py
```

**Pattern B: Centralized Pipelines (If you prefer grouping)**
```
After - Group pipelines together:
my_project/
├── pipelines/
│   ├── finance.plx
│   ├── finance_struct.py
│   ├── legal.plx
│   └── legal_struct.py
└── core/
    └── (your other code)
```

**Pattern C: Flat (Small projects)**
```
After - Just put them in your source directory:
my_project/
├── finance_pipeline.plx
├── finance_struct.py
└── main.py
```

**Action Items:**

1. **Choose your organization** (any of the above patterns work)

2. **Move .plx files** to where they make sense for YOUR project:
   ```bash
   # Example: Moving to topic-based structure
   mv pipelex_libraries/pipelines/finance.plx my_project/finance/
   ```

3. **Rename structure files** with `_struct.py` suffix:
   ```bash
   # Example
   mv my_project/finance/finance.py my_project/finance/finance_struct.py
   ```

4. **Clean up:**
   ```bash
   # After all files are moved
   rm -rf pipelex_libraries/
   
   # Remove from .gitignore if present
   sed -i '/^\/pipelex_libraries$/d' .gitignore
   ```

**Remember:** Configuration (`.pipelex/`) stays at repository root.

### Step 2: Update Python Code Initialization

**Before:**
```python
from pipelex.pipelex import Pipelex

pipelex_instance = Pipelex.make(
    relative_config_folder_path="../../../pipelex/libraries",
    from_file=True
)
```

**After:**
```python
from pipelex.pipelex import Pipelex

# No path needed - automatic discovery
pipelex_instance = Pipelex.make()
```

**Find and replace in all Python files:**
- Remove `relative_config_folder_path` parameter
- Remove `config_folder_path` parameter
- Remove `from_file` parameter

### Step 3: Update Custom Functions

All custom functions used in `PipeFunc` operators must now have the `@pipe_func()` decorator for auto-discovery.

**Before:**
```python
from pipelex.core.memory.working_memory import WorkingMemory
from pipelex.core.stuffs.text_content import TextContent

async def my_custom_function(working_memory: WorkingMemory) -> TextContent:
    input_data = working_memory.get_stuff("input_name")
    return TextContent(text=f"Processed: {input_data.content.text}")
```

**After:**
```python
from pipelex.system.registries.func_registry import pipe_func
from pipelex.core.memory.working_memory import WorkingMemory
from pipelex.core.stuffs.text_content import TextContent

@pipe_func()  # Add this decorator
async def my_custom_function(working_memory: WorkingMemory) -> TextContent:
    input_data = working_memory.get_stuff("input_name")
    return TextContent(text=f"Processed: {input_data.content.text}")

# Optional: specify a custom name
@pipe_func(name="custom_processor")
async def another_function(working_memory: WorkingMemory) -> TextContent:
    # Implementation
    pass
```

### Step 4: Update CLI Commands

**Before:**
```bash
# You had to specify config folder path
pipelex validate all -c path/to/pipelex/libraries
pipelex build blueprint "..." -c your/path/to/pipelex/libraries
```

**After:**
```bash
# No config path needed - automatic discovery
pipelex validate all
pipelex build blueprint "..."
```

### Step 5: Update Imports in Python Code

Update imports from the old library structure:

**Before:**
```python
from pipelex.libraries.pipelines.finance import Invoice, InvoiceData
```

**After:**
```python
# Import from your own project structure
from my_project.pipelines.finance_struct import Invoice, InvoiceData
```

### Step 6: Update Concept References (Optional)

While domain-prefixed concept references still work, you can now use simpler references:

**Before:**
```plx
inputs = { prompt = "images.ImgGenPrompt" }
inputs = { wedding_photo = "images.Photo" }
```

**After:**
```plx
# Simpler references (domain prefix optional)
inputs = { prompt = "ImgGenPrompt" }
inputs = { wedding_photo = "Photo" }
```

### Auto-Discovery Explained

**The big change:** Pipelex now scans your entire project and finds:

- **`.plx` files** - Pipeline definitions (wherever they are!)
- **Structure classes** - Classes inheriting from `StructuredContent`
- **Custom functions** - Functions decorated with `@pipe_func()`

**This means:**
- No special `pipelex_libraries/pipelines/` folder needed
- Put `.plx` files where they logically belong in YOUR codebase
- Keep related things together (pipelines with their code)

**Excluded directories** (automatically skipped):
- `.venv`, `.git`, `__pycache__`
- `.pytest_cache`, `.mypy_cache`, `.ruff_cache`
- `node_modules`, `.env`, `results`

### Troubleshooting

**Issue: Pipelines not found**

Solution: Ensure `.plx` files are not in excluded directories and run:
```bash
pipelex show pipes  # See what was discovered
```

**Issue: Structure classes not registered**

Solution:
1. Ensure classes inherit from `StructuredContent`
2. Check class names match concept names exactly
3. Use `_struct.py` suffix for structure files

**Issue: Custom functions not found**

Solution:
1. Add `@pipe_func()` decorator
2. Ensure function is `async` and accepts `working_memory`
3. Verify function is in a discoverable location

## 2. General Changes

### Rename `definition` to `description`

**Find:** `definition = "`
**Replace with:** `description = "`

This applies to all pipe types.

**Before:**
```plx
[pipe.example]
type = "PipeLLM"
definition = "Process data"
```

**After:**
```plx
[pipe.example]
type = "PipeLLM"
description = "Process data"
```

## 3. PipeCompose (formerly PipeJinja2)

### Rename pipe type

**Find:** `type = "PipeJinja2"`
**Replace with:** `type = "PipeCompose"`

### Rename template fields

**Find:** `jinja2 = `
**Replace with:** `template = `

**Find:** `jinja2_name = `
**Replace with:** `template_name = `

**Before:**
```plx
[pipe.compose_report]
type = "PipeJinja2"
description = "Compose a report"
inputs = { data = "ReportData" }
output = "Text"
jinja2 = """
Report: $data
"""
```

**After:**
```plx
[pipe.compose_report]
type = "PipeCompose"
description = "Compose a report"
inputs = { data = "ReportData" }
output = "Text"
template = """
Report: $data
"""
```

### Nested template section (optional)

If you need more control, you can now use a nested template section:

**Before:**
```plx
[pipe.example]
type = "PipeJinja2"
jinja2 = "Template content"
template_category = "html"
```

**After:**
```plx
[pipe.example]
type = "PipeCompose"

[pipe.example.template]
template = "Template content"
category = "html"
templating_style = { tag_style = "square_brackets", text_format = "html" }
```

## 4. PipeExtract (formerly PipeOCR)

### Rename pipe type

**Find:** `type = "PipeOCR"`
**Replace with:** `type = "PipeExtract"`

### Rename model field

**Find:** `ocr_model = `
**Replace with:** `model = `

### Input naming

The input no longer needs to be named `ocr_input`. You can name it anything as long as it's a single input that is either an `Image` or a `PDF`.

**Before:**
```plx
[pipe.extract_info]
type = "PipeOCR"
description = "Extract text from document"
inputs = { ocr_input = "PDF" }
output = "Page"
ocr_model = "mistral-ocr"
```

**After:**
```plx
[pipe.extract_info]
type = "PipeExtract"
description = "Extract text from document"
inputs = { document = "PDF" }
output = "Page"
model = "base_extract_mistral"
```

### Python function renames

If you're using these functions in Python code:

**Find:** `ocr_page_contents_from_pdf`
**Replace with:** `extract_page_contents_from_pdf`

**Find:** `ocr_page_contents_and_views_from_pdf`
**Replace with:** `extract_page_contents_and_views_from_pdf`

## 5. PipeLLM Changes

### Rename prompt field

**Find:** `prompt_template = `
**Replace with:** `prompt = `

### Rename model fields

**Find:** `llm = `
**Replace with:** `model = `

**Find:** `llm_to_structure = `
**Replace with:** `model_to_structure = `

### Tag image inputs in prompts

Image inputs must now be explicitly tagged in the prompt using `$image_name` or `@image_name`.

**Before:**
```plx
[pipe.analyze_image]
type = "PipeLLM"
description = "Analyze image"
inputs = { image = "Image" }
output = "ImageAnalysis"
prompt_template = "Describe what you see in this image"
```

**After:**
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

You can also reference images inline:
```plx
prompt = "Analyze the colors in $photo and the shapes in $painting."
```

**Complete example:**

**Before:**
```plx
[pipe.extract_info]
type = "PipeLLM"
definition = "Extract information"
inputs = { text = "Text" }
output = "PersonInfo"
llm = { llm_handle = "gpt-4o", temperature = 0.1 }
prompt_template = """
Extract person information from this text:
@text
"""
```

**After:**
```plx
[pipe.extract_info]
type = "PipeLLM"
description = "Extract information"
inputs = { text = "Text" }
output = "PersonInfo"
model = { model = "gpt-4o", temperature = 0.1 }
prompt = """
Extract person information from this text:
@text
"""
```

## 6. PipeImgGen Changes

### Rename model field

**Find:** `img_gen = `
**Replace with:** `model = `

### Remove technical settings from pipe level

Settings like `nb_steps` and `guidance_scale` should now be configured in model settings or presets, not at the pipe level.

**Before:**
```plx
[pipe.generate_photo]
type = "PipeImgGen"
description = "Generate a photo"
inputs = { prompt = "ImgGenPrompt" }
output = "Photo"
img_gen = { img_gen_handle = "fast-img-gen", quality = "hd" }
aspect_ratio = "16:9"
nb_steps = 8
```

**After:**
```plx
[pipe.generate_photo]
type = "PipeImgGen"
description = "Generate a photo"
inputs = { prompt = "ImgGenPrompt" }
output = "Photo"
model = { model = "fast-img-gen" }
aspect_ratio = "16:9"
quality = "hd"
```

Or use a preset:
```plx
model = "img_gen_preset_name"
```

## 7. PipeCondition Changes

### Rename outcome fields

**Find:** `[pipe.your_pipe.pipe_map]`
**Replace with:** `[pipe.your_pipe.outcomes]`

**Find:** `default_pipe_code = `
**Replace with:** `default_outcome = `

### Add required default_outcome

The `default_outcome` field is now **required**. If you don't want any default behavior, use `"fail"`.

**Before:**
```plx
[pipe.conditional_operation]
type = "PipeCondition"
description = "Decide which pipe to run"
inputs = { input_data = "CategoryInput" }
output = "native.Text"
expression = "input_data.category"

[pipe.conditional_operation.pipe_map]
small = "process_small"
medium = "process_medium"
large = "process_large"
```

**After:**
```plx
[pipe.conditional_operation]
type = "PipeCondition"
description = "Decide which pipe to run"
inputs = { input_data = "CategoryInput" }
output = "native.Text"
expression = "input_data.category"
default_outcome = "process_medium"

[pipe.conditional_operation.outcomes]
small = "process_small"
medium = "process_medium"
large = "process_large"
```

To fail when no match:
```plx
default_outcome = "fail"
```

## 8. Configuration Files (.pipelex/ directory)

### LLM presets in deck files

**Find:** `llm_handle = `
**Replace with:** `model = `

**Before (.pipelex/inference/deck/base_deck.toml):**
```toml
[presets.llm]
llm_to_reason = { llm_handle = "claude-3-5-sonnet", temperature = 1 }
```

**After:**
```toml
[presets.llm]
llm_to_reason = { model = "claude-3-5-sonnet", temperature = 1 }
```

### Image generation presets

**Find:** `img_gen_handle = `
**Replace with:** `model = `

**Before:**
```toml
[presets.img_gen]
fast_gen = { img_gen_handle = "fast-img-gen", quality = "standard" }
```

**After:**
```toml
[presets.img_gen]
fast_gen = { model = "fast-img-gen", quality = "standard" }
```

### Extract presets (formerly OCR)

**Find:** `ocr_handle = `
**Replace with:** `model = `

**Find:** `[presets.ocr]`
**Replace with:** `[presets.extract]`

**Find:** `base_ocr_pypdfium2`
**Replace with:** `base_extract_pypdfium2`

**Find:** `base_ocr_mistral`
**Replace with:** `base_extract_mistral`

**Before:**
```toml
[presets.ocr]
base_ocr_mistral = { ocr_handle = "mistral-ocr" }
```

**After:**
```toml
[presets.extract]
base_extract_mistral = { model = "mistral-ocr" }
```

### pipelex.toml

**Find:** `ocr_config`
**Replace with:** `extract_config`

**Find:** `is_auto_setup_preset_ocr`
**Replace with:** `is_auto_setup_preset_extract`

**Find:** `nb_ocr_pages`
**Replace with:** `nb_extract_pages`

**Before (.pipelex/pipelex.toml):**
```toml
[ocr_config]
is_auto_setup_preset_ocr = true
nb_ocr_pages = 10
```

**After:**
```toml
[extract_config]
is_auto_setup_preset_extract = true
nb_extract_pages = 10
```

## 9. Test Markers

### Update pytest markers

**Find:** `@pytest.mark.ocr`
**Replace with:** `@pytest.mark.extract`

**Before:**
```python
@pytest.mark.ocr
@pytest.mark.inference
class TestOCRPipeline:
    async def test_extract(self):
        # test code
```

**After:**
```python
@pytest.mark.extract
@pytest.mark.inference
class TestExtractPipeline:
    async def test_extract(self):
        # test code
```

### Update test markers in pytest.ini or pyproject.toml

**Find:** `ocr: uses OCR`
**Replace with:** `extract: uses text/image extraction from documents`

### Update make commands

**Find:** `make test-ocr` or `make to`
**Replace with:** `make test-extract` or `make te`

## 10. Validation

After making changes, thoroughly test your migration:

### Activate Virtual Environment

```bash
# Activate your virtual environment first
source .venv/bin/activate  # Unix/macOS
# or
.venv\Scripts\activate  # Windows
```

### Validation Steps

1. **Validate pipeline syntax:**
   ```bash
   pipelex validate all
   ```

2. **Check specific pipes:**
   ```bash
   pipelex show pipes  # List all discovered pipes
   pipelex show pipe YOUR_PIPE_CODE  # Inspect specific pipe
   ```

3. **Run your test suite:**
   ```bash
   pytest tests/
   # or if using make:
   make test
   ```

4. **Test pipeline execution:**
   - Run your application
   - Execute example pipelines
   - Verify outputs are as expected

5. **Check for issues:**
   - Review any validation errors
   - Check imports are working
   - Verify structure classes are discovered
   - Confirm custom functions are registered

## 11. Python API Changes for Client Projects

These changes affect Python code that imports from or uses pipelex.

### Refactoring of `StuffContent` Subclasses

The monolithic `pipelex.core.stuffs.stuff_content` module has been split into individual files for each core content type. This improves modularity and clarity.

**You must update your imports for these classes:**

| Class Name | Old Import Path | New Import Path |
| :--- | :--- | :--- |
| `StructuredContent` | `pipelex.core.stuffs.stuff_content` | `pipelex.core.stuffs.structured_content` |
| `TextContent` | `pipelex.core.stuffs.stuff_content` | `pipelex.core.stuffs.text_content` |
| `ImageContent` | `pipelex.core.stuffs.stuff_content` | `pipelex.core.stuffs.image_content` |
| `ListContent` | `pipelex.core.stuffs.stuff_content` | `pipelex.core.stuffs.list_content` |
| `PDFContent` | `pipelex.core.stuffs.stuff_content` | `pipelex.core.stuffs.pdf_content` |
| `PageContent` | `pipelex.core.stuffs.stuff_content` | `pipelex.core.stuffs.page_content` |
| `NumberContent` | `pipelex.core.stuffs.stuff_content` | `pipelex.core.stuffs.number_content` |
| `HtmlContent` | `pipelex.core.stuffs.stuff_content` | `pipelex.core.stuffs.html_content` |
| `MermaidContent` | `pipelex.core.stuffs.stuff_content` | `pipelex.core.stuffs.mermaid_content` |
| `TextAndImagesContent` | `pipelex.core.stuffs.stuff_content` | `pipelex.core.stuffs.text_and_images_content` |

**Example Migration:**

**Before:**
```python
from pipelex.core.stuffs.stuff_content import StructuredContent, TextContent, ImageContent

class MyData(StructuredContent):
    text_field: TextContent
    image_field: ImageContent
```

**After:**
```python
from pipelex.core.stuffs.structured_content import StructuredContent
from pipelex.core.stuffs.text_content import TextContent
from pipelex.core.stuffs.image_content import ImageContent

class MyData(StructuredContent):
    text_field: TextContent
    image_field: ImageContent
```

### Core Module Relocations

Several core modules related to pipe execution and input handling have been moved to more logical packages.

#### Pipe Execution (`pipe_works` → `pipe_run`)

The `pipelex.pipe_works` package has been renamed to `pipelex.pipe_run`. Additionally, `PipeRunParams` and its factory have been moved into this new package.

| Old Path | New Path | Description |
| :--- | :--- | :--- |
| `pipelex.core.pipes.pipe_run_params` | `pipelex.pipe_run.pipe_run_params` | Contains `PipeRunParams`, `PipeRunMode`, etc. |
| `pipelex.core.pipes.pipe_run_params_factory` | `pipelex.pipe_run.pipe_run_params_factory` | Factory for creating `PipeRunParams`. |
| `pipelex.pipe_works.pipe_router_protocol` | `pipelex.pipe_run.pipe_router_protocol` | The abstract protocol for the pipe router. |

**Example Migration:**

**Before:**
```python
from pipelex.core.pipes.pipe_run_params import PipeRunParams
from pipelex.pipe_works.pipe_router_protocol import PipeRouterProtocol
```

**After:**
```python
from pipelex.pipe_run.pipe_run_params import PipeRunParams
from pipelex.pipe_run.pipe_router_protocol import PipeRouterProtocol
```

#### Pipe Input Specifications (`pipe_input` → `input_requirements`)

Modules for defining pipe inputs have been renamed for clarity. The main class `PipeInputSpec` is now `InputRequirements`.

| Old Path | New Path | Description |
| :--- | :--- | :--- |
| `pipelex.core.pipes.pipe_input` | `pipelex.core.pipes.input_requirements` | Contains `InputRequirements` (formerly `PipeInputSpec`). |
| `pipelex.core.pipes.pipe_input_blueprint` | `pipelex.core.pipes.input_requirement_blueprint` | Contains `InputRequirementBlueprint`. |
| `pipelex.core.pipes.pipe_input_factory` | `pipelex.core.pipes.input_requirements_factory` | Contains `InputRequirementsFactory`. |

**Example Migration:**

**Before:**
```python
from pipelex.core.pipes.pipe_input import PipeInputSpec
from pipelex.core.pipes.pipe_input_factory import PipeInputSpecFactory
```

**After:**
```python
from pipelex.core.pipes.input_requirements import InputRequirements
from pipelex.core.pipes.input_requirements_factory import InputRequirementsFactory
```

#### Comprehensive OCR → Extract Renaming

All modules, classes, and configurations related to `ocr` have been renamed to `extract` to better reflect capabilities beyond OCR.

| Old Path / Name | New Path / Name | Description |
| :--- | :--- | :--- |
| `pipelex.cogt.ocr` | `pipelex.cogt.extract` | Main package for extraction logic. |
| `pipelex.pipe_operators.ocr` | `pipelex.pipe_operators.extract` | Package for the `PipeExtract` operator. |
| `pipelex.cogt.ocr.ocr_input` | `pipelex.cogt.extract.extract_input` | Contains `ExtractInput` (formerly `OcrInput`). |
| `pipelex.cogt.ocr.ocr_job` | `pipelex.cogt.extract.extract_job` | Contains `ExtractJob` (formerly `OcrJob`). |
| `pipelex.cogt.ocr.ocr_worker_abstract` | `pipelex.cogt.extract.extract_worker_abstract` | Contains `ExtractWorkerAbstract`. |

**Example Migration:**

**Before:**
```python
from pipelex.cogt.ocr.ocr_input import OcrInput
from pipelex.cogt.ocr.ocr_worker_abstract import OcrWorkerAbstract
```

**After:**
```python
from pipelex.cogt.extract.extract_input import ExtractInput
from pipelex.cogt.extract.extract_worker_abstract import ExtractWorkerAbstract
```

### Renamed Base Library Pipes

**Find:** `ocr_page_contents_from_pdf`
**Replace with:** `extract_page_contents_from_pdf`

**Find:** `ocr_page_contents_and_views_from_pdf`
**Replace with:** `extract_page_contents_and_views_from_pdf`

**Before:**
```python
pipe_output = await execute_pipeline(
    pipe_code="ocr_page_contents_from_pdf",
    input_memory={
        "ocr_input": PDFContent(url=pdf_url),
    },
)
```

**After:**
```python
pipe_output = await execute_pipeline(
    pipe_code="extract_page_contents_from_pdf",
    input_memory={
        "document": PDFContent(url=pdf_url),
    },
)
```

### Builder Module Relocation

The pipeline builder has been promoted to a top-level package:

**Old:** `pipelex.libraries.pipelines.builder`
**New:** `pipelex.builder`

**Note:** This change only affects internal Pipelex code. Most users won't need to update anything related to the builder module.

### Core Abstractions (`Provider` → `Library`)

The abstract base classes for core components have been renamed for consistency. Hub accessor methods have been updated accordingly.

| Old Class Name | New Class Name | Hub Accessor Method |
| :--- | :--- | :--- |
| `ConceptProviderAbstract` | `ConceptLibraryAbstract` | `get_concept_library()` |
| `DomainProviderAbstract` | `DomainLibraryAbstract` | `get_domain_library()` |
| `PipeProviderAbstract` | `PipeLibraryAbstract` | `get_pipe_library()` |

**Example Migration:**

**Before:**
```python
from pipelex.core.concepts.concept_provider_abstract import ConceptProviderAbstract
concept_provider = hub.get_concept_provider()
```

**After:**
```python
from pipelex.core.concepts.concept_library_abstract import ConceptLibraryAbstract
concept_library = hub.get_concept_library()
```

### Templating Refactoring

The `pipelex.tools.templating` package has been refactored:

- Core logic now resides in `pipelex.cogt.templating`
- Jinja2-specific utilities are in `pipelex.tools.jinja2`

**Example Migration:**

**Before:**
```python
from pipelex.tools.templating.template_processor import TemplateProcessor
```

**After:**
```python
from pipelex.cogt.templating.template_processor import TemplateProcessor
```

### Removed Methods and Classes

The following methods and classes have been removed. If your code uses them, you'll need to refactor:

- `PipeLibrary.add_or_update_pipe()` - Removed
- `PipelexHub.get_optional_library_manager()` - Removed
- Hub methods: `get_optional_domain_provider()` and `get_optional_concept_provider()` - Removed

### Hub Method Renames

If you use hub methods directly:

**Find:** `get_*_provider()`
**Replace with:** `get_*_library()`

**Find:** `set_*_provider()`
**Replace with:** `set_*_library()`

### External Plugin API Changes

If you're using external LLM plugins:

**Find:** `llm_handle` parameter
**Replace with:** `model` parameter

**Before:**
```python
get_inference_manager().set_llm_worker_from_external_plugin(
    llm_handle="my_custom_llm",
    llm_worker_class=MyLLMWorker,
)
```

**After:**
```python
get_inference_manager().set_llm_worker_from_external_plugin(
    model="my_custom_llm",
    llm_worker_class=MyLLMWorker,
)
```

## 12. File Cleanup

### Remove Deprecated Files

Remove the following files if they exist in your project:

```bash
# Remove old template file (moved to .pipelex/pipelex.toml)
rm -f pipelex_libraries/templates/base_templates.toml
rm -rf pipelex_libraries/templates/  # If empty after removal
```

### Update Documentation Files

If your project has `AGENTS.md` or `CLAUDE.md` files with Pipelex examples:

1. Update all PLX syntax examples following sections 1-8 of this guide
2. Update Python code examples following section 10
3. Search for and update:
   - `ocr_page_contents_from_pdf` → `extract_page_contents_from_pdf`
   - `type = "PipeOcr"` → `type = "PipeExtract"`
   - `ocr_model` → `model`
   - `llm = ` → `model = `
   - `prompt_template = ` → `prompt = `

## 13. Common Issues

### Issue: Pipeline validation fails with "unknown field"

**Cause:** You may have used an old field name (e.g., `prompt_template`, `jinja2`, `llm`, `ocr_model`).

**Solution:** Search your .plx files for the old field names and replace them according to this guide.

### Issue: Tests fail with marker errors

**Cause:** Test markers haven't been updated from `ocr` to `extract`.

**Solution:** Update all `@pytest.mark.ocr` to `@pytest.mark.extract`.

### Issue: Configuration not loading

**Cause:** Configuration files still use old section names (e.g., `[presets.ocr]`).

**Solution:** Rename sections and fields in your .pipelex/ configuration files.

### Issue: Import errors for renamed classes

**Cause:** Code imports classes that were renamed (e.g., `ConceptProviderAbstract`).

**Solution:** Update imports to use new names (`ConceptLibraryAbstract`, etc.) or refactor to avoid using internal classes.

### Issue: base_templates.toml not found

**Cause:** The `base_templates.toml` file has been removed. Generic prompts moved to `.pipelex/pipelex.toml`.

**Solution:** Remove references to this file. The templates are now auto-loaded from the config.

### Issue: ImportError for StuffContent subclasses

**Cause:** Imports still use the old monolithic `pipelex.core.stuffs.stuff_content` module.

**Solution:** Update imports to use individual modules. See Section 11 for the complete mapping table.

**Example:**
```python
# Old (will fail)
from pipelex.core.stuffs.stuff_content import StructuredContent, TextContent

# New (correct)
from pipelex.core.stuffs.structured_content import StructuredContent
from pipelex.core.stuffs.text_content import TextContent
```

### Issue: ImportError for pipe execution classes

**Cause:** Code imports from old `pipelex.pipe_works` package or old pipe input modules.

**Solution:** Update to use new package names:
- `pipelex.pipe_works` → `pipelex.pipe_run`
- `pipelex.core.pipes.pipe_input` → `pipelex.core.pipes.input_requirements`
- `PipeInputSpec` → `InputRequirements`

### Issue: ImportError for OCR-related classes

**Cause:** Code still imports from `pipelex.cogt.ocr` or `pipelex.pipe_operators.ocr`.

**Solution:** Update all OCR imports to Extract:
- `pipelex.cogt.ocr` → `pipelex.cogt.extract`
- `pipelex.pipe_operators.ocr` → `pipelex.pipe_operators.extract`
- All class names: `Ocr*` → `Extract*`

## 14. Automation Tools

You can automate many of these text replacements using standard tools available on your platform:

### Available Tools by Platform

**Unix/Linux/macOS:**
- `sed` - Stream editor for find/replace in files
- `find` - Locate files and execute commands on them
- `grep` - Search for patterns in files

**Windows:**
- PowerShell's `Get-Content` and `-replace` operator
- Git Bash (includes Unix tools)
- WSL (Windows Subsystem for Linux)

### What Can Be Automated

The following replacements can be done with find/replace tools:

**In `.plx` files:**
- `definition = "` → `description = "`
- `type = "PipeJinja2"` → `type = "PipeCompose"`
- `type = "PipeOCR"` → `type = "PipeExtract"`
- `prompt_template = ` → `prompt = `
- `jinja2 = ` → `template = `
- `ocr_model = ` → `model = `
- `[pipe.X.pipe_map]` → `[pipe.X.outcomes]`
- `default_pipe_code = ` → `default_outcome = `

**In `.py` files:**
- `ocr_page_contents_from_pdf` → `extract_page_contents_from_pdf`
- Remove `relative_config_folder_path` parameters from `Pipelex.make()`
- Remove `config_folder_path` parameters from `Pipelex.make()`
- `from pipelex.core.stuffs.stuff_content import` → Update to specific module imports
- `from pipelex.pipe_works` → `from pipelex.pipe_run`
- `from pipelex.core.pipes.pipe_input` → `from pipelex.core.pipes.input_requirements`
- `from pipelex.cogt.ocr` → `from pipelex.cogt.extract`
- `PipeInputSpec` → `InputRequirements`
- `ConceptProviderAbstract` → `ConceptLibraryAbstract`
- `DomainProviderAbstract` → `DomainLibraryAbstract`
- `PipeProviderAbstract` → `PipeLibraryAbstract`
- `.get_*_provider()` → `.get_*_library()`
- `.set_*_provider()` → `.set_*_library()`

**In `.toml` files:**
- `llm_handle = ` → `model = `
- `img_gen_handle = ` → `model = `
- `ocr_handle = ` → `model = `
- `[presets.ocr]` → `[presets.extract]`
- `base_ocr_*` → `base_extract_*`

**In test files:**
- `@pytest.mark.ocr` → `@pytest.mark.extract`

### What CANNOT Be Automated

These require manual intervention:

1. Moving `.plx` files to appropriate locations (project-specific)
2. Renaming structure files to `*_struct.py` suffix
3. Adding `@pipe_func()` decorator to custom functions
4. Updating imports to match your new structure
5. Splitting `StuffContent` imports into individual module imports (requires analyzing which classes are used)
6. Adding `default_outcome` to `PipeCondition` pipes
7. Tagging image inputs in `PipeLLM` prompts with `$` or `@`
8. Reviewing and testing all changes

### Recommendation

1. **Test incrementally:** Apply changes to one file type at a time
2. **Use version control:** Commit before migrating so you can revert if needed
3. **Activate your virtual environment** before running Pipelex commands
4. **Validate after each change** (see Validation section)

## 15. Additional Resources

- See AGENTS.md for complete documentation of the current syntax
- Run `make validate` frequently to catch issues early
- Check the test files in `tests/test_pipelines/` for examples of the new syntax

## Support

If you encounter issues during migration:
1. Check that all old field names have been replaced
2. Run `make validate` to see specific error messages
3. Review the examples in AGENTS.md
4. Check that required fields like `default_outcome` are present

