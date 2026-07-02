---
description: "Generate images from text prompts within your Pipelex pipelines using PipeImgGen. Configure models, sizes, and output formats declaratively."
---

# PipeImgGen

The `PipeImgGen` operator is used to generate images from a text prompt using a specified image generation model.

## How it works

`PipeImgGen` takes a required `prompt` **string template** (plus an optional `negative_prompt`) and a set of parameters, then calls an underlying image generation service (like GPT Image or Flux) to create one or more images. It does **not** consume a dedicated "prompt concept" — the prompt is a template you write directly on the pipe.

The variables you declare in `inputs` are **injected into that template** at run time:

- **Text inputs** (concept `Text`, or anything refining it) are interpolated into the prompt string — reference them with `$var` (or `@var` / `{{ var }}`).
- **Image inputs** (concept `Image`, single or a list) are referenced in the prompt the same way. Each referenced image is pulled from working memory, replaced in the text by an `[Image N]` placeholder token, and passed alongside the rendered text to the generator. This is the **same vision pattern** used for image inputs to `PipeLLM`, and it is what enables image-to-image, reference-image, and image-editing generation (e.g. Flux / GPT Image with reference images), bounded by the model's `max_prompt_images`.

The pipe can be configured to generate a single image or a list of images. Its only concept constraints are that declared image inputs must be `Image`-compatible and the `output` must be `Image`-compatible.

## Configuration

`PipeImgGen` is configured in your pipeline's `.mthds` file.

### The `prompt` Field is Required

**IMPORTANT:** `PipeImgGen` requires an explicit `prompt` field. When using dynamic inputs, the `prompt` field must reference the input variable using the `$` prefix.

**Wrong - Missing required `prompt` field:**

```toml
[pipe.render_slide]
type = "PipeImgGen"
inputs = { img_prompt = "Text" }
output = "Image"
model = "$gen-image"
# ERROR: Missing required field 'prompt'
```

**Correct - `prompt` field references the input:**

```toml
[pipe.render_slide]
type = "PipeImgGen"
inputs = { img_prompt = "Text" }
output = "Image"
prompt = "$img_prompt"
model = "$gen-image"
```

### Image Generation Models and Backend System

PipeImgGen uses the unified inference backend system to manage image generation models. This means you can:

- Use different image generation providers (OpenAI GPT Image, FAL models like Flux, etc.)
- Configure image generation models through the same backend system as LLMs and OCR models
- Use image generation presets for consistent configurations across your pipelines
- Route image generation requests to different backends based on your routing profile

Common image generation model handles:

- `base-img-gen`: Base image generation model (alias for flux-pro/v1.1)
- `best-img-gen`: Best quality image generation model (alias for flux-pro/v1.1-ultra)
- `fast-img-gen`: Fast image generation model (alias for fast-lightning-sdxl)

Image generation presets are defined in your model deck configuration and can include parameters like `quality`, `guidance_scale`, and `safety_tolerance`.

### MTHDS Parameters

| Parameter               | Type            | Description                                                                                                                   | Required |
| ----------------------- | --------------- | ----------------------------------------------------------------------------------------------------------------------------- | -------- |
| `type`                  | string          | The type of the pipe: `PipeImgGen`                                                                          | Yes      |
| `description`           | string          | A description of the image generation operation.                                                                           | Yes      |
| `inputs`                | dictionary      | The input concept(s) for the image generation operation, as a dictionary mapping input names to concept codes. Required when the prompt references variables. | No       |
| `output`                | string          | The output concept produced by the image generation operation. Use bracket notation for multiple images: `"Image[3]"` generates exactly 3 images.                                                | Yes      |
| `model`           | string          | The choice of image generation model name, setting, or preset to use (e.g., `"gpt-image-1"`). Defaults to the model specified in the global config.    | No       |
| `prompt`                | string          | The image generation prompt. Can be a static string or reference input variables using `$` prefix (e.g., `"$description"` or `"A sketch of: $subject"`). | Yes      |
| `negative_prompt`       | string          | Optional negative prompt when supported by the selected model or provider.                                                    | No       |
| `aspect_ratio`          | string          | The desired aspect ratio of the image. Valid values: `"square"`, `"landscape_4_3"`, `"landscape_3_2"`, `"landscape_16_9"`, `"landscape_21_9"`, `"landscape_4_1"`, `"landscape_8_1"`, `"portrait_3_4"`, `"portrait_2_3"`, `"portrait_9_16"`, `"portrait_9_21"`, `"portrait_1_4"`, `"portrait_1_8"`. The banner ratios (`landscape_4_1`, `landscape_8_1`, `portrait_1_4`, `portrait_1_8`) are only supported by Gemini 3.1 image models.                                                              | No       |
| `seed`                  | integer or "auto" | A seed for the random number generator to ensure reproducibility. `"auto"` uses a random seed.                                | No       |
| `background`            | string          | Optional background setting when supported by the selected provider.                                                          | No       |
| `output_format`         | string          | Optional output image format when supported by the selected provider.                                                         | No       |
| `is_raw`                | boolean         | Request a raw generation mode when supported by the selected provider.                                                        | No       |

### Example: Generating a single image from a static prompt

This pipe generates one image of a futuristic car without requiring any input.

```toml
[pipe.generate_car_image]
type = "PipeImgGen"
description = "Generate a futuristic car image"
output = "Image"
prompt = "A sleek, futuristic sports car driving on a neon-lit highway at night."
model = "$gen-image"
aspect_ratio = "landscape_16_9"
```

### Example: Generating an image from a dynamic prompt

This pipe takes a text prompt as input and generates an image.

```toml
[pipe.generate_from_description]
type = "PipeImgGen"
description = "Generate an image from a description"
inputs = { description = "Text" }
output = "Image"
prompt = "$description"
model = "$gen-image"
```

### Example: Dynamic prompt with prefix text

You can combine static text with dynamic variables in the prompt:

```toml
[pipe.generate_sketch]
type = "PipeImgGen"
description = "Generate a black and white sketch from a description"
inputs = { subject = "Text" }
output = "Image"
prompt = "Create a black and white pencil sketch of: $subject"
model = "$gen-image"
```

### Example: Generating multiple images

This pipe takes a text prompt as input and generates three variations of the image using bracket notation.

```toml
[pipe.generate_logo_variations]
type = "PipeImgGen"
description = "Generate three logo variations from a prompt"
inputs = { img_prompt = "Text" }
output = "Image[3]"
prompt = "$img_prompt"
model = "$gen-image"
aspect_ratio = "square"
```

### Example: Image-to-image with a reference image

Declare an `Image` input and reference it in the prompt. At run time the referenced image is pulled from working memory, replaced in the text by an `[Image N]` placeholder, and passed to the generator alongside the rendered text — enabling image-to-image, reference-image, and editing generation.

```toml
[pipe.restyle_photo]
type = "PipeImgGen"
description = "Restyle a reference photo as an oil painting"
inputs = { ref = "Image" }
output = "Image"
prompt = "Repaint this photo as an oil painting in the style of Van Gogh: $ref"
model = "$gen-image"
```

You can also reference several images by declaring a list input. Each referenced image becomes its own `[Image N]` token, up to the model's `max_prompt_images`:

```toml
[pipe.blend_references]
type = "PipeImgGen"
description = "Blend multiple reference images into one scene"
inputs = { refs = "Image[]" }
output = "Image"
prompt = "Combine the styles of these reference images into a single coherent scene: $refs"
model = "$gen-image"
```

Image references also work through a dotted path to a nested image field (e.g. `$page.page_view` when `page` is a `Page`), and through any of the `$var`, `@var`, or `{{ var }}` syntaxes.

### Inputs and outputs

The `output` of `PipeImgGen` has to be a concept compatible with the native `Image` concept — a concept is compatible if it refines `Image`. Its inputs are ordinary variables injected into the `prompt` template: `Text`-compatible variables are interpolated as text, and `Image`-compatible variables are injected as reference images (as shown above). There is no dedicated prompt concept anywhere in this flow.

To use the multiple-images example above, you would reference an ordinary `Text` stuff (e.g., "A minimalist logo for a coffee shop, featuring a stylized mountain and a coffee bean") from the `prompt` template. After running, the output will be a list containing three generated `ImageContent` objects.

## Related Documentation

- [Image Generation Feature](../../../features/image-generation.md) - Overview of image generation capabilities
- [Cloud Storage](../../../features/cloud-storage.md) - Store generated images in cloud storage

