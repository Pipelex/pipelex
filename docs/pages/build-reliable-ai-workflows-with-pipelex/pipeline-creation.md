# Pipeline Creation

Pipelex provides powerful tools to automatically generate complete, working pipelines from natural language requirements. This feature leverages AI to translate your ideas into fully functional pipeline code, dramatically speeding up development.

## Overview

The pipeline creation system creates a fully working pipeline that has been both statically and dynamically validated. The system automatically handles all aspects of pipeline generation, from understanding requirements to producing executable code.

!!! warning "Execution Time"
    Pipeline generation can take 4 to 7 minutes to complete, as the system performs comprehensive validation and testing to ensure the pipeline works correctly.

## Core Commands

### Build Blueprint

Generate a complete pipeline blueprint from requirements:

```bash
pipelex build blueprint "BRIEF IN NATURAL LANGUAGE" [OPTIONS]
```

**Example:**
```bash
pipelex build blueprint "Take a photo as input, and render the opposite of the photo" \
  -c your/path/to/pipelex/libraries \
  -o output/pipeline/file/path
```

**Options:**
- `--output, -o`: Output path for generated files
- `--config, -c`: Path to libraries folder

## Complete Workflow

### 1. Requirements Analysis

Start with clear, specific requirements:

```text
Take a photo as input, and render the opposite of the photo
```

