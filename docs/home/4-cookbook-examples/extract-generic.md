# Example: Generic Document Extraction

This example demonstrates a powerful and generic pipeline for extracting content from complex PDF documents. It can handle documents that contain both text and images, and it merges the extracted content into a single, coherent output.

## Get the code

[**➡️ View on GitHub: examples/extract_generic.py**](https://github.com/Pipelex/pipelex-cookbook/blob/main/examples/extract_generic.py)

## The Pipeline Explained

The `power_extractor` pipeline is at the heart of this example. After its execution, a custom function `merge_markdown_and_images` is used to combine the text (converted to Markdown) and the images from all pages.

```python
async def extract_generic(pdf_url: str) -> TextAndImagesContent:
    pipe_output = await execute_pipeline(
        pipe_code="power_extractor",
        inputs={
            "document": PDFContent(url=pdf_url),
        },
    )
    working_memory = pipe_output.working_memory
    markdown_and_images: TextAndImagesContent = merge_markdown_and_images(working_memory)
    return markdown_and_images
```

The `merge_markdown_and_images` function is a great example of how you can add your own Python code to a Pipelex workflow to perform custom processing.

```python
def merge_markdown_and_images(working_memory: WorkingMemory) -> TextAndImagesContent:
    # Pages extracted from the PDF by PipeOCR
    page_contents_list = working_memory.get_stuff_as_list(name="page_contents", item_type=PageContent)
    # Markdown text extracted from the Pages by PipeLLM
    page_markdown_list = working_memory.get_stuff_as_list(name="markdowns", item_type=TextContent)

    # ... (check for length equality)

    # Concatenate the markdown text
    concatenated_markdown_text: str = "\n".join([page_markdown.text for page_markdown in page_markdown_list.items])

    # Aggregate the images from the page contents
    image_contents: List[ImageContent] = []
    for page_content in page_contents_list.items:
        if page_content.text_and_images.images:
            image_contents.extend(page_content.text_and_images.images)

    return TextAndImagesContent(
        text=TextContent(text=concatenated_markdown_text),
        images=image_contents,
    )
```

This example shows the flexibility of Pipelex in handling complex, multi-modal documents and allowing for custom logic. 