# The MTHDS Package System — Design Specification

## 1. Vision

Methods are designed to be composable, shareable, and reusable. Today, bundles can reference concepts across domains, but the standard lacks the infrastructure for web-scale distribution: there are no globally unique addresses, no explicit dependencies, no visibility controls, and pipes lack the namespacing that concepts already have.

The MTHDS Package System introduces the structures needed to turn individual bundles into nodes of the **Know-How Graph**: a federated network of reusable, discoverable, type-safe AI methods.

### Design Principles

These principles are drawn from what works in existing ecosystems (Go modules, Rust crates, Agent Skills) and what's unique to MTHDS:

- **Filesystem as interface.** Packages are directories of text files. Git-native, human-readable, agent-readable. No proprietary formats, no binary blobs.
- **Progressive enhancement.** A single `.mthds` file still works. Packaging is opt-in complexity added only when you need distribution.
- **Type-driven composability.** Unlike Agent Skills (discovered by text description), pipes have typed signatures. The concept system enables semantic discovery: "I have X, I need Y."
- **Federated distribution.** Decentralized storage (Git), centralized discovery (registries). No single point of ownership.
- **Packages own namespaces, domains carry meaning.** The package is the ownership/isolation boundary. The domain is a semantic label and an intra-package namespace, but it never merges across packages.

---

## 2. Core Concepts

### Three Layers

| Layer | What it is | Role |
|-------|-----------|------|
| **Domain** | A semantic namespace for concepts and pipes within a package. E.g., `recruitment`, `legal.contracts`, `scoring`. | Intra-package organization. Semantic label for discovery. Carries meaning about what the bundle is about. |
| **Bundle** | A single `.mthds` file. Declares exactly one domain. Contains concept definitions and pipe definitions. | The authoring unit. Where concepts and pipes are defined. |
| **Package** | A directory with a manifest (`METHODS.toml`) and one or more bundles. Has a globally unique address. | The distribution unit. Owns a namespace. Declares dependencies and exports. |

### Hierarchical Domains

Domains can be hierarchical, using `.` as the hierarchy separator:

```
legal
legal.contracts
legal.contracts.shareholder_agreements
```

This enables natural organization of complex knowledge areas. A large package covering legal methods can structure its domains as a tree rather than a flat list.

**The hierarchy is purely organizational.** There is no implicit scope or inheritance between parent and child domains. `legal.contracts` does not automatically have access to concepts defined in `legal`. If a bundle in `legal.contracts` needs concepts from `legal`, it uses explicit domain-qualified references — the same as any other cross-domain reference. This keeps the system predictable: you can read a bundle and know exactly where its references come from.

### Key Rule: Packages Isolate Namespaces

Two packages can both declare `domain = "recruitment"`. Their concepts and pipes are completely independent — there is no merging. The domain name is semantic (it tells you what the bundle is about) and serves as a namespace within its package, but across packages, the package address is the true isolation boundary.

This means:

- `recruitment.CandidateProfile` from Package A and `recruitment.CandidateProfile` from Package B are **different things**.
- To reference something from another package, you must qualify it with the package identity.
- Within a single package, bundles sharing the same domain DO merge their namespace (same behavior as today's multi-file loading). Conflicts within the same package + same domain are errors.

### Why Not Merge Domains?

Merging domains across packages would create fragile implicit coupling: any package declaring `domain = "recruitment"` could inject concepts into your namespace. Instead, cross-package composition is explicit — through dependencies, concept refinement, and pipe invocation. This is how Go modules, Rust crates, and every robust package system works: you build on top of other packages, you don't extend their namespace.

The domain remains valuable for **discovery**: searching the Know-How Graph for "all packages in the recruitment domain" is powerful. But discovery is not namespace merging.

### Domain Naming Rules

- Domain names must be lowercase `snake_case` segments, optionally separated by `.` for hierarchy.
- Each segment follows `snake_case` rules: `[a-z][a-z0-9_]*`.
- Recommended depth: 1-3 levels. Recommended segment length: 1-4 words.
- Reserved domains that cannot be used by packages: `native`, `mthds`, `pipelex`. (Note: currently not enforced by domain validation — the manifest parser is the right place to check this.)

---

## 3. Package Structure

A package is a directory following progressive enhancement — start minimal, add structure as needed:

```
legal-tools/
├── METHODS.toml                    # Package manifest (required for distribution)
├── general_legal.mthds             # Bundle: domain = "legal"
├── contract_analysis.mthds         # Bundle: domain = "legal.contracts"
├── shareholder_agreements.mthds    # Bundle: domain = "legal.contracts.shareholder"
├── scoring.mthds                   # Bundle: domain = "scoring"
├── README.md                       # Optional: human-facing documentation
├── test_data/                      # Optional: example inputs
│   └── inputs.json
└── LICENSE                         # Optional: licensing terms
```

### Minimal Package

The absolute minimum for a distributable package:

```
my-tool/
├── METHODS.toml
└── method.mthds
```

### Standalone Bundle (No Package)

A `.mthds` file without a manifest still works. It behaves as an implicit local package with no dependencies (beyond native concepts) and all pipes public. This preserves the "single file = working method" experience for learning, prototyping, and simple projects.

---

## 4. The Package Manifest

`METHODS.toml` — the identity card and dependency declaration for a package.

```toml
[package]
address = "github.com/acme/legal-tools"
version = "0.3.0"
description = "Legal document analysis and contract review methods."
authors = ["ACME Legal Tech <legal@acme.com>"]
license = "MIT"
mthds_version = ">=0.2.0"

[dependencies]
"github.com/mthds/document-processing" = { version = "^1.0.0", alias = "docproc" }
"github.com/mthds/scoring-lib" = { version = "^0.5.0", alias = "scoring_lib" }

[exports.legal]
pipes = ["classify_document"]

[exports.legal.contracts]
pipes = ["extract_clause", "analyze_nda", "compare_contracts"]

[exports.scoring]
pipes = ["compute_weighted_score"]
```

### Fields

**`[package]`**

| Field | Required | Description |
|-------|----------|-------------|
| `address` | Yes | Globally unique identifier. Must start with a hostname. URL-style, self-describing. The address IS the fetch location (modulo protocol). |
| `version` | Yes | Semantic version. |
| `description` | Yes | Human-readable summary of the package's purpose. Written at the package level (not duplicating pipe signatures). |
| `authors` | No | List of author identifiers. |
| `license` | No | SPDX license identifier. |
| `mthds_version` | No | Minimum MTHDS standard version required. |

**`[dependencies]`**

Each key is a package address (must start with a hostname). Values:

| Field | Required | Description |
|-------|----------|-------------|
| `version` | Yes | Version constraint (semver range). |
| `alias` | Yes | Short `snake_case` name for use in `.mthds` cross-package references. Must be valid `snake_case`. No auto-defaulting — explicit aliases keep references readable and intentional. |

**`[exports]`**

Uses TOML sub-tables, one per domain. The domain path maps directly to the TOML table path — `legal.contracts` becomes `[exports.legal.contracts]`. Each sub-table contains:

| Field | Required | Description |
|-------|----------|-------------|
| `pipes` | Yes | List of pipe codes that are public from this domain. |

Rules:

- **Concepts are always public.** They are vocabulary — the whole point of domains is shared meaning.
- **Pipes are private by default.** A non-exported pipe is only accessible from within its own domain. Pipes listed in `[exports]` are callable from any domain within the package and by external packages.
- **`main_pipe` is auto-exported.** If a bundle declares a `main_pipe`, it is automatically part of the public API.
- Pipes not listed in exports are implementation details — invisible to consumers.

---

## 5. Namespace Resolution

References to concepts and pipes resolve through three scopes, from most local to most global.

### Parsing Rule

A reference is parsed by splitting on the **last `.`** to separate the domain path from the name:

- `extract_clause` → bare name (no dot, local)
- `legal.contracts.extract_clause` → domain `legal.contracts`, pipe `extract_clause`
- `legal.contracts.NonCompeteClause` → domain `legal.contracts`, concept `NonCompeteClause`
- `scoring.compute_score` → domain `scoring`, pipe `compute_score`

The casing of the last segment disambiguates: `snake_case` = pipe code, `PascalCase` = concept code. This is unambiguous because pipe codes and concept codes follow different casing conventions.

For package-qualified references, `->` is split first:

- `docproc->legal.contracts.extract_clause` → package `docproc`, domain `legal.contracts`, pipe `extract_clause`

### Scope 1: Bundle-Local (Bare Names)

Within a `.mthds` file, bare names resolve to the current bundle and its domain. This is how things work today.

```toml
# In contract_analysis.mthds (domain = "legal.contracts")
[pipe.extract_clause]
inputs = { contract = "ContractDocument" }   # concept from this bundle
output = "NonCompeteClause"                   # concept from this bundle
steps = [
    { pipe = "parse_sections", result = "sections" }  # pipe from this bundle
]
```

### Scope 2: Domain-Qualified (Cross-Bundle, Same Package)

When referencing something from another bundle within the same package (or for explicitness), use `domain_path.name`:

```toml
# Concepts — single-segment domain (already supported today)
inputs = { doc = "legal.ClassifiedDocument" }
output = "scoring.WeightedScore"

# Concepts — hierarchical domain (NEW)
inputs = { clause = "legal.contracts.NonCompeteClause" }

# Pipes (NEW — same syntax as concepts)
steps = [
    { pipe = "legal.classify_document", result = "classified" },
    { pipe = "legal.contracts.extract_clause", result = "clause" },
    { pipe = "scoring.compute_weighted_score", result = "score" }
]
```

This is the main change for pipe namespacing: pipes get domain-qualified references, symmetric with concepts.

### Scope 3: Package-Qualified (Cross-Package)

When referencing something from another package, prefix with the package alias and `->`:

```toml
# Using dependency alias from METHODS.toml
inputs = { pages = "docproc->extraction.Page" }
steps = [
    { pipe = "docproc->extraction.extract_text", result = "pages" }
]
```

The `->` (arrow) separator was chosen for **readability by non-technical audiences**. MTHDS is a language that business people and domain experts read and contribute to — the separator must feel natural, not "geeky."

- Reads as natural language: "from docproc, get extraction.extract_text"
- Directional — conveys "reaching into another package" intuitively
- Visually distinctive from `.` — the package boundary is immediately visible at a glance
- Universally understood (arrows are not a programming concept)

**Alias naming rule**: Package aliases must be `snake_case` (consistent with domain names). This ensures clean readability — e.g., `acme_hr->recruitment.extract_cv`.

### Resolution Order

When resolving a bare reference like `NonCompeteClause`:

1. Check native concepts (`Text`, `Image`, `Document`, etc.) — native always takes priority
2. Look in the current bundle's declared concepts
3. Look in other bundles of the same domain within the same package
4. If not found: error

When resolving `legal.contracts.NonCompeteClause`:

1. Look in the `legal.contracts` domain within the current package
2. If not found: error (domain-qualified refs don't fall through to dependencies)

When resolving `acme->legal.contracts.NonCompeteClause`:

1. Look in the `legal.contracts` domain of the package aliased as `acme`
2. If not found: error

### Special Namespace: `native`

Built-in concepts remain accessible as `native.Image`, `native.Text`, etc. — or by bare name (`Image`, `Text`) since they're always in scope. The `native` prefix is a reserved namespace that no package can claim.

---

## 6. Pipe Namespacing — All Reference Points

Every place in the `.mthds` format that references a pipe must support the three-scope syntax:

| Location | Current | With Namespacing |
|----------|---------|-----------------|
| `main_pipe` | `"extract_clause"` | `"extract_clause"` (always local) |
| `steps[].pipe` | `"extract_documents"` | `"extract_documents"` or `"legal.contracts.extract_clause"` or `"pkg->legal.contracts.extract_clause"` |
| `parallels[].pipe` | `"analyze_cv"` | Same three-scope options |
| `branch_pipe_code` | `"process_single_cv"` | Same three-scope options |
| `outcomes` values | `"deep_analysis"` | Same three-scope options |
| `default_outcome` | `"fallback_analysis"` | Same three-scope options |

**Rule**: Pipe *definitions* (the `[pipe.my_pipe]` keys) are always local bare names. Namespacing applies only to pipe *references*.

---

## 7. Dependency Management

### Addressing

Package addresses are URL-style identifiers that must start with a hostname. They double as fetch locations:

```
github.com/mthds/document-processing
github.com/acme/legal-tools
gitlab.com/company/internal-methods
```

The canonical form is always the full hostname-based address.

### Fetching

Resolution chain:

0. **Local path**: Dependencies with a `path` field in `METHODS.toml` are resolved directly from the local filesystem. This supports development-time workflows (similar to Cargo's `path` deps or Go's `replace` directives).
1. **Local cache**: `~/.mthds/packages/` (global) or `.mthds/packages/` (project-local)
2. **VCS fetch**: The address IS the fetch URL — `github.com/acme/...` maps to `https://github.com/acme/...`
3. **Proxy/mirror**: Optional, configurable proxy for speed, reliability, or air-gapped environments (like Go's `GOPROXY`)

### Lock File

`methods.lock` — auto-generated, committed to version control:

```toml
["github.com/mthds/document-processing"]
version = "1.2.3"
hash = "sha256:a1b2c3d4..."
source = "https://github.com/mthds/document-processing"

["github.com/mthds/scoring-lib"]
version = "0.5.1"
hash = "sha256:e5f6g7h8..."
source = "https://github.com/mthds/scoring-lib"
```

### Integrity

- **SHA-256 checksums** in the lock file for every resolved package.
- **Optional signed manifests** for enterprise use (verifiable authorship).
- Checksum verification on every install/update.

### Version Resolution Strategy

Minimum version selection (Go's approach): deterministic, reproducible, simple. If Package A requires `>=1.0.0` of B and Package C requires `>=1.2.0` of B, resolve to `1.2.0` — the minimum version that satisfies all constraints.

### Cross-Package Concept Refinement Validation

When concept A in Package X `refines` concept B in Package Y, compatibility is validated at **both install time and load time**:

- **Install time**: verify that the referenced concept exists in the declared dependency version. Detect breaking changes early (e.g., if Package Y removes concept B in a new version).
- **Load time**: verify structural compatibility when bundles are actually loaded into the runtime.

---

## 8. Distribution Architecture

Following the federated model: decentralized storage, centralized discovery.

### Storage: Git Repositories

Packages live in Git repositories. The repository IS the package. No upload step, no proprietary hosting. Authors retain full control.

A repository can contain one package (at the root) or multiple packages (in subdirectories, with distinct addresses).

### Discovery: Registry Indexes

One or more registry services index packages without owning them. A registry provides:

- **Search**: by domain, by concept, by pipe signature, by description
- **Type-compatible search** (unique to MTHDS): "find pipes that accept `Document` and produce something refining `Text`"
- **Metadata**: versions, descriptions, licenses, dependency graphs
- **Social signals**: install counts, stars, community endorsements
- **Concept/pipe browsing**: navigate the refinement hierarchy, explore pipe signatures

Registries build their index by:

1. Crawling known package addresses
2. Parsing `METHODS.toml` for metadata
3. Parsing `.mthds` files for concept definitions and pipe signatures
4. No duplication — all data derived from the source files

### Installation

CLI-driven, inspired by `go get` and `npx skills add`:

```bash
mthds pkg add github.com/mthds/document-processing
mthds pkg add github.com/acme/legal-tools@0.3.0
mthds pkg install    # install all dependencies from lock file
mthds pkg update     # update to latest compatible versions
```

### Multi-Tier Deployment

Inspired by Agent Skills' enterprise tiers:

| Tier | Scope | Typical Use |
|------|-------|-------------|
| **Local** | Single `.mthds` file, no manifest | Learning, prototyping, one-off methods |
| **Project** | Package in a project repo | Team methods, versioned with the codebase |
| **Organization** | Internal registry/proxy | Company-wide approved methods, governance |
| **Community** | Public Git repos + public registries | Open-source Know-How Graph |

---

## 9. The Know-How Graph Integration

The package system is the infrastructure layer that enables the Know-How Graph to operate at web scale.

### Pipes as Typed Nodes

Every exported pipe has a typed signature:

```
extract_clause: (ContractDocument) → NonCompeteClause
classify_document: (Document) → ClassifiedDocument
compute_weighted_score: (CandidateProfile, JobRequirements) → WeightedScore
```

These signatures, combined with concept refinement hierarchies, form a directed graph where:

- **Nodes** are pipe signatures (typed transformations)
- **Edges** are data flow connections (output of one pipe type-matches input of another)
- **Refinement edges** connect concept hierarchies (`NonCompeteClause refines ContractClause refines Text`)

### Discovery Capabilities

The type system enables queries that text-based discovery (like Agent Skills) cannot support:

| Query Type | Example |
|-----------|---------|
| "I have X, I need Y" | "I have a `Document`, I need a `NonCompeteClause`" → finds all pipes/chains that produce it |
| "What can I do with X?" | "What pipes accept `ContractDocument` as input?" → shows downstream possibilities |
| Auto-composition | No single pipe goes from X to Y? Find a chain through the graph. |
| Compatibility check | Before installing a package, verify its pipes are type-compatible with yours. |

### Concept Refinement Across Packages

Cross-package concept refinement enables building on others' vocabulary:

```toml
# In your package, depending on acme_legal
[concept.EmploymentNDA]
description = "A non-disclosure agreement specific to employment contexts"
refines = "acme_legal->legal.contracts.NonDisclosureAgreement"
```

This extends the refinement hierarchy across package boundaries, enriching the Know-How Graph without merging namespaces.

---

*This is a living design document. It will evolve as we implement and discover edge cases.*
