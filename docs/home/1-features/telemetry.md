---
title: "Telemetry & Observability"
description: "Production monitoring for Pipelex AI methods with Langfuse, OpenTelemetry, and PostHog integration. Track costs, latency, errors, and execution patterns."
---

# Telemetry & Observability

Production-ready monitoring for your AI methods.

## Overview

Pipelex provides comprehensive telemetry and observability capabilities to monitor your AI methods in production. Track costs, latency, errors, and execution patterns across multiple destinations. Custom telemetry is opt-in and configurable per integration mode (CLI, pytest, API). When Pipelex Gateway is enabled as an inference backend, privacy-respecting Gateway metrics are collected automatically.

## Langfuse Integration

Full LLM observability with complete span data. Track every LLM call, its inputs, outputs, tokens, cost, and latency. Supports both Langfuse Cloud and self-hosted instances via the OTLP exporter.

## OpenTelemetry (OTLP)

Send execution spans to any OTLP-compatible backend for integration with your existing observability stack. Configure multiple OTLP exporters with custom endpoints and headers to fan out telemetry to different destinations.

## PostHog Integration

Event tracking and AI span tracing with fine-grained privacy controls. Choose between anonymous and identified modes. Configure what data to capture: content, pipe codes, output class names, and content length limits.

## Gateway Telemetry

When using Pipelex Gateway as your inference backend, privacy-respecting metrics are automatically collected: models used, token counts, latency, and error rates. This data is tied to your Gateway API key (hashed for security) and requires no additional configuration.

## Privacy Controls

- **DO_NOT_TRACK** — Universal telemetry disable flag, respected by all integrations
- **Configurable destinations** — Choose independently what data goes to PostHog, Langfuse, OTLP, or Gateway
- **Content redaction** — Control whether prompt/completion content is included in spans
- **Mode-based gating** — Enable custom telemetry for CLI usage but disable it during unit tests

For configuration, see [Telemetry Configuration](../7-configuration/config-practical/telemetry-config.md) and [Telemetry Setup](../5-setup/telemetry.md).
