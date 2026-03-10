---
title: Concepts & Structured Types
---

# Concepts & Structured Types

The semantic typing system that gives meaning to your AI data.

## Overview

<!-- TODO: Expand with examples -->

Concepts are Pipelex's type system. They define what kind of data flows through your pipelines — not just the shape, but the meaning. A concept can be as simple as "a tweet about a product" or as complex as "an invoice with line items, totals, and tax breakdowns."

## Native Concepts

<!-- TODO: List and describe each native concept -->

Pre-built universal concepts available in every Pipelex project:

- **Text** — Plain text content
- **Image** — Image data (base64, URL, or file path)
- **Document** — A document container
- **PDF** — PDF document
- **Page** — A single page from a document
- **Number** — Numeric value
- **JSON** — Arbitrary JSON data
- **SearchResult** — Web search result
- **Dynamic** — Dynamic typing
- **Anything** — Universal type

## Custom Concepts

<!-- TODO: Show how to define custom concepts in .mthds files -->

Define your own concepts with natural language descriptions and optional structured fields.

## Inline Structures

<!-- TODO: Explain inline field definitions with examples, including nested concepts -->

Define structured fields directly in `.mthds` files without writing Python. Supports nested concepts for complex data shapes.

## Python StructuredContent Classes

<!-- TODO: Explain Pydantic model generation and hand-written classes -->

Generate Pydantic BaseModels from your declarative concepts for full IDE autocomplete, type checking, and validation.

## Concept Refinement & Hierarchies

<!-- TODO: Explain concept inheritance and multi-level taxonomies -->

Create specialized versions of existing concepts. Build multi-level concept hierarchies for domain modeling.

For detailed guidance, see [Define Your Concepts](../6-build-reliable-ai-workflows/concepts/define_your_concepts.md).
