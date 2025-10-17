# Executing Pipelines with Inputs

When you run a Pipelex pipeline from Python, you often need to provide input data. The `input_memory` parameter gives you a flexible and intuitive way to pass data to your pipelines.

This guide explains the different formats you can use and when to use each one.

## Understanding input_memory

The `input_memory` parameter accepts a dictionary where:

- **Keys** are the input variable names (matching the `inputs` defined in your pipeline)
- **Values** can be provided in multiple formats for convenience

Under the hood, `input_memory` uses this type definition:

```python
StuffContentOrData = dict[str, Any] | StuffContent | list[Any] | str
ImplicitMemory = dict[str, StuffContentOrData]
```

Pipelex is smart about detecting what you mean and automatically wraps your data in the appropriate content types.

!!! tip "Working with Lists"
    When providing multiple items as input (lists) or expecting multiple outputs, understanding multiplicity is essential. See [Understanding Multiplicity](understanding-multiplicity.md) for a comprehensive guide on how Pipelex handles single items versus collections.

## Quick Comparison

Here's when to use each format:

| Format | Use Case | Example |
|--------|----------|---------|
| **Simple String** | Text inputs, quick prototypes | `"input": "Hello world"` |
| **Native Content** | PDF, Image, or other native types | `"doc": PDFContent(url="file.pdf")` |
| **Explicit Format** | Custom concepts, refined concepts | `"data": {"concept": "domain.ConceptCode", "content": value}` |
| **Mixed Formats** | Multiple inputs of different types | Combine any of the above |

## Format 1: Simple String Inputs

The simplest way to provide text input is with a plain string. Pipelex automatically converts it to `TextContent`.

### Example

```python
pipe_output = await execute_pipeline(
    pipe_code="summarize_story",
    input_memory={
        "story": """
        Once upon a time there was a brave knight who saved the kingdom from a dragon.
        [...]
        # Imagine this is a long text for the purpose of this example
        [...]
        and they lived happily ever after.
        """,
    },
)
```

**When to use:**

- Your pipeline expects a `Text` concept
- You're passing simple string data
- You want the most concise syntax

## Format 2: Native Content Types

For native concepts like `PDF`, `Image`, `Text`, `Number`, and `Page`, you can use their content classes directly.

### PDF Example

```python
from pipelex.core.stuffs.pdf_content import PDFContent

pipe_output = await execute_pipeline(
    pipe_code="process_invoice",
    input_memory={
        "document": PDFContent(url="invoice.pdf"),
    },
)
```

### Image Example

```python
from pipelex.core.stuffs.image_content import ImageContent

pipe_output = await execute_pipeline(
    pipe_code="analyze_photo",
    input_memory={
        "photo": ImageContent(url="photo.jpg"),
    },
)
```

**Why this works:**

Native content types are automatically recognized by Pipelex. The system knows that `PDFContent` corresponds to the `PDF` concept, `ImageContent` to `Image`, and so on.

**When to use:**

- Your pipeline expects a native concept (`PDF`, `Image`, `Text`, `Number`, `Page`)
- You want type safety and IDE autocomplete
- You're loading from files or URLs

## Format 3: Explicit Concept Format

For custom concepts or concepts that refine native types, use the explicit format with `concept` and `content` keys.

### Example with Refined Concept

```python
from pipelex.core.stuffs.image_content import ImageContent

pipe_output = await execute_pipeline(
    pipe_code="extract_gantt",
    input_memory={
        "gantt_chart_image": {
            "concept": "gantt.GanttChartImage",  # Custom concept that refines Image
            "content": ImageContent(url="gantt.png"),
        }
    },
)
```

### Example with Custom Structured Type

```python
pipe_output = await execute_pipeline(
    pipe_code="answer_question",
    input_memory={
        "question": {
            "concept": "qa.Question",
            "content": "What is the capital of France?",
        },
    },
)
```

**When to use:**

- Your pipeline expects a custom concept (not a native one)
- Your concept refines a native type but adds semantic meaning
- You need to be explicit about which concept you're providing

!!! note "Why Explicit Format is Sometimes Required"
    If you have a concept like `gantt.GanttChartImage` that refines the native `Image` concept, Pipelex can't automatically know you mean a `GanttChartImage` when you pass an `ImageContent`. The explicit format removes this ambiguity.

## Format 4: Multiple Inputs with Mixed Formats

You can mix and match formats freely in the same `input_memory` dictionary.

### Complex Example

```python
from pipelex.core.stuffs.text_content import load_text_from_path

pipe_output = await execute_pipeline(
    pipe_code="analyze_contract",
    input_memory={
        # Format 1: Simple string
        "client_instructions": "Focus on payment terms",
        
        # Format 1: String loaded from file (still just a string)
        "contract_text": load_text_from_path("contract.txt"),
        
        # Format 3: Explicit concept
        "question": {
            "concept": "legal.Question",
            "content": "What are the fees?",
        },
    },
)
```

**When to use:**

- Your pipeline has multiple inputs
- Different inputs have different types or requirements
- You want to use the most convenient format for each input

## Guidelines: Choosing the Right Format

Follow these simple rules:

### Use Simple Strings When

- ✅ The input is text data
- ✅ The pipeline expects a `Text` concept
- ✅ You want minimal syntax

### Use Native Content Types When

- ✅ Working with `PDF`, `Image`, `Number`, or `Page` concepts
- ✅ You want type checking and IDE support
- ✅ Loading from files or URLs

### Use Explicit Format When

- ✅ Your concept is not a native type
- ✅ Your concept refines a native type (adds semantic meaning)
- ✅ You need to specify exactly which concept you're providing
- ✅ Pipelex gives you a type error without it

## Common Patterns

### Pattern 1: Document Processing

```python
# Most document processing pipelines expect a PDF input
pipe_output = await execute_pipeline(
    pipe_code="extract_data",
    input_memory={
        "document": PDFContent(url="document.pdf"),
    },
)
```

### Pattern 2: Image Analysis

```python
# Image processing with native Image concept
pipe_output = await execute_pipeline(
    pipe_code="describe_image",
    input_memory={
        "image": ImageContent(url="photo.jpg"),
    },
)
```

### Pattern 3: Text Generation

```python
# Simple text input for generation tasks
pipe_output = await execute_pipeline(
    pipe_code="write_story",
    input_memory={
        "topic": "A robot learning to love",
    },
)
```

### Pattern 4: Specialized Types

```python
# Custom concept that needs explicit specification
pipe_output = await execute_pipeline(
    pipe_code="process_tweet",
    input_memory={
        "draft_tweet": {
            "concept": "social.DraftTweet",
            "content": "Check out this amazing framework!",
        },
    },
)
```

## Working with Structured Content

If you have structured data defined as a `StructuredContent` class, you can pass instances directly when using the explicit format.

### Example

```python
from my_project.models import Character

# Create a structured object
character = Character(
    name="Alice",
    age=30,
    description="A brave explorer",
)

# Pass it to the pipeline
pipe_output = await execute_pipeline(
    pipe_code="analyze_character",
    input_memory={
        "character": {
            "concept": "story.Character",
            "content": character,
        },
    },
)
```

## Alternative: Using working_memory Directly

For advanced use cases, you can construct the working memory explicitly instead of using `input_memory`:

```python
from pipelex.core.stuffs.stuff_factory import StuffFactory
from pipelex.core.memory.working_memory_factory import WorkingMemoryFactory

# Create a stuff object
character_stuff = StuffFactory.make_from_concept_string(
    concept_string="story.Character",
    name="character",
    content=character_data,
)

# Create working memory
working_memory = WorkingMemoryFactory.make_from_single_stuff(
    stuff=character_stuff,
)

# Execute with working memory
pipe_output = await execute_pipeline(
    pipe_code="analyze_character",
    working_memory=working_memory,
)
```

**When to use `working_memory` directly:**

- You need fine-grained control over stuff naming
- You're building complex multi-stuff scenarios
- You're working with intermediate pipeline states

**For most cases, `input_memory` is simpler and recommended.**

## Troubleshooting

### Error: "Concept not found"

If you see an error about a concept not being found, you may need to use the explicit format:

```python
# ❌ Won't work if MyType is a custom concept
input_memory={"data": my_value}

# ✅ Use explicit format
input_memory={
    "data": {
        "concept": "domain.MyType",
        "content": my_value,
    }
}
```

### Error: "Type mismatch"

Make sure the content type matches what your concept expects:

```python
# ❌ Wrong: passing a string when concept expects structured data
input_memory={
    "character": {
        "concept": "story.Character",
        "content": "Alice",  # Should be a Character instance
    }
}

# ✅ Correct: pass the right type
input_memory={
    "character": {
        "concept": "story.Character",
        "content": Character(name="Alice", age=30, ...),
    }
}
```

## Related Documentation

- [Design and Run Pipelines](design_and_run_pipelines.md) - Learn about pipeline execution basics
- [Define Your Concepts](define_your_concepts.md) - Understand concepts and their role
- [Structuring Concepts](structuring-concepts.md) - Create structured data types
- [Cookbook Examples](../cookbook-examples/index.md) - See real-world input patterns


