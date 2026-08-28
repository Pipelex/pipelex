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
| `Document` | A document (PDF, DOCX, PPTX, web page) | `DocumentContent` |
| `TextAndImages` | Text with its associated images | `TextAndImagesContent` |
| `Number` | A number | `NumberContent` |
| `YesNo` | The answer to a yes/no question | `YesNoContent` |
| `Date` | A calendar date, optionally with a time of day | `DateContent` |
| `Time` | A time of day, optionally with a UTC offset | `TimeContent` |
| `Page` | A document page with text, images, and optional page view | `PageContent` |
| `Dynamic` | A dynamic concept that adapts to context | `DynamicContent` |
| `JSON` | A JSON object | `JSONContent` |
| `Html` | HTML content with inner HTML and optional CSS class | `HtmlContent` |
| `SearchResult` | A web search result with answer and sources | `SearchResultContent` |
| `Composite` | A named composition of contents | `CompositeContent` |
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
    public_url: str | None = None
    source_prompt: str | None = None
    source_negative_prompt: str | None = None
    caption: str | None = None
    mime_type: str | None = None
    width: int | None = None
    height: int | None = None
    filename: str | None = None
```

**Fields:**

- `url`: Location of the image (a storage URI, an HTTP(S) URL, or a base64 data URL)
- `public_url`: Optional public-facing URL (when `url` is a private/internal reference)
- `source_prompt` / `source_negative_prompt`: The prompts used to generate the image (if applicable)
- `caption`: Descriptive text for the image
- `mime_type`: Optional MIME type of the image
- `width` / `height`: Pixel dimensions — present together or not at all
- `filename`: Optional original filename

**Use for:** Photos, generated images, diagrams, screenshots.

### DocumentContent

Represents a document (PDF, DOCX, PPTX, etc.):

```python
class DocumentContent(StuffContent):
    url: str
    public_url: str | None = None
    mime_type: str | None = None
    filename: str | None = None
    title: str | None = None
    snippet: str | None = None
```

**Fields:**

- `url`: Location of the document file, storage URL, or web page URL
- `public_url`: Optional public-facing URL (when `url` is a private/internal reference)
- `mime_type`: Optional MIME type of the document (e.g., "application/pdf", "application/vnd.openxmlformats-officedocument.wordprocessingml.document")
- `filename`: Optional filename of the document
- `title`: Optional title of the document or source
- `snippet`: Optional text snippet or excerpt from the document

**Use for:** Contracts, invoices, reports, presentations, web pages, search source citations, any document file.

### NumberContent

Represents numeric values:

```python
class NumberContent(StuffContent):
    number: Union[int, float]
```

**Use for:** Counts, calculations, metrics, scores.

### YesNoContent

Represents the answer to a yes/no question — a single boolean verdict:

```python
class YesNoContent(StuffContent):
    yes_no: bool
```

Renders as `yes` or `no` when injected into a prompt. Especially handy as a `PipeLLM` output for judgments — `output = "YesNo"` makes the model return a typed boolean instead of free text answering "yes"/"no":

```toml
[pipe.judge_is_urgent]
type = "PipeLLM"
description = "Decide whether a message is urgent"
inputs = { message = "Text" }
output = "YesNo"
prompt = "Is the following message urgent? Answer yes or no.\n\n$message"
```

Read the verdict from a Python caller via `pipe_output.main_stuff_as_yes_no.yes_no`.

**Use for:** Yes/no judgments, boolean classifications, presence/absence checks, pass/fail verdicts.

### DateContent

Represents a calendar date, as precise as its source states — a required `date` plus an optional time of day:

```python
class DateContent(StuffContent):
    date: datetime.date
    time: datetime.time | None = None
```

The time is present only when the source states one — the concept never invents a time, so an LLM extracting "delivery by March 15" produces a date with no time, while a ticket's "7 Jul 2026, 15:40" keeps the time (and its UTC offset, when stated). It renders as ISO 8601 truncated to the stated precision (`2026-07-07`, or `2026-07-07T15:40:00+02:00`) when injected into a prompt. As a `PipeLLM` output, `output = "Date"` makes the model return the two-field structure:

```toml
[pipe.extract_departure]
type = "PipeLLM"
description = "Extract the scheduled departure from a ticket"
inputs = { ticket = "Ticket" }
output = "Date"
prompt = "Extract the scheduled departure from this ticket: $ticket"
```

As a pipeline input, a top-level TOML date or datetime literal maps to `Date` directly (`departure = 2026-07-07T15:40:00+02:00`); read it from a Python caller via `pipe_output.main_stuff_as_date`.

### TimeContent

Represents a time of day, as precise as its source states — never attached to an invented date:

```python
class TimeContent(StuffContent):
    time: datetime.time
```

The UTC offset is kept on the `time` when the source states one, exactly as `Date` handles its optional time. It renders as ISO 8601 (`15:40:00`, or `15:40:00+02:00`) when injected into a prompt. As a pipeline input, a top-level TOML time-of-day literal maps to `Time` directly (`opening = 09:00:00`).

**Use for:** Opening hours, schedules, times of day with no specific date.

**Use for:** Issue dates, due dates, dates of birth, departures, effective/termination dates — any date found on a document. For a date value without any date attached (a bare time of day), degrade to `Text`.

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

### HtmlContent

Represents HTML content with styling:

```python
class HtmlContent(StuffContent):
    inner_html: str
    css_class: str | None = None
```

**Fields:**

- `inner_html`: The inner HTML of the content
- `css_class`: The CSS class applied to the wrapping element, optional — content that needs no wrapper simply omits it, and the HTML rendering then returns the raw `inner_html` with no wrapping `div`

**Use for:** Rendered HTML fragments, styled content blocks, HTML-based reports.

### SearchResultContent

Represents the result of a web search query. Produced by `PipeSearch`:

```python
class SearchResultContent(StuffContent):
    answer: str
    sources: list[DocumentContent] = Field(default_factory=empty_list_factory_of(DocumentContent))
```

**Fields:**

- `answer`: The synthesized answer text from the search
- `sources`: A list of `DocumentContent` source citations (each with `url`, `title`, and `snippet`)

**Use for:** Web search results, research findings, information retrieval with citations.

### CompositeContent

An untyped named composition of contents. Produced by `PipeParallel` when its output is `Composite`:

```python
class CompositeContent(StuffContent):
    model_config = ConfigDict(extra="allow")
```

Each named sub-content is a top-level field of the composite — there is no wrapper key, so the serialized shape matches what a bespoke structured concept with the same field names would produce.

**Use for:** Combining parallel branch results without declaring a bespoke concept.

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
prompt = """
Analyze this document and provide a summary:

@document
"""
```

### In Pipe Outputs

```toml
[pipe.process_image]
type = "PipeLLM"
description = "Describe an image"
inputs = { photo = "Image" }
output = "Text"
prompt = "Describe what you see in this image: $photo"
```

### With Page Content

The `Page` concept is particularly useful with `PipeExtract`:

```toml
[pipe.extract_pages]
type = "PipeExtract"
description = "Extract content from a document"
inputs = { document = "Document" }
output = "Page[]"
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
prompt = """
Summarize this content:

@content
"""
```

### Document Extraction

```toml
[pipe.extract_pages]
type = "PipeExtract"
description = "Extract content from a document"
inputs = { document = "Document" }
output = "Page[]"

[pipe.analyze_pages]
type = "PipeLLM"
description = "Analyze pages"
inputs = { pages = "Page[]" }
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
prompt = """
Given this context: $context

Analyze this image: $image
"""
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
- [MTHDS Language Tutorial](../../get-started/mthds-language-tutorial.md) - Use native concepts in pipelines

