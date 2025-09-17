# Building Pipelex Pipelines from Drafts

This guide explains how to translate a markdown pipeline draft into a formal `PipelexBundleBlueprint` structure that can be validated and executed by Pipelex.

## Overview

1. Convert the draft's narrative flow into a formal domain/concepts/pipes structure
2. Map draft notation to specific pipe types and configurations
3. Ensure all working memory references are properly captured in operator pipe inputs (wrapping up input requirements for controller pipes will be done later)

## Translation Workflow

### Step 1: Extract Domain Information

Create the blueprint root:
```json
{
  "domain": "domain_name",
  "definition": "What this pipeline does"
}
```

### Step 2: Identify and Define Concepts

Review the draft for all data types mentioned:

- **Input variables** → Concepts needed
- **Intermediate results** → Concepts needed
- **Final output** → Concept needed

#### Concept Rules

1. **Use native concepts when possible**:
   - `Text`, `Image`, `PDF`, `TextAndImages`, `Number`, `Page`, `LLMPrompt`
   - Don't redefine these

2. **Use library concepts when applicable**:
   - `documents.TextAndImagesContent`
   - `images.VisualDescription`
   - `images.ImgGenPrompt`
   - `images.Photo`

3. **Create domain concepts for specialized data**:
   - Use PascalCase: `Analysis`, `TechnicalReport`, `UserQuery`
   - Never use plurals: `Document` not `Documents`
   - Never use circumstantial names: `Photo` not `InputPhoto`
   - Avoid adjectives: `Text` not `LongText`

#### Concept Definition Formats

Quick form (for simple text-based concepts):
```json
"concept": {
  "UserQuery": "Natural language question from a user",
  "Summary": "Condensed version of content"
}
```

Full form (when structure or refinement needed):
```json
"concept": {
  "TechnicalAnalysis": {
    "definition": "Technical analysis of a system",
    "refines": "Text"
  }
}
```

### Step 3: Translate Flow Steps to Pipes

Map each step from your draft to the appropriate pipe type and configuration.

#### Operator Mappings

| Draft Notation | Pipe Type | Key Configuration |
|---------------|-----------|-------------------|
| `LLM[purpose]: (inputs) → output` | `PipeLLM` | Set `prompt_template` or `prompt` |
| `OCR: (document) → pages` | `PipeOcr` | Input must be named `ocr_input` |
| `ImgGen: (prompt) → image` | `PipeImgGen` | Configure image generation settings |
| `Func[name]: (data) → result` | `PipeFunc` | Reference Python function |

#### Controller Mappings

| Draft Pattern | Pipe Type | Structure |
|--------------|-----------|-----------|
| Sequential steps (Step 1, Step 2...) | `PipeSequence` | Use `steps` array |
| Process each item in list | `PipeSequence` step with batch | Add `batch_over` and `batch_as` to step |
| Parallel branches (Branch A, Branch B...) | `PipeParallel` | Use `parallels` array |
| Conditional routing (Case "x"...) | `PipeCondition` | Use `expression` and `pipe_map` |

### Step 4: Configure Each Pipe

#### PipeLLM Configuration

From draft step:
```markdown
### Step: Analyze document for key insights
LLM[analyze]: (document, criteria) → analysis
```

To blueprint:
```json
"analyze_document": {
  "type": "PipeLLM",
  "definition": "Analyze document for key insights",
  "inputs": {
    "document": "Text",
    "criteria": "Text"
  },
  "output": "Analysis",
  "prompt_template": "Analyze the following document based on the provided criteria.\n\n@document\n\n@criteria"
}
```

**Prompt Template Rules**:

- Use `@variable` for block content (multi-line)
- Use `$variable` for inline content (within sentences)

#### PipeOcr Configuration

From draft step:
```markdown
### Step: Extract content from PDF
OCR: (document) → pages
```

To blueprint:
```json
"extract_pages": {
  "type": "PipeOcr",
  "definition": "Extract content from PDF",
  "inputs": {
    "ocr_input": "PDF"  // Must be named ocr_input
  },
  "output": "Page",  // Output is always Page concept
  "page_images": true,
  "page_views": true
  "ocr_handle": "mistral/mistral-ocr-latest"
}
```

#### PipeSequence Configuration

From draft sequence:
```markdown
Step 1: Extract information
extract_info(document) → key_info

Step 2: Analyze information
analyze(key_info) → analysis
```

To blueprint:
```json
"process_document": {
  "type": "PipeSequence",
  "definition": "Extract and analyze document",
  "inputs": {
    "document": "Text"
  },
  "output": "Analysis",
  "steps": [
    {
      "pipe": "extract_info",
      "result": "key_info"
    },
    {
      "pipe": "analyze_info",
      "result": "analysis"
    }
  ]
}
```

#### Batch Processing Configuration

From draft batch:
```markdown
Process each item in documents:
analyze_document(document) → analysis
```

To blueprint step within PipeSequence:
```json
{
  "pipe": "analyze_single",
  "batch_over": "documents",
  "batch_as": "document",
  "result": "analyses"
}
```
Using the above, the required input used is `documents`, and by looping on the items of that list, each one will be named `document`, and that's how it will be received in the `analyze_single` pipe.

#### PipeCondition Configuration

From draft conditional:
```markdown
Route based on category:
Case "technical": analyze_technical(document) → analysis
Case "legal": analyze_legal(document) → analysis
```

To blueprint:
```json
"route_analysis": {
  "type": "PipeCondition",
  "definition": "Route document to appropriate analyzer",
  "inputs": {
    "document": "Text",
    "category": "Text"
  },
  "output": "Analysis",
  "expression": "category",
  "pipe_map": {
    "technical": "analyze_technical",
    "legal": "analyze_legal"
  }
}
```

## Complete Example: Draft to Blueprint

### Draft (Markdown)

```markdown
# Pipeline: document_insights
Domain: analysis
Purpose: Extract insights from documents based on criteria

## Inputs
- `document` : Document to analyze
- `criteria` : Analysis criteria

## Flow

### Step 1: Extract key information
LLM[extract]: (document) → key_points

### Step 2: Analyze against criteria
LLM[analyze]: (key_points, criteria) → insights

## Output
Returns: `insights`
```

### Blueprint (JSON)

```json
{
  "domain": "analysis",
  "definition": "Extract insights from documents based on criteria",
  "concept": {
    "KeyPoints": "Important information extracted from document",
    "Insights": "Analysis results based on specific criteria"
  },
  "pipe": {
    "document_insights": {
      "type": "PipeSequence",
      "definition": "Extract and analyze document insights",
      "output": "Insights",
      "steps": [
        {
          "pipe": "extract_key_points",
          "result": "key_points"
        },
        {
          "pipe": "analyze_points",
          "result": "insights"
        }
      ]
    },
    "extract_key_points": {
      "type": "PipeLLM",
      "definition": "Extract key information",
      "inputs": {
        "document": "Text"
      },
      "output": "KeyPoints",
      "prompt_template": "Extract the key points from this document.\n\n@document"
    },
    "analyze_points": {
      "type": "PipeLLM",
      "definition": "Analyze against criteria",
      "inputs": {
        "key_points": "KeyPoints",
        "criteria": "Text"
      },
      "output": "Insights",
      "prompt_template": "Analyze these key points against the provided criteria.\n\n@key_points\n\n@criteria"
    }
  }
}
```

## Validation Checklist

Before finalizing your blueprint:

- [ ] Domain is defined with a single word or snake_case code
- [ ] All concepts follow naming conventions (PascalCase, no plurals, no adjectives, no circumstantial names)
- [ ] Native concepts are not redefined
- [ ] Each pipe has `type`, `definition`, `inputs`, and `output`
- [ ] Controller pipes don't need to declare inputs, they will be inferred from the blueprint
- [ ] OCR pipes use `ocr_input` as the input variable name
- [ ] Batch operations specify both `batch_over` and `batch_as`
- [ ] Variable names are semantic (describe what they are, not their role)
- [ ] All referenced sub-pipes exist in the blueprint
- [ ] Prompt templates use `@` for blocks and `$` for inline content

## Common Pitfalls to Avoid

2. **Wrong OCR input name**: Must be `ocr_input`, not `document` or `pdf`
3. **Redefining native concepts**: Use `Text` directly, don't create `MyText`
4. **Circumstantial naming**: Use `Photo` not `InputPhoto`, `Analysis` not `FinalAnalysis`
5. **Missing result names**: Each step in a sequence should specify its `result` name
6. **Inconsistent variable names**: The same data should have the same name throughout
