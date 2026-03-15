---
title: "Advisory Board Example"
description: "Solve complex business problems through multi-board consultation — a Pipelex pipeline that consults specialized advisory boards and synthesizes strategic recommendations."
---

# Example: Advisory Board

!!! warning "Work in Progress"
    This example is under active development and may change.

This example solves complex business problems by consulting multiple specialized advisory boards (Executive, Product, Engineering, Marketing, etc.), analyzing consensus and conflicts across their responses, and producing a comprehensive strategic report.

## Get the code

[![GitHub](https://img.shields.io/badge/View_on_GitHub-5a0dad?logo=github&logoColor=white&style=flat)](https://github.com/Pipelex/pipelex-cookbook/blob/main/examples/wip/advisory_board/bundle.mthds)

## What it demonstrates

- Complex concept hierarchy (BusinessProblem, AdvisoryBoard, BoardResponse, ConsensusItem, ConflictItem, StrategicReport, etc.)
- Multi-board consultation pattern with batching
- Consensus and conflict analysis across expert opinions
- Multi-file method bundle (main `bundle.mthds` + `presentation.mthds`)
- 16 specialized advisory boards to choose from

## The Method: `bundle.mthds`

### Pipeline overview

```toml
[pipe.master_advisory_orchestrator]
type = "PipeSequence"
inputs = { user_input = "Text" }
output = "presentation.MarkdownReport"
steps = [
  { pipe = "classify_business_problem", result = "business_problem" },
  { pipe = "select_advisory_boards", result = "selected_advisory_boards" },
  { pipe = "consult_board", batch_over = "selected_advisory_boards",
    batch_as = "advisory_board", result = "board_consultations" },
  { pipe = "analyze_board_responses", result = "response_analysis" },
  { pipe = "generate_strategic_report", result = "strategic_report" },
  { pipe = "present_as_markdown", result = "strategic_report_markdown" },
]
```

The pipeline:

1. **Classifies** the business problem into a structured `BusinessProblem` (category, urgency, stakeholders)
2. **Selects** 5-10 relevant advisory boards from 16 available
3. **Consults** each board in parallel (batched) for domain-specific recommendations
4. **Analyzes** all responses to find consensus, conflicts, and unique insights
5. **Generates** a comprehensive strategic report with implementation roadmap and risk assessment
6. **Presents** the report as formatted markdown

## How to run

```bash
pipelex run bundle examples/wip/advisory_board/bundle.mthds \
  -i examples/wip/advisory_board/inputs.json
```

## Related Documentation

- [PipeSequence Controller](../building-methods/pipes/pipe-controllers/PipeSequence.md) - Chain pipes into sequential workflows
- [PipeLLM Operator](../building-methods/pipes/pipe-operators/PipeLLM.md) - The core operator for LLM interactions
- [Understanding Multiplicity](../building-methods/pipes/understanding-multiplicity.md) - How batching works
