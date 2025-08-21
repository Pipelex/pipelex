# Defining Structures for Pipelex Pipelines

This guide explains how to define schemas and enums for structured data generation in multi-step workflows. This step occurs between drafting pipelines (see `draft_pipelines.md`) and building them (see `build_pipelines.md`).

## When to Define Structures

After drafting your pipeline but before building it, review your draft for:

1. **Complex data that needs validation**: When your pipeline generates structured information that must follow specific formats
2. **Multi-field outputs**: When a single "result" actually contains multiple related pieces of information
3. **Constrained values**: When fields can only have specific allowed values
4. **Reusable data types**: When the same structure appears in multiple places

## Structure Definition Workflow

### Step 1: Identify Structure Needs from Draft

Review your pipeline draft and look for:

```markdown
# Example draft excerpt
LLM[analyze]: (document) → analysis_report
LLM[extract]: (page) → contact_info
LLM[classify]: (query) → support_category
```

Ask yourself:
- What specific fields does `analysis_report` contain?
- What format should `contact_info` follow?
- What are the valid values for `support_category`?

### Step 2: Design Schema Definitions

Create a TOML file defining your structures using the syntax from `structured_output_generator.py`.

## Structure Definition Syntax

### Basic Structure Definition

```toml
[structure.ModelName]
definition = "Clear description of what this represents"

[structure.ModelName.fields]
field_name = "Field description"
another_field = { type = "text", definition = "More detailed field", required = true }
```

### Field Types

| Type | Description | Example |
|------|-------------|---------|
| `text` | String content | `name = "Person's full name"` |
| `number` | Floating point | `score = { type = "number", definition = "Confidence score" }` |
| `integer` | Whole numbers | `count = { type = "integer", definition = "Number of items" }` |
| `boolean` | True/false | `active = { type = "boolean", definition = "Is active" }` |
| `list` | Array of items | `tags = { type = "list", item_type = "text", definition = "List of tags" }` |
| `dict` | Key-value pairs | `metadata = { type = "dict", key_type = "text", value_type = "text" }` |

### Field Configuration Options

```toml
# Required field (must be provided)
title = { type = "text", definition = "Document title", required = true }

# Optional field with default value
priority = { type = "integer", definition = "Priority level", default = 1 }

# List with specific item type
categories = { type = "list", item_type = "text", definition = "Document categories" }
```

## Enum Definition Syntax

### Simple Enum (List of Values)

```toml
[enum.Priority]
definition = "Task priority levels"
values = ["low", "medium", "high", "urgent"]
```

### Descriptive Enum (Key-Value Pairs)

```toml
[enum.DocumentType]
definition = "Types of documents we can process"

[enum.DocumentType.values]
technical = "Technical documentation and manuals"
legal = "Legal contracts and agreements"
financial = "Financial reports and statements"
marketing = "Marketing materials and content"
```

### Using Enums in Structures

```toml
# Reference defined enum
status = { type = "Priority", definition = "Current priority level" }

# Inline choices for simple cases
size = { choices = ["S", "M", "L", "XL"], definition = "Available sizes" }
```

## Complete Example: Document Analysis Pipeline

### From Draft to Structures

**Original Draft Step:**
```markdown
### Step 2: Extract structured information from each page
LLM[extract]: (page) → page_info

### Step 3: Classify document type and priority
LLM[classify]: (document_content) → document_metadata

### Step 4: Generate comprehensive analysis
LLM[analyze]: (page_info_list, document_metadata) → final_analysis
```

**Structure Definition (document_analysis_structures.toml):**

```toml
# Enums for constrained values
[enum.DocumentType]
definition = "Types of documents we can process"
values = ["technical", "legal", "financial", "marketing", "general"]

[enum.Priority]
definition = "Document processing priority"
values = ["low", "medium", "high", "urgent"]

[enum.ConfidenceLevel]
definition = "AI confidence in extraction"

[enum.ConfidenceLevel.values]
low = "Low confidence - manual review recommended"
medium = "Medium confidence - spot check suggested"  
high = "High confidence - likely accurate"

# Structures for structured data
[structure.PageInfo]
definition = "Structured information extracted from a document page"

[structure.PageInfo.fields]
page_number = { type = "integer", definition = "Page number in document", required = true }
main_content = "Primary text content of the page"
key_points = { type = "list", item_type = "text", definition = "Important points found on page" }
entities = { type = "list", item_type = "text", definition = "Named entities (people, organizations, etc.)" }
confidence = { type = "ConfidenceLevel", definition = "Confidence in extraction quality" }

[structure.DocumentMetadata]
definition = "High-level document classification and properties"

[structure.DocumentMetadata.fields]
document_type = { type = "DocumentType", definition = "Classified document type", required = true }
priority = { type = "Priority", definition = "Processing priority", required = true }
title = "Inferred document title"
summary = "Brief document summary"
page_count = { type = "integer", definition = "Total number of pages" }
language = { choices = ["en", "fr", "es", "de"], definition = "Document language" }

[structure.DocumentAnalysis]
definition = "Comprehensive analysis combining all extracted information"

[structure.DocumentAnalysis.fields]
document_metadata = { type = "DocumentMetadata", definition = "Document classification info", required = true }
page_analyses = { type = "list", item_type = "PageInfo", definition = "Analysis for each page", required = true }
overall_insights = { type = "list", item_type = "text", definition = "Key insights across entire document" }
recommendations = { type = "list", item_type = "text", definition = "Recommended actions based on analysis" }
confidence_score = { type = "number", definition = "Overall confidence in analysis (0.0-1.0)" }
```

## Best Practices

### 1. Semantic Naming
- Use **PascalCase** for schema and enum names: `DocumentAnalysis`, `Priority`
- Use **snake_case** for field names: `page_number`, `confidence_score`
- Avoid plurals in schema names: `PageInfo` not `PageInfos`
- Avoid circumstantial names: `Analysis` not `FinalAnalysis`

### 2. Clear Definitions
- Every schema and enum should have a `definition`
- Field descriptions should explain what the field contains, not how it's used
- Use complete sentences for definitions

### 3. Appropriate Constraints
- Mark fields as `required = true` only when they're always expected
- Use enums for fields with limited, known values
- Use inline `choices` for simple, one-off constraints
- Set reasonable defaults where applicable

### 4. Logical Grouping
- Group related fields into the same schema
- Don't create overly granular schemas for simple data
- Consider if a field should be separate or part of a larger structure

### 5. Reusability
- Design schemas to be reusable across different pipes
- Create enums for values that appear in multiple contexts
- Avoid pipeline-specific naming in reusable structures

## Integration with Pipeline Building

### Updating Concept Definitions

After defining structures, update your pipeline blueprint concepts to reference the structure definitions:

**Simple approach (structure name matches concept name):**
```json
"concept": {
  "PageInfo": "Information extracted from a page",
  "DocumentMetadata": "Document classification data", 
  "DocumentAnalysis": "Complete document analysis"
}
```

**Structure reference approaches:**
```json
"concept": {
  "PageInfo": {
    "definition": "Structured information extracted from a document page",
    "structure": "PageInfo"
  },
  "DocumentMetadata": {
    "definition": "High-level document classification and properties",
    "structure": {
      "document_type": {
        "type": "DocumentType",
        "definition": "Classified document type",
        "required": true
      },
      "priority": {
        "type": "Priority", 
        "definition": "Processing priority",
        "required": true
      },
      "title": "Inferred document title",
      "summary": "Brief document summary",
      "page_count": {
        "type": "integer",
        "definition": "Total number of pages"
      },
      "language": {
        "choices": ["en", "fr", "es", "de"],
        "definition": "Document language"
      }
    }
  },
  "DocumentAnalysis": {
    "definition": "Comprehensive analysis combining all extracted information",
    "structure": "DocumentAnalysis"
  }
}
```

**Structure attribute options:**
- **String reference**: `"structure": "ClassName"` - References a predefined structure class
- **Inline definition**: `"structure": { ... }` - Defines fields directly within the concept
- **Auto-detection**: Omit `structure` entirely - System looks for StructuredContent subclass with matching concept name or falls back on `Text` (i.e. not structured)

### When to Use Each Approach

**Use string reference when:**
- Structure is reusable across multiple concepts or pipelines
- Structure is complex and benefits from being defined in a separate TOML file
- You want to maintain separation between concept definitions and structure details

**Use inline definition when:**
- Structure is specific to this one concept
- Structure is simple and doesn't warrant a separate definition
- You want to keep concept and structure together for clarity
- Rapid prototyping where you don't want to manage separate files

**Use auto-detection when:**
- Concept name exactly matches an existing StructuredContent class
- Working with simple, standard structures that are already registered

### Generating Python Classes

**From TOML files:**
```python
from pipelex.create.structured_output_generator import generate_structured_outputs_from_toml_file

# Generate Python classes from TOML definitions
generate_structured_outputs_from_toml_file(
    "document_analysis_structures.toml",
    "document_analysis.py"
)
```

**From inline definitions (for concept integration):**
```python
from pipelex.create.structured_output_generator import generate_structured_output_from_inline_definition

# Generate from inline field definitions (as used in concept.structure)
fields_def = {
    "document_type": {
        "type": "DocumentType",
        "definition": "Classified document type",
        "required": True
    },
    "priority": {
        "type": "Priority", 
        "definition": "Processing priority",
        "required": True
    },
    "title": "Inferred document title",
    "page_count": {
        "type": "integer",
        "definition": "Total number of pages"
    },
    "language": {
        "choices": ["en", "fr", "es", "de"],
        "definition": "Document language"
    }
}

enums = {
    "DocumentType": {
        "definition": "Types of documents we can process",
        "values": ["technical", "legal", "financial", "marketing", "general"]
    },
    "Priority": {
        "definition": "Document processing priority", 
        "values": ["low", "medium", "high", "urgent"]
    }
}

python_code = generate_structured_output_from_inline_definition(
    "DocumentMetadata", 
    fields_def,
    enums
)
```

## Validation Checklist

Before finalizing your structure definitions:

- [ ] All structure names use PascalCase and are singular
- [ ] All field names use snake_case
- [ ] Every structure and enum has a clear `definition`
- [ ] Required fields are marked appropriately
- [ ] Enums are used for constrained values with known options
- [ ] Field types match the expected data format
- [ ] Structures group related fields logically
- [ ] Structure names are semantic (describe what they are, not how they're used)
- [ ] No native concepts (Text, Image, PDF) are redefined
- [ ] List item types are specified correctly
- [ ] Dictionary key and value types are appropriate

## Common Patterns

### Contact Information
```toml
[structure.ContactInfo]
definition = "Contact information extracted from document"

[structure.ContactInfo.fields]
name = "Full name of contact"
email = "Email address"
phone = "Phone number"
company = "Company or organization name"
address = "Physical address"
```

### Analysis Results
```toml
[enum.Sentiment]
definition = "Sentiment analysis results"
values = ["positive", "negative", "neutral"]

[structure.TextAnalysis]
definition = "Results of text analysis"

[structure.TextAnalysis.fields]
sentiment = { type = "Sentiment", definition = "Overall sentiment", required = true }
key_themes = { type = "list", item_type = "text", definition = "Main themes identified" }
confidence = { type = "number", definition = "Analysis confidence (0.0-1.0)" }
word_count = { type = "integer", definition = "Total word count" }
```

### Classification Results
```toml
[structure.Classification]
definition = "Multi-class classification result"

[structure.Classification.fields]
predicted_class = { type = "text", definition = "Most likely class", required = true }
confidence_scores = { type = "dict", key_type = "text", value_type = "number", definition = "Confidence for each class" }
threshold_met = { type = "boolean", definition = "Whether prediction meets confidence threshold" }
```

This structured approach ensures your pipeline generates well-validated, type-safe data that can be reliably processed by downstream systems.
