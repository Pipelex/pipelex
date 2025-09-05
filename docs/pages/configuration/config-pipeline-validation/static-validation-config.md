# Static Validation Configuration

The `StaticValidationConfig` class controls how Pipelex handles validation errors during static analysis.

## Configuration Options

```python
class StaticValidationReaction(StrEnum):
    RAISE = "raise"    # Raise an exception
    LOG = "log"        # Log the error but continue
    IGNORE = "ignore"  # Silently ignore the error

class StaticValidationConfig(ConfigModel):
    default_reaction: StaticValidationReaction
    reactions: Dict[StaticValidationErrorType, StaticValidationReaction]
```

### Fields

- `default_reaction`: Default reaction for validation errors not specifically configured
- `reactions`: Dictionary mapping specific error types to their reactions

## Error Types and Reactions

Each validation error type can be configured to have one of three reactions:

- `RAISE`: Stops execution and raises an exception
- `LOG`: Logs the error but allows execution to continue
- `IGNORE`: Silently ignores the error

## Example Configuration

```toml
[pipelex.static_validation_config]
default_reaction = "raise"

[pipelex.static_validation_config.reactions]
# Enable one of these to tolerate some static validation errors, like you would for pyright or some linters
# missing_input_variable = "log"
# extraneous_input_variable = "log"
# inadequate_input_concept = "log"
# too_many_candidate_inputs = "log"
```

## Validation Process

1. When a validation error is detected, the system looks up the error type in the `reactions` dictionary
2. If the error type is found, the corresponding reaction is used
3. If the error type is not found, the `default_reaction` is used
4. The reaction determines how the error is handled

## Best Practices

- Use `RAISE` for critical errors that should never be ignored
- Use `LOG` for warnings that should be addressed but aren't critical
- Use `IGNORE` sparingly and only for known, harmless cases
- Configure specific reactions for known error types
- Use a reasonable `default_reaction` for unexpected error types
