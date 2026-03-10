---
title: Telemetry & Observability
---

# Telemetry & Observability

Production-ready monitoring for your AI methods.

## Overview

<!-- TODO: Expand with observability strategy -->

Pipelex provides comprehensive telemetry and observability capabilities to monitor your AI methods in production. Track costs, latency, errors, and execution patterns.

## Langfuse Integration

<!-- TODO: Describe Langfuse setup and capabilities -->

Full LLM observability with complete span data. Track every LLM call, its inputs, outputs, tokens, cost, and latency.

## OpenTelemetry (OTLP)

<!-- TODO: Describe OTLP integration -->

Send execution spans to any OTLP-compatible backend for integration with your existing observability stack.

## PostHog Integration

<!-- TODO: Describe PostHog event tracking -->

Event tracking and AI span tracing with privacy controls.

## Gateway Telemetry

<!-- TODO: Describe automatic gateway metrics -->

Automatic, privacy-respecting metrics collected by the Gateway: models used, token counts, latency, and error rates.

## Privacy Controls

<!-- TODO: Describe DO_NOT_TRACK and other privacy options -->

- **DO_NOT_TRACK** — Universal telemetry disable flag
- **Configurable destinations** — Choose what data goes where
- **Data minimization** — Only collect what's needed

For configuration, see [Telemetry Configuration](../7-configuration/config-practical/telemetry-config.md) and [Telemetry Setup](../5-setup/telemetry.md).
