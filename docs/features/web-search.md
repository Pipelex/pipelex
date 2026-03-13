---
title: "Web Search"
description: "Structured web search integrated into Pipelex pipelines. PipeSearch returns results with source citations, ready for downstream LLM processing."
---

# Web Search

Structured web search integrated into your pipelines.

## Overview

PipeSearch brings web search directly into your methods. Results come back as structured data with source citations, making them ready for downstream processing by LLMs or other pipes. Search is powered by Linkup (direct SDK) or via Pipelex Gateway.

## Key Capabilities

- **Structured results** — Search results returned as typed SearchResult concepts with an answer and sourced citations
- **Source citations** — Automatic source tracking for provenance and attribution
- **Pipeline integration** — Feed search results directly into PipeLLM for grounded generation with real-time data

## Usage in Pipelines

Use PipeSearch in a PipeSequence to retrieve information from the web and then process it with an LLM. The search results are stored in working memory as SearchResult concepts, available to downstream pipes.

See [PipeSearch reference](../building-methods/pipes/pipe-operators/PipeSearch.md).
