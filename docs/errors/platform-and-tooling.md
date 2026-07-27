---
title: "Platform & tooling"
description: "Pipelex error classes in the Platform & tooling area, grouped by subsystem."
---

<!-- pipelex:generated -->

# Platform & tooling

Each error class below has a stable RFC 7807 `type` URI that dereferences to its
own page. Classes are grouped by subsystem.

## Base & root errors

- [`PipelexConfigError`](pipelex-config-error.md) — Pipelex config
- [`PipelexError`](pipelex-error.md) — Pipelex error
- [`PipelexSetupError`](pipelex-setup-error.md) — Pipelex setup
- [`PipelexUnexpectedError`](pipelex-unexpected-error.md) — Unexpected internal error
- [`SecurityError`](security-error.md) — Security policy violation

## Tools

- [`ArgumentTypeError`](argument-type-error.md) — Argument type
- [`AwsCredentialsError`](aws-credentials-error.md) — Aws credentials
- [`ContextProviderError`](context-provider-error.md) — Context provider
- [`CsvCoercionError`](csv-coercion-error.md) — CSV coercion error
- [`CsvColumnError`](csv-column-error.md) — CSV column error
- [`CsvError`](csv-error.md) — CSV error
- [`CsvFlatnessError`](csv-flatness-error.md) — CSV flatness error
- [`CsvReadError`](csv-read-error.md) — CSV read error
- [`FileTypeError`](file-type-error.md) — File type
- [`Jinja2ContextError`](jinja2-context-error.md) — Jinja 2 context
- [`Jinja2DetectVariablesError`](jinja2-detect-variables-error.md) — Jinja 2 detect variables
- [`Jinja2StuffError`](jinja2-stuff-error.md) — Jinja 2 stuff
- [`Jinja2TemplateRenderError`](jinja2-template-render-error.md) — Jinja 2 template render
- [`Jinja2TemplateSyntaxError`](jinja2-template-syntax-error.md) — Jinja 2 template syntax
- [`JsonTypeError`](json-type-error.md) — Json type
- [`ModuleFileError`](module-file-error.md) — Module file
- [`PyPdfium2RendererError`](py-pdfium2-renderer-error.md) — Py pdfium 2 renderer
- [`SecretNotFoundError`](secret-not-found-error.md) — Secret not found
- [`SsrfBlockedError`](ssrf-blocked-error.md) — Outbound request blocked (SSRF guard)
- [`StorageConfigError`](storage-config-error.md) — Storage config
- [`StorageError`](storage-error.md) — Storage error
- [`StorageFileNotFoundError`](storage-file-not-found-error.md) — Storage file not found
- [`StorageGcpCredentialsError`](storage-gcp-credentials-error.md) — Storage gcp credentials
- [`StorageGcpError`](storage-gcp-error.md) — Storage gcp
- [`StorageInvalidKeyError`](storage-invalid-key-error.md) — Storage invalid key
- [`StorageInvalidUriError`](storage-invalid-uri-error.md) — Storage invalid uri
- [`StorageLocalError`](storage-local-error.md) — Local storage error
- [`StorageS3Error`](storage-s3-error.md) — S3 storage error
- [`TomlError`](toml-error.md) — TOML parse error
- [`UnknownVarPrefixError`](unknown-var-prefix-error.md) — Unknown var prefix
- [`VarFallbackPatternError`](var-fallback-pattern-error.md) — Var fallback pattern
- [`VarNotFoundError`](var-not-found-error.md) — Var not found

## Kit

- [`KitError`](kit-error.md) — Kit
- [`KitIndexLoadingError`](kit-index-loading-error.md) — Kit index loading

## System & configuration

- [`ConfigModelError`](config-model-error.md) — Config model
- [`ConfigValidationError`](config-validation-error.md) — Config validation
- [`CredentialsError`](credentials-error.md) — Missing or invalid credentials
- [`EnvVarNotFoundError`](env-var-not-found-error.md) — Environment variable not set
- [`FatalError`](fatal-error.md) — Fatal error
- [`FuncRegistryError`](func-registry-error.md) — Func registry
- [`GatewayApiKeyMissingError`](gateway-api-key-missing-error.md) — Gateway api key missing
- [`GatewayConfigMergeError`](gateway-config-merge-error.md) — Gateway config merge
- [`GatewayDoNotTrackConflictError`](gateway-do-not-track-conflict-error.md) — Gateway do not track conflict
- [`GatewayTelemetryManagerInjectedError`](gateway-telemetry-manager-injected-error.md) — Gateway telemetry manager injected
- [`GatewayTermsNotAcceptedError`](gateway-terms-not-accepted-error.md) — Gateway terms not accepted
- [`InferenceSetupRequiredError`](inference-setup-required-error.md) — Inference setup required
- [`JobMetadataError`](job-metadata-error.md) — Job metadata
- [`LangfuseCredentialsError`](langfuse-credentials-error.md) — Langfuse credentials
- [`MissingDependencyError`](missing-dependency-error.md) — Missing dependency
- [`NestedKeyConflictError`](nested-key-conflict-error.md) — Nested key conflict
- [`PipelexServiceConfigValidationError`](pipelex-service-config-validation-error.md) — Pipelex service config validation
- [`PipelexServiceError`](pipelex-service-error.md) — Pipelex service
- [`RemoteConfigFetchError`](remote-config-fetch-error.md) — Remote config fetch
- [`RemoteConfigUnavailableError`](remote-config-unavailable-error.md) — Remote config unavailable
- [`RemoteConfigValidationError`](remote-config-validation-error.md) — Remote config validation
- [`TelemetryConfigError`](telemetry-config-error.md) — Telemetry config
- [`TelemetryConfigValidationError`](telemetry-config-validation-error.md) — Telemetry config validation
- [`ToolError`](tool-error.md) — Tool error
- [`TracebackMessageError`](traceback-message-error.md) — Traceback message

## CLI

- [`AmbiguousInputsFilesError`](ambiguous-inputs-files-error.md) — Ambiguous inputs files
- [`DriftAckError`](drift-ack-error.md) — Drift ack
- [`DriftError`](drift-error.md) — Drift
- [`DriftGitError`](drift-git-error.md) — Drift git
- [`DriftManifestError`](drift-manifest-error.md) — Drift manifest
- [`PipelexCLIError`](pipelex-cli-error.md) — Pipelex CLI
- [`ReadinessCheckError`](readiness-check-error.md) — Readiness check

## Codegen

- [`CodegenError`](codegen-error.md) — Codegen error
- [`CodegenLockError`](codegen-lock-error.md) — Codegen lock error
- [`CodegenStampError`](codegen-stamp-error.md) — Codegen stamp error

## Mthds parsing

- [`BundleElaboratorError`](bundle-elaborator-error.md) — Bundle elaborator
- [`MthdsParserError`](mthds-parser-error.md) — Mthds parser

[Back to Error Reference](index.md)
