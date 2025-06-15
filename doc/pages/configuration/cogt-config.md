# Cognitive Tools (Cogt) Configuration

The Cogt configuration manages all cognitive tools in Pipelex, including LLM (Language Models), IMGG (Image Generation), and OCR (Optical Character Recognition) capabilities.

## Overview

```toml
[pipelex.cogt]
# Main Cogt configuration sections
[pipelex.cogt.inference_manager_config]
[pipelex.cogt.llm_config]
[pipelex.cogt.imgg_config]
[pipelex.cogt.ocr_config]
```

## Inference Manager Configuration

Controls automatic setup of various cognitive tools:

```toml
[pipelex.cogt.inference_manager_config]
is_auto_setup_preset_llm = true
is_auto_setup_preset_imgg = true
is_auto_setup_preset_ocr = true
```

## LLM Configuration

Configuration for Language Model interactions:

```toml
[pipelex.cogt.llm_config]
default_max_images = 4  # Maximum number of images in prompts

# Platform preferences for different LLMs
[pipelex.cogt.llm_config.preferred_platforms]
gpt-4 = "openai"
claude-3-opus = "anthropic"

# Job configuration
[pipelex.cogt.llm_config.llm_job_config]
is_streaming_enabled = true
max_retries = 3  # Between 1 and 10

# Instructor settings
[pipelex.cogt.llm_config.instructor_config]
is_openai_structured_output_enabled = true
```

### LLM Job Parameters

When configuring LLM jobs, you can set:

- `temperature` (float, 0-1): Controls randomness in outputs
- `max_tokens` (optional int): Maximum tokens in response
- `seed` (optional int): For reproducible outputs

## Image Generation (IMGG) Configuration

Configuration for image generation capabilities:

```toml
[pipelex.cogt.imgg_config]
default_imgg_handle = "stable_diffusion"
imgg_handles = ["stable_diffusion", "dall_e"]

[pipelex.cogt.imgg_config.imgg_job_config]
is_sync_mode = true

# Default parameters for image generation
[pipelex.cogt.imgg_config.imgg_param_defaults]
aspect_ratio = "square"  # Options: square, landscape_4_3, landscape_3_2, landscape_16_9, landscape_21_9,
                        #         portrait_4_3, portrait_2_3, portrait_9_16, portrait_9_21
background = "auto"     # Options: transparent, opaque, auto
quality = "high"        # Options: low, medium, high
nb_steps = 50          # Number of diffusion steps
guidance_scale = 7.5    # Controls adherence to prompt
is_moderated = true    # Enable content moderation
safety_tolerance = 3    # Safety level (1-6)
is_raw = false         # Raw output mode
output_format = "png"  # Options: png, jpg, webp
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
[pipelex.cogt.ocr_config]
ocr_handles = ["tesseract", "azure_ocr"]
page_output_text_file_name = "page_text.txt"
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
[pipelex.cogt]
[pipelex.cogt.inference_manager_config]
is_auto_setup_preset_llm = true
is_auto_setup_preset_imgg = true
is_auto_setup_preset_ocr = true

[pipelex.cogt.llm_config]
default_max_images = 4
preferred_platforms = { "gpt-4" = "openai", "claude-3-opus" = "anthropic" }

[pipelex.cogt.llm_config.llm_job_config]
is_streaming_enabled = true
max_retries = 3

[pipelex.cogt.llm_config.instructor_config]
is_openai_structured_output_enabled = true

[pipelex.cogt.imgg_config]
default_imgg_handle = "stable_diffusion"
imgg_handles = ["stable_diffusion", "dall_e"]

[pipelex.cogt.imgg_config.imgg_job_config]
is_sync_mode = true

[pipelex.cogt.imgg_config.imgg_param_defaults]
aspect_ratio = "square"
background = "auto"
quality = "high"
nb_steps = 50
guidance_scale = 7.5
is_moderated = true
safety_tolerance = 3
is_raw = false
output_format = "png"
seed = "auto"

[pipelex.cogt.ocr_config]
ocr_handles = ["tesseract", "azure_ocr"]
page_output_text_file_name = "page_text.txt"
```
