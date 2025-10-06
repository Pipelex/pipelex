# New Inference Backend Configuration System

This document provides an overview of the new system for configuring LLM inference backends, models, and routing within Pipelex. The system is designed to be highly flexible and is managed through a series of TOML configuration files.

The core components of this system reside in the following directories:
- `pipelex/cogt/model_backends/`
- `pipelex/cogt/model_routing/`
- `pipelex/cogt/models/`

## Core Concepts

The new system is built around a few key concepts: Inference Backends, Model Specs, Routing Profiles, and the Model Deck. This unified system now supports all types of AI models: LLMs for text generation, OCR models for text extraction, and Image Generation models.

### 1. Inference Backends

An **Inference Backend** represents a provider of AI services, such as OpenAI, Anthropic, Google Vertex AI, FAL, etc. Each backend is defined by its name, API endpoint, and authentication details (e.g., API key). Backends can provide different types of models including LLMs, OCR models, and Image Generation models.

- **Implementation**: `pipelex.cogt.model_backends.backend.InferenceBackend`
- **Configuration**: Backends are defined in a central TOML file (e.g., `backends.toml`), specified by `cogt.inference_config.backends_library_path` in the main configuration.

### 2. Model Specs

An **Inference Model Spec** (`InferenceModelSpec`) provides detailed information about a specific model available through a backend. This includes:

-   `model_type`: The type of model (`llm`, `text_extractor`, or `img_gen`).
-   `model_id`: The identifier used by the backend's API.
-   `sdk`: The Pipelex SDK to use for communication (e.g., `openai`, `anthropic`, `fal`, `pypdfium2`).
-   Capabilities: Supported `inputs` (e.g., `text`, `images`, `pdf`) and `outputs` (e.g., `text`, `structured`, `pages`, `image`).
-   Pricing: `costs` for input and output tokens or operations.
-   Constraints: `max_tokens`, `max_prompt_images`, and other model-specific limitations.

- **Implementation**: `pipelex.cogt.model_backends.model_spec.InferenceModelSpec`
- **Configuration**: Model specs for each backend are defined in their own dedicated TOML file (e.g., `openai.toml`, `anthropic.toml`). The path to these files is determined by `cogt.inference_config.model_specs_path(backend_name)`.

### 3. Routing Profiles

A **Routing Profile** (`RoutingProfile`) defines the rules for selecting which backend should be used for a given model name. This allows for flexible and environment-specific model routing. A routing profile consists of:

-   A `default` backend to use if no other rule matches.
-   A set of `routes` that map a model name (or a pattern) to a specific backend.

The routing logic supports exact matches, as well as prefix, suffix, and "contains" wildcard (`*`) matching.

- **Implementation**: `pipelex.cogt.model_routing.routing_profile.RoutingProfile`
- **Configuration**: Multiple routing profiles can be defined in a single TOML file (e.g., `routing.toml`), specified by `cogt.inference_config.routing_profile_library_path`. One profile is designated as `active`.

### 4. The Model Deck

The **Model Deck** (`ModelDeck`) is the final, unified collection of all configured and available models in the system. It is constructed at runtime by the `ModelManager` and serves as the single source of truth for the rest of the application. The Model Deck contains:

-   **Inference Models**: A resolved map of model names (`model_handle`) to their corresponding `InferenceModelSpec`.
-   **Aliases**: User-friendly names that map to one or more model names, creating a fallback chain (e.g., `best-claude` -> `claude-3-opus-20240229`, `base-img-gen` -> `flux-pro/v1.1`).
-   **LLM Presets**: Pre-defined configurations (`LLMSetting`) for specific tasks, combining an `llm_handle` with parameters like `temperature` and `max_tokens` (e.g., `llm_to_reason`).
-   **OCR Presets**: Pre-defined configurations (`OcrSetting`) for OCR tasks, combining an `ocr_handle` with parameters like `max_nb_images` and `image_min_size` (e.g., `base_ocr_mistral`).
-   **Image Generation Presets**: Pre-defined configurations (`ImgGenSetting`) for image generation tasks, combining an `img_gen_handle` with parameters like `quality`, `guidance_scale`, and `safety_tolerance` (e.g., `base_img_gen`, `high_quality_img_gen`).
-   **Default Choices**: Default model presets to use for text generation (`for_text`), structured data extraction (`for_object`), OCR operations (`ocr.choice_default`), and image generation (`img_gen.choice_default`).

- **Implementation**: `pipelex.cogt.models.model_deck.ModelDeck`
- **Configuration**: Aliases, presets, and defaults are loaded from one or more `model_deck.toml` files, specified by `cogt.inference_config.get_model_deck_paths()`.

### 5. OCR Integration

**OCR (Optical Character Recognition)** models are now fully integrated into the inference backend system. OCR models extract text and images from PDFs and images, producing structured page data.

- **Model Type**: `text_extractor`
- **Common SDKs**: `mistral` (for Mistral OCR models), `pypdfium2` (for local PDF text extraction)
- **Inputs**: `pdf`, `image`
- **Outputs**: `pages` (structured page data with text and images)
- **Usage**: OCR models are referenced by their `ocr_handle` in `PipeExtract` operations and can use OCR presets for common configurations

Example OCR model configuration:
```toml
[mistral-ocr]
model_type = "text_extractor"
model_id = "mistral-ocr-latest"
inputs = ["pdf", "image"]
outputs = ["pages"]
costs = { input = 0.4, output = 2.0 }
```

### 6. Image Generation Integration

**Image Generation** models are integrated into the same system, allowing for consistent configuration and routing of image generation requests.

- **Model Type**: `img_gen`
- **Common SDKs**: `fal` (for FAL models), `openai` (for DALL-E models)
- **Inputs**: `text` (prompts)
- **Outputs**: `image`
- **Usage**: Image generation models are referenced by their `img_gen_handle` in `PipeImgGen` operations and support presets for different quality levels and use cases

Example Image Generation model configuration:
```toml
["flux-pro/v1.1"]
model_type = "img_gen"
model_id = "fal-ai/flux-pro/v1.1"
inputs = ["text"]
outputs = ["image"]
costs = { input = 0.05, output = 0.0 }
```

## How It All Works Together: The Loading Process

The entire system is orchestrated by the `ModelManager` during application startup. Here is a step-by-step breakdown of the process:

1.  **Load Backends**: The `InferenceBackendLibrary` reads the `backends.toml` file to get a list of all defined backends. For each enabled backend, it proceeds to load its associated models.
2.  **Load Model Specs**: For each backend, the library reads the corresponding `<backend_name>.toml` file to load the `InferenceModelSpec` for every model that backend provides. This includes LLM models, OCR models (`text_extractor` type), and Image Generation models (`img_gen` type).
3.  **Load Routing Profiles**: The `RoutingProfileLibrary` reads the `routing.toml` file to load all defined routing profiles and identifies the `active` profile.
4.  **Build the Deck**: The `ModelManager` begins to build the `ModelDeck`.
    a. It gets the list of all models from all loaded backends (LLMs, OCR models, and Image Generation models).
    b. For each model, it consults the `active` `RoutingProfile` to determine which backend should be used.
    c. It retrieves the `InferenceModelSpec` for that model from the chosen backend.
    d. This resolved model spec is added to the `ModelDeck`'s list of `inference_models`.
5.  **Load Deck Configuration**: The `ModelManager` reads the `base_deck.toml` and other model deck files from the `deck` directory and loads the `aliases`, `llm_presets`, `ocr_presets`, `img_gen_presets`, and default choices into the `ModelDeck`.
6.  **Finalization**: The `ModelDeck` is now fully constructed and ready to be used by the rest of Pipelex to get model specifications and settings for LLMs, OCR operations, and Image Generation via `get_model_deck()`.

This layered configuration system provides a powerful way to manage models from various providers, route them according to specific needs, and define reusable presets for common tasks, all through a set of clear and manageable TOML files. The unified approach ensures that LLMs, OCR models, and Image Generation models are all managed consistently within the same infrastructure.
