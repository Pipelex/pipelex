# Native Concepts

Pipelex includes several built-in native concepts that cover common data types in AI workflows. These concepts come with predefined structures and are automatically available in all pipelines—no setup required.

For an introduction to concepts, see [Define Your Concepts](define_your_concepts.md).

## What Are Native Concepts?

Native concepts are ready-to-use building blocks for AI workflows. They represent common data types you'll frequently work with: text, images, PDFs, numbers, and combinations thereof.

**Key characteristics:**

- **Pre-defined**: Built into Pipelex, no need to declare them
- **Structured**: Each has a corresponding Python data model
- **Universal**: Available across all pipelines and domains
- **Extensible**: You can refine them to create more specific concepts

## Available Native Concepts

Here are all the native concepts you can use out of the box:

| Concept | Description | Content Class Name |
|-----------------|-------------|---------------------|
| `Text` | A text | `TextContent` |
| `Image` | An image | `ImageContent` |
| `PDF` | A PDF document | `PDFContent` |
| `TextAndImages` | Text with its associated images | `TextAndImagesContent` |
| `Number` | A number | `NumberContent` |
| `Page` | A document page with text, images, and optional page view | `PageContent` |
| `Dynamic` | A dynamic concept that adapts to context | `DynamicContent` |
| `Anything` | Any type of content | *No specific implementation* |

## Native Concept Structures

Each native concept has a corresponding Python structure that defines its data model. Understanding these structures helps you work with the data they contain.

### TextContent

The simplest native concept:

```python
class TextContent(StuffContent):
    text: str
```

**Use for:** Plain text outputs, summaries, descriptions, etc.

### ImageContent

Represents an image with optional metadata:

```python
class ImageContent(StuffContent):
    url: str
    source_prompt: Optional[str] = None
    caption: Optional[str] = None
    base_64: Optional[str] = None
```

**Fields:**
- `url`: Location of the image (file path or URL)
- `source_prompt`: The prompt used to generate the image (if applicable)
- `caption`: Descriptive text for the image
- `base_64`: Base64-encoded image data (alternative to URL)

**Use for:** Photos, generated images, diagrams, screenshots.

### PDFContent

Represents a PDF document:

```python
class PDFContent(StuffContent):
    url: str
```

**Fields:**
- `url`: Location of the PDF file (file path or URL)

**Use for:** Contracts, invoices, reports, any PDF document.

### NumberContent

Represents numeric values:

```python
class NumberContent(StuffContent):
    number: Union[int, float]
```

**Use for:** Counts, calculations, metrics, scores.

### TextAndImagesContent

Combines text with one or more images:

```python
class TextAndImagesContent(StuffContent):
    text: Optional[TextContent]
    images: Optional[List[ImageContent]]
```

**Use for:** Rich content combining text and visuals, extracted document content, reports with diagrams.

### PageContent

Represents a document page with both content and visual representation:

```python
class PageContent(StructuredContent):
    text_and_images: TextAndImagesContent
    page_view: Optional[ImageContent] = None
```

**Fields:**
- `text_and_images`: The extracted text and embedded images from the page
- `page_view`: A screenshot or rendering of the entire page

**Use for:** Document pages extracted by `PipeExtract`, individual pages from multi-page documents.

### DynamicContent

A flexible concept that adapts to context:

```python
class DynamicContent(StuffContent):
    # Dynamic content that can adapt to context
    # Structure is flexible and determined at runtime
    pass
```

**Use for:** Workflows where the content structure isn't known in advance.

### Anything

!!! note "Special Concepts"
    `Anything` is referenced in the native concept definitions but does not have specific implementations. It is handled through the generic content system and is primarily used as semantic markers.

## Using Native Concepts

Native concepts can be used directly in your pipeline definitions without any additional setup:

### In Pipe Inputs

```plx
[pipe.analyze_document]
type = "PipeLLM"
description = "Analyze a PDF document"
inputs = { document = "PDF" }
output = "Text"
prompt = "Analyze this document and provide a summary"
```

### In Pipe Outputs

```plx
[pipe.process_image]
type = "PipeLLM"
description = "Describe an image"
inputs = { photo = "Image" }
output = "Text"
prompt = "Describe what you see in this image"
```

### With Page Content

The `Page` concept is particularly useful with `PipeExtract`:

```plx
[pipe.extract_pages]
type = "PipeExtract"
description = "Extract content from a document"
inputs = { document = "PDF" }
output = "Page"
```

This extracts each page with both its text/images and a visual representation.

### In Complex Workflows

```plx
[pipe.create_report]
type = "PipeSequence"
description = "Generate a report with text and images"
inputs = { data = "Text" }
output = "TextAndImages"
steps = [
    { pipe = "analyze_data", result = "analysis" },
    { pipe = "create_charts", result = "charts" },
    { pipe = "combine_content", result = "report" }
]
```

## Refining Native Concepts

You can create more specific concepts by refining native ones—for example, creating an `Invoice` concept that refines `PDF` or a `ProductPhoto` that refines `Image`. This gives you semantic clarity while inheriting the native concept's structure.

**For complete details on refinement syntax, type compatibility, limitations, best practices, and future features, see [Refining Concepts](refining-concepts.md).**

## When to Use Native Concepts

Use native concepts directly when:

- ✅ Working with simple, unstructured data
- ✅ The native structure is sufficient for your needs
- ✅ You want maximum interoperability across pipes
- ✅ Prototyping and quick experiments

Refine native concepts when:

- ✅ You need semantic specificity (e.g., `Invoice` vs `PDF`)
- ✅ You want to add custom structure on top of the base structure
- ✅ Building domain-specific workflows
- ✅ Need type safety for specific document types

## Common Patterns

### Text Processing

```plx
[pipe.summarize]
type = "PipeLLM"
description = "Summarize any text"
inputs = { content = "Text" }
output = "Text"
prompt = "Summarize this content: @content"
```

### Document Extraction

```plx
[pipe.extract_pages]
type = "PipeExtract"
description = "Extract content from a document"
inputs = { document = "PDF" }
output = "Page[]"

[pipe.analyze_page]
type = "PipeLLM"
description = "Analyze a page"
inputs = { page = "Page[]" }
output = "Text"
prompt = """Analyze those pages: 
@pages
"""

[pipe.extract_and_analyze]
type = "PipeSequence"
description = "Extract and analyze a PDF"
inputs = { document = "PDF" }
output = "Text"
steps = [
    { pipe = "extract_pages", result = "pages" },
    { pipe = "analyze_pages", result = "analysis" }
]
```

### Multi-Modal Processing

```plx
[pipe.analyze_with_context]
type = "PipeLLM"
description = "Analyze image with text context"
inputs = { image = "Image", context = "Text" }
output = "Text"
prompt = "Given this context: $context

Analyze this image: $image"
```

## Related Documentation

- [Define Your Concepts](define_your_concepts.md) - Learn about concept semantics
- [Inline Structures](inline-structures.md) - Add structure to refined concepts
- [Python StructuredContent Classes](python-classes.md) - Advanced customization
- [Writing Workflows Tutorial](../../2-get-started/pipe-builder.md) - Use native concepts in pipelines

