# MTHDS Documentation — Progress

| # | Document | Status | Session Date |
|---|----------|--------|-------------|
| 1 | `03-specification.md` | done | 2026-02-16 |
| 2 | `01-the-language.md` | pending | — |
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
