# Designing Pipelines

In Pipelex, a pipeline is not just a rigid sequence of steps; it's a dynamic and intelligent workflow built by composing individual, reusable components called **pipes**. This approach allows you to break down complex AI tasks into manageable, testable, and reliable units.

This guide provides an overview of how to design your pipelines.

## The Building Blocks: Pipes

A pipeline is composed of pipes. There are two fundamental types of pipes you will use to build your workflows:

*   **[Pipe Operators](./pipe-operators/index.md)**: These are the "workers" of your pipeline. They perform concrete actions like calling an LLM (`PipeLLM`), extracting text from a document (`PipeExtract`), or running a Python function (`PipeFunc`). Each operator is a specialized tool designed for a specific task.
*   **[Pipe Controllers](./pipe-controllers/index.md)**: These are the "managers" of your pipeline. They don't perform tasks themselves but orchestrate the execution flow of other pipes. They define the logic of your workflow, such as running pipes in sequence (`PipeSequence`), in parallel (`PipeParallel`), or based on a condition (`PipeCondition`).

## Designing a Pipeline: Composition in PLX

The most common way to design a pipeline is by defining and composing pipes in a `.plx` configuration file. This provides a clear, declarative way to see the structure of your workflow.

Each pipe, whether it's an operator or a controller, is defined in its own `[pipe.<pipe_code>]` table. The `<pipe_code>` becomes the unique identifier for that pipe.

!!! important "Pipe Code Naming Convention"
    Pipe codes **MUST** be in `snake_case` (lowercase with underscores). Use descriptive names that clearly indicate what the pipe does.
    
    **Valid pipe codes:**
    ```plx
    ✅ [pipe.generate_tagline]
    ✅ [pipe.extract_invoice]
    ✅ [pipe.validate_and_process]
    ✅ [pipe.send_email]
    ```
    
    **Invalid pipe codes:**
    ```plx
    ❌ [pipe.GenerateTagline]     # PascalCase not allowed
    ❌ [pipe.generateTagline]      # camelCase not allowed
    ❌ [pipe.generate-tagline]     # Hyphens not allowed
    ❌ [pipe.GENERATE_TAGLINE]     # All caps not allowed
    ```

Let's look at a simple example. Imagine we want a workflow that:
1.  Takes a product description.
2.  Generates a short, catchy marketing tagline for it.

We can achieve this with a `PipeLLM` operator.

`marketing_pipeline.plx`
```plx
domain = "marketing"
description = "Marketing content generation domain"

# 1. Define the concepts used in our pipes
[concept]
ProductDescription = "A description of a product's features and benefits"
Tagline = "A catchy marketing tagline"

# 2. Define the pipe that does the work
[pipe.generate_tagline]
type = "PipeLLM"
description = "Generate a catchy tagline for a product"
inputs = { description = "ProductDescription" }
output = "Tagline"
prompt = """
Product Description:
@description

Generate a catchy tagline based on the above description.
The tagline should be memorable, concise, and highlight the key benefit.
"""
```

This defines a single-step pipeline. The pipe `generate_tagline` takes a `ProductDescription` as input and outputs a `Tagline` (both are native Text concepts, see more about native concepts [here](../concepts/native-concepts.md)).

The inputs specified will be required before the pipe is executed. Those inputs should be stored in the [Working Memory](working-memory.md).

The output concept is very important. Indeed, the output of your pipe will be corresponding to the concept you specify. If the concept is structured, the output will be a structured object. If the concept is native, the output will be a string.

### Understanding the Pipe Contract

Every pipe defines a **contract** through its `inputs` and `output` fields. This contract is fundamental to how Pipelex ensures reliability in your workflows:

*   **`inputs`**: This dictionary defines the **mandatory and necessary** data that must be present in the [Working Memory](working-memory.md) before the pipe can execute. Each key in the dictionary becomes a variable name that you can reference in your pipe's logic (e.g., in prompts), and each value specifies the concept type that the data must conform to. If any required input is missing or doesn't match the expected concept, the pipeline will fail a clear error message.
You can specify multiple inputs by using a list of concepts. For example, `inputs = { description = "ProductDescription", keywords = "Keyword[]" }` will require a `ProductDescription` and a list of `Keyword`s. (See more about [Understanding Multiplicity](./understanding-multiplicity.md) for details.)

*   **`output`**: This field declares what the pipe will produce. The output will always be an instance of the specified concept. The structure and type of the output depend on the concept definition (See more about concepts [here](../concepts/native-concepts.md)).
    *   You can specify **multiple outputs** using bracket notation (e.g., `Keyword[]` for a variable list, or `Image[3]` for exactly 3 images)

### Multi-Step Workflows

To create a multi-step workflow, you use a controller. The `PipeSequence` controller is the most common one. It executes a series of pipes in a specific order.


`marketing_pipeline.plx`
```plx
domain = "marketing"
description = "Marketing content generation domain"

# 1. Define the concepts used in our pipes
[concept]
ProductDescription = "A description of a product's features and benefits"
Tagline = "A catchy marketing tagline"

# 2. Define the first step of your pipe
[pipe.generate_tagline]
type = "PipeLLM"
description = "Generate a catchy tagline for a product"
inputs = { description = "ProductDescription" }
output = "Tagline"
prompt = """
Product Description:
@description

Generate a catchy tagline based on the above description.
The tagline should be memorable, concise, and highlight the key benefit.
"""

# 3. Define the second step of your pipe
[pipe.extract_keywords_from_tagline]
type = "PipeLLM"
description = "Extract keywords from a tagline"
inputs = { tagline = "Tagline" }
output = "Keyword[]"
prompt = """
Extract the most relevant keywords from the following tagline. Focus on features, benefits, and unique selling points:

@tagline

"""

# 4. Define the controller that orchestrates the two steps
[pipe.description_to_tagline]
type = "PipeSequence"
description = "From product description to tagline"
inputs = { description = "ProductDescription" }
output = "Tagline"
steps = [
    { pipe = "generate_tagline", result = "tagline" },
    { pipe = "extract_keywords_from_tagline", result = "keywords" },
]
```

!!! note "Multiple Outputs"
    The `[]` bracket notation in `output = "Keyword[]"` allows the LLM to generate as many keywords as it finds relevant. For a comprehensive guide on controlling how many items pipes produce or accept, see [Understanding Multiplicity](./understanding-multiplicity.md).


This defines a two-step pipeline. The `PipeSequence` controller `description_to_tagline` takes a `ProductDescription` as input and outputs a `Tagline`. The first step is `generate_tagline` which generates a `Tagline` from the `ProductDescription`. The second step is `extract_keywords_from_tagline` which extracts keywords from the `Tagline`.

See here all the different operators, see [Pipe Operators](./pipe-operators/index.md).
See here all the different controllers, see [Pipe Controllers](./pipe-controllers/index.md).

See more about the possibilities in designing your pipelines in the [Pipelex Bundle Specification](../pipelex-bundle-specification.md).