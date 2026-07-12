---
description: "Run Pipelex pipelines from the CLI, Python API, or Pipelex Client. Execute .mthds bundles and retrieve structured outputs programmatically."
---

# Executing Pipelines

Once your pipes are defined in `.mthds` files, you can execute them in multiple ways.

## The Simplest Approach: Run a Bundle File

The easiest way to execute a pipeline is to point directly to your `.mthds` bundle file. No library configuration needed.

### Using the CLI

```bash
# Run the bundle's main_pipe
pipelex run bundle path/to/my_bundle.mthds

# Run a specific pipe from the bundle
pipelex run bundle path/to/my_bundle.mthds --pipe my_specific_pipe

# Run with inputs
pipelex run bundle path/to/my_bundle.mthds --inputs inputs.json
```

!!! tip "Preparing Inputs"
    You can generate an input template with `pipelex build inputs bundle path/to/my_bundle.mthds`, which writes an `inputs.json` next to the bundle (in the bundle's own directory) with the required input structure — the light, signature-driven values ready to fill in. See [Build Inputs](../../tools/cli/build/inputs.md).

### Using Python

```python
from pipelex.pipelex import Pipelex
from pipelex.pipeline.runner import PipelexMTHDSProtocol

Pipelex.make()

# Run the bundle's main_pipe
runner = PipelexMTHDSProtocol(
    bundle_uris=["path/to/my_bundle.mthds"],
)
response = await runner.execute(
    # Provide values directly — each is interpreted against the pipe's declared input signature.
    inputs={
        "my_input": "Hello world",
    },
)
pipe_output = response.pipe_output

# Or run a specific pipe from the bundle
runner = PipelexMTHDSProtocol(
    bundle_uris=["path/to/my_bundle.mthds"],
)
response = await runner.execute(
    pipe_code="my_specific_pipe",
    inputs={...},
)
pipe_output = response.pipe_output
```

!!! info "How `main_pipe` Works"
    When you run a bundle without specifying a `pipe_code`, Pipelex executes the bundle's `main_pipe` (declared at the top of the `.mthds` file). If no `main_pipe` is defined and no `pipe_code` is provided, an error is raised.

    If you provide both `bundle_uris` and `pipe_code`, the explicit `pipe_code` takes priority over `main_pipe`.

See the [Pipelex Bundle Specification](../pipelex-bundle-specification.md) for more about the `main_pipe` property.

---

## Advanced: Using Library Directories

For larger projects with multiple bundles spread across directories, you can configure **library directories** to load all your pipes at once and reference them by code.

### Understanding Libraries

When executing pipelines programmatically, Pipelex can load pipe **libraries** - collections of pipes loaded from one or more directories. This is useful when:

- You have multiple bundles across different directories
- You want to reference pipes by code without specifying the bundle path each time
- You're building an application that needs access to many pipes

#### Library Parameters

When using `PipelexMTHDSProtocol`, you can control library behavior with these parameters:

- **`library_id`**: A unique identifier for the library instance. If not specified, it defaults to the `pipeline_run_id` (a unique ID generated for each pipeline execution).

- **`library_dirs`**: A list of directory paths to load pipe definitions from. **These directories must contain both your `.mthds` files AND any Python files defining `StructuredContent` classes** (e.g., `*_struct.py` files). If not specified, Pipelex falls back to the default library directories passed to `Pipelex.make(library_dirs=...)`, then to the `PIPELEXPATH` environment variable; if none of these are set, no library directories are loaded.

- **`mthds_contents`**: When provided to `PipelexMTHDSProtocol.execute()`, Pipelex parses these strings and loads them into the library in addition to any resolved library directories (bundles already loaded from directories are deduplicated). To run with only this content, disable directory loading explicitly (e.g. `library_dirs=[]`). This is useful for dynamic pipeline execution without file-based definitions.

!!! info "Python Structure Classes"
    If your concepts use Python `StructuredContent` classes instead of inline structures, those Python files must be in the directories specified by `library_dirs`. Pipelex auto-discovers and registers these classes during library loading. Learn more about [Python StructuredContent Classes](../concepts/python-classes.md).

!!! info "Learn More About Libraries"
    For a comprehensive understanding of libraries, including their structure, uniqueness rules, lifecycle, and best practices, see [Libraries](../libraries.md).

!!! tip "Library Directory Configuration"
    For complete configuration options including the `PIPELEXPATH` environment variable, CLI options, and priority resolution, see [Configuring Library Directories](../../configuration/config-technical/library-config.md#configuring-library-directories).

### Running Pipes by Code

This approach loads pipe definitions from directories and executes a specific pipe by its code.

**Basic usage** (default library directories set at initialization):

```python
from pipelex.pipelex import Pipelex
from pipelex.pipeline.runner import PipelexMTHDSProtocol

# First, initialize Pipelex with default library directories
# (used by every run unless overridden per call)
Pipelex.make(library_dirs=["./pipelines"])

# Execute the pipeline and wait for the result
runner = PipelexMTHDSProtocol()
response = await runner.execute(
    pipe_code="description_to_tagline",
    inputs={
        "description": "EcoClean Pro is a revolutionary biodegradable cleaning solution that removes 99.9% of germs while being completely safe for children and pets. Made from plant-based ingredients.",
    },
)
pipe_output = response.pipe_output
```

**Loading from specific directories**:

```python
# Load pipes from specific directories
runner = PipelexMTHDSProtocol(
    library_dirs=["./pipelines", "./shared_pipes"],
)
response = await runner.execute(
    pipe_code="description_to_tagline",
    inputs={
        "description": "...",
    },
)
pipe_output = response.pipe_output
```

**Using a custom library ID**:

```python
# Use a custom library ID for managing multiple library instances
runner = PipelexMTHDSProtocol(
    library_id="my_marketing_library",
    library_dirs=["./marketing_pipes"],
)
response = await runner.execute(
    pipe_code="description_to_tagline",
    inputs={
        "description": "...",
    },
)
pipe_output = response.pipe_output
```

!!! tip "Listing available pipes"
    Use `pipelex show pipe --all` to list the pipes available in your project.

### Using MTHDS Content Directly

You can directly pass MTHDS content as a string to `PipelexMTHDSProtocol.execute()`, useful for dynamic pipeline execution without file-based definitions.

```python
from pipelex.pipelex import Pipelex
from pipelex.pipeline.runner import PipelexMTHDSProtocol

my_pipe_content = '''
domain = "marketing"
description = "Marketing content generation domain"
main_pipe = "generate_tagline"

[concept]
ProductDescription = "A description of a product's features and benefits"
Tagline = "A catchy marketing tagline"

[pipe.generate_tagline]
type = "PipeLLM"
description = "Generate a catchy tagline for a product"
inputs = { description = "ProductDescription" }
output = "Tagline"
prompt = """
Product Description: $description

Generate a catchy tagline based on the above description. The tagline should be memorable, concise, and highlight the key benefit.
"""
'''

Pipelex.make()

runner = PipelexMTHDSProtocol()
response = await runner.execute(
    mthds_contents=[my_pipe_content],
    inputs={
        "description": "EcoClean Pro is a revolutionary biodegradable cleaning solution that removes 99.9% of germs while being completely safe for children and pets. Made from plant-based ingredients.",
    },
)
pipe_output = response.pipe_output
```

!!! note "Pipe Code Resolution"
    When using `mthds_contents`:

    - If the content has a `main_pipe` property and you don't provide `pipe_code`, the `main_pipe` is executed
    - If you provide `pipe_code`, it overrides `main_pipe`
    - If there's no `main_pipe` and no `pipe_code`, an error is raised

---

## Using the Pipelex API

Pipelex has a REST API for executing pipelines. See more about it [here](https://pipelex.github.io/pipelex-api/).

---

## Background Execution

<!-- start exists on PipelexMTHDSProtocol as a protocol stub (raises NotImplementedError).
     The public entry point is execute(). Keep this note so reviewers don't flag the stub as contradictory. -->
The public Python entry point is `PipelexMTHDSProtocol.execute()`. The older standalone `start` function is no longer a documented entry point.

---

## Run Modes & Backends

Every execution method above accepts a run mode (live or dry run) and a backend (in-process or Temporal). See [Run Modes & Backends](run-modes-and-backends.md) for the full matrix and when to use each combination.
