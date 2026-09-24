# Example: DPE Extraction

This example extracts information from French "Diagnostic de Performance Energetique" (DPE) documents. It uses a three-step pipeline: extract pages, convert each to markdown using vision, then conclude the DPE details from the combined markdown.

## Get the code

[![GitHub](https://img.shields.io/badge/View_on_GitHub-5a0dad?logo=github&logoColor=white&style=flat)](https://github.com/Pipelex/pipelex-cookbook/blob/main/examples/b_basics/document_extract/extract_dpe/bundle.mthds)

## What it demonstrates

- Custom structured concept with constrained choices (energy efficiency classes A-G)
- Three-step extraction: pages, markdown per page, then conclude
- Vision-based extraction focused on specific document elements (energy classes, graphs, tables)
- Using shared method packages for page extraction

## The Method: `bundle.mthds`

### DPE concept

```toml
[concept.Dpe]
description = "A diagnostic of the energy performance of a building"

[concept.Dpe.structure]
address                       = { type = "text", description = "The address of the building" }
date_of_issue                 = { type = "date", description = "The date the DPE was issued" }
date_of_expiration            = { type = "date", description = "The expiration date of the DPE" }
energy_efficiency_class       = { type = "text", description = "The energy efficiency class",
                                  choices = ["A", "B", "C", "D", "E", "F", "G"] }
per_year_per_m2_consumption   = { type = "number", description = "Energy consumption per year per m2" }
co2_emission_class            = { type = "text", description = "The CO2 emission class",
                                  choices = ["A", "B", "C", "D", "E", "F", "G"] }
per_year_per_m2_co2_emissions = { type = "number", description = "CO2 emissions per year per m2" }
yearly_energy_costs           = { type = "number", description = "Yearly energy costs" }
```

### Pipeline

```toml
[pipe.power_extractor_dpe]
type = "PipeSequence"
inputs = { document = "Document" }
output = "Dpe"
steps = [
  { pipe = "github.com/Pipelex/methods/documents->documents.extract_page_contents_and_views",
    result = "page_contents" },
  { pipe = "write_markdown_from_page_content_dpe",
    batch_over = "page_contents", batch_as = "page_content",
    result = "dpe_pages" },
  { pipe = "conclude_dpe", result = "dpe" },
]
```

The final `conclude_dpe` step takes all the markdown pages and produces a single structured `Dpe` object.

## How to run

```bash
pipelex run bundle examples/b_basics/document_extract/extract_dpe/bundle.mthds \
  -i examples/b_basics/document_extract/extract_dpe/inputs.json
```

## Related Documentation

- [PipeLLM Operator](../building-methods/pipes/pipe-operators/PipeLLM.md) - The core operator for LLM interactions
- [Document Extraction](../features/document-extraction.md) - Overview of document extraction capabilities
