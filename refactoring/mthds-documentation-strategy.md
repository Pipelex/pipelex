# MTHDS Documentation Website — Strategy

This document defines the content strategy, information architecture, and editorial guidelines for the MTHDS open standard documentation website. The site is built with MkDocs (Material theme) in a separate repository.

---

## 1. Positioning & Branding

### What MTHDS Is

MTHDS is an open standard for defining, packaging, and distributing AI methods. It provides a typed language for composable AI methods — a way to describe what an AI should do, with what inputs, producing what outputs, in files that humans and machines can read.

### Tagline Candidates

- "A typed language for composable AI methods"
- "Define, package, and distribute AI methods as code"
- "The open standard for shareable AI methods"

### Pipelex Relationship

Pipelex is the maintainer and reference implementation of MTHDS. The documentation website presents MTHDS as a standalone standard. Pipelex does not appear in the navigation, the landing page, or any core documentation section.

Pipelex is mentioned in exactly these places:

- **Footer**: "MTHDS is maintained by the Pipelex project" with a link to the Pipelex repository.
- **About page**: A sentence explaining that Pipelex is the reference implementation, with a link to Pipelex documentation.
- **Occasional callouts**: In the "For Implementers" section, phrases like "The reference implementation (Pipelex) handles this by..." to illustrate implementation choices without prescribing them.

### Reference Model: Agent Skills

The agentskills.io site presents Agent Skills as a standalone standard without branding Anthropic in the core documentation. Anthropic is acknowledged as the creator, not as the product owner. MTHDS follows the same pattern: the standard speaks for itself.

---

## 2. Audience Analysis

### Method Authors

Domain experts and technical users who write `.mthds` files, create packages, and manage dependencies. They want to learn the language, understand the workflow, and ship methods that others can use.

What they need from the docs:

- Conceptual explanations of what MTHDS is and why it exists.
- Tutorials that walk through writing a first method, creating a package, publishing it.
- Reference material for the `.mthds` file format and `METHODS.toml` manifest.
- CLI command reference for day-to-day operations.

### Runtime Implementers

Developers building tools that load, validate, and execute MTHDS bundles. They need specification-level precision: parsing rules, validation constraints, resolution algorithms, error conditions.

What they need from the docs:

- Formal specification of every file format (`.mthds`, `METHODS.toml`, `methods.lock`).
- Normative rules for namespace resolution, dependency resolution, version selection.
- A guide to building a compliant runtime: loader architecture, validation order, library isolation.

### How the Docs Serve Both

The site shares a common entry point ("What is MTHDS?") and then forks:

- **Authors** follow the Language, Package System, Guides, and CLI Reference sections. The writing is example-led and task-oriented.
- **Implementers** follow the Specification and "For Implementers" sections. The writing is precise and normative.

Both audiences use the Know-How Graph section (authors to discover methods, implementers to understand the query model).

---

## 3. The Two Pillars Framing

MTHDS has two complementary but separable halves. The documentation presents them as two pillars, reflecting the progressive enhancement principle: start with Pillar 1 alone, add Pillar 2 when you need distribution.

### Pillar 1 — The Language

The `.mthds` file format. Everything you need to define typed data and AI methods in a single file.

Core elements:

- **Concepts**: Typed data declarations with fields and refinement (inheritance). Field types include `text`, `integer`, `number`, `boolean`, `date`, `list`, `dict`, and `concept` references.
- **Pipes**: Typed transformations. Five operators (`PipeLLM`, `PipeFunc`, `PipeImgGen`, `PipeExtract`, `PipeCompose`) and four controllers (`PipeSequence`, `PipeParallel`, `PipeCondition`, `PipeBatch`).
- **Domains**: Hierarchical namespacing for concepts and pipes within a file or package. Naming rules, reserved domains (`native`, `mthds`, `pipelex`).
- **Namespace resolution**: Bare names (bundle-local), domain-qualified (`domain.Name`), package-qualified (`alias->domain.Name`).

A single `.mthds` file works standalone — no manifest, no package, no dependencies. This is the starting point for learning and prototyping.

### Pillar 2 — The Package System

The infrastructure for distributing and composing methods at scale.

Core elements:

- **`METHODS.toml` manifest**: Package identity, dependencies, exports.
- **Exports and visibility**: Pipes are private by default. Concepts are always public. `main_pipe` is auto-exported.
- **Dependencies**: Aliases, version constraints (semver ranges), local path deps for development.
- **Cross-package references**: The `->` syntax (`alias->domain.pipe_code`).
- **Lock file** (`methods.lock`): Resolved versions and SHA-256 checksums.
- **Distribution**: Git-native storage, federated discovery through registries, package cache.
- **Version resolution**: Minimum Version Selection (Go's approach).

### Progressive Enhancement Principle

The documentation reinforces this layering at every opportunity:

1. **Single file**: A `.mthds` file works on its own. No configuration, no manifest.
2. **Package**: Add a `METHODS.toml` to get exports, visibility, and identity.
3. **Dependencies**: Add `[dependencies]` to compose with other packages.
4. **Ecosystem**: Publish, search, and discover through the Know-How Graph.

---

## 4. Information Architecture (Sitemap)

```
Home (landing page)
│
├── What is MTHDS?
│   ├── The Two Pillars (language + packages)
│   ├── Core Concepts (bundles, domains, concepts, pipes)
│   └── Progressive Enhancement (single file → package → ecosystem)
│
├── THE LANGUAGE (Pillar 1)
│   ├── Bundles (.mthds files — structure, header fields)
│   ├── Concepts
│   │   ├── Simple declarations vs structured concepts
│   │   ├── Field types (text, integer, number, boolean, date, list, dict, concept)
│   │   ├── Refinement (inheritance)
│   │   └── Native concepts (Text, Image, Document, Html, Number, JSON, etc.)
│   ├── Pipes — Operators
│   │   ├── PipeLLM (LLM generation)
│   │   ├── PipeFunc (Python functions)
│   │   ├── PipeImgGen (image generation)
│   │   ├── PipeExtract (document extraction)
│   │   └── PipeCompose (templates & constructs)
│   ├── Pipes — Controllers
│   │   ├── PipeSequence (sequential steps)
│   │   ├── PipeParallel (concurrent branches)
│   │   ├── PipeCondition (conditional routing)
│   │   └── PipeBatch (map over lists)
│   ├── Domains (naming rules, hierarchy, reserved domains)
│   └── Namespace Resolution (bare, domain-qualified, package-qualified)
│
├── THE PACKAGE SYSTEM (Pillar 2)
│   ├── Package Structure (directory layout, minimal vs full)
│   ├── The Manifest (METHODS.toml — identity, deps, exports)
│   ├── Exports & Visibility (private by default, main_pipe auto-export)
│   ├── Dependencies (aliases, version constraints, local path deps)
│   ├── Cross-Package References (-> syntax, resolution rules)
│   ├── Lock File (methods.lock — versions, checksums)
│   ├── Distribution (addressing, VCS fetching, cache, registries)
│   └── Version Resolution (Minimum Version Selection)
│
├── THE KNOW-HOW GRAPH
│   ├── Typed Pipe Signatures
│   ├── Type-Compatible Search ("I have X, I need Y")
│   ├── Auto-Composition (chain suggestions)
│   └── Cross-Package Concept Refinement
│
├── SPECIFICATION (normative reference)
│   ├── .mthds File Format (all fields, validation rules, EBNF-like grammar)
│   ├── METHODS.toml Format (all fields, constraints)
│   ├── methods.lock Format
│   └── Namespace Resolution Rules (formal algorithm)
│
├── CLI REFERENCE
│   ├── mthds init / mthds validate / mthds run (core commands)
│   └── mthds pkg (init, list, add, install, update, lock, publish,
│                   index, search, inspect, graph)
│
├── GUIDES
│   ├── Write Your First Method (tutorial: single .mthds file)
│   ├── Create a Package (tutorial: add METHODS.toml, exports)
│   ├── Use Dependencies (how-to: add deps, cross-package refs)
│   ├── Publish a Package (how-to: validation, tagging)
│   └── Discover Methods (how-to: search, type-compatible queries)
│
├── FOR IMPLEMENTERS
│   ├── Building a Runtime (loader architecture, resolution order)
│   ├── Validation Rules (comprehensive list)
│   └── Package Loading (dependency resolution, library isolation)
│
└── ABOUT
    ├── Design Philosophy (filesystem as interface, progressive enhancement, etc.)
    ├── Comparison with Agent Skills (typed vs text-based, language vs format)
    ├── Roadmap
    └── Contributing
```

---

## 5. Progressive Disclosure Strategy

Each layer of the documentation reveals more complexity only when the reader is ready.

### Landing Page (~200 words)

One sentence: what MTHDS is. The two pillars in two short paragraphs. Three entry points: "Learn the language" (authors), "Read the specification" (implementers), "Get started" (tutorial). No jargon, no feature lists.

### "What is MTHDS?" (~1000 words)

The conceptual overview. Analogies to help non-programmers understand: concepts are like typed forms, pipes are like processing steps, domains are like folders. The three layers (domain, bundle, package) explained with a concrete example. The progressive enhancement story: you start with a file, you end with an ecosystem.

### Language and Package System Sections (~500-800 words each page)

Each page opens with a real `.mthds` or `METHODS.toml` snippet. The snippet is shown first, then explained line by line. Every concept is grounded in something concrete before abstraction is introduced.

Example structure for a Language page:

1. A complete `.mthds` snippet that demonstrates the topic.
2. "What this does" — a plain-language explanation.
3. "How it works" — the rules, constraints, and edge cases.
4. "See also" — links to related pages.

### Specification (length varies)

Formal, normative. Tables of fields with type, required/optional, constraints, and default values. Validation rules as numbered lists. EBNF-like grammar for parsing rules. This section is the authoritative reference — it can be long because precision is the goal.

### Guides (task-oriented, ~500-1000 words each)

Step-by-step, numbered instructions. "You want to do X. Here's how." Each guide starts with prerequisites, walks through the steps, and ends with verification ("run `mthds validate` to confirm").

---

## 6. Tone & Voice Guidelines

### Standard-Focused

Write "MTHDS defines..." not "We built..." The standard is the subject, not the team behind it.

### Accessible but Precise

The Language section should be readable by intelligent non-programmers — domain experts who will write `.mthds` files. Use analogies, avoid unnecessary jargon, define terms on first use. The Specification section prioritizes precision over accessibility — implementers expect formal language.

### Example-Led

Every concept introduced with a concrete `.mthds` or `METHODS.toml` snippet first, explanation second. The reader should see what something looks like before reading what it means.

### No Marketing Speak

No superlatives ("revolutionary", "powerful", "best-in-class"). No hype. No feature comparisons that position MTHDS as "better" than alternatives. Let the design speak for itself.

### Third-Person for Implementations

When referring to implementation behavior:

- "A compliant runtime must validate domain names against the reserved list."
- "The reference implementation (Pipelex) uses Minimum Version Selection for dependency resolution."
- Not: "We validate domain names" or "Our runtime uses MVS."

### Active Voice, Imperative for Instructions

In guides and tutorials: "Create a file named `method.mthds`." In reference: "The `address` field specifies the globally unique package identifier."

---

## 7. Standard/Implementation Boundary

### Core Docs: Standard Only

The Language, Package System, Know-How Graph, and Specification sections describe the MTHDS standard. They contain no implementation-specific details — no Python class names, no Pipelex configuration, no runtime-specific behavior.

These sections answer: "What does the standard define?" They never answer: "How does Pipelex implement it?"

### CLI Reference: The `mthds` CLI

The CLI reference uses the `mthds` command (a real, separate project). All examples use `mthds` commands, not `pipelex` commands. The `mthds` CLI is the standard's official tool, independent of any particular runtime.

### "For Implementers": Where Implementation Lives

This section is explicitly about building runtimes. It can reference Pipelex as the reference implementation for illustration, but always with the framing: "The reference implementation does X. A compliant runtime may choose a different approach as long as it satisfies the specification."

### Pipelex Mentions

Pipelex appears in:

- The About page (as maintainer and reference implementation).
- Occasional "reference implementation" callouts in the Implementers section.
- Links to Pipelex documentation for runtime-specific features (configuration, deployment, builder).
- The footer.

Pipelex does not appear in: the landing page, the Language section, the Package System section, the Specification, the CLI Reference, or the Guides.

---

## 8. CLI Command Reference Page

A dedicated page listing all `mthds` CLI commands. Each command includes a synopsis, flags, and at least one example. The commands map to the current `pipelex pkg` command set.

### Core Commands

| Command | Synopsis |
|---------|----------|
| `mthds init` | Initialize a new MTHDS package in the current directory. Scans `.mthds` files, generates a skeleton `METHODS.toml`. |
| `mthds validate` | Validate `.mthds` files and the manifest. Resolves dependencies, checks cross-package references, reports errors. |
| `mthds run` | Execute a method. Loads the package, resolves dependencies, runs the specified pipe. |

### Package Commands (`mthds pkg`)

| Command | Synopsis | Key Flags |
|---------|----------|-----------|
| `mthds pkg init` | Create a `METHODS.toml` in the current directory from existing `.mthds` files. | — |
| `mthds pkg list` | Display the package manifest: identity, dependencies, and exported pipes. | — |
| `mthds pkg add` | Add a dependency to the manifest. | `<address>`, `--alias`, `--version`, `--path` |
| `mthds pkg install` | Fetch and cache all dependencies from the lock file. Verifies integrity. | — |
| `mthds pkg update` | Re-resolve dependencies to latest compatible versions. Regenerates the lock file. | — |
| `mthds pkg lock` | Regenerate the lock file from the current manifest. Resolves transitive dependencies. | — |
| `mthds pkg publish` | Validate package readiness for distribution. Runs 15 checks. Optionally creates a git tag. | `--tag` |
| `mthds pkg index` | Build and display the local package index. | `--cache` (include cached packages) |
| `mthds pkg search` | Search the package index by text, domain, or type-compatible signatures. | `--accepts <concept>`, `--produces <concept>` |
| `mthds pkg inspect` | Display detailed information about a package: domains, concepts, pipe signatures. | `<address>` |
| `mthds pkg graph` | Query the Know-How Graph for concept/pipe relationships. | `--from <concept>`, `--to <concept>`, `--check`, `--compose` |

### Example Page Structure

Each command entry on the page follows this pattern:

```
### mthds pkg add

Add a dependency to the package manifest.

**Usage:**
    mthds pkg add <address> [--alias NAME] [--version CONSTRAINT] [--path LOCAL_PATH]

**Arguments:**
    address    Package address (e.g., github.com/mthds/document-processing)

**Options:**
    --alias     Short name for cross-package references (default: derived from address)
    --version   Version constraint (e.g., ^1.0.0, >=0.5.0)
    --path      Local filesystem path (for development-time dependencies)

**Examples:**
    mthds pkg add github.com/mthds/document-processing
    mthds pkg add github.com/acme/legal-tools --alias acme_legal --version "^0.3.0"
    mthds pkg add github.com/team/scoring --path ../scoring-lib
```

---

## 9. Content Phasing

The documentation should be written in phases that mirror the standard's progressive enhancement principle. Each phase is self-contained and useful on its own.

### Phase A — Foundation (write first)

The minimum viable documentation. A reader can understand what MTHDS is and write a single-file method.

Pages:

- Home (landing page)
- What is MTHDS?
- The Language: Bundles, Concepts (all sub-pages), Pipes — Operators (all five types), Pipes — Controllers (all four types), Domains
- Specification: `.mthds` File Format
- Guide: Write Your First Method

### Phase B — Packages (write second)

The reader can now create and manage packages.

Pages:

- The Package System: all pages (Package Structure, Manifest, Exports & Visibility, Dependencies, Cross-Package References, Lock File, Version Resolution)
- Specification: `METHODS.toml` Format, `methods.lock` Format, Namespace Resolution Rules
- Namespace Resolution (Language section)
- CLI Reference (full page)
- Guide: Create a Package

### Phase C — Ecosystem (write third)

The reader can publish, discover, and compose methods across packages.

Pages:

- The Know-How Graph: all pages
- Distribution (Package System section)
- Guide: Use Dependencies
- Guide: Publish a Package
- Guide: Discover Methods
- For Implementers: all pages (Building a Runtime, Validation Rules, Package Loading)

### Phase D — Polish (write last)

Context, philosophy, and community.

Pages:

- About: Design Philosophy
- About: Comparison with Agent Skills
- About: Roadmap
- About: Contributing

---

## 10. Inspiration Notes from Agent Skills

### What Agent Skills Does Well

The agentskills.io site has only four pages but feels complete because the standard is simple. Key patterns to adopt:

- **Clean landing page** with clear entry points for different audiences.
- **Specification as normative reference** — a single authoritative source for the file format.
- **"Integrate" section** for implementers, separated from the standard description.
- **Neutral tone** — the standard speaks for itself, the company is acknowledged but not foregrounded.

### Where MTHDS Differs

MTHDS needs significantly more documentation than Agent Skills because it is a richer standard:

| Dimension | Agent Skills | MTHDS |
|-----------|-------------|-------|
| **Language** | No language to teach (JSON/YAML format only) | Full language section needed (concepts, pipes, domains, resolution) |
| **Package system** | No dependencies, no versioning | Complete package system (manifest, deps, lock file, distribution) |
| **Type system** | Text descriptions for discovery | Typed signatures enabling semantic discovery ("I have X, I need Y") |
| **Composition** | No built-in composition model | Controllers (sequence, parallel, condition, batch) + auto-composition |
| **CLI** | No CLI | Full `mthds` CLI with package management commands |

### Design Parallels

The Agent Skills architecture document's analysis of "progressive disclosure" and "federated distribution" maps directly to MTHDS design principles. The Design Philosophy page should reference these parallels:

- Agent Skills' tiered skill hosting (built-in → user-created → community) parallels MTHDS's multi-tier deployment (local → project → organization → community).
- Agent Skills' "skills as files" philosophy parallels MTHDS's "filesystem as interface" principle.
- Both standards favor decentralized storage with centralized discovery.

---

## 11. MkDocs Configuration Notes

### Theme: Material for MkDocs

The site uses the Material theme with these recommended features:

- **Navigation tabs** for top-level sections (Language, Package System, Specification, etc.).
- **Table of contents** on the right side for in-page navigation.
- **Search** with full-text indexing.
- **Code highlighting** for TOML (`.mthds` files and `METHODS.toml` snippets).
- **Admonitions** for notes, warnings, and "tip" callouts.
- **Content tabs** where appropriate (e.g., showing minimal vs full package structure).

### Custom Syntax Highlighting

TOML is the primary code language. Ensure the MkDocs configuration registers TOML highlighting. Consider a custom lexer or aliases if Material's default TOML highlighting doesn't handle `.mthds`-specific patterns well (e.g., the `->` syntax in cross-package references).

### Navigation Structure

The `mkdocs.yml` navigation should mirror the sitemap in Section 4. Use nested navigation with section headers matching the pillar framing:

```yaml
nav:
  - Home: index.md
  - What is MTHDS?: what-is-mthds/index.md
  - The Language:
      - Bundles: language/bundles.md
      - Concepts: language/concepts.md
      # ... etc.
  - The Package System:
      - Package Structure: packages/structure.md
      # ... etc.
  - The Know-How Graph: know-how-graph/index.md
  - Specification:
      - .mthds File Format: spec/mthds-format.md
      # ... etc.
  - CLI Reference: cli/index.md
  - Guides:
      - Write Your First Method: guides/first-method.md
      # ... etc.
  - For Implementers:
      - Building a Runtime: implementers/runtime.md
      # ... etc.
  - About:
      - Design Philosophy: about/philosophy.md
      # ... etc.
```

---

## Source Material

- `refactoring/pipelex-package-system-design_v6.md` — The MTHDS standard specification
- `refactoring/pipelex-package-system-changes_v6.md` — Evolution plan and implementation status
- `refactoring/mthds-implementation-brief_v8.md` — Phase-by-phase implementation details
- Agent Skills architecture analysis (Google Drive)
- agentskills.io site structure
- Full `.mthds` format reference (from codebase: `pipelex/core/`)
