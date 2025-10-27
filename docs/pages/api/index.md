# Pipelex API Guide

This guide covers everything you need to know about using the Pipelex API to execute pipelines with flexible input formats.

## Table of Contents

1. [Quick Reference](#quick-reference)
2. [Execute Pipeline](#execute-pipeline)
3. [Input Format: PipelineInputs](#input-format-pipelineinputs)
   - [Case 1: Direct Content Format](#case-1-direct-content-format)
   - [Case 2: Explicit Format (Concept and Content)](#case-2-explicit-format-concept-and-content)
4. [Search Domains Explained](#search-domains-explained)
5. [PLX Content: Execute Pipelines Inline](#plx-content-execute-pipelines-inline)
6. [Error Handling](#error-handling)
7. [Best Practices](#best-practices)
8. [Client Libraries](#client-libraries)

---

## Base URL

```
https://api.pipelex.ai/api/v1
```

## Authentication

Include your API key in the Authorization header:

```
Authorization: Bearer YOUR_API_KEY
```

---

## Quick Reference

### Input Formats at a Glance

```json
// 1. Simple text (Case 1.1)
{ "text": "Hello, world!" }

// 2. List of text (Case 1.2)
{ "documents": ["text1", "text2", "text3"] }

// 3. Explicit format (Case 2.1)
{ "text": { "concept": "Text", "content": "Hello!" } }

// 4. Structured data (Case 2.5)
{ "invoice": { "concept": "Invoice", "content": { "number": "001", "amount": 100 } } }

// 5. Domain-prefixed concept (Case 2.5)
{ "data": { "concept": "accounting.Invoice", "content": { ... } } }

// 6. DictStuff instance (Python clients only)
DictStuff(concept="Invoice", content={...})
```

### Key Points

✅ **DO:** Use direct strings for text: `{"text": "Hello"}`  
❌ **DON'T:** Over-complicate text: `{"text": {"concept": "Text", "content": "Hello"}}`

✅ **DO:** Specify domain when ambiguous: `"accounting.Invoice"`  
❌ **DON'T:** Use generic names when you have duplicates: `"Invoice"`

✅ **DO:** Use `plx_content` for dynamic pipelines  
❌ **DON'T:** Use both `pipe_code` and `plx_content` together

---

## Execute Pipeline

Execute a Pipelex pipeline with flexible inputs.

**Endpoint:** `POST /pipeline/{pipe_code}/execute`

**Path Parameters:**

- `pipe_code` (string, required): The code identifying the pipeline to execute

**Request Body:**

```json
{
  "inputs": {
    "input_name": "simple text or object"
  },
  "output_name": null,
  "output_multiplicity": null,
  "dynamic_output_concept_code": null,
  "plx_content": null
}
```

**Request Fields:**

- `inputs` (PipelineInputs): Flexible input format - see [Input Format: PipelineInputs](#input-format-pipelineinputs) below
- `output_name` (string, optional): Name for the output slot
- `output_multiplicity` (string, optional): Output multiplicity setting
- `dynamic_output_concept_code` (string, optional): Override output concept
- `plx_content` (string, optional): Inline pipeline definition - see [PLX Content](#plx-content-execute-pipelines-inline)

**Response:**

```json
{
  "status": "success",
  "message": null,
  "error": null,
  "pipeline_run_id": "abc123...",
  "created_at": "2025-10-20T12:00:00Z",
  "pipeline_state": "COMPLETED",
  "finished_at": "2025-10-20T12:00:05Z",
  "pipe_output": {
    "working_memory": {
      "root": { ... },
      "aliases": { ... }
    },
    "pipeline_run_id": "abc123..."
  },
  "main_stuff_name": "result"
}
```

---

## Input Format: PipelineInputs

Run your pipeline with flexible inputs that adapt to your needs. Pipelex supports multiple formats for providing inputs, making it easy to work with simple text, structured data, or complex objects. 

### What is PipelineInputs?

The `inputs` field uses **PipelineInputs** format - a smart, flexible way to provide data to your pipelines. Instead of forcing you into a rigid structure, PipelineInputs intelligently interprets your data based on how you provide it.

### How Input Formatting Works

**Case 1: Direct Content** - Provide the value directly (simplest)

- 1.1: String → `"my text"`
- 1.2: List of strings → `["text1", "text2"]`
- 1.3: StructuredContent object → `MyClass(arg1="value")`
- 1.4: List of StuffContent objects → `[MyClass(...), MyClass(...)]`
- 1.5: ListContent of StuffContent objects → `ListContent(items=[MyClass(...), MyClass(...)])`

**Note:** Cases 1.3 and 1.5 are at the same level - both handle content types that inherit from `StuffContent`, but for different purposes (custom classes vs. list wrappers).

**Case 2: Explicit Format** - Use `{"concept": "...", "content": "..."}` for control (plain dict or DictStuff instance)

- 2.1: String with concept → `{"concept": "Text", "content": "my text"}`
- 2.2: List of strings with concept → `{"concept": "Text", "content": ["text1", "text2"]}`
- 2.3: StructuredContent object with concept → `{"concept": "Invoice", "content": InvoiceObject}`
- 2.4: List of StructuredContent objects with concept → `{"concept": "Invoice", "content": [...]}`
- 2.5: Dictionary (structured data) → `{"concept": "Invoice", "content": {"field": "value"}}`
- 2.6: List of dictionaries → `{"concept": "Invoice", "content": [{...}, {...}]}`

**Pro Tip:** For **text inputs specifically**, skip the verbose format. Just provide the string directly: `"text": "Hello"` instead of `"text": {"concept": "Text", "content": "Hello"}`

---

## Case 1: Direct Content Format

When you provide content directly (without the `concept` key), Pipelex intelligently infers the type.

### 1.1: Simple String (Text)

The simplest case - just provide a string directly:

```json
{
  "inputs": {
    "my_text": "my text"
  }
}
```

**Result:** Automatically becomes `TextContent` with concept `native.Text`

### 1.2: List of Strings (Text List)

Provide multiple text items as a list:

```json
{
  "inputs": {
    "my_texts": ["my text1", "my text2", "my text3"]
  }
}
```

**Result:** Becomes a `ListContent` containing multiple `TextContent` items

**Note:** The concept must be compatible with `native.Text` or an error will be raised.

### 1.3: StructuredContent Object

Provide a structured object directly (for Python clients):

```python
# Python client example
from my_project.domain.domain_struct import MyConcept, MySubClass

inputs = {
    "invoice_data": MyConcept(arg1="arg1", arg2=1, arg3=MySubClass(arg4="arg4"))
}
```

**What is StructuredContent?**

- `StructuredContent` is the base class for user-defined data structures in Pipelex
- You create your own classes by inheriting from `StructuredContent`
- These classes are defined in your project's Python files
- Learn more: [Python StructuredContent Classes](../build-reliable-ai-workflows-with-pipelex/define_your_concepts.md#3-python-structuredcontent-classes)

**Concept Resolution:**

- The system searches all available domains for a concept matching the class name
- If multiple concepts with the same name exist in different domains → **Error**: Must specify domain
- If no concept is found → **Error**

### 1.4: List of StuffContent Objects

Provide multiple content objects in a plain Python list:

```python
# Python client example
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
# Python client example
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

- All items within the `ListContent` must be `StuffContent` objects (this includes both `StructuredContent` and native content like `TextContent`, `ImageContent`)
- All items must be of the same type
- The `ListContent` cannot be empty
- Concept is inferred from the first item's class name (not from "ListContent")

**Use Case:** This format is useful when you already have data wrapped in a `ListContent` object from a previous pipeline execution or when working with Pipelex's internal data structures.

---

## Case 2: Explicit Format (Concept and Content)

Use the explicit format `{"concept": "...", "content": "..."}` when you need precise control over concept selection or when working with domain-specific concepts.

### 2.1: Explicit String Input

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

**Concept Options:**

- `"Text"` or `"native.Text"` for native text
- Any custom concept that is strictly compatible with `native.Text`

### 2.2: Explicit List of Strings

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

For Python clients, you can also pass `DictStuff` instances instead of plain dicts. `DictStuff` is a Pydantic model with the same structure as the explicit format.

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

# Using DictStuff instance with list of dicts content
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

# Using DictStuff instance with list of strings (for Text concept)
response = await client.execute_pipeline(
    pipe_code="analyze_texts",
    inputs={
        "documents": DictStuff(
            concept="Text",
            content=["document 1", "document 2", "document 3"]
        )
    }
)
```

**DictStuff Structure:**

- `concept` (str): The concept code (with optional domain prefix)
- `content` (dict[str, Any] | list[Any]): The actual data content

**Content Types:**

- **Dictionary**: Single structured object → Creates a single Stuff
- **List of dicts**: Multiple structured objects → Creates ListContent with validated items
- **List of strings** (for Text-compatible concepts): Creates ListContent of TextContent

**Note:** `DictStuff` instances are automatically converted to plain dicts and processed through the standard Case 2 logic.

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
3. If found in **multiple domains** → ❌ Error: "Ambiguous concept: Found 'Invoice' in domains: accounting, billing. Use 'domain.Invoice' format."
4. If **not found** → ❌ Error: "Concept 'Invoice' not found in any domain"

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

## Multiple Input Combinations

Combine different input types in a single request:

```json
{
  "inputs": {
    "text": "Analyze this contract for risks.",
    "category": {
      "concept": "Category",
      "content": {"name": "legal", "priority": "high"}
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

In this example:

- `text` uses direct string format (Case 1.1)
- `category` uses explicit format with structured content (Case 2.5)
- `options` uses direct list format (Case 1.2)
- `invoice` uses explicit format with domain prefix and structured content (Case 2.5)

---

## PLX Content: Execute Pipelines Inline

The `plx_content` field allows you to execute pipelines by providing their `.plx` definition directly in the request, without needing to reference a pre-existing `pipe_code`.

### When to Use PLX Content

Use `plx_content` when you want to:

- Execute a dynamically generated pipeline
- Test a pipeline without deploying it
- Run one-off pipelines that don't need to be stored
- Prototype new pipelines quickly

### Basic Usage

Instead of referencing a `pipe_code`, provide the complete pipeline definition:

```bash
curl -X POST https://api.pipelex.ai/api/v1/pipeline/execute \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "plx_content": "domain = \"my_domain\"\n\n[concept]\nGreeting = \"A greeting message\"\n\n[pipe.hello]\ntype = \"PipeLLM\"\ndescription = \"Generate a greeting\"\noutput = \"Greeting\"\nprompt = \"Generate a friendly greeting\"",
    "inputs": {
      "name": "Alice"
    }
  }'
```

### PLX Content Structure

The `plx_content` should contain a valid `.plx` file as a string:

```json
{
  "plx_content": "domain = \"example\"\n\n[concept]\nResult = \"A result\"\n\n[pipe.my_pipe]\ntype = \"PipeLLM\"\ndescription = \"Process input\"\ninputs = { text = \"Text\" }\noutput = \"Result\"\nprompt = \"Process this: @text\""
}
```

**Key Points:**

- The `plx_content` must be a valid Pipelex pipeline definition
- Include newlines (`\n`) to properly format the pipeline
- The pipeline will be validated before execution
- All concepts and pipes must be properly defined within the content

### Example: Dynamic Pipeline

```python
from pipelex.client import PipelexClient

client = PipelexClient(api_token="YOUR_API_KEY")

# Define a pipeline inline
plx_pipeline = """
domain = "sentiment_analysis"

[concept]
SentimentScore = "A sentiment score"

[concept.SentimentScore.structure]
score = { type = "number", description = "Sentiment score from -1 to 1", required = true }
label = { type = "text", description = "Sentiment label", required = true }

[pipe.analyze]
type = "PipeLLM"
description = "Analyze sentiment of text"
inputs = { text = "Text" }
output = "SentimentScore"
model = { model = "gpt-4o-mini", temperature = 0.3 }
prompt = \"\"\"
Analyze the sentiment of this text and provide a score from -1 (negative) to 1 (positive):

@text
\"\"\"
"""

# Execute the pipeline
response = await client.execute_pipeline(
    pipe_code="analyze",
    plx_content=plx_pipeline,
    inputs={
        "text": "This product exceeded all my expectations!"
    }
)

print(response.pipe_output)
```

### Combining PLX Content with Inputs

You can use all the PipelineInputs input formats described above with `plx_content`:

```json
{
  "plx_content": "domain = \"processing\"...",
  "inputs": {
    "text": "Simple direct input",
    "data": {
      "concept": "DataRecord",
      "content": {
        "id": 123,
        "values": [1, 2, 3]
      }
    }
  }
}
```

### Validation

When you provide `plx_content`:
1. The pipeline definition is parsed and validated
2. All concepts and structures are verified
3. The pipeline is executed if valid
4. Errors are returned if the pipeline definition is invalid

!!! important "Mutually Exclusive Parameters"
    `plx_content` and `pipe_code` are mutually exclusive. Use one or the other, not both.

---

## Error Handling

### Error Response Format

```json
{
  "status": "error",
  "message": "Pipeline execution failed",
  "error": "Invalid concept: UnknownConcept",
  "pipeline_run_id": "abc123",
  "pipeline_state": "FAILED"
}
```

### HTTP Status Codes

- `200 OK`: Pipeline executed successfully
- `400 Bad Request`: Invalid input format
- `401 Unauthorized`: Missing or invalid API key
- `404 Not Found`: Pipeline not found
- `500 Internal Server Error`: Server error

### Common Errors

**Concept Not Found**
```json
{
  "status": "error",
  "error": "Concept 'UnknownConcept' not found in the library"
}
```

**Ambiguous Concept**
```json
{
  "status": "error",
  "error": "Ambiguous concept: Found 'Invoice' in domains: accounting, billing. Use 'domain.Invoice' format."
}
```

**Invalid Input Type**
```json
{
  "status": "error",
  "error": "Trying to create a Stuff from a list of strings but the items are not of the same type"
}
```

---

## Best Practices

### Input Design

1. **Use Direct Format for Simple Inputs**
   ```json
   // ✅ Good
   { "text": "Hello" }
   
   // ❌ Unnecessary
   { "text": { "concept": "Text", "content": "Hello" } }
   ```

2. **Be Explicit with Custom Concepts**
   ```json
   // ✅ Good - clear and unambiguous
   { "invoice": { "concept": "accounting.Invoice", "content": {...} } }
   ```

3. **Validate Before Sending**

   - Ensure all required fields are present
   - Match field types to concept structure
   - Use domain prefixes when concepts might be ambiguous

### Performance Tips

1. **Batch Processing**: Use list inputs when processing multiple items
2. **Reuse Connections**: Keep the client instance for multiple requests
3. **Handle Async Properly**: Use proper async/await patterns in Python

### Security

1. **Protect API Keys**: Never commit API keys to version control
2. **Use Environment Variables**: Store credentials securely
   ```python
   import os
   api_token = os.getenv("PIPELEX_API_TOKEN")
   ```

---

## Client Libraries

### Python

#### Installation

```bash
pip install pipelex
```

#### Basic Usage (Direct Text Input)

```python
from pipelex.client import PipelexClient

client = PipelexClient(api_token="YOUR_API_KEY")

# Simple text input - no need for concept/content structure
response = await client.execute_pipeline(
    pipe_code="analyze_sentiment",
    inputs={
        "text": "This is amazing!"
    }
)

print(response.pipe_output.working_memory)
```

#### Structured Input

```python
from pipelex.client import PipelexClient

client = PipelexClient(api_token="YOUR_API_KEY")

# Explicit concept and structured content
response = await client.execute_pipeline(
    pipe_code="extract_invoice",
    inputs={
        "document": {
            "concept": "PDF",
            "content": {
                "url": "https://example.com/invoice.pdf"
            }
        }
    }
)

# Access the main output
invoice = response.pipe_output.working_memory.root["invoice"]
print(f"Invoice Number: {invoice['content']['invoice_number']}")
```

#### Multiple Inputs with Mixed Formats

```python
from pipelex.client import PipelexClient

client = PipelexClient(api_token="YOUR_API_KEY")

response = await client.execute_pipeline(
    pipe_code="contract_analysis",
    inputs={
        # Direct text input
        "contract_text": "This is the contract text...",
        
        # Structured input with explicit concept
        "analysis_config": {
            "concept": "AnalysisConfig",
            "content": {
                "priority": "high",
                "focus_areas": ["liability", "termination"]
            }
        },
        
        # Direct list input
        "reference_docs": ["doc1", "doc2", "doc3"]
    }
)

print(response.pipeline_state)
print(response.main_stuff_name)
```

#### Using StructuredContent Objects (Advanced)

```python
from pipelex.client import PipelexClient
from my_project.invoices.invoice_struct import Invoice, InvoiceLineItem

client = PipelexClient(api_token="YOUR_API_KEY")

# Create StructuredContent objects directly
invoice_data = Invoice(
    invoice_number="INV-001",
    amount=1250.00,
    line_items=[
        InvoiceLineItem(description="Service A", amount=500.00),
        InvoiceLineItem(description="Service B", amount=750.00)
    ]
)

# Pass StructuredContent object directly (Case 1.3)
response = await client.execute_pipeline(
    pipe_code="validate_invoice",
    inputs={
        "invoice": invoice_data
    }
)
```

#### Using Domain-Prefixed Concepts

```python
from pipelex.client import PipelexClient

client = PipelexClient(api_token="YOUR_API_KEY")

response = await client.execute_pipeline(
    pipe_code="multi_domain_processing",
    inputs={
        "accounting_invoice": {
            "concept": "accounting.Invoice",  # From accounting domain
            "content": {
                "invoice_number": "INV-001",
                "amount": 1250.00
            }
        },
        "billing_invoice": {
            "concept": "billing.Invoice",  # From billing domain
            "content": {
                "customer_id": "CUST-123",
                "period": "2025-10"
            }
        }
    }
)
```

---

## Support

For questions or issues:

- **Documentation**: [https://docs.pipelex.ai](https://docs.pipelex.ai)
- **Discord Community**: [https://go.pipelex.com/discord](https://go.pipelex.com/discord)
- **GitHub**: [https://github.com/pipelex/pipelex](https://github.com/pipelex/pipelex)
- **Email**: [support@pipelex.ai](mailto:support@pipelex.ai)
