# Pipelex Bundle Specification

A **Pipelex bundle** is the fundamental unit of organization in Pipelex. It's a single `.plx` file that defines a cohesive set of concepts and pipes for a specific domain of work.

## What is a Pipelex Bundle?

A Pipelex bundle (`.plx` file) brings together:

- **Domain declaration** - The semantic namespace for all concepts and pipes in this bundle
- **Concepts** - The knowledge structures that flow through your pipes (optional)
- **Pipes** - The processing units that transform and manipulate your concepts (optional)

Think of a bundle as a self-contained module that solves a specific problem domain. For example, you might have:

- `invoice_processing.plx` - Bundle for invoice extraction and validation
- `marketing.plx` - Bundle for generating marketing content
- `document_analysis.plx` - Bundle for analyzing documents

## Bundle Structure

Every Pipelex bundle follows this structure:

```plx
# 1. Domain Declaration (MANDATORY)
domain = "domain_name"
description = "Description of what this domain handles"

# 2. Optional: Main Pipe Declaration
main_pipe = "pipe_code"

# 3. Concept Definitions (OPTIONAL)
[concept]
ConceptName1 = "Description"
ConceptName2 = "Description"

# 4. Pipe Definitions (OPTIONAL)
[pipe]
[pipe.pipe_code]
type = "PipeLLM"
# ... pipe configuration

[pipe.pipe_code_2]
...
```

### 1. Domain Declaration (MANDATORY)

Every bundle **must** declare a domain. Only the `domain` field is mandatory; all other fields are optional:

```plx
domain = "invoice_processing"
description = "Tools for extracting and validating invoice data"
source = "path/to/invoice_processing.plx"
system_prompt = "You are an expert in financial document processing."
main_pipe = "extract_and_validate_invoice"
```

**Bundle Header Fields:**

- **`domain`** (required) - The unique identifier for this bundle's namespace
- **`description`** (Optional) - A human-readable description of what this bundle does
- **`source`** (Optional) - The file path of the bundle (usually set automatically)
- **`system_prompt`** (Optional) - A system prompt that applies to all `PipeLLM` operators in this bundle
- **`main_pipe`** (Optional) - The default pipe to execute when no specific pipe is requested when running the bundle (covered in section 2)

**Why domains matter:**

- Domains create unique namespaces for your concepts and pipes
- They prevent naming conflicts when multiple bundles define concepts with the same name
- They enable organized, modular pipeline architecture

Learn more about domains in [Understanding Domains](./domain.md).

**About `system_prompt`:**

When you define a `system_prompt` at the bundle level, it automatically applies to every `PipeLLM` operator in the bundle. This is useful for setting domain-specific context:

```plx
domain = "medical_records"
system_prompt = "You are a medical records specialist with expertise in HIPAA compliance and clinical documentation."

[pipe.extract_diagnosis]
type = "PipeLLM"
# This pipe will automatically use the bundle's system_prompt
inputs = { record = "MedicalRecord" }
output = "Diagnosis"
prompt = "Extract the primary diagnosis from this medical record: @record"
```

Individual pipes can override the bundle's system prompt by defining their own `system_prompt` field.

**About `main_pipe`:**

You can specify a default pipe to execute when no specific pipe is requested:

```plx
domain = "invoice_processing"
main_pipe = "extract_and_validate_invoice"
```

**How `main_pipe` works:**

- When executing a bundle without specifying a `pipe_code`, Pipelex runs the `main_pipe`
- If no `main_pipe` is specified, you must explicitly provide the `pipe_code` when executing
- The `main_pipe` value must reference a pipe defined in the same bundle

See more about executing pipes in [Executing Pipelines](./pipes/executing-pipelines.md).

### 3. Concept Definitions (OPTIONAL)

Concepts define the knowledge structures in your domain. While optional, most bundles define at least a few concepts (See more about concepts in [Define Your Concepts](./concepts/define_your_concepts.md)):

```plx
[concept]
Invoice = "A commercial document issued by a seller to a buyer"
Vendor = "A company or individual that provides goods or services"
LineItem = "An individual item or service listed in an invoice"
```

**Concept Naming:**

Within a bundle, you reference concepts by their simple name (`Invoice`). However, their **full identifier** includes the domain:

```
domain_name.ConceptName
```

For example, if your domain is `invoice_processing`, the concept `Invoice` has the full identifier:

```
invoice_processing.Invoice
```

This full identifier is how other bundles reference your concepts.

### 4. Pipe Definitions (OPTIONAL)

Pipes are the processing units that transform data. Like concepts, they're optional:

```plx
[pipe.extract_invoice]
type = "PipeExtract"
description = "Extract text and images from an invoice PDF"
inputs = { document = "PDF" }
output = "Page"
```
See more about designing pipes in [Designing Pipelines](./pipes/index.md).

## Referencing Concepts: When to Use Domain Prefixes

Understanding when to use domain prefixes is crucial for writing clean, maintainable bundles.

### Same-Bundle References (No Prefix Needed)

When a pipe in a bundle references a concept **defined in the same bundle**, you don't need the domain prefix:

```plx
domain = "invoice_processing"

[concept]
Invoice = "A commercial document issued by a seller to a buyer"
ValidationResult = "Result of validating an invoice"

[pipe.validate_invoice]
type = "PipeLLM"
description = "Validate invoice data"
inputs = { invoice = "Invoice" }          # ✅ No prefix needed
output = "ValidationResult"               # ✅ No prefix needed
prompt = "Validate this invoice: @invoice"
```

This is the most common case and keeps your code clean.

### Cross-Bundle References (Prefix Required)

When a pipe references a concept **from another bundle/domain**, you must use the full domain prefix:

```plx
domain = "accounting"

[concept]
Payment = "A financial transaction recording money transfer"
ReconciliationReport = "Report of payment reconciliation"
```

```plx
[pipe.reconcile_payment]
type = "PipeLLM"
description = "Reconcile a payment with an invoice"
inputs = { 
    invoice = "invoice_processing.Invoice",      # ✅ Different domain, needs prefix
    payment = "Payment"                          # ✅ Same domain, no prefix
}
output = "ReconciliationReport"
prompt = """
Reconcile this payment with the invoice...
"""
```

## Bundles Working Together

One of Pipelex's strengths is how bundles can reference and build upon each other, creating modular, reusable pipeline architectures.

### Calling Pipes from Other Bundles

A pipe in one bundle can call a pipe from another bundle using the full pipe identifier:

```plx
domain = "accounts_payable"

[pipe.process_vendor_invoice]
type = "PipeSequence"
description = "Process a vendor invoice end-to-end"
inputs = { pdf_document = "PDF" }
output = "PaymentSchedule"
steps = [
    # Call pipe from invoice_processing domain
    { pipe = "invoice_processing.extract_invoice", result = "extracted_data" },
    
    # Call pipe from validation domain
    { pipe = "validation.validate_data", result = "validation_report" },
    
    # Call pipe from this domain (no prefix needed)
    { pipe = "schedule_payment", result = "payment_schedule" }
]

[pipe.schedule_payment]
type = "PipeLLM"
description = "Schedule payment based on invoice data"
inputs = { 
    extracted_data = "invoice_processing.Invoice",   # Concept from another domain
    validation_report = "validation.Report"           # Concept from another domain
}
output = "PaymentSchedule"
prompt = "..."
```

## Related Documentation

- [Understanding Domains](./domain.md) - Deep dive into domain organization
- [Designing Pipelines](./pipes/index.md) - Learn how to design and compose pipes
- [Define Your Concepts](./concepts/define_your_concepts.md) - Complete guide to concept definitions
- [Kick off a Pipelex Workflow Project](./kick-off-a-pipelex-workflow-project.md) - Start a new project

