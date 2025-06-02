# Changelog

## [v0.2.10] - 2025-06-02

### Highlights

**Python Support Expansion** - We're no longer tied to Python 3.11! Now supporting Python 3.10, 3.11, 3.12, and 3.13 with full CI coverage across all versions.

**Major Model Additions** - Claude 4 (Opus & Sonnet), Grok-3, and GPT-4 image generation are now in the house.

### Pipeline Base Library update
- **New pipe** - `extract_page_contents_and_views_from_pdf` transfered from cookbook to base library (congrats on the promotion!). This pipe extracts text, linked images, **AND** page_view images (rendered pages) - it's very useful if you want to use Vision in follow-up pipes

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
- pipelex cli: Added `list-pipes` method that can list all the availables pipes with descriptions.
- Use a minimum version for `uv` instead of a fixed version
- Implement `AGENTS.md` for Codex
- Add tests for some of the `tools.misc`
- pipelex cli: Rename `pipelex run-setup` to `pipelex validate`

## [v0.2.8] - 2025-05-28

- Defaults to `uv`
- Simplify llm provider config: All the API keys, urls, and regions are to be set in `.env`.
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
