---
title: "Distributed Execution"
description: "Run Pipelex methods as durable, horizontally-scaled workflows — crash survival, per-step retries, and operational visibility, delivered through the Pipelex platform."
---

# Distributed Execution

Run your `.mthds` methods as durable workflows — the same methods you build locally, executed with crash survival, per-step retries, and horizontal scale.

## Overview

Pipelex pipelines normally run in-process. When you need durability, retries that survive failure, and scale, the same pipelines run as durable workflows: each pipe becomes a workflow, child pipes become child workflows, and every LLM call, image generation, or document extraction becomes an independently-retried unit of work. Pipelex handles the AI work; the orchestration layer handles durability, retries, scheduling, and visibility — and your method code doesn't change.

## What you get

- **Crash survival** — long pipelines resume exactly where they left off after a restart.
- **Per-step retries** — each LLM call, extraction, or image generation retries on its own, with its own timeout and retry policy.
- **Horizontal scale** — fan work across workers and route workloads to pools that scale and fail independently.
- **Operational visibility** — every run is durable, observable, and replayable.

## Backends

Distributed execution is delivered through the Pipelex platform, on proven orchestration engines — [Temporal-backed durable execution](https://pipelex.com/products#temporal), and a [Mistral Workflows](https://pipelex.com/products#mistral-workflows) integration that runs your pipes inside Mistral's managed Workflows. Both run the identical methods through the same Pipelex runtime, so the durability model and the error contract are the same whichever one executes your work.

## Get started

See the **[Distributed Execution](../distributed-execution/index.md)** capability guide, or explore the platform at **[Pipelex products](https://pipelex.com/products#durable-execution)**.
