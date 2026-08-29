# Run Commands

Execute a pipeline with optional inputs and outputs.

The `run` command has three subcommands depending on where your pipeline is defined:

```bash
pipelex run pipe ...      # Run a pipe from your project's library
pipelex run bundle ...    # Run a pipeline from a bundle file or directory
pipelex run method ...    # Run an installed method package
```

## Run Pipe

```bash
pipelex run pipe <PIPE_CODE> [OPTIONS]
```

Runs a pipe by code from your project's pipe library.

**Arguments:**

- `PIPE_CODE` - The pipe code to run

**Options:**

- `--inputs`, `-i` - Path to a JSON or TOML file containing inputs (discriminated by file extension — see [Input File Formats](#input-file-formats))
- `--output-dir`, `-o` - Directory to save outputs (defaults to `results/`)
- `--save-main-stuff` / `--no-save-main-stuff` - Whether to save the main output to a file
- `--save-working-memory` / `--no-save-working-memory` - Whether to save the full working memory
- `--working-memory-path` - Custom path for the working memory output file
- `--save-csv` - Write the main stuff to this literal CSV path (**not** under `--output-dir`; absolute or `~`/relative paths all work). Requires a flat list output. See [CSV Input & Output](../../building-methods/pipes/csv-input-and-output.md)
- `--no-pretty-print` - Skip pretty printing the main output
- `--graph` / `--no-graph` - Enable/disable execution graph visualization
- `--graph-full-data` / `--graph-no-data` - Include full data in the graph visualization
- `--dry-run` - Dry-run the pipeline without calling AI providers; no inference credentials are needed
- `--mock-inputs` - Use mock inputs for the pipeline (requires `--dry-run`)
- `--library-dir`, `-L` - Directory to search for pipe definitions. Can be specified multiple times.

**Examples:**

```bash
# Run a pipe by code
pipelex run pipe hello_world

# Run with inputs from JSON file
pipelex run pipe write_weekly_report --inputs weekly_report_data.json

# Run with custom output directory
pipelex run pipe hello_world --output-dir my_output/

# Run without saving or pretty printing
pipelex run pipe my_pipe --no-save-main-stuff --no-pretty-print

# Write a flat list output to CSV (literal path, not under --output-dir)
pipelex run pipe summarize_people --inputs people.json --save-csv summaries.csv

# Dry-run (no AI calls, no credentials needed)
pipelex run pipe my_pipe --dry-run

# Run with custom library directories
pipelex run pipe my_pipe -L ./pipelines -L ./shared_pipes
```

## Run Bundle

```bash
pipelex run bundle <PATH> [OPTIONS]
```

Runs a pipeline from a bundle file (`.mthds`) or a pipeline directory. When a directory is given, the bundle file is auto-detected inside it — and so is an inputs file (`inputs.json` or `inputs.toml`) when `--inputs` is not passed (see [Input File Formats](#input-file-formats)).

**Arguments:**

- `PATH` - Path to a `.mthds` bundle file or a directory containing one

**Options:**

- `--pipe PIPE_CODE` - Run a specific pipe from the bundle (defaults to the bundle's main pipe)
- `--inputs`, `-i` - Path to a JSON or TOML file containing inputs (discriminated by file extension — see [Input File Formats](#input-file-formats))
- `--output-dir`, `-o` - Directory to save outputs
- `--save-main-stuff` / `--no-save-main-stuff` - Whether to save the main output
- `--save-working-memory` / `--no-save-working-memory` - Whether to save the full working memory
- `--working-memory-path` - Custom path for the working memory output file
- `--save-csv` - Write the main stuff to this literal CSV path (**not** under `--output-dir`; absolute or `~`/relative paths all work). Requires a flat list output. See [CSV Input & Output](../../building-methods/pipes/csv-input-and-output.md)
- `--no-pretty-print` - Skip pretty printing the main output
- `--graph` / `--no-graph` - Enable/disable execution graph visualization
- `--graph-full-data` / `--graph-no-data` - Include full data in the graph visualization
- `--dry-run` - Dry-run the pipeline without calling AI providers; no inference credentials are needed
- `--mock-inputs` - Use mock inputs for the pipeline (requires `--dry-run`)
- `--library-dir`, `-L` - Directory to search for additional pipe definitions. Can be specified multiple times.

**Examples:**

```bash
# Run a bundle file (uses its main_pipe)
pipelex run bundle my_bundle.mthds

# Run a pipeline directory
pipelex run bundle pipelines/invoice_processor/

# Run a specific pipe from a bundle
pipelex run bundle my_bundle.mthds --pipe extract_invoice

# Run with inputs
pipelex run bundle my_bundle.mthds --inputs invoice_data.json

# Run with execution graph
pipelex run bundle my_bundle.mthds --graph
```

## Run Method

```bash
pipelex run method <NAME> [OPTIONS]
```

Runs a pipeline from an installed method package.

**Arguments:**

- `NAME` - The name of the installed method to run, a method address (`github.com/owner/repo[/name][@tag]`), or a GitHub URL — see [Run a Method by Address](run-by-address.md)

**Options:**

- `--pipe PIPE_CODE` - Run a specific pipe within the method (defaults to the method's main pipe)
- `--inputs`, `-i` - Path to a JSON or TOML file containing inputs (discriminated by file extension — see [Input File Formats](#input-file-formats))
- `--output-dir`, `-o` - Directory to save outputs (defaults to `results/` inside the method's directory; for a method fetched by address, `results/` under your current working directory — see [Run a Method by Address](run-by-address.md))
- `--save-main-stuff` / `--no-save-main-stuff` - Whether to save the main output
- `--save-working-memory` / `--no-save-working-memory` - Whether to save the full working memory
- `--working-memory-path` - Custom path for the working memory output file
- `--save-csv` - Write the main stuff to this literal CSV path (**not** under `--output-dir`; absolute or `~`/relative paths all work). Requires a flat list output. See [CSV Input & Output](../../building-methods/pipes/csv-input-and-output.md)
- `--no-pretty-print` - Skip pretty printing the main output
- `--graph` / `--no-graph` - Enable/disable execution graph visualization
- `--graph-full-data` / `--graph-no-data` - Include full data in the graph visualization
- `--dry-run` - Dry-run the pipeline without calling AI providers; no inference credentials are needed
- `--mock-inputs` - Use mock inputs for the pipeline (requires `--dry-run`)
- `--library-dir`, `-L` - Directory to search for additional pipe definitions. Can be specified multiple times.

**Examples:**

```bash
# Run an installed method
pipelex run method invoice_extractor

# Run a specific pipe within a method
pipelex run method invoice_extractor --pipe extract_amounts

# Run with inputs
pipelex run method invoice_extractor --inputs invoice_data.json

# Run a method fetched by address from a public GitHub repository, pinned at a tag
pipelex run method github.com/Pipelex/methods/documents@v0.1.0 --pipe extract_document_text
```

## Input File Formats

An inputs file is a dictionary whose keys are input variable names, and each value is interpreted **against the pipe's declared signature** — so you provide the values directly (a string, a number, an object) and Pipelex types them as the declared concept. See [Providing Inputs](../../building-methods/pipes/provide-inputs.md) for the full model, including the explicit `{concept, content}` escape hatch. Pipelex accepts **both JSON and TOML**, discriminated by the file extension:

- A `.toml` suffix is parsed as TOML.
- Every other value — `.json`, no extension, anything else — is parsed as JSON.

There is no content sniffing: the extension alone decides. Inline JSON passed to `--inputs` (a value starting with `{`) stays JSON-only.

An input declared optional (`?`) on the entry pipe may be omitted — the run records a `not_provided` absence for it instead of failing (see [Understanding Optionality](../../building-methods/pipes/understanding-optionality.md)).

Both formats produce the same input dictionary for the value types they share, so the [PipelineInputs shapes](../../building-methods/pipes/provide-inputs.md) apply to both — with one structural exception: JSON `null` has no TOML equivalent (TOML has no null type).

### JSON

Provide each value directly — a string, a number, an object — and it is typed as the input's declared concept:

```json
{
  "instructions": "simple string value",
  "priority": 3,
  "client": { "name": "Acme Corp", "country": "France" }
}
```

To override or disambiguate a concept, wrap a value in the explicit `{concept, content}` envelope (`{"concept": "domain_code.ConceptName", "content": {...}}`) — see [Providing Inputs](../../building-methods/pipes/provide-inputs.md#the-explicit-format-escape-hatch).

### TOML

The same inputs in TOML. TOML's multi-line strings (`"""..."""`) make text-heavy inputs far more pleasant to author than escaped JSON:

```toml
instructions = """
Focus on payment terms.
Flag anything that looks unusual.
"""

priority = 3

[client]
name = "Acme Corp"
country = "France"
```

!!! tip "TOML temporal literals are native `Date` / `Time` inputs"
    A top-level TOML date or datetime literal (e.g. `hearing = 2026-09-01` or `departure = 2026-07-07T15:40:00+02:00`) maps directly to the native [`Date`](../../building-methods/concepts/native-concepts.md) concept — the offset is kept when stated. A bare *time-of-day* literal (`opening = 09:00:00`) maps to the native `Time` concept; it never silently becomes a `Date` (a time alone has no date to attach to, so shaping a `Time` into a `Date` slot fails the compatibility check).

### Auto-detection and ambiguity

`run bundle <dir>` auto-detects a default inputs file inside the directory when `--inputs` is omitted: it looks for `inputs.json`, then `inputs.toml`. If **both** exist, the run fails with an ambiguity error asking you to pass `--inputs` explicitly — passing `--inputs` always bypasses auto-detection.

## Output Format

The output JSON contains the complete working memory after pipeline execution, including all intermediate results and the final output.

### Absent main output

A run whose main output resolves as a recorded absence (an optional `?` output that produced nothing — e.g. a `PipeCondition` `continue` outcome, or a skipped producer) is a **successful** run. The CLI prints the absence with its reason, and `--save-main-stuff` writes an explicit absence artifact instead of a value dump: `main_stuff.json` is `{"absent": true, ...}` with the absence record, and `main_stuff.md` is a human-readable summary including the provenance chain (no HTML render or interactive viewer is produced — there is nothing to view). `--save-csv` fails with an explicit error and a non-zero exit code, the same way it does for any main output that is not a flat list — there is no tabular value to save.

## Related Documentation

- [Executing Pipelines](../../building-methods/pipes/executing-pipelines.md)
- [Providing Inputs to Pipelines](../../building-methods/pipes/provide-inputs.md)
- [CSV Input & Output](../../building-methods/pipes/csv-input-and-output.md)
- [Design and Run Pipelines](../../building-methods/pipes/index.md)
