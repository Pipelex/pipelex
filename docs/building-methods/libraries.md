---
description: "Libraries collect domains, concepts, and pipes into a unified runtime context. Understand how Pipelex loads and resolves your Methods."
---

# Libraries

A **Library** in Pipelex is a complete collection of domains, concepts, and pipes that can be loaded and used together. It represents the full set of Pipelex definitions available for execution within a specific context, typically for a single pipeline run.

## Library Structure

A Library is composed of three core components:

- **DomainLibrary**: Manages all domain definitions
- **ConceptLibrary**: Manages all concept definitions across domains
- **PipeLibrary**: Manages all pipe definitions

These three components together form what we call a **Pipelex Bundle** (the content you define in `.mthds` files). Learn more about bundle structure and syntax in the [Pipelex Bundle Specification](./pipelex-bundle-specification.md).

## Understanding Library Scope

When you execute pipelines using `execute` or `start`, a library is created to hold all the necessary definitions. This library:

- Contains the pipes and concepts available for execution
- Provides isolation between different pipeline runs when using different library IDs
- Can be loaded from local directories or from MTHDS content strings

## Uniqueness Rules

Libraries enforce specific uniqueness constraints to maintain consistency:

| Component | Uniqueness Scope | Example |
|-----------|-----------------|---------|
| **Domains** | Unique per library | Each library can have one `marketing` domain |
| **Pipes** | Unique per library* | Each library can have one `generate_tagline` pipe |
| **Concepts** | Unique per domain | Each domain can have one `ProductDescription` concept |
| **Domain.Concept** | Unique per library | `marketing.ProductDescription` is unique within a library |

!!! info "Future Change"
    *Pipe uniqueness will soon be scoped per domain instead of per library, allowing different domains within the same library to have pipes with the same code.

## Local vs Remote Libraries

### Local Libraries (Current)

Currently, all libraries are **local**, meaning they are loaded from:

- Directories on your filesystem (using the `library_dirs` constructor parameter)
- MTHDS content strings (using the `mthds_contents` parameter)
- The current working directory (default behavior)

```python
# Loading from local directories
runner = PipelexMTHDSProtocol(library_dirs=["./pipelines", "./shared_pipes"])
response = await runner.execute(
    pipe_code="generate_tagline",
    inputs={...},
)
pipe_output = response.pipe_output
```

### Remote Libraries (Coming Soon)

In the future, you'll be able to import and use remote libraries, enabling:

- Sharing pipe definitions across teams and projects
- Versioned library dependencies
- Centralized library management

## Library Lifecycle

### 1. Library Creation

When the runner executes a method, a library is created with a unique `library_id`. Pipelex-specific configuration (library id, directories) is provided on the `PipelexMTHDSProtocol` constructor:

```python
# Explicit library ID
runner = PipelexMTHDSProtocol(library_id="my_custom_library")
response = await runner.execute(
    pipe_code="my_pipe",
    inputs={...},
)

# Automatic library ID (defaults to pipeline_run_id)
runner = PipelexMTHDSProtocol()
response = await runner.execute(
    pipe_code="my_pipe",
    inputs={...},
)
```

### 2. Library Loading

The library is populated based on the parameters you provide:

**Option A: Loading from directories**

```python
# Loads all .mthds files from specified directories
runner = PipelexMTHDSProtocol(library_dirs=["./pipelines"])
response = await runner.execute(
    pipe_code="my_pipe",
    inputs={...},
)
```

**Option B: Loading from MTHDS content**

```python
# Loads only the provided MTHDS content
mthds_content = """
domain = "marketing"

[concept]
ProductDescription = "A product description"

[pipe.my_pipe]
type = "PipeLLM"
inputs = { desc = "ProductDescription" }
output = "Tagline"
prompt = "Generate a tagline for: @desc"
"""

runner = PipelexMTHDSProtocol()
response = await runner.execute(
    mthds_contents=[mthds_content],
    pipe_code="my_pipe",
    inputs={...},
)
```

### 3. Library Validation

After loading, the library validates:

- All pipe input/output concepts exist in the concept library
- All pipe dependencies (for pipe controllers) exist in the pipe library
- Domain and concept definitions are consistent

## Working with Multiple Libraries

You can manage multiple libraries simultaneously by using different `library_id` values:

```python
# Library for marketing pipelines
marketing_runner = PipelexMTHDSProtocol(library_id="marketing_lib", library_dirs=["./marketing_pipes"])
marketing_response = await marketing_runner.execute(
    pipe_code="generate_tagline",
    inputs={...},
)

# Library for analytics pipelines
analytics_runner = PipelexMTHDSProtocol(library_id="analytics_lib", library_dirs=["./analytics_pipes"])
analytics_response = await analytics_runner.execute(
    pipe_code="analyze_data",
    inputs={...},
)
```

## Best Practices

### 1. Use Explicit Library IDs for Long-Running Applications

```python
# Good: Explicit ID for maintaining state
runner = PipelexMTHDSProtocol(library_id="app_library")
response = await runner.execute(
    pipe_code="my_pipe",
    inputs={...},
)
```

### 2. Use MTHDS Content for Dynamic Pipelines

When generating or modifying pipelines dynamically, use `mthds_contents`:

```python
# Generate MTHDS content dynamically
mthds_content = generate_custom_pipeline(user_requirements)

runner = PipelexMTHDSProtocol()
response = await runner.execute(
    mthds_contents=[mthds_content],
    inputs={...},
)
```

A temporary library will be created holding the Pipelex bundle, and the library_id will be pipeline_run_id.

### 3. Reuse Library IDs for Related Executions

If multiple pipeline runs should share the same library context:

```python
runner = PipelexMTHDSProtocol(library_id="shared_context", library_dirs=["./pipes"])

# First execution
response1 = await runner.execute(
    pipe_code="pipe1",
    inputs={...},
)

# Second execution with same library
response2 = await runner.execute(
    pipe_code="pipe2",
    inputs={...},
)
```

## Related Documentation

- [Executing Pipelines](pipes/executing-pipelines.md) - Learn how to execute pipelines with different library configurations
- [Pipelex Bundle Specification](./pipelex-bundle-specification.md) - Understand the structure of MTHDS files
- [Domains](./domain.md) - Learn about organizing pipes into domains
- [Concepts](./concepts/define_your_concepts.md) - Understand how concepts work within libraries

