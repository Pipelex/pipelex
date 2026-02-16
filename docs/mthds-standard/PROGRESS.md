# MTHDS Documentation — Progress

| # | Document | Status | Session Date |
|---|----------|--------|-------------|
| 1 | `03-specification.md` | done | 2026-02-16 |
| 2 | `01-the-language.md` | done | 2026-02-16 |
| 3 | `02-the-package-system.md` | done | 2026-02-16 |
| 4 | `00-home-and-overview.md` | done | 2026-02-16 |
| 5 | `04-cli-and-guides.md` | done | 2026-02-16 |
| 6 | `05-implementers-and-about.md` | done | 2026-02-16 |

## Notes

### Session 1 — 2026-02-16 — `03-specification.md`

**Decisions made:**

- All field names, enum values, and validation rules were verified against the codebase (code wins over design doc).
- The design doc used `mthds_version = ">=0.2.0"` in examples, but the actual `MTHDS_STANDARD_VERSION` in code is `"1.0.0"`. The spec reflects the real current version.
- Native concepts: the full list of 11 native concepts was documented (the design doc only listed a few with "etc."). Complete list: Dynamic, Text, Image, Document, Html, TextAndImages, Number, ImgGenPrompt, Page, JSON, Anything.
- The `source` field on `PipelexBundleBlueprint`, `ConceptBlueprint`, and `PipeBlueprint` is an internal loader field (not user-facing in .mthds files). Omitted from the spec.
- `PipeCompose.construct_blueprint` is the internal Python field name; in MTHDS files the key is `construct` (via Pydantic alias). The spec uses `construct`.
- The `PipeCondition.expression_template` and `expression` are mutually exclusive (exactly one required) — confirmed in code.
- `PipeBatch.input_item_name` must not equal any key in inputs (not just `input_list_name`) — confirmed in code.

**Open questions for future docs:**

- The `model` field on PipeLLM/PipeImgGen/PipeExtract uses routing profile syntax (`$prefix`, `@prefix`). This is runtime-specific behavior. The spec documents the field as a string; the routing profile mechanics belong in the "For Implementers" section.
- The `TemplateBlueprint` object form of `PipeCompose.template` (with `category`, `templating_style`, `extra_context`) is an advanced feature. Documented at high level; details belong in the Language doc.
- Cross-package concept refinement validation (install-time + load-time) is described in the design doc but the current code validates at load time only. The spec does not prescribe when validation occurs — that is an implementation concern.

### Session 2 — 2026-02-16 — `01-the-language.md`

**Structure:**

- 6 pages: Bundles, Concepts, Pipes — Operators, Pipes — Controllers, Putting It All Together, Domains, Namespace Resolution.
- Added a "Putting It All Together" page (not in the original sitemap) as a bridge between Pipes and Domains. It uses the joke generation bundle from the spec as a complete worked example showing concepts, operators, and controllers working together.

**Decisions made:**

- All technical claims verified against the codebase (5 spot-checks passed: PipeType enum, NativeConceptCode enum, ConceptStructureBlueprintFieldType enum, PipelexBundleBlueprint header fields, PipeBatch validation rules).
- Followed the teaching tone: example-first, explanation-second. Every concept introduced with a `.mthds` snippet.
- Used the same terminology as the spec (`03-specification.md`): "bundle", "concept code", "pipe code", "domain code", "bare reference", "domain-qualified", "package-qualified".
- The `model` field routing profile syntax (`$prefix`, `@prefix`) is mentioned briefly in tables but not explained in depth — consistent with the spec's approach of documenting it as a string. Routing profile mechanics remain deferred to "For Implementers".
- The `TemplateBlueprint` object form of `PipeCompose.template` is shown with a brief example. The `category` field's enum values and `extra_context` details are not exhaustively documented — these are advanced features better suited for the Implementers doc.
- Cross-references use `[text](file.md#anchor)` format. Some anchors (e.g., `02-the-package-system.md`) point to documents not yet written — these will resolve when those docs are created.

**Cross-document consistency:**

- All native concept codes match the spec's table exactly (11 codes, same order).
- All pipe types match the spec (5 operators, 4 controllers).
- Concept field types match the spec (8 types).
- The resolution flowchart in the Namespace Resolution page matches the spec's flowchart verbatim.
- Examples reused from the spec are copied exactly (joke generation bundle, CandidateProfile concept, scoring_lib cross-package example).

**Prep notes for next document (`02-the-package-system.md`):**

- The Language doc references the Package System doc in several "See Also" sections. The Package System doc should cover: package structure, METHODS.toml manifest, exports & visibility, dependencies, cross-package references, lock file, distribution, version resolution, and the Know-How Graph.
- Key codebase paths to verify: `manifest.py` (MthdsPackageManifest, PackageDependency, DomainExports, RESERVED_DOMAINS), `visibility.py` (PackageVisibilityChecker), `dependency_resolver.py`, `vcs_resolver.py`, `lock_file.py`, `semver.py`.

### Session 3 — 2026-02-16 — `02-the-package-system.md`

**Structure:**

- 9 pages: Package Structure, The Manifest, Exports & Visibility, Dependencies, Cross-Package References, The Lock File, Distribution, Version Resolution, The Know-How Graph.
- Progressive ordering: starts with directory layout, builds through manifest fields, visibility, dependencies, cross-package references, then moves to lock file, distribution, version resolution, and culminates with the Know-How Graph vision.

**Decisions made:**

- All technical details verified against the codebase (7 spot-checks passed: RESERVED_DOMAINS, MTHDS_STANDARD_VERSION, cache layout `~/.mthds/packages/`, VCS URL construction, MVS algorithm, local path deps not resolved transitively, lock file hash pattern).
- The cross-package scoring_lib example is reused from both the spec and the language doc for consistency across all three documents.
- Version constraint table includes all operators supported in code (`>=`, `<=`, `>`, `<`, `==`, `!=`, `^`, `~`, wildcard `*`, compound `,`) — verified against `VERSION_CONSTRAINT_PATTERN` regex in `manifest.py`.
- The hash computation algorithm matches `compute_directory_hash()` in `lock_file.py` exactly: rglob files, skip .git, sort by POSIX path, feed path string UTF-8 + raw bytes.
- Manifest discovery algorithm matches `find_package_manifest()` in `discovery.py`: walk up, stop at METHODS.toml or .git or root.
- The `PackageDependency` model in code has an `alias` field (populated from the TOML key during parsing), but the TOML representation uses the key directly — the doc correctly shows the TOML syntax where the key IS the alias.
- Visibility checker behavior confirmed: no manifest = all public, bare refs always allowed, same-domain always allowed, cross-domain checks exports list and main_pipe.

**Cross-document consistency:**

- All terminology matches `01-the-language.md` and `03-specification.md`: "bundle", "concept code", "pipe code", "domain code", "bare reference", "domain-qualified", "package-qualified".
- The three visibility rules (concepts always public, pipes private by default, main_pipe auto-exported) match the spec's `[exports]` section exactly.
- The scoring_lib cross-package example is identical across all three docs.
- The cross-package reference resolution steps match the spec's flowchart.
- Reserved domains listed consistently (`native`, `mthds`, `pipelex`).
- The `METHODS.toml` example uses `mthds_version = ">=1.0.0"` (consistent with Session 1's decision to use the real standard version `1.0.0`, not the design doc's `0.2.0`).

**Open questions for future docs:**

- The `mthds pkg publish` command runs validation checks. The number (mentioned as "15 checks" in the strategy doc) should be verified when writing the CLI reference in `04-cli-tooling-and-guides.md`.
- The `mthds pkg graph` command has `--from`, `--to`, `--check`, `--compose`, and `--max-depth` options. The auto-composition feature (graph traversal) should be documented in the CLI reference with practical examples.
- The `mthds pkg search` command has `--accepts` and `--produces` options for type-compatible search. These tie directly to the Know-How Graph and should be showcased in the "Discover Methods" guide.

**Prep notes for next document (`00-home-and-overview.md`):**

- The overview should introduce the Two Pillars (Language + Package System) and the Progressive Enhancement principle.
- It should provide 4 entry points as per the strategy doc: "Set up your editor", "Learn the language", "Read the specification", "Get started".
- Keep it concise (~200 words for landing, ~1000 words for "What is MTHDS?").
- All substance now exists in docs 01, 02, and 03 — the overview can reference them with confidence.

### Session 4 — 2026-02-16 — `00-home-and-overview.md`

**Structure:**

- 2 pages: Home (landing page), What is MTHDS? (conceptual overview).
- Home page uses Material for MkDocs `grid cards` for the four entry points: "Set Up Your Editor", "Learn the Language", "Read the Specification", "Get Started". "Set Up Your Editor" is listed first per the strategy doc's guidance.
- "What is MTHDS?" page covers: The Two Pillars, Core Concepts at a Glance, A Concrete Example, Progressive Enhancement, What Makes MTHDS Different, Where to Go Next.

**Decisions made:**

- Followed the strategy doc's tone guidelines: compelling, concise, no marketing speak, no superlatives. The standard speaks for itself.
- Pipelex does not appear anywhere in the document, consistent with the strategy doc's standard/implementation boundary.
- The joke generation bundle is reused as the concrete example, consistent with `03-specification.md` (lines 708–750) and `01-the-language.md` (lines 633–675). The example is copied exactly.
- Added a "Core Concepts at a Glance" table with analogies (concept = form with typed fields, pipe = processing step, domain = folder, bundle = source file, package = versioned library) as recommended by the strategy doc.
- Added a "What Makes MTHDS Different" section covering three differentiators: typed signatures, built-in composition, and a real package system. This is neutral and factual, not comparative or promotional.
- The `->` syntax explanation uses the same phrasing as the design doc: "chosen for readability by non-technical audiences."

**Cross-document consistency (5 spot-checks passed):**

- The joke generation example matches `03-specification.md` and `01-the-language.md` exactly.
- Five operators (PipeLLM, PipeFunc, PipeImgGen, PipeExtract, PipeCompose) and four controllers (PipeSequence, PipeParallel, PipeCondition, PipeBatch) confirmed against `PipeType` enum in `pipe_blueprint.py`.
- Progressive enhancement four layers (single file → package → dependencies → ecosystem) match `02-the-package-system.md` Package Structure page.
- `->` syntax and cross-package reference description consistent across all docs.
- Pipelex absent from the document, as required.

**Prep notes for next document (`04-cli-tooling-and-guides.md`):**

- This is the largest remaining document: CLI Reference (all commands), Tooling (Editor Support, Formatting & Linting, JSON Schema), Getting Started (Write Your First Method), and 4 Guides (Create Package, Use Deps, Publish, Discover).
- The `mthds pkg publish` validation checks count (strategy doc says "15 checks") should be verified against `publish_validation.py`.
- The `mthds pkg graph` command options (`--from`, `--to`, `--check`, `--compose`, `--max-depth`) should be documented with practical examples.
- The `mthds pkg search` command options (`--accepts`, `--produces`) should be showcased in the "Discover Methods" guide.
- CLI commands map to the `pipelex/cli/commands/pkg/` directory. VS Code extension info is in `../vscode-pipelex/editors/vscode/package.json`. The `plxt` CLI is in `../vscode-pipelex/crates/pipelex-cli/`.
- The "Write Your First Method" guide should walk through creating a `.mthds` file step by step, using the editor extension for syntax highlighting, `plxt fmt` for formatting, and `mthds validate` for validation.
- The document should not reference Pipelex in the CLI Reference, Tooling, or Guides sections (per the strategy doc's standard/implementation boundary). The `mthds` CLI is the standard's official tool.

### Session 5 — 2026-02-16 — `04-cli-and-guides.md`

**Structure:**

- 9 pages: CLI Reference, Editor Support, Formatting & Linting, MTHDS JSON Schema, Write Your First Method, Create a Package, Use Dependencies, Publish a Package, Discover Methods.
- CLI Reference covers 2 core commands (`validate`, `run`) and 11 package commands (`pkg init`, `list`, `add`, `lock`, `install`, `update`, `index`, `search`, `inspect`, `graph`, `publish`).
- Tooling covers the VS Code extension (7 semantic token types, formatting, schema validation), the `plxt` CLI (format/lint), and the MTHDS JSON Schema.
- Getting Started is a step-by-step tutorial creating a text summarizer bundle from scratch.
- Guides cover the four remaining workflows: creating a package, using dependencies, publishing, and discovering methods.

**Decisions made:**

- All CLI command flags verified against the actual code in `pipelex/cli/commands/pkg/app.py` and individual `*_cmd.py` files. Flag names, short aliases, and default values match the implementation exactly.
- The `mthds pkg add` default version is `0.1.0` (from code: `typer.Option(...) = "0.1.0"`), documented accurately.
- The `mthds pkg publish` validation runs 15 checks across 7 categories — confirmed by counting the check points in `publish_validation.py` (comments #1 through #14-15, spanning manifest, manifest completeness, mthds_version, bundles, exports, visibility, dependencies, lock file, and git checks).
- The `mthds pkg graph` command uses `package_address::concept_ref` format for `--from`/`--to` (confirmed in `graph_cmd.py:_parse_concept_id`). The native package address is `__native__` (confirmed in `graph/models.py:NATIVE_PACKAGE_ADDRESS`).
- The `mthds pkg search` command uses fuzzy matching for `--accepts`/`--produces` (confirmed in `search_cmd.py:_resolve_concept_fuzzy`), while `mthds pkg graph` uses precise concept IDs. The doc explains both approaches.
- The VS Code extension provides 7 MTHDS-specific semantic token types — verified against `package.json` `semanticTokenTypes` array: `mthdsConcept`, `mthdsPipeType`, `mthdsDataVariable`, `mthdsPipeName`, `mthdsPipeSection`, `mthdsConceptSection`, `mthdsModelRef`.
- The `plxt` CLI has `format` (alias `fmt`) and `lint` (aliases `check`, `validate`) commands — verified in `args.rs`.
- Pipelex is mentioned only in the Editor Support page (the extension is named "Pipelex" in the marketplace) and in the Formatting & Linting page (plxt is distributed with Pipelex docs). The CLI Reference and Guides use only the `mthds` command, consistent with the strategy doc's standard/implementation boundary.

**Cross-document consistency (5 spot-checks passed):**

- MTHDS_STANDARD_VERSION = "1.0.0" — consistent with all previous documents.
- RESERVED_DOMAINS = {"native", "mthds", "pipelex"} — matches spec and all docs.
- Cache path `~/.mthds/packages/` — matches `02-the-package-system.md` Distribution page.
- Version constraint syntax in the "Use Dependencies" guide matches `02-the-package-system.md` Dependencies page.
- Visibility rules (concepts always public, pipes private by default, main_pipe auto-exported) described consistently in the "Create a Package" guide and the "Use Dependencies" guide.

**Open questions resolved from previous sessions:**

- The "15 checks" claim from the strategy doc is confirmed: the code runs checks numbered 1 through 14-15, mapping to 15 distinct validation points.
- The `mthds pkg graph` command options are fully documented with practical examples including auto-composition (`--compose`) and compatibility checking (`--check`).
- The `mthds pkg search` command's `--accepts` and `--produces` options are showcased in the "Discover Methods" guide with multiple examples.

**Prep notes for next document (`05-implementers-and-about.md`):**

- The Implementers section should cover: Building a Runtime (loader architecture, resolution order), Validation Rules (comprehensive list), Package Loading (dependency resolution, library isolation), Building Editor Support (TextMate grammar, semantic token types, JSON Schema usage, LSP integration).
- The About section should cover: Design Philosophy (filesystem as interface, progressive enhancement, type-driven composability, federated distribution), Comparison with Agent Skills (typed vs text-based, language vs format), Roadmap, Contributing.
- Key codebase paths: `pipelex/core/` for runtime architecture, `publish_validation.py` for validation rules, `dependency_resolver.py` for package loading, `../vscode-pipelex/editors/vscode/src/syntax/mthds/` for TextMate grammar internals, `../vscode-pipelex/editors/vscode/src/pipelex/semanticTokenProvider.ts` for semantic token implementation.
- The `model` field routing profile syntax (`$prefix`, `@prefix`, `~prefix`) should be documented in the Implementers section — this was deferred from the spec and language docs.
- The `TemplateBlueprint` advanced features (`category`, `templating_style`, `extra_context`) should also be covered in the Implementers section.

### Session 6 — 2026-02-16 — `05-implementers-and-about.md`

**Structure:**

- 7 pages: Building a Runtime, Validation Rules, Package Loading, Building Editor Support, Design Philosophy, Comparison with Agent Skills, Roadmap, Contributing.
- The Implementers section (4 pages) focuses on how to build a compliant MTHDS runtime, validator, or editor tool. Uses pseudocode algorithms and the reference implementation (Pipelex) for illustration, with consistent framing: "A compliant runtime may choose a different approach as long as it satisfies the specification."
- The About section (4 pages) covers design rationale, Agent Skills comparison, roadmap, and contributing.

**Decisions made:**

- The `model` field routing profile mechanics are documented in the "Building a Runtime" page under "Model Routing (Implementation-Specific)". The `$` prefix (LLM/image gen), `@` prefix (extraction), and no-prefix (direct model identifier) conventions are described. The `~` prefix mentioned in Session 5 prep notes was not found in the codebase — only `$` and `@` are used. The doc documents only what exists.
- The `TemplateBlueprint` advanced features are documented in the "Building a Runtime" page under "Template Blueprint (Advanced PipeCompose)". All 7 `TemplateCategory` values (`basic`, `expression`, `html`, `markdown`, `mermaid`, `llm_prompt`, `img_gen_prompt`) are listed — verified against `template_category.py`.
- The Validation Rules page consolidates all rules from the spec into 9 stages, ordered by when they should be enforced during loading. This provides implementers with a checklist.
- The publish validation table lists all 15 checks with their categories and severity levels — verified against `publish_validation.py`.
- The dependency resolution algorithm pseudocode matches `resolve_all_dependencies()` and `_resolve_transitive_tree()` in `dependency_resolver.py`: local deps are non-transitive, remote deps are transitive with DFS cycle detection and diamond handling.
- The visibility checking algorithm pseudocode matches `check_visibility_for_blueprints()` in `visibility.py`: three passes (reserved domains, intra-package visibility, cross-package aliases).
- The Agent Skills comparison uses neutral language per the strategy doc: "no feature comparisons that position MTHDS as 'better' than alternatives." The comparison table is factual.
- Pipelex is mentioned only with the "reference implementation" framing, consistent with the strategy doc's boundary. Pipelex appears in: "Building a Runtime" (model routing, template blueprint, Pydantic discriminated union), "Building Editor Support" (schema generator command), and "Contributing" (coding standards). It does not appear in the About section pages.

**Cross-document consistency (5 spot-checks passed):**

- RESERVED_DOMAINS = {"native", "mthds", "pipelex"} — matches all previous documents.
- MTHDS_STANDARD_VERSION = "1.0.0" — matches all previous documents.
- IssueCategory has 7 values matching "seven categories" for publish validation — consistent with `04-cli-and-guides.md`.
- TemplateCategory values match the 7 values listed in the doc — verified against codebase.
- `select_minimum_version_for_multiple_constraints` algorithm matches the diamond resolution pseudocode.

**Open questions resolved from previous sessions:**

- The `model` field routing profile syntax deferred from Sessions 1–2 is now documented in "Building a Runtime".
- The `TemplateBlueprint` advanced features deferred from Sessions 1–2 are now documented in "Building a Runtime".
- Cross-package concept refinement validation (install-time vs load-time) is addressed in the "Roadmap" page as a near-term goal, noting the current code validates at load time only.

**All documents are now complete.** A final consistency review across all 6 documents found no issues. Terminology, technical claims, and cross-references are consistent.

### Final Consistency Review — 2026-02-16

A comprehensive cross-document review was performed by re-reading all 6 documents and spot-checking against the codebase. Findings:

**Codebase spot-checks (7 checks, all passed):**

1. `PipeType` enum: 5 operators (PipeFunc, PipeImgGen, PipeCompose, PipeLLM, PipeExtract) + 4 controllers (PipeBatch, PipeCondition, PipeParallel, PipeSequence) — matches all docs.
2. `NativeConceptCode` enum: 11 values (Dynamic, Text, Image, Document, Html, TextAndImages, Number, ImgGenPrompt, Page, JSON, Anything) — matches spec and language doc exactly (same order).
3. `RESERVED_DOMAINS`: `frozenset({"native", "mthds", "pipelex"})` — consistent across all 6 docs.
4. `MTHDS_STANDARD_VERSION`: `"1.0.0"` — consistent across all 6 docs.
5. `ConceptStructureBlueprintFieldType` enum: 8 values (text, list, dict, integer, boolean, number, date, concept) — matches spec and language doc.
6. `TemplateCategory` enum: 7 values (basic, expression, html, markdown, mermaid, llm_prompt, img_gen_prompt) — matches implementers doc.
7. `NATIVE_PACKAGE_ADDRESS`: `"__native__"` — matches CLI reference in `04-cli-and-guides.md`.

**Cross-document consistency checks (5 checks, all passed):**

1. **Joke generation example**: Identical across `03-specification.md`, `01-the-language.md`, and `00-home-and-overview.md` (minor TOML whitespace alignment difference in the overview version — semantically identical).
2. **scoring_lib cross-package example**: Consistent across `03-specification.md`, `01-the-language.md`, `02-the-package-system.md`, and `05-implementers-and-about.md`.
3. **Reserved domains**: All mentions across all 6 docs consistently list `native`, `mthds`, `pipelex`.
4. **Cross-reference filenames**: All `[text](file.md#anchor)` links use correct filenames (`04-cli-and-guides.md`, `05-implementers-and-about.md`, etc.).
5. **Terminology**: "bundle", "concept code", "pipe code", "domain code", "bare reference", "domain-qualified", "package-qualified" used consistently across all docs.

**No issues found.** The documentation project is complete and internally consistent.
