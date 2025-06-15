# Dry Run Configuration

The `DryRunConfig` class controls how Pipelex behaves during dry runs.

## Configuration Options

```python
class DryRunConfig(ConfigModel):
    apply_to_jinja2_rendering: bool
    text_gen_truncate_length: int
```

### Fields

- `apply_to_jinja2_rendering`: When true, simulates Jinja2 template rendering during dry runs
- `text_gen_truncate_length`: Maximum length of generated text during dry runs

## Example Configuration

```toml
[pipelex.dry_run_config]
apply_to_jinja2_rendering = true
text_gen_truncate_length = 100
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
