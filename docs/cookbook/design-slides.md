---
title: "Design Slides Example"
description: "Generate multiple slide design proposals from a brief — including themes, visual mockups, and an HTML report — using Pipelex."
---

# Example: Design Slides

This example takes a slide design brief and generates multiple themed design proposals, complete with visual mockups and an HTML report comparing them.

## Get the code

[![GitHub](https://img.shields.io/badge/View_on_GitHub-5a0dad?logo=github&logoColor=white&style=flat)](https://github.com/Pipelex/pipelex-cookbook/blob/main/examples/b_basics/generate_visuals/design_slides/bundle.mthds)

## What it demonstrates

- Rich concept hierarchy (nested structures: `Theme` contains `ColorPalette`, `Typography`, `LayoutSettings`, `StyleSettings`)
- `nb_output` parameter to generate multiple results from a single pipe
- `PipeImgGen` for generating visual mockup images
- `PipeCompose` with an HTML template for report rendering
- Multi-step creative pipeline: polish brief, generate themes, render visuals, compose report

## The Method: `bundle.mthds`

### Key concepts

The method defines a deep hierarchy of design concepts:

```toml
[concept.SlideDesignBrief]
description = "Client brief for slide deck design"

[concept.SlideDesignBrief.structure]
topic = { type = "text", description = "The main topic or subject of the presentation", required = true }
brand_guidelines = { type = "text", description = "The client's brand guidelines", required = false }
tone = { type = "text", description = "The tone of the presentation", choices = [
  "formal", "playful", "innovative", "trustworthy", "artsy",
], required = false }
# ... goal, audience fields
```

```toml
[concept.Theme]
description = "Complete presentation theme with colors, typography, layout, and style"

[concept.Theme.structure]
name       = { type = "text", description = "Theme name identifier", required = true }
colors     = { type = "concept", concept_ref = "ColorPalette", description = "Color palette for the theme", required = true }
typography = { type = "concept", concept_ref = "Typography", description = "Typography settings", required = true }
layout     = { type = "concept", concept_ref = "LayoutSettings", description = "Layout configuration", required = true }
style      = { type = "concept", concept_ref = "StyleSettings", description = "Visual style settings", required = true }
```

### Pipeline

```toml
[pipe.generate_design_proposals_from_rough_brief]
type = "PipeSequence"
description = "Transform a design brief into multiple themes with visual mockups and HTML report"
inputs = { brief = "SlideDesignBrief" }
output = "Html"
steps = [
  { pipe = "polish_brief", result = "polished_brief" },
  { pipe = "generate_multiple_themes", nb_output = 3, result = "themes" },
  { pipe = "render_visual_proposal", batch_over = "themes", batch_as = "theme", result = "design_proposals" },
  { pipe = "compose_proposals_report", result = "proposals_report" },
]
```

The `nb_output = 3` parameter tells `generate_multiple_themes` to produce 3 different theme proposals. Each theme is then rendered as a visual mockup using `PipeImgGen`, and everything is assembled into an HTML report.

## How to run

```bash
pipelex run bundle examples/b_basics/generate_visuals/design_slides/bundle.mthds \
  -i examples/b_basics/generate_visuals/design_slides/inputs.json
```

## Related Documentation

- [PipeLLM Operator](../building-methods/pipes/pipe-operators/PipeLLM.md) - The core operator for LLM interactions
- [PipeImgGen Operator](../building-methods/pipes/pipe-operators/PipeImgGen.md) - Generate images from prompts
- [PipeCompose Operator](../building-methods/pipes/pipe-operators/PipeCompose.md) - Template-based data composition
- [PipeSequence Controller](../building-methods/pipes/pipe-controllers/PipeSequence.md) - Chain pipes into sequential workflows
