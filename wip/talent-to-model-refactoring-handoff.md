# Handoff: Talent-to-Model Refactoring — Skills Update

## What changed in `pipelex`

PipeSpec subclasses no longer use talent fields. The `pipelex-agent pipe` command now accepts a `model` field with preset names directly, instead of talent names that got resolved to presets.

### Before

```json
{
  "type": "PipeLLM",
  "pipe_code": "summarize",
  "description": "Summarize document",
  "inputs": {"document": "Document"},
  "output": "Summary",
  "llm_talent": "creative-writer",
  "prompt": "Summarize:\n\n@document"
}
```

### After

```json
{
  "type": "PipeLLM",
  "pipe_code": "summarize",
  "description": "Summarize document",
  "inputs": {"document": "Document"},
  "output": "Summary",
  "model": "$writing-creative",
  "prompt": "Summarize:\n\n@document"
}
```

### Field mapping (old talent → new model value)

| Pipe type | Old field | New field | Example old value | Example new value |
|-----------|-----------|-----------|-------------------|-------------------|
| PipeLLM | `llm_talent` | `model` | `"creative-writer"` | `"$writing-creative"` |
| PipeLLM | `llm_talent` | `model` | `"data-retrieval"` | `"$retrieval"` |
| PipeLLM | `llm_talent` | `model` | `"engineer"` | `"$engineering-structured"` |
| PipeLLM | `llm_talent` | `model` | `"coder"` | `"$engineering-code"` |
| PipeLLM | `llm_talent` | `model` | `"code-analyzer"` | `"$engineering-codebase-analysis"` |
| PipeLLM | `llm_talent` | `model` | `"hr-expert"` | `"$writing-factual"` |
| PipeLLM | `llm_talent` | `model` | `"accounting-expert"` | `"$writing-factual"` |
| PipeLLM | `llm_talent` | `model` | `"vision-language-model"` | `"$vision"` |
| PipeLLM | `llm_talent` | `model` | `"visual-designer"` | `"$img-gen-prompting"` |
| PipeExtract | `extract_talent` | `model` | `"pdf-basic-text-extractor"` | `"@default-text-from-pdf"` |
| PipeExtract | `extract_talent` | `model` | `"image-text-extractor"` | `"@default-extract-image"` |
| PipeExtract | `extract_talent` | `model` | `"full-document-extractor"` | `"@default-extract-document"` |
| PipeExtract | `extract_talent` | `model` | `"web-page-extractor"` | `"@default-extract-web-page"` |
| PipeImgGen | `img_gen_talent` | `model` | `"gen-image"` | `"$gen-image"` |
| PipeImgGen | `img_gen_talent` | `model` | `"gen-image-fast"` | `"$gen-image-fast"` |
| PipeImgGen | `img_gen_talent` | `model` | `"gen-image-high-quality"` | `"$gen-image-high-quality"` |
| PipeSearch | `search_talent` | `model` | `"web-search"` | `"$standard"` |
| PipeSearch | `search_talent` | `model` | `"web-search-deep"` | `"$deep"` |

### Key behavior changes

1. **`model` is optional** (`str | None`, default `None`). When omitted, the runtime uses its configured default. Previously, `search_talent` defaulted to `"web-search"` — now `model` defaults to `None`.
2. **No backward compatibility**. The CLI no longer accepts `llm_talent`, `extract_talent`, `img_gen_talent`, `search_talent`, `talent_name`, or `talent` fields. It will reject them as unexpected fields.
3. **No reverse resolution**. The CLI no longer resolves preset names back to talent names. Agents must send presets directly.
4. **`pipelex-agent models` still outputs talent mappings**. The "Talent Mappings" section remains in the output — it's now guidance for choosing the right preset, not a required lookup. The hint text changed to: _"Talent mappings show which model preset corresponds to each talent. When building pipes, use the model preset name directly as the 'model' field..."_

## Skills files that need updating

### 1. `skills/skills/shared/mthds-agent-guide.md`

**Line 280**: Update the `pipelex pipe` command description and example.

- Change field names from `llm_talent`/`extract_talent`/`img_gen_talent`/`search_talent` to `model`
- Change example values from talent names to preset names
- Remove the instruction to "use talent names, not preset names" — it's now the opposite

### 2. `skills/skills/mthds-build/SKILL.md`

**Line 262**: Update the field name instructions.

- Old: _"the talent field matching the pipe type: `llm_talent` for PipeLLM, `extract_talent` for PipeExtract..."_
- New: _"`model` for PipeLLM/PipeExtract/PipeImgGen/PipeSearch (use preset names from `pipelex-agent models`)"_

### 3. `skills/skills/mthds-build/references/manual-build-phases.md`

Extensive updates needed:

- **Lines 85-88**: Replace talent field name instructions with `model`
- **Lines 98, 209, 221, 233, 248, 259**: Replace `"llm_talent": "..."` / `"extract_talent": "..."` / etc. with `"model": "$preset"`
- **Lines 292-294**: Update CLI command examples
- **Line 339**: Remove or rewrite the note about CLI using talent names — it now uses presets directly

### 4. `skills/skills/mthds-build/references/talents-and-presets.md`

**Complete rewrite needed.** The core premise ("always use Talent names, never preset names") is now inverted. Suggested new content:

- Explain that `pipelex-agent models` lists available presets
- The Talent Mappings section in the output is guidance for choosing the right preset
- When calling `pipelex-agent pipe`, use the preset name directly as the `model` field
- Keep the mapping table as a reference, but flip the emphasis: presets are what you use, talents explain the intent

### 5. `skills/skills/mthds-edit/SKILL.md`

**Line 143**: Update the reference description.

- Old: _"read when setting or changing talent fields in a pipe. Use talent names..."_
- New: _"read when setting or changing the model field in a pipe. Use preset names from `pipelex-agent models`"_

### 6. `skills/skills/mthds-edit/references/talents-and-presets.md`

Same rewrite as `mthds-build/references/talents-and-presets.md` (these may be identical files or copies).

## What NOT to change

- The `pipelex-agent models` command itself — it still outputs talent mappings as guidance
- The talent enums in `pipelex/builder/talents/` — they still exist and are used by `models` output
- The `pipelex.toml` config — talent preset mappings remain
- The `pipelex-agent concept` command — unaffected (concepts don't use talents)
