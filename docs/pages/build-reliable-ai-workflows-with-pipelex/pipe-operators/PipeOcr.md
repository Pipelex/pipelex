# PipeOcr

The `PipeOcr` operator performs Optical Character Recognition (OCR) on images and PDF documents. It extracts text, embedded images, and provides full-page renderings.

## How it works

`PipeOcr` takes a single input, which must be either an `Image` or a `Pdf`. It processes the document page by page and produces a list of `PageContent` objects. Each `PageContent` object encapsulates all the information extracted from a single page.

The output is always a list, even if the input is a single image (in which case the list will contain just one item).

### The `PageContent` Structure

The `PageContent` object has the following structure:

-   `text_and_images`: Contains the main extracted content.
    -   `text`: The recognized text from the page as a `TextContent`.
    -   `images`: A list of any images found embedded within the page.
-   `page_view`: An `ImageContent` object representing a full visual rendering of the page.

## Configuration

`PipeOcr` is configured in your pipeline's `.plx` file.

### PLX Parameters

| Parameter                   | Type    | Description                                                                                                                              | Required |
| --------------------------- | ------- | ---------------------------------------------------------------------------------------------------------------------------------------- | -------- |
| `type`                      | string  | The type of the pipe: `PipeOcr`                                                                          | Yes      |
| `definition`               | string  | A description of the OCR operation.                                                                   | Yes      |
| `inputs`                    | Fixed  | The input for the PipeOcr is the key `ocr_input` and the value is either of concept `Image` or `Pdf`.                                                     | Yes       |
| `output`                    | string  | The output concept produced by the OCR operation.                                                | Yes      |
| `page_images`               | boolean | If `true`, any images found within the document pages will be extracted and included in the output. Defaults to `false`.                 | No       |
| `page_views`                | boolean | If `true`, a high-fidelity image of each page will be included in the `page_view` field. Defaults to `false`.                              | No       |
| `page_views_dpi`            | integer | The resolution (in Dots Per Inch) for the generated page views when processing a PDF. Defaults to `150`.                                 | No       |
| `page_image_captions`       | boolean | If `true`, the OCR service may attempt to generate captions for the images found. *Note: This feature depends on the OCR provider.*        | No       |

### Example: Processing a PDF

This example defines a pipe that takes a PDF, extracts text and full-page images, and outputs them as a list of pages.

```plx
[concept]
ScannedDocument = "A document that has been scanned as a PDF"

[concept.ExtractedPages]
definition = "A list of pages extracted from a document by OCR"
refines = "Page"

[pipe.extract_text_from_document]
type = "PipeOcr"
definition = "Extract text from a scanned document"
inputs = { ocr_input = "ScannedDocument" }
output = "Page"
page_views = true
page_views_dpi = 200
```

The output of the PipeOcr must be exactly the native `Page` concept.

To use this pipe, you would first need to load a PDF into the `ScannedDocument` concept. After the pipe runs, the `ExtractedPages` concept will contain a list of `PageContent` objects, where each object has the extracted text and a 200 DPI image of the corresponding page.
