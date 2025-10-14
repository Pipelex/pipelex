# Example: DPE Extraction

This example demonstrates how to extract information from a French "Diagnostic de Performance Énergétique" (DPE) document. This is a specialized document, and the pipeline is tailored to its specific structure.

## Get the code

[**➡️ View on GitHub: examples/extract_dpe.py**](https://github.com/Pipelex/pipelex-cookbook/blob/main/examples/extract_dpe.py)

## The Pipeline Explained

The pipeline `power_extractor_dpe` is designed to recognize and extract the key information from a DPE document. The result is a structured `Dpe` object.

```python
async def extract_dpe(pdf_url: str) -> Dpe:
    pipe_output = await execute_pipeline(
        pipe_code="power_extractor_dpe",
        input_memory={
            "document": PDFContent(url=pdf_url),
        },
    )
    working_memory = pipe_output.working_memory
    dpe: Dpe = working_memory.get_list_stuff_first_item_as(name="dpe", item_type=Dpe)
    return dpe
```

This example shows how Pipelex can be used for very specific document extraction tasks by creating custom pipelines and data models.

## The Data Structure: `Dpe` Model

The pipeline extracts a `Dpe` object, which is structured to hold the specific information found in a French "Diagnostic de Performance Énergétique". It even uses a custom `IndexScale` enum for the energy efficiency classes.

```python
class IndexScale(StrEnum):
    A = "A"
    B = "B"
    C = "C"
    D = "D"
    E = "E"
    F = "F"
    G = "G"


class Dpe(StructuredContent):
    address: Optional[str] = None
    date_of_issue: Optional[datetime] = None
    date_of_expiration: Optional[datetime] = None
    energy_efficiency_class: Optional[IndexScale] = None
    per_year_per_m2_consumption: Optional[float] = None
    co2_emission_class: Optional[IndexScale] = None
    per_year_per_m2_co2_emissions: Optional[float] = None
    yearly_energy_costs: Optional[float] = None
```

## The Pipeline Definition: `extract_dpe.plx`

The pipeline uses a `PipeLLM` with a very specific prompt to extract the information from the document. The combination of the image and the OCR text allows the LLM to accurately capture all the details.

```plx
[pipe.write_markdown_from_page_content_dpe]
type = "PipeLLM"
description = "Write markdown from page content of a 'Diagnostic de Performance Energetique'"
inputs = { "page_content.page_view" = "Image", page_content = "Page" }
output = "Dpe"
model = "llm_for_img_to_text"
structuring_method = "preliminary_text"
system_prompt = """You are a multimodal LLM, expert at converting images into perfect markdown."""
prompt = """
You are given an image of a French 'Diagnostic de Performance Energetique': $page_content.page_view
Your role is to convert the image into perfect markdown.

To help you do so, you are given the text extracted from the page by an OCR model.
@page_content.text_and_images.text.text

- It is very important that you collect every element, especially if they are related to the energy performance of the building.
- Pay attention to all the pieces of information that may be included in images, graphs, charts, or tables.
- We value letters like "A, B, C, D, E, F, G" as they are energy performance classes.
- Pay attention to the text alignment, it might have been misaligned by the OCR.
- The OCR extraction may be highly incomplete. It is your job to complete the text and add the missing information using the image.
- Output only the markdown, nothing else. No need for "```markdown" or "```".
- You can use HTML if it helps you.
- You can use tables if it is relevant.
"""
```
This is a great example of how to create a highly specialized extraction pipeline by combining a custom data model with a detailed, guiding prompt. 