# Library Configuration

The Library Configuration manages how Pipelex organizes, loads, and handles libraries in your project. Libraries in Pipelex include pipelines, LLM integrations, LLM decks, and templates.

## Directory Structure

The library system uses two main root directories:
- Internal library root (`pipelex/libraries`): Contains the base libraries shipped with Pipelex
- Exported library root (`pipelex_libraries`): Contains your project's libraries, including copies of base libraries

### Standard Paths

```
pipelex_libraries/           # Exported library root
├── pipelines/              # Pipeline definitions
│   ├── base_library/      # Base pipelines from Pipelex
│   └── your_pipelines/    # Your custom pipelines
├── llm_integrations/      # LLM integration configurations
├── llm_deck/             # LLM model configurations
└── templates/            # Template files
```

## Library Components

### 1. Pipelines

Pipelines are defined in TOML files with the following structure:
```toml
domain = "your_domain"
definition = "Domain definition"

[concept]
concept_name = "concept definition"
another_concept = { definition = "detailed concept", attributes = {} }

[pipe]
pipe_name = { PipeClassName = "pipe definition", config = {} }
```

Key features:
- Each TOML file must specify a `domain`
- Concepts can be defined as strings or detailed dictionaries
- Pipes require a class name and definition
- Supports nested structure for organization

### 2. LLM Deck

The LLM deck configuration defines available language models and their settings:
- Located in `pipelex_libraries/llm_deck/`
- Supports multiple TOML files for organization
- Can be overridden with `overrides.toml`

### 3. Templates

Template files for various components:
- Located in `pipelex_libraries/templates/`
- Used for standardizing configurations
- Supports TOML format

## Library Loading Process

1. **Domain Loading**:
   - Loads domain definitions first
   - Each domain must be defined exactly once
   - Supports system prompts and structure templates

2. **Concept Loading**:
   - Loads native concepts first
   - Loads custom concepts from TOML files
   - Validates concept definitions and relationships

3. **Pipe Loading**:
   - Loads pipe definitions after concepts
   - Validates pipe configurations
   - Links pipes with their respective domains

## Configuration Options

### Path Configuration
All paths are configurable through class variables in `LibraryConfig`:

```python
package_name = "pipelex"
internal_library_root = "libraries"
exported_library_root = "pipelex_libraries"
exported_pipelines_path = "pipelex_libraries/pipelines"
exported_llm_integrations_path = "pipelex_libraries/llm_integrations"
exported_llm_deck_path = "pipelex_libraries/llm_deck"
exported_templates_path = "pipelex_libraries/templates"
```

### Library Initialization

Use the CLI command to initialize libraries:
```bash
pipelex init-libraries
```

This will:
1. Create the necessary directory structure
2. Copy base libraries to your project
3. Set up initial configuration files

### Library Export Options

When exporting libraries to your project:
- Use `overwrite=True` to force update existing files
- Preserve custom overrides in `llm_deck/overrides.toml`
- Maintain directory structure and initialization files

## Validation

The library manager performs several validation steps:

1. **LLM Deck Validation**:
   - Ensures LLM configurations are complete
   - Validates model settings

2. **Concept Library Validation**:
   - Checks concept relationships
   - Validates concept definitions

3. **Pipe Library Validation**:
   - Verifies pipe configurations
   - Checks domain relationships

4. **Domain Library Validation**:
   - Ensures domain completeness
   - Validates domain relationships

## Error Handling

The library system includes specific error types:
- `LibraryError`: Base error for library issues
- `LibraryParsingError`: For TOML parsing issues
- `ConceptLibraryError`: For concept-related issues
- `PipeLibraryError`: For pipe-related issues
- `LLMDeckNotFoundError`: For missing LLM configurations

## Best Practices

1. **Organization**:
   - Keep related concepts and pipes in the same TOML file
   - Use meaningful domain names
   - Structure complex libraries using subdirectories

2. **Validation**:
   - Run `pipelex validate` after making changes
   - Check for domain consistency
   - Verify concept relationships

3. **Customization**:
   - Use `overrides.toml` for local LLM settings
   - Keep custom pipelines separate from base library
   - Document domain-specific configurations

← [**Back to Configuration**](configuration.md)

→ [**Next section: Tracker Configuration**](tracker-config.md)

--- 