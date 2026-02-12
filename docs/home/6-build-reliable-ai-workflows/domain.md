# Understanding Domains

A domain in Pipelex is a **semantic namespace** that organizes related concepts and pipes. It's declared at the top of every `.mthds` file and serves as an identifier for grouping related functionality.

## What is a Domain?

A domain is defined by three properties:

- **`code`** (required) - The unique identifier for the domain (must be snake_case)
- **`description`** (optional) - A human-readable description of the domain's purpose
- **`system_prompt`** (optional) - A default system prompt for all PipeLLM operators in bundles using this domain

## Declaring a Domain

Every `.mthds` file must declare its domain at the beginning:

```toml
domain = "invoice_processing"
description = "Tools for extracting, validating, and processing invoice documents"
system_prompt = "You are an expert in financial document analysis and invoice processing."
```

!!! important "Domain Code Naming Convention"
    Domain codes **MUST** be in `snake_case` (lowercase with underscores). Use descriptive names that clearly indicate the domain's purpose.
    
    **Valid domain codes:**
    ```toml
    ✅ domain = "finance"
    ✅ domain = "invoice_processing"
    ✅ domain = "medical_records"
    ✅ domain = "customer_service"
    ```
    
    **Invalid domain codes:**
    ```toml
    ❌ domain = "Finance"           # No uppercase
    ❌ domain = "invoice-processing" # No hyphens
    ❌ domain = "INVOICE_PROCESSING" # No all caps
    ❌ domain = "invoiceProcessing"  # camelCase not allowed
    ```

## Hierarchical Domains

Domains support **dotted paths** to express a hierarchy:

```toml
domain = "legal"
domain = "legal.contracts"
domain = "legal.contracts.shareholder"
```

Each segment must be `snake_case`. The hierarchy is organizational — there is no scope inheritance between parent and child domains. `legal.contracts` and `legal` are independent namespaces; defining concepts in one does not affect the other.

**Valid hierarchical domains:**

```toml
✅ domain = "legal.contracts"
✅ domain = "legal.contracts.shareholder"
✅ domain = "finance.reporting"
```

**Invalid hierarchical domains:**

```toml
❌ domain = ".legal"              # Cannot start with a dot
❌ domain = "legal."              # Cannot end with a dot
❌ domain = "legal..contracts"    # No consecutive dots
❌ domain = "Legal.Contracts"     # Segments must be snake_case
```

Hierarchical domains are used in the `[exports]` section of `METHODS.toml` to control pipe visibility across domains. See [Packages](./packages.md) for details.

## How Domains Work

### Concept Namespacing

Every concept defined in a bundle belongs to the domain declared in that bundle. The full identifier for a concept is:

```
domain_code.ConceptName
```

**Example:**

```toml
domain = "finance"

[concept]
Invoice = "A commercial document for a sale"
Payment = "A financial transaction"
```

This creates two concepts:
- `finance.Invoice`
- `finance.Payment`

### Domain as Namespace

The domain code prevents naming conflicts. Multiple bundles can define concepts with the same name if they're in different domains:

```toml
# finance.mthds
domain = "finance"
[concept]
Report = "A financial report"
```

```toml
# marketing.mthds
domain = "marketing"
[concept]
Report = "A marketing campaign report"
```

Result: Two different concepts (`finance.Report` and `marketing.Report`) with no conflict.

### Multiple Bundles, Same Domain

Multiple `.mthds` files can declare the same domain. They all contribute to that domain's namespace:

```toml
# finance_invoices.mthds
domain = "finance"
[concept]
Invoice = "..."
```

```toml
# finance_payments.mthds
domain = "finance"
[concept]
Payment = "..."
```

Both files contribute to the `finance` domain, creating:
- `finance.Invoice`
- `finance.Payment`

## Using Domains

### In Bundle Files

**Same-domain references** (no prefix needed):

```toml
domain = "finance"

[concept]
Invoice = "A commercial document"

[pipe.process_invoice]
type = "PipeLLM"
inputs = { invoice = "Invoice" }    # Same domain, no prefix
output = "Text"
prompt = "Process this invoice: @invoice"
```

**Cross-domain references** (prefix required):

```toml
domain = "accounting"

[pipe.reconcile]
type = "PipeLLM"
inputs = { invoice = "finance.Invoice" }    # Different domain, needs prefix
output = "Report"
prompt = "Reconcile this invoice: @invoice"
```

### In Python Code

Always use the full identifier when referencing concepts in code:

```python
from pipelex.core.stuffs.stuff_factory import StuffFactory

invoice_stuff = StuffFactory.make_from_concept_ref(
    concept_ref="finance.Invoice",  # domain_code.ConceptName
    name="invoice_123",
    content=invoice_data
)
```

## System Prompt Inheritance

When you set a `system_prompt` at the domain level, it applies to all `PipeLLM` operators in bundles that declare that domain:

```toml
domain = "medical_records"
system_prompt = "You are a medical records specialist with expertise in HIPAA compliance."

[pipe.extract_diagnosis]
type = "PipeLLM"
# Automatically inherits the domain's system_prompt
inputs = { record = "MedicalRecord" }
output = "Diagnosis"
prompt = "Extract the primary diagnosis: @record"
```

Individual pipes can override the domain system prompt by defining their own `system_prompt` field.

## Related Documentation

- [Packages](./packages.md) - Controlling pipe visibility with exports
- [Pipelex Bundle Specification](./pipelex-bundle-specification.md) - How domains are declared in bundles
- [Kick off a Pipelex Method Project](./kick-off-a-methods-project.md) - Getting started
- [Define Your Concepts](./concepts/define_your_concepts.md) - Creating concepts within domains
- [Designing Pipelines](./pipes/index.md) - Building pipes within domains
