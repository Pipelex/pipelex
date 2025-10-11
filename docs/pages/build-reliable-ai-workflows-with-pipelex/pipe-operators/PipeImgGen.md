# PipeImgGen

The `PipeImgGen` operator is used to generate images from a text prompt using a specified image generation model.

## How it works

`PipeImgGen` takes a text prompt and a set of parameters, then calls an underlying image generation service (like GPT Image or Flux) to create one or more images.

The prompt can be provided in two ways:
1.  As a static string directly in the pipe's PLX definition using the `img_gen_prompt` parameter.
2.  As a dynamic input by connecting a concept that is or refines `native.Text`.

The pipe can be configured to generate a single image or a list of images.

## Configuration

`PipeImgGen` is configured in your pipeline's `.plx` file.

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

### PLX Parameters

| Parameter               | Type            | Description                                                                                                                   | Required |
| ----------------------- | --------------- | ----------------------------------------------------------------------------------------------------------------------------- | -------- |
| `type`                  | string          | The type of the pipe: `PipeImgGen`                                                                          | Yes      |
| `description`           | string          | A description of the image generation operation.                                                                           | Yes      |
| `inputs`                | dictionary      | The input concept(s) for the image generation operation, as a dictionary mapping input names to concept codes.                                                     | Yes       |
| `output`                | string          | The output concept produced by the image generation operation.                                                | Yes      |
| `img_gen_prompt`        | string          | A static text prompt for image generation. Use this *or* `input`.                                                             | No       |
| `nb_output`             | integer         | The number of images to generate. If omitted, a single image is generated.                                                    | No       |
| `img_gen`           | string          | The choice of image generation model handle preset or setting to use (e.g., `"gpt-image-1"`). Defaults to the model specified in the global config.    | No       |
| `aspect_ratio`          | string          | The desired aspect ratio of the image (e.g., `"16:9"`, `"1:1"`).                                                              | No       |
| `quality`               | string          | The quality of the generated image (e.g., `"standard"`, `"hd"`).                                                              | No       |
| `seed`                  | integer or "auto" | A seed for the random number generator to ensure reproducibility. `"auto"` uses a random seed.                                | No       |
| `nb_steps`              | integer         | For diffusion models, the number of steps to run. More steps can increase detail but take longer.                             | No       |
| `guidance_scale`        | float           | How strictly the model should adhere to the prompt. Higher values mean closer adherence.                                      | No       |


### Example: Generating a single image from a static prompt

This pipe generates one image of a futuristic car without requiring any input.

```plx
[pipe.generate_car_image]
type = "PipeImgGen"
description = "Generate a futuristic car image"
output = "Image"
img_gen_prompt = "A sleek, futuristic sports car driving on a neon-lit highway at night."
img_gen = "base_img_gen"
aspect_ratio = "16:9"
quality = "hd"
```

### Example: Generating multiple images from a dynamic prompt

This pipe takes a text prompt as input and generates three variations of the image.

```plx
[concept]
ImagePrompt = "A text prompt for generating an image"

[pipe.generate_logo_variations]
type = "PipeImgGen"
description = "Generate three logo variations from a prompt"
inputs = { prompt = "images.ImgGenPrompt" }
output = "Image"
nb_output = 3
img_gen = "base_img_gen"
aspect_ratio = "1:1"
```

The output of the PipeImgGen has to be a concept compatible with the native `Image` concept. A concept is compatible with the `Image` concept if it refines the `Image` concept.

To use this pipe, you would first load a text prompt (e.g., "A minimalist logo for a coffee shop, featuring a stylized mountain and a coffee bean") into the "prompt" stuff (`ImgGenPrompt` concept). After running, the output will be a list containing three generated `ImageContent` objects.

