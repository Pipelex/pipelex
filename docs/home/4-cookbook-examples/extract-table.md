# Example: Table Extraction from Image

This example shows how to extract a table from an image and convert it into a structured HTML format. This is a common requirement when dealing with scanned documents or reports where data is presented in tabular form.

## Get the code

[**➡️ View on GitHub: examples/extract_table.py**](https://github.com/Pipelex/pipelex-cookbook/blob/main/examples/extract_table.py)

## The Pipeline Explained

The pipeline `extract_html_table_and_review` takes an image of a table, processes it, and returns an `HtmlTable` object.

```python
async def extract_table(table_screenshot: str) -> HtmlTable:
    pipe_output = await execute_pipeline(
        pipe_code="extract_html_table_and_review",
        inputs={
            "table_screenshot": {
                "concept": "tables.TableScreenshot",
                "content": ImageContent(url=table_screenshot),
            }
        },
    )
    html_table = pipe_output.main_stuff_as(content_type=HtmlTable)
    return html_table
```

This is another example of Pipelex's multi-modal capabilities, turning visual information into structured data.

## The Data Structure: `HtmlTable` Model

The pipeline outputs an `HtmlTable` object. This is a great example of a "smart" data model. It uses a `pydantic.model_validator` to parse the generated HTML with BeautifulSoup and validate its structure, ensuring the LLM has produced valid and well-formed HTML.

```python
class HtmlTable(StructuredContent):
    title: str
    inner_html_table: str
    allowed_tags: ClassVar[set[str]] = { "br", "table", "thead", "tbody", "tr", "th", "td" }

    @model_validator(mode="after")
    def validate_html_table(self) -> Self:
        soup = BeautifulSoup(self.inner_html_table, "html.parser")
        # Check if there's exactly one table element
        tables = soup.find_all("table")
        if len(tables) != 1:
            raise ValueError(f"HTML must contain exactly one table element...")
        
        # Validate that only allowed table-related tags are present
        all_tags = {tag.name for tag in soup.find_all()}
        invalid_tags = all_tags - self.allowed_tags
        if invalid_tags:
            raise ValueError(f"Invalid HTML tags found: {invalid_tags}")
        
        # ... more validation
        return self
```

## The Pipeline Definition: `table.plx`

The pipeline uses a two-step "extract and review" pattern. The first pipe does the initial extraction, and the second pipe reviews the generated HTML against the original image to correct any errors. This is a powerful pattern for increasing the reliability of LLM outputs.

```plx
[pipe.extract_html_table_and_review]
type = "PipeSequence"
description = "Get an HTML table and review it"
inputs = { table_screenshot = "TableScreenshot" }
output = "HtmlTable"
steps = [
    # First, do an initial extraction of the table from the image
    { pipe = "extract_html_table_from_image", result = "html_table" },
    # Then, ask an LLM to review the extracted table against the image and correct it
    { pipe = "review_html_table", result = "reviewed_html_table" },
]

[pipe.review_html_table]
type = "PipeLLM"
description = "Review an HTML table"
inputs = { table_screenshot = "TableScreenshot", html_table = "HtmlTable" }
output = "HtmlTable"
prompt = """
Your role is to correct an html_table to make sure that it matches the one in the provided image: $table_screenshot

@html_table

Pay attention to the text and formatting (color, borders, ...).
Rewrite the entire html table with your potential corrections.
Make sure you do not forget any text.
"""
```
This self-correction pattern is a key technique for building robust and reliable AI workflows with Pipelex. 