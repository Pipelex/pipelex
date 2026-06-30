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
- [`DryRunGraphNotProducedError`](dry-run-graph-not-produced-error.md) — Dry run graph not produced
- [`PipeJobError`](pipe-job-error.md) — Pipe job
- [`PipeRouterError`](pipe-router-error.md) — Pipe router
- [`PipeRunError`](pipe-run-error.md) — Pipe run
- [`PipeRunParamsError`](pipe-run-params-error.md) — Pipe run params
- [`StorageDeliveryError`](storage-delivery-error.md) — Storage delivery
- [`WebhookDeliveryError`](webhook-delivery-error.md) — Webhook delivery

## Pipeline execution

- [`JobMetadataError`](job-metadata-error.md) — Job metadata
- [`PipeExecutionError`](pipe-execution-error.md) — Pipe execution
- [`PipeIOContractError`](pipe-io-contract-error.md) — Pipe IO contract
- [`PipeStackOverflowError`](pipe-stack-overflow-error.md) — Pipe stack overflow
- [`PipelineExecutionError`](pipeline-execution-error.md) — Pipeline execution
- [`PipelineInputContentError`](pipeline-input-content-error.md) — Pipeline input content
- [`PipelineManagerAlreadyExistsError`](pipeline-manager-already-exists-error.md) — Pipeline manager already exists
- [`PipelineManagerNotFoundError`](pipeline-manager-not-found-error.md) — Pipeline manager not found
- [`ValidateBundleError`](validate-bundle-error.md) — Validate bundle

## Runtime bridge

- [`MissingBundleValidatorError`](missing-bundle-validator-error.md) — Missing bundle validator
- [`MissingOrchestratorError`](missing-orchestrator-error.md) — Missing orchestrator
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
