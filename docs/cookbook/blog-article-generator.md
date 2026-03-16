---
title: "Blog Article Generator Example"
description: "Generate SEO-optimized blog articles from a structured request using a two-step Pipelex pipeline."
---

# Example: Blog Article Generator

!!! warning "Work in Progress"
    This example is under active development and may change.

This example generates complete SEO-optimized blog articles from a structured request. It uses a two-step pipeline: create an outline, then write the full article.

## Get the code

[![GitHub](https://img.shields.io/badge/View_on_GitHub-5a0dad?logo=github&logoColor=white&style=flat)](https://github.com/Pipelex/pipelex-cookbook/blob/main/examples/wip/blog_article_generator/bundle.mthds)

## What it demonstrates

- Structured input concept (`BlogArticleRequest` with topic, audience, tone, length)
- Two-step content generation: outline then write
- Constrained choices for tone and length fields

## The Method: `bundle.mthds`

### Input concept

```toml
[concept.BlogArticleRequest]
description = "Structured request describing the blog article to generate"

[concept.BlogArticleRequest.structure]
text = { type = "text", description = "Free-form instruction for the article", required = true }
topic = { type = "text", description = "The main topic of the blog article", required = true }
audience = { type = "text", description = "Target audience for the article", required = true }
tone = { type = "text", description = "Writing tone", choices = [
  "Casual", "Professional", "Humorous", "Academic",
], required = true }
length = { type = "text", description = "Desired article length", choices = [
  "Short", "Medium", "Long",
], required = true }
```

### Pipeline

```toml
[pipe.generate_blog_article]
type = "PipeSequence"
inputs = { user_prompt = "BlogArticleRequest" }
output = "BlogArticle"
steps = [
  { pipe = "create_outline", result = "outline" },
  { pipe = "write_article", result = "article" },
]
```

## How to run

```bash
pipelex run bundle examples/wip/blog_article_generator/bundle.mthds \
  -i examples/wip/blog_article_generator/inputs.json
```

## Related Documentation

- [PipeLLM Operator](../building-methods/pipes/pipe-operators/PipeLLM.md) - The core operator for LLM interactions
- [PipeSequence Controller](../building-methods/pipes/pipe-controllers/PipeSequence.md) - Chain pipes into sequential workflows
