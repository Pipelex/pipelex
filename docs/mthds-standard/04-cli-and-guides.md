# CLI, Tooling & Guides

<!-- Source document for the MTHDS docs website.
     Each "## Page:" section becomes an individual MkDocs page.

     Tone: Practical, step-by-step. Every command must be copy-pasteable.
     Every guide must walk through a complete workflow end to end.
     Uses the `mthds` CLI (the standard's official tool), not implementation-specific commands.
     Cross-references use [text](link) format pointing to the spec and other pages.
-->

## Page: CLI Reference

The `mthds` CLI is the official command-line tool for working with MTHDS packages. It covers validation, execution, and the full package management lifecycle.

### Core Commands

#### `mthds validate`

Validate `.mthds` files, individual pipes, or an entire project.

**Usage:**

```
mthds validate <target>
mthds validate --bundle <file.mthds>
mthds validate --bundle <file.mthds> --pipe <pipe_code>
mthds validate --all
```

**Arguments:**

| Argument | Description |
|----------|-------------|
| `target` | A pipe code or a bundle file path (`.mthds`). Auto-detected based on file extension. |

**Options:**

| Option | Short | Description |
|--------|-------|-------------|
| `--pipe` | | Pipe code to validate. Optional when using `--bundle`. |
| `--bundle` | | Bundle file path (`.mthds`). Validates all pipes in the bundle. |
| `--all` | `-a` | Validate all pipes in all loaded libraries. |
| `--library-dir` | `-L` | Directory to search for `.mthds` files. Can be specified multiple times. |

**Examples:**

```bash
# Validate a single pipe by code
mthds validate extract_clause

# Validate a bundle file
mthds validate contract_analysis.mthds

# Validate a specific pipe within a bundle
mthds validate --bundle contract_analysis.mthds --pipe extract_clause

# Validate all pipes in the project
mthds validate --all
```

---

#### `mthds run`

Execute a method. Loads the bundle, resolves dependencies, and runs the specified pipe.

**Usage:**

```
mthds run <target>
mthds run --bundle <file.mthds>
mthds run --bundle <file.mthds> --pipe <pipe_code>
mthds run <directory/>
```

**Arguments:**

| Argument | Description |
|----------|-------------|
| `target` | A pipe code, a bundle file path (`.mthds`), or a pipeline directory. Auto-detected. |

**Options:**

| Option | Short | Description |
|--------|-------|-------------|
| `--pipe` | | Pipe code to run. If omitted when using `--bundle`, runs the bundle's `main_pipe`. |
| `--bundle` | | Bundle file path (`.mthds`). |
| `--inputs` | `-i` | Path to a JSON file with input data. |
| `--output-dir` | `-o` | Base directory for all outputs. Default: `results`. |
| `--dry-run` | | Run in dry mode (no actual inference calls). |
| `--library-dir` | `-L` | Directory to search for `.mthds` files. Can be specified multiple times. |

**Examples:**

```bash
# Run a bundle's main pipe
mthds run joke_generation.mthds

# Run a specific pipe within a bundle
mthds run --bundle contract_analysis.mthds --pipe extract_clause

# Run with input data
mthds run extract_clause --inputs data.json

# Run a pipeline directory (auto-detects bundle and inputs)
mthds run pipeline_01/

# Dry run (no inference calls)
mthds run joke_generation.mthds --dry-run
```

When a directory is provided as the target, `mthds run` auto-detects the `.mthds` bundle file and an optional `inputs.json` file within it.

---

### Package Commands (`mthds pkg`)

Package commands manage the full lifecycle of MTHDS packages: initialization, dependencies, distribution, and discovery.

#### `mthds pkg init`

Initialize a `METHODS.toml` package manifest from `.mthds` files in the current directory.

**Usage:**

```
mthds pkg init [--force]
```

**Options:**

| Option | Short | Description |
|--------|-------|-------------|
| `--force` | `-f` | Overwrite an existing `METHODS.toml`. |

The command scans all `.mthds` files recursively, extracts domain and pipe information, and generates a skeleton `METHODS.toml` with a placeholder address and auto-populated exports. Edit the generated file to set the correct address and refine exports.

**Example:**

```bash
mthds pkg init
# Created METHODS.toml with:
#   Domains: 2
#   Total pipes: 7
#   Bundles scanned: 3
#
# Edit METHODS.toml to set the correct address and configure exports.
```

---

#### `mthds pkg list`

Display the package manifest for the current directory.

**Usage:**

```
mthds pkg list
```

Walks up from the current directory to find a `METHODS.toml` and displays its contents: package identity, dependencies, and exports.

---

#### `mthds pkg add`

Add a dependency to `METHODS.toml`.

**Usage:**

```
mthds pkg add <address> [--alias NAME] [--version CONSTRAINT] [--path LOCAL_PATH]
```

**Arguments:**

| Argument | Description |
|----------|-------------|
| `address` | Package address (e.g., `github.com/mthds/document-processing`). |

**Options:**

| Option | Short | Description |
|--------|-------|-------------|
| `--alias` | `-a` | Dependency alias. Auto-derived from the last path segment if not provided. |
| `--version` | `-v` | Version constraint. Default: `0.1.0`. |
| `--path` | `-p` | Local filesystem path to the dependency (for development). |

**Examples:**

```bash
# Add a remote dependency (alias auto-derived as "document_processing")
mthds pkg add github.com/mthds/document-processing --version "^1.0.0"

# Add with a custom alias
mthds pkg add github.com/acme/legal-tools --alias acme_legal --version "^0.3.0"

# Add a local development dependency
mthds pkg add github.com/team/scoring --path ../scoring-lib --version "^0.5.0"
```

---

#### `mthds pkg lock`

Resolve dependencies and generate `methods.lock`.

**Usage:**

```
mthds pkg lock
```

Reads the `[dependencies]` section of `METHODS.toml`, resolves all versions (including transitive dependencies), and writes the lock file. The lock file records exact versions and SHA-256 integrity hashes for reproducible builds.

---

#### `mthds pkg install`

Fetch and cache all dependencies from `methods.lock`.

**Usage:**

```
mthds pkg install
```

For each entry in the lock file, checks the local cache (`~/.mthds/packages/`). Missing packages are fetched via Git. After fetching, integrity hashes are verified against the lock file.

---

#### `mthds pkg update`

Re-resolve dependencies to latest compatible versions and update `methods.lock`.

**Usage:**

```
mthds pkg update
```

Performs a fresh resolution of all dependencies (ignoring the existing lock file), writes the updated lock file, and displays a diff showing added, removed, and updated packages.

---

#### `mthds pkg index`

Build and display the local package index.

**Usage:**

```
mthds pkg index [--cache]
```

**Options:**

| Option | Short | Description |
|--------|-------|-------------|
| `--cache` | `-c` | Index cached packages instead of the current project. |

Displays a summary table showing each package's address, version, description, and counts of domains, concepts, and pipes.

---

#### `mthds pkg search`

Search the package index for concepts and pipes.

**Usage:**

```
mthds pkg search <query> [options]
mthds pkg search --accepts <concept> [--produces <concept>]
```

**Arguments:**

| Argument | Description |
|----------|-------------|
| `query` | Search term (case-insensitive substring match). Optional if using `--accepts` or `--produces`. |

**Options:**

| Option | Short | Description |
|--------|-------|-------------|
| `--domain` | `-d` | Filter results to a specific domain. |
| `--concept` | | Show only matching concepts. |
| `--pipe` | | Show only matching pipes. |
| `--cache` | `-c` | Search cached packages instead of the current project. |
| `--accepts` | | Find pipes that accept this concept (type-compatible search). |
| `--produces` | | Find pipes that produce this concept (type-compatible search). |

**Examples:**

```bash
# Text search for concepts and pipes
mthds pkg search "contract"

# Search only pipes in a specific domain
mthds pkg search "extract" --pipe --domain legal.contracts

# Type-compatible search: "What can I do with a Document?"
mthds pkg search --accepts Document

# Type-compatible search: "What produces a NonCompeteClause?"
mthds pkg search --produces NonCompeteClause

# Combined: "What transforms Text into ScoreResult?"
mthds pkg search --accepts Text --produces ScoreResult
```

Type-compatible search uses the [Know-How Graph](02-the-package-system.md#page-the-know-how-graph) to find pipes by their typed signatures. It understands concept refinement: searching for pipes that accept `Text` also finds pipes that accept `NonCompeteClause` (since `NonCompeteClause` refines `Text`).

---

#### `mthds pkg inspect`

Display detailed information about a package.

**Usage:**

```
mthds pkg inspect <address> [--cache]
```

**Arguments:**

| Argument | Description |
|----------|-------------|
| `address` | Package address to inspect. |

**Options:**

| Option | Short | Description |
|--------|-------|-------------|
| `--cache` | `-c` | Look in the package cache instead of the current project. |

Displays the package's metadata, domains, concepts (with structure fields and refinement), and pipe signatures (with inputs, outputs, and export status).

**Example:**

```bash
mthds pkg inspect github.com/acme/legal-tools
```

---

#### `mthds pkg graph`

Query the Know-How Graph for concept and pipe relationships.

**Usage:**

```
mthds pkg graph --from <concept_id> [--to <concept_id>] [options]
mthds pkg graph --check <pipe_key_a>,<pipe_key_b>
```

**Options:**

| Option | Short | Description |
|--------|-------|-------------|
| `--from` | `-f` | Concept ID — find pipes that accept it. Format: `package_address::concept_ref`. |
| `--to` | `-t` | Concept ID — find pipes that produce it. |
| `--check` | | Two pipe keys comma-separated — check if the output of the first is compatible with an input of the second. |
| `--max-depth` | `-m` | Maximum chain depth when using `--from` and `--to` together. Default: `3`. |
| `--compose` | | Show an MTHDS composition template for discovered chains. Requires both `--from` and `--to`. |
| `--cache` | `-c` | Use cached packages instead of the current project. |

**Examples:**

```bash
# Find all pipes that accept a specific concept
mthds pkg graph --from "__native__::native.Document"

# Find all pipes that produce a specific concept
mthds pkg graph --to "github.com/acme/legal-tools::legal.contracts.NonCompeteClause"

# Find chains from Document to NonCompeteClause (auto-composition)
mthds pkg graph \
  --from "__native__::native.Document" \
  --to "github.com/acme/legal-tools::legal.contracts.NonCompeteClause"

# Same query, but generate an MTHDS snippet for the chain
mthds pkg graph \
  --from "__native__::native.Document" \
  --to "github.com/acme/legal-tools::legal.contracts.NonCompeteClause" \
  --compose

# Check if two pipes are compatible (can be chained)
mthds pkg graph --check "github.com/acme/legal-tools::extract_pages,github.com/acme/legal-tools::analyze_content"
```

When both `--from` and `--to` are provided, the command searches for multi-step pipe chains through the graph, up to `--max-depth` hops. With `--compose`, it generates a ready-to-use MTHDS `PipeSequence` snippet for each discovered chain.

---

#### `mthds pkg publish`

Validate that a package is ready for distribution.

**Usage:**

```
mthds pkg publish [--tag]
```

**Options:**

| Option | Description |
|--------|-------------|
| `--tag` | Create a local git tag `v{version}` if validation passes. |

Runs 15 validation checks across seven categories:

| Category | Checks |
|----------|--------|
| **Manifest** | `METHODS.toml` exists and parses; required fields are valid; `mthds_version` constraint is parseable and satisfiable. |
| **Manifest completeness** | Authors and license are present (warnings if missing). |
| **Bundles** | At least one `.mthds` file exists; all bundles parse without error. |
| **Exports** | Every exported pipe actually exists in the scanned bundles. |
| **Visibility** | Cross-domain pipe references respect export rules. |
| **Dependencies** | No wildcard (`*`) version constraints (warning). |
| **Lock file** | `methods.lock` exists and includes all remote dependencies; parses without error. |
| **Git** | Working directory is clean; version tag does not already exist. |

Errors block publishing. Warnings are advisory. With `--tag`, the command creates a `v{version}` git tag locally if all checks pass.

**Example:**

```bash
# Validate readiness
mthds pkg publish

# Validate and create a git tag
mthds pkg publish --tag
```

---

## Page: Editor Support

The MTHDS editor extension for VS Code and Cursor provides syntax highlighting, semantic tokens, formatting, and validation for `.mthds` files. It is the recommended way to work with MTHDS.

### Installation

Install the **Pipelex** extension from the VS Code Marketplace:

1. Open VS Code or Cursor.
2. Go to Extensions (`Ctrl+Shift+X` / `Cmd+Shift+X`).
3. Search for **Pipelex**.
4. Click **Install**.

The extension activates automatically for `.mthds` files.

### Features

#### Syntax Highlighting

The extension provides a full TextMate grammar for `.mthds` files, built on top of TOML highlighting. It recognizes MTHDS-specific constructs: pipe sections, concept sections, prompt templates, Jinja2 variables (`{{ }}`, `@variable`, `$variable`), and HTML content embedded in prompts.

Markdown code blocks tagged as `mthds` or `toml` also receive syntax highlighting when the extension is active.

#### Semantic Tokens

Beyond TextMate grammar-based highlighting, the extension provides 7 semantic token types that distinguish MTHDS-specific elements:

| Token type | Applies to | Visual hint |
|------------|-----------|-------------|
| `mthdsConcept` | Concept names (e.g., `ContractClause`, `Text`) | Type color |
| `mthdsPipeType` | Pipe type values (e.g., `PipeLLM`, `PipeSequence`) | Type color, bold |
| `mthdsDataVariable` | Data variables in prompts | Variable color |
| `mthdsPipeName` | Pipe names in references | Function color |
| `mthdsPipeSection` | Pipe section headers (`[pipe.my_pipe]`) | Keyword color, bold |
| `mthdsConceptSection` | Concept section headers (`[concept.MyConcept]`) | Keyword color, bold |
| `mthdsModelRef` | Model field references (`$preset`, `@alias`) | Variable color, bold |

Semantic tokens are enabled by default. To toggle them:

- `pipelex.mthds.semanticTokens` — MTHDS-specific semantic tokens.
- `pipelex.syntax.semanticTokens` — TOML table/array key tokens.

#### Formatting

The extension includes a built-in formatter for `.mthds` and `.toml` files. It uses the same engine as the `plxt` CLI (see [Formatting & Linting](#page-formatting--linting)). Format on save works out of the box.

Formatting options are configurable in VS Code settings under `pipelex.formatter.*` (e.g., `alignEntries`, `columnWidth`, `trailingNewline`).

#### Schema Validation

The extension supports JSON Schema-based validation and completion for TOML files. When the MTHDS JSON Schema is configured (see [MTHDS JSON Schema](#page-mthds-json-schema)), the editor provides:

- Autocomplete suggestions for field names and values.
- Inline validation errors for invalid fields or types.
- Hover documentation for known fields.

Schema support is enabled by default (`pipelex.schema.enabled`).

#### Additional Commands

The extension contributes several commands accessible via the Command Palette:

| Command | Description |
|---------|-------------|
| **TOML: Copy as JSON** | Copy selected TOML as JSON. |
| **TOML: Copy as TOML** | Copy selected text as TOML. |
| **TOML: Paste as JSON** | Paste clipboard content as JSON. |
| **TOML: Paste as TOML** | Paste clipboard content as TOML. |
| **TOML: Select Schema** | Choose a JSON Schema for the current TOML file. |

---

## Page: Formatting & Linting

`plxt` is the CLI tool for formatting and linting `.mthds` and `.toml` files. It ensures consistent style across MTHDS projects.

### Installation

`plxt` is distributed as a standalone binary. Install it via the instructions in the Pipelex documentation, or use the bundled version included with the VS Code extension.

### Formatting

Format `.mthds` and `.toml` files in place:

```bash
# Format all .mthds and .toml files in the current directory (recursive)
plxt format .

# Format a single file
plxt format contract_analysis.mthds

# Format and see what changed (check mode — exits non-zero if changes needed)
plxt format --check .
```

The `plxt format` command (also available as `plxt fmt`) aligns entries, normalizes whitespace, and ensures consistent TOML style. Files are modified in place.

### Linting

Lint `.mthds` and `.toml` files for structural issues:

```bash
# Lint all files in the current directory
plxt lint .

# Lint a single file
plxt lint contract_analysis.mthds
```

The `plxt lint` command (also available as `plxt check` or `plxt validate`) checks for TOML structural issues and reports errors.

### Configuration

`plxt` reads its configuration from a `.pipelex/plxt.toml` file in the project root or a parent directory. This file controls formatting rules (alignment, column width, trailing commas, etc.) and can define per-file-type overrides.

A basic configuration:

```toml
[formatting]
align_entries      = true
column_width       = 100
trailing_newline   = true
array_trailing_comma = true
```

For the full list of configuration options, see the Pipelex documentation.

### Editor Integration

When the VS Code extension is installed, `plxt` formatting runs automatically on save. The extension uses the same formatting engine, so files formatted via CLI and editor produce identical results.

---

## Page: MTHDS JSON Schema

The MTHDS standard includes a machine-readable JSON Schema that describes the structure of `.mthds` files. Tools and editors can use this schema for validation, autocompletion, and documentation.

### What It Covers

The schema defines the complete structure of an `.mthds` bundle:

- **Header fields**: `domain`, `description`, `system_prompt`, `main_pipe`.
- **Concept definitions**: both simple (string) and structured forms, including `structure` fields, `refines`, and all field types (`text`, `integer`, `number`, `boolean`, `date`, `list`, `dict`, `concept`, `choices`).
- **Pipe definitions**: all nine pipe types with their specific fields — `PipeLLM`, `PipeFunc`, `PipeImgGen`, `PipeExtract`, `PipeCompose`, `PipeSequence`, `PipeParallel`, `PipeCondition`, `PipeBatch`.
- **Sub-pipe blueprints**: the `steps`, `branches`, `outcomes`, and `construct` structures used by controllers and PipeCompose.

### Where to Find It

The schema is located at `pipelex/language/mthds_schema.json` in the Pipelex repository. It is auto-generated from the MTHDS data model to ensure it stays in sync with the implementation.

### How to Use It

#### With the VS Code Extension

The VS Code extension can use the schema for autocompletion and inline validation. Configure it via `pipelex.schema.associations` in your VS Code settings:

```json
{
  "pipelex.schema.associations": {
    ".*\\.mthds$": "path/to/mthds_schema.json"
  }
}
```

#### With Other Editors

Any editor that supports JSON Schema for TOML can use the MTHDS schema. Configure your editor's TOML language server to associate `.mthds` files with the schema.

#### For Tooling

The schema can be used programmatically for:

- Building custom validators for `.mthds` files.
- Generating documentation from the schema structure.
- Implementing autocompletion in non-VS Code editors.

For detailed guidance on building editor support, see [For Implementers: Building Editor Support](05-implementers-and-about.md).

---

## Page: Write Your First Method

This guide walks you through creating a working `.mthds` file from scratch. By the end, you will have a method that generates a short summary from a text input.

### Prerequisites

- A text editor with MTHDS support. Install the [VS Code extension](#page-editor-support) for the best experience.
- The `plxt` CLI installed for formatting (see [Formatting & Linting](#page-formatting--linting)).
- The `mthds` CLI installed for validation.

### Step 1: Create a `.mthds` File

Create a new file called `summarizer.mthds` and add a domain header:

```toml
domain      = "summarization"
description = "Text summarization methods"
```

Every bundle starts with a `domain` — a namespace for the concepts and pipes you will define. The domain name uses `snake_case` segments separated by dots.

### Step 2: Define a Concept

Add a concept to describe the kind of data your method produces:

```toml
domain      = "summarization"
description = "Text summarization methods"

[concept]
Summary = "A concise summary of a longer text"
```

This declares a simple concept called `Summary`. It has no internal structure — it is a semantic label that gives meaning to the data your pipe produces.

Concept codes use `PascalCase` (e.g., `Summary`, `ContractClause`, `CandidateProfile`).

### Step 3: Define a Pipe

Add a pipe that takes text input and produces a summary:

```toml
domain      = "summarization"
description = "Text summarization methods"
main_pipe   = "summarize"

[concept]
Summary = "A concise summary of a longer text"

[pipe.summarize]
type        = "PipeLLM"
description = "Summarize the input text in 2-3 sentences"
inputs      = { text = "Text" }
output      = "Summary"
prompt      = """
Summarize the following text in 2-3 concise sentences. Focus on the key points.

@text
"""
```

Here is what each field does:

- `type = "PipeLLM"` — this pipe uses a large language model to generate output.
- `inputs = { text = "Text" }` — the pipe accepts one input called `text`, of the native `Text` type.
- `output = "Summary"` — the pipe produces a `Summary` concept.
- `prompt` — the LLM prompt template. `@text` is shorthand for `{{ text }}`, injecting the input variable.

The `main_pipe = "summarize"` header marks this pipe as the bundle's primary entry point.

### Step 4: Format Your File

Run the formatter to ensure consistent style:

```bash
plxt fmt summarizer.mthds
```

The formatter aligns entries, normalizes whitespace, and ensures your file follows MTHDS style conventions.

### Step 5: Validate

Validate your bundle:

```bash
mthds validate summarizer.mthds
```

If everything is correct, you will see a success message. If there are errors — a misspelled concept reference, an unused input, a missing required field — the validator reports them with specific messages.

### The Complete File

```toml
domain      = "summarization"
description = "Text summarization methods"
main_pipe   = "summarize"

[concept]
Summary = "A concise summary of a longer text"

[pipe.summarize]
type        = "PipeLLM"
description = "Summarize the input text in 2-3 sentences"
inputs      = { text = "Text" }
output      = "Summary"
prompt      = """
Summarize the following text in 2-3 concise sentences. Focus on the key points.

@text
"""
```

This file works as a standalone bundle — no manifest, no package, no dependencies. To run it:

```bash
mthds run summarizer.mthds
```

### Next Steps

- Add more concepts and pipes to your bundle. See [The Language](01-the-language.md) for the full set of pipe types and concept features.
- When you are ready to distribute your methods, see [Create a Package](#page-create-a-package).

---

## Page: Create a Package

This guide walks you through turning a standalone bundle into a distributable MTHDS package.

### What You Start With

You have one or more `.mthds` files that work on their own:

```
my-methods/
├── summarizer.mthds
└── classifier.mthds
```

### Step 1: Initialize the Manifest

Run `mthds pkg init` from the package directory:

```bash
cd my-methods
mthds pkg init
```

This scans all `.mthds` files, extracts domains and pipe names, and generates a `METHODS.toml` skeleton:

```toml
[package]
address     = "example.com/yourorg/my_methods"
version     = "0.1.0"
description = "Package generated from 2 .mthds file(s)"

[exports.summarization]
pipes = ["summarize"]

[exports.classification]
pipes = ["classify_document"]
```

### Step 2: Set the Package Address

Edit the `address` field to your actual repository location:

```toml
[package]
address     = "github.com/yourorg/my-methods"
version     = "0.1.0"
description = "Text summarization and document classification methods"
```

The address must start with a hostname (containing at least one dot), followed by a path. It doubles as the fetch location when other packages depend on yours.

### Step 3: Configure Exports

Review the `[exports]` section. The generated manifest exports all pipes found during scanning. Narrow it down to your public API:

```toml
[exports.summarization]
pipes = ["summarize"]

[exports.classification]
pipes = ["classify_document"]
```

Pipes not listed in `[exports]` are private — they are implementation details invisible to consumers. Pipes declared as `main_pipe` in a bundle header are auto-exported regardless of whether they appear here.

Concepts are always public — they do not need to be listed.

### Step 4: Add Metadata

Add optional but recommended fields:

```toml
[package]
address       = "github.com/yourorg/my-methods"
version       = "0.1.0"
description   = "Text summarization and document classification methods"
authors       = ["Your Name <you@example.com>"]
license       = "MIT"
mthds_version = ">=1.0.0"
```

### Step 5: Validate

Verify your package is well-formed:

```bash
mthds validate --all
```

This validates all pipes across all bundles in the package, checking concept references, pipe references, and visibility rules.

### The Result

Your package directory now looks like:

```
my-methods/
├── METHODS.toml
├── summarizer.mthds
└── classifier.mthds
```

You have a distributable package with a globally unique address, versioned identity, and controlled exports. Other packages can now depend on it.

### See Also

- [The Manifest](02-the-package-system.md#page-the-manifest) — full reference for `METHODS.toml` fields.
- [Exports & Visibility](02-the-package-system.md#page-exports--visibility) — how visibility rules work.
- [Use Dependencies](#page-use-dependencies) — how to depend on other packages.

---

## Page: Use Dependencies

This guide shows how to add dependencies on other MTHDS packages and use their concepts and pipes in your bundles.

### Step 1: Add a Dependency

Use `mthds pkg add` to add a dependency to your `METHODS.toml`:

```bash
mthds pkg add github.com/mthds/document-processing --version "^1.0.0"
```

This adds an entry to the `[dependencies]` section:

```toml
[dependencies]
document_processing = { address = "github.com/mthds/document-processing", version = "^1.0.0" }
```

The alias (`document_processing`) is auto-derived from the last segment of the address. To choose a shorter alias:

```bash
mthds pkg add github.com/mthds/document-processing --alias docproc --version "^1.0.0"
```

```toml
[dependencies]
docproc = { address = "github.com/mthds/document-processing", version = "^1.0.0" }
```

### Step 2: Resolve and Lock

Generate the lock file to pin exact versions:

```bash
mthds pkg lock
```

Then install the dependencies into the local cache:

```bash
mthds pkg install
```

### Step 3: Use Cross-Package References

In your `.mthds` files, reference the dependency's concepts and pipes using the `->` syntax:

```toml
domain = "analysis"

[pipe.analyze_document]
type        = "PipeSequence"
description = "Extract pages from a document and analyze them"
inputs      = { document = "Document" }
output      = "AnalysisResult"
steps = [
    { pipe = "docproc->extraction.extract_text", result = "pages" },
    { pipe = "process_pages", result = "analysis" },
]
```

The reference `docproc->extraction.extract_text` reads as: "from the package aliased as `docproc`, get the pipe `extract_text` in the `extraction` domain."

Cross-package concept references work the same way:

```toml
[concept.DetailedPage]
description = "An enriched page with additional metadata"
refines     = "docproc->extraction.ExtractedPage"
```

### Step 4: Validate

```bash
mthds validate --all
```

Validation checks that:

- The alias `docproc` exists in `[dependencies]`.
- The pipe `extract_text` exists in the `extraction` domain of the resolved dependency.
- The pipe is exported by the dependency (listed in its `[exports]` or declared as `main_pipe`).

### Using Local Path Dependencies

During development, you can point a dependency to a local directory instead of fetching it remotely:

```bash
mthds pkg add github.com/mthds/document-processing --path ../document-processing --version "^1.0.0"
```

```toml
[dependencies]
docproc = { address = "github.com/mthds/document-processing", version = "^1.0.0", path = "../document-processing" }
```

Local path dependencies are resolved from the filesystem at load time. They are not resolved transitively and are excluded from the lock file.

### Updating Dependencies

To update all dependencies to their latest compatible versions:

```bash
mthds pkg update
```

This performs a fresh resolution, writes an updated `methods.lock`, and shows a diff of what changed.

### See Also

- [Dependencies](02-the-package-system.md#page-dependencies) — full reference for dependency fields and version constraints.
- [Cross-Package References](02-the-package-system.md#page-cross-package-references) — the `->` syntax explained.
- [Version Resolution](02-the-package-system.md#page-version-resolution) — how Minimum Version Selection works.

---

## Page: Publish a Package

This guide walks you through preparing a package for distribution and creating a version tag.

### Prerequisites

Before publishing:

- Your package has a `METHODS.toml` with a valid `address` and `version`.
- All `.mthds` files parse without error.
- If you have remote dependencies, a `methods.lock` file exists and is up to date.
- Your git working directory is clean (all changes committed).

### Step 1: Validate for Publishing

Run the publish validation:

```bash
mthds pkg publish
```

This runs 15 checks across seven categories (manifest, bundles, exports, visibility, dependencies, lock file, git). The output shows errors and warnings:

```
┌──────────────────────────────────────────────────────────┐
│ Errors                                                    │
├──────────┬─────────────────────────────┬─────────────────┤
│ Category │ Message                     │ Suggestion      │
├──────────┼─────────────────────────────┼─────────────────┤
│ export   │ Exported pipe 'old_pipe'    │ Remove from     │
│          │ in domain 'legal' not found │ [exports.legal] │
│          │ in bundles                  │ or add it       │
└──────────┴─────────────────────────────┴─────────────────┘

1 error(s), 0 warning(s)
Package is NOT ready for distribution.
```

Fix all errors before proceeding. Warnings are advisory — they flag things like missing `authors` or `license` fields, which are recommended but not required.

### Step 2: Fix Issues

Common issues and how to fix them:

| Issue | Fix |
|-------|-----|
| Exported pipe not found in bundles | Remove the pipe from `[exports]` or add it to a `.mthds` file. |
| Lock file missing | Run `mthds pkg lock`. |
| Git working directory has uncommitted changes | Commit or stash changes. |
| Git tag already exists | Bump the `version` in `METHODS.toml`. |
| Wildcard version on dependency | Pin to a specific constraint (e.g., `^1.0.0`). |

### Step 3: Create a Version Tag

Once all checks pass, create a git tag:

```bash
mthds pkg publish --tag
```

This validates the package and, on success, creates a local git tag `v{version}` (e.g., `v0.3.0`).

### Step 4: Push

Push your code and the tag to make the package available:

```bash
git push origin main
git push origin v0.3.0
```

Other packages can now depend on yours using the address and version:

```toml
[dependencies]
legal = { address = "github.com/yourorg/legal-tools", version = "^0.3.0" }
```

### Version Bumping

When you make changes and want to publish a new version:

1. Update the `version` field in `METHODS.toml`.
2. Update `methods.lock` if dependencies changed (`mthds pkg lock`).
3. Commit all changes.
4. Run `mthds pkg publish --tag`.
5. Push code and tag.

Follow [Semantic Versioning](https://semver.org/): increment the major version for breaking changes, minor for new features, and patch for fixes.

### See Also

- [The Manifest](02-the-package-system.md#page-the-manifest) — `address` and `version` field requirements.
- [The Lock File](02-the-package-system.md#page-the-lock-file) — what gets locked and when.
- [Distribution](02-the-package-system.md#page-distribution) — how packages are fetched by consumers.

---

## Page: Discover Methods

This guide shows how to search for and discover existing MTHDS methods — by text, by domain, or by typed signature.

### Searching by Text

The simplest search is a text query:

```bash
mthds pkg search "contract"
```

This searches concepts and pipes for the term "contract" (case-insensitive substring match) and displays matching results in tables showing package, name, domain, description, and export status.

To narrow results:

```bash
# Show only concepts
mthds pkg search "contract" --concept

# Show only pipes
mthds pkg search "contract" --pipe

# Filter by domain
mthds pkg search "extract" --domain legal.contracts
```

### Searching by Type ("I Have X, I Need Y")

MTHDS enables something that text-based discovery cannot: **type-compatible search**. Instead of searching by name, you search by what data types a pipe accepts or produces.

#### "What can I do with X?"

Find all pipes that accept a given concept:

```bash
mthds pkg search --accepts Document
```

This returns every pipe whose input type is `Document` or a concept that `Document` refines. Because the search understands the concept refinement hierarchy, it finds pipes you might not discover through text search alone.

#### "What produces Y?"

Find all pipes that produce a given concept:

```bash
mthds pkg search --produces NonCompeteClause
```

#### Combining Accepts and Produces

Find pipes that bridge two types:

```bash
mthds pkg search --accepts Document --produces NonCompeteClause
```

### Exploring the Know-How Graph

For more advanced queries — multi-step chains, compatibility checks, auto-composition — use the `mthds pkg graph` command.

#### Finding Chains

When no single pipe transforms X into Y, the graph can find multi-step chains:

```bash
mthds pkg graph \
  --from "__native__::native.Document" \
  --to "github.com/acme/legal-tools::legal.contracts.NonCompeteClause"
```

This might discover a chain like:

```
1. extract_pages -> analyze_content -> extract_clause
```

With `--compose`, it generates a ready-to-use MTHDS snippet:

```bash
mthds pkg graph \
  --from "__native__::native.Document" \
  --to "github.com/acme/legal-tools::legal.contracts.NonCompeteClause" \
  --compose
```

#### Checking Compatibility

Before wiring two pipes together, verify they are type-compatible:

```bash
mthds pkg graph --check "pkg_a::extract_pages,pkg_a::analyze_content"
```

This reports whether the output of the first pipe matches any input of the second.

### Searching Cached Packages

By default, search and graph commands operate on the current project. To search across all cached packages (everything you have installed):

```bash
mthds pkg search "scoring" --cache
mthds pkg graph --from "__native__::native.Text" --cache
```

### Inspecting a Package

To see the full contents of a specific package — its domains, concepts, and pipe signatures:

```bash
mthds pkg inspect github.com/acme/legal-tools
```

This displays detailed tables for every domain, concept (including structure fields and refinement), and pipe (including inputs, outputs, and export status).

### Building the Index

Before searching, you may want to build or refresh the package index:

```bash
# Index the current project
mthds pkg index

# Index all cached packages
mthds pkg index --cache
```

The index is built automatically when you run search or graph commands, but building it explicitly lets you verify what packages are available.

### See Also

- [The Know-How Graph](02-the-package-system.md#page-the-know-how-graph) — how typed signatures enable semantic discovery.
- [Cross-Package References](02-the-package-system.md#page-cross-package-references) — how to use discovered pipes in your bundles.
- [Use Dependencies](#page-use-dependencies) — how to add a discovered package as a dependency.
