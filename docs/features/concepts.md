---
title: "Concepts & Structured Types"
description: "Learn about Pipelex Concepts — the semantic typing system that defines what kind of data flows through your AI pipelines, including native types, inline structures, and Python classes."
---

# Concepts & Structured Types

The semantic typing system that gives meaning to your AI data.

## Overview

Concepts are Pipelex's type system. They define what kind of data flows through your pipelines — not just the shape, but the meaning. A concept can be as simple as "a tweet about a product" or as complex as "an invoice with line items, totals, and tax breakdowns." Every pipe declares the concepts it accepts as input and produces as output, enabling Pipelex to validate data flow at definition time rather than runtime.

## Native Concepts

Pre-built universal concepts available in every Pipelex project:

- **Dynamic** — Dynamic typing, resolved at runtime
- **Text** — Plain text content
- **Image** — Image data (base64, URL, or file path)
- **Document** — A document container (PDF, image, or other file)
- **Html** — HTML content
- **TextAndImages** — Combined text and image content in a single structure
- **Number** — Numeric value
- **YesNo** — The answer to a yes/no question
- **Date** — A calendar date, optionally with a time of day
- **Time** — A time of day, optionally with a UTC offset
- **Page** — A single page extracted from a document, with markdown text and optional images
- **JSON** — Arbitrary JSON data
- **SearchResult** — Web search result with source citations
- **Composite** — A named composition of contents
- **Anything** — Universal type that accepts any content

## Custom Concepts

Define your own concepts with natural language descriptions and optional structured fields. Custom concepts live in `.mthds` files within a domain and can carry a description that guides LLMs, structured fields for validation, or both.

## Inline Structures

Define structured fields directly in `.mthds` files without writing Python. Inline structures support typed fields (text, integer, boolean, number, date, datetime, time, list, dict) and nested concepts for complex data shapes — making it possible to build fully structured methods without leaving the MTHDS language.

## Python StructuredContent Classes

For advanced use cases, generate Pydantic BaseModels from your declarative concepts. This gives you full IDE autocomplete, type checking, and runtime validation. You can also hand-write `StructuredContent` classes when you need custom logic beyond what MTHDS declarations provide.

## Concept Refinement & Hierarchies

Create specialized versions of existing concepts using the `refines` keyword. Build concept hierarchies for domain modeling — for example, a `DetailedInvoice` that refines a base `Invoice` concept, inheriting its structure while adding more specific semantics.

For detailed guidance, see [Define Your Concepts](../building-methods/concepts/define_your_concepts.md).
