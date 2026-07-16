---
title: "Library Directories and Bundle Loading"
description: "Tell Pipelex where to find your `.mthds` bundle files. Point to a bundle directly or configure library directories for automatic discovery."
---

# Library Directories and Bundle Loading

When running pipelines, Pipelex needs to find your `.mthds` bundle files. There are two approaches:

1. **Point to the bundle file directly** - The simplest option. Just pass the path to your `.mthds` file. No configuration needed.

2. **Configure library directories** - For larger projects. Pipelex scans directories to discover all bundles, letting you reference pipes by code.

Most users should start with the first approach.

## The Simplest Way: Use the Bundle Path Directly

If you just want to run a pipe from a single `.mthds` file, **you don't need any library configuration**. Simply point to your bundle file:

```bash
# CLI: run the bundle's main_pipe
pipelex run bundle path/to/my_bundle.mthds

# CLI: run a specific pipe from the bundle
pipelex run bundle path/to/my_bundle.mthds --pipe my_pipe
```

```python
from pipelex.pipeline.runner import PipelexMTHDSProtocol

# Python: run the bundle's main_pipe
runner = PipelexMTHDSProtocol(
    bundle_uris=["path/to/my_bundle.mthds"],
)
response = await runner.execute(
    inputs={...},
)
pipe_output = response.pipe_output

# Python: run a specific pipe from the bundle
runner = PipelexMTHDSProtocol(
    bundle_uris=["path/to/my_bundle.mthds"],
)
response = await runner.execute(
    pipe_code="my_pipe",
    inputs={...},
)
pipe_output = response.pipe_output
```

This is the recommended approach for newcomers and simple projects. Pipelex reads the file directly - no discovery needed.

!!! tip "When to use library directories"
    The library directory configuration below is useful when you have **multiple bundles across different directories** and want to reference pipes by code without specifying the bundle path each time. For most use cases, pointing to the `.mthds` file directly is simpler.

---

## How Pipeline Discovery Works

When you initialize Pipelex with `Pipelex.make()`, the system:

1. **Scans your project directory** for all `.mthds` files
2. **Discovers Python structure classes** that inherit from `StructuredContent`
3. **Loads pipeline definitions** including domains, concepts, and pipes
4. **Registers custom functions** decorated with `@pipe_func()`

All of this happens automatically - no configuration needed.

## Configuring Library Directories

When executing pipelines, Pipelex needs to know where to find your `.mthds` files and Python structure classes. You can configure this using a **3-tier priority system** that gives you flexibility from global defaults to per-execution overrides.

### The 3-Tier Priority System

Pipelex resolves library directories using this priority order (highest to lowest):

| Priority | Source | When to Use |
|----------|--------|-------------|
| **1 (Highest)** | Per-call `library_dirs` parameter | Override for specific pipeline executions |
| **2** | Instance default via `Pipelex.make(library_dirs=...)` | Application-wide default |
| **3 (Fallback)** | `PIPELEXPATH` environment variable | System-wide or shell session default |

!!! info "Empty List is Valid"
    Passing an empty list `[]` to `library_dirs` is a valid explicit value that **disables** directory-based library loading. This is useful when using `mthds_contents` directly without needing files from the filesystem.

### Using the PIPELEXPATH Environment Variable

The `PIPELEXPATH` environment variable provides a system-wide default for library directories. It uses PATH-style syntax:

- **Unix/macOS**: Colon-separated paths (`:`)
- **Windows**: Semicolon-separated paths (`;`)

**Bash / Zsh (macOS/Linux):**

```bash
# Single directory
export PIPELEXPATH="/path/to/my/pipelines"

# Multiple directories (colon-separated)
export PIPELEXPATH="/path/to/shared_pipes:/path/to/project_pipes"

# Add to your ~/.bashrc or ~/.zshrc for persistence
echo 'export PIPELEXPATH="/path/to/my/pipelines"' >> ~/.bashrc
```

**PowerShell (Windows):**

```powershell
# Single directory
$env:PIPELEXPATH = "C:\path\to\my\pipelines"

# Multiple directories (semicolon-separated)
$env:PIPELEXPATH = "C:\shared_pipes;C:\project_pipes"
```

**In a `.env` file:**

```bash
# .env file in your project root
PIPELEXPATH=/path/to/shared_pipes:/path/to/project_pipes
```

### Using the CLI `--library-dir` Option

When running pipelines from the command line, use the `-L` or `--library-dir` option. This option can be specified multiple times to include multiple directories.

```bash
# Single directory
pipelex run pipe my_pipe -L /path/to/pipelines

# Multiple directories
pipelex run pipe my_pipe -L /path/to/shared_pipes -L /path/to/project_pipes

# Combined with other options
pipelex run bundle my_bundle.mthds --inputs data.json -L /path/to/pipelines

# Available on multiple commands
pipelex validate --all -L /path/to/pipelines/dir
pipelex show pipe --all -L /path/to/pipelines/dir
pipelex which my_pipe -L /path/to/pipelines/dir
```

!!! tip "CLI Option Overrides PIPELEXPATH"
    When you use `-L` on the command line, it takes precedence over any `PIPELEXPATH` environment variable that may be set.

### Setting Instance Defaults with `Pipelex.make()`

For Python applications, you can set a default library directory when initializing Pipelex. This default will be used for all subsequent `PipelexMTHDSProtocol.execute()` calls unless overridden.

```python
from pipelex.pipelex import Pipelex
from pipelex.pipeline.runner import PipelexMTHDSProtocol

# Set instance-level defaults at initialization
Pipelex.make(
    library_dirs=["/path/to/shared_pipes", "/path/to/project_pipes"]
)

# All PipelexMTHDSProtocol.execute() calls will use these directories by default
runner = PipelexMTHDSProtocol()
response = await runner.execute(
    pipe_code="my_pipe",
    inputs={"input": "value"},
)
pipe_output = response.pipe_output
```

### Per-Runner Override with `PipelexMTHDSProtocol`

For maximum flexibility, you can override library directories on each `PipelexMTHDSProtocol` instance:

```python
from pipelex.pipelex import Pipelex
from pipelex.pipeline.runner import PipelexMTHDSProtocol

# Initialize with default directories
Pipelex.make(
    library_dirs=["/path/to/default_pipes"]
)

# Use the default directories
runner1 = PipelexMTHDSProtocol()
response1 = await runner1.execute(
    pipe_code="default_pipe",
    inputs={"input": "value"},
)
pipe_output1 = response1.pipe_output

# Override for a specific execution
runner2 = PipelexMTHDSProtocol(
    library_dirs=["/path/to/special_pipes"],  # Overrides instance default
)
response2 = await runner2.execute(
    pipe_code="special_pipe",
    inputs={"input": "value"},
)
pipe_output2 = response2.pipe_output

# Disable directory loading (use only mthds_contents)
runner3 = PipelexMTHDSProtocol(
    library_dirs=[],  # Empty list disables directory-based loading
)
response3 = await runner3.execute(
    mthds_contents=[my_mthds_string],
    inputs={"input": "value"},
)
pipe_output3 = response3.pipe_output
```

### Priority Resolution Examples

**Example 1: Environment variable as fallback**

```bash
# Shell: Set PIPELEXPATH
export PIPELEXPATH="/shared/pipes"
```

```python
from pipelex.pipeline.runner import PipelexMTHDSProtocol

# Python: No library_dirs specified anywhere
Pipelex.make()  # No library_dirs

# Uses PIPELEXPATH: /shared/pipes
runner = PipelexMTHDSProtocol()
response = await runner.execute(pipe_code="my_pipe", inputs={...})
pipe_output = response.pipe_output
```

**Example 2: Instance default overrides PIPELEXPATH**

```bash
# Shell: PIPELEXPATH is set
export PIPELEXPATH="/shared/pipes"
```

```python
from pipelex.pipeline.runner import PipelexMTHDSProtocol

# Python: Instance default set
Pipelex.make(library_dirs=["/project/pipes"])

# Uses instance default: /project/pipes (PIPELEXPATH ignored)
runner = PipelexMTHDSProtocol()
response = await runner.execute(pipe_code="my_pipe", inputs={...})
pipe_output = response.pipe_output
```

**Example 3: Per-call override takes highest priority**

```python
from pipelex.pipeline.runner import PipelexMTHDSProtocol

Pipelex.make(library_dirs=["/default/pipes"])

# Uses per-runner value: /special/pipes
runner = PipelexMTHDSProtocol(
    library_dirs=["/special/pipes"],  # Highest priority
)
response = await runner.execute(
    pipe_code="my_pipe",
    inputs={...},
)
pipe_output = response.pipe_output
```

### Best Practices

1. **Use PIPELEXPATH for shared libraries**: Set it in your shell profile for directories that should always be available.

2. **Use `Pipelex.make(library_dirs=...)` for application defaults**: When building an application, set sensible defaults at initialization.

3. **Use per-call `library_dirs` for exceptions**: Override only when a specific execution needs different directories.

4. **Use empty list `[]` for isolated execution**: When you want to execute only from `mthds_contents` without loading any file-based definitions.

5. **Include structure class directories**: Remember that `library_dirs` must contain both `.mthds` files AND Python files defining `StructuredContent` classes.

## Excluded Directories

To improve performance and avoid loading unnecessary files, Pipelex automatically excludes common directories from discovery:

- `.venv`, `venv`, `env`, `virtualenv`, `.virtualenv` - Virtual environments
- `.git` - Git repository data
- `__pycache__` - Python bytecode cache
- `.pytest_cache` - Pytest cache
- `.mypy_cache` - Mypy type checker cache
- `.ruff_cache` - Ruff linter cache
- `node_modules` - Node.js dependencies
- `.env` - Environment files
- `results` - Common output directory

Files in these directories will not be scanned, even if they contain `.mthds` files or structure classes.

## Project Organization

**Golden rule:** Put `.mthds` files where they make sense in YOUR project. Pipelex finds them automatically.

### Common Patterns

**1. Topic-Based (Recommended for structured projects)**

Keep pipelines with related code:

```
your_project/
├── my_project/
│   ├── finance/
│   │   ├── models.py
│   │   ├── services.py
│   │   ├── invoices.mthds          # With finance code
│   │   └── invoices_struct.py
│   └── legal/
│       ├── models.py
│       ├── contracts.mthds         # With legal code
│       └── contracts_struct.py
├── .pipelex/
└── requirements.txt
```

**Benefits:**

- Related things stay together
- Easy to find pipeline for a specific module
- Natural code organization

**2. Centralized (For simpler discovery)**

Group all pipelines in one place:

```
your_project/
├── my_project/
│   ├── pipelines/          # All pipelines here
│   │   ├── finance.mthds
│   │   ├── finance_struct.py
│   │   ├── legal.mthds
│   │   └── legal_struct.py
│   └── core/
└── .pipelex/
```

**Benefits:**

- All pipelines in one location
- Simple structure for small projects

## Alternative Structures

Pipelex supports flexible organization. Here are other valid approaches:

### Feature-Based Organization

```
your_project/
├── my_project/
│   ├── features/
│   │   ├── document_processing/
│   │   │   ├── extract.mthds
│   │   │   └── extract_struct.py
│   │   └── image_generation/
│   │       ├── generate.mthds
│   │       └── generate_struct.py
│   └── main.py
└── .pipelex/
```

### Domain-Driven Organization

```
your_project/
├── my_project/
│   ├── finance/
│   │   ├── pipelines/
│   │   │   └── invoices.mthds
│   │   └── invoice_struct.py
│   ├── legal/
│   │   ├── pipelines/
│   │   │   └── contracts.mthds
│   │   └── contract_struct.py
│   └── main.py
└── .pipelex/
```

### Flat Organization (Small Projects)

```
your_project/
├── my_project/
│   ├── invoice_processing.mthds
│   ├── invoice_struct.py
│   └── main.py
└── .pipelex/
```

## Loading Process

Pipelex loads your pipelines in a specific order to ensure dependencies are resolved correctly:

### 1. Domain Loading

- Loads domain definitions from all `.mthds` files
- Each domain must be defined exactly once
- Supports system prompts and structure templates per domain

### 2. Concept Loading

- Loads native concepts (Text, Image, Document, etc.)
- Loads custom concepts from `.mthds` files
- Validates concept definitions and relationships
- Links concepts to Python structure classes by name

### 3. Structure Class Registration

- Discovers all classes inheriting from `StructuredContent`
- Registers them in the class registry
- Makes them available for structured output generation

### 4. Pipe Loading

- Loads pipe definitions from `.mthds` files
- Validates pipe configurations
- Links pipes with their respective domains
- Resolves input/output concept references

### 5. Function Registration

- Discovers functions decorated with `@pipe_func()`
- Registers them in the function registry
- Makes them available for `PipeFunc` operators

## Custom Function Registration

For custom functions used in `PipeFunc` operators, add the `@pipe_func()` decorator:

```python
from pipelex.system.registries.func_registry import pipe_func
from pipelex.core.memory.working_memory import WorkingMemory
from pipelex.core.stuffs.text_content import TextContent

@pipe_func()
async def my_custom_function(working_memory: WorkingMemory) -> TextContent:
    """
    This function is automatically discovered and registered.
    """
    input_data = working_memory.get_stuff("input_name")
    # Process data
    return TextContent(text=f"Processed: {input_data.content.text}")

# Optional: specify a custom name
@pipe_func(name="custom_processor")
async def another_function(working_memory: WorkingMemory) -> TextContent:
    # Implementation
    pass
```

## Validation

After making changes to your pipelines, validate them:

```bash
# Validate all pipelines
pipelex validate --all

# Validate a specific pipe
pipelex validate YOUR_PIPE_CODE

# Show all available pipes
pipelex show pipe --all

# Show details of a specific pipe
pipelex show pipe YOUR_PIPE_CODE
```

## Best Practices

### 1. Organization

- Keep related concepts and pipes in the same `.mthds` file
- Use meaningful domain codes that reflect functionality
- Match Python file names with MTHDS file names (`finance.mthds` → `finance.py`)
- Group complex pipelines using subdirectories

### 2. Structure Classes

- Only create Python classes when you need structured output
- Name classes to match concept names exactly
- Use `_struct.py` suffix for files containing structure classes (e.g., `finance_struct.py`)
- Inherit from `StructuredContent` or its subclasses
- Place structure class files near their corresponding `.mthds` files
- **Keep modules clean**: Avoid module-level code that executes on import (Pipelex imports modules during auto-discovery)

### 3. Custom Functions

- Always use the `@pipe_func()` decorator
- Use descriptive function names
- Document function parameters and return types
- Keep functions focused and testable
- **Keep modules clean**: Avoid module-level code that executes on import (Pipelex imports modules during auto-discovery)

### 4. Validation

- Run `pipelex validate --all` after making changes
- Check for domain code consistency
- Verify concept relationships
- Test pipes individually before composing them

## Troubleshooting

### Pipelines Not Found

**Problem:** Pipelex doesn't find your `.mthds` files.

**Solutions:**

1. Ensure files have the `.mthds` extension
2. Check that files are not in excluded directories
3. Verify file permissions allow reading
4. Run `pipelex show pipe --all` to see what was discovered

### Structure Classes Not Registered

**Problem:** Your Python classes aren't recognized.

**Solutions:**

1. Ensure classes inherit from `StructuredContent`
2. Check class names match concept names exactly
3. Verify files are not in excluded directories
4. Make sure class definitions are valid Python

### Custom Functions Not Found

**Problem:** `PipeFunc` can't find your function.

**Solutions:**

1. Add the `@pipe_func()` decorator
2. Ensure function signature matches requirements
3. Check function is `async` and accepts `working_memory`
4. Verify function is in a discoverable location

### Validation Errors

**Problem:** `pipelex validate --all` shows errors.

**Solutions:**

1. Read error messages carefully - they indicate the problem
2. Check concept references are spelled correctly
3. Verify pipe configurations match expected format
4. Ensure all required fields are present

## Related Documentation

- [Libraries](../../building-methods/libraries.md) - Understanding method libraries
- [Packages](../../building-methods/packages.md) - Organizing methods into packages
