# Generic Template Names Configuration

The `GenericTemplateNames` class defines names for system-wide templates used in Pipelex.

## Configuration Options

```python
class GenericTemplateNames(ConfigModel):
    structure_from_preliminary_text_user: str
    structure_from_preliminary_text_system: str
```

### Fields

- `structure_from_preliminary_text_user`: Template name for user-facing preliminary text structuring
- `structure_from_preliminary_text_system`: Template name for system-level preliminary text structuring

## Example Configuration

```toml
[pipelex.generic_template_names]
structure_from_preliminary_text_user = "structure_from_text_user.jinja2"
structure_from_preliminary_text_system = "structure_from_text_system.jinja2"
```

## Template Usage

### User Templates
- Used for transforming user input into structured format
- Typically more verbose and user-friendly
- May include additional guidance or formatting

### System Templates
- Used for internal text structuring
- More concise and performance-oriented
- Focus on efficient processing

## Best Practices

- Use descriptive template names
- Keep user and system templates separate
- Follow consistent naming conventions
- Document template purposes and usage
- Version control templates alongside code
