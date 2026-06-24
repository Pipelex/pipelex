---
title: "Distributed Execution"
description: "Run Pipelex methods as durable, horizontally-scaled workflows — crash survival, automatic per-step retries, and operational visibility, delivered through the Pipelex platform."
---

# Distributed Execution

Pipelex methods run in-process by default — you call a pipe and everything happens in one process. When you move to production and need work that survives crashes, retries every step under failure, and scales across machines, the **same methods** run as durable workflows. No rewrite: the methods you build locally are the methods that run distributed.

## What it gives you

- **Crash survival** — a long-running pipeline resumes exactly where it left off after a restart or worker crash, instead of starting over.
- **Per-step retries** — every LLM call, image generation, and document extraction retries on its own, with its own timeout and retry policy, so one flaky provider call doesn't sink the whole run.
- **Horizontal scale** — fan work out across many workers, and route different workloads — a provider, a model, OCR — to their own pools so they scale and fail independently.
- **Operational visibility** — every run is durable and observable: see what's running, what each step is doing, and replay history when you need it.

## How it works

You don't change your methods. Under the hood, Pipelex maps each method onto a durable execution graph — controller pipes become workflows, and each leaf operation (the actual AI calls) becomes an independently-retried unit of work. Pipelex handles the AI; the orchestration layer handles durability, retries, scheduling, and visibility. Which durable backend runs your methods is a deployment choice, not a code change.

## Backends

Distributed execution is delivered through the Pipelex platform, on top of proven orchestration engines:

- **[Temporal-backed execution](https://pipelex.com/products#temporal)** — run your methods as durable workflows on a Temporal control plane, with per-step retries and full replay history.
- **[Mistral Workflows](https://pipelex.com/products#mistral-workflows)** — run your pipes inside Mistral's managed Workflows orchestration, so there's no control plane for you to operate.

Both run the identical `.mthds` methods through the same Pipelex runtime, so the durability model and the [error contract](../reliability/failure-classification.md) are the same whichever one executes your work.

## Get started

Distributed and durable execution is part of the Pipelex platform rather than something you wire up yourself. To run your methods durably at scale — or to talk through which backend fits your deployment — see **[Pipelex products](https://pipelex.com/products#durable-execution)**.

For the failure-handling model that durable execution builds on, see [Retries & Resilience](../reliability/retries-and-resilience.md).
