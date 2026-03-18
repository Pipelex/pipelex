---
title: "Generate Image Example"
description: "Generate creative, absurd images using a multi-step pipeline that imagines a scene, crafts a prompt, and renders the image."
---

# Example: Generate Image

This example generates creative, absurd images through a three-step pipeline: imagine a surreal scene concept, refine it into an optimized image prompt, then render the image.

## Get the code

[![GitHub](https://img.shields.io/badge/View_on_GitHub-5a0dad?logo=github&logoColor=white&style=flat)](https://github.com/Pipelex/pipelex-cookbook/blob/main/examples/b_basics/generate_visuals/gen_image/bundle.mthds)

## What it demonstrates

- Concept refinement (`SceneConcept` and `ImagePrompt` both refine `Text`)
- `PipeImgGen` for image generation
- Multi-step creative pipeline where each step builds on the previous one
- No external inputs required — the pipeline generates everything from scratch

## The Method: `bundle.mthds`

```toml
domain      = "crazy_image_generation"
main_pipe   = "generate_crazy_image"

[concept.SceneConcept]
description = "A creative, abstract description of an absurd and surreal scene."
refines = "Text"

[concept.ImagePrompt]
description = "A detailed textual description optimized for image generation models."
refines = "Text"

[pipe.generate_crazy_image]
type = "PipeSequence"
description = "Main pipeline that imagines a scene, refines it into a prompt, and renders the image"
output = "Image"
steps = [
  { pipe = "imagine_scene", result = "scene_concept" },
  { pipe = "generate_img_prompt", result = "image_prompt" },
  { pipe = "render_image", result = "crazy_image" },
]
```

The `render_image` pipe uses `PipeImgGen` to generate the final image:

```toml
[pipe.render_image]
type        = "PipeImgGen"
description = "Generates the absurd image based on the creative scene description"
inputs      = { image_prompt = "ImagePrompt" }
output      = "Image"
prompt      = "$image_prompt"
model       = "@default-small"
```

## How to run

```bash
pipelex run bundle examples/b_basics/generate_visuals/gen_image/bundle.mthds
```

No inputs needed — the pipeline imagines everything from scratch.

## Related Documentation

- [PipeImgGen Operator](../building-methods/pipes/pipe-operators/PipeImgGen.md) - Generate images from prompts
- [PipeLLM Operator](../building-methods/pipes/pipe-operators/PipeLLM.md) - The core operator for LLM interactions
- [Refining Concepts](../building-methods/concepts/refining-concepts.md) - How concept refinement works
