---
title: MTHDS Language
---

# MTHDS Language

The declarative, TOML-based file format for defining AI methods without writing code.

## Overview

<!-- TODO: Expand with examples and philosophy -->

MTHDS (`.mthds` files) is a domain-specific language for defining AI methods. It lets developers declare concepts, pipes, and pipelines in a structured format that is both human-readable and machine-executable.

## Domains

<!-- TODO: Explain domains, naming conventions, and hierarchical namespaces -->

Semantic namespaces for organizing related concepts and pipes. Domains provide hierarchical naming and scoping.

## Bundles

<!-- TODO: Explain bundle structure, main pipe, and how bundles are loaded -->

A bundle is a complete method package defined in a single `.mthds` file. It contains domain definitions, concepts, and pipes, with a designated main pipe as the entry point.

## Packages & Dependencies

<!-- TODO: Explain METHODS.toml, package identity, dependencies, and export visibility -->

Package management with `METHODS.toml` manifest files. Declare package identity, dependencies with semantic version constraints (exact, caret, tilde, comparison), and export visibility controls.

## Cross-Package References

<!-- TODO: Explain the `->` operator for referencing across packages -->

Reference concepts and pipes across package boundaries using the `->` operator with fully qualified names.

## Pure MTHDS Development

<!-- TODO: Explain how to build methods entirely in .mthds files without Python -->

Inline concept structures with nested concepts make Pipelex fully usable with just `.mthds` files and the CLI — no Python code required.

## Language Specification

For the formal language specification, see [MTHDS Language Spec v0.1.0](../3-understand-pipelex/language-spec-v0-1-0.md).
