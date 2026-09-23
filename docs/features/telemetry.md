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

## Per-run attribution

A span or an event produced during a run is attributed to that run's own caller, not to the process that served it — which is what lets one deployment run many people's methods and still see each person's generations on their own timeline. The identity comes from the run: `user_id` is who started it, and the optional `analytics_groups` mapping says which of your entities it belongs to. Both are supplied where the run is, they ride the job through every nested pipe and across a process boundary, and they reach PostHog in the fields it reserves for identity — never as an event property or a span name. Work a host does for a known caller without it being a run is attributed the same way: validating a bundle, whose `pipe_dry_run` event and dry runs carry the caller the host passed, and an unhandled exception raised inside a run, which carries that run's caller out to the exception hook. Anything that names no caller of its own reports under the `user_id` you configured: an event outside any run and any caller's work, and a run on your own machine, whose caller is the literal `local` rather than a person a backend could tell apart — though its groups still ride, because which entities a run belongs to is a separate question from who started it. All of that describes the destinations you control; Pipelex's own Gateway stream receives a one-way digest of the caller inside your key's hash and none of your groups. See [Telemetry Setup](../setup/telemetry.md) for how to supply the groups.

## Gateway Telemetry

When using Pipelex Gateway as your inference backend, privacy-respecting metrics are automatically collected: models used, token counts, latency, and error rates. This data is tied to your Gateway API key (hashed for security) and requires no additional configuration.

## Privacy Controls

- **DO_NOT_TRACK** — Universal telemetry disable flag, respected by all integrations
- **Configurable destinations** — Choose independently what data goes to PostHog, Langfuse, OTLP, or Gateway
- **Content redaction** — Control whether prompt/completion content is included in spans
- **Mode-based gating** — Enable custom telemetry for CLI usage but disable it during unit tests

For configuration, see [Telemetry Configuration](../configuration/config-practical/telemetry-config.md) and [Telemetry Setup](../setup/telemetry.md).
