# Structure Configuration

The `StructureConfig` class controls how Pipelex handles structural processing of content.

## Configuration Options

```python
class StructureConfig(ConfigModel):
    is_default_text_then_structure: bool
```

### Fields

- `is_default_text_then_structure`: When true, processes text content before applying structural transformations

## Example Configuration

```toml
[pipelex.structure_config]
is_default_text_then_structure = true
```

## Processing Flow

The `is_default_text_then_structure` flag determines the order of processing:

1. When `true`:
   - Text content is processed first
   - Structural transformations are applied to the processed text
   - This is useful when text needs to be cleaned or normalized before structuring

2. When `false`:
   - Structural transformations are applied first
   - Text processing happens after structuring
   - This is useful when the structure needs to be preserved during text processing

## Use Cases

### Text Then Structure (`true`)
- Text cleaning and normalization
- Content extraction and preprocessing
- Format standardization before structuring

### Structure Then Text (`false`)
- Preserving document structure
- Template-based processing
- Format-specific transformations

## Related Topics

- [Content Processing](../Processing/content-processing.md)
- [Text Processing](../Processing/text-processing.md)
- [Structure Processing](../Processing/structure-processing.md) 