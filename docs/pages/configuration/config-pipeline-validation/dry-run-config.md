# Dry Run Configuration

The `DryRunConfig` class controls how Pipelex behaves during dry runs.

## Configuration Options

```python
class DryRunConfig(ConfigModel):
    apply_to_jinja2_rendering: bool
    text_gen_truncate_length: int
    nb_list_items: int
    nb_extract_pages: int
    image_urls: List[str]
    allowed_to_fail_pipes: List[str] = Field(default_factory=list)
```

### Fields

- `apply_to_jinja2_rendering`: When true, simulates Jinja2 template rendering during dry runs
- `text_gen_truncate_length`: Maximum length of generated text during dry runs
- `nb_list_items`: Number of items to generate for list content during dry runs
- `nb_extract_pages`: Number of pages to simulate for OCR operations during dry runs
- `image_urls`: List of image URLs to use for dry run testing (must be non-empty)
- `allowed_to_fail_pipes`: List of pipe names that are allowed to fail during dry runs (optional)

## Example Configuration

```toml
[pipelex.dry_run_config]
apply_to_jinja2_rendering = true
text_gen_truncate_length = 100
nb_list_items = 3
nb_extract_pages = 2
image_urls = ["https://example.com/image1.jpg", "https://example.com/image2.jpg"]
allowed_to_fail_pipes = ["optional_pipe", "experimental_pipe"]
```

## Dry Run Behavior

### Template Rendering

When `apply_to_jinja2_rendering` is true:

- Templates are processed but not actually rendered
- Variables are validated
- Template syntax is checked
- No actual content is generated

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
- Enable template validation when testing templates
- Review dry run logs for potential issues
