# The Language

<!-- Source document for the MTHDS docs website.
     Each "## Page:" section becomes an individual MkDocs page.

     Tone: Teaching. Clear, progressive. Start simple, build complexity.
     Every concept grounded in a concrete .mthds example first, explanation second.
     Cross-references use [text](link) format pointing to the spec and other pages.
-->

## Page: Bundles

A **bundle** is a single `.mthds` file. It is the authoring unit of MTHDS — the place where you define typed data and typed transformations.

### A First Look

```toml
domain      = "legal.contracts"
description = "Contract analysis methods for legal documents"
main_pipe   = "extract_clause"

[concept]
ContractClause = "A clause extracted from a legal contract"

[pipe.extract_clause]
type        = "PipeLLM"
description = "Extract the key clause from a contract"
inputs      = { contract_text = "Text" }
output      = "ContractClause"
prompt      = "Extract the key clause from the following contract: @contract_text"
```

This is a complete, valid `.mthds` file. It defines one concept, one pipe, and works on its own — no manifest, no package, no dependencies needed.

### What This Does

The file declares a **domain** (`legal.contracts`), a **concept** (`ContractClause`), and a **pipe** (`extract_clause`) that uses an LLM to transform `Text` into a `ContractClause`. The `main_pipe` header marks `extract_clause` as the bundle's primary entry point.

### File Format

A `.mthds` file is a valid [TOML](https://toml.io/) document encoded in UTF-8. The `.mthds` extension is required. If you know TOML, you already know the syntax — MTHDS adds structure and meaning on top of it.

### Bundle Structure

Every bundle has up to three sections:

1. **Header fields** — top-level key-value pairs that identify the bundle.
2. **Concept definitions** — typed data declarations in `[concept]` tables.
3. **Pipe definitions** — typed transformations in `[pipe.<pipe_code>]` tables.

All three are optional in the TOML sense, but a useful bundle will contain at least one concept or one pipe.

### Header Fields

Header fields appear at the top of the file, before any `[concept]` or `[pipe]` tables.

| Field | Required | Description |
|-------|----------|-------------|
| `domain` | Yes | The domain this bundle belongs to. Determines the namespace for all concepts and pipes defined in this file. |
| `description` | No | A human-readable description of what this bundle provides. |
| `system_prompt` | No | A default system prompt applied to all `PipeLLM` pipes in this bundle that do not define their own. |
| `main_pipe` | No | The pipe code of the bundle's primary entry point. Auto-exported when the bundle is part of a package. |

The `domain` field is the only required header. It assigns a namespace to everything in the file — more on this in [Domains](#page-domains).

The `main_pipe` field, if present, must be a valid `snake_case` pipe code and must reference a pipe defined in the same bundle.

### Standalone Bundles

A `.mthds` file works on its own, without a package manifest. When used standalone:

- All pipes are treated as public (no visibility restrictions).
- No dependencies are available beyond native concepts.
- The bundle is not distributable (no package address).

This makes `.mthds` files ideal for learning, prototyping, and simple projects. When you need distribution, add a `METHODS.toml` manifest — see [The Package System](02-the-package-system.md).

---

## Page: Concepts

Concepts are typed data declarations. They define the vocabulary of a domain — the kinds of data that pipes accept as input and produce as output.

### Simple Concepts

The simplest form of concept declaration uses a flat `[concept]` table. Each key is a concept code, and the value is a description string:

```toml
[concept]
ContractClause = "A clause extracted from a legal contract"
UserProfile    = "A user's profile information"
```

These concepts exist as named types. They have no internal structure — they are semantic labels that give meaning to data flowing through pipes.

**Naming rule:** Concept codes must be `PascalCase`, matching the pattern `[A-Z][a-zA-Z0-9]*`. Examples: `ContractClause`, `UserProfile`, `CVAnalysis`.

### Structured Concepts

When a concept needs internal structure — specific fields with types — use a `[concept.<ConceptCode>]` sub-table:

```toml
[concept.LineItem]
description = "A single line item in an invoice"

[concept.LineItem.structure]
product_name = { type = "text", description = "Name of the product", required = true }
quantity     = { type = "integer", description = "Quantity ordered", required = true }
unit_price   = { type = "number", description = "Price per unit", required = true }
```

The `structure` table defines the fields of the concept. Each field has a type and a description.

Both simple and structured forms can coexist in the same bundle:

```toml
[concept]
ContractClause = "A clause extracted from a legal contract"

[concept.LineItem]
description = "A single line item in an invoice"

[concept.LineItem.structure]
product_name = { type = "text", description = "Name of the product", required = true }
quantity     = { type = "integer", description = "Quantity ordered", required = true }
unit_price   = { type = "number", description = "Price per unit", required = true }
```

### Concept Blueprint Fields

When using the structured form `[concept.<ConceptCode>]`:

| Field | Required | Description |
|-------|----------|-------------|
| `description` | Yes | Human-readable description of the concept. |
| `structure` | No | Field definitions. If a string, it is a shorthand description (equivalent to a simple declaration). If a table, each key is a field name mapped to a field blueprint. |
| `refines` | No | A concept reference indicating specialization of another concept. |

`refines` and `structure` cannot both be present on the same concept. A concept either refines another concept or defines its own structure, not both.

### Field Types

Each field in a concept's `structure` is defined by a field blueprint. The `type` field determines the kind of data:

| Type | Description | Example `default_value` |
|------|-------------|------------------------|
| `text` | A string value. | `"hello"` |
| `integer` | A whole number. | `42` |
| `number` | A numeric value (integer or floating-point). | `3.14` |
| `boolean` | A true/false value. | `true` |
| `date` | A date value. | *(datetime)* |
| `list` | An ordered collection. Use `item_type` to specify element type. | `["a", "b"]` |
| `dict` | A key-value mapping. Requires `key_type` and `value_type`. | *(table)* |
| `concept` | A reference to another concept. Requires `concept_ref`. Cannot have a `default_value`. | *(not allowed)* |

When `type` is omitted and `choices` is provided, the field becomes an enumeration — its value must be one of the listed strings.

### Field Blueprint Reference

The complete set of attributes available on each field in a concept's `structure`:

| Attribute | Required | Description |
|-----------|----------|-------------|
| `description` | Yes | Human-readable description. |
| `type` | Conditional | The field type (see table above). Required unless `choices` is provided. |
| `required` | No | Whether the field is required. Default: `false`. |
| `default_value` | No | Default value, must match the declared type. |
| `choices` | No | Fixed set of allowed string values. When set, `type` must be omitted. |
| `key_type` | Conditional | Key type for `dict` fields. Required when `type = "dict"`. |
| `value_type` | Conditional | Value type for `dict` fields. Required when `type = "dict"`. |
| `item_type` | No | Item type for `list` fields. When `"concept"`, requires `item_concept_ref`. |
| `concept_ref` | Conditional | Concept reference for `concept`-typed fields. Required when `type = "concept"`. |
| `item_concept_ref` | Conditional | Concept reference for list items when `item_type = "concept"`. |

### A Complete Example

This concept demonstrates every field type:

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

### Concept Refinement

Refinement establishes a specialization relationship between concepts. A refined concept inherits the semantic meaning of its parent and can be used anywhere the parent is expected.

```toml
[concept.NonCompeteClause]
description = "A non-compete clause in an employment contract"
refines     = "ContractClause"
```

`NonCompeteClause` is a specialization of `ContractClause`. Any pipe that accepts `ContractClause` also accepts `NonCompeteClause`.

The `refines` field accepts three forms of concept reference:

- **Bare code:** `"ContractClause"` — resolved within the current bundle's domain.
- **Domain-qualified:** `"legal.ContractClause"` — resolved within the current package.
- **Cross-package:** `"acme_legal->legal.contracts.NonDisclosureAgreement"` — resolved from a dependency.

Cross-package refinement is how you build on another package's vocabulary without merging namespaces. See [Namespace Resolution](#page-namespace-resolution) for the full resolution rules.

### Native Concepts

MTHDS provides a set of built-in concepts that are always available in every bundle without declaration. They belong to the reserved `native` domain.

| Code | Description |
|------|-------------|
| `Dynamic` | A dynamically-typed value. |
| `Text` | A text string. |
| `Image` | An image (binary). |
| `Document` | A document (e.g., PDF). |
| `Html` | HTML content. |
| `TextAndImages` | Combined text and image content. |
| `Number` | A numeric value. |
| `ImgGenPrompt` | A prompt for image generation. |
| `Page` | A single page extracted from a document. |
| `JSON` | A JSON value. |
| `Anything` | Accepts any type. |

Native concepts can be referenced by bare code (`Text`, `Image`) or by qualified reference (`native.Text`, `native.Image`). Bare native codes always take priority during name resolution.

A bundle cannot declare a concept with the same code as a native concept. For example, defining `[concept] Text = "My custom text"` is an error.

### See Also

- [Specification: Concept Definitions](03-specification.md#concept-definitions) — normative reference for all concept fields and validation rules.
- [Pipes](#page-pipes--operators) — how concepts are used as pipe inputs and outputs.
- [Native Concepts table](03-specification.md#native-concepts) — full list with qualified references.

---

## Page: Pipes — Operators

Pipes are typed transformations — the actions in MTHDS. Each pipe has a typed signature: it declares what concepts it accepts as input and what concept it produces as output.

MTHDS defines two categories of pipes:

- **Operators** — pipes that perform a single transformation (this page).
- **Controllers** — pipes that orchestrate other pipes (next page).

### Common Fields

All pipe types share these base fields:

| Field | Required | Description |
|-------|----------|-------------|
| `type` | Yes | The pipe type (e.g., `"PipeLLM"`, `"PipeSequence"`). |
| `description` | Yes | Human-readable description of what this pipe does. |
| `inputs` | No | Input declarations. Keys are input names (`snake_case`), values are concept references. |
| `output` | Yes | The output concept reference. |

**Pipe codes** are the keys in `[pipe.<pipe_code>]` tables. They must be `snake_case`, matching `[a-z][a-z0-9_]*`.

**Concept references in inputs and output** support an optional multiplicity suffix:

| Syntax | Meaning |
|--------|---------|
| `ConceptName` | A single instance. |
| `ConceptName[]` | A variable-length list. |
| `ConceptName[N]` | A fixed-length list of exactly N items (N ≥ 1). |

### PipeLLM

Generates output by invoking a large language model with a prompt.

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

**What this does:** Takes a `Page` input, sends it to an LLM with the given prompt and system prompt, and produces a `CVAnalysis` output.

**Key fields:**

| Field | Required | Description |
|-------|----------|-------------|
| `prompt` | No | The LLM prompt template. Supports Jinja2 syntax and `@variable` / `$variable` shorthand. |
| `system_prompt` | No | System prompt for the LLM. Falls back to the bundle-level `system_prompt` if omitted. |
| `model` | No | LLM model choice. Supports routing profiles (prefixed with `$`). |
| `model_to_structure` | No | Model used for structuring the LLM output into the declared concept. |
| `structuring_method` | No | How the output is structured: `"direct"` or `"preliminary_text"`. |

**Prompt template syntax:**

- `{{ variable_name }}` — standard Jinja2 variable substitution.
- `@variable_name` — shorthand, preprocessed to Jinja2 syntax.
- `$variable_name` — shorthand, preprocessed to Jinja2 syntax.
- Dotted paths are supported: `{{ doc_request.document_type }}`, `@doc_request.priority`.

Every variable referenced in the prompt must correspond to a declared input, and every declared input must be referenced in the prompt or system prompt. Unused inputs are rejected.

### PipeFunc

Calls a registered Python function.

```toml
[pipe.capitalize_text]
type          = "PipeFunc"
description   = "Capitalize the input text"
inputs        = { text = "Text" }
output        = "Text"
function_name = "my_package.text_utils.capitalize"
```

**What this does:** Passes the `Text` input to the Python function `my_package.text_utils.capitalize` and returns the result as `Text`.

**Key fields:**

| Field | Required | Description |
|-------|----------|-------------|
| `function_name` | Yes | The fully-qualified name of the Python function to call. |

PipeFunc bridges MTHDS with custom code. The function must be registered in the runtime.

### PipeImgGen

Generates images using an image generation model.

```toml
[pipe.generate_portrait]
type        = "PipeImgGen"
description = "Generate a portrait image from a description"
inputs      = { description = "Text" }
output      = "Image"
prompt      = "A professional portrait: $description"
model       = "$gen-image-testing"
```

**What this does:** Takes a `Text` description, sends it to an image generation model, and produces an `Image` output.

**Key fields:**

| Field | Required | Description |
|-------|----------|-------------|
| `prompt` | Yes | The image generation prompt. Supports Jinja2 and `$variable` shorthand. |
| `negative_prompt` | No | Concepts to avoid in generation. |
| `model` | No | Image generation model choice. Supports routing profiles (prefixed with `$`). |
| `aspect_ratio` | No | Desired aspect ratio for the generated image. |
| `seed` | No | Random seed for reproducibility. `"auto"` lets the model choose. |
| `output_format` | No | Image output format (e.g., `"png"`, `"jpeg"`). |

### PipeExtract

Extracts structured content from documents (e.g., PDF pages).

```toml
[pipe.extract_cv]
type        = "PipeExtract"
description = "Extract text content from a CV PDF document"
inputs      = { cv_pdf = "Document" }
output      = "Page[]"
model       = "@default-text-from-pdf"
```

**What this does:** Takes a `Document` input and extracts its content as a variable-length list of `Page` objects.

**Key fields:**

| Field | Required | Description |
|-------|----------|-------------|
| `model` | No | Extraction model choice. Supports routing profiles (prefixed with `@`). |
| `max_page_images` | No | Maximum number of page images to process. |
| `page_image_captions` | No | Whether to generate captions for page images. |
| `page_views` | No | Whether to generate page views. |
| `page_views_dpi` | No | DPI for page view rendering. |

**Constraints:** PipeExtract requires exactly one input (typically `Document` or a concept refining it) and the output must be `"Page[]"`.

### PipeCompose

Composes output by assembling data from working memory. PipeCompose has two modes: **template mode** and **construct mode**. Exactly one must be used.

#### Template Mode

Uses a Jinja2 template to produce text output:

```toml
[pipe.format_report]
type        = "PipeCompose"
description = "Format analysis results into a report"
inputs      = { analysis = "CVAnalysis", candidate_name = "Text" }
output      = "Text"
template    = """
# Report for {{ candidate_name }}

{{ analysis.summary }}

Skills: {{ analysis.skills }}
"""
```

The `template` field can be a plain string (as above) or a table with additional options:

```toml
[pipe.format_report.template]
template        = "# Report for {{ candidate_name }}"
category        = "basic"
templating_style = "default"
```

#### Construct Mode

Composes structured output field-by-field from working memory:

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

Each field in the `construct` table defines how a field of the output concept is composed:

| Value form | Method | Description |
|------------|--------|-------------|
| Literal (`string`, `integer`, `float`, `boolean`, `array`) | Fixed | The field value is the literal. |
| `{ from = "path" }` | Variable reference | The field value comes from a variable in working memory. |
| `{ from = "path", list_to_dict_keyed_by = "attr" }` | Variable reference with transform | Converts a list to a dict keyed by the named attribute. |
| `{ template = "..." }` | Template | The field value is rendered from a Jinja2 template string. |
| Nested table (no `from` or `template` key) | Nested construct | The field is recursively composed. |

**Constraint:** PipeCompose output must be a single concept — multiplicity (`[]` or `[N]`) is not allowed.

### See Also

- [Specification: Pipe Definitions](03-specification.md#pipe-definitions) — normative reference for all pipe types and validation rules.
- [Pipes — Controllers](#page-pipes--controllers) — orchestrating multiple pipes.

---

## Page: Pipes — Controllers

Controllers are pipes that orchestrate other pipes. They do not perform transformations themselves — they arrange when and how operator pipes (and other controllers) execute.

### PipeSequence

Executes a series of pipes in order. Each step's output is added to working memory, where subsequent steps can consume it.

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

**What this does:** Runs `extract_pages` first, stores its output as `pages` in working memory. Then runs `analyze_content` (which can use `pages`), stores the result as `analysis`. Finally runs `generate_summary`, producing the final `AnalysisResult`.

**Step fields:**

| Field | Required | Description |
|-------|----------|-------------|
| `pipe` | Yes | Pipe reference (bare, domain-qualified, or package-qualified). |
| `result` | No | Name under which the step's output is stored in working memory. |
| `nb_output` | No | Expected number of output items. Mutually exclusive with `multiple_output`. |
| `multiple_output` | No | Whether to expect multiple output items. Mutually exclusive with `nb_output`. |
| `batch_over` | No | Working memory variable to iterate over (inline batch). Requires `batch_as`. |
| `batch_as` | No | Name for each item during inline batch iteration. Requires `batch_over`. |

A sequence must contain at least one step.

Inline batching (`batch_over` / `batch_as`) allows iterating over a list within a sequence step, without needing a dedicated `PipeBatch`. Both must be provided together, and they must not have the same value.

### PipeParallel

Executes multiple pipes concurrently. Each branch operates independently.

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

**What this does:** Runs `extract_cv` and `extract_job_offer` at the same time. With `add_each_output = true`, each branch's output is individually stored in working memory under its `result` name.

**Key fields:**

| Field | Required | Description |
|-------|----------|-------------|
| `branches` | Yes | List of sub-pipe invocations to execute concurrently. |
| `add_each_output` | No | If `true`, each branch's output is stored individually. Default: `false`. |
| `combined_output` | No | Concept reference for a combined output that merges all branch results. |

At least one of `add_each_output` or `combined_output` must be set — otherwise the pipe produces no usable output.

### PipeCondition

Routes execution to different pipes based on an evaluated condition.

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

**What this does:** Evaluates `doc_request.document_type` and routes to the matching pipe. If the document type is `"technical"`, it runs `process_technical`. If no outcome matches, `"continue"` means execution proceeds without running a sub-pipe.

**Key fields:**

| Field | Required | Description |
|-------|----------|-------------|
| `expression_template` | Conditional | A Jinja2 template that evaluates to a string matching an outcome key. Exactly one of `expression_template` or `expression` is required. |
| `expression` | Conditional | A static expression string. Exactly one of `expression_template` or `expression` is required. |
| `outcomes` | Yes | Maps outcome strings to pipe references. Must have at least one entry. |
| `default_outcome` | Yes | The pipe reference (or special outcome) to use when no outcome key matches. |
| `add_alias_from_expression_to` | No | If set, stores the evaluated expression value in working memory under this name. |

**Special outcomes:** Two string values have special meaning and are not treated as pipe references:

- `"fail"` — abort execution with an error.
- `"continue"` — skip this branch and continue without executing a sub-pipe.

### PipeBatch

Maps a single pipe over each item in a list input, producing a list output.

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

**What this does:** Takes a list of `Topic` items and runs `generate_joke` on each one, producing a list of `Joke` outputs.

**Key fields:**

| Field | Required | Description |
|-------|----------|-------------|
| `branch_pipe_code` | Yes | The pipe reference to invoke for each item. |
| `input_list_name` | Yes | The name of the input that contains the list to iterate over. Must exist as a key in `inputs`. |
| `input_item_name` | Yes | The name under which each individual item is passed to the branch pipe. |

**Constraints:**

- `input_item_name` must not equal `input_list_name`.
- `input_item_name` must not equal any key in `inputs`.

A naming tip: use the plural for the list and its singular form for the item (e.g., list `"topics"` → item `"topic"`).

### Pipe Reference Syntax in Controllers

Every location in a controller that references another pipe supports three forms:

| Form | Syntax | Example |
|------|--------|---------|
| Bare | `pipe_code` | `"extract_clause"` |
| Domain-qualified | `domain.pipe_code` | `"legal.contracts.extract_clause"` |
| Package-qualified | `alias->domain.pipe_code` | `"docproc->extraction.extract_text"` |

These references appear in:

- `steps[].pipe` (PipeSequence)
- `branches[].pipe` (PipeParallel)
- `outcomes` values (PipeCondition)
- `default_outcome` (PipeCondition)
- `branch_pipe_code` (PipeBatch)

Pipe *definitions* (the `[pipe.<pipe_code>]` table keys) are always bare `snake_case` names. Namespacing applies only to pipe *references*.

### See Also

- [Specification: Controller Definitions](03-specification.md#controller-pipesequence) — normative reference for all controller types and validation rules.
- [Pipes — Operators](#page-pipes--operators) — the individual transformations that controllers orchestrate.

---

## Page: Putting It All Together

Before moving on to domains and namespace resolution, here is a complete bundle that uses both operators and controllers. It shows how concepts, pipes, and working memory flow together.

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

### How It Works

1. `generate_jokes_from_topics` is a `PipeSequence` — the entry point.
2. Step 1 calls `generate_topics`, a `PipeLLM` that produces exactly 3 `Topic` items (`Topic[3]`). The result is stored in working memory as `topics`.
3. Step 2 calls `batch_generate_jokes`, a `PipeBatch` that iterates over `topics`. For each `Topic`, it invokes `generate_joke`.
4. `generate_joke` is a `PipeLLM` that takes one `topic` and produces one `Joke`.
5. The batch collects all jokes into `Joke[]`, which becomes the final output.

Two concepts (`Topic` and `Joke`) both refine the native `Text` concept. Four pipes — one sequence, one batch, two LLM operators — work together through working memory.

---

## Page: Domains

Domains are namespaces for concepts and pipes within a bundle. Every bundle declares exactly one domain in its header, and all concepts and pipes in that bundle belong to that domain.

### What Domains Are For

Domains serve two purposes:

1. **Organization** — group related concepts and pipes under a meaningful name. A domain like `legal.contracts` tells you what the bundle is about.
2. **Namespacing** — prevent naming collisions. Two bundles in different domains can define concepts or pipes with the same name without conflict.

### Declaring a Domain

The `domain` field in the bundle header sets the namespace:

```toml
domain = "legal.contracts"
```

Everything in this file — every concept and every pipe — belongs to `legal.contracts`.

### Hierarchical Domains

Domains can be hierarchical, using `.` as the separator:

```toml
legal
legal.contracts
legal.contracts.shareholder
```

This allows natural organization of complex knowledge areas. A large package covering legal methods might structure its domains as a tree:

- `legal` — general legal concepts and utilities
- `legal.contracts` — contract-specific methods
- `legal.contracts.shareholder` — shareholder agreement specifics

**The hierarchy is purely organizational.** There is no implicit scope or inheritance between parent and child domains. `legal.contracts` does not automatically have access to concepts defined in `legal`. If a bundle in `legal.contracts` needs a concept from `legal`, it uses an explicit domain-qualified reference — the same as any other cross-domain reference.

### Domain Naming Rules

- A domain code is one or more `snake_case` segments separated by `.`.
- Each segment must match `[a-z][a-z0-9_]*`.
- Recommended depth: 1–3 levels.
- Recommended segment length: 1–4 words.

### Reserved Domains

Three domain names are reserved and cannot be used as the first segment of any user-defined domain:

| Domain | Purpose |
|--------|---------|
| `native` | Built-in concept types (`Text`, `Image`, `Document`, etc.). |
| `mthds` | Reserved for the MTHDS standard. |
| `pipelex` | Reserved for the reference implementation. |

For example, `native.custom` and `pipelex.utils` are invalid domain names.

### Same Domain Across Bundles

Within a single package, multiple bundles can share the same domain. When they do, their concepts and pipes merge into a single namespace:

```
my-package/
├── METHODS.toml
├── general_legal.mthds       # domain = "legal"
└── legal_utils.mthds         # domain = "legal"
```

Both files contribute concepts and pipes to the `legal` domain. If both files define a concept `ContractClause`, that is a conflict — an error at load time.

### Domains Across Packages

Two packages can both declare `domain = "recruitment"`. Their concepts and pipes are completely independent — there is no merging of namespaces across packages. The package boundary is the true isolation boundary.

This means `recruitment.CandidateProfile` from Package A and `recruitment.CandidateProfile` from Package B are different things. To use something from another package, you must qualify the reference with the package alias (see [Namespace Resolution](#page-namespace-resolution)).

The domain name remains valuable for **discovery**: searching for "all packages in the recruitment domain" is a meaningful query. But discovery does not merge namespaces.

### See Also

- [Specification: Domain Naming Rules](03-specification.md#domain-naming-rules) — normative reference.
- [Namespace Resolution](#page-namespace-resolution) — how references are resolved across bundles and packages.

---

## Page: Namespace Resolution

When a pipe references a concept or another pipe, MTHDS resolves that reference through a well-defined set of rules. Understanding these rules is essential for working with multi-bundle packages and cross-package dependencies.

### Three Forms of Reference

Every reference to a concept or pipe uses one of three forms:

| Form | Syntax | Example |
|------|--------|---------|
| **Bare** | `name` | `ContractClause`, `extract_clause` |
| **Domain-qualified** | `domain_path.name` | `legal.contracts.NonCompeteClause`, `scoring.compute_score` |
| **Package-qualified** | `alias->domain_path.name` | `acme->legal.ContractClause`, `docproc->extraction.extract_text` |

### How References Are Parsed

**Cross-package references** (`->` syntax): The string is split on the first `->`. The left part is the package alias, the right part is parsed as a domain-qualified or bare reference.

**Domain-qualified references** (`.` syntax): The string is split on the **last `.`**. The left part is the domain path, the right part is the local code (concept code or pipe code).

**Disambiguation** between concepts and pipes in a domain-qualified reference relies on casing:

- `snake_case` final segment → pipe code (e.g., `scoring.compute_score`)
- `PascalCase` final segment → concept code (e.g., `scoring.WeightedScore`)

This is unambiguous because concept codes and pipe codes follow mutually exclusive casing conventions.

### Resolution Order for Bare References

#### Bare Concept References

When resolving a bare concept code like `ContractClause`:

1. **Native concepts** — check if it matches a native concept code (`Text`, `Image`, etc.). Native concepts always take priority.
2. **Current bundle** — check concepts declared in the same `.mthds` file.
3. **Same domain, other bundles** — if the bundle is part of a package, check concepts in other bundles that declare the same domain.
4. **Error** — if not found in any of the above.

Bare concept references do not fall through to other domains or other packages.

#### Bare Pipe References

When resolving a bare pipe code like `extract_clause`:

1. **Current bundle** — check pipes declared in the same `.mthds` file.
2. **Same domain, other bundles** — if the bundle is part of a package, check pipes in other bundles that declare the same domain.
3. **Error** — if not found.

Bare pipe references do not fall through to other domains or other packages.

### Resolution of Domain-Qualified References

When resolving `domain_path.name` (e.g., `legal.contracts.extract_clause`):

1. Look in the named domain within the **current package**.
2. If not found: **error**.

Domain-qualified references are explicit about which domain to look in. They do not fall through to dependencies.

### Resolution of Package-Qualified References

When resolving `alias->domain_path.name` (e.g., `docproc->extraction.extract_text`):

1. Identify the dependency by the alias. The alias must match a key in the `[dependencies]` section of the consuming package's `METHODS.toml`.
2. Look in the named domain of the **resolved dependency package**.
3. If not found: **error**.

**Visibility rules for cross-package pipe references:**

- The referenced pipe must be exported by the dependency package (listed in its `[exports]` section or declared as `main_pipe` in a bundle header).
- If the pipe is not exported, the reference fails with a visibility error.

**Concepts are always public.** No visibility check is needed for cross-package concept references.

### Visibility Within a Package

When a package has a `METHODS.toml` manifest:

- **Same-domain references** — always allowed. A pipe in `legal.contracts` can reference any other pipe in `legal.contracts`.
- **Cross-domain references** (within the same package) — the target pipe must be exported. A pipe in `scoring` referencing `legal.contracts.extract_clause` requires that `extract_clause` is listed in `[exports.legal.contracts]` or is the `main_pipe` of a bundle in that domain.
- **Bare references** — always allowed (they resolve within the same domain).

When no manifest is present (standalone bundle), all pipes are treated as public.

### A Concrete Example

Package A depends on Package B with alias `scoring_lib`.

Package B's manifest (`METHODS.toml`):

```toml
[package]
address = "github.com/mthds/scoring-lib"
version = "0.5.0"
description = "Scoring utilities"

[exports.scoring]
pipes = ["compute_weighted_score"]
```

Package B's bundle (`scoring.mthds`):

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

Package A's bundle (`analysis.mthds`):

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
2. Look up `scoring_lib` in Package A's `[dependencies]` — found.
3. Parse remainder: split on last `.` → domain `scoring`, pipe code `compute_weighted_score`.
4. Look in domain `scoring` of Package B — pipe found.
5. Visibility check: `compute_weighted_score` is in `[exports.scoring]` — accessible.
6. Resolution succeeds.

**If Package A tried `scoring_lib->scoring.internal_helper`:**

Steps 1–4 would succeed (the pipe exists), but the visibility check would fail — `internal_helper` is not in `[exports.scoring]` and is not `main_pipe`. This is a visibility error.

**Cross-package concept references** work the same way but skip the visibility check, since concepts are always public:

```toml
[concept.DetailedScore]
description = "An extended score with additional analysis"
refines     = "scoring_lib->scoring.ScoreResult"
```

### Resolution Flowchart

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

### See Also

- [Specification: Namespace Resolution Rules](03-specification.md#page-namespace-resolution-rules) — the normative, formal definition of all resolution rules.
- [Domains](#page-domains) — how domains organize concepts and pipes.
- [The Package System: Exports & Visibility](02-the-package-system.md) — how packages control what they expose.
