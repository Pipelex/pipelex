# Changelog

## [v0.14.3] - 2025-10-29

### Added
 - Image generation models via BlackBoxAI backend: `flux-pro`, `flux-pro/v1.1`, `flux-pro/v1.1-ultra` (Black Forest Labs), `fast-lightning-sdxl` (ByteDance), and `nano-banana` (Google). Implemented using new `openai_alt_img_gen` SDK worker with chat completion-style API.
 - Language model: `claude-4.5-sonnet` (Anthropic) via BlackBoxAI backend.
 - Routing profile: `all_blackboxai` profile routes all supported model requests to BlackBoxAI backend.

### Changed
 - Model aliases in `base_deck.toml`: `base-img-gen` → `flux-pro/v1.1-ultra`, `best-img-gen` → `nano-banana`, `llm_for_large_codebase` now includes `claude-4.5-sonnet`.
 - Configuration file: `BLACKBOX_RULES.md` renamed to `.blackboxrules`.

### Fixed
 - Image generation schema: `ImgGenJobParams.seed` field now explicitly defined with `default=None`.
 - CLI bundle validation: `pipelex validate` command now accepts bundle path (`.plx` file) which are in the package and already loaded and performs dry run on all pipes in the bundle.


## [v0.14.2] - 2025-10-29

### Chaged
- Improved pipe builder.

### Added
- CLI to generate inputs JSON.

## [v0.14.1] - 2025-10-27

### Added
- Tutorial GIF on the README.md file.

## [v0.14.0] - 2025-10-27

### Added
 - **`pipelex doctor` command**: Diagnoses and fixes common configuration issues including missing files, invalid telemetry settings, and unset environment variables for enabled backends.
 - **Interactive backend selection in `pipelex init`**: Multi-select menu for enabling/disabling inference backends (OpenAI, Anthropic, Amazon Bedrock, etc.).
 - **JSON input support**: `pipelex run --inputs` flag accepts a JSON file path for passing structured data to pipelines.
 - **`pretty_print` methods**: Added to `PipeSpec`, `ConceptSpec`, and `Stuff` objects for readable debugging output.
 - **VS Code debug configuration**: "Debug run pipe" launch configuration for debugging pipeline executions.
 - **`display_name` attribute**: Added to all inference backends in `backends.toml` for better UI presentation.
 - **Documentation headers**: All default `.toml` configuration files now include headers with links to documentation and support channels.

### Changed
 - **`pipelex init` redesign**: Transformed into a unified, interactive setup wizard with rich terminal UI for configuration files, backend selection, and telemetry preferences. Telemetry is now configured here instead of via first-run prompt.
 - **`README.md` rewrite**: Complete overhaul featuring a simplified 5-step quick-start guide highlighting the `pipelex build` command.
 - **Documentation updates**: "Quick Start" guide renamed to "Writing Workflows" with simplified content. Python examples updated to use JSON input method, removing manual `Stuff` and `WorkingMemory` object creation boilerplate. Developer guides and AI assistant rules now recommend `pipelex validate` over `make validate`. Added instructions emphasizing `.venv` activation before running commands.
 - **Error handling improvements**: Pipelines now validate required inputs upfront and fail early with `PipeRunInputsError`. `pipelex run` prints full rich-formatted exception tracebacks on error.
 - **Default enabled backends**: Amazon Bedrock, Google AI, and Google Vertex AI are now enabled by default.
 - **Naming consistency**: "AWS Bedrock" renamed to "Amazon Bedrock" throughout codebase, configuration, and documentation.

### Fixed

- Some documentation links were broken.

## [v0.13.2] - 2025-10-25

### Added

- Added the `n8n` documentation page for the [n8n-nodes-pipelex](https://github.com/Pipelex/n8n-nodes-pipelex) package.
- Added optional telemetry system with first-run interactive prompt offering three modes: off (no data collected), anonymous (usage data without identification), and identified (usage data with user identification). Automatically respects `DO_NOT_TRACK` environment variable and redacts sensitive data (prompts, responses, file paths, URLs). Configuration stored in `.pipelex/telemetry.toml`.
- Added telemetry documentation: user-friendly setup guide and comprehensive configuration reference.

### Changed

- Updated the `PipelexClient` and changed the route of the API calls to `v1/pipeline/execute` and `v1/pipeline/start`.
- Changed the parameter `input_memory` to `inputs` in the documentaton.

## [v0.13.1] - 2025-10-22

### Changed

- Changed the `pydantic`dependency from `==2.10.6` to `>=2.10.6,<3.0.0` to avoid compatibility issues.

## [v0.13.0] - 2025-10-21

### Highlights - Simplifying pipeline execution and improving developer experience

This release focuses on making Pipelex more accessible and easier to use, with major improvements to the CLI, simplified syntax for multiplicity, and a complete documentation overhaul:

- **New CLI commands**: Run pipelines directly with `pipelex run`, generate Python runners with `pipelex build runner`, and inspect your AI backend configuration with `pipelex show backends`
- **Simplified pipeline inputs**: The new `inputs` parameter replaces `input_memory` and accepts strings, lists, or content objects directly - no more complex dictionary structures
- **Getting started faster**: Completely rewritten quick-start guide and new documentation sections help you go from installation to your first pipeline in minutes

### Added

- CLI command `pipelex run`: Top-level command to execute pipelines directly from the CLI. Can run pipes from the package or from any `.plx` bundle file, with options to provide inputs from a JSON file and save the output
- CLI command `pipelex build runner`: Generates Python script with imports and example input structures for any pipe
- CLI command `pipelex show backends`: Displays configured AI providers, their status, and active routing rules
- Model presets: Added task-oriented presets including `llm_to_write_questions`, `llm_to_code`, `llm_for_basic_vision`, `llm_for_visual_analysis`
- Documentation: Complete quick-start guide rewrite, new guides for "Understanding Multiplicity", "API Guide", "Executing Pipelines with Inputs", and updated README with video demo
- Migration guide: Updated guide at `pipelex/kit/migrations/migrate_0.11.0_0.12.x.md`

### Changed

- **Unified bracket notation for multiplicity**: Single items use `"Concept"`, variable lists use `"Concept[]"`, fixed-count lists use `"Concept[3]"`. Applies to both `inputs` and `output` fields in `.plx` files
- **Pipeline input format**: `input_memory` parameter renamed to `inputs`; now accepts strings, lists of strings, `StuffContent` objects, or explicit concept dictionaries instead of `CompactMemory`
- **Bundle `main_pipe` attribute**: Pipelex bundles (`.plx` files) now support a `main_pipe` attribute to designate the primary entry point of the bundle. Used by `pipelex run` and `pipelex build runner` commands to simplify execution
- **Model preset names**: `llm_to_reason` → `llm_for_complex_reasoning`, `base_ocr_mistral` → `extract_text_from_visuals`, `base_extract_pypdfium2` → `extract_text_from_pdf`, `base_img_gen` → `gen_image_basic`, `fast_img_gen` → `gen_image_fast`, `high_quality_img_gen` → `gen_image_high_quality`
- **Unified model parameter**: `PipeExtract` and `PipeImgGen` now use `model` parameter for consistency across all operator pipes
- **`PipeExtract` operator**: Output is now consistently validated to be the `Page` concept, simplifying its usage for document processing
- **CLI improvements**: `pipelex run` and `pipelex validate` now auto-detect pipe code vs `.plx` bundle files; `pipelex validate` promoted to top-level command with improved error reporting and syntax-highlighted code snippets
- **CLI reorganization**: Main command-line interface restructured for better usability with improved help texts and more logical command order
- **Python API**: `Pipelex.make()` now accepts dependency injection arguments directly
- **Python coding standards**: Updated internal coding standards to recommend declaring variables with a type but no default value to better leverage linters for bug detection
- **Default configuration**: Azure and AWS inference backends now disabled by default in template configuration

### Fixed

- Structure generation: Special characters (double quotes, backslashes) in concept field descriptions or default values no longer produce invalid Python code

### Removed

- Legacy multiplicity syntax: `nb_output`, `multiple_output` parameters, and complex input dictionary syntax with `multiplicity` field
- Pipe-specific model parameters: `ocr` parameter from `PipeExtract` and `img_gen` parameter from `PipeImgGen`
- `prompt_template_to_structure` and `system_prompt_to_structure` configurations at the pipe and domain level
- Project Name discovery from Configuration
- Temporary design document for the new inference backend system (feature now fully implemented and documented)

## [v0.12.0] - 2025-10-15

### Highlights - Moving fast and breaking things

- Added the new builder pipeline system for auto-generating Pipelex bundles from user briefs
  - it's a pipeline to generate pipelines, and it works!
  - the pipeline definitions are in `pipelex_libraries/pipelines/base_library/builder/`
  - removed the previous draft which was named `meta_pipeline.plx`

**Breaking changes... for good!**

We tried to group all the renamings we wanted to do which impact our language, so that you get one migration to apply and then we will be way more stable in the future releases.

This is all in the spirit of making Pipelex a declarative language, where you express what you want to do, and the system will figure out how to do it. So our focus inwas to make the Pipelex language easier to understand and use for non-technical users, and at the same time use more consistent and obvious words that developers are used to.

**💡 Pro tip:** To make migration easier, pass the [migration guide](https://github.com/Pipelex/pipelex/blob/main/pipelex/kit/migrations/migrate_0.11.0_0.12.0.md) to your favorite SWE agent (Cursor, Claude Code, github copilot, etc.) and let it handle the bulk of the changes!

- **Removed centralized `pipelex_libraries` folder system**
  - Pipelines are now auto-discovered from anywhere in your project—no special directory required
  - No config path parameters needed in `Pipelex.make()` or CLI commands (just call `Pipelex.make()`)
  - Custom functions require `@pipe_func()` decorator for auto-discovery
  - Structure classes auto-discovered (must inherit from `StructuredContent`)
  - Configuration stays at repository root in `.pipelex/` directory
  - See [migration guide](https://github.com/PipelexLab/pipelex/blob/main/pipelex/kit/migrations/migrate_0.11.0_0.12.0.md) for details on reorganizing your project structure

- General changes
  - renamed `definition` fields to `description` across all cases

- Renamed **PipeJinja2** to **PipeCompose**
  - the fact that our templating engine is Jinja2 is a technnical detail, not fundamental to the language, especially since we included a pre-processor enabling insertion of variables in prompts using `@variable` or `$variable`, in addition to the jinja2 syntax `{{ variable }}`
  - renamed `jinja2` field to `template` for the same reason
  - for more control, instead of providing a string for the `template` field, you can also use a nested `template` section with `template`, `category` and `templating_style` fields

- Renamed **PipeOCR** to **PipeExtract**
  - this is to account for various text extraction techniques from images and docs, including but not only OCR; e.g. we now have integrated the `pypdfium2` package which can extract text and images from PDF, when it's actually real text (not an image), and soon we'll add support for other document extraction models solutions
  - removed obligation to name your document input `ocr_input`, it can now be named whatever you want as long as it's a single input and it's either an `Image` or a `PDF` or some concept refining PDF or Image
  - renamed `ocr_page_contents_from_pdf` to `extract_page_contents_from_pdf`
  - renamed `ocr_page_contents_and_views_from_pdf` to `extract_page_contents_and_views_from_pdf`
  - introduced model settings and presets for extract models like we had for LLMs
  - renamed `ocr_model` to `model` for choice of model, preset, or explicit setting and introduced `base_ocr_mistral` as an alias to `mistral-ocr`

- **PipeLLM** field renames
  - image inputs must now be tagged in the prompt like all other inputs; you can just drop their names at the beginning or end of the prompt, or you can reference them in meaningful sentences to guide the Visual LLM, e.g. "Analyze the colors in $some_photo and the shapes in $some_painting." 
  - renamed `prompt_template` field to `prompt`
  - renamed `llm` field to `model`
  - renamed `llm_to_structure` field to `model_to_structure`

- **PipeImgGen** field renames
  - renamed `img_gen` field to `model` for choice of model, preset, or explicit setting
  - removed some technical settings such as `nb_steps` from the pipe attributes, instead you can set these as model settings or model presets
  - introduced model settings and presets for image generation models like we had for LLMs

- **PipeCondition** field renames
  - renamed `pipe_map` to `outcomes`
  - renamed `default_pipe_code` to `default_outcome` and it's now a required field, because we need to know what to do if the expression doesn't match any key in the outcomes map; if you don't know what to do in that case, then it's a failure and you can use the `fail` value

- **Configuration file changes** (`.pipelex/` directory)
  - Renamed parameter `llm_handle` to `model` across all LLM presets in deck files
  - Renamed parameter `img_gen_handle` to `model` across all image generation presets in deck files
  - Renamed parameter `ocr_handle` to `model` in extraction presets
  - Renamed `ocr` section to `extract` throughout configuration files
  - Renamed `ocr_config` to `extract_config` in `pipelex.toml`
  - Renamed `base_ocr_pypdfium2` to `base_extract_pypdfium2`
  - Renamed `is_auto_setup_preset_ocr` to `is_auto_setup_preset_extract`
  - Renamed `nb_ocr_pages` to `nb_extract_pages`
  - Updated pytest marker from 'ocr' to 'extract'

### Added
 - Added `cheap-gpt` model alias for `gpt-4o-mini`
 - Added `cheap_llm_for_vision` preset using `gemini-2.5-flash-lite`
 - Added `llm_for_testing_vision` and `llm_for_testing_vision_structured` presets for vision testing
 - Added `is_dump_text_prompts_enabled` and `is_dump_response_text_enabled` configuration flags to have the console display everything that goes in and out of the LLMs
 - Added `generic_templates` section in `llm_config` with structure extraction prompts
 - Added useful error messages with migration configuration maps pin-pointing the fields to rename for config and plx files
 - Added improved error message for `PipeFunc` when function not found in registry, mentioning `@pipe_func()` decorator requirement since v0.12.0
 - Added pytest filterwarnings to ignore deprecated class-based config warnings
 - Added `Flow` class that represents the flow of pipe signatures
 - Added `pipe-builder` command `flow` to generate flow view from pipeline brief
 - Added `FlowFactory` class to create Flow from PipelexBundleSpec or PLX files
 - Added `sort_pipes_by_dependencies()` function for topological sorting of pipes
 - Added `pipe_sorter.py` module for pipe dependency sorting utilities
 - Added `search_for_nested_image_fields_in_structure_class()` method to Concept class
 - Added `image_field_search.py` module with utilities to search for image fields in structure classes
 - Added `pipe_dependencies` property to PipeBlueprint and controller blueprints
 - Added `ordered_pipe_dependencies` property to PipeBlueprint for ordered dependencies
 - Added `get_native_concept()` function to hub
 - Added `get_pipes()` function to hub
 - Added `remove_concepts_by_codes()` method to ConceptLibraryAbstract
 - Added `remove_pipes_by_codes()` method to PipeLibraryAbstract
 - Added template preprocessing with `preprocess_template()` function
 - Added better dependency checking for optional SDK packages (anthropic, mistralai, boto3, aioboto3)
 - Added `MissingDependencyError` exception for missing optional dependencies
 - Added `library_utils.py` module with utility functions for PLX file discovery using `importlib.resources`
 - Added `class_utils.py` module with `are_classes_equivalent()` and `has_compatible_field()` functions
 - Added comprehensive unit tests for `CostRegistry`, `WorkingMemory`, and `ModuleInspector`
 - Added `ScanConfig` class with configurable excluded directories for library scanning
 - Added CSV export capabilities to `CostRegistry` with `save_to_csv()` and `to_records()` methods
 - Added default configuration template in `pipelex/kit/configs/pipelex.toml`

### Changed
 - Replaced package `toml` by `tomli` which is more modern and faster
 - Updated Gemini 2.0 model from `gemini-2.0-flash-exp` to `gemini-2.0-flash` with new pricing (input: $0.10, output: $0.40 per million tokens)
 - Updated Gemini 2.5 Series comment from '(when available)' to stable release
 - Updated `base-claude` from `claude-4-sonnet` to `claude-4.5-sonnet` across all presets
 - Updated kajson dependency from version `0.3.0` to `0.3.1`
 - Updated httpx dependency to `>=0.23.0,<1.0.0` for broader compatibility
 - Cleanup env example and better explain how to set up keys in README and docs
 - Changed Gemini routing from `google` backend to `pipelex_inference` backend
 - **BREAKING:** Major module reorganization - moved `tools/config/`, `tools/exceptions.py`, `tools/environment.py`, `tools/runtime_manager.py` to `system/` package structure (`system/configuration/`, `system/exceptions.py`, `system/environment.py`, `system/runtime.py`)
 - **BREAKING:** Reorganized registry modules from `tools/` to `system/registries/` (affects `class_registry_utils`, `func_registry`, `func_registry_utils`, `registry_models`)
 - **BREAKING:** Split `pipelex.core.stuffs.stuff_content` module into individual files per content type (affects imports: `StructuredContent`, `TextContent`, `ImageContent`, `ListContent`, `PDFContent`, `PageContent`, `NumberContent`, `HtmlContent`, `MermaidContent`, `TextAndImagesContent`)
 - **BREAKING:** Renamed package `pipelex.pipe_works` to `pipelex.pipe_run` and moved `PipeRunParams` classes into it
 - **BREAKING:** Cost reporting changed from Excel (xlsx) to CSV format using native Python csv module instead of pandas
 - Renamed `ConfigManager` to `ConfigLoader`
 - Renamed `PipelexRegistryModels` to `CoreRegistryModels`
 - Renamed `PipelexTestModels` to `TestRegistryModels`
 - Renamed `generate_jinja2_context()` to `generate_context()` in `WorkingMemory` and `ContextProviderAbstract`
 - Renamed `ConceptProviderAbstract` to `ConceptLibraryAbstract`
 - Renamed `DomainProviderAbstract` to `DomainLibraryAbstract`
 - Renamed `PipeProviderAbstract` to `PipeLibraryAbstract`
 - Renamed `PipeInputSpec` to `InputRequirements`
 - Renamed `PipeInputSpecFactory` to `InputRequirementsFactory`
 - Renamed `pipe_input.py` to `input_requirements.py`
 - Renamed `pipe_input_factory.py` to `input_requirements_factory.py`
 - Renamed `pipe_input_blueprint.py` to `input_requirement_blueprint.py`
 - Changed hub methods from `get_*_provider()` to `get_*_library()` pattern
 - Changed hub methods from `set_*_provider()` to `set_*_library()` pattern
 - Changed `PipeLLM` validation to check all inputs are in required variables
 - Updated `LLMPromptSpec` to handle image collections (lists/tuples) in addition to single images
 - Changed Mermaid diagram URL generation from `/img/` to `/svg/` endpoint
 - Changed `PipeLLMPromptTemplate.make_llm_prompt()` to private method `_make_llm_prompt()`
 - Updated pipe-builder prompts to include concept specs for better context
 - Updated `PipelexBundleSpec.to_blueprint()` to sort pipes by dependencies before creating bundle
 - Changed exception base class from `PipelexError` to `PipelexException` throughout codebase
 - Updated Makefile pyright target to use `--pythonpath` flag correctly
 - Enhanced `LibraryManager` to use `importlib.resources` for reliable PLX file discovery across all installation modes (wheel, source, relative path)
 - Simplified `FuncRegistryUtils` to exclusively register functions with `@pipe_func` decorator (removed `decorator_names` and `require_decorator` parameters)
 - Updated `ReportingManager` to get config directly instead of via constructor parameter
 - Updated PipeFunc documentation to reflect `@pipe_func()` decorator requirement and auto-discovery from anywhere in project
 - Added warnings about module-level code execution during auto-discovery to PipeFunc and StructuredContent documentation

### Fixed
 - Fixed Makefile target `pyright` to use correct pythonpath flag
 - Fixed bug with inputs of the `PipeLLM` where image inputs couldn't be used and tagged in prompts
 - Fixed image input handling in `LLMPromptSpec` to support both single images and image collections
 - Fixed template preprocessing to handle jinja2 templates correctly
 - Fixed hard dependencies by moving imports to function scope in model_lists.py
 - Updated README badge URL to point to main branch instead of feature/pipe-builder branch

### Removed
 - Removed centralized `pipelex_libraries` folder system and `pipelex init libraries` command
 - Removed config path parameters from `Pipelex.make()` (`relative_config_folder_path`, `config_folder_path`, `from_file`)
 - Removed Gemini 1.5 series models: `gemini-1.5-pro`, `gemini-1.5-flash`, and `gemini-1.5-flash-8b`
 - Removed `base_templates.toml` file (generic prompts moved to `pipelex.toml`)
 - Removed `gpt-5-mini` from possible models in pipe-builder
 - Removed useless functions in `LLMJobFactory`: `make_llm_job_from_prompt_factory()`, `make_llm_job_from_prompt_template()`, `make_llm_job_from_prompt_contents()`
 - Removed `add_or_update_pipe()` method from PipeLibrary
 - Removed `get_optional_library_manager()` method from PipelexHub
 - Removed `get_optional_domain_provider()` and `get_optional_concept_provider()` methods from hub
 - Removed unused test fixtures (apple, cherry, blueberry, concept_provider, pretty) from conftest.py
 - Removed some Vision/Image description pipes from the base library, because we doubt they were useful as they were
 - Removed pandas and openpyxl dependencies (including stubs: pandas-stubs, types-openpyxl)
 - Removed Excel file generation for cost reports and `to_dataframe()` method from `CostRegistry`
 - Removed `should_warn_if_already_registered` parameter from `func_registry.register_function()`
 - Removed `decorator_names` and `require_decorator` parameters from `FuncRegistryUtils` methods
 - Removed `_find_plx_files_in_dir()` and `_get_pipelex_plx_files_from_dirs()` methods from `LibraryManager` (refactored to `library_utils` module)
 - Removed hardcoded excluded directories from `ClassRegistryUtils` and `FuncRegistryUtils` (now use `ScanConfig`)
 - Removed `are_classes_equivalent()` and `has_compatible_field()` methods from `ClassRegistryUtils` (moved to `class_utils` module)

## [v0.11.0] - 2025-10-01

### Highlights

- **New pipe builder** pipeline to generate Pipes based on a brief in natural language: use the cli `pipelex build pipe "Your task"` to build the pipe.
- **New observer system:** inject your own class to observe and trace all details before and after each pipe run. We also provide a local observer that dumps the payloads to local JSONL files = new-line delilmited json, i.e. one json object per line.
- **Full refactoring of OCR and Image Generation** to use the same patterns as `LLM` workers and pipes.

### Added

 - Added `claude-4.5-sonnet` to the model deck.
 - Added a badge on the `README.md` to display the number of tests.
 - Added new test cases for environment variable functions
 - Added new documentation for `PipeFunc` on how to register functions.
 - Added `pipelex show models [BACKEND_NAME]` command to list available models from a specific backend.

### Changed 

 - Renamed `llm_deck` terminology to `model_deck` throughout codebase and documentation, now that it's also used for OCR and Image Generation models
 - Renamed `is_gha_testing` property to `is_ci_testing` in RuntimeManager
 - Refactored `all_env_vars_are_set()` function to only accept a list of keys, single string support now uses `is_env_var_set()`
 - Modified `any_env_var_is_placeholder()` to use new placeholder detection logic
 - Updated test environment setup to use dynamic placeholder generation instead of hardcoded values

### Fixed
 - Fixed logic error in `any_env_var_is_placeholder()` function - now correctly returns False when no placeholders are found

### Removed
 - Removed `get_rooted_path()` and `get_env_rooted_path()` utility functions which were not used
 - Removed hardcoded placeholder dictionary and `ENV_DUMMY_PLACEHOLDER_VALUE` constant in test setup
 - Removed function `run_pipe_code` in pipe router because it was not relevant (used mostly in tests)
 - Remove the use of `PipeCompose` in `PipeCondition`, to only use jinja2 directly, through the `ContentGenerator`
 - Remove the template libraries from the pipelex libraries.
 - Removed `claude-3.5-sonnet` and `claude-3.5-sonnet-v2` from the model deck.

## [v0.10.2] - 2025-09-18

### Added

- Unified OCR system using model handles instead of separate OcrHandle enum
- ModelType enum supporting LLM and TEXT_EXTRACTOR types  
- Enhanced error handling in library loading with better validation messages
- Config template management with `config-template` and `cft` Makefile targets to update templates from the `.pipelex/` directory

### Changed

- ⚠️ Breaking changes:
  - Renamed `ocr_handle` to `ocr_model` in `PipeExtract` blueprint, so you'll need to update your PLX code accordingly
  - Updated .env.example file with slightly modified key names (more standard).
- OCR system now uses InferenceModelSpec with unified model handles
- Renamed `get_llm_deck()` to `get_model_deck()` and updated parameter names from `llm_handle` to `model_handle`
- Simplified OCR worker factory using plugin SDK matching
- Enhanced plugin system compatibility with InferenceModelSpec
- Improved error messages throughout system
- Improved management of placeholder environment variables for unit tests

### Removed

- Legacy OCR classes: OcrHandle, OcrPlatform, OcrEngine, OcrEngineFactory
- Obsolete configuration fields and setup methods
- PipelexFileError exception class


## [v0.10.1] - 2025-09-17

### Changed

- Enabled all backends, still required to pass all unit tests.
- A few tweaks to the base model deck.

## [v0.10.0] - 2025-09-17

### Highlight: New Inference Backend Configuration System

We've completely redesigned how LLMs are configured and accessed in Pipelex, making it more flexible and easier to get started:

- **Get started in seconds** with [Pipelex Inference](home/7-configuration/config-technical/inference-backend-config.md): Use a single API key to access all major LLM providers (OpenAI, Anthropic, Google, Mistral, and more)
- **Flexible backend configuration**: Configure multiple inference backends (Azure OpenAI, Amazon Bedrock, Vertex AI, etc.) through simple TOML files in `.pipelex/inference/`
- **Smart model routing**: Automatically route models to the right backend using [routing profiles](home/7-configuration/config-technical/inference-backend-config.md#routing-profiles) with pattern matching
- **User-friendly aliases**: Define shortcuts like `best-claude` → `claude-4.1-opus` with optional fallback chains
- **Cost-aware model specs**: Each model includes detailed pricing, capabilities, and constraints for better cost management

For complete details, see the [Inference Backend Configuration](home/7-configuration/config-technical/inference-backend-config.md) documentation.

### Added

- New inference backend configuration system in `.pipelex/inference/` directory
- Support for 10+ inference backends: OpenAI, Anthropic, Azure OpenAI, Amazon Bedrock, Mistral, Vertex AI, XAI, BlackboxAI, Perplexity, Ollama, and **Pipelex Inference**
- Model routing profiles with pattern matching (`*model*`, `model*`, `*model`)
- Model aliases with waterfall fallback chains
- Environment variable and secret substitution in TOML configs (`${VAR}` and `${secret:KEY}`)
- Comprehensive model specifications with detailed cost categories
- Unified plugin SDK registry for all backends
- CI environment detection with automatic placeholder API keys for testing
- Improved `pipelex init config` command to copy entire configuration template directory structure to `.pipelex/` with smart file handling (skips existing files, shows clear progress messages)
- Added `FuncRegistryUtils` to register functions in a pipelex folder that have a specific signature.
- Added `mistral-medium` and `mistral-medium-2508` to the Mistral backend configuration.
- Added `gemini-2.5-flash` to the VertexAI backend configuration.

### Changed

- LLM configuration moved from `pipelex_libraries/llm_deck/` to `.pipelex/inference/deck/`
- LLM handles simplified to direct model names or user-defined aliases
- Model deck completely redesigned with inference models, aliases, and presets
- Plugin system refactored to use backend-specific TOML configuration
- Token categories renamed to cost categories with expanded types

### Fixed

- Improved error messages for missing environment variables
- Enhanced TOML configuration validation
- More robust model routing and backend selection

### Removed

- Legacy LLM model library system (`llm_integrations/` directory)
- Platform-specific configuration classes (AnthropicConfig, OpenAIConfig, etc.)
- Deprecated LLM engine blueprint and factory classes
- Old LLM platform and family enumerations

### Security

- Enhanced secret management with secure fallback patterns
- Improved API key handling through centralized backend configuration

## [v0.9.5] - 2025-09-12

### Highlight
 - Pinned `instructor` to version `<1.10.0` to avoid errors with `mypy`

### Added
 - Added `PIPELEX_INFERENCE` LLM family enum value
 - Added support for `PIPELEX_INFERENCE` in OpenAI LLM worker
 - Added Azure OpenAI platform support for Grok models (`grok-3` and `grok-3-mini`)
 - Added debug logging for `PipeParallel` output contents
 - Added `TOML` file filtering in LLM model library loading
 - Added error handling for Unicode decode errors in LLM model library
 - Added new test model configurations for `pipelex` and `vertex_ai` platforms

### Changed
 - Improved error messages in `StuffFactory` to include concept code and stuff name
 - Disabled `is_gen_object_supported` for all Grok models (`grok-3`, `grok-3-mini`, `grok-3-fast`)
 - Updated test configurations to use different LLM models and platforms
 - Modified `Jinja2` filter to use default `TagStyle.TICKS` instead of raising error
 - Added proper error handling for Unicode decode errors when loading model libraries
 - Improved error handling in Anthropic plugin tests with specific `AuthenticationError` handling
 - Image handling in `AnthropicFactory` now converts image URLs to `base64` data URLs with proper MIME type prefix
 - Put back Discord link in `README.md`

### Fixed
 - Pinned `instructor` to version `<1.10.0` to avoid errors with `mypy`

## [v0.9.4] - 2025-09-06

### Added

- Added support for BlackboxAI models

## [v0.9.3] - 2025-09-06

### Added

 - Better support for BlackboxAI IDE
 - VS Code extensions recommendations file with Pipelex, Ruff, and MyPy extensions
 - File association for .plx files in VS Code settings

## [v0.9.2] - 2025-09-05

### Fixed

- Fix the rules of all agents.

### Added

- Added agent rule for copilot
- Added a rule to forbidden structuring basic text concepts

## [v0.9.1] - 2025-09-05

### Fixed
- Fixed many inconsistencies in the documentation.

## [v0.9.0] - 2025-09-02

### Refacto

- Changed the pipeline file extension from `.toml` to `.plx`: Updated the LibraryManager in consequence.

## Fixed

- Fixed the `structuring_method` behavior in the `PipeLLM` pipe: Putting it to `preliminary_text`, the `PipeLLM` will always generate text before generating the structure -> Reliability increased by a lot.

### Fixed

- Fixed a bug in the `needed_inputs` method of the `PipeSequence` pipe.

### Changed

- `dry_run_pipe` now returns a `DryRunOutput` object instead of a `str` with additional information.
- Updated `cocode` dependency from version `v0.0.10` to `v0.0.15`.

### Added

- Added the `FuncRegistryUtils` class to register functions in the library.

## [v0.8.1] - 2025-08-27

### Bugfix

- Bugfix: Fixed the `PipeFunc` output concept code and structure class name in the dry run.

## [v0.8.0] - 2025-08-27

### Refactor

- Refactored the concepts: Blueprints are now more explicit, and hold only concept strings or code. Pipes hold concept instances.
- Organized code: Created subfolders for controller and operator pipes.
- Say goodbye to `PipeLLMPrompt`.
- Removed the `PipeCompose` and `PipeLLMPrompt` from the `PipeLLM`.

### Added

- Added a lot of unit tests.
- Loading the library can now be done from toml file or from `PipelexBundleBlueprint`.

### Fixed

- Backported `backports.strenum` to `>=1.3.0` to support Python 3.10 now in dependencies and not in optional dependencies.

## [v0.7.0] - 2025-08-20

### Refactor

- Refactored the Blueprints. Introduces the `PipelexInterpreter` that interprets the Pipelex language and creates the Pipelex Blueprints (and vice versa)
- Modified the way we declare pipes. Use the field `type = "PipeLLM"` instead of field `PipeLLM`. (Same for all pipes)
- Refactored the `LibraryManager`.
- Refactored CLI commands and added new ones. Modified CLI command structure:
  - **`pipelex init`** - Initialization commands
    - `pipelex init libraries [DIRECTORY]` - Initialize pipelex libraries (creates `pipelex_libraries` folder)
    - `pipelex init config` - Initialize pipelex configuration (creates `pipelex.toml`)
  - **`pipelex validate`** - Validation and dry-run commands  
    - `pipelex validate all -c pipelex/libraries` - Validate all libraries and dry-run all pipes
    - `pipelex validate pipe PIPE_CODE` - Dry run a single pipe by its code
  - **`pipelex show`** - Show and list commands
    - `pipelex show config` - Show the pipelex configuration
    - `pipelex show pipes` - List all available pipes with descriptions
    - `pipelex show pipe PIPE_CODE` - Show a single pipe definition
  - **`pipelex migrate`** - Migration commands
    - `pipelex migrate run` - Migrate TOML files to new syntax (with `--dry-run` and `--backups` options)
  - **`pipelex build`** - Build artifacts like pipeline blueprints
    - `pipelex build draft PIPELINE_NAME` - Generate a draft pipeline
    - `pipelex build blueprint PIPELINE_NAME` - Generate a pipeline blueprint
- Organized `concept`, `pipe`, `working_memory`, `stuff` files into folders.

### Changed

- Allow `aiofiles` version `>=23.2.1`
- GHA Cla assistant fixed with Github App

### Added

- New LLM families `LLMFamily.GPT_5`, `LLMFamily.GPT_5_CHAT` and `LLMFamily.CLAUDE_4_1`
- Added support for Claude 4.1 and GPT 5 models (inc. mini, nano, chat)
- New Pipe that generates pipe. Pipe code: `build_blueprint`
- New tests. Especially for the `PipelexInterpreter`.
- Migration files and cli commands to migrate Pipelex language to new syntax.
- Introduces `PipelexBundle`, which correspond to the python paradigm of the Pipelex TOML syntax.

## [v0.6.10] - 2025-08-02

### Added
 - New test file for source code manipulation functions (tests/cases/source_code.py)
 - New integration test for PipeFunc functionality (tests/integration/pipelex/pipes/pipe_operator/pipe_func/test_pipe_func.py)
 - New package structure file for pipe_func tests (__init__.py)
 - Simplified input memory creation for native concepts (Text, Image, PDF) in pipeline execution
 - Added Pipeline requests link to GitHub issue template config

### Changed
 - Updated pipeline execution documentation and examples to use input_memory instead of working_memory
 - Renamed pipeline from 'extract_page_contents_from_pdf' to 'ocr_page_contents_from_pdf'
 - Renamed pipeline from 'extract_page_contents_and_views_from_pdf' to 'ocr_page_contents_and_views_from_pdf'
 - Updated cocode dependency from version 0.0.6 to 0.0.9

### Fixed
 - Fixed typo in pipeline description ('aspage views' to 'as full page views')

### Removed
 - Removed WorkingMemoryFactory and StuffFactory imports from pipeline execution examples
 - Removed working memory creation code from pipeline examples


## [v0.6.9] - 2025-07-26

### Changed

Simplified input memory:

- The concept code can now be provided with arg named `concept` in addition to `concept_code`
- You can pass a simple string to create a `Text` stuff


## [v0.6.8] - 2025-07-25

### Added
- New method `make_stuff_using_concept_name_and_search_domains` in `StuffFactory` for creating stuff using concept names and search domains.
- New method `make_stuff_from_stuff_content_using_search_domains` in `StuffFactory` for creating stuff from stuff content using search domains.
- New method `make_from_implicit_memory` in `WorkingMemoryFactory` for creating working memory from implicit memory.
- New method `create_mock_content` in `WorkingMemoryFactory` for creating mock content for requirements.

### Changed
- Refactored `PipeInput` to use `InputRequirement` and `TypedNamedInputRequirement` classes instead of plain strings for input specifications.
- Updated `WorkingMemoryFactory` to handle `PipelineInputs` instead of `CompactMemory`.
- Replaced `ExecutePipelineException` with `PipelineInputError` in `execute_pipeline` function.
- Updated `PipeBatch`, `PipeCondition`, `PipeParallel`, `PipeSequence`, `PipeFunc`, `PipeImgGen`, `PipeCompose`, `PipeLLM`, and `PipeExtract` classes to use `InputRequirement` for input handling.
- Updated `PipeInput` creation in various test files to use `make_from_dict` method.
- Updated `pyproject.toml` to exclude `pypdfium2` version `4.30.1`.
- Updated `Jinja2TemplateCategory` to handle HTML and Markdown templates differently.

### Fixed
- Corrected error messages in `StuffFactory` and `StuffContentFactory` to provide more detailed information about exceptions.

## [v0.6.7] - 2025-07-24

### Removed
- Removed the `structure_classes` parameter from the `Pipelex` class.

## [v0.6.6] - 2025-07-24

### Added
- Added a new method `verify_content_type` in the `Stuff` class to verify and convert content to the expected type.
- Added `cocode==0.0.6` to the development dependencies in `pyproject.toml`.

### Changed
- Updated `Stuff` class methods to use the new `verify_content_type` method for content verification.
- Updated `vertexai.toml` to change LLM IDs from preview models to released models: `gemini-2.5-pro` and `gemini-2.5-flash`.

### Removed
- Removed `reinitlibraries`, `rl`, `v`, and `init` targets from the Makefile.

## [v0.6.5] - 2025-07-21

### Fixed

- In the documentation, fixed the use of `execute_pipeline`.

## [v0.6.4] - 2025-07-19

- Fixed the `README.md` link to the documentation

## [v0.6.3] - 2025-07-18

### Changed
- Enhanced `Stuff.content_as()` method with improved type validation logic - now attempts model validation when `isinstance` check fails

## [v0.6.2] - 2025-07-18

### Added
- New `dry-run-pipe` cli command to dry run a single pipe by its code
- New `show-pipe` cli command to display pipe definitions from the pipe library
- New `dry_run_single_pipe()` function for running individual pipe dry runs

### Changed
- Updated `init-libraries` command to accept a directory argument and create `pipelex_libraries` folder in specified location
- Updated `validate` command to use `-c` flag for the config folder path

## [v0.6.1] - 2025-07-16

- Can execute pipelines with `input_memory`: It is a `CompactMemory: Dict[str, Dict[str, Any]]`

## [v0.6.0] - 2025-07-15

### Changed 
- **Enhanced `Pipelex.make()` method**: Complete overhaul of the initialization method with new path configuration options and robust validation:
  - Added `relative_config_folder_path` and `absolute_config_folder_path` parameters for flexible config folder specification
  - The `from_file` parameter controls path resolution: if `True` (default), relative paths are resolved relative to the caller's file location; if `False`, relative to the current working directory (useful for CLI scenarios)
- Renamed Makefile targets like `make doc` to `make docs` for consistency

### Added
- Added github action for inference tests
- `load_json_list_from_path` function in `pipelex.tools.misc.file_utils`: Loads a JSON file and ensures it contains a list.
- Added issue templates
- Updated Azure/OpenAI integrations, using dated deployment names systematically

## [v0.5.2] - 2025-07-11

- log a warning when dry running a `PipeFunc`
- Update Readme.md

## [v0.5.1] - 2025-07-09

## Fixed

- Fixed the `ConceptFactory.make_from_blueprint` method: Concepts defined in single-line format no longer automatically refine `TextContent` when a structure class with the same name exists
- `ConceptFactory.make_concept_from_definition` is now `ConceptFactory.make_concept_from_definition_str`

## Added

- Bumped `kajson` to `v0.3.0`: Introducing `MetaSingleton` for better singleton management
- Unit tests for `ConceptLibrary.is_compatible_by_concept_code`

## [v0.5.0] - 2025-07-01

### Highlight: Vibe Coding an AI workflow becomes a reality

**Create AI workflows from natural language without writing code** - The combination of Pipelex's declarative language, comprehensive Cursor rules, and robust validation tools enables AI assistants to autonomously iterate on pipelines until all errors are resolved and workflows are ready to run.

### Added

- **Complete Dry Run & Static Validation System** - A comprehensive validation framework that catches configuration and pipeline errors before any expensive inference operations.
- **WorkingMemoryFactory Enhancement**: New `make_for_dry_run()` method creates working memory with realistic mock objects for zero-cost pipeline testing
- **Enhanced Dry Run System**: Complete dry run support for all pipe controllers (`PipeCondition`, `PipeParallel`, `PipeBatch`) with mock data generation using `polyfactory`
- **Comprehensive Static Validation**: Enhanced static validation with configurable error handling for missing/extraneous input variables and domain validation
- **TOML File Validation**: Automatic detection and prevention of trailing whitespaces, formatting issues, and compilation blockers in pipeline files
- **Pipeline Testing Framework**: New `dry_run_all_pipes()` method enables comprehensive testing of entire pipeline libraries
- **Enhanced Library Loading**: Improved error handling and validation during TOML file loading with proper exception propagation

### Configuration

- **Dry Run Configuration**: New `allowed_to_fail_pipes` setting allows specific pipes (like infinite loop examples that fail on purpose) to be excluded from dry run validation
- **Static Validation Control**: Configurable error reactions (`raise`, `log`, `ignore`) for different validation error types

### Documentation & Development Experience

- **Cursor Rules Enhancement**: Comprehensive pipe controller documentation covering `PipeSequence`, `PipeCondition`, `PipeBatch`, and `PipeParallel`, improved PipeOperator documentation for `PipeLLM`, `PipeOCR`
- **Pipeline Validation CLI**: Enhanced `pipelex validate all -c pipelex/libraries` command with better error reporting and validation coverage
- **Improved Error Messages**: Better formatting and context for pipeline configuration errors

### Changed

- **Error Message Improvements**: Updated PipeCondition error messages to reference `expression_template` instead of deprecated `expression_jinja2`

## [v0.4.11] - 2025-06-30

- **LLM Settings Simplification**: Streamlined LLM choice system by removing complex `for_object_direct`, `for_object_list`, and `for_object_list_direct` options. LLM selection now uses a simpler fallback pattern: specific choice → text choice → overrides → defaults.
- **Image Model Updates**: Renamed `image_bytes` field to `base_64` in `PromptImageTypedBytes` for better consistency. Updated to use `CustomBaseModel` base class to benefit from bytes truncation when printing.

## [v0.4.10] - 2025-06-30

- Fixed a bad import statement

## [v0.4.9] - 2025-06-30

### Highlights

**Plugin System Refactoring** - Complete overhaul of the plugin architecture to support external LLM providers.

### Added

- **External Plugin Support**: New `LLMWorkerAbstract` base class for integrating custom LLM providers, and we don't mean only an OpenAI-SDK-based LLM with a custom endpoint, now the implementation can be anything, as long as it implements the `LLMWorkerAbstract` interface.
- **Plugin SDK Registry**: Better management of SDK instances with proper teardown handling
- **Enhanced Error Formatting**: Improved Pydantic validation error messages for enums

### Changed

- **Plugin Architecture**: Moved plugin system to dedicated `pipelex.plugins` package
- **LLM Workers**: Split into `LLMWorkerInternalAbstract` (for built-in providers) and `LLMWorkerAbstract` (for external plugins)
- **Configuration**: Plugin configs moved from main `pipelex.toml` to separate `pipelex_libraries/plugins/plugin_config.toml` (⚠️ breaking change)
- **Error Handling**: Standardized credential errors with new `CredentialsError` base class

## [v0.4.8] - 2025-06-26

- Added `StorageProviderAbstract`
- Updated the changelog of `v0.4.7`: Moved `Added StorageProviderAbstract` to `v0.4.8`

## [v0.4.7] - 2025-06-26

- Added an API serializer: introducing the `compact_memory`, a new way to encode/decode the working memory as json, for the API.
- When creating a Concept with no structure specified and no explicit `refines`, set it to refine `native.Text`
- `JobMetadata`: added `job_name`. Removed `top_job_id` and `wfid`
- `PipeOutput`: added `pipeline_run_id`

## [v0.4.6] - 2025-06-24

- Changed the link to the doc in the `README.md`: https://docs.pipelex.com

## [v0.4.5] - 2025-06-23

### Changed
- **Test structure overhaul**: Reorganized test directory structure for better organization:
  - Tests now separated into `unit/`, `integration/`, and `e2e/` directories
  - Created `tests/cases/` package for pure test data and constants
  - Created `tests/helpers/` package for test utilities
  - Cleaned up test imports and removed empty `__init__.py` files
- **Class registry refactoring**: Updated kajson from 0.1.6 to 0.2.0, adapted to changes in [Kajson](https://github.com/Pipelex/kajson)'s class registry with new `ClassRegistryUtils` (better separation of concerns)
- **Dependency updates**:
  - Added pytest-mock to dev dependencies for improved unit testing

### Added
- **Coverage commands**: New Makefile targets for test coverage analysis:
  - `make cov`: Run tests with coverage report
  - `make cov-missing` (or `make cm`): Show coverage with missing lines
- **Test configuration**: Set `xfail_strict = true` in pytest config for stricter test failure handling
- **Pydantic validation errors**: Enhanced error formatting to properly handle model_type errors

### Fixed
- **External links**: Removed broken Markdown target="_blank" syntax from MANIFESTO.md links
- **Variable naming consistency**: Fixed redundant naming in OpenAI config (openai_openai_config → openai_config)
- **Makefile optimization**: Removed parallel test execution (`-n auto`) from codex-tests, works better now

### Tests
- **Unit tests added**: New comprehensive unit tests for:
  - `ClassRegistryUtils`
  - `FuncRegistry` 
  - `ModuleInspector`
  - File finding utilities

## [v0.4.4] - 2025-06-20

### Fixed
- Changed the allowed base branch names in the GHA `guard-branches.yml`: `doc` -> `docs`
- Fixed `kajson` dependency (see [kajson v0.1.6 changelog](https://github.com/Pipelex/kajson/blob/main/CHANGELOG.md))

### Cursor rules
- Added Cursor rules for coding best practices and standards (including linting methods). Added TDD (Test Driven Development) rule on demand.
- Various changes

### Documentation
- Added documentation for referencing images in PipeLLM.
- Fixed typos

### Refactor
- Removed the `images` field from PipeLLM - images can now be referenced directly in the `inputs`
- Moved the list-pipes CLI function to the `PipeLibrary` class.

## [v0.4.3] - 2025-06-19

### Fixed
- **Removed deprecated Gemini 1.5 models**: Removed `gemini-1.5-flash` and `gemini-1.5-pro` from the VertexAI integration as they are no longer supported
- Fixed multiple import statements across the codebase

### Documentation
- **Enhanced MkDocs search**: Added search functionality to the documentation site
- **Proofreading improvements**: Fixed various typos and improved clarity across documentation

### Refactor
- Mini refactor: changed kajson dependency to `kajson==0.1.5` (instead of `>=`) to tolerate temporary breaking changes from kajson

## [v0.4.2] - 2025-06-17

- Fixed the inheritance config manager method (Undocumented feature, soon to be removed)
- Fixed the `deploy-doc.yml` GitHub Action
- Grouped the mkdocs dependencies in a single group `docs` in the `pyproject.toml` file

## [v0.4.1] - 2025-06-16

- Changed discord link to the new one: https://go.pipelex.com/discord
- Added `hello-world` example in the `cookbook-examples` of the documentation.

## [v0.4.0] - 2025-06-16

### Highlight: Complete documentation overhaul

- **MkDocs** setup for static web docs generation
    - **Material** for MkDocs theme, custom styling and navigation
    - Other plugins: meta-manager, glightbox
    - **GitHub Pages** deployment, mapped to [docs.pipelex.com](http://docs.pipelex.com)
    - Added GHA workflows for documentation deployment and validation
- **Added to docs:**
    - [**Manifesto**](https://docs.pipelex.com/manifesto/) explaining the Pipelex viewpoint
    - [**The Pipelex Paradigm**](https://docs.pipelex.com/pages/pipelex-paradigm-for-repeatable-ai-workflows/) explaining the fundamentals of Pipelex's solution
    - [**Cookbook examples](https://docs.pipelex.com/pages/cookbook-examples/)** presented and explained, commented code, some event with [mermaid](https://docs.pipelex.com/pages/cookbook-examples/invoice-extractor/) [flow](https://docs.pipelex.com/pages/cookbook-examples/extract-gantt/) [charts](https://docs.pipelex.com/pages/cookbook-examples/write-tweet/)
    - And plenty of details about **using Pipelex** and **developing for Pipelex,** from **structured generation** to PipeOperators (**LLM**, **Image generation**, **OCR**…) to PipeControllers (**Sequence**, **Parallel**, **Batch**, **Condition**…), workflow **optimization**, workflow static **validation** and dry run… there's still work to do, but we move fast!
- **Also a major update of Cursor rules**

### Tooling Improvements

- Pipeline tracking: restored **visual flowchart generation using Mermaid**
- Enhanced dry run configuration: added more granular control with `nb_list_items`, `nb_extract_pages`, and `image_urls`
- New feature flags: better control over pipeline tracking, activity tracking, and reporting
- Improved OCR configuration: handle image file type for Mistral-OCR, added `default_page_views_dpi` setting
- Enhanced LLM configuration: **better prompting for structured generation with automatic schema insertion** for two-step structuring: generate plain text and then structure via Json
- Better logging: Enhanced log truncation and display for large objects like image bytes (there are still cases to deal with)

### Refactor

**Concept system refactoring**

- Improved concept code factory with better domain handling, so you no longer need the `native` domain prefix for native domains, you can just call them by their names: `Text`, `Image`, `PDF`, `Page`, `Number`…
- Concept `refines` attribute can now be a string for single refined concepts (the most common case)

### Breaking Changes

- File structure changes: documentation moved from `doc/` to `docs/`
- Configuration changes: some configuration keys have been renamed or restructured
- `StuffFactory.make_stuff()` argument `concept_code` renamed to `concept_str` to explicitly support concepts without fully qualified domains (e.g., `Text` or `PDF` implicitly `native` )
- Some method signatures have been updated

### Tests

- **Added Concept refinement validation:** `TestConceptRefinesValidationFunction` and `TestConceptPydanticFieldValidation` ensure proper concept inheritance and field validation

## [v0.3.2] - 2025-06-13

- Improved automatic insertion of class structure from BaseModel into prompts, based on the PipeLLM's `output_concept`. New unit test included.
- The ReportingManager now reports costs for all pipeline IDs when no `pipeline_run_id` is specified.
- The `make_from_str` method from the `StuffFactory` class now uses `Text` context by default.

## [v0.3.1] - 2025-06-10

### Added
- New pytest marker `dry_runnable` for tests that can run without inference.
- Enhanced `make` targets with dry-run capabilities for improved test coverage:
  - `make test-xdist` (or `make t`): Runs all non-inference tests **plus inference tests** that support dry-runs - fast and resource-efficient
  - `make test-inference` (or `make ti`): Runs tests requiring actual inference, with actual inference (slow and costly)
- Parallel test execution using `pytest-xdist` (`-n auto`) enabled for:
  - GitHub Actions workflows
  - Codex test targets
  
### Changed
- Domain validation is now less restrictive in pipeline TOML: the `description` attribute is now `Optional`

## [v0.3.0] - 2025-06-09

### Highlights

- **Structured Input Specifications**: Pipe inputs are now defined as a dictionary mapping a required variable name to a concept code (`required_variable` -> `concept_code`). This replaces the previous single `input` field and allows for multiple, named inputs, making pipes more powerful and explicit. This is a **breaking change**.
- **Static Validation for Inference Pipes**: You can now catch configuration and input mistakes in your pipelines *before* running any operations. This static validation checks `PipeLLM`, `PipeExtract`, and `PipeImgGen`. Static validation for controller pipes (PipeSequence, PipeParallel…) will come in a future release.
    - Configure the behavior for different error types using the `static_validation_config` section in your settings. For each error type, choose to `raise`, `log`, or `ignore`.
- **Dry Run Mode for Zero-Cost Pipeline Validation**: A powerful dry-run mode allows you to test entire pipelines without making any actual inference calls. It's fast, costs nothing, works offline, and is perfect for linting and validating pipeline logic.
    - The new `dry_run_config` lets you control settings, like disabling Jinja2 rendering during a dry run.
    - This feature leverages `polyfactory` to generate mock Pydantic models for simulated outputs.
    - Error handling for bad inputs during `run_pipe` has been improved and is fully effective in dry-run mode.
    - One limitation: currently, dry running doesn't work when the pipeline uses a PipeCondition. This will be fixed in a future release.

### Added

- **`native.Anything` Concept**: A new flexible native concept that is compatible with any other concept, simplifying pipe definitions where input types can vary.
- Added dependency on `polyfactory` for mock Pydantic model generation in dry-run mode.

### Changed

- **Refactored Cognitive Workers**: The abstraction for `LLM`, `ImgGen`, and `Ocr` workers has been elegantly simplified. The old decorator-based approach (`..._job_func`) has been replaced with a more robust pattern: a public base method now handles pre- and post-execution logic while calling a private abstract method that each worker implements.
- The `b64_image_bytes` field in `PromptImageBytes` was renamed to `base_64` for better consistency.

### Fixed

- Resolved a logged error related to the pipe stack when using `PipeParallel`.
- The pipe tracker functionality has been restored. It no longer crashes when using nested object attributes (e.g., `my_object.attribute`) as pipe inputs.

### Tests

- A new pytest command-line option `--pipe-run-mode` has been added to switch between `live` and `dry` runs (default is `dry`). All pipe tests now respect this mode.
- Introduced the `pipelex_api` pytest marker for tests related to the Pipelex API client, separating them from general `inference` or `llm` tests.
- Added a `make test-pipelex-api` target (shorthand: `make ta`) to exclusively run these new API client tests.

### Removed

- The `llm_job_func.py` file and the associated decorators have been removed as part of the cognitive worker refactoring.

## [v0.2.14] - 2025-06-06

- Added a feature flag for the `ReportingManager` in the config: 
```bash
[pipelex]
[pipelex.feature_config]
is_reporting_enabled = true
```
- Moved the reporting config form the `cogt`config to the Pipelex config.

## [v0.2.13] - 2025-06-06

- Added Discord badge on the Readme. Join the community! -> https://go.pipelex.com/discord
- Added a client for the Pipelex API. Join the waitlist -> https://www.pipelex.com/signup
- Removed the `run_pipe_code` function. Replaced by `execute_pipeline` in `pipelex.pipeline.execute`.
- Added llm deck `llm_for_img_to_text`.
- Renamed `InferenceReportManager` to `ReportingManager`: It can report more than Inference cost. Renamed `InferenceReportDelegate` to `ReportingProtocol`.
- Added an injection of dependency for `ReportingManager`
- pipelex cli: fixed some bugs

## [v0.2.12] - 2025-06-03

- pipelex cli: Split `pipelex init` into 2 separate functions: `pipelex init-libraries` and `pipelex init-config`
- Fixed the inheritance config manager method
- Rename Mission to Pipeline
- Enable to start a pipeline and let in run in the background, getting it's run id, but not waiting for the output
- `Makefile`: avoid defaulting pytest to verbose. Setup target `make test-xdist` = Run unit tests with `xdist`, make it the default for shorthand `make t`. The old `make t` is now `make tp` (test-with-prints)
- Added `mistral-small-3.1` and `qwen3:8b`
- Fix template pre-processor: don't try and substitute a dollar numerical like $10 or @25
- Refactor with less "OpenAI" naming for non-openai stuff that just uses the OpenAI SDK

## [v0.2.11] - 2025-06-02

- HotFix for v0.2.10 👇 regarding the new pipelex/pipelex_init.toml`

## [v0.2.10] - 2025-06-02

### Highlights

**Python Support Expansion** - We're no longer tied to Python 3.11! Now supporting Python 3.10, 3.11, 3.12, and 3.13 with full CI coverage across all versions.

**Major Model Additions** - Claude 4 (Opus & Sonnet), Grok-3, and GPT-4 image generation are now in the house.

### Pipeline Base Library update
- **New pipe** - `ocr_page_contents_and_views_from_pdf` transferred from cookbook to base library (congrats on the promotion!). This pipe extracts text, linked images, **AND** page_view images (rendered pages) - it's very useful if you want to use Vision in follow-up pipes

### Added

- **Template preprocessor** - New `@?` token prefix for optional variable insertion - if a variable doesn't exist, we gracefully skip it instead of throwing exceptions
- **Claude 4 support** - Both Opus and Sonnet variants, available through Anthropic SDK (direct & Bedrock) plus Bedrock SDK. Includes specific max_tokens limit reduction to prevent timeout/streaming issues (temporary workaround)
- **Grok-3 family support** - Full support via OpenAI SDK for X.AI's latest models  
- **GPT-4 image generation** - New `gpt-image-1` model through OpenAI SDK, available via PipeImgGen. Currently saves local files (addressing in next release)
- **Gemini update** - Added latest `gemini-2.5-pro` to the lineup
- **Image generation enhancements** - Better quality controls, improved background handling options, auto-adapts to different models: Flux, SDXL and now gpt-image-1

### Refactored

- Moved subpackage `plugin` to the same level as `cogt` within **pipelex** for better visibility
- Major cleanup in the unit tests, hierarchy significantly flattened
- Strengthened error handling throughout inference flows and template preprocessing
- Added `make test-quiet` (shorthand `tq`) to Makefile to run tests without capturing outputs (i.e. without pytest `-s` option)
- Stopped using Fixtures for `pipe_router` and `content_generator`: we're now always getting the singleton from `pipelex.hub`


### Fixed

- **Perplexity integration** - Fixed breaking changes from recent updates

### Dependencies

- Added **pytest-xdist** to run unit tests in parallel on multiple CPUs. Not yet integrated into the Makefile, so run it manually with `pytest -n auto` (without inference) or `pytest -n auto -m "inference"` (inference only). 
- Swapped pytest-pretty for pytest-sugar - because readable test names > pretty tables
- Updated instructor to v1.8.3
- All dependencies tested against Python 3.10, 3.11, 3.12, and 3.13

### Tests

- TestTemplatePreprocessor
- TestImgGenByOpenAIGpt
- TestImageGeneration
- TestPipeImgGen


## [v0.2.9] - 2025-05-30

- Include `pyproject.toml` inside the project build.
- Fix `ImgGenEngineFactory`: image generation (imgg) handle required format is `platform/model_name`
- pipelex cli: Added `list-pipes` method that can list all the available pipes along with their descriptions.
- Use a minimum version for `uv` instead of a fixed version
- Implement `AGENTS.md` for Codex
- Add tests for some of the `tools.misc`
- pipelex cli: Rename `pipelex run-setup` to `pipelex validate all -c pipelex/libraries`

## [v0.2.8] - 2025-05-28

- Replaced `poetry` by `uv` for dependency management.
- Simplify llm provider config: All the API keys, urls, and regions now live in the `.env`.
- Added logging level `OFF`, prevents any log from hitting the console

## [v0.2.7] - 2025-05-26

- Reboot repository

## [v0.2.6] - 2025-05-26

- Refactor: use `ActivityManagerProtocol`, rename `BaseModelTypeVar`

## [v0.2.5] - 2025-05-25

- Add custom LLM integration via OpenAI sdk with custom `base_url`

## [v0.2.4] - 2025-05-25

- Tidy tools
- Tidy inference API plugins
- Tidy WIP feature `ActivityManager`

## [v0.2.2] - 2025-05-22

- Simplify the use of native concepts
- Include "page views" in the outputs of Ocr features

## [v0.2.1] - 2025-05-22

- Added `OcrWorkerAbstract` and `MistralOcrWorker`, along with `PipeExtract` for OCR processing of images and PDFs.
- Introduced `MissionManager` for managing missions, cost reports, and activity tracking.
- Added detection and handling for pipe stack overflow, configurable with `pipe_stack_limit`.
- More possibilities for dependency injection and better class structure.
- Misc updates including simplified PR template, LLM deck overrides, removal of unused config vars, and disabling of an LLM platform id.

## [v0.2.0] - 2025-05-19

- Added OCR, thanks to Mistral
- Refactoring and cleanup

## [v0.1.14] - 2025-05-13

- Initial release 🎉
