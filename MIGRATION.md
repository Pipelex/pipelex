# Migration Guide - Breaking Changes

This guide will help you migrate your Pipelex pipelines and configurations to the latest version.

## Overview

This release introduces several breaking changes to make the Pipelex language more declarative, intuitive, and consistent. The changes affect:
- Pipeline definitions (.plx files)
- Configuration files (.pipelex/ directory)
- Test markers

## Migration Checklist

- [ ] Update PipeCompose (formerly PipeJinja2)
- [ ] Update PipeExtract (formerly PipeOCR)
- [ ] Update PipeLLM prompts and fields
- [ ] Update PipeImgGen fields
- [ ] Update PipeCondition fields
- [ ] Update configuration files
- [ ] Update test markers
- [ ] Run validation

## 1. General Changes

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

## 2. PipeCompose (formerly PipeJinja2)

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

## 3. PipeExtract (formerly PipeOCR)

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

## 4. PipeLLM Changes

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

## 5. PipeImgGen Changes

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

## 6. PipeCondition Changes

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

## 7. Configuration Files (.pipelex/ directory)

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

## 8. Test Markers

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

## 9. Validation

After making all changes, run validation:

```bash
# Fix any unused imports
make fix-unused-imports

# Validate all pipelines
make validate

# Run type checking and linting
make check

# Run tests (non-inference)
make tp
```

## 10. Python API Changes for Client Projects

These changes affect Python code that imports from or uses pipelex.

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

### Removed Methods and Classes

The following methods and classes have been removed. If your code uses them, you'll need to refactor:

- `PipeLibrary.add_or_update_pipe()` - Removed
- `PipelexHub.get_optional_library_manager()` - Removed
- Hub methods: `get_optional_domain_provider()` and `get_optional_concept_provider()` - Removed

### Renamed Internal Classes (if used)

If your project directly imports these internal classes:

- `ConceptProviderAbstract` → `ConceptLibraryAbstract`
- `DomainProviderAbstract` → `DomainLibraryAbstract`
- `PipeProviderAbstract` → `PipeLibraryAbstract`
- `PipeInputSpec` → `InputRequirements`
- `PipeInputSpecFactory` → `InputRequirementsFactory`
- `PipelexError` → `PipelexException` (base exception class)

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

## 11. File Cleanup

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

## 12. Common Issues

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

## 13. Automated Migration Script

You can use this bash script to automatically apply most changes:

```bash
#!/bin/bash

# Find all .plx files and apply replacements
find . -name "*.plx" -type f -exec sed -i '' \
  -e 's/definition = "/description = "/g' \
  -e 's/type = "PipeJinja2"/type = "PipeCompose"/g' \
  -e 's/type = "PipeOCR"/type = "PipeExtract"/g' \
  -e 's/prompt_template = /prompt = /g' \
  -e 's/jinja2 = /template = /g' \
  -e 's/jinja2_name = /template_name = /g' \
  -e 's/ocr_model = /model = /g' \
  -e 's/\[pipe\.\([^.]*\)\.pipe_map\]/[pipe.\1.outcomes]/g' \
  -e 's/default_pipe_code = /default_outcome = /g' \
  {} +

# Update Python files with renamed pipe codes
find . -name "*.py" -type f -exec sed -i '' \
  -e 's/ocr_page_contents_from_pdf/extract_page_contents_from_pdf/g' \
  -e 's/ocr_page_contents_and_views_from_pdf/extract_page_contents_and_views_from_pdf/g' \
  {} +

# Update documentation files
find . \( -name "AGENTS.md" -o -name "CLAUDE.md" \) -type f -exec sed -i '' \
  -e 's/definition = "/description = "/g' \
  -e 's/type = "PipeOcr"/type = "PipeExtract"/g' \
  -e 's/ocr_model = /model = /g' \
  -e 's/ocr_page_contents_from_pdf/extract_page_contents_from_pdf/g' \
  -e 's/ocr_page_contents_and_views_from_pdf/extract_page_contents_and_views_from_pdf/g' \
  {} +

# Find all .toml files in .pipelex and apply replacements
find .pipelex -name "*.toml" -type f -exec sed -i '' \
  -e 's/llm_handle = /model = /g' \
  -e 's/img_gen_handle = /model = /g' \
  -e 's/ocr_handle = /model = /g' \
  -e 's/\[presets\.ocr\]/[presets.extract]/g' \
  -e 's/base_ocr_pypdfium2/base_extract_pypdfium2/g' \
  -e 's/base_ocr_mistral/base_extract_mistral/g' \
  -e 's/ocr_config/extract_config/g' \
  -e 's/is_auto_setup_preset_ocr/is_auto_setup_preset_extract/g' \
  -e 's/nb_ocr_pages/nb_extract_pages/g' \
  {} +

# Find all test files and update markers
find tests -name "*.py" -type f -exec sed -i '' \
  -e 's/@pytest\.mark\.ocr/@pytest.mark.extract/g' \
  {} +

# Remove deprecated files
rm -f pipelex_libraries/templates/base_templates.toml

echo "Automated migration complete. Please review changes and:"
echo "1. Manually add default_outcome to all PipeCondition pipes"
echo "2. Tag image inputs in PipeLLM prompts"
echo "3. Remove nb_steps from PipeImgGen if present"
echo "4. Run 'make validate' to check for errors"
```

**Note:** 
- macOS: Use `sed -i ''` (as shown above)
- Linux: Replace `sed -i ''` with `sed -i`
- Windows: Use Git Bash, WSL, or the PowerShell script below

### Windows PowerShell Migration Script

```powershell
# Find all .plx files and apply replacements
Get-ChildItem -Path . -Filter *.plx -Recurse | ForEach-Object {
    $content = Get-Content $_.FullName -Raw
    $content = $content -replace 'definition = "', 'description = "'
    $content = $content -replace 'type = "PipeJinja2"', 'type = "PipeCompose"'
    $content = $content -replace 'type = "PipeOCR"', 'type = "PipeExtract"'
    $content = $content -replace 'prompt_template = ', 'prompt = '
    $content = $content -replace 'jinja2 = ', 'template = '
    $content = $content -replace 'jinja2_name = ', 'template_name = '
    $content = $content -replace 'ocr_model = ', 'model = '
    $content = $content -replace '\[pipe\.([^.]+)\.pipe_map\]', '[pipe.$1.outcomes]'
    $content = $content -replace 'default_pipe_code = ', 'default_outcome = '
    Set-Content -Path $_.FullName -Value $content -NoNewline
}

# Update Python files with renamed pipe codes
Get-ChildItem -Path . -Filter *.py -Recurse | ForEach-Object {
    $content = Get-Content $_.FullName -Raw
    $content = $content -replace 'ocr_page_contents_from_pdf', 'extract_page_contents_from_pdf'
    $content = $content -replace 'ocr_page_contents_and_views_from_pdf', 'extract_page_contents_and_views_from_pdf'
    Set-Content -Path $_.FullName -Value $content -NoNewline
}

# Find all .toml files in .pipelex and apply replacements
Get-ChildItem -Path .pipelex -Filter *.toml -Recurse | ForEach-Object {
    $content = Get-Content $_.FullName -Raw
    $content = $content -replace 'llm_handle = ', 'model = '
    $content = $content -replace 'img_gen_handle = ', 'model = '
    $content = $content -replace 'ocr_handle = ', 'model = '
    $content = $content -replace '\[presets\.ocr\]', '[presets.extract]'
    $content = $content -replace 'base_ocr_pypdfium2', 'base_extract_pypdfium2'
    $content = $content -replace 'base_ocr_mistral', 'base_extract_mistral'
    $content = $content -replace 'ocr_config', 'extract_config'
    $content = $content -replace 'is_auto_setup_preset_ocr', 'is_auto_setup_preset_extract'
    $content = $content -replace 'nb_ocr_pages', 'nb_extract_pages'
    Set-Content -Path $_.FullName -Value $content -NoNewline
}

# Find all test files and update markers
Get-ChildItem -Path tests -Filter *.py -Recurse | ForEach-Object {
    $content = Get-Content $_.FullName -Raw
    $content = $content -replace '@pytest\.mark\.ocr', '@pytest.mark.extract'
    Set-Content -Path $_.FullName -Value $content -NoNewline
}

# Remove deprecated files
Remove-Item -Path "pipelex_libraries/templates/base_templates.toml" -ErrorAction SilentlyContinue

Write-Host "Automated migration complete. Please review changes and:"
Write-Host "1. Manually add default_outcome to all PipeCondition pipes"
Write-Host "2. Tag image inputs in PipeLLM prompts"
Write-Host "3. Remove nb_steps from PipeImgGen if present"
Write-Host "4. Run 'make validate' to check for errors"
```

## 14. Additional Resources

- See AGENTS.md for complete documentation of the current syntax
- Run `make validate` frequently to catch issues early
- Check the test files in `tests/test_pipelines/` for examples of the new syntax

## Support

If you encounter issues during migration:
1. Check that all old field names have been replaced
2. Run `make validate` to see specific error messages
3. Review the examples in AGENTS.md
4. Check that required fields like `default_outcome` are present

