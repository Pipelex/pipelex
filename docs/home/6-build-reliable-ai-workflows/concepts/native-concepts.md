# Native Concepts

Pipelex includes several built-in native concepts that cover common data types in AI methods. These concepts come with predefined structures and are automatically available in all pipelines—no setup required.

For an introduction to concepts, see [Define Your Concepts](define_your_concepts.md).

## What Are Native Concepts?

Native concepts are ready-to-use building blocks for AI methods. They represent common data types you'll frequently work with: text, images, documents, numbers, and combinations thereof.

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
| `Document` | A document (PDF, DOCX, PPTX) | `DocumentContent` |
| `TextAndImages` | Text with its associated images | `TextAndImagesContent` |
| `Number` | A number | `NumberContent` |
| `Page` | A document page with text, images, and optional page view | `PageContent` |
| `Dynamic` | A dynamic concept that adapts to context | `DynamicContent` |
| `JSON` | A JSON object | `JSONContent` |
| `SearchResult` | A web search result with answer and sources | `SearchResultContent` |
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

### DocumentContent

Represents a document (PDF, DOCX, PPTX, etc.):

```python
class DocumentContent(StuffContent):
    url: str
    mime_type: str | None = None
```

**Fields:**

- `url`: Location of the document file (file path or URL)
- `mime_type`: Optional MIME type of the document (e.g., "application/pdf", "application/vnd.openxmlformats-officedocument.wordprocessingml.document")

**Use for:** Contracts, invoices, reports, presentations, any document file.

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
    raw_html: Optional[str]
```

**Fields:**

- `text`: The text content
- `images`: A list of images extracted from the content
- `raw_html`: The raw HTML of the fetched page, when requested via `include_raw_html`

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

**Use for:** Methods where the content structure isn't known in advance.

### JSONContent

A concept that represents a JSON object. This enables pipes to receive as input or to output any JSON object.

```python
class JSONContent(StuffContent):
    json_obj: dict[str, Any]
```

### SearchResultContent

Represents the result of a web search query. Produced by `PipeSearch`:

```python
class SearchResultContent(StuffContent):
    answer: str
    sources: list[SearchSourceContent] = []
```

**Fields:**

- `answer`: The synthesized answer text from the search
- `sources`: A list of source citations, each containing:
    - `name` (str): Source name/title
    - `url` (str): Source URL
    - `snippet` (str | None): Relevant excerpt from the source

**Use for:** Web search results, research findings, information retrieval with citations.

### Anything

!!! note "Special Concepts"
    `Anything` is referenced in the native concept definitions but does not have specific implementations. It is handled through the generic content system and is primarily used as semantic markers.

## Using Native Concepts

Native concepts can be used directly in your pipeline definitions without any additional setup:

### In Pipe Inputs

```toml
[pipe.analyze_document]
type = "PipeLLM"
description = "Analyze a document"
inputs = { document = "Document" }
output = "Text"
prompt = "Analyze this document and provide a summary"
```

### In Pipe Outputs

```toml
[pipe.process_image]
type = "PipeLLM"
description = "Describe an image"
inputs = { photo = "Image" }
output = "Text"
prompt = "Describe what you see in this image"
```

### With Page Content

The `Page` concept is particularly useful with `PipeExtract`:

```toml
[pipe.extract_pages]
type = "PipeExtract"
description = "Extract content from a document"
inputs = { document = "Document" }
output = "Page"
```

This extracts each page with both its text/images and a visual representation.

### In Complex Methods

```toml
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

You can create more specific concepts by refining native ones—for example, creating an `Invoice` concept that refines `Document` or a `ProductPhoto` that refines `Image`. This gives you semantic clarity while inheriting the native concept's structure.

**For complete details on refinement syntax, type compatibility, limitations, best practices, and future features, see [Refining Concepts](refining-concepts.md).**

## When to Use Native Concepts

Use native concepts directly when:

- ✅ Working with simple, unstructured data
- ✅ The native structure is sufficient for your needs
- ✅ You want maximum interoperability across pipes
- ✅ Prototyping and quick experiments

Refine native concepts when:

- ✅ You need semantic specificity (e.g., `Invoice` vs `Document`)
- ✅ You want to add custom structure on top of the base structure
- ✅ Building domain-specific methods
- ✅ Need type safety for specific document types

## Common Patterns

### Text Processing

```toml
[pipe.summarize]
type = "PipeLLM"
description = "Summarize any text"
inputs = { content = "Text" }
output = "Text"
prompt = "Summarize this content: @content"
```

### Document Extraction

```toml
[pipe.extract_pages]
type = "PipeExtract"
description = "Extract content from a document"
inputs = { document = "Document" }
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
description = "Extract and analyze a document"
inputs = { document = "Document" }
output = "Text"
steps = [
    { pipe = "extract_pages", result = "pages" },
    { pipe = "analyze_pages", result = "analysis" }
]
```

### Multi-Modal Processing

```toml
[pipe.analyze_with_context]
type = "PipeLLM"
description = "Analyze image with text context"
inputs = { image = "Image", context = "Text" }
output = "Text"
prompt = "Given this context: $context

Analyze this image: $image"
```

### Web Search

```toml
[pipe.search_topic]
type = "PipeSearch"
description = "Search the web for information"
inputs = { topic = "Text" }
output = "SearchResult"
model = "$standard"
prompt = "What is $topic?"
```

## Related Documentation

- [Define Your Concepts](define_your_concepts.md) - Learn about concept semantics
- [Inline Structures](inline-structures.md) - Add structure to refined concepts
- [Python StructuredContent Classes](python-classes.md) - Advanced customization
- [Writing Methods Tutorial](../../2-get-started/pipe-builder.md) - Use native concepts in pipelines

