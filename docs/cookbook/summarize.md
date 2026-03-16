---
title: "Summarize Example"
description: "Summarize text using a multi-step pipeline that extracts topics, summarizes each, and combines them into a final summary."
---

# Example: Summarize

This example demonstrates two approaches to summarizing text: a direct structured summary and a multi-step topic-based summarization pipeline.

## Get the code

[![GitHub](https://img.shields.io/badge/View_on_GitHub-5a0dad?logo=github&logoColor=white&style=flat)](https://github.com/Pipelex/pipelex-cookbook/blob/main/examples/a_quick_start/summarize.mthds)

## What it demonstrates

- Defining custom concepts with inline structures (`StructuredSummary`)
- Multi-step `PipeSequence` with intermediate results
- Batching over a list of topics (`batch_over` / `batch_as`)
- Two pipes producing different outputs from the same input

## The Method: `summarize.mthds`

### Concepts

The method defines a `StructuredSummary` concept with fields for the summary, an abstract, and a list of main concepts:

```toml
domain        = "summarize"
description   = "Example of summarizing text by topics."
system_prompt = "You are an expert at summarizing text."

[concept]
Topic   = "A topic a text deals with."
Summary = "A concise rewriting of a dense text."

[concept.StructuredSummary]
description = "A summary with a structured output."

[concept.StructuredSummary.structure]
summary       = { type = "text", description = "Summary of the text, super clear and factual", required = true }
abstract      = { type = "text", description = "Abstract of the summary 1 short sentences", required = true }
main_concepts = { type = "list", item_type = "text", description = "Array of main concepts tackled in the text" }
```

### Multi-step pipeline

The `summarize_by_steps` pipeline breaks summarization into three stages: extract topics, summarize each topic individually (batched), then combine all summaries:

```toml
[pipe.summarize_by_steps]
type = "PipeSequence"
description = "Summarize text by steps: extract topics, summarize for each topic, summarize from summaries."
inputs = { text = "Text" }
output = "Summary"
steps = [
  { pipe = "extract_topics", result = "topics" },
  { pipe = "summarize_topic", batch_over = "topics", batch_as = "topic", result = "summarized_topics" },
  { pipe = "summarize_from_summaries", result = "summary" },
]
```

Each topic is summarized independently using `batch_over`, and the final step merges everything into a single cohesive summary.

## How to run

**Direct structured summary:**

```bash
pipelex run bundle examples/a_quick_start/summarize.mthds \
  --pipe summarize_with_structure \
  -i examples/a_quick_start/inputs.json
```

**Multi-step topic-based summary:**

```bash
pipelex run bundle examples/a_quick_start/summarize.mthds \
  --pipe summarize_by_steps \
  -i examples/a_quick_start/inputs.json
```

## Related Documentation

- [PipeSequence Controller](../building-methods/pipes/pipe-controllers/PipeSequence.md) - Chain pipes into sequential workflows
- [PipeLLM Operator](../building-methods/pipes/pipe-operators/PipeLLM.md) - The core operator for LLM interactions
- [Understanding Multiplicity](../building-methods/pipes/understanding-multiplicity.md) - How batching works
