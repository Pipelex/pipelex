# Changelog

## [v0.9.2] - 2025-09-05

### Fixed

- Fix the rules of all agents.

### Added

- Added agent rule for copilot
- Added a rule to forbiden structuring basic text concepts

## [v0.9.1] - 2025-09-05

### Fixed
- Fixed many inconsistencies in the documentation.

## [v0.9.0] - 2025-09-02

### Refacto

- Changed the pipeline file extension from `.toml` to `.plx`: Updated the LibraryManager in consequence.

## Fixed

- Fixed the `structuring_method` behavior in the `PipeLLM` pipe: Putting it to `preliminary_text`, the `PipeLLM` will always generate text before generating the structure -> Reliability increased by a lot.

### Changed

- Updated `cocode` dependency from version `v0.0.10` to `v0.0.15`.

## [v0.8.1] - 2025-08-27

### Bugfix

- Bugfix: Fixed the `PipeFunc` output concept code and structure class name in the dry run.

## [v0.8.0] - 2025-08-27

### Refactor

- Refactored the concepts: Blueprints are now more explicit, and hold only concept strings or code. Pipes hold concept instances.
- Organized code: Created subfolders for controller and operator pipes.
- Say goodbye to `PipeLLMPrompt`.
- Removed the `PipeJinja2` and `PipeLLMPrompt` from the `PipeLLM`.

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
- Refactored `PipeInputSpec` to use `InputRequirement` and `TypedNamedInputRequirement` classes instead of plain strings for input specifications.
- Updated `WorkingMemoryFactory` to handle `ImplicitMemory` instead of `CompactMemory`.
- Replaced `ExecutePipelineException` with `PipelineInputError` in `execute_pipeline` function.
- Updated `PipeBatch`, `PipeCondition`, `PipeParallel`, `PipeSequence`, `PipeFunc`, `PipeImgGen`, `PipeJinja2`, `PipeLLM`, and `PipeOcr` classes to use `InputRequirement` for input handling.
- Updated `PipeInputSpec` creation in various test files to use `make_from_dict` method.
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

- **OCR Input Standardization**: Changed OCR pipe input parameter naming to consistently use `ocr_input` for both image and PDF inputs, improving consistency across the API
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
- Enhanced dry run configuration: added more granular control with `nb_list_items`, `nb_ocr_pages`, and `image_urls`
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
- Domain validation is now less restrictive in pipeline TOML: the `definition` attribute is now `Optional`

## [v0.3.0] - 2025-06-09

### Highlights

- **Structured Input Specifications**: Pipe inputs are now defined as a dictionary mapping a required variable name to a concept code (`required_variable` -> `concept_code`). This replaces the previous single `input` field and allows for multiple, named inputs, making pipes more powerful and explicit. This is a **breaking change**.
- **Static Validation for Inference Pipes**: You can now catch configuration and input mistakes in your pipelines *before* running any operations. This static validation checks `PipeLLM`, `PipeOcr`, and `PipeImgGen`. Static validation for controller pipes (PipeSequence, PipeParallel…) will come in a future release.
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

- **Refactored Cognitive Workers**: The abstraction for `LLM`, `Imgg`, and `Ocr` workers has been elegantly simplified. The old decorator-based approach (`..._job_func`) has been replaced with a more robust pattern: a public base method now handles pre- and post-execution logic while calling a private abstract method that each worker implements.
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
- TestImggByOpenAIGpt
- TestImageGeneration
- TestPipeImgg


## [v0.2.9] - 2025-05-30

- Include `pyproject.toml` inside the project build.
- Fix `ImggEngineFactory`: image generation (imgg) handle required format is `platform/model_name`
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

- Added `OcrWorkerAbstract` and `MistralOcrWorker`, along with `PipeOcr` for OCR processing of images and PDFs.
- Introduced `MissionManager` for managing missions, cost reports, and activity tracking.
- Added detection and handling for pipe stack overflow, configurable with `pipe_stack_limit`.
- More possibilities for dependency injection and better class structure.
- Misc updates including simplified PR template, LLM deck overrides, removal of unused config vars, and disabling of an LLM platform id.

## [v0.2.0] - 2025-05-19

- Added OCR, thanks to Mistral
- Refactoring and cleanup

## [v0.1.14] - 2025-05-13

- Initial release 🎉
