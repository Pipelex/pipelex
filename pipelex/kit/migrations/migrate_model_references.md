# Migration Guide: Prefix-Based Model Reference Syntax

## Overview

This is a **BREAKING CHANGE** that introduces explicit prefix syntax to disambiguate model references in Pipelex. Starting with this version, bare strings (without prefixes) are treated strictly as direct model handles.

## New Syntax

| Type      | Sigil  | Namespace (Canonical) | Example                                              |
|-----------|--------|----------------------|------------------------------------------------------|
| Preset    | `$`    | `preset:`            | `$llm_for_creativity` or `preset:llm_for_creativity` |
| Alias     | `@`    | `alias:`             | `@best-claude` or `alias:best-claude`                |
| Waterfall | `~`    | `waterfall:`         | `~cheap_llm` or `waterfall:cheap_llm`                |
| Handle    | (none) | `handle:` (optional) | `gpt-4o-mini` or `handle:gpt-4o-mini`                |

Both sigil prefixes (`$`, `@`, `~`) and namespace prefixes (`preset:`, `alias:`, `waterfall:`, `handle:`) are supported and interchangeable.

## What Changed

**Before (old syntax):**
```toml
# In .plx files or deck overrides
model = "cheap_llm"           # Was ambiguous - could be preset, waterfall, or handle
model = "best-claude"         # Was ambiguous - could be alias or handle
model = "llm_for_creativity"  # Was ambiguous - could be preset or handle
```

**After (new syntax):**
```toml
# In .plx files or deck overrides
model = "~cheap_llm"           # Explicit: this is a waterfall
model = "@best-claude"         # Explicit: this is an alias
model = "$llm_for_creativity"  # Explicit: this is a preset
model = "gpt-4o-mini"          # Bare string: direct model handle
```

## Migration Steps

### 1. Update .plx Files

Search for `model = "` in your `.plx` files and update each reference:

**For presets** (defined in `[llm.presets]`, `[extract.presets]`, `[img_gen.presets]`):
```toml
# Before
model = "writing-creative"

# After
model = "$writing-creative"
```

**For waterfalls** (defined in `[waterfalls]`):
```toml
# Before
model = "cheap_llm"
model = "smart_llm_for_structured"

# After
model = "~cheap_llm"
model = "~smart_llm_for_structured"
```

**For aliases** (defined in `[aliases]`):
```toml
# Before
model = "best-claude"
model = "base-gpt"

# After
model = "@best-claude"
model = "@base-gpt"
```

### 2. Update Deck Overrides

Update your `.pipelex/inference/deck/overrides.toml`:

```toml
# Before
[llm.choice_defaults]
for_text = "cheap_llm"
for_object = "cheap_llm_for_structured"

# After
[llm.choice_defaults]
for_text = "~cheap_llm"
for_object = "~cheap_llm_for_structured"
```

### 3. Update Python Code (if applicable)

If you're using model choice strings directly in Python code:

```python
# Before
llm_choice = "cheap_llm"

# After
llm_choice = "~cheap_llm"  # waterfall
llm_choice = "$llm_for_creativity"  # preset
llm_choice = "@best-claude"  # alias
```

## Common Patterns to Search and Replace

| Old Pattern                        | New Pattern                        | Type      |
|------------------------------------|------------------------------------|-----------|
| `cheap_llm`                        | `~small-llm`                       | Waterfall |
| `cheap_llm_for_structured`         | `~small-llm-structured`            | Waterfall |
| `cheap_llm_for_vision`             | `~small-llm-vision`                | Waterfall |
| `cheap_llm_for_creativity`         | `~small-llm-creative`              | Waterfall |
| `smart_llm`                        | `~premium-llm`                     | Waterfall |
| `smart_llm_for_structured`         | `~premium-llm-structured`          | Waterfall |
| `smart_llm_with_vision`            | `~premium-llm-vision`              | Waterfall |
| `llm_for_large_codebase`           | `~large-context-llm-code`          | Waterfall |
| `pdf_text_extractor`               | `~pdf_text_extractor`              | Waterfall |
| `image_text_extractor`             | `~image_text_extractor`            | Waterfall |
| `best-claude`                      | `@best-claude`                     | Alias     |
| `base-gpt`                         | `@best-gpt`                        | Alias     |
| `base-gemini`                      | `@best-gemini`                     | Alias     |
| `base-mistral`                     | `@best-mistral`                    | Alias     |
| `best-gpt`                         | `@best-gpt`                        | Alias     |
| `base-img-gen`                     | `@default-general` (img_gen)       | Alias     |
| `best-img-gen`                     | `@default-premium` (img_gen)       | Alias     |
| `fast-img-gen`                     | `@default-small` (img_gen)         | Alias     |
| `default-general`                  | `@default-general`                 | Alias     |
| `default-premium`                  | `@default-premium`                 | Alias     |
| `default-small`                    | `@default-small`                   | Alias     |
| `writing-creative`                 | `$writing-creative`                | Preset    |
| `writing-factual`                  | `$writing-factual`                 | Preset    |
| `llm_for_factual_writing`          | `$writing-factual`                 | Preset    |
| `llm_to_retrieve`                  | `$retrieval`                       | Preset    |
| `engineering-structured`           | `$engineering-structured`          | Preset    |
| `llm_to_extract_invoice`           | `$engineering-structured`          | Preset    |
| `llm_for_complex_reasoning`        | `$engineering-structured`          | Preset    |
| `llm_to_code`                      | `$engineering-code`                | Preset    |
| `llm_to_analyze_large_codebase`    | `$engineering-codebase-analysis`   | Preset    |
| `llm_for_img_to_text`              | `$vision`                          | Preset    |
| `llm_for_img_to_text_cheap`        | `$vision-cheap`                    | Preset    |
| `llm_to_extract_diagram`           | `$vision-diagram`                  | Preset    |
| `vision-diagram`                   | `$vision-diagram`                  | Preset    |
| `llm_for_testing_gen_text`         | `$testing-text`                    | Preset    |
| `llm_for_testing_gen_object`       | `$testing-object`                  | Preset    |
| `vision-cheap`                     | `$vision-cheap`                    | Preset    |
| `extract-all-from-document`        | `$extract-all-from-document`       | Preset    |
| `extract-text-from-pdf`            | `$extract-text-from-pdf`           | Preset    |
| `gen_image_basic`                  | `$gen-image`                       | Preset    |
| `gen_image_fast`                   | `$gen-image-fast`                  | Preset    |
| `gen_image_high_quality`           | `$gen-image-high-quality`          | Preset    |
| `gen-image-testing`                | `$gen-image-testing`               | Preset    |

## Error Messages

If you see an error like:
```
Model handle 'llm_for_creativity' was not found in the model deck
Available handle: gpt-4o-mini, claude-3-haiku, ...
```

This means you're using a bare string that's being interpreted as a direct model handle. Check if it's actually a preset, waterfall, or alias and add the appropriate prefix.

## Benefits of This Change

1. **Explicit intent**: No more ambiguity about what type of reference you're using
2. **Better error messages**: The system knows exactly what you intended and can provide relevant available options
3. **Easier debugging**: You can immediately tell what type of reference is being used just by looking at the config
4. **Future-proof**: Adding new reference types won't cause conflicts with existing names
