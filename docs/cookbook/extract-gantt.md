---
title: "Gantt Chart Extraction Example"
description: "Extract tasks, dates, and dependencies from Gantt chart images using a step-by-step divide-and-conquer Pipelex pipeline."
---

# Example: Gantt Chart Extraction

This example extracts structured information from Gantt chart images: timescale, task names, task details (dates, dependencies), and milestones. It uses a "divide and conquer" approach where each aspect is extracted separately.

## Get the code

[![GitHub](https://img.shields.io/badge/View_on_GitHub-5a0dad?logo=github&logoColor=white&style=flat)](https://github.com/Pipelex/pipelex-cookbook/blob/main/examples/b_basics/document_extract/extract_gantt/bundle.mthds)

## What it demonstrates

- Divide-and-conquer extraction: timescale, task names, task details, then assemble
- Batching over task names to extract details for each independently
- Vision-based extraction using `$vision-diagram` model
- Rich structured output (`GanttChart` with `GanttTaskDetails` and `Milestone` lists)
- Two alternative approaches: step-by-step vs. direct one-shot extraction

## The Method: `bundle.mthds`

### Pipeline

```toml
[pipe.extract_gantt_by_steps]
type = "PipeSequence"
description = "Extract all details from a gantt chart"
inputs = { gantt_chart_image = "GanttChartImage" }
output = "GanttChart"
steps = [
    { pipe = "extract_gantt_timescale", result = "gantt_timescale" },
    { pipe = "extract_gantt_task_names", result = "gantt_task_names" },
    { pipe = "extract_details_of_task", batch_as = "gantt_task_name",
      result = "details_of_all_tasks" },
    { pipe = "gather_in_a_gantt_chart", result = "gantt_chart" },
]
```

Each task's details are extracted individually using the chart image, the timescale context, and the specific task name — making each extraction focused and accurate.

The bundle also includes a `transcript_gantt_direct` pipe for one-shot extraction to markdown, useful for simpler charts.

## How to run

```bash
pipelex run bundle examples/b_basics/document_extract/extract_gantt/bundle.mthds \
  -i examples/b_basics/document_extract/extract_gantt/inputs.json
```

## Related Documentation

- [PipeLLM Operator](../building-methods/pipes/pipe-operators/PipeLLM.md) - The core operator for LLM interactions
- [PipeSequence Controller](../building-methods/pipes/pipe-controllers/PipeSequence.md) - Chain pipes into sequential workflows
