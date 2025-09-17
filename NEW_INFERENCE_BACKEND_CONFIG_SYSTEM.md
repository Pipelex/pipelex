# New Inference Backend Configuration System

This document provides an overview of the new system for configuring LLM inference backends, models, and routing within Pipelex. The system is designed to be highly flexible and is managed through a series of TOML configuration files.

The core components of this system reside in the following directories:
- `pipelex/cogt/model_backends/`
- `pipelex/cogt/model_routing/`
- `pipelex/cogt/models/`

## Core Concepts

The new system is built around a few key concepts: Inference Backends, Model Specs, Routing Profiles, and the Model Deck.

### 1. Inference Backends

An **Inference Backend** represents a provider of LLM services, such as OpenAI, Anthropic, Google Vertex AI, etc. Each backend is defined by its name, API endpoint, and authentication details (e.g., API key).

- **Implementation**: `pipelex.cogt.model_backends.backend.InferenceBackend`
- **Configuration**: Backends are defined in a central TOML file (e.g., `backends.toml`), specified by `cogt.inference_config.backends_library_path` in the main configuration.

### 2. Model Specs

An **Inference Model Spec** (`InferenceModelSpec`) provides detailed information about a specific model available through a backend. This includes:

-   `model_id`: The identifier used by the backend's API.
-   `sdk`: The Pipelex SDK to use for communication (e.g., `openai`, `anthropic`).
-   Capabilities: Supported `inputs` (e.g., `text`, `images`) and `outputs` (e.g., `text`, `structured`).
-   Pricing: `costs` for input and output tokens.
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

-   **Inference Models**: A resolved map of model names (`llm_handle`) to their corresponding `InferenceModelSpec`.
-   **Aliases**: User-friendly names that map to one or more model names, creating a fallback chain (e.g., `best-claude` -> `claude-3-opus-20240229`).
-   **LLM Presets**: Pre-defined configurations (`LLMSetting`) for specific tasks, combining an `llm_handle` with parameters like `temperature` and `max_tokens` (e.g., `llm_to_reason`).
-   **Default Choices**: Default model presets to use for text generation (`for_text`) and structured data extraction (`for_object`).

- **Implementation**: `pipelex.cogt.models.model_deck.ModelDeck`
- **Configuration**: Aliases, presets, and defaults are loaded from one or more `llm_deck.toml` files, specified by `cogt.inference_config.get_llm_deck_paths()`.

## How It All Works Together: The Loading Process

The entire system is orchestrated by the `ModelManager` during application startup. Here is a step-by-step breakdown of the process:

1.  **Load Backends**: The `InferenceBackendLibrary` reads the `backends.toml` file to get a list of all defined backends. For each enabled backend, it proceeds to load its associated models.
2.  **Load Model Specs**: For each backend, the library reads the corresponding `<backend_name>.toml` file to load the `InferenceModelSpec` for every model that backend provides.
3.  **Load Routing Profiles**: The `RoutingProfileLibrary` reads the `routing.toml` file to load all defined routing profiles and identifies the `active` profile.
4.  **Build the Deck**: The `ModelManager` begins to build the `ModelDeck`.
    a. It gets the list of all models from all loaded backends.
    b. For each model, it consults the `active` `RoutingProfile` to determine which backend should be used.
    c. It retrieves the `InferenceModelSpec` for that model from the chosen backend.
    d. This resolved model spec is added to the `ModelDeck`'s list of `inference_models`.
5.  **Load Deck Configuration**: The `ModelManager` reads the `llm_deck.toml` files and loads the `aliases`, `llm_presets`, and default choices into the `ModelDeck`.
6.  **Finalization**: The `ModelDeck` is now fully constructed and ready to be used by the rest of Pipelex to get model specifications and settings via `get_models_manager().get_llm_deck()`.

This layered configuration system provides a powerful way to manage models from various providers, route them according to specific needs, and define reusable presets for common tasks, all through a set of clear and manageable TOML files.
