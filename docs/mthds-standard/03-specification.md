# Specification

<!-- Source document for the MTHDS docs website.
     Each "## Page:" section becomes an individual MkDocs page.

     Normative language follows RFC 2119:
       MUST / MUST NOT  — absolute requirement or prohibition
       SHOULD / SHOULD NOT — recommended but deviations are possible with good reason
       MAY — truly optional
-->

## Page: .mthds File Format

The `.mthds` file is a TOML document that defines typed data (concepts) and typed transformations (pipes) within a single domain. This page is the normative reference for every field, validation rule, and structural constraint of the format.

### File Encoding and Syntax

A `.mthds` file MUST be a valid TOML document encoded in UTF-8. The file extension MUST be `.mthds`. Parsers MUST reject files that are not valid TOML before any MTHDS-specific validation occurs.

### Top-Level Structure

A `.mthds` file is called a **bundle**. It consists of:

1. **Header fields** — top-level key-value pairs that identify the bundle.
2. **Concept definitions** — a `[concept]` table and/or `[concept.<ConceptCode>]` sub-tables.
3. **Pipe definitions** — `[pipe.<pipe_code>]` sub-tables.

All three sections are optional in the TOML sense (an empty `.mthds` file is valid TOML), but a useful bundle will contain at least one concept or one pipe.

### Header Fields

Header fields appear at the top level of the TOML document, before any `[concept]` or `[pipe]` tables.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `domain` | string | Yes | The domain this bundle belongs to. Determines the namespace for all concepts and pipes defined in this file. |
| `description` | string | No | A human-readable description of what this bundle provides. |
| `system_prompt` | string | No | A default system prompt applied to all `PipeLLM` pipes in this bundle that do not define their own `system_prompt`. |
| `main_pipe` | string | No | The pipe code of the bundle's primary entry point. If set, this pipe is auto-exported when the bundle is part of a package. |

**Validation rules:**

- `domain` MUST be a valid domain code (see [Domain Naming Rules](#domain-naming-rules)).
- `main_pipe`, if present, MUST be a valid pipe code (`snake_case`) and MUST reference a pipe defined in this bundle.

**Example:**

```toml
domain      = "legal.contracts"
description = "Contract analysis methods for legal documents"
main_pipe   = "extract_clause"
```

### Domain Naming Rules

Domain codes define the namespace for all concepts and pipes in a bundle.

**Syntax:**

- A domain code is one or more `snake_case` segments separated by `.` (dot).
- Each segment MUST match the pattern `[a-z][a-z0-9_]*`.
- Domains MAY be hierarchical: `legal`, `legal.contracts`, `legal.contracts.shareholder`.

**Reserved domains:**

The following domain names are reserved and MUST NOT be used as the first segment of any user-defined domain:

- `native` — built-in concept types
- `mthds` — reserved for the MTHDS standard
- `pipelex` — reserved for the reference implementation

A compliant implementation MUST reject bundles that declare a domain starting with a reserved segment (e.g., `native.custom` is invalid).

**Recommendations:**

- Depth SHOULD be 1–3 levels.
- Each segment SHOULD be 1–4 words.

### Concept Definitions

Concepts are typed data declarations. They define the vocabulary of a domain — the kinds of data that pipes accept and produce.

#### Simple Concept Declarations

The simplest form of concept declaration uses a flat `[concept]` table where each key is a concept code and the value is a description string:

```toml
[concept]
ContractClause = "A clause extracted from a legal contract"
UserProfile    = "A user's profile information"
```

This form declares concepts with no structure and no refinement. They exist as named types.

#### Structured Concept Declarations

A concept with fields uses a `[concept.<ConceptCode>]` sub-table:

```toml
[concept.LineItem]
description = "A single line item in an invoice"

[concept.LineItem.structure]
product_name = { type = "text", description = "Name of the product", required = true }
quantity     = { type = "integer", description = "Quantity ordered", required = true }
unit_price   = { type = "number", description = "Price per unit", required = true }
```

Both forms MAY coexist in the same bundle. A bundle MAY mix simple declarations in `[concept]` with structured declarations as `[concept.<Code>]` sub-tables.

#### Concept Blueprint Fields

When using the structured form `[concept.<ConceptCode>]`, the following fields are available:

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `description` | string | Yes | Human-readable description of the concept. |
| `structure` | table or string | No | Field definitions for the concept. If a string, it is a shorthand description (equivalent to a simple declaration). If a table, each key is a field name mapped to a field blueprint. |
| `refines` | string | No | A concept reference indicating that this concept is a specialization of another concept. |

**Validation rules:**

- `refines` and `structure` MUST NOT both be present on the same concept. A concept either refines another concept or defines its own structure, not both.
- `refines`, if present, MUST be a valid concept reference: either a bare concept code (`PascalCase`) or a domain-qualified reference (`domain.ConceptCode`). Cross-package references (`alias->domain.ConceptCode`) are also valid.
- Concept codes MUST be `PascalCase`, matching the pattern `[A-Z][a-zA-Z0-9]*`.
- Concept codes MUST NOT collide with native concept codes (see [Native Concepts](#native-concepts)).

#### Concept Refinement

Refinement establishes a specialization relationship between concepts. A concept that refines another inherits its semantic meaning and can be used anywhere the parent concept is expected.

```toml
[concept.NonCompeteClause]
description = "A non-compete clause in an employment contract"
refines     = "ContractClause"
```

The `refines` field accepts:

- A bare concept code: `"ContractClause"` — resolved within the current bundle's domain.
- A domain-qualified reference: `"legal.ContractClause"` — resolved within the current package.
- A cross-package reference: `"acme_legal->legal.contracts.NonDisclosureAgreement"` — resolved from a dependency.

#### Concept Structure Fields

When `structure` is a table, each key is a field name and each value is a field blueprint. Field names MUST NOT start with an underscore (`_`), as these are reserved for internal use. Field names MUST NOT collide with reserved field names (Pydantic model attributes and internal metadata fields).

##### Field Blueprint

Each field in a concept structure is defined by a field blueprint:

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `description` | string | Yes | Human-readable description of the field. |
| `type` | string | Conditional | The field type. Required unless `choices` is provided. |
| `required` | boolean | No | Whether the field is required. Default: `false`. |
| `default_value` | any | No | Default value for the field. Must match the declared type. |
| `choices` | array of strings | No | Fixed set of allowed string values. When `choices` is set, `type` MUST be omitted (the type is implicitly an enum of the given choices). |
| `key_type` | string | Conditional | Key type for `dict` fields. Required when `type = "dict"`. |
| `value_type` | string | Conditional | Value type for `dict` fields. Required when `type = "dict"`. |
| `item_type` | string | No | Item type for `list` fields. When set to `"concept"`, `item_concept_ref` is required. |
| `concept_ref` | string | Conditional | Concept reference for `concept`-typed fields. Required when `type = "concept"`. |
| `item_concept_ref` | string | Conditional | Concept reference for list items when `item_type = "concept"`. |

##### Field Types

The `type` field accepts the following values:

| Type | Description | `default_value` type |
|------|-------------|---------------------|
| `text` | A string value. | `string` |
| `integer` | A whole number. | `integer` |
| `number` | A numeric value (integer or floating-point). | `integer` or `float` |
| `boolean` | A true/false value. | `boolean` |
| `date` | A date value. | `datetime` |
| `list` | An ordered collection. Use `item_type` to specify element type. | `array` |
| `dict` | A key-value mapping. Requires `key_type` and `value_type`. | `table` |
| `concept` | A reference to another concept. Requires `concept_ref`. Cannot have `default_value`. | *(not allowed)* |

When `type` is omitted and `choices` is provided, the field is an enumeration field. The value MUST be one of the strings in the `choices` array.

**Validation rules for field types:**

- `type = "dict"`: `key_type` and `value_type` MUST both be non-empty.
- `type = "concept"`: `concept_ref` MUST be set. `default_value` MUST NOT be set.
- `type = "list"` with `item_type = "concept"`: `item_concept_ref` MUST be set.
- `item_concept_ref` MUST NOT be set unless `item_type = "concept"`.
- `concept_ref` MUST NOT be set unless `type = "concept"`.
- If `choices` is provided and `type` is omitted, `default_value` (if present) MUST be one of the values in `choices`.
- If both `type` and `default_value` are set, the runtime type of `default_value` MUST match the declared `type`.

**Example — concept with all field types:**

```toml
[concept.CandidateProfile]
description = "A candidate's profile for job matching"

[concept.CandidateProfile.structure]
full_name        = { type = "text", description = "Full name", required = true }
years_experience = { type = "integer", description = "Years of professional experience" }
gpa              = { type = "number", description = "Grade point average" }
is_active        = { type = "boolean", description = "Whether actively looking", default_value = true }
graduation_date  = { type = "date", description = "Date of graduation" }
skills           = { type = "list", item_type = "text", description = "List of skills" }
metadata         = { type = "dict", key_type = "text", value_type = "text", description = "Additional metadata" }
seniority_level  = { description = "Seniority level", choices = ["junior", "mid", "senior", "lead"] }
address          = { type = "concept", concept_ref = "Address", description = "Home address" }
references       = { type = "list", item_type = "concept", item_concept_ref = "ContactInfo", description = "Professional references" }
```

### Native Concepts

Native concepts are built-in types that are always available in every bundle without declaration. They belong to the reserved `native` domain.

| Code | Qualified Reference | Description |
|------|-------------------|-------------|
| `Dynamic` | `native.Dynamic` | A dynamically-typed value. |
| `Text` | `native.Text` | A text string. |
| `Image` | `native.Image` | An image (binary). |
| `Document` | `native.Document` | A document (e.g., PDF). |
| `Html` | `native.Html` | HTML content. |
| `TextAndImages` | `native.TextAndImages` | Combined text and image content. |
| `Number` | `native.Number` | A numeric value. |
| `ImgGenPrompt` | `native.ImgGenPrompt` | A prompt for image generation. |
| `Page` | `native.Page` | A single page extracted from a document. |
| `JSON` | `native.JSON` | A JSON value. |
| `Anything` | `native.Anything` | Accepts any type. |

Native concepts MAY be referenced by bare code (`Text`, `Image`) or by qualified reference (`native.Text`, `native.Image`). Bare native concept codes always take priority during resolution.

A bundle MUST NOT declare a concept with the same code as a native concept. A compliant implementation MUST reject such declarations.

### Pipe Definitions

Pipes are typed transformations. Each pipe has a typed signature: it declares what concepts it accepts as input and what concept it produces as output.

#### Common Pipe Fields

All pipe types share these base fields:

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `type` | string | Yes | The pipe type. Determines which category and additional fields are available. |
| `description` | string | Yes | Human-readable description of what this pipe does. |
| `inputs` | table | No | Input declarations. Keys are input names (`snake_case`), values are concept references with optional multiplicity. |
| `output` | string | Yes | The output concept reference with optional multiplicity. |

**Pipe codes:**

- Pipe codes are the keys in `[pipe.<pipe_code>]` tables.
- Pipe codes MUST be `snake_case`, matching the pattern `[a-z][a-z0-9_]*`.

**Input names:**

- Input names MUST be `snake_case`.
- Dotted input names are allowed for nested field access (e.g., `my_input.field_name`), where each segment MUST be `snake_case`.

**Concept references in inputs and output:**

Concept references in `inputs` and `output` support an optional multiplicity suffix:

| Syntax | Meaning |
|--------|---------|
| `ConceptName` | A single instance. |
| `ConceptName[]` | A variable-length list (runtime determines count). |
| `ConceptName[N]` | A fixed-length list of exactly N items (N ≥ 1). |

Concept references MAY be bare codes (`Text`), domain-qualified (`legal.ContractClause`), or cross-package qualified (`alias->domain.ConceptCode`).

**Example:**

```toml
[pipe.analyze_contract]
type        = "PipeLLM"
description = "Analyze a legal contract and extract key clauses"
output      = "ContractClause[5]"

[pipe.analyze_contract.inputs]
contract_text = "Text"
```

#### Pipe Types

MTHDS defines nine pipe types in two categories:

**Operators** — pipes that perform a single transformation:

| Type | Value | Description |
|------|-------|-------------|
| PipeLLM | `"PipeLLM"` | Generates output using a large language model. |
| PipeFunc | `"PipeFunc"` | Calls a registered Python function. |
| PipeImgGen | `"PipeImgGen"` | Generates images using an image generation model. |
| PipeExtract | `"PipeExtract"` | Extracts structured content from documents. |
| PipeCompose | `"PipeCompose"` | Composes output from templates or constructs. |

**Controllers** — pipes that orchestrate other pipes:

| Type | Value | Description |
|------|-------|-------------|
| PipeSequence | `"PipeSequence"` | Executes a series of pipes in order. |
| PipeParallel | `"PipeParallel"` | Executes pipes concurrently. |
| PipeCondition | `"PipeCondition"` | Routes execution based on a condition. |
| PipeBatch | `"PipeBatch"` | Maps a pipe over each item in a list. |

### Operator: PipeLLM

Generates output by invoking a large language model with a prompt.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `type` | `"PipeLLM"` | Yes | — |
| `description` | string | Yes | — |
| `inputs` | table | No | — |
| `output` | string | Yes | — |
| `prompt` | string | No | The LLM prompt template. Supports Jinja2 syntax and the `@variable` / `$variable` shorthand. |
| `system_prompt` | string | No | System prompt for the LLM. If omitted, the bundle-level `system_prompt` is used (if any). |
| `model` | string | No | LLM model choice. Supports named models and routing profiles (prefixed with `$`). |
| `model_to_structure` | string | No | Model used for structuring the LLM output into the declared concept. |
| `structuring_method` | string | No | How the output is structured. Values: `"direct"`, `"preliminary_text"`. |

**Prompt template syntax:**

- `{{ variable_name }}` — standard Jinja2 variable substitution.
- `@variable_name` — shorthand, preprocessed to Jinja2 syntax.
- `$variable_name` — shorthand, preprocessed to Jinja2 syntax.
- Dotted paths are supported: `{{ doc_request.document_type }}`, `@doc_request.priority`.

**Validation rules:**

- Every variable referenced in `prompt` and `system_prompt` MUST correspond to a declared input (by root name). Internal variables starting with `_` and the special names `preliminary_text` and `place_holder` are excluded from this check.
- Every declared input MUST be referenced by at least one variable in `prompt` or `system_prompt`. Unused inputs are rejected.

**Example:**

```toml
[pipe.analyze_cv]
type = "PipeLLM"
description = "Analyze a CV to extract key professional information"
output = "CVAnalysis"
model = "$writing-factual"
system_prompt = """
You are an expert HR analyst specializing in CV evaluation.
"""
prompt = """
Analyze the following CV and extract the candidate's key professional information.

@cv_pages
"""

[pipe.analyze_cv.inputs]
cv_pages = "Page"
```

### Operator: PipeFunc

Calls a registered Python function.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `type` | `"PipeFunc"` | Yes | — |
| `description` | string | Yes | — |
| `inputs` | table | No | — |
| `output` | string | Yes | — |
| `function_name` | string | Yes | The fully-qualified name of the Python function to call. |

**Example:**

```toml
[pipe.capitalize_text]
type          = "PipeFunc"
description   = "Capitalize the input text"
inputs        = { text = "Text" }
output        = "Text"
function_name = "my_package.text_utils.capitalize"
```

### Operator: PipeImgGen

Generates images using an image generation model.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `type` | `"PipeImgGen"` | Yes | — |
| `description` | string | Yes | — |
| `inputs` | table | No | — |
| `output` | string | Yes | — |
| `prompt` | string | Yes | The image generation prompt. Supports Jinja2 and `$variable` shorthand. |
| `negative_prompt` | string | No | A negative prompt (concepts to avoid in generation). |
| `model` | string | No | Image generation model choice. Supports routing profiles (prefixed with `$`). |
| `aspect_ratio` | string | No | Desired aspect ratio for the generated image. |
| `is_raw` | boolean | No | Whether to use raw mode (less post-processing). |
| `seed` | integer or `"auto"` | No | Random seed for reproducibility. `"auto"` lets the model choose. |
| `background` | string | No | Background setting for the generated image. |
| `output_format` | string | No | Image output format (e.g., `"png"`, `"jpeg"`). |

**Validation rules:**

- Every variable referenced in `prompt` MUST correspond to a declared input.

**Example:**

```toml
[pipe.generate_portrait]
type        = "PipeImgGen"
description = "Generate a portrait image from a description"
inputs      = { description = "Text" }
output      = "Image"
prompt      = "A professional portrait: $description"
model       = "$gen-image-testing"
```

### Operator: PipeExtract

Extracts structured content from documents (e.g., PDF pages).

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `type` | `"PipeExtract"` | Yes | — |
| `description` | string | Yes | — |
| `inputs` | table | Yes | MUST contain exactly one input. |
| `output` | string | Yes | MUST be `"Page[]"`. |
| `model` | string | No | Extraction model choice. Supports routing profiles (prefixed with `@`). |
| `max_page_images` | integer | No | Maximum number of page images to process. |
| `page_image_captions` | boolean | No | Whether to generate captions for page images. |
| `page_views` | boolean | No | Whether to generate page views. |
| `page_views_dpi` | integer | No | DPI for page view rendering. |

**Validation rules:**

- `inputs` MUST contain exactly one entry. The input concept SHOULD be `Document` or a concept that refines `Document` or `Image`.
- `output` MUST be `"Page[]"` (a variable-length list of `Page`).

**Example:**

```toml
[pipe.extract_cv]
type        = "PipeExtract"
description = "Extract text content from a CV PDF document"
inputs      = { cv_pdf = "Document" }
output      = "Page[]"
model       = "@default-text-from-pdf"
```

### Operator: PipeCompose

Composes output by assembling data from working memory using either a template or a construct. Exactly one of `template` or `construct` MUST be provided.

#### Template Mode

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `type` | `"PipeCompose"` | Yes | — |
| `description` | string | Yes | — |
| `inputs` | table | No | — |
| `output` | string | Yes | MUST be a single concept (no multiplicity). |
| `template` | string or table | Yes (if no `construct`) | A Jinja2 template string, or a template blueprint table with `template`, `category`, `templating_style`, and `extra_context` fields. |

When `template` is a string, it is a Jinja2 template rendered with the input variables. When `template` is a table, it MUST contain a `template` field (string) and MAY contain `category`, `templating_style`, and `extra_context`.

**Validation rules (template mode):**

- Every variable referenced in the template MUST correspond to a declared input.
- `output` MUST NOT use multiplicity brackets (`[]` or `[N]`).

#### Construct Mode

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `type` | `"PipeCompose"` | Yes | — |
| `description` | string | Yes | — |
| `inputs` | table | No | — |
| `output` | string | Yes | MUST be a single concept (no multiplicity). |
| `construct` | table | Yes (if no `template`) | A field-by-field composition blueprint. |

The `construct` table defines how each field of the output concept is composed. Each key is a field name, and the value defines the composition method:

| Value form | Method | Description |
|------------|--------|-------------|
| Literal (`string`, `integer`, `float`, `boolean`, `array`) | Fixed | The field value is the literal. |
| `{ from = "path" }` | Variable reference | The field value comes from a variable in working memory. `path` is a dotted path (e.g., `"match_analysis.score"`). |
| `{ from = "path", list_to_dict_keyed_by = "attr" }` | Variable reference with transform | Converts a list to a dict keyed by the named attribute. |
| `{ template = "..." }` | Template | The field value is rendered from a Jinja2 template string. |
| Nested table (no `from` or `template` key) | Nested construct | The field is recursively composed from a nested construct. |

**Validation rules (construct mode):**

- The root variable of every `from` path and every template variable MUST correspond to a declared input.
- `from` and `template` are mutually exclusive within a single field definition.

**Example — construct mode:**

```toml
[pipe.compose_interview_sheet]
type        = "PipeCompose"
description = "Compose the final interview sheet"
inputs      = { match_analysis = "MatchAnalysis", interview_questions = "InterviewQuestion[]" }
output      = "InterviewSheet"

[pipe.compose_interview_sheet.construct]
overall_match_score  = { from = "match_analysis.overall_match_score" }
matching_skills      = { from = "match_analysis.matching_skills" }
missing_skills       = { from = "match_analysis.missing_skills" }
questions            = { from = "interview_questions" }
```

### Controller: PipeSequence

Executes a series of sub-pipes in order. The output of each step is added to working memory and can be consumed by subsequent steps.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `type` | `"PipeSequence"` | Yes | — |
| `description` | string | Yes | — |
| `inputs` | table | No | — |
| `output` | string | Yes | — |
| `steps` | array of tables | Yes | Ordered list of sub-pipe invocations. MUST contain at least one step. |

Each step is a **sub-pipe blueprint**:

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `pipe` | string | Yes | Pipe reference (bare, domain-qualified, or package-qualified). |
| `result` | string | No | Name under which the step's output is stored in working memory. |
| `nb_output` | integer | No | Expected number of output items. Mutually exclusive with `multiple_output`. |
| `multiple_output` | boolean | No | Whether to expect multiple output items. Mutually exclusive with `nb_output`. |
| `batch_over` | string | No | Working memory variable to iterate over (inline batch). Requires `batch_as`. |
| `batch_as` | string | No | Name for each item during inline batch iteration. Requires `batch_over`. |

**Validation rules:**

- `steps` MUST contain at least one entry.
- `nb_output` and `multiple_output` MUST NOT both be set on the same step.
- `batch_over` and `batch_as` MUST either both be present or both be absent.
- `batch_over` and `batch_as` MUST NOT be the same value.

**Example:**

```toml
[pipe.process_document]
type        = "PipeSequence"
description = "Full document processing pipeline"
inputs      = { document = "Document" }
output      = "AnalysisResult"
steps = [
    { pipe = "extract_pages", result = "pages" },
    { pipe = "analyze_content", result = "analysis" },
    { pipe = "generate_summary", result = "summary" },
]
```

### Controller: PipeParallel

Executes multiple sub-pipes concurrently. Each branch operates independently.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `type` | `"PipeParallel"` | Yes | — |
| `description` | string | Yes | — |
| `inputs` | table | No | — |
| `output` | string | Yes | — |
| `branches` | array of tables | Yes | List of sub-pipe invocations to execute concurrently. |
| `add_each_output` | boolean | No | If `true`, each branch's output is individually added to working memory under its `result` name. Default: `false`. |
| `combined_output` | string | No | Concept reference for a combined output that merges all branch results. |

**Validation rules:**

- At least one of `add_each_output` or `combined_output` MUST be set (otherwise the pipe produces no output).
- `combined_output`, if present, MUST be a valid concept reference.
- Each branch follows the same sub-pipe blueprint format as `PipeSequence` steps.

**Example:**

```toml
[pipe.extract_documents]
type        = "PipeParallel"
description = "Extract text from both CV and job offer concurrently"
inputs      = { cv_pdf = "Document", job_offer_pdf = "Document" }
output      = "Page[]"
add_each_output = true
branches = [
    { pipe = "extract_cv", result = "cv_pages" },
    { pipe = "extract_job_offer", result = "job_offer_pages" },
]
```

### Controller: PipeCondition

Routes execution to different pipes based on an evaluated condition.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `type` | `"PipeCondition"` | Yes | — |
| `description` | string | Yes | — |
| `inputs` | table | No | — |
| `output` | string | Yes | — |
| `expression_template` | string | Conditional | A Jinja2 template that evaluates to a string matching an outcome key. Exactly one of `expression_template` or `expression` MUST be provided. |
| `expression` | string | Conditional | A static expression string. Exactly one of `expression_template` or `expression` MUST be provided. |
| `outcomes` | table | Yes | Maps outcome strings to pipe references. MUST have at least one entry. |
| `default_outcome` | string | Yes | The pipe reference (or special outcome) to use when no outcome key matches. |
| `add_alias_from_expression_to` | string | No | If set, stores the evaluated expression value in working memory under this name. |

**Special outcomes:**

Certain string values in `outcomes` values and `default_outcome` have special meaning and are not treated as pipe references:

| Value | Meaning |
|-------|---------|
| `"fail"` | Abort execution with an error. |
| `"continue"` | Skip this branch and continue without executing a sub-pipe. |

**Example:**

```toml
[pipe.route_by_document_type]
type                = "PipeCondition"
description         = "Route processing based on document type"
inputs              = { doc_request = "DocumentRequest" }
output              = "Text"
expression_template = "{{ doc_request.document_type }}"
default_outcome     = "continue"

[pipe.route_by_document_type.outcomes]
technical = "process_technical"
business  = "process_business"
legal     = "process_legal"
```

### Controller: PipeBatch

Maps a single pipe over each item in a list input, producing a list output.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `type` | `"PipeBatch"` | Yes | — |
| `description` | string | Yes | — |
| `inputs` | table | Yes | MUST include an entry whose name matches `input_list_name`. |
| `output` | string | Yes | — |
| `branch_pipe_code` | string | Yes | The pipe reference to invoke for each item. |
| `input_list_name` | string | Yes | The name of the input that contains the list to iterate over. |
| `input_item_name` | string | Yes | The name under which each individual item is passed to the branch pipe. |

**Validation rules:**

- `input_list_name` MUST exist as a key in `inputs`.
- `input_item_name` MUST NOT be empty.
- `input_item_name` MUST NOT equal `input_list_name`.
- `input_item_name` MUST NOT equal any key in `inputs`.

**Example:**

```toml
[pipe.batch_generate_jokes]
type             = "PipeBatch"
description      = "Generate a joke for each topic"
inputs           = { topics = "Topic[]" }
output           = "Joke[]"
branch_pipe_code = "generate_joke"
input_list_name  = "topics"
input_item_name  = "topic"
```

### Pipe Reference Syntax

Every location in a `.mthds` file that references another pipe supports three forms:

| Form | Syntax | Example | Resolution |
|------|--------|---------|------------|
| Bare | `pipe_code` | `"extract_clause"` | Resolved within the current bundle and its domain. |
| Domain-qualified | `domain.pipe_code` | `"legal.contracts.extract_clause"` | Resolved within the named domain of the current package. |
| Package-qualified | `alias->domain.pipe_code` | `"docproc->extraction.extract_text"` | Resolved in the named domain of the dependency identified by the alias. |

Pipe references appear in:

- `steps[].pipe` (PipeSequence)
- `branches[].pipe` (PipeParallel)
- `outcomes` values (PipeCondition)
- `default_outcome` (PipeCondition)
- `branch_pipe_code` (PipeBatch)

Pipe *definitions* (the `[pipe.<pipe_code>]` table keys) are always bare `snake_case` names. Namespacing applies only to pipe *references*.

### Concept Reference Syntax

Every location that references a concept supports three forms, symmetric with pipe references:

| Form | Syntax | Example | Resolution |
|------|--------|---------|------------|
| Bare | `ConceptCode` | `"ContractClause"` | Resolved in order: native concepts → current bundle → same domain. |
| Domain-qualified | `domain.ConceptCode` | `"legal.contracts.NonCompeteClause"` | Resolved within the named domain of the current package. |
| Package-qualified | `alias->domain.ConceptCode` | `"acme->legal.ContractClause"` | Resolved in the named domain of the dependency identified by the alias. |

The disambiguation between concepts and pipes in a domain-qualified reference relies on casing:

- `snake_case` final segment → pipe code
- `PascalCase` final segment → concept code

Concept references appear in:

- `inputs` values
- `output`
- `refines`
- `concept_ref` and `item_concept_ref` in structure field blueprints
- `combined_output` (PipeParallel)

### Complete Bundle Example

```toml
domain      = "joke_generation"
description = "Generating one-liner jokes from topics"
main_pipe   = "generate_jokes_from_topics"

[concept.Topic]
description = "A subject or theme that can be used as the basis for a joke."
refines     = "Text"

[concept.Joke]
description = "A humorous one-liner intended to make people laugh."
refines     = "Text"

[pipe.generate_jokes_from_topics]
type        = "PipeSequence"
description = "Generate 3 joke topics and create a joke for each"
output      = "Joke[]"
steps = [
    { pipe = "generate_topics", result = "topics" },
    { pipe = "batch_generate_jokes", result = "jokes" },
]

[pipe.generate_topics]
type   = "PipeLLM"
description = "Generate 3 distinct topics suitable for jokes"
output = "Topic[3]"
prompt = "Generate 3 distinct and varied topics for crafting one-liner jokes."

[pipe.batch_generate_jokes]
type             = "PipeBatch"
description      = "Generate a joke for each topic"
inputs           = { topics = "Topic[]" }
output           = "Joke[]"
branch_pipe_code = "generate_joke"
input_list_name  = "topics"
input_item_name  = "topic"

[pipe.generate_joke]
type        = "PipeLLM"
description = "Write a clever one-liner joke about the given topic"
inputs      = { topic = "Topic" }
output      = "Joke"
prompt      = "Write a clever one-liner joke about $topic. Be concise and witty."
```

---

## Page: METHODS.toml Manifest Format

The `METHODS.toml` file is the package manifest — the identity card and dependency declaration for an MTHDS package. It MUST be named exactly `METHODS.toml` and MUST be located at the root of the package directory.

### File Encoding and Syntax

`METHODS.toml` MUST be a valid TOML document encoded in UTF-8.

### Top-Level Sections

A `METHODS.toml` file contains up to three top-level sections:

| Section | Required | Description |
|---------|----------|-------------|
| `[package]` | Yes | Package identity and metadata. |
| `[dependencies]` | No | Dependencies on other MTHDS packages. |
| `[exports]` | No | Visibility declarations for pipes. |

### The `[package]` Section

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `address` | string | Yes | Globally unique package identifier. MUST follow the hostname/path pattern. |
| `version` | string | Yes | Package version. MUST be valid [semantic versioning](https://semver.org/) (`MAJOR.MINOR.PATCH`, with optional pre-release and build metadata). |
| `description` | string | Yes | Human-readable summary of the package's purpose. MUST NOT be empty. |
| `authors` | array of strings | No | List of author identifiers (e.g., `"Name <email>"`). Default: empty list. |
| `license` | string | No | SPDX license identifier (e.g., `"MIT"`, `"Apache-2.0"`). |
| `mthds_version` | string | No | MTHDS standard version constraint. If set, MUST be a valid version constraint. |

#### Address Format

The package address is the globally unique identifier for the package. It doubles as the fetch location for VCS-based distribution.

**Pattern:** `^[a-zA-Z0-9._-]+\.[a-zA-Z0-9._-]+/[a-zA-Z0-9._/-]+$`

In plain language: the address MUST start with a hostname (containing at least one dot), followed by a `/`, followed by one or more path segments.

**Examples of valid addresses:**

```
github.com/acme/legal-tools
github.com/mthds/document-processing
gitlab.com/company/internal-methods
```

**Examples of invalid addresses:**

```
legal-tools                     # No hostname
acme/legal-tools                # No dot in hostname
```

#### Version Format

The `version` field MUST conform to [Semantic Versioning 2.0.0](https://semver.org/):

```
MAJOR.MINOR.PATCH[-pre-release][+build-metadata]
```

**Examples:** `1.0.0`, `0.3.0`, `2.1.3-beta.1`, `1.0.0-rc.1+build.42`

#### mthds_version Constraints

The `mthds_version` field, if present, declares which versions of the MTHDS standard this package is compatible with. It uses version constraint syntax (see [Version Constraint Syntax](#version-constraint-syntax)).

The current MTHDS standard version is `1.0.0`.

### The `[dependencies]` Section

Each entry in `[dependencies]` declares a dependency on another MTHDS package. The key is the **alias** — a `snake_case` identifier used in cross-package references (`->` syntax).

```toml
[dependencies]
docproc     = { address = "github.com/mthds/document-processing", version = "^1.0.0" }
scoring_lib = { address = "github.com/mthds/scoring-lib", version = "^0.5.0" }
```

#### Dependency Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `address` | string | Yes | The dependency's package address. MUST follow the hostname/path pattern. |
| `version` | string | Yes | Version constraint for the dependency (see [Version Constraint Syntax](#version-constraint-syntax)). |
| `path` | string | No | Local filesystem path to the dependency, resolved relative to the manifest directory. For development-time workflows. |

#### Alias Rules

- The alias (the TOML key) MUST be `snake_case`, matching `[a-z][a-z0-9_]*`.
- All aliases within a single `[dependencies]` section MUST be unique.
- The alias is used in cross-package references: `alias->domain.name`.

#### The `path` Field

When `path` is set, the dependency is resolved from the local filesystem instead of being fetched via VCS. This supports development-time workflows where packages are co-located on disk, similar to Cargo's `path` dependencies or Go's `replace` directives.

- The path is resolved relative to the directory containing `METHODS.toml`.
- Local path dependencies are NOT resolved transitively — only the root package's local paths are honored.
- Local path dependencies are excluded from the lock file.

**Example:**

```toml
[dependencies]
scoring = { address = "github.com/mthds/scoring-lib", version = "^0.5.0", path = "../scoring-lib" }
```

#### Version Constraint Syntax

Version constraints specify which versions of a dependency are acceptable.

| Form | Syntax | Example | Meaning |
|------|--------|---------|---------|
| Exact | `MAJOR.MINOR.PATCH` | `1.0.0` | Exactly this version. |
| Caret | `^MAJOR.MINOR.PATCH` | `^1.0.0` | Compatible release (same major version). |
| Tilde | `~MAJOR.MINOR.PATCH` | `~1.0.0` | Approximately compatible (same major.minor). |
| Greater-or-equal | `>=MAJOR.MINOR.PATCH` | `>=1.0.0` | This version or newer. |
| Less-than | `<MAJOR.MINOR.PATCH` | `<2.0.0` | Older than this version. |
| Greater | `>MAJOR.MINOR.PATCH` | `>1.0.0` | Newer than this version. |
| Less-or-equal | `<=MAJOR.MINOR.PATCH` | `<=2.0.0` | This version or older. |
| Equal | `==MAJOR.MINOR.PATCH` | `==1.0.0` | Exactly this version. |
| Not-equal | `!=MAJOR.MINOR.PATCH` | `!=1.0.0` | Any version except this one. |
| Compound | constraint `, ` constraint | `>=1.0.0, <2.0.0` | Both constraints must be satisfied. |
| Wildcard | `*`, `MAJOR.*`, `MAJOR.MINOR.*` | `1.*` | Any version matching the prefix. |

Partial versions are allowed: `1.0` is equivalent to `1.0.*`.

### The `[exports]` Section

The `[exports]` section controls which pipes are visible to consumers of the package.

**Default visibility rules:**

- **Concepts are always public.** Concepts are vocabulary — they are always accessible from outside the package.
- **Pipes are private by default.** A pipe not listed in `[exports]` is an implementation detail, invisible to consumers.
- **`main_pipe` is auto-exported.** If a bundle declares a `main_pipe`, that pipe is automatically part of the public API, regardless of whether it appears in `[exports]`.

#### Exports Table Structure

The `[exports]` section uses nested TOML tables that mirror the domain hierarchy. The domain path maps directly to the TOML table path:

```toml
[exports.legal]
pipes = ["classify_document"]

[exports.legal.contracts]
pipes = ["extract_clause", "analyze_nda", "compare_contracts"]

[exports.scoring]
pipes = ["compute_weighted_score"]
```

Each leaf table contains:

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `pipes` | array of strings | Yes | Pipe codes that are public from this domain. Each entry MUST be a valid pipe code (`snake_case`). |

**Validation rules:**

- Domain paths in `[exports]` MUST be valid domain codes.
- Domain paths in `[exports]` MUST NOT start with a reserved domain segment (`native`, `mthds`, `pipelex`).
- A domain MAY have both a `pipes` list and sub-domain tables (e.g., `[exports.legal]` with `pipes` AND `[exports.legal.contracts]`).

#### Standalone Bundles (No Manifest)

A `.mthds` file without a `METHODS.toml` manifest is a standalone bundle. It behaves as an implicit local package with:

- No dependencies (beyond native concepts).
- All pipes treated as public (no visibility restrictions).
- No package address (not distributable).

This preserves the "single file = working method" experience for learning, prototyping, and simple projects.

### Package Directory Structure

A package is a directory containing a `METHODS.toml` manifest and one or more `.mthds` bundle files. The directory layout follows a progressive enhancement principle — start minimal, add structure as needed.

**Minimal package:**

```
my-tool/
├── METHODS.toml
└── main.mthds
```

**Full package:**

```
legal-tools/
├── METHODS.toml
├── methods.lock
├── general_legal.mthds
├── contract_analysis.mthds
├── shareholder_agreements.mthds
├── scoring.mthds
├── README.md
└── LICENSE
```

**Rules:**

- `METHODS.toml` MUST be at the directory root.
- `methods.lock` MUST be at the directory root, alongside `METHODS.toml`.
- `.mthds` files MAY be at the root or in subdirectories. A compliant implementation MUST discover all `.mthds` files recursively.
- A single directory SHOULD contain one package. Multiple packages in subdirectories with distinct addresses are possible but outside the scope of this specification.

### Manifest Discovery

When loading a `.mthds` bundle, a compliant implementation SHOULD discover the manifest by walking up from the bundle file's directory:

1. Check the current directory for `METHODS.toml`.
2. If not found, move to the parent directory.
3. Stop when `METHODS.toml` is found, a `.git` directory is encountered, or the filesystem root is reached.
4. If no manifest is found, the bundle is treated as a standalone bundle (no package).

### Complete Manifest Example

```toml
[package]
address       = "github.com/acme/legal-tools"
version       = "0.3.0"
description   = "Legal document analysis and contract review methods."
authors       = ["ACME Legal Tech <legal@acme.com>"]
license       = "MIT"
mthds_version = ">=1.0.0"

[dependencies]
docproc     = { address = "github.com/mthds/document-processing", version = "^1.0.0" }
scoring_lib = { address = "github.com/mthds/scoring-lib", version = "^0.5.0" }

[exports.legal]
pipes = ["classify_document"]

[exports.legal.contracts]
pipes = ["extract_clause", "analyze_nda", "compare_contracts"]

[exports.scoring]
pipes = ["compute_weighted_score"]
```

---

## Page: methods.lock Format

The `methods.lock` file records the exact resolved versions and integrity hashes for all remote dependencies, enabling reproducible builds. It is auto-generated and SHOULD be committed to version control.

### File Name and Location

The lock file MUST be named `methods.lock` and MUST be located at the root of the package directory, alongside `METHODS.toml`.

### File Encoding and Syntax

`methods.lock` MUST be a valid TOML document encoded in UTF-8.

### Structure

The lock file is a flat TOML document where each top-level table key is a package address, and the value is a table containing the locked metadata for that package.

```toml
["github.com/mthds/document-processing"]
version = "1.2.3"
hash    = "sha256:a1b2c3d4e5f6..."
source  = "https://github.com/mthds/document-processing"

["github.com/mthds/scoring-lib"]
version = "0.5.1"
hash    = "sha256:e5f6a7b8c9d0..."
source  = "https://github.com/mthds/scoring-lib"
```

Because package addresses contain dots and slashes, they MUST be quoted as TOML keys.

### Locked Package Fields

Each entry in the lock file contains:

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `version` | string | Yes | The exact resolved version. MUST be valid semver. |
| `hash` | string | Yes | Integrity hash of the package contents. MUST match the pattern `sha256:[0-9a-f]{64}`. |
| `source` | string | Yes | The HTTPS URL from which the package was fetched. MUST start with `https://`. |

### Hash Computation

The integrity hash is a deterministic SHA-256 hash of the package directory contents, computed as follows:

1. Collect all regular files recursively under the package directory.
2. Exclude any path containing `.git` in its components.
3. Sort files by their POSIX-normalized relative path (for cross-platform determinism).
4. For each file in sorted order, feed into the hasher:
   a. The relative path string, encoded as UTF-8.
   b. The raw file bytes.
5. The resulting hash is formatted as `sha256:` followed by the 64-character lowercase hex digest.

### Which Packages Are Locked

- **Remote dependencies** (those without a `path` field in the root manifest) are locked, including all transitive remote dependencies.
- **Local path dependencies** are NOT locked. They are resolved from the filesystem at load time and are expected to change during development.

### When the Lock File Updates

The lock file is regenerated when:

- `mthds pkg lock` is run — resolves all dependencies and writes the lock file.
- `mthds pkg update` is run — re-resolves to latest compatible versions and rewrites the lock file.
- `mthds pkg add` is run — adds a new dependency and may trigger re-resolution.

### Verification

When installing from a lock file (`mthds pkg install`), a compliant implementation MUST:

1. For each entry in the lock file, locate the corresponding cached package directory.
2. Recompute the SHA-256 hash of the cached directory using the algorithm described above.
3. Compare the computed hash with the `hash` field in the lock file.
4. Reject the installation if any hash does not match (integrity failure).

### Deterministic Output

Lock file entries MUST be sorted by package address (lexicographic ascending) to produce deterministic output suitable for clean version control diffs.

An empty lock file (no remote dependencies) MAY be an empty file or absent entirely.

---

## Page: Namespace Resolution Rules

This page defines the formal rules for resolving references to concepts and pipes across bundles, domains, and packages.

### Reference Syntax Overview

All references to concepts and pipes in MTHDS follow a uniform three-tier syntax:

| Tier | Syntax | Example (concept) | Example (pipe) |
|------|--------|--------------------|----------------|
| Bare | `name` | `ContractClause` | `extract_clause` |
| Domain-qualified | `domain_path.name` | `legal.contracts.NonCompeteClause` | `legal.contracts.extract_clause` |
| Package-qualified | `alias->domain_path.name` | `acme->legal.ContractClause` | `docproc->extraction.extract_text` |

### Parsing Rules

#### Splitting Cross-Package References

If the reference string contains `->`, it is a cross-package reference. The string is split on the first `->`:

- Left part: the package alias.
- Right part: the remainder (a domain-qualified or bare reference).

The alias MUST be `snake_case`. The remainder is parsed as a domain-qualified or bare reference.

#### Splitting Domain-Qualified References

For the remainder (or the entire string if no `->` is present), the reference is parsed by splitting on the **last `.`** (dot):

- Left part: the domain path.
- Right part: the local code (concept code or pipe code).

If no `.` is present, the reference is a bare name with no domain qualification.

**Examples:**

| Reference | Domain Path | Local Code | Type |
|-----------|-------------|------------|------|
| `extract_clause` | *(none)* | `extract_clause` | Bare pipe |
| `NonCompeteClause` | *(none)* | `NonCompeteClause` | Bare concept |
| `scoring.compute_score` | `scoring` | `compute_score` | Domain-qualified pipe |
| `legal.contracts.NonCompeteClause` | `legal.contracts` | `NonCompeteClause` | Domain-qualified concept |
| `docproc->extraction.extract_text` | `extraction` (in package `docproc`) | `extract_text` | Package-qualified pipe |

#### Disambiguation: Concept vs. Pipe

When parsing a domain-qualified reference, the casing of the local code (the segment after the last `.`) determines whether it is a concept or a pipe:

- `PascalCase` (`[A-Z][a-zA-Z0-9]*`) → concept code.
- `snake_case` (`[a-z][a-z0-9_]*`) → pipe code.

This disambiguation is unambiguous because concept codes and pipe codes follow mutually exclusive casing conventions.

### Domain Path Validation

Each segment of a domain path MUST be `snake_case`:

- Match pattern: `[a-z][a-z0-9_]*`
- Segments are separated by `.`
- No leading, trailing, or consecutive dots

### Resolution Order for Bare Concept References

When resolving a bare concept code (no domain qualifier, no package prefix):

1. **Native concepts** — check if the code matches a native concept code (`Text`, `Image`, `Document`, `Html`, `TextAndImages`, `Number`, `ImgGenPrompt`, `Page`, `JSON`, `Dynamic`, `Anything`). Native concepts always take priority.
2. **Current bundle** — check concepts declared in the same `.mthds` file.
3. **Same domain, other bundles** — if the bundle is part of a package, check concepts in other bundles that declare the same domain.
4. **Error** — if not found in any of the above, the reference is invalid.

Bare concept references do NOT fall through to other domains or other packages.

### Resolution Order for Bare Pipe References

When resolving a bare pipe code (no domain qualifier, no package prefix):

1. **Current bundle** — check pipes declared in the same `.mthds` file.
2. **Same domain, other bundles** — if the bundle is part of a package, check pipes in other bundles that declare the same domain.
3. **Error** — if not found, the reference is invalid.

Bare pipe references do NOT fall through to other domains or other packages.

### Resolution of Domain-Qualified References

When resolving `domain_path.name` (no package prefix):

1. Look in the named domain within the **current package**.
2. If not found: **error**. Domain-qualified references do not fall through to dependencies.

This applies to both concept and pipe references.

### Resolution of Package-Qualified References

When resolving `alias->domain_path.name`:

1. Identify the dependency by the alias. The alias MUST match a key in the `[dependencies]` section of the consuming package's `METHODS.toml`.
2. Look in the named domain of the **resolved dependency package**.
3. If not found: **error**.

**Visibility constraints for cross-package pipe references:**

- The referenced pipe MUST be exported by the dependency package (listed in its `[exports]` section or declared as `main_pipe` in its bundle header).
- If the pipe is not exported, the reference is a visibility error.

**Visibility for cross-package concept references:**

- Concepts are always public. No visibility check is needed for cross-package concept references.

### Visibility Rules (Intra-Package)

Within a package that has a `METHODS.toml` manifest:

- **Same-domain references** — always allowed. A pipe in domain `legal.contracts` can reference any other pipe in `legal.contracts` without restriction.
- **Cross-domain references** (within the same package) — the target pipe MUST be exported. A pipe in domain `scoring` referencing `legal.contracts.extract_clause` requires that `extract_clause` is listed in `[exports.legal.contracts]` (or is the `main_pipe` of a bundle in `legal.contracts`).
- **Bare references** — always allowed at the visibility level (they resolve within the same domain).

When no manifest is present (standalone bundle), all pipes are treated as public.

### Reserved Domains

The following domain names are reserved at the first segment level:

| Domain | Owner | Purpose |
|--------|-------|---------|
| `native` | MTHDS standard | Built-in concept types. |
| `mthds` | MTHDS standard | Reserved for future standard extensions. |
| `pipelex` | Reference implementation | Reserved for the reference implementation. |

**Enforcement points:**

- A compliant implementation MUST reject `METHODS.toml` exports that use a reserved domain path.
- A compliant implementation MUST reject bundles that declare a domain starting with a reserved segment when the bundle is part of a package.
- A compliant implementation MUST reject packages at publish time if any bundle uses a reserved domain.

The `native` domain is the only reserved domain with active semantics: it serves as the namespace for native concepts (`native.Text`, `native.Image`, etc.).

### Package Namespace Isolation

Two packages MAY declare the same domain name (e.g., both declare `domain = "recruitment"`). Their concepts and pipes are completely independent — there is no merging of namespaces across packages.

Within a single package, bundles that share the same domain DO merge their namespace. Concept or pipe code collisions within the same package and same domain are errors.

### Conflict Rules

| Scope | Conflict type | Result |
|-------|--------------|--------|
| Same bundle | Duplicate concept code | TOML parse error (duplicate key). |
| Same bundle | Duplicate pipe code | TOML parse error (duplicate key). |
| Same domain, different bundles (same package) | Duplicate concept code | Error at load time. |
| Same domain, different bundles (same package) | Duplicate pipe code | Error at load time. |
| Different domains (same package) | Same concept or pipe code | No conflict — different namespaces. |
| Different packages | Same domain and same concept/pipe code | No conflict — package isolation. |

### Version Resolution Strategy

When resolving dependency versions, a compliant implementation SHOULD use **Minimum Version Selection** (MVS), following Go's approach:

1. Collect all version constraints for a given package address from all dependents (direct and transitive).
2. List all available versions (from VCS tags).
3. Sort versions in ascending order.
4. Select the **minimum** version that satisfies **all** constraints simultaneously.

If no version satisfies all constraints, the resolution fails with an error.

**Properties of MVS:**

- **Deterministic** — the same set of constraints always produces the same result.
- **Reproducible** — no dependency on a "latest" query or timestamp.
- **Simple** — no backtracking solver needed.

### Transitive Dependency Resolution

Dependencies are resolved transitively with the following rules:

- **Remote dependencies** are resolved recursively. If Package A depends on Package B, and Package B depends on Package C, then Package C is also resolved.
- **Local path dependencies** are resolved at the root level only. They are NOT resolved transitively.
- **Cycle detection** — if a dependency is encountered while it is already on the resolution stack, the resolver MUST report a cycle error.
- **Diamond dependencies** — when the same package address is required by multiple dependents with different version constraints, MVS selects the minimum version satisfying all constraints simultaneously.

### Fetching Remote Dependencies

Package addresses map to Git clone URLs by the following rule:

1. Prepend `https://`.
2. Append `.git` (if not already present).

For example: `github.com/acme/legal-tools` → `https://github.com/acme/legal-tools.git`

The resolution chain for fetching a dependency is:

1. **Local path** — if the dependency has a `path` field in `METHODS.toml`, resolve from the local filesystem.
2. **Local cache** — check `~/.mthds/packages/{address}/{version}/` for a cached copy.
3. **VCS fetch** — clone the repository at the resolved version tag using `git clone --depth 1 --branch {tag}`.

Version tags in the remote repository MAY use a `v` prefix (e.g., `v1.0.0`). The prefix is stripped during version parsing.

### Cache Layout

The default package cache is located at `~/.mthds/packages/`. Cached packages are stored at:

```
~/.mthds/packages/{address}/{version}/
```

For example:

```
~/.mthds/packages/github.com/acme/legal-tools/1.0.0/
```

The `.git` directory is removed from cached copies.

### Cross-Package Reference Examples

The following examples illustrate the complete reference resolution for cross-package scenarios.

**Setup:** Package A depends on Package B with alias `scoring_lib`.

Package B (`METHODS.toml`):

```toml
[package]
address = "github.com/mthds/scoring-lib"
version = "0.5.0"
description = "Scoring utilities"

[exports.scoring]
pipes = ["compute_weighted_score"]
```

Package B (`scoring.mthds`):

```toml
domain    = "scoring"
main_pipe = "compute_weighted_score"

[concept.ScoreResult]
description = "A weighted score result"

[pipe.compute_weighted_score]
type        = "PipeLLM"
description = "Compute a weighted score"
inputs      = { item = "Text" }
output      = "ScoreResult"
prompt      = "Compute a weighted score for: $item"

[pipe.internal_helper]
type        = "PipeLLM"
description = "Internal helper (not exported)"
inputs      = { data = "Text" }
output      = "Text"
prompt      = "Process: $data"
```

Package A (`analysis.mthds`):

```toml
domain = "analysis"

[pipe.analyze_item]
type        = "PipeSequence"
description = "Analyze using scoring dependency"
inputs      = { item = "Text" }
output      = "Text"
steps = [
    { pipe = "scoring_lib->scoring.compute_weighted_score", result = "score" },
    { pipe = "summarize", result = "summary" },
]
```

**Resolution of `scoring_lib->scoring.compute_weighted_score`:**

1. `->` detected — split into alias `scoring_lib` and remainder `scoring.compute_weighted_score`.
2. Look up `scoring_lib` in Package A's `[dependencies]` — found, resolves to `github.com/mthds/scoring-lib`.
3. Parse remainder: split on last `.` → domain `scoring`, pipe code `compute_weighted_score`.
4. Look in domain `scoring` of the resolved Package B — pipe found.
5. Visibility check: `compute_weighted_score` is in `[exports.scoring]` pipes — accessible.
6. Resolution succeeds.

**If Package A tried `scoring_lib->scoring.internal_helper`:**

1. Steps 1–4 as above — pipe `internal_helper` is found in Package B's `scoring` domain.
2. Visibility check: `internal_helper` is NOT in `[exports.scoring]` and is NOT `main_pipe` — **visibility error**.

**Cross-package concept reference:**

```toml
[concept.DetailedScore]
description = "An extended score with additional analysis"
refines     = "scoring_lib->scoring.ScoreResult"
```

This refines `ScoreResult` from Package B. Concepts are always public, so no visibility check is needed.

### Validation Rule Summary

This section consolidates the validation rules scattered throughout this specification into a single reference.

#### Bundle-Level Validation

1. The file MUST be valid TOML.
2. `domain` MUST be present and MUST be a valid domain code.
3. `main_pipe`, if present, MUST be `snake_case` and MUST reference a pipe defined in the same bundle.
4. Concept codes MUST be `PascalCase`.
5. Concept codes MUST NOT match any native concept code.
6. Pipe codes MUST be `snake_case`.
7. `refines` and `structure` MUST NOT both be set on the same concept.
8. Local concept references (bare or same-domain) MUST resolve to a declared concept in the bundle or a native concept.
9. Same-domain pipe references MUST resolve to a declared pipe in the bundle.
10. Cross-package references (`->` syntax) are deferred to package-level validation.

#### Concept Structure Field Validation

1. `description` MUST be present on every field.
2. If `type` is omitted, `choices` MUST be non-empty.
3. `type = "dict"` requires both `key_type` and `value_type`.
4. `type = "concept"` requires `concept_ref` and forbids `default_value`.
5. `type = "list"` with `item_type = "concept"` requires `item_concept_ref`.
6. `concept_ref` MUST NOT be set unless `type = "concept"`.
7. `item_concept_ref` MUST NOT be set unless `item_type = "concept"`.
8. `default_value` type MUST match the declared `type`.
9. If `choices` is set and `default_value` is present, `default_value` MUST be in `choices`.
10. Field names MUST NOT start with `_`.

#### Pipe Validation (Type-Specific)

1. **PipeLLM**: All prompt variables MUST have matching inputs. All inputs MUST be used.
2. **PipeFunc**: `function_name` MUST be present.
3. **PipeImgGen**: `prompt` MUST be present. All prompt variables MUST have matching inputs.
4. **PipeExtract**: Exactly one input MUST be declared. `output` MUST be `"Page[]"`.
5. **PipeCompose**: Exactly one of `template` or `construct` MUST be present. Output MUST NOT use multiplicity.
6. **PipeSequence**: `steps` MUST have at least one entry.
7. **PipeParallel**: At least one of `add_each_output` or `combined_output` MUST be set.
8. **PipeCondition**: Exactly one of `expression_template` or `expression` MUST be present. `outcomes` MUST have at least one entry.
9. **PipeBatch**: `input_list_name` MUST be in `inputs`. `input_item_name` MUST NOT equal `input_list_name` or any `inputs` key.

#### Package-Level Validation

1. `[package]` section MUST be present in `METHODS.toml`.
2. `address` MUST match the hostname/path pattern.
3. `version` MUST be valid semver.
4. `description` MUST NOT be empty.
5. All dependency aliases MUST be unique.
6. All dependency aliases MUST be `snake_case`.
7. All dependency addresses MUST match the hostname/path pattern.
8. All dependency version constraints MUST be valid.
9. Domain paths in `[exports]` MUST NOT use reserved domains.
10. All pipe codes in `[exports]` MUST be valid `snake_case`.
11. Cross-package references MUST reference known dependency aliases.
12. Cross-package pipe references MUST target exported pipes.
13. Bundles MUST NOT use reserved domains as their first segment.

#### Lock File Validation

1. Each entry's `version` MUST be valid semver.
2. Each entry's `hash` MUST match `sha256:[0-9a-f]{64}`.
3. Each entry's `source` MUST start with `https://`.

### Summary: Reference Resolution Flowchart

Given a reference string `R`:

```
1. Does R contain "->"?
   YES → Split into (alias, remainder).
         Look up alias in [dependencies].
         Parse remainder as domain-qualified or bare ref.
         Resolve in the dependency's namespace.
         For pipes: check export visibility.
   NO  → Continue to step 2.

2. Does R contain "."?
   YES → Split on last "." into (domain_path, local_code).
         Resolve in domain_path within current package.
   NO  → R is a bare name. Continue to step 3.

3. Is R a concept code (PascalCase)?
   YES → Check native concepts → current bundle → same domain.
   NO  → R is a pipe code (snake_case).
         Check current bundle → same domain.

4. Not found? → Error.
```
