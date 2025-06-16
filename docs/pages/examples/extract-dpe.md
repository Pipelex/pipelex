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
        concept_str="PDF",
        name="pdf",
    )
    pipe_output, _ = await execute_pipeline(
        pipe_code="power_extractor_dpe",
        working_memory=working_memory,
    )
    working_memory = pipe_output.working_memory
    dpe: Dpe = working_memory.get_list_stuff_first_item_as(name="dpe", item_type=Dpe)
    return dpe
```

This example shows how Pipelex can be used for very specific document extraction tasks by creating custom pipelines and data models. 