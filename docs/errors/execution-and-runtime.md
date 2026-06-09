---
title: "Execution & runtime"
description: "Pipelex error classes in the Execution & runtime area, grouped by subsystem."
---

<!-- pipelex:generated -->

# Execution & runtime

Each error class below has a stable RFC 7807 `type` URI that dereferences to its
own page. Classes are grouped by subsystem.

## Pipe execution

- [`AsyncExecutionNotEnabledError`](async-execution-not-enabled-error.md) — Async execution not enabled
- [`BatchParamsError`](batch-params-error.md) — Batch params
- [`DeliveryError`](delivery-error.md) — Delivery
- [`DryRunError`](dry-run-error.md) — Dry run
- [`PipeJobError`](pipe-job-error.md) — Pipe job
- [`PipeRouterError`](pipe-router-error.md) — Pipe router
- [`PipeRunError`](pipe-run-error.md) — Pipe run
- [`PipeRunParamsError`](pipe-run-params-error.md) — Pipe run params
- [`StorageDeliveryError`](storage-delivery-error.md) — Storage delivery
- [`WebhookDeliveryError`](webhook-delivery-error.md) — Webhook delivery

## Pipeline execution

- [`JobMetadataError`](job-metadata-error.md) — Job metadata
- [`PipeExecutionError`](pipe-execution-error.md) — Pipe execution
- [`PipeStackOverflowError`](pipe-stack-overflow-error.md) — Pipe stack overflow
- [`PipelineExecutionError`](pipeline-execution-error.md) — Pipeline execution
- [`PipelineManagerAlreadyExistsError`](pipeline-manager-already-exists-error.md) — Pipeline manager already exists
- [`PipelineManagerNotFoundError`](pipeline-manager-not-found-error.md) — Pipeline manager not found
- [`ValidateBundleError`](validate-bundle-error.md) — Validate bundle

## Temporal execution

- [`ContentGenerationError`](content-generation-error.md) — Content generation
- [`SearchAttributeRegistrationError`](search-attribute-registration-error.md) — Search attribute registration
- [`TemporalConfigError`](temporal-config-error.md) — Temporal config
- [`TemporalFlowError`](temporal-flow-error.md) — Temporal flow
- [`TemporalServerError`](temporal-server-error.md) — Temporal server
- [`UnrecoverableWorkflowFailureError`](unrecoverable-workflow-failure-error.md) — Unrecoverable workflow failure
- [`WorkerProfileConfigError`](worker-profile-config-error.md) — Worker profile config
- [`WorkerScopeConfigError`](worker-scope-config-error.md) — Worker scope config
- [`WorkerTaskQueueUnknownError`](worker-task-queue-unknown-error.md) — Worker task queue unknown
- [`WorkflowExecutionError`](workflow-execution-error.md) — Workflow execution
- [`WorkflowInputError`](workflow-input-error.md) — Workflow input

## Runtime bridge

- [`MissingMistralWorkflowsPluginError`](missing-mistral-workflows-plugin-error.md) — Missing mistral workflows plugin
- [`MissingPipelexTemporalExtraError`](missing-pipelex-temporal-extra-error.md) — Missing pipelex temporal extra
- [`PipelexBridgeDispatchError`](pipelex-bridge-dispatch-error.md) — Pipelex bridge dispatch
- [`PipelexRuntimeBridgeError`](pipelex-runtime-bridge-error.md) — Pipelex runtime bridge

## Graph

- [`GraphSpecError`](graph-spec-error.md) — Graph spec
- [`GraphSpecValidationError`](graph-spec-validation-error.md) — Graph spec validation

## Tracing

- [`EventLogError`](event-log-error.md) — Event log
- [`EventLogReadError`](event-log-read-error.md) — Event log read
- [`EventLogSetupError`](event-log-setup-error.md) — Event log setup

[Back to Error Reference](index.md)
