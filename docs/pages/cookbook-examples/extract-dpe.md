# Example: DPE Extraction

This example demonstrates how to extract information from a French "Diagnostic de Performance Énergétique" (DPE) document. This is a specialized document, and the pipeline is tailored to its specific structure.

## Get the code

[**➡️ View on GitHub: examples/extract_dpe.py**](https://github.com/Pipelex/pipelex-cookbook/blob/main/examples/extract_dpe.py)

## The Pipeline Explained

The pipeline `power_extractor_dpe` is designed to recognize and extract the key information from a DPE document. The result is a structured `Dpe` object.

```python
async def extract_dpe(pdf_url: str) -> Dpe:
    working_memory = WorkingMemoryFactory.make_from_pdf(
        pdf_url=pdf_url,
        concept_string="PDF",
        name="pdf",
    )
    pipe_output = await execute_pipeline(
        pipe_code="power_extractor_dpe",
        working_memory=working_memory,
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
definition = "Write markdown from page content of a 'Diagnostic de Performance Energetique'"
inputs = { page_content = "Page" }
output = "Dpe" # The output is structured as a Dpe object
llm = "llm_for_img_to_text"
structuring_method = "preliminary_text"
system_prompt = """You are a multimodal LLM, expert in converting images into perfect markdown."""
prompt_template = """
You are given an image of a French 'Diagnostic de Performance Energetique'.
Your role is to convert the image into perfect markdown.

To help you do so, you are given the text extracted from the page by an OCR model.
@page_content.text_and_images.text.text

- It is very important that you collect every element, especially if they are related to the energy performance of the building.
- We value letters like "A, B, C, D, E, F, G" as they are energy performance classes.
# ... (prompt continues)
"""
```
This is a great example of how to create a highly specialized extraction pipeline by combining a custom data model with a detailed, guiding prompt. 