# Cognitive Tools (Cogt) Configuration

The Cogt configuration manages all cognitive tools in Pipelex, including LLM (Language Models), IMGG (Image Generation), and OCR (Optical Character Recognition) capabilities.

## Overview

```toml
[cogt]
# Main Cogt configuration sections
[cogt.inference_manager_config]
[cogt.llm_config]
[cogt.imgg_config]
[cogt.ocr_config]
```

## Inference Manager Configuration

Controls automatic setup of various cognitive tools:

```toml
[cogt.inference_manager_config]
is_auto_setup_preset_llm = true
is_auto_setup_preset_imgg = true
is_auto_setup_preset_ocr = true
```

## LLM Configuration

Configuration for all Language Model interactions:

```toml
[cogt.llm_config]
default_max_images = 100  # Maximum number of images in prompts

# Job configuration
[cogt.llm_config.llm_job_config]
is_streaming_enabled = false
max_retries = 3  # Between 1 and 10

# Instructor settings
[cogt.llm_config.instructor_config]
is_openai_structured_output_enabled = false
```

### LLM Job Parameters

When configuring LLM jobs, you can set:

- `temperature` (float, 0-1): Controls randomness in outputs
- `max_tokens` (optional int): Maximum tokens in response
- `seed` (optional int): For reproducible outputs

## Image Generation (IMGG) Configuration

Configuration for image generation capabilities:

```toml
[cogt.imgg_config]
default_imgg_handle = "fal-ai/flux-pro"
imgg_handles = ["fal-ai/flux-pro", "fal-ai/fast-lightning-sdxl"]

[cogt.imgg_config.imgg_job_config]
is_sync_mode = false

# Default parameters for image generation
[cogt.imgg_config.imgg_param_defaults]
aspect_ratio = "square"  # Options: square, landscape_4_3, landscape_3_2, landscape_16_9, landscape_21_9,
                         # portrait_3_4, portrait_2_3, portrait_9_16, portrait_9_21
background = "auto"     # Options: transparent, opaque, auto
quality = "low"        # Options: low, medium, high
# nb_steps = 1          # Number of diffusion steps (28 is good for Flux, [1,2,4,8] for SDXL Lightning)
guidance_scale = 3.5    # Controls adherence to prompt
is_moderated = true    # Enable content moderation
safety_tolerance = 5    # Safety level (1-6)
is_raw = false         # Raw output mode
output_format = "jpg"  # Options: png, jpg, webp
seed = "auto"          # "auto" or specific integer
```

### IMGG Job Parameters

Image generation jobs support these parameters:

- **Dimensions**:

    - `aspect_ratio`: Predefined ratios for image dimensions
    - `background`: Background handling mode

- **Quality Control**:

    - `quality`: Output quality level
    - `nb_steps`: Number of generation steps
    - `guidance_scale`: How closely to follow the prompt

- **Safety**:

    - `is_moderated`: Enable content moderation
    - `safety_tolerance`: Safety check strictness (1-6)

- **Output**:

    - `is_raw`: Raw output mode
    - `output_format`: Image format (PNG/JPG/WEBP)
    - `seed`: For reproducible generation

## OCR Configuration

Configuration for Optical Character Recognition:

```toml
[cogt.ocr_config]
ocr_handles = ["mistral/mistral-ocr-latest"]
page_output_text_file_name = "page_text.md"
default_page_views_dpi = 72
```

## Validation Rules

### LLM Configuration
- Temperature must be between 0 and 1
- Max tokens must be positive
- Max retries must be between 1 and 10
- Seeds must be non-negative

### IMGG Configuration
- Guidance scale must be positive
- Safety tolerance must be between 1 and 6
- Number of steps must be positive
- Strict validation for enums (aspect ratio, background, quality, output format)

## Best Practices

1. **LLM Settings**:

    - Start with lower temperatures (0.1-0.3) for consistent outputs
    - Use streaming for better user experience
    - Set appropriate retry limits based on your use case

2. **IMGG Settings**:

    - Enable moderation for production use
    - Use appropriate aspect ratios for your use case
    - Balance quality and performance with step count

3. **General**:

     - Enable auto-setup for easier initialization
     - Use platform preferences to ensure consistent model selection
     - Configure OCR handles based on your accuracy needs

## Example Complete Configuration

```toml
[cogt]
[cogt.inference_manager_config]
is_auto_setup_preset_llm = true
is_auto_setup_preset_imgg = true
is_auto_setup_preset_ocr = true

[cogt.llm_config]
default_max_images = 100

[cogt.llm_config.llm_job_config]
is_streaming_enabled = false
max_retries = 3

[cogt.llm_config.instructor_config]
is_openai_structured_output_enabled = false

[cogt.imgg_config]
default_imgg_handle = "fal-ai/flux-pro/v1.1-ultra"
imgg_handles = ["fal-ai/flux-pro", "fal-ai/fast-lightning-sdxl"]

[cogt.imgg_config.imgg_job_config]
is_sync_mode = false

[cogt.imgg_config.imgg_param_defaults]
aspect_ratio = "square"
background = "auto"
quality = "low"
# nb_steps = 1
guidance_scale = 3.5
is_moderated = true
safety_tolerance = 5
is_raw = false
output_format = "jpg"
seed = "auto"

[cogt.ocr_config]
ocr_handles = ["mistral/mistral-ocr-latest"]
page_output_text_file_name = "page_text.md"
```
