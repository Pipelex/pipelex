# PipeImgGen

The `PipeImgGen` operator is used to generate images from a text prompt using a specified image generation model.

## How it works

`PipeImgGen` takes a text prompt and a set of parameters, then calls an underlying image generation service (like DALL-E 3 or Stable Diffusion) to create one or more images.

The prompt can be provided in two ways:
1.  As a static string directly in the pipe's TOML definition using the `imgg_prompt` parameter.
2.  As a dynamic input by connecting a concept that is or refines `native.Text`.

The pipe can be configured to generate a single image or a list of images.

## Configuration

`PipeImgGen` is configured in your pipeline's `.toml` file.

### TOML Parameters

| Parameter               | Type            | Description                                                                                                                   | Required |
| ----------------------- | --------------- | ----------------------------------------------------------------------------------------------------------------------------- | -------- |
| `PipeImgGen`            | string          | A descriptive name for the pipe's function.                                                                                   | Yes      |
| `input`                 | string          | The input concept (must be a `Text`) that provides the prompt. Use this *or* `imgg_prompt`.                                    | No       |
| `output`                | string          | The output concept. Should be compatible with `native.Image`.                                                                 | No       |
| `imgg_prompt`           | string          | A static text prompt for image generation. Use this *or* `input`.                                                             | No       |
| `output_multiplicity`   | integer         | The number of images to generate. If omitted, a single image is generated.                                                    | No       |
| `imgg_handle`           | string          | The handle for the image generation model to use (e.g., `"dall-e-3"`). Defaults to the model specified in the global config.    | No       |
| `aspect_ratio`          | string          | The desired aspect ratio of the image (e.g., `"16:9"`, `"1:1"`).                                                              | No       |
| `quality`               | string          | The quality of the generated image (e.g., `"standard"`, `"hd"`).                                                              | No       |
| `seed`                  | integer or "auto" | A seed for the random number generator to ensure reproducibility. `"auto"` uses a random seed.                                | No       |
| `nb_steps`              | integer         | For diffusion models, the number of steps to run. More steps can increase detail but take longer.                             | No       |
| `guidance_scale`        | float           | How strictly the model should adhere to the prompt. Higher values mean closer adherence.                                      | No       |


### Example: Generating a single image from a static prompt

This pipe generates one image of a futuristic car without requiring any input.

```toml
[pipe.generate_car_image]
PipeImgGen = "Generate a futuristic car image"
output = "native.Image"
imgg_prompt = "A sleek, futuristic sports car driving on a neon-lit highway at night."
imgg_handle = "dall-e-3"
aspect_ratio = "16:9"
quality = "hd"
```

### Example: Generating multiple images from a dynamic prompt

This pipe takes a text prompt as input and generates three variations of the image.

```toml
[concept]
ImagePrompt = "A text prompt for generating an image"

[pipe.generate_logo_variations]
PipeImgGen = "Generate three logo variations from a prompt"
input = "ImagePrompt"
output = "native.Image"
output_multiplicity = 3
imgg_handle = "stable-diffusion"
aspect_ratio = "1:1"
```

To use this pipe, you would first load a text prompt (e.g., "A minimalist logo for a coffee shop, featuring a stylized mountain and a coffee bean") into the `ImagePrompt` concept. After running, the output will be a list containing three generated `ImageContent` objects.
