# Providing Inputs to Pipelines

When running Pipelex pipelines, you need to provide input data that matches what your pipeline expects. This guide explains how to prepare and format inputs, whether you're using the CLI, Python API, or Pipelex Client.

## Preparing Inputs with the CLI

The Pipelex CLI can generate a template JSON file with all the required inputs for your pipeline:

```bash
pipelex build inputs path/to/my_pipe.plx
```

This creates a `results/inputs.json` file with the structure needed for your pipeline. You can then fill in the values and use it with:

```bash
pipelex run path/to/my_pipe.plx --inputs results/inputs.json
```

See more about the options of the CLI [here](../../../home/9-tools/cli.md).

!!! tip "Starting Point for Input Structure"
    Use `pipelex build inputs` to quickly understand what inputs your pipeline expects and generate a template to fill in.

## Understanding PipelineInputs Format

The `inputs` parameter uses **PipelineInputs** format - a smart, flexible way to provide data to your pipelines. Instead of forcing you into a rigid structure, PipelineInputs intelligently interprets your data based on how you provide it.

!!! tip "Working with Lists"
    When providing multiple items as input (lists) or expecting multiple outputs, understanding multiplicity is essential. See [Understanding Multiplicity](understanding-multiplicity.md) for a comprehensive guide on how Pipelex handles single items versus collections.

### TL;DR: How Input Formatting Works

**Case 1: Direct Content** - Provide the value directly (simplest)

- 1.1: String → `"my text"`
- 1.2: List of strings → `["text1", "text2"]`
- 1.3: StructuredContent object → `MyClass(arg1="value")`
- 1.4: List of StuffContent objects → `[MyClass(...), MyClass(...)]`
- 1.5: ListContent of StuffContent objects → `ListContent(items=[MyClass(...), MyClass(...)])`

**Case 2: Explicit Format** - Use `{"concept": "...", "content": "..."}` for control

- 2.1: String with concept → `{"concept": "Text", "content": "my text"}`
- 2.2: List of strings with concept → `{"concept": "Text", "content": ["text1", "text2"]}`
- 2.3: StructuredContent object with concept → `{"concept": "Invoice", "content": InvoiceObject}`
- 2.4: List of StructuredContent objects with concept → `{"concept": "Invoice", "content": [...]}`
- 2.5: Dictionary (structured data) → `{"concept": "Invoice", "content": {"field": "value"}}`
- 2.6: List of dictionaries → `{"concept": "Invoice", "content": [{...}, {...}]}`

!!! tip "Pro Tip for Text Inputs"
    For text inputs specifically, skip the verbose format. Just provide the string directly: `"text": "Hello"` instead of `"text": {"concept": "Text", "content": "Hello"}`

---

## Case 1: Direct Content Format

When you provide content directly (without the `concept` key), Pipelex intelligently infers the type.

### 1.1: Simple String (Text)

The simplest case - just provide a string directly:

**JSON Format:**
```json
{
  "inputs": {
    "my_text": "my text"
  }
}
```

**Python Format:**
```python
inputs = {
    "my_text": "my text"
}
```

**Result:** Automatically becomes `TextContent` with concept `native.Text`

### 1.2: List of Strings (Text List)

Provide multiple text items as a list:

**JSON Format:**
```json
{
  "inputs": {
    "my_texts": ["my text1", "my text2", "my text3"]
  }
}
```

**Python Format:**
```python
inputs = {
    "my_texts": ["my text1", "my text2", "my text3"]
}
```

**Result:** Becomes a `ListContent` containing multiple `TextContent` items

**Note:** The concept must be compatible with `native.Text` or an error will be raised.

### 1.3: StructuredContent Object

Provide a structured object directly (for Python clients):

```python
from my_project.domain.domain_struct import MyConcept, MySubClass

inputs = {
    "invoice_data": MyConcept(
        arg1="arg1", 
        arg2=1, 
        arg3=MySubClass(arg4="arg4")
    )
}
```

**What is StructuredContent?**

- `StructuredContent` is the base class for user-defined data structures in Pipelex
- You create your own classes by inheriting from `StructuredContent`
- These classes are defined in your project's Python files
- Learn more: [Python StructuredContent Classes](../concepts/python-classes.md)

**Concept Resolution:**

- The system searches all available domains for a concept matching the class name
- If multiple concepts with the same name exist in different domains → **Error**: Must specify domain
- If no concept is found → **Error**

### 1.4: List of StuffContent Objects

Provide multiple content objects in a plain Python list:

```python
inputs = {
    "invoice_list": [
        MyConcept(arg1="arg1", arg2=1, arg3=MySubClass(arg4="arg4")),
        MyConcept(arg1="arg1_2", arg2=2, arg3=MySubClass(arg4="arg4_2"))
    ]
}
```

**What it accepts:**

- Lists of `StructuredContent` objects (user-defined classes)
- Lists of native content objects (`TextContent`, `ImageContent`, etc.)

**Requirements:**

- All items must be of the same type
- Concept resolution follows the same rules as 1.3
- Creates a new `ListContent` wrapper internally

### 1.5: ListContent of StuffContent Objects

Provide an existing `ListContent` wrapper object (Python clients):

```python
from pipelex.core.stuffs.list_content import ListContent

inputs = {
    "invoice_list": ListContent(items=[
        MyConcept(arg1="arg1", arg2=1, arg3=MySubClass(arg4="arg4")),
        MyConcept(arg1="arg1_2", arg2=2, arg3=MySubClass(arg4="arg4_2"))
    ])
}
```

**Key Difference from Case 1.4:**

- Case 1.4: Plain Python list `[item1, item2]` → **Creates** a new `ListContent` wrapper
- Case 1.5: Already wrapped `ListContent(items=[item1, item2])` → **Uses** the wrapper directly

**Why Case 1.5 is Separate from Case 1.3:**

- `StructuredContent` and `ListContent` are **sibling classes** (both inherit from `StuffContent`)
- Case 1.3 handles user-defined structured data classes
- Case 1.5 handles list container wrappers
- They're at the same inheritance level, not parent-child

**Requirements:**

- All items within the `ListContent` must be `StuffContent` objects
- All items must be of the same type
- The `ListContent` cannot be empty
- Concept is inferred from the first item's class name (not from "ListContent")

---

## Case 2: Explicit Format (Concept and Content)

Use the explicit format `{"concept": "...", "content": "..."}` when you need precise control over concept selection or when working with domain-specific concepts.

### 2.1: Explicit String Input

**JSON Format:**
```json
{
  "inputs": {
    "text": {
      "concept": "Text",
      "content": "my text"
    }
  }
}
```

**Python Format:**
```python
inputs = {
    "text": {
        "concept": "Text",
        "content": "my text"
    }
}
```

**Concept Options:**

- `"Text"` or `"native.Text"` for native text
- Any custom concept that is strictly compatible with `native.Text`

### 2.2: Explicit List of Strings

**JSON Format:**
```json
{
  "inputs": {
    "documents": {
      "concept": "Text",
      "content": ["text1", "text2", "text3"]
    }
  }
}
```

**Result:** `ListContent` with multiple `TextContent` items

### 2.3: Structured Object with Concept

**JSON Format:**
```json
{
  "inputs": {
    "invoice_data": {
      "concept": "Invoice",
      "content": {
        "invoice_number": "INV-001",
        "amount": 1250.00,
        "date": "2025-10-20"
      }
    }
  }
}
```

**Python Format:**
```python
inputs = {
    "invoice_data": {
        "concept": "Invoice",
        "content": {
            "invoice_number": "INV-001",
            "amount": 1250.00,
            "date": "2025-10-20"
        }
    }
}
```

**Concept Resolution with Search Domains:**

When you specify a concept name without a domain prefix:

- ✅ If the concept exists in only one domain → Automatically found
- ❌ If the concept exists in multiple domains → **Error**: "Multiple concepts found. Please specify domain as 'domain.Concept'"
- ❌ If the concept doesn't exist → **Error**: "Concept not found"

**Using Domain Prefix:**

```json
{
  "concept": "accounting.Invoice"
}
```

This explicitly tells Pipelex to use the `Invoice` concept from the `accounting` domain.

### 2.4: List of Structured Objects

**JSON Format:**
```json
{
  "inputs": {
    "invoices": {
      "concept": "Invoice",
      "content": [
        {
          "invoice_number": "INV-001",
          "amount": 1250.00
        },
        {
          "invoice_number": "INV-002",
          "amount": 890.00
        }
      ]
    }
  }
}
```

**Result:** `ListContent` with multiple structured content items

### 2.5: Dictionary Content

Provide structured data as a dictionary:

**JSON Format:**
```json
{
  "inputs": {
    "person": {
      "concept": "PersonInfo",
      "content": {
        "arg1": "something",
        "arg2": 1,
        "arg3": {
          "arg4": "something else"
        }
      }
    }
  }
}
```

The system will:

1. Find the concept structure (with domain resolution as explained above)
2. Validate the dictionary against the concept's structure
3. Create the appropriate content object

### 2.6: List of Dictionaries

**JSON Format:**
```json
{
  "inputs": {
    "people": {
      "concept": "PersonInfo",
      "content": [
        {
          "arg1": "something",
          "arg2": 1,
          "arg3": {"arg4": "something else"}
        },
        {
          "arg1": "something else",
          "arg2": 2,
          "arg3": {"arg4": "something else else"}
        }
      ]
    }
  }
}
```

### Using DictStuff Instances (Python Clients Only)

For Python clients, you can also pass `DictStuff` instances instead of plain dicts:

```python
from pipelex.client import PipelexClient
from pipelex.core.stuffs.stuff import DictStuff

client = PipelexClient(api_token="YOUR_API_KEY")

# Using DictStuff instance with dict content
response = await client.execute_pipeline(
    pipe_code="process_invoice",
    inputs={
        "invoice": DictStuff(
            concept="accounting.Invoice",
            content={
                "invoice_number": "INV-001",
                "amount": 1250.00,
                "date": "2025-10-20"
            }
        )
    }
)

# Using DictStuff instance with list of dicts
response = await client.execute_pipeline(
    pipe_code="process_invoices",
    inputs={
        "invoices": DictStuff(
            concept="accounting.Invoice",
            content=[
                {"invoice_number": "INV-001", "amount": 1250.00},
                {"invoice_number": "INV-002", "amount": 890.00}
            ]
        )
    }
)
```

---

## Search Domains Explained

When you reference a concept by name (like `"Invoice"` or `"PersonInfo"`), Pipelex needs to find it in your loaded domains.

### Automatic Search

```json
{
  "concept": "Invoice"
}
```

**What happens:**

1. Pipelex searches all available domains for a concept named `"Invoice"`
2. If found in **exactly one domain** → ✅ Uses that concept
3. If found in **multiple domains** → ❌ Error: "Ambiguous concept"
4. If **not found** → ❌ Error: "Concept not found"

### Explicit Domain Specification

To avoid ambiguity, specify the domain explicitly:

```json
{
  "concept": "accounting.Invoice"
}
```

**Format:** `"domain_name.ConceptName"`

This tells Pipelex exactly which concept to use, bypassing the search.

### Best Practices

- Use simple names (`"Invoice"`) when you have unique concept names across domains
- Use domain-prefixed names (`"accounting.Invoice"`) when:
  - You have concepts with the same name in different domains
  - You want to be explicit about which concept to use
  - You're building APIs that need to be unambiguous

---

## Common Input Patterns

### Pattern 1: Simple Text Input

```python
inputs = {
    "story": "Once upon a time...",
}
```

### Pattern 2: Native Content Types (PDF, Image)

```python
from pipelex.core.stuffs.pdf_content import PDFContent
from pipelex.core.stuffs.image_content import ImageContent

inputs = {
    "document": PDFContent(url="invoice.pdf"),
    "photo": ImageContent(url="photo.jpg"),
}
```

### Pattern 3: Custom Concepts with Explicit Format

```python
inputs = {
    "gantt_chart_image": {
        "concept": "gantt.GanttChartImage",
        "content": ImageContent(url="gantt.png"),
    }
}
```

### Pattern 4: Structured Data

```python
inputs = {
    "character": {
        "concept": "story.Character",
        "content": {
            "name": "Alice",
            "age": 30,
            "description": "A brave explorer"
        }
    }
}
```

### Pattern 5: Multiple Inputs with Mixed Formats

```python
from pipelex.core.stuffs.text_content import load_text_from_path

inputs = {
    # Simple string
    "client_instructions": "Focus on payment terms",
    
    # String loaded from file
    "contract_text": load_text_from_path("contract.txt"),
    
    # Explicit concept format
    "question": {
        "concept": "legal.Question",
        "content": "What are the fees?",
    },
}
```

---

## Complete Examples

### Example 1: Using JSON Inputs (CLI)

```json
{
  "inputs": {
    "text": "Analyze this contract for risks.",
    "category": {
      "concept": "Category",
      "content": {
        "name": "legal",
        "priority": "high"
      }
    },
    "options": ["option1", "option2", "option3"],
    "invoice": {
      "concept": "accounting.Invoice",
      "content": {
        "invoice_number": "INV-001",
        "amount": 1250.00
      }
    }
  }
}
```

### Example 2: Using Python Inputs

```python
from pipelex.core.stuffs.image_content import ImageContent

inputs = {
    # Direct string (Case 1.1)
    "topic": "A robot learning to love",
    
    # Native content type (Case 1.3)
    "photo": ImageContent(url="photo.jpg"),
    
    # Explicit format with custom concept (Case 2.3)
    "draft_tweet": {
        "concept": "social.DraftTweet",
        "content": "Check out this amazing framework!",
    },
    
    # List of strings (Case 1.2)
    "keywords": ["AI", "automation", "future"],
}
```

---

## Troubleshooting

### Error: "Concept not found"

If you see an error about a concept not being found, use the explicit format:

```python
# ❌ Won't work if MyType is a custom concept
inputs = {"data": my_value}

# ✅ Use explicit format
inputs = {
    "data": {
        "concept": "domain.MyType",
        "content": my_value,
    }
}
```

### Error: "Type mismatch"

Make sure the content type matches what your concept expects:

```python
# ❌ Wrong: passing a string when concept expects structured data
inputs = {
    "character": {
        "concept": "story.Character",
        "content": "Alice",  # Should be a Character instance or dict
    }
}

# ✅ Correct: pass the right type
inputs = {
    "character": {
        "concept": "story.Character",
        "content": {"name": "Alice", "age": 30, "description": "..."},
    }
}
```

### Error: "Ambiguous concept"

When a concept name exists in multiple domains, specify the domain:

```python
# ❌ Ambiguous if "Invoice" exists in multiple domains
inputs = {
    "invoice": {
        "concept": "Invoice",
        "content": {...}
    }
}

# ✅ Specify the domain
inputs = {
    "invoice": {
        "concept": "accounting.Invoice",
        "content": {...}
    }
}
```

---

## Related Documentation

- [Executing Pipelines](./executing-pipelines.md) - Learn how to run pipelines with these inputs
- [Define Your Concepts](../concepts/define_your_concepts.md) - Understand concepts and their role
- [Understanding Multiplicity](understanding-multiplicity.md) - Working with single items vs. lists
- [Inline Structures](../concepts/inline-structures.md) - Create structured data types with inline syntax
- [Python StructuredContent Classes](../concepts/python-classes.md) - Advanced structured data with Python
