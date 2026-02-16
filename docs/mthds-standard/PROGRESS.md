# MTHDS Documentation — Progress

| # | Document | Status | Session Date |
|---|----------|--------|-------------|
| 1 | `03-specification.md` | done | 2026-02-16 |
| 2 | `01-the-language.md` | done | 2026-02-16 |
| 3 | `02-the-package-system.md` | pending | — |
| 4 | `00-home-and-overview.md` | pending | — |
| 5 | `04-cli-and-guides.md` | pending | — |
| 6 | `05-implementers-and-about.md` | pending | — |

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
