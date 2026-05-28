# PipeExtract

The `PipeExtract` operator extracts structured content from documents. For PDFs and images, it performs OCR to extract text, embedded images, and full-page renderings. For web pages, it fetches and extracts page content.

## How it works

`PipeExtract` takes a single input, which must be a `Document` or an `Image` (or a concept that refines one of them). The document URL can be a file path, a storage URL, or a web page URL. It processes the input and produces a list of `PageContent` objects. Each `PageContent` object encapsulates all the information extracted from one page.

The output is always a list. If the input is a single image, the output still contains one `Page` item.

### The `PageContent` Structure

The `PageContent` object has the following structure:

-   `text_and_images`: Contains the main extracted content.
    -   `text`: The recognized text from the page as a `TextContent`.
    -   `images`: A list of any images found embedded within the page.
-   `page_view`: An `ImageContent` object representing a full visual rendering of the page.

## Configuration

`PipeExtract` is configured in your pipeline's `.mthds` file.

### Extraction Models and Backend System

PipeExtract uses the unified inference backend system to manage extraction models. This means you can:

- Use different extraction providers (Mistral OCR, Linkup Fetch, local PDF extraction via internal backend, etc.)
- Configure extraction models through the same backend system as LLMs and image generation models
- Use extraction presets for consistent configurations across your pipelines
- Route extraction requests to different backends based on your routing profile

Common extraction model handles:

- `mistral-ocr`: Mistral's OCR model for high-quality text and image extraction
- `pypdfium2-extract-pdf`: Local PDF text extraction (no API calls required)
- `linkup-fetch`: Web page content extraction from URLs

Common model aliases:

- `@default-extract-web-page`: Default for web page extraction (Linkup Fetch)
- `@default-extract-document`: Default for document extraction (Azure Document Intelligence)
- `@default-text-from-pdf`: Fast local PDF text extraction (pypdfium2)

Extraction presets are defined in your model deck configuration and can include parameters like `max_nb_images` and `image_min_size`.

### MTHDS Parameters

| Parameter                   | Type    | Description                                                                                                                              | Required |
| --------------------------- | ------- | ---------------------------------------------------------------------------------------------------------------------------------------- | -------- |
| `type`                      | string  | The type of the pipe: `PipeExtract`                                                                          | Yes      |
| `description`               | string  | A description of the extraction operation.                                                                   | Yes      |
| `inputs`                    | Fixed  | The value must be of concept `Document` or `Image` (or a concept that refines one of them). For web page extraction, the Document holds a web URL.                                                     | Yes       |
| `output`                    | string  | The output concept produced by the extraction operation. Use `Page[]`.                                  | Yes      |
| `max_page_images`           | integer or null | Maximum number of images to extract from pages: `null` (or omit) for unlimited, `0` for no images, or a positive integer to limit. Defaults to the value in your Extract model preset. | No       |
| `page_views`                | boolean | If `true`, a high-fidelity image of each page will be included in the `page_view` field. Defaults to `false`.                              | No       |
| `page_views_dpi`            | integer | The resolution (in Dots Per Inch) for the generated page views when processing a PDF. Defaults to `150`.                                 | No       |
| `page_image_captions`       | boolean | If `true`, the OCR service may attempt to generate captions for the images found. *Note: This feature depends on the OCR provider.*        | No       |
| `render_js`                 | boolean | For web-page extraction: if `true`, the extraction backend renders JavaScript before fetching the page content. Defaults to `false`. *Note: Only honored by backends that support headless rendering.* | No       |
| `include_raw_html`          | boolean | For web-page extraction: if `true`, the extracted `Page` populates its `raw_html` field with the fetched page's HTML. Defaults to `false`. | No       |
| `model`                       | string  | The Extract model choice by name, setting, or preset to use (e.g., `"mistral-document-ai-2505"`, `"@default-extract-document"`). Defaults to the model specified in the global config. | No       |

### Example: Processing a PDF

This example defines a pipe that takes a PDF, extracts text and full-page images, and outputs them as a list of pages.

```toml
[concept]
ScannedDocument = "A document that has been scanned as a PDF"

[concept.ExtractedPages]
description = "A list of pages extracted from a document by OCR"
refines = "Page"

[pipe.extract_text_from_document]
type = "PipeExtract"
description = "Extract text from a scanned document"
inputs = { document = "ScannedDocument" }
output = "Page[]"
page_views = true
page_views_dpi = 200
```

The output of `PipeExtract` must be `Page[]`.

To use this pipe, first load a PDF into the `ScannedDocument` concept. After the pipe runs, the output contains a list of `PageContent` objects, where each object has the extracted text and a 200 DPI image of the corresponding page.

### Example: Extracting a Web Page

This example defines a pipe that extracts content from a web page URL.

```toml
[pipe.extract_web_article]
type        = "PipeExtract"
description = "Extract content from a web page"
inputs      = { article_url = "Document" }
output      = "Page[]"
model       = "@default-extract-web-page"
```

Pass a web URL as the `document_uri` when running the pipe. PipeExtract fetches the page and extracts its content into `Page` objects, following the same pattern as document extraction.

## Related Documentation

- [Generic Document Extraction Example](../../../cookbook/extract-generic.md) - Extract markdown from complex PDFs using vision
- [Invoice Extraction Example](../../../cookbook/extract-invoice.md) - Complete invoice processing pipeline
- [Document Extraction Feature](../../../features/document-extraction.md) - Overview of document extraction capabilities
