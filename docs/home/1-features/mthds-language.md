---
title: MTHDS Language
---

# MTHDS Language

The declarative, TOML-based file format for defining AI methods without writing code.

## Overview

MTHDS (`.mthds` files) is a domain-specific language for defining AI methods. It lets developers declare concepts, pipes, and pipelines in a structured format that is both human-readable and machine-executable. The philosophy is separation of concerns: method logic is declared in MTHDS, while execution is handled by the Pipelex runtime. This keeps prompts, data flow, and orchestration version-controlled and reviewable.

## Domains

Semantic namespaces for organizing related concepts and pipes. Domains provide hierarchical naming and scoping, preventing name collisions across packages. Each `.mthds` file declares a single domain, and multiple files can contribute to the same domain.

## Bundles

A bundle is a complete method package defined in a single `.mthds` file. It contains a domain declaration, concepts, and pipes, and can optionally designate a `main_pipe` as the entry point. Bundles are self-contained and can be executed via the CLI or Python API.

## Packages & Dependencies

Package management with `METHODS.toml` manifest files. Declare package identity, dependencies with semantic version constraints (exact, caret, tilde, comparison), and export visibility controls. Packages can be installed from GitHub repositories or local directories.

## Cross-Package References

Reference concepts and pipes across package boundaries using the `->` operator with fully qualified names. This enables method composition — build complex methods from smaller, reusable packages.

## Pure MTHDS Development

Inline concept structures with nested concepts make Pipelex fully usable with just `.mthds` files and the CLI — no Python code required. Define structured outputs, orchestrate multi-step pipelines, and run everything from the command line.

## Language Specification

For the formal language specification, see [mthds.ai](https://mthds.ai).
