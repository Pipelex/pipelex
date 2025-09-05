# Pipeline Creation

Pipelex provides powerful tools to automatically generate pipeline blueprints from natural language requirements. This feature leverages AI to translate your ideas into working pipeline code, dramatically speeding up development.

## Overview

The pipeline creation system works in several stages:

1. **Draft Generation**: Convert natural language requirements into structured markdown drafts
2. **Blueprint Creation**: Transform drafts into formal pipeline blueprints (PLX format)
3. **Validation**: Automatically validate and fix common issues
4. **Implementation**: Generate executable pipeline code

## Core Commands

### Build Blueprint

Generate a complete pipeline blueprint from requirements:

```bash
pipelex build blueprint PIPELINE_NAME --requirements "REQUIREMENTS_TEXT" [OPTIONS]
```

**Example:**
```bash
pipelex build blueprint gen_photopposite \
  --requirements "Take a photo as input, analyze its content and its most important feature, imagine the opposite to that feature, render it as a photo" \
  -c pipelex/libraries \
  -o pipelex/libraries/pipelines/temp/result_4/photopposite \
  --validate
```

**Options:**
- `--domain, -d`: Domain for the pipeline (default: "wip_domain")
- `--requirements, -r`: Requirements text directly
- `--file, -f`: Path to file containing requirements
- `--output, -o`: Output path for generated files
- `--validate`: Validate the generated blueprint
- `--config-folder-path, -c`: Path to libraries folder

### Build Draft

Generate just a pipeline draft (intermediate step):

```bash
pipelex build draft PIPELINE_NAME --requirements "REQUIREMENTS_TEXT" [OPTIONS]
```

**Options:**
- `--raw`: Generate raw text draft instead of structured draft
- All other options same as blueprint command

### Validate Blueprint

Validate an existing blueprint file:

```bash
pipelex validate blueprint BLUEPRINT_PATH [OPTIONS]
```

**Example:**
```bash
pipelex validate blueprint pipelex/libraries/pipelines/temp/result_3/photopposite.plx \
  -c pipelex/libraries
```

**Options:**
- `--config-folder-path, -c`: Path to libraries folder
- `--fix/--no-fix, -f/-F`: Enable/disable automatic error fixing (default: enabled)

## Complete Workflow

### 1. Requirements Analysis

Start with clear, specific requirements:

```text
Take a photo as input, analyze its content and its most important feature, 
imagine the opposite to that feature, render it as a photo
```

### 2. Draft Generation

The system first creates a structured markdown draft:

```markdown
# Pipeline: gen_photopposite
Domain: image_processing
Purpose: Generate opposite version of photo's main feature

## Inputs
- `photo` : Input photo to analyze and transform

## Flow

WorkingMemory starts with: {photo}

### Step 1: Analyze photo content
LLM[analyze]: (photo) → analysis

WorkingMemory now contains: {photo, analysis}

### Step 2: Generate opposite concept
LLM[conceptualize]: (analysis) → opposite_concept

WorkingMemory now contains: {photo, analysis, opposite_concept}

### Step 3: Render opposite photo
ImgGen: (opposite_concept) → opposite_photo

WorkingMemory now contains: {photo, analysis, opposite_concept, opposite_photo}

## Output
Returns: `opposite_photo` - Photo showing opposite of main feature
```

### 3. Blueprint Creation

The draft is converted into a formal PLX blueprint:

```plx
domain = "image_processing"
definition = "Generate opposite version of photo's main feature"

[concept]
PhotoAnalysis = "Analysis of photo content and main features"
OppositePhotoPrompt = "Prompt for generating opposite version of photo"

[pipe.gen_photopposite]
type = "PipeSequence"
definition = "Generate opposite version of photo's main feature"
output = "Image"
steps = [
    { pipe = "analyze_photo", result = "analysis" },
    { pipe = "create_opposite_concept", result = "opposite_concept" },
    { pipe = "render_opposite", result = "opposite_photo" }
]

[pipe.analyze_photo]
type = "PipeLLM"
definition = "Analyze photo content and identify main feature"
inputs = { photo = "Image" }
output = "PhotoAnalysis"
prompt_template = """
Analyze this photo and identify its most important visual feature.

@photo

Focus on the dominant element, color, mood, or characteristic that defines this image.
"""

[pipe.create_opposite_concept]
type = "PipeLLM"
definition = "Create concept for opposite version"
inputs = { analysis = "PhotoAnalysis" }
output = "OppositePhotoPrompt"
prompt_template = """
Based on this photo analysis, create a detailed prompt for generating the opposite version.

@analysis

Describe what the opposite would look like, focusing on reversing the main feature while maintaining photo realism.
"""

[pipe.render_opposite]
type = "PipeImgGen"
definition = "Generate the opposite photo"
inputs = { opposite_concept = "OppositePhotoPrompt" }
output = "Image"
```

### 4. Validation and Fixing

The system automatically:

- **Validates syntax**: Ensures PLX structure is correct
- **Checks concepts**: Verifies all concepts are properly defined
- **Validates inputs**: Ensures all pipe inputs are available
- **Fixes errors**: Automatically adds missing inputs or corrects common issues
- **Dry runs**: Tests pipeline execution without making API calls

## Generated Files

When you run the build command, several files are created:

```
output_path_base_draft.md      # Original markdown draft
output_path_base_rough.plx    # Initial blueprint
output_path_base_rough.json    # Blueprint in JSON format
output_path_base_fixed.plx    # Validated and fixed blueprint (if --validate used)
output_path_base_fixed.json    # Fixed blueprint in JSON format
```

## Best Practices

### Writing Requirements

**Good requirements:**
```text
Analyze a PDF document, extract key financial data, and generate a summary report with charts
```

**Better requirements:**
```text
Take a PDF financial statement as input, use OCR to extract text and tables, 
identify revenue, expenses, and profit figures, then generate a structured 
summary report with visual charts showing trends
```

### Domain Selection

Choose descriptive domain names:
- `financial_analysis` instead of `finance`
- `document_processing` instead of `docs`
- `image_generation` instead of `images`

### Output Path Organization

Organize generated pipelines:
```
pipelex/libraries/pipelines/
  temp/                    # Temporary/experimental pipelines
    result_1/
    result_2/
  domain_name/            # Production pipelines
    pipeline_name.plx
    structures.py
```

## Advanced Features

### Custom Templates

The system uses built-in templates from:
- `.pipelex/create/draft_pipelines.md` - Drafting guidelines
- `.pipelex/create/build_pipelines.md` - Blueprint creation rules

### Error Fixing

The validation system can automatically fix:
- Missing input variables
- Incorrect concept references
- Malformed pipe definitions
- Input/output mismatches

### Integration with Existing Libraries

Generated blueprints automatically integrate with:
- Native concepts (`Text`, `Image`, `PDF`, etc.)
- Library concepts (`documents.TextAndImages`, etc.)
- Custom domain concepts

## Troubleshooting

### Common Issues

**"Missing input variable" error:**
- Usually fixed automatically with `--validate`
- Check that all pipe inputs are available in WorkingMemory

**"Invalid concept" error:**
- Ensure concept names use PascalCase
- Don't redefine native concepts
- Avoid plurals in concept names

**"Pipe not found" error:**
- Check that all referenced pipes exist in the blueprint
- Verify pipe names match exactly

### Getting Help

```bash
# Validate your entire setup
pipelex validate all -c path/to/your/pipelex/config/folder

# Test a specific pipe
pipelex validate pipe your_pipe_name -c path/to/your/pipelex/config/folder

# Check blueprint structure
pipelex validate blueprint your_blueprint.plx -c path/to/your/pipelex/config/folder --no-fix
```

## Next Steps

After creating your blueprint:

1. **Review the generated code** - Check that it matches your requirements
2. **Create structure classes** - Add Python classes for custom concepts if needed
3. **Test the pipeline** - Run validation and dry runs
4. **Execute the pipeline** - Use `execute_pipeline()` to run it with real data
5. **Iterate and improve** - Refine based on results

The pipeline creation system makes it easy to go from idea to working code in minutes, while maintaining the full power and flexibility of Pipelex pipelines.
