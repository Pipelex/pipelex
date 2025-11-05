# Pipe Output

When you execute a pipeline, each pipe produces a `Stuff` that is automatically stored in the [Working Memory](working-memory.md). The final output of the pipeline execution is accessible through a `PipeOutput` object.

## How Pipe Outputs Work

Every pipe in your pipeline creates a **stuff** as its output. This stuff is a structured data container that holds:

A `Stuff` is a structured data container that holds:

- The concept that defines the structure
- The actual instance of the concept (text, structured data, images, etc.)

Each pipe's output is automatically added to the working memory with a name (specified by the `result` field in the [Pipe Sequence](./pipe-controllers/PipeSequence.md)). 

The **main_stuff** is the final output produced by the last pipe in your pipeline.

## Accessing Pipeline Output

When you execute a pipeline, you receive a `PipeOutput` object:

```python
pipe_output = await execute_pipeline(
    pipe_code="process_invoice",
    inputs={...}
)
```

The `PipeOutput` object provides methods to extract and work with the main output.

## Extracting the Main Output

How you extract the main output depends on how the concept structure was defined.

### Option 1: Python Class Structure

If the output concept was defined as a Python class (inheriting from `StructuredContent`, see more here [Python StructuredContent Classes](../concepts/python-classes.md)), you can import the class and use it for type-safe extraction:

```python
from my_project.finance.finance_struct import Invoice

pipe_output = await execute_pipeline(
    pipe_code="extract_invoice",
    inputs={...}
)

# Extract with type safety
invoice = pipe_output.main_stuff_as(content_type=Invoice)
# invoice is now typed as Invoice with full IDE support
```

### Option 2: Inline Structure

If the output concept was defined with [inline structures](../concepts/inline-structures.md) directly in the `.plx` file, the generated class is not importable. Use the `PipeOutput` accessor methods instead:

```python
pipe_output = await execute_pipeline(
    pipe_code="extract_invoice",
    inputs={...}
)

# Access as dictionary-like structure
main_stuff = pipe_output.main_stuff
content = main_stuff.content  # Access the content object

# Or for text outputs
text_content = pipe_output.main_stuff_as_text
text = pipe_output.main_stuff_as_str  # Direct string access
```

## PipeOutput Accessor Methods

The `PipeOutput` class provides specialized methods for accessing different types of content:

### Generic Accessors

**`main_stuff`** - Returns the raw `Stuff` object containing the output:

```python
stuff = pipe_output.main_stuff
```

**`main_stuff_as(content_type)`** - Extracts content as a specific type:

```python
invoice = pipe_output.main_stuff_as(content_type=Invoice)
```

### List Accessors

**`main_stuff_as_list(item_type)`** - Returns a `ListContent` wrapper with typed items:

```python
invoice_list = pipe_output.main_stuff_as_list(item_type=Invoice)
# Access: invoice_list.items
```

**`main_stuff_as_items(item_type)`** - Returns the items directly as a Python list:

```python
invoices = pipe_output.main_stuff_as_items(item_type=Invoice)
# Direct list of Invoice objects
```

### Native Content Type Accessors

For native Pipelex concepts, use these convenience properties:

**`main_stuff_as_text`** - Returns `TextContent` object:

```python
text_content = pipe_output.main_stuff_as_text
```

This works only if the main_stuff is (or refines) a `TextContent` concept.

**`main_stuff_as_str`** - Returns the text as a string:

```python
text = pipe_output.main_stuff_as_str
```

This works only if the main_stuff is (or refines) a `TextContent` concept.

**`main_stuff_as_image`** - Returns `ImageContent` object:

```python
image = pipe_output.main_stuff_as_image
```

This works only if the main_stuff is (or refines) a `ImageContent` concept.

**`main_stuff_as_text_and_image`** - Returns `TextAndImagesContent` object:

```python
content = pipe_output.main_stuff_as_text_and_image
```

This works only if the main_stuff is (or refines) a `TextContent` and a `ImageContent` concept.

**`main_stuff_as_number`** - Returns `NumberContent` object:

```python
number = pipe_output.main_stuff_as_number
```

This works only if the main_stuff is (or refines) a `NumberContent` concept.

**`main_stuff_as_html`** - Returns `HtmlContent` object:

```python
html = pipe_output.main_stuff_as_html
```

This works only if the main_stuff is (or refines) a `HtmlContent` concept.

**`main_stuff_as_mermaid`** - Returns `MermaidContent` object:

```python
mermaid = pipe_output.main_stuff_as_mermaid
```

This works only if the main_stuff is (or refines) a `MermaidContent` concept.

## Working Memory Access

The `PipeOutput` object also provides access to the complete working memory:

```python
working_memory = pipe_output.working_memory
```

This allows you to access intermediate results from multi-step pipelines. See [Working Memory](working-memory.md) for details.

## Related Documentation

- [Working Memory](working-memory.md) - Understanding data flow between pipes
- [Executing Pipelines](executing-pipelines.md) - How to run pipelines
- [Inline Structures](../concepts/inline-structures.md) - Defining structures in `.plx` files
- [Python StructuredContent Classes](../concepts/python-classes.md) - Defining structures in Python

