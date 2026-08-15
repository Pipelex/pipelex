---
description: "Configure dry-run behavior in Pipelex — set mock generation rules, truncation limits, image URLs, and allowed-to-fail pipes via TOML."
---

# Dry Run Configuration

The `DryRunConfig` class controls how Pipelex behaves during dry runs.

## Configuration Options

```python
class DryRunConfig(ConfigModel):
    text_gen_truncate_length: int
    nb_list_items: int
    nb_extract_pages: int
    image_urls: List[str]
    allowed_to_fail_pipes: List[str] = Field(default_factory=list)
```

### Fields

- `text_gen_truncate_length`: Maximum length of generated text during dry runs
- `nb_list_items`: Number of items to generate for list content during dry runs
- `nb_extract_pages`: Number of pages to simulate for OCR operations during dry runs
- `image_urls`: List of image URLs to use for dry run testing (must be non-empty)
- `allowed_to_fail_pipes`: List of pipe names that are allowed to fail during dry runs (optional)

## Example Configuration

```toml
[inference.dry_run]
text_gen_truncate_length = 100
nb_list_items = 3
nb_extract_pages = 2
image_urls = ["https://pipelex-pytest-assets.s3.eu-west-3.amazonaws.com/ai_lympics.jpg", "https://pipelex-pytest-assets.s3.eu-west-3.amazonaws.com/animal_lympics.jpg"]
allowed_to_fail_pipes = ["optional_pipe", "experimental_pipe"]
```

## Dry Run Behavior

During a dry run, no AI provider is ever called and no storage IO is performed: each inference leaf (LLM text/object generation, image generation, document extraction, web search, templating) produces a synthetic mock instead. Jinja2 templates are still parse-checked, so a broken template fails loudly even in a dry run.

### Text Generation

The `text_gen_truncate_length` controls:

- Maximum length of simulated text output
- Helps prevent excessive resource usage during testing
- Makes dry run output more manageable

## Use Cases

1. **Testing Pipeline Logic**

     - Validate pipeline structure
     - Check template syntax
     - Verify variable references

2. **Resource Estimation**

     - Estimate processing time
     - Calculate potential costs
     - Plan resource allocation

3. **Debugging**

     - Trace execution paths
     - Identify potential issues
     - Test error handling

## Best Practices

- Use dry runs for testing before production
- Set appropriate truncation lengths
- Review dry run logs for potential issues

## Related Documentation

- [Validation & Dry Run](../../features/validation-dry-run.md) - Overview of validation and dry run capabilities
- [CLI validate](../../tools/cli/validate.md) - Using the CLI to validate methods
