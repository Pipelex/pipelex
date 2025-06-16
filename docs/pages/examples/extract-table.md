# Example: Table Extraction from Image

This example shows how to extract a table from an image and convert it into a structured HTML format. This is a common requirement when dealing with scanned documents or reports where data is presented in tabular form.

## Get the code

[**➡️ View on GitHub: examples/extract_table.py**](https://github.com/Pipelex/pipelex-cookbook/blob/main/examples/extract_table.py)

## The Pipeline Explained

The pipeline `extract_html_table_and_review` takes an image of a table, processes it, and returns an `HtmlTable` object.

```python
async def extract_table(table_screenshot: str) -> HtmlTable:
    working_memory = WorkingMemoryFactory.make_from_image(
        image_url=table_screenshot,
        concept_str="tables.TableScreenshot",
        name="table_screenshot",
    )
    pipe_output, _ = await execute_pipeline(
        pipe_code="extract_html_table_and_review",
        working_memory=working_memory,
    )
    html_table = pipe_output.main_stuff_as(content_type=HtmlTable)
    return html_table
```

This is another example of Pipelex's multi-modal capabilities, turning visual information into structured data. 