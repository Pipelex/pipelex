# For Implementers & About

<!-- Source document for the MTHDS docs website.
     Each "## Page:" section becomes an individual MkDocs page.

     Tone: Technical, detailed. Aimed at developers building runtimes, editors,
     or other tooling that works with MTHDS files. Pseudocode and algorithm
     descriptions are welcome. The About section is more reflective — design
     rationale, comparisons, and community guidance.

     The reference implementation (Pipelex) is used for illustration.
     A compliant runtime may choose different approaches as long as it satisfies
     the specification.
-->

## Page: Building a Runtime

This page describes how to build a runtime that loads, validates, and executes MTHDS bundles and packages. The specification defines *what* must hold; this page describes *how* the reference implementation achieves it, as guidance for alternative implementations.

### High-Level Architecture

A compliant MTHDS runtime has four main subsystems:

1. **Parser** — reads `.mthds` TOML files into an in-memory bundle model.
2. **Loader** — discovers manifests, resolves dependencies, assembles a library of bundles.
3. **Validator** — checks all structural, naming, reference, and visibility rules.
4. **Executor** — runs pipes by dispatching to operator backends (LLM, function, image generation, extraction, composition) and orchestrating controllers.

The first three are specified by the standard; the fourth is implementation-specific (the standard defines *what* a pipe does, not *how*).

### Parsing .mthds Files

A `.mthds` file is valid TOML. Parse it with any compliant TOML parser, then validate the resulting structure against the MTHDS data model.

**Recommended approach:**

1. Parse the TOML into a generic dictionary.
2. Extract header fields (`domain`, `description`, `system_prompt`, `main_pipe`).
3. Extract the `concept` table — a mix of simple declarations (string values) and structured declarations (sub-tables with `description`, `structure`, `refines`).
4. Extract `pipe` sub-tables. Each pipe has a `type` field that determines the discriminated union variant (one of the nine pipe types).
5. Validate all fields against the rules in the [Specification](03-specification.md).

The reference implementation uses Pydantic's discriminated union on the `type` field to dispatch pipe parsing:

```
PipeBlueprintUnion = PipeFuncBlueprint
                   | PipeImgGenBlueprint
                   | PipeComposeBlueprint
                   | PipeLLMBlueprint
                   | PipeExtractBlueprint
                   | PipeBatchBlueprint
                   | PipeConditionBlueprint
                   | PipeParallelBlueprint
                   | PipeSequenceBlueprint
```

This means an invalid `type` value is rejected at parse time, before any field-level validation occurs.

### Manifest Discovery

When loading a bundle, the runtime must locate the package manifest (`METHODS.toml`) by walking up the directory tree:

```
function find_manifest(bundle_path):
    current = parent_directory(bundle_path)
    while true:
        if "METHODS.toml" exists in current:
            return parse_manifest(current / "METHODS.toml")
        if ".git" directory exists in current:
            return null  // stop at repository boundary
        parent = parent_directory(current)
        if parent == current:
            return null  // filesystem root
        current = parent
```

If no manifest is found, the bundle is treated as a standalone bundle: all pipes are public, no dependencies are available beyond native concepts, and the bundle is not distributable.

### Loading a Package

Loading a package involves these steps in order:

1. **Parse the manifest** — read `METHODS.toml` and validate all fields (address, version, dependencies, exports). Reject immediately on any parse or validation error.
2. **Discover bundles** — recursively find all `.mthds` files under the package root.
3. **Parse all bundles** — parse each `.mthds` file into a bundle blueprint. Collect parse errors.
4. **Resolve dependencies** — for each dependency in the manifest:
    - If it has a `path` field, resolve from the local filesystem (non-transitive).
    - If it is remote, resolve via VCS (transitive, with cycle detection and diamond handling).
5. **Build the library** — assemble all parsed bundles (local and dependency) into a library structure indexed by domain and package.
6. **Validate references** — check that all concept and pipe references resolve correctly, following the [Namespace Resolution Rules](03-specification.md#page-namespace-resolution-rules).
7. **Validate visibility** — check that cross-domain and cross-package pipe references respect export rules.

### Working Memory

Controllers orchestrate pipes through **working memory** — a key-value store that accumulates results as a pipeline executes.

When a `PipeSequence` runs, each step's output is stored under its `result` name. Subsequent steps can consume any previously stored value. The final step's output (or the value matching the sequence's `output` concept) becomes the sequence's output.

Working memory is scoped to a pipeline execution. Each top-level `mthds run` invocation starts with a fresh working memory containing only the declared inputs.

### Concept Refinement at Runtime

Concept refinement establishes a type-compatibility relationship. When a pipe declares `inputs = { doc = "ContractClause" }`, any concept that refines `ContractClause` (directly or transitively) is an acceptable input.

A runtime must build and query a refinement graph:

```
function is_compatible(actual_concept, expected_concept):
    if actual_concept == expected_concept:
        return true
    if actual_concept is a native concept and expected_concept == "Anything":
        return true
    parent = refinement_parent(actual_concept)
    if parent is null:
        return false
    return is_compatible(parent, expected_concept)
```

The refinement graph is built during loading by following `refines` fields across all loaded concepts (including cross-package refinements).

### Model Routing (Implementation-Specific)

The `model` field on `PipeLLM`, `PipeImgGen`, and `PipeExtract` is a string in the `.mthds` file. The standard does not prescribe how this string maps to an actual model.

The reference implementation uses a routing profile system with prefix conventions:

| Prefix | Meaning | Example |
|--------|---------|---------|
| `$` | Named routing profile for LLM and image generation models | `$writing-factual` |
| `@` | Named routing profile for extraction models | `@default-text-from-pdf` |
| *(none)* | Direct model identifier | `gpt-4o` |

A routing profile maps a semantic intent (e.g., "writing-factual") to a concrete model (e.g., `gpt-4o`) through a configuration layer. This allows method authors to express *what kind* of model they need without hardcoding a specific model name.

A compliant runtime may implement model routing differently — or not at all, treating the `model` field as a direct model identifier. The standard requires only that the field be a string.

### Template Blueprint (Advanced PipeCompose)

When the `template` field of a `PipeCompose` pipe is a table (rather than a plain string), it is a **template blueprint** with additional rendering options:

| Field | Type | Description |
|-------|------|-------------|
| `template` | string | The Jinja2 template source. Required. |
| `category` | string | Determines which Jinja2 filters and rendering rules apply. Values: `basic`, `expression`, `html`, `markdown`, `mermaid`, `llm_prompt`, `img_gen_prompt`. |
| `templating_style` | object or null | Controls tag style and text formatting during rendering. |
| `extra_context` | object or null | Additional variables injected into the template rendering context beyond the pipe's declared inputs. |

The `category` field influences which Jinja2 filters are available. For example, `html` templates get HTML-specific filters, while `llm_prompt` templates get prompt-specific filters. The reference implementation registers different filter sets per category.

A compliant runtime must support the plain string form of `template`. The table form with `category`, `templating_style`, and `extra_context` is an advanced feature that implementations may support progressively.

---

## Page: Validation Rules

This page consolidates all validation rules from the [Specification](03-specification.md) into an ordered checklist for implementers. Rules are grouped by the stage at which they should be enforced.

### Stage 1: TOML Parsing

Before any MTHDS-specific validation, the file must be valid TOML.

- The file MUST be valid UTF-8-encoded TOML.
- A `.mthds` file MUST have the `.mthds` extension.
- `METHODS.toml` MUST be named exactly `METHODS.toml`.
- `methods.lock` MUST be named exactly `methods.lock`.

### Stage 2: Bundle Structural Validation

After parsing TOML into a dictionary, validate the bundle structure:

1. `domain` MUST be present.
2. `domain` MUST be a valid domain code: one or more `snake_case` segments (`[a-z][a-z0-9_]*`) separated by `.`.
3. `main_pipe`, if present, MUST be `snake_case` and MUST reference a pipe defined in the same bundle.
4. Concept codes MUST be `PascalCase` (`[A-Z][a-zA-Z0-9]*`).
5. Concept codes MUST NOT match any native concept code (`Dynamic`, `Text`, `Image`, `Document`, `Html`, `TextAndImages`, `Number`, `ImgGenPrompt`, `Page`, `JSON`, `Anything`).
6. Pipe codes MUST be `snake_case` (`[a-z][a-z0-9_]*`).
7. `refines` and `structure` MUST NOT both be set on the same concept.

### Stage 3: Concept Field Validation

For each field in a concept's `structure`:

1. `description` MUST be present.
2. If `type` is omitted, `choices` MUST be non-empty.
3. `type = "dict"` requires both `key_type` and `value_type`.
4. `type = "concept"` requires `concept_ref` and forbids `default_value`.
5. `type = "list"` with `item_type = "concept"` requires `item_concept_ref`.
6. `concept_ref` MUST NOT be set unless `type = "concept"`.
7. `item_concept_ref` MUST NOT be set unless `item_type = "concept"`.
8. `default_value` type MUST match the declared `type`.
9. If `choices` is set and `default_value` is present, `default_value` MUST be in `choices`.
10. Field names MUST NOT start with `_`.

### Stage 4: Pipe Type-Specific Validation

Each pipe type has specific rules:

**PipeLLM:**

- All prompt and system_prompt variables MUST have matching inputs.
- All inputs MUST be referenced in prompt or system_prompt.

**PipeFunc:**

- `function_name` MUST be present and non-empty.

**PipeImgGen:**

- `prompt` MUST be present.
- All prompt variables MUST have matching inputs.

**PipeExtract:**

- `inputs` MUST contain exactly one entry.
- `output` MUST be `"Page[]"`.

**PipeCompose:**

- Exactly one of `template` or `construct` MUST be present.
- `output` MUST NOT use multiplicity brackets (`[]` or `[N]`).
- All template/construct variables MUST have matching inputs.

**PipeSequence:**

- `steps` MUST have at least one entry.
- `nb_output` and `multiple_output` MUST NOT both be set on the same step.
- `batch_over` and `batch_as` MUST either both be present or both be absent.
- `batch_over` and `batch_as` MUST NOT be the same value.

**PipeParallel:**

- At least one of `add_each_output` or `combined_output` MUST be set.

**PipeCondition:**

- Exactly one of `expression_template` or `expression` MUST be present.
- `outcomes` MUST have at least one entry.

**PipeBatch:**

- `input_list_name` MUST be in `inputs`.
- `input_item_name` MUST NOT be empty.
- `input_item_name` MUST NOT equal `input_list_name`.
- `input_item_name` MUST NOT equal any key in `inputs`.

### Stage 5: Reference Validation (Bundle-Level)

Within a single bundle:

- Bare concept references MUST resolve to: a native concept, a concept in the current bundle, or a concept in the same domain (same package).
- Bare pipe references MUST resolve to: a pipe in the current bundle, or a pipe in the same domain (same package).
- Domain-qualified references MUST resolve within the current package.
- Cross-package references (`->` syntax) are deferred to package-level validation.

### Stage 6: Manifest Validation

For `METHODS.toml`:

1. `[package]` section MUST be present.
2. `address` MUST match the pattern `^[a-zA-Z0-9._-]+\.[a-zA-Z0-9._-]+/[a-zA-Z0-9._/-]+$`.
3. `version` MUST be valid semver.
4. `description` MUST NOT be empty.
5. All dependency aliases MUST be unique and `snake_case`.
6. All dependency addresses MUST match the hostname/path pattern.
7. All dependency version constraints MUST be valid.
8. Domain paths in `[exports]` MUST be valid domain codes.
9. Domain paths in `[exports]` MUST NOT use reserved domains (`native`, `mthds`, `pipelex`).
10. All pipe codes in `[exports]` MUST be valid `snake_case`.

### Stage 7: Package-Level Validation

After loading all bundles and resolving dependencies:

1. Bundles MUST NOT declare a domain starting with a reserved segment.
2. Cross-package references MUST reference known dependency aliases.
3. Cross-package pipe references MUST target exported pipes.
4. Exported pipes MUST exist in the scanned bundles.
5. Same-domain concept and pipe code collisions across bundles are errors.

### Stage 8: Lock File Validation

For `methods.lock`:

1. Each entry's `version` MUST be valid semver.
2. Each entry's `hash` MUST match `sha256:[0-9a-f]{64}`.
3. Each entry's `source` MUST start with `https://`.

### Stage 9: Publish Validation

The `mthds pkg publish` command runs 15 checks across seven categories. These are advisory (for distribution readiness) rather than mandatory for loading:

| # | Category | Check | Level |
|---|----------|-------|-------|
| 1 | Manifest | `METHODS.toml` exists and parses | Error |
| 2 | Manifest | Authors are specified | Warning |
| 3 | Manifest | License is specified | Warning |
| 4 | Manifest | `mthds_version` constraint is parseable | Error |
| 5 | Manifest | `mthds_version` is satisfiable by current standard version | Warning |
| 6 | Bundle | At least one `.mthds` file exists | Error |
| 7 | Bundle | All bundles parse without error | Error |
| 8 | Export | Every exported pipe exists in the scanned bundles | Error |
| 9 | Visibility | Cross-domain pipe references respect export rules | Error |
| 10 | Visibility | Bundles do not use reserved domains | Error |
| 11 | Visibility | Cross-package references use known dependency aliases | Error |
| 12 | Dependency | No wildcard (`*`) version constraints | Warning |
| 13 | Lock file | `methods.lock` exists for packages with remote dependencies | Error |
| 14 | Lock file | Lock file includes all remote dependency addresses | Warning |
| 15 | Git | Working directory is clean; version tag does not already exist | Warning/Error |

---

## Page: Package Loading

This page details the dependency resolution algorithm, library assembly, and namespace isolation mechanics.

### Dependency Resolution Algorithm

Dependency resolution is a recursive process that handles local paths, remote fetching, cycle detection, and diamond dependencies.

```
function resolve_all_dependencies(manifest, package_root):
    local_resolved = []
    remote_deps = []

    for dep in manifest.dependencies:
        if dep.path is not null:
            local_resolved.append(resolve_from_filesystem(dep, package_root))
        else:
            remote_deps.append(dep)

    resolved_map = {}        // address -> resolved dependency
    constraints = {}         // address -> list of version constraints
    resolution_stack = set() // for cycle detection

    resolve_transitive_tree(remote_deps, resolution_stack, resolved_map, constraints)

    return local_resolved + values(resolved_map)
```

**Key rules:**

- **Local path dependencies** are resolved directly from the filesystem. They are NOT resolved transitively — only the root package's local paths are honored.
- **Remote dependencies** are resolved transitively. If Package A depends on Package B, and B depends on Package C, then C is also resolved.
- **Cycle detection** uses a DFS stack set. If an address is encountered while already on the stack, the resolver reports a cycle error.

### Diamond Dependency Handling

Diamond dependencies occur when the same package is required by multiple dependents with different version constraints.

```
function resolve_diamond(address, all_constraints, available_tags):
    parsed_constraints = [parse_constraint(c) for c in all_constraints]
    for version in sorted(available_tags, ascending):
        if all(constraint.matches(version) for constraint in parsed_constraints):
            return version
    error("No version satisfies all constraints")
```

This is Minimum Version Selection applied to multiple constraints simultaneously. The resolver:

1. Collects all version constraints from every dependent that requires the package.
2. Lists available version tags from the remote repository (cached to avoid repeated network calls).
3. Sorts versions in ascending order.
4. Selects the first version that satisfies ALL constraints.

When a diamond re-resolution picks a different version than previously resolved, the stale sub-dependency constraints contributed by the old version are recursively removed before re-resolving.

### VCS Fetching

Remote packages are fetched via Git with a three-tier resolution chain:

1. **Local cache check** — look in `~/.mthds/packages/{address}/{version}/`.
2. **VCS fetch** — if not cached, clone the repository:
    - Map address to clone URL: prepend `https://`, append `.git`.
    - List remote tags: `git ls-remote --tags {url}`.
    - Filter tags that parse as valid semver (strip optional `v` prefix).
    - Select version via MVS.
    - Clone at the selected tag: `git clone --depth 1 --branch {tag}`.
3. **Cache storage** — store the cloned directory under `~/.mthds/packages/{address}/{version}/`, removing the `.git` directory.

Cache writes use a staging directory with atomic rename for safety against partial writes.

### Library Assembly

After resolving all dependencies, the runtime assembles a **library** — the complete set of loaded bundles indexed by domain and package:

```
Library:
    local_bundles:     domain -> list of bundle blueprints
    dependency_bundles: (alias, domain) -> list of bundle blueprints
    exported_pipes:    (alias, domain) -> set of pipe codes
    main_pipes:        (alias, domain) -> pipe code
```

The library provides the lookup context for namespace resolution. When a pipe reference like `scoring_lib->scoring.compute_weighted_score` is encountered:

1. Find the dependency by alias `scoring_lib`.
2. Look up domain `scoring` in the dependency's bundles.
3. Find the pipe `compute_weighted_score`.
4. Verify it is exported (in the `[exports]` list or declared as `main_pipe`).

### Namespace Isolation

Packages isolate namespaces completely. Two packages declaring `domain = "recruitment"` have independent concept and pipe namespaces. The isolation boundary is the package, not the domain.

Within a single package, bundles sharing the same domain merge into a single namespace. Collisions (duplicate concept or pipe codes within the same domain of the same package) are errors.

The reference implementation enforces isolation through the library structure: lookups are always scoped to a specific package (identified by alias for dependencies, or "current package" for local references).

### Visibility Checking Algorithm

The visibility checker runs after library assembly:

```
function check_visibility(manifest, bundles):
    exported_pipes = build_export_index(manifest)
    main_pipes = build_main_pipe_index(bundles)

    errors = []

    // Check reserved domains
    for bundle in bundles:
        if bundle.domain starts with reserved segment:
            errors.append(reserved domain error)

    // Check intra-package cross-domain references
    for bundle in bundles:
        for (pipe_ref, context) in bundle.collect_pipe_references():
            if pipe_ref is special outcome ("fail", "continue"):
                skip
            if pipe_ref is cross-package (contains "->"):
                validate alias exists in dependencies
            else:
                ref = parse_pipe_ref(pipe_ref)
                if ref is qualified and not same domain as bundle:
                    if ref.pipe_code not in exported_pipes[ref.domain]:
                        if ref.pipe_code != main_pipes[ref.domain]:
                            errors.append(visibility error)

    return errors
```

The checker runs three passes:

1. **Reserved domain check** — ensures no bundle uses `native`, `mthds`, or `pipelex` as the first domain segment.
2. **Intra-package visibility** — ensures cross-domain pipe references target exported or main_pipe pipes.
3. **Cross-package alias validation** — ensures `->` references use aliases declared in `[dependencies]`.

### See Also

- [Specification: Namespace Resolution Rules](03-specification.md#page-namespace-resolution-rules) — the formal resolution algorithm.
- [The Package System: Version Resolution](02-the-package-system.md#page-version-resolution) — how MVS works.

---

## Page: Building Editor Support

This page describes how to build editor support for `.mthds` files — syntax highlighting, semantic tokens, schema validation, and formatting.

### TextMate Grammar

The primary mechanism for syntax highlighting is a TextMate grammar layered on top of TOML. The grammar recognizes MTHDS-specific constructs within the TOML structure.

**Scope hierarchy:**

The base scope is `source.mthds` (extending `source.toml`). Key MTHDS-specific scopes include:

- `meta.pipe-section.mthds` — `[pipe.<name>]` table headers
- `meta.concept-section.mthds` — `[concept.<name>]` table headers
- `entity.name.type.mthds` — concept codes in `PascalCase`
- `entity.name.function.mthds` — pipe codes in references
- `string.template.mthds` — prompt template strings
- `variable.other.jinja.mthds` — Jinja2 variables (`{{ }}`, `@var`, `$var`)

**Key patterns to recognize:**

1. **Pipe sections** — table headers matching `[pipe.<snake_case>]` or `[pipe.<snake_case>.<subfield>]`.
2. **Concept sections** — table headers matching `[concept.<PascalCase>]` or `[concept.<PascalCase>.structure]`.
3. **Pipe type values** — string values that match the nine pipe type names (`PipeLLM`, `PipeFunc`, etc.) in the `type` field of pipe sections.
4. **Prompt templates** — multi-line strings containing Jinja2 syntax and `@variable` / `$variable` shorthand.
5. **Cross-package references** — strings containing `->` (the arrow separator for package-qualified references).
6. **Model references** — string values with `$` or `@` prefixes in the `model` field.

**Implementation approach:**

The reference implementation's TextMate grammar is structured as a set of injection grammars that layer on top of the TOML base grammar. This allows TOML syntax to remain correct while MTHDS-specific constructs receive additional semantic coloring.

### Semantic Token Types

Beyond TextMate grammar-based highlighting, an LSP-aware extension can provide semantic tokens for more precise highlighting. The reference implementation defines 7 MTHDS-specific semantic token types:

| Token Type | Description | Applied To |
|------------|-------------|------------|
| `mthdsConcept` | Concept names | `ContractClause`, `Text`, `Image`, concept references in `inputs`, `output`, `refines` |
| `mthdsPipeType` | Pipe type values | `PipeLLM`, `PipeSequence`, etc. in the `type` field |
| `mthdsDataVariable` | Data variables in prompts | `@variable_name`, `$variable_name`, `{{ variable }}` |
| `mthdsPipeName` | Pipe names in references | Pipe codes in `steps[].pipe`, `branch_pipe_code`, `outcomes`, etc. |
| `mthdsPipeSection` | Pipe section headers | The entire `[pipe.my_pipe]` header |
| `mthdsConceptSection` | Concept section headers | The entire `[concept.MyConcept]` header |
| `mthdsModelRef` | Model field references | Values in the `model` field (e.g., `$writing-factual`, `@default-text-from-pdf`) |

**Detection algorithm for semantic tokens:**

The semantic token provider parses the TOML document and walks the AST to identify MTHDS-specific elements. For each token, it determines the type based on:

1. **Context** — is this value inside a `[pipe.*]` section or a `[concept.*]` section?
2. **Field name** — is this the `type` field, the `model` field, a prompt field, an `inputs`/`output` field?
3. **Value pattern** — does the value match `PascalCase` (concept), `snake_case` (pipe), or have a `$`/`@` prefix (model ref)?

### Using the MTHDS JSON Schema

The MTHDS JSON Schema (`mthds_schema.json`) provides machine-readable validation for `.mthds` files. It is a standard JSON Schema document that describes the complete bundle structure.

**What the schema covers:**

- Header fields (`domain`, `description`, `system_prompt`, `main_pipe`)
- Concept definitions (simple and structured forms)
- All nine pipe types with their specific fields
- Sub-pipe blueprints (`steps`, `branches`, `outcomes`, `construct`)
- Field types and their constraints

**How to use it:**

1. **For validation** — feed the parsed TOML (as JSON) through a JSON Schema validator. This catches structural errors (wrong field types, missing required fields) without implementing MTHDS-specific validation logic.
2. **For autocompletion** — use the schema's `properties` and `enum` values to suggest field names and valid values.
3. **For hover documentation** — use the schema's `description` fields to show documentation on hover.

**Generating the schema:**

The reference implementation auto-generates the schema from the Pydantic data model (`PipelexBundleBlueprint`) using the `pipelex-dev generate-mthds-schema` command. This ensures the schema stays in sync with the implementation. Alternative implementations can use the published schema directly.

**Configuring schema association:**

In the `plxt.toml` configuration, associate `.mthds` files with the schema:

```toml
[[rule]]
include = ["**/*.mthds"]

[rule.schema]
path = "path/to/mthds_schema.json"
```

### LSP Integration Points

For a full language server implementation, consider these integration points:

- **Diagnostics** — run validation (Stages 2–7 from the [Validation Rules](#page-validation-rules) page) and report errors as LSP diagnostics.
- **Completion** — suggest pipe type names, native concept codes, field type names, concept codes from the current bundle, and pipe codes for references.
- **Hover** — show concept descriptions, pipe signatures, and field documentation.
- **Go to Definition** — navigate from a concept/pipe reference to its definition (may span files for domain-qualified or cross-package references).
- **Find References** — find all usages of a concept or pipe across bundles.
- **Rename** — rename a concept or pipe code across all references in the package.

### See Also

- [Tooling: Editor Support](04-cli-and-guides.md#page-editor-support) — user-facing editor documentation.
- [Tooling: MTHDS JSON Schema](04-cli-and-guides.md#page-mthds-json-schema) — user-facing schema documentation.

---

## Page: Design Philosophy

MTHDS was designed with a specific set of principles that inform every decision in the standard. Understanding these principles helps explain why the standard works the way it does.

### Filesystem as Interface

MTHDS packages are directories of text files. `.mthds` bundles are TOML. `METHODS.toml` is TOML. `methods.lock` is TOML. There are no binary formats, no databases, no proprietary encodings.

This means:

- **Version control works natively.** Every change to a method is a diff. Merge conflicts are resolvable by humans.
- **Agents can read and write methods.** AI agents that work with text files can create, modify, and validate MTHDS files without special tooling.
- **No vendor lock-in.** Any tool that reads TOML can read MTHDS files. The standard does not require any specific runtime, editor, or platform.

### Progressive Enhancement

MTHDS is designed so that each layer of functionality is opt-in:

1. **A single `.mthds` file works on its own.** No manifest, no package, no configuration. This is the entry point for learning and prototyping.
2. **Add a `METHODS.toml` to get packaging.** A globally unique address, version, and visibility controls. No behavior changes for the bundles themselves.
3. **Add `[dependencies]` to compose with others.** Cross-package references become available. Existing bundles continue to work unchanged.
4. **Publish to the ecosystem.** Registry indexes crawl your package. The Know-How Graph discovers your methods. No changes to your files are required.

Each layer builds on the previous one without breaking it. A standalone bundle that works today continues to work unchanged inside a package.

### Type-Driven Composability

Every pipe in MTHDS declares a typed signature: the concepts it accepts and the concept it produces. This is not just documentation — it is the foundation of the system.

Typed signatures enable:

- **Compile-time validation.** A runtime can verify that the output of one pipe is compatible with the input of the next before executing anything.
- **Semantic discovery.** The Know-How Graph answers "I have a `Document`, I need a `NonCompeteClause`" by traversing typed signatures and refinement hierarchies.
- **Auto-composition.** When no single pipe transforms X to Y, the graph can discover multi-step chains through intermediate concepts.

This contrasts with text-based approaches where capabilities are described in natural language. Text descriptions enable keyword search but not type-safe composition.

### Federated Distribution

MTHDS follows a federated model: decentralized storage with centralized discovery.

- **Storage is decentralized.** Packages live in Git repositories owned by their authors. There is no central package host. The package address (e.g., `github.com/acme/legal-tools`) IS the fetch location.
- **Discovery is centralized.** Registry indexes crawl and index packages without owning them. Multiple registries can coexist, each serving different communities.

This mirrors how the web works: content is hosted anywhere, search engines index it. No single entity controls the ecosystem.

### Packages Own Namespaces, Domains Carry Meaning

Domains are semantic labels that carry meaning about what a bundle is about — `legal.contracts`, `scoring`, `recruitment`. But domains do not merge across packages. Two packages declaring `domain = "recruitment"` have completely independent namespaces.

The package is the isolation boundary. Cross-package references are always explicit (`alias->domain.name`). There is no implicit coupling through shared domain names.

This is a deliberate design choice. Merging domains across packages would create fragile implicit coupling: any package declaring a domain could inject concepts into your namespace. Instead, cross-package composition is explicit — through dependencies and typed references.

The domain name remains valuable for discovery. Searching the Know-How Graph for "all packages in the recruitment domain" is meaningful. But discovery is not namespace merging.

---

## Page: Comparison with Agent Skills

Both MTHDS and [Agent Skills](https://agentskills.io/) address the problem of defining and discovering AI capabilities. They take fundamentally different approaches, reflecting different design goals.

### Scope Comparison

| Dimension | Agent Skills | MTHDS |
|-----------|-------------|-------|
| **Format** | JSON or YAML manifest describing a skill | TOML-based language with concepts, pipes, domains |
| **Type system** | Text descriptions for inputs/outputs | Typed signatures with concept refinement |
| **Composition** | No built-in composition model | Controllers (sequence, parallel, condition, batch) |
| **Package system** | No dependencies or versioning | Full package system with manifest, lock file, dependencies |
| **Discovery** | Text-based search (name, description, tags) | Typed search ("I have X, I need Y") + text search |
| **Distribution** | Hosted registry or skill files | Git-native, federated (decentralized storage, centralized discovery) |
| **CLI** | No CLI | Full `mthds` CLI with package management |

### What Agent Skills Does Well

Agent Skills is deliberately minimal. A skill is a manifest file that describes what an AI capability does in natural language. This makes it:

- **Simple to adopt.** Writing a skill manifest requires no new syntax — it is standard JSON/YAML.
- **Runtime-agnostic.** Any AI framework can consume a skill manifest.
- **Easy to discover.** Text descriptions are searchable by keywords, tags, and categories.

The simplicity is a feature. Agent Skills serves the use case of "tell me what capabilities exist" without prescribing how they are implemented or composed.

### What MTHDS Adds

MTHDS targets a different use case: defining, composing, and distributing AI methods with type safety.

- **Typed signatures** enable semantic discovery that text descriptions cannot support. "Find pipes that accept `Document` and produce `NonCompeteClause`" is a precise query with a precise answer.
- **Built-in composition** means multi-step methods are defined in the same file as the individual steps. A PipeSequence that extracts, analyzes, and summarizes is a single method, not an external orchestration.
- **A real package system** with versioned dependencies, lock files, and visibility controls makes methods reusable across teams and organizations.

### Design Parallels

Despite different approaches, the two standards share design principles:

- **Progressive disclosure.** Agent Skills' tiered skill hosting (built-in → user-created → community) parallels MTHDS's progressive enhancement (single file → package → ecosystem).
- **Skills as files.** Both standards treat capabilities as human-readable text files, not database entries or API registrations.
- **Federated distribution.** Both favor decentralized storage with centralized discovery.

### When to Use Which

- Use **Agent Skills** when you need a lightweight manifest that describes what an AI capability does, for use with frameworks that support the Agent Skills standard.
- Use **MTHDS** when you need typed composition, versioned dependencies, and type-safe discovery across packages.

The two standards are not mutually exclusive. A package's `main_pipe` could be exposed as an Agent Skill for frameworks that consume that format.

---

## Page: Roadmap

The MTHDS standard is at version `1.0.0`. This page outlines planned and potential directions for future development.

### Near-Term

- **Registry reference implementation.** A reference implementation for the registry index, enabling `mthds pkg search` to query remote registries in addition to local packages.
- **Package signing.** Optional signed manifests for enterprise use, enabling verifiable authorship and integrity beyond SHA-256 content hashes.
- **Cross-package concept refinement validation at install time.** The specification allows validation of concept refinement across packages at both install time and load time. The current reference implementation validates at load time only. Install-time validation would detect breaking changes earlier.

### Medium-Term

- **Know-How Graph web interface.** A web-based explorer for the Know-How Graph, enabling visual navigation of concept hierarchies and pipe chains across the public ecosystem.
- **Proxy/mirror support.** Configurable proxy for package fetching, supporting speed, reliability, and air-gapped environments (similar to Go's `GOPROXY`).
- **MTHDS language server protocol (LSP).** A standalone LSP server that provides diagnostics, completion, hover, and go-to-definition for `.mthds` files, usable by any editor.

### Long-Term

- **Conditional concept fields.** Allow concept structure fields to be conditionally present based on the values of other fields.
- **Parametric concepts.** Concepts that accept type parameters (e.g., `Result<T>` where T is another concept).
- **Runtime interoperability standard.** A specification for how different MTHDS runtimes can exchange concept instances, enabling cross-runtime pipe invocation.

### Contributing to the Roadmap

The roadmap is shaped by community needs. If you have a use case that the standard does not yet support, open an issue in the MTHDS standard repository. Proposals that include concrete `.mthds` examples demonstrating the need are especially helpful.

---

## Page: Contributing

MTHDS is an open standard. Contributions are welcome — whether they are bug reports, specification clarifications, tooling improvements, or new packages.

### Ways to Contribute

#### Report Issues

If you find an inconsistency in the specification, a bug in a tool, or an edge case that is not documented, open an issue in the MTHDS standard repository. Include:

- What you expected to happen.
- What actually happened.
- A minimal `.mthds` or `METHODS.toml` example that demonstrates the issue.

#### Propose Specification Changes

Specification changes follow a structured process:

1. **Open a discussion** describing the problem and your proposed solution. Include concrete `.mthds` examples showing before/after.
2. **Draft the change** as a pull request against the specification. Normative changes use RFC 2119 language (`MUST`, `SHOULD`, `MAY`).
3. **Review** by the maintainers and community. Changes to the specification require careful consideration of backward compatibility.
4. **Merge and release** as a new minor or major version of the standard.

#### Build Packages

The ecosystem grows through packages. Publish packages that solve real problems in your domain. Well-documented packages with clear concept hierarchies and typed pipe signatures make the Know-How Graph more useful for everyone.

#### Build Tools

The standard is tool-agnostic. If you build an MTHDS-related tool — an alternative runtime, an editor extension, a registry implementation, a visualization tool — share it with the community.

### Coding Standards for the Reference Implementation

The reference implementation (Pipelex) has its own coding standards and contribution guidelines. See the Pipelex repository for details.

### License

The MTHDS standard specification is open. Implementations may use any license. The reference implementation's license is specified in its repository.
