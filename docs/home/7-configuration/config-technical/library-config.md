# Pipeline Discovery and Loading

Pipelex automatically discovers and loads pipeline files (`.plx`) and structure classes from your project. This page explains how the discovery system works and how to organize your pipelines effectively.

## How Pipeline Discovery Works

When you initialize Pipelex with `Pipelex.make()`, the system:

1. **Scans your project directory** for all `.plx` files
2. **Discovers Python structure classes** that inherit from `StructuredContent`
3. **Loads pipeline definitions** including domains, concepts, and pipes
4. **Registers custom functions** decorated with `@pipe_func()`

All of this happens automatically - no configuration needed.

## Excluded Directories

To improve performance and avoid loading unnecessary files, Pipelex automatically excludes common directories from discovery:

- `.venv` - Virtual environments
- `.git` - Git repository data
- `__pycache__` - Python bytecode cache
- `.pytest_cache` - Pytest cache
- `.mypy_cache` - Mypy type checker cache
- `.ruff_cache` - Ruff linter cache
- `node_modules` - Node.js dependencies
- `.env` - Environment files
- `results` - Common output directory

Files in these directories will not be scanned, even if they contain `.plx` files or structure classes.

## Project Organization

**Golden rule:** Put `.plx` files where they make sense in YOUR project. Pipelex finds them automatically.

### Common Patterns

**1. Topic-Based (Recommended for structured projects)**

Keep pipelines with related code:

```
your_project/
├── my_project/
│   ├── finance/
│   │   ├── models.py
│   │   ├── services.py
│   │   ├── invoices.plx          # With finance code
│   │   └── invoices_struct.py
│   └── legal/
│       ├── models.py
│       ├── contracts.plx         # With legal code
│       └── contracts_struct.py
├── .pipelex/
└── requirements.txt
```

**Benefits:**

- Related things stay together
- Easy to find pipeline for a specific module
- Natural code organization

**2. Centralized (For simpler discovery)**

Group all pipelines in one place:

```
your_project/
├── my_project/
│   ├── pipelines/          # All pipelines here
│   │   ├── finance.plx
│   │   ├── finance_struct.py
│   │   ├── legal.plx
│   │   └── legal_struct.py
│   └── core/
└── .pipelex/
```

**Benefits:**

- All pipelines in one location
- Simple structure for small projects

## Alternative Structures

Pipelex supports flexible organization. Here are other valid approaches:

### Feature-Based Organization

```
your_project/
├── my_project/
│   ├── features/
│   │   ├── document_processing/
│   │   │   ├── extract.plx
│   │   │   └── extract_struct.py
│   │   └── image_generation/
│   │       ├── generate.plx
│   │       └── generate_struct.py
│   └── main.py
└── .pipelex/
```

### Domain-Driven Organization

```
your_project/
├── my_project/
│   ├── finance/
│   │   ├── pipelines/
│   │   │   └── invoices.plx
│   │   └── invoice_struct.py
│   ├── legal/
│   │   ├── pipelines/
│   │   │   └── contracts.plx
│   │   └── contract_struct.py
│   └── main.py
└── .pipelex/
```

### Flat Organization (Small Projects)

```
your_project/
├── my_project/
│   ├── invoice_processing.plx
│   ├── invoice_struct.py
│   └── main.py
└── .pipelex/
```

## Loading Process

Pipelex loads your pipelines in a specific order to ensure dependencies are resolved correctly:

### 1. Domain Loading

- Loads domain definitions from all `.plx` files
- Each domain must be defined exactly once
- Supports system prompts and structure templates per domain

### 2. Concept Loading

- Loads native concepts (Text, Image, PDF, etc.)
- Loads custom concepts from `.plx` files
- Validates concept definitions and relationships
- Links concepts to Python structure classes by name

### 3. Structure Class Registration

- Discovers all classes inheriting from `StructuredContent`
- Registers them in the class registry
- Makes them available for structured output generation

### 4. Pipe Loading

- Loads pipe definitions from `.plx` files
- Validates pipe configurations
- Links pipes with their respective domains
- Resolves input/output concept references

### 5. Function Registration

- Discovers functions decorated with `@pipe_func()`
- Registers them in the function registry
- Makes them available for `PipeFunc` operators

## Custom Function Registration

For custom functions used in `PipeFunc` operators, add the `@pipe_func()` decorator:

```python
from pipelex.system.registries.func_registry import pipe_func
from pipelex.core.memory.working_memory import WorkingMemory
from pipelex.core.stuffs.text_content import TextContent

@pipe_func()
async def my_custom_function(working_memory: WorkingMemory) -> TextContent:
    """
    This function is automatically discovered and registered.
    """
    input_data = working_memory.get_stuff("input_name")
    # Process data
    return TextContent(text=f"Processed: {input_data.content.text}")

# Optional: specify a custom name
@pipe_func(name="custom_processor")
async def another_function(working_memory: WorkingMemory) -> TextContent:
    # Implementation
    pass
```

## Validation

After making changes to your pipelines, validate them:

```bash
# Validate all pipelines
pipelex validate all

# Validate a specific pipe
pipelex validate pipe YOUR_PIPE_CODE

# Show all available pipes
pipelex show pipes

# Show details of a specific pipe
pipelex show pipe YOUR_PIPE_CODE
```

## Best Practices

### 1. Organization

- Keep related concepts and pipes in the same `.plx` file
- Use meaningful domain names that reflect functionality
- Match Python file names with PLX file names (`finance.plx` → `finance.py`)
- Group complex pipelines using subdirectories

### 2. Structure Classes

- Only create Python classes when you need structured output
- Name classes to match concept names exactly
- Use `_struct.py` suffix for files containing structure classes (e.g., `finance_struct.py`)
- Inherit from `StructuredContent` or its subclasses
- Place structure class files near their corresponding `.plx` files
- **Keep modules clean**: Avoid module-level code that executes on import (Pipelex imports modules during auto-discovery)

### 3. Custom Functions

- Always use the `@pipe_func()` decorator
- Use descriptive function names
- Document function parameters and return types
- Keep functions focused and testable
- **Keep modules clean**: Avoid module-level code that executes on import (Pipelex imports modules during auto-discovery)

### 4. Validation

- Run `pipelex validate all` after making changes
- Check for domain consistency
- Verify concept relationships
- Test pipes individually before composing them

## Troubleshooting

### Pipelines Not Found

**Problem:** Pipelex doesn't find your `.plx` files.

**Solutions:**

1. Ensure files have the `.plx` extension
2. Check that files are not in excluded directories
3. Verify file permissions allow reading
4. Run `pipelex show pipes` to see what was discovered

### Structure Classes Not Registered

**Problem:** Your Python classes aren't recognized.

**Solutions:**

1. Ensure classes inherit from `StructuredContent`
2. Check class names match concept names exactly
3. Verify files are not in excluded directories
4. Make sure class definitions are valid Python

### Custom Functions Not Found

**Problem:** `PipeFunc` can't find your function.

**Solutions:**

1. Add the `@pipe_func()` decorator
2. Ensure function signature matches requirements
3. Check function is `async` and accepts `working_memory`
4. Verify function is in a discoverable location

### Validation Errors

**Problem:** `pipelex validate all` shows errors.

**Solutions:**

1. Read error messages carefully - they indicate the problem
2. Check concept references are spelled correctly
3. Verify pipe configurations match expected format
4. Ensure all required fields are present
