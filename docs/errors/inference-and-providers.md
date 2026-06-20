---
title: "Inference & providers"
description: "Pipelex error classes in the Inference & providers area, grouped by subsystem."
---

<!-- pipelex:generated -->

# Inference & providers

Each error class below has a stable RFC 7807 `type` URI that dereferences to its
own page. Classes are grouped by subsystem.

## Inference (Cogt)

- [`CogtError`](cogt-error.md) — AI inference failed
- [`CostRegistryError`](cost-registry-error.md) — Cost registry
- [`DryRunMockBuildError`](dry-run-mock-build-error.md) — Dry run mock build
- [`DryRunObjectFidelityError`](dry-run-object-fidelity-error.md) — Dry run object fidelity
- [`ExtractCapabilityError`](extract-capability-error.md) — Extract capability
- [`ExtractHandleNotFoundError`](extract-handle-not-found-error.md) — Extract handle not found
- [`ExtractInputError`](extract-input-error.md) — Extract input
- [`ExtractJobFailureError`](extract-job-failure-error.md) — Extract job failure
- [`ExtractModelNotFoundError`](extract-model-not-found-error.md) — Extract model not found
- [`ExtractOutputError`](extract-output-error.md) — Extract output
- [`FalCredentialsError`](fal-credentials-error.md) — Fal credentials
- [`GatewayUnknownModelError`](gateway-unknown-model-error.md) — Gateway unknown model
- [`GeneratedImageError`](generated-image-error.md) — Generated image
- [`ImageContentError`](image-content-error.md) — Image content
- [`ImgGenGeneratedTypeError`](img-gen-generated-type-error.md) — Img gen generated type
- [`ImgGenGenerationError`](img-gen-generation-error.md) — Img gen generation
- [`ImgGenHandleNotFoundError`](img-gen-handle-not-found-error.md) — Img gen handle not found
- [`ImgGenModelNotFoundError`](img-gen-model-not-found-error.md) — Img gen model not found
- [`ImgGenParameterError`](img-gen-parameter-error.md) — Img gen parameter
- [`ImgGenPromptError`](img-gen-prompt-error.md) — Img gen prompt
- [`ImgGenSettingsValidationError`](img-gen-settings-validation-error.md) — Img gen settings validation
- [`InferenceBackendCredentialsError`](inference-backend-credentials-error.md) — Inference backend credentials
- [`InferenceBackendLibraryError`](inference-backend-library-error.md) — Inference backend library
- [`InferenceBackendLibraryNotFoundError`](inference-backend-library-not-found-error.md) — Inference backend library not found
- [`InferenceBackendLibraryValidationError`](inference-backend-library-validation-error.md) — Inference backend library validation
- [`InferenceModelSpecError`](inference-model-spec-error.md) — Inference model spec
- [`LLMAssignmentError`](llm-assignment-error.md) — LLM assignment
- [`LLMCapabilityError`](llm-capability-error.md) — LLM capability
- [`LLMCompletionError`](llm-completion-error.md) — LLM completion
- [`LLMConfigError`](llm-config-error.md) — LLM config
- [`LLMHandleNotFoundError`](llm-handle-not-found-error.md) — LLM handle not found
- [`LLMModelNotFoundError`](llm-model-not-found-error.md) — LLM model not found
- [`LLMPromptParameterError`](llm-prompt-parameter-error.md) — LLM prompt parameter
- [`LLMPromptSpecError`](llm-prompt-spec-error.md) — LLM prompt spec
- [`LLMPromptTemplateInputsError`](llm-prompt-template-inputs-error.md) — LLM prompt template inputs
- [`LLMSettingsValidationError`](llm-settings-validation-error.md) — LLM settings validation
- [`ModelChoiceNotFoundError`](model-choice-not-found-error.md) — Model choice not found
- [`ModelDeckNotFoundError`](model-deck-not-found-error.md) — Model deck not found
- [`ModelDeckPresetValidatonError`](model-deck-preset-validaton-error.md) — Model deck preset validaton
- [`ModelDeckValidationError`](model-deck-validation-error.md) — Model deck validation
- [`ModelDeckValidatonError`](model-deck-validaton-error.md) — Model deck validaton
- [`ModelManagerError`](model-manager-error.md) — Model manager
- [`ModelNotFoundError`](model-not-found-error.md) — Model not found
- [`ModelReferenceParseError`](model-reference-parse-error.md) — Model reference parse
- [`ModelWaterfallError`](model-waterfall-error.md) — Model waterfall
- [`NeitherUrlNorDataError`](neither-url-nor-data-error.md) — Neither url nor data
- [`PromptDocumentFactoryError`](prompt-document-factory-error.md) — Prompt document factory
- [`PromptImageFactoryError`](prompt-image-factory-error.md) — Prompt image factory
- [`PromptImageFormatError`](prompt-image-format-error.md) — Prompt image format
- [`ReportingManagerError`](reporting-manager-error.md) — Reporting manager
- [`RoutingProfileBlueprintValueError`](routing-profile-blueprint-value-error.md) — Routing profile blueprint value
- [`RoutingProfileDisabledBackendError`](routing-profile-disabled-backend-error.md) — Routing profile disabled backend
- [`RoutingProfileLibraryError`](routing-profile-library-error.md) — Routing profile library
- [`RoutingProfileLibraryNotFoundError`](routing-profile-library-not-found-error.md) — Routing profile library not found
- [`SdkTypeError`](sdk-type-error.md) — Sdk type
- [`SearchHandleNotFoundError`](search-handle-not-found-error.md) — Search handle not found
- [`SearchJobFailureError`](search-job-failure-error.md) — Search job failure
- [`SearchModelNotFoundError`](search-model-not-found-error.md) — Search model not found
- [`TemplateSigilSyntaxError`](template-sigil-syntax-error.md) — Template sigil syntax
- [`UnsafeSchemaError`](unsafe-schema-error.md) — Unsafe schema

## Provider plugins

- [`AnthropicFactoryError`](anthropic-factory-error.md) — Anthropic factory
- [`AnthropicModelListingError`](anthropic-model-listing-error.md) — Anthropic model listing
- [`AnthropicSDKUnsupportedError`](anthropic-sdk-unsupported-error.md) — Anthropic SDK unsupported
- [`AnthropicWorkerConfigurationError`](anthropic-worker-configuration-error.md) — Anthropic worker configuration
- [`AzureCredentialsError`](azure-credentials-error.md) — Azure credentials
- [`BedrockFactoryError`](bedrock-factory-error.md) — Bedrock factory
- [`BedrockWorkerConfigurationError`](bedrock-worker-configuration-error.md) — Bedrock worker configuration
- [`BrokenPluginError`](broken-plugin-error.md) — Broken plugin
- [`CoreUnconditionalPluginDisabledError`](core-unconditional-plugin-disabled-error.md) — Core unconditional plugin disabled
- [`DuplicateInferenceBackendError`](duplicate-inference-backend-error.md) — Duplicate inference backend
- [`DuplicateOrchestratorError`](duplicate-orchestrator-error.md) — Duplicate orchestrator
- [`GatewayCredentialsError`](gateway-credentials-error.md) — Gateway credentials
- [`GatewayDeckError`](gateway-deck-error.md) — Gateway deck
- [`GatewayError`](gateway-error.md) — Gateway
- [`GatewayExtractResponseError`](gateway-extract-response-error.md) — Gateway extract response
- [`GatewayFactoryError`](gateway-factory-error.md) — Gateway factory
- [`GatewaySearchResponseError`](gateway-search-response-error.md) — Gateway search response
- [`GoogleImgGenWorkerError`](google-img-gen-worker-error.md) — Google img gen worker
- [`GoogleLLMWorkerError`](google-llm-worker-error.md) — Google LLM worker
- [`HubSlotAlreadyClaimedError`](hub-slot-already-claimed-error.md) — Hub slot already claimed
- [`InferenceBackendNotFoundError`](inference-backend-not-found-error.md) — Inference backend not found
- [`MistralExtractResponseError`](mistral-extract-response-error.md) — Mistral extract response
- [`MistralModelListingError`](mistral-model-listing-error.md) — Mistral model listing
- [`MistralPluginError`](mistral-plugin-error.md) — Mistral plugin
- [`MistralWorkerConfigurationError`](mistral-worker-configuration-error.md) — Mistral worker configuration
- [`OpenAIClientFactoryError`](open-ai-client-factory-error.md) — OpenAI client factory error
- [`PluginApiVersionMismatchError`](plugin-api-version-mismatch-error.md) — Plugin api version mismatch
- [`PluginError`](plugin-error.md) — Plugin error
- [`PortkeyCredentialsError`](portkey-credentials-error.md) — Portkey credentials
- [`PortkeyError`](portkey-error.md) — Portkey
- [`PortkeyFactoryError`](portkey-factory-error.md) — Portkey factory
- [`VertexAIConfigError`](vertex-ai-config-error.md) — VertexAI configuration error
- [`VertexAICredentialsError`](vertex-ai-credentials-error.md) — VertexAI credentials error

[Back to Error Reference](index.md)
