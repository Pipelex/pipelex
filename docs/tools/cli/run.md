---
description: "Execute pipelines from your project library, .mthds bundle files, or installed method packages with optional inputs and outputs."
---

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
- `--hosted` / `--local` - Run on the hosted Pipelex API or on this machine. Defaults to `[run] execution` (see [Running on the Hosted API](#running-on-the-hosted-api)), else local
- `--base-url` - The origin a hosted run calls, `scheme://host[:port]`. Overrides `PIPELEX_BASE_URL`, which overrides `https://api.pipelex.com`

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

# Run on the hosted Pipelex API, sending the library
pipelex run pipe my_pipe -L ./pipelines --hosted --inputs data.json
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
- `--hosted` / `--local` - Run on the hosted Pipelex API or on this machine. Defaults to `[run] execution` (see [Running on the Hosted API](#running-on-the-hosted-api)), else local
- `--base-url` - The origin a hosted run calls, `scheme://host[:port]`. Overrides `PIPELEX_BASE_URL`, which overrides `https://api.pipelex.com`

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

# Run on the hosted Pipelex API
pipelex run bundle my_bundle.mthds --hosted
```

## Run Method

```bash
pipelex run method <NAME> [OPTIONS]
```

Runs a pipeline from an installed method package.

**Arguments:**

- `NAME` - The name of the installed method to run, a method address (`github.com/owner/repo[/name][@tag]`), or a GitHub URL — see [Run a Method by Address](run-by-address.md). On a hosted run, also a stored method's catalog id (`mt_…`)

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
- `--hosted` / `--local` - Run on the hosted Pipelex API or on this machine. Defaults to `[run] execution` (see [Running on the Hosted API](#running-on-the-hosted-api)), else local
- `--base-url` - The origin a hosted run calls, `scheme://host[:port]`. Overrides `PIPELEX_BASE_URL`, which overrides `https://api.pipelex.com`

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

# Run a published method on the hosted Pipelex API, which resolves the address itself
pipelex run method github.com/Pipelex/methods/text_stats@v0.1.7 --hosted --inputs '{"text": "Hello world."}'

# Run a method stored on the hosted platform, by its catalog id
pipelex run method mt_abc123 --hosted --inputs data.json
```

## Running on the Hosted API

A run executes on this machine by default, with the inference backends configured in `.pipelex/inference/` and your own provider keys. It can execute on the hosted Pipelex API instead, which needs only a Pipelex API key: no provider key and no inference configuration on this machine, since a hosted run boots nothing locally.

Where a run executes is decided in this order:

1. `--hosted` or `--local` on the command.
2. `[run] execution` in `.pipelex/pipelex.toml` (`"local"` or `"hosted"`; the project's file over the one in `~/.pipelex/`), see [Run Configuration](../../configuration/config-practical/run-config.md).
3. Local.

The key is read from `PIPELEX_API_KEY`, exported in your shell or saved in `~/.pipelex/.env` (or a `.env` in the working directory), which Pipelex loads at startup. The run goes to `--base-url` when given, else to `PIPELEX_BASE_URL`, else to `https://api.pipelex.com`. Either value must be an origin, `scheme://host[:port]` with `http` or `https` and no path such as `/v1`; anything else is refused before a request is sent, naming the setting it came from. A self-hosted Pipelex API server is reached the same way, by pointing the base URL at it.

**What a hosted run sends** is what a local run would load:

- `run bundle` sends the bundle, then every `.mthds` file of its library directories (the bundle's own directory for `run bundle <dir>`, then `-L`; for a bundle file with no `-L`, `PIPELEXPATH`), each once. Without `--pipe`, the bundle's `main_pipe` is read from the bundle here, as a local run reads it.
- `run pipe` sends every `.mthds` file of its library directories: the installed method exporting the pipe and `-L`, else `PIPELEXPATH`. With none of them, the run is refused and asks for `-L`.
- `run method` sends an installed or local method's files. A published address goes as a reference and a catalog id (`mt_…`) as an id, both resolved by the hosted API: nothing is fetched or read locally, `-L` is refused with them, and a relative `--inputs` path resolves against the working directory rather than the method's. A method installed under a name spelled like a catalog id, such as `mt_reports`, is that installed method, not an id.

**Local files in the inputs** are uploaded before the run. A path at a document or image input (compact, as `"invoice.pdf"`, or as the `url` of a document or image object, in a list or nested in a structure) is uploaded, and the run receives its storage URI instead. A relative path written in an inputs file resolves against that file's directory, as on a local run. A text that reads like a file name at any other input is left as text, and `http(s)://` URLs, whatever the case of the scheme, are passed through for the hosted API to fetch. When the inputs name a local file, the method's signature is read from the hosted API first, and a method that does not load is refused there, before any run starts, with validation errors that name the file each fault is in.

**What it saves** goes where a local run saves its outputs, in `<output-dir>/<pipe>_output_NN/`: `main_stuff.json` (and `main_stuff.md` when the main output is text), `working_memory.json`, and `graphspec.json` when the hosted API returned the run's graph, which [`pipelex graph render`](../../features/execution-graph.md) turns into a viewer. The run id is printed with the recap.

**What it refuses**: `--dry-run`, `--mock-inputs`, `--mock-usage`, `--orchestrator`, `--save-csv`, `--costs` / `--no-costs` and `--graph-full-data` / `--graph-no-data` steer this machine's runtime, which a hosted run never boots, so each is refused with a message pointing at `--local`. `--base-url` on a run that executes locally is refused too.

**When it fails**, the message gives the hosted API's reason and a next step: the one the server advised when it gave one, else one that follows the status (a refused key points at `PIPELEX_API_KEY`, an unknown method or route at the method's address and the base URL, a rate limit says to wait). A bundle the hosted API refuses lists its validation errors, and so does a run that started and failed on them. Once the hosted API has acknowledged the run, the failure also prints the run id: a run that failed, one that outlived the wait, one that completed without a main output, and one whose result could not be read, because the network or the hosted API failed while the run was being followed. That last one may still be running and is paid for, so look it up by its id on app.pipelex.com rather than running the command again. The exit code is `1`.

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

### The results directory

Each run that saves anything gets its own numbered directory under `--output-dir` (`results/<pipe_code>_output_01/`, then `_02`, and so on). With `--save-working-memory` it holds `working_memory.json`, with `--save-main-stuff` the `main_stuff.*` renders, and with `--graph` the graph outputs that `graphs_inclusion` enables: `graphspec.json`, the Mermaid code and viewer, and the ReactFlow viewer. When the main output is a Document or an Image, `--save-main-stuff` also copies the file itself into the directory under its own name, so a PDF that a [`PipeDocGen`](../../building-methods/pipes/pipe-operators/PipeDocGen.md) step produced lands as `invoice-INV-2026-0142.pdf` and opens with a double-click, and the run prints its path. It never replaces a file the run writes in the directory: a file whose name is taken, such as a document passed through from an earlier run as `main_stuff.json`, is saved as `main_stuff-1.json`. A dry run produces no file, so it copies nothing. In `working_memory.json` each stuff names its concept by ref — `{"stuff_code": …, "stuff_name": …, "concept": "<domain>.<Code>", "content": …}` — and carries no concept definition; see [Working Memory](../../building-methods/pipes/working-memory.md#in-memory-and-on-the-wire).

Beside `graphspec.json`, and gated by the same `graphspec_json` flag, the run writes the three files that describe the data the graph carries:

- `pipe_io_contracts.json` - each pipe's input and output contract, with the JSON Schema of its output
- `input_form.json` - each pipe's input-form descriptor
- `output_form.json` - each pipe's output-form descriptor

They are the same artifacts a validation report returns under those names, keyed by namespaced `pipe_ref` for every pipe in the library the run executed against, and they are what a graph viewer needs to show a data node's value rather than only the concept's structure: the VS Code extension reads them from the graphspec's own directory. A run with `--no-graph` writes none of them. See [Execution Graph Tracing](../../under-the-hood/execution-graph-tracing.md#outputs).

### Absent main output

A run whose main output resolves as a recorded absence (an optional `?` output that produced nothing — e.g. a `PipeCondition` `continue` outcome, or a skipped producer) is a **successful** run. The CLI prints the absence with its reason, and `--save-main-stuff` writes an explicit absence artifact instead of a value dump: `main_stuff.json` is `{"absent": true, ...}` with the absence record, and `main_stuff.md` is a human-readable summary including the provenance chain (no HTML render or interactive viewer is produced — there is nothing to view). `--save-csv` fails with an explicit error and a non-zero exit code, the same way it does for any main output that is not a flat list — there is no tabular value to save.

## An Invalid Bundle

A run loads its bundle before any pipe runs, and refuses an invalid one there, before spending anything. The refusal is reported the way [`pipelex validate`](validate.md) reports the same bundle: the grouped invalid-bundle panel, with one located item per refusal (its pipe, its field, its message and its suggested fix when it has one), and exit code `1`. A bundle file run on its own is loaded from its text, so the items of a refusal found while loading it name no file, and the panel names the bundle instead; a bundle that does not parse when `run bundle` looks for its `main_pipe` (no `--pipe`) names its file on the item too. That holds whether the parse or the load refuses the bundle, and for a refusal found while loading a library directory you pass with `-L` (or the bundle's own directory, for `run bundle <dir>`). When the items carry automatic fixes, the panel names the `pipelex fix bundle` command that applies them.

## Related Documentation

- [Executing Pipelines](../../building-methods/pipes/executing-pipelines.md)
- [Providing Inputs to Pipelines](../../building-methods/pipes/provide-inputs.md)
- [CSV Input & Output](../../building-methods/pipes/csv-input-and-output.md)
- [Design and Run Pipelines](../../building-methods/pipes/index.md)
