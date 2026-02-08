# Talents vs Model Presets

The agent CLI uses human-friendly "talent" names that map to model presets. This shields you from needing to know specific model names.

## LLM Talents → Model Presets

| Talent | Model Preset |
|--------|--------------|
| `data-retrieval` | `$retrieval` |
| `hr-expert` | `$writing-factual` |
| `accounting-expert` | `$writing-factual` |
| `creative-writer` | `$writing-creative` |
| `engineer` | `$engineering-structured` |
| `coder` | `$engineering-code` |
| `code-analyzer` | `$engineering-codebase-analysis` |
| `vision-language-model` | `$vision` |
| `visual-designer` | `$img-gen-prompting` |

## Extract Talents → Model Presets

| Talent | Model Preset |
|--------|--------------|
| `pdf-basic-text-extractor` | `@default-text-from-pdf` |
| `image-text-extractor` | `@default-extract-image` |
| `full-document-extractor` | `@default-extract-document` |

## Image Generation Talents → Model Presets

| Talent | Model Preset |
|--------|--------------|
| `gen-image` | `$gen-image` |
| `gen-image-fast` | `$gen-image-fast` |
| `gen-image-high-quality` | `$gen-image-high-quality` |
