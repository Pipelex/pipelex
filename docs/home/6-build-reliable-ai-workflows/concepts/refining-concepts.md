# Refining Concepts

Concept refinement allows you to create more specific versions of existing concepts while inheriting their structure. This provides semantic clarity and type safety for domain-specific workflows.

## What is Concept Refinement?

Refinement is the process of creating a specialized concept from a more general one. When you refine a concept, the new concept:

- **Inherits the structure** of the base concept
- **Adds semantic specificity** to clarify its purpose

Think of it as creating a subtype: an `Invoice` is a specific kind of `PDF`, and a `Photo` is a specific kind of `Image`.

## Why Refine Concepts?

### 1. Semantic Clarity

Refined concepts make your pipeline's intent explicit:

```plx
# ❌ Less clear
[pipe.process_invoice]
inputs = { invoice = "PDF" }

# ✅ More clear
[pipe.process_invoice]
inputs = { invoice = "Invoice" }
```

### 2. Self-Documenting Code

```plx
[pipe.extract_contract_terms]
type = "PipeLLM"
description = "Extract key terms from a contract"
inputs = { contract = "Contract" }  # Clear what type of document is expected
output = "ContractTerms"
```

### 3. Domain-Specific Workflows

Build pipelines tailored to specific use cases:

```plx
domain = "finance"

[concept.Invoice]
description = "A commercial invoice"
refines = "PDF"

[concept.Receipt]
description = "Proof of payment"
refines = "PDF"

[pipe.process_invoice]
type = "PipeLLM"
inputs = { invoice = "Invoice" }
output = "InvoiceData"
# ... invoice-specific processing

[pipe.process_receipt]
type = "PipeLLM"
inputs = { receipt = "Receipt" }
output = "ReceiptData"
# ... receipt-specific processing
```

### 4. Type Validation

Using specific concept names helps catch errors early:

```plx
[pipe.analyze_invoice]
inputs = { invoice = "Invoice" }  # Only accepts Invoice
output = "Analysis"
```

## Current Limitations

!!! warning "You can only refine native concepts (For Now)"
    Currently, you can **only refine [native concepts](native-concepts.md)**. Refining custom concepts will be supported in a future release

!!! warning "No structure on refined concepts (For Now)"
    When you refine a concept, you **cannot** add an inline structure or specify a `structure_class_name`. This limitation will be lifted in future releases.
    
    **Not allowed:**
    ```plx
    [concept.Invoice]
    description = "A commercial invoice"
    refines = "PDF"
    structure_class_name = "InvoiceModel"  # ❌ Not allowed
    
    [concept.Invoice.structure]  # ❌ Not allowed
    invoice_number = "Invoice ID"
    ```
    
    **Allowed:**
    ```plx
    [concept.Invoice]
    description = "A commercial invoice"
    refines = "PDF"  # ✅ Inherits PDFContent structure
    ```

## Basic Refinement Syntax

Define a refined concept using the `refines` field:

```plx
[concept.ConceptName]
description = "Description of the refined concept"
refines = "NativeConceptName"
```

### Refining PDF

```plx
[concept.Invoice]
description = "A commercial document issued by a seller to a buyer"
refines = "PDF"

[concept.Contract]
description = "A legally binding agreement between parties"
refines = "PDF"
```

Both concepts inherit the `PDFContent` structure (with a `url` field) but represent semantically distinct document types.

### Refining Image

```plx
[concept.ProductPhoto]
description = "A photograph of a product for marketing purposes"
refines = "Image"

[concept.Screenshot]
description = "A screen capture image"
refines = "Image"
```

Each inherits `ImageContent` structure (url, caption, base_64, etc.) with specific semantic meaning.

### Refining Text

```plx
[concept.Article]
description = "A written composition on a specific topic"
refines = "Text"

[concept.Summary]
description = "A condensed version of a longer text"
refines = "Text"
```

## Type Compatibility

Understanding how refined concepts interact with pipe inputs is crucial.

### How Refinement Affects Type Checking

!!! important "Key Rule"
    A pipe that accepts a **native concept** will **NOT** accept concepts that refine it.
    
    ```plx
    [pipe.extract_text]
    inputs = { document = "PDF" }  # Only accepts PDF, not Invoice or Contract
    ```
    
    If you want a pipe to accept both a native concept and its refinements, you must explicitly define the pipe to accept the refined concepts or use a more general approach.

### Practical Example

```plx
[concept.Invoice]
refines = "PDF"

[concept.Contract]
refines = "PDF"

# This pipe only accepts generic PDFs
[pipe.extract_from_pdf]
type = "PipeExtract"
inputs = { document = "PDF" }
output = "Page"

# This pipe only accepts Invoices
[pipe.process_invoice]
type = "PipeLLM"
inputs = { invoice = "Invoice" }
output = "InvoiceData"

# This pipe only accepts Contracts
[pipe.process_contract]
type = "PipeLLM"
inputs = { contract = "Contract" }
output = "ContractData"
```

In this setup:

- `extract_from_pdf` expects exactly `PDF` (not `Invoice` or `Contract`)
- `process_invoice` expects exactly `Invoice`
- `process_contract` expects exactly `Contract`

## Best Practices

### 1. Choose Meaningful Names

```plx
# ❌ Avoid generic or vague names
[concept.Document1]
refines = "PDF"

# ✅ Use specific, descriptive names
[concept.Invoice]
refines = "PDF"
```

### 2. Write Clear Descriptions

```plx
# ❌ Too vague
[concept.Invoice]
description = "A document"
refines = "PDF"

# ✅ Clear and specific
[concept.Invoice]
description = "A commercial document issued by a seller to a buyer, detailing products or services provided and payment terms"
refines = "PDF"
```

### 3. Don't Over-Refine

```plx
# ❌ Too specific, creates unnecessary complexity
[concept.SmallInvoice]
description = "An invoice under $100"
refines = "PDF"

[concept.LargeInvoice]
description = "An invoice over $1000"
refines = "PDF"

# ✅ Keep it general, handle specifics in processing logic
[concept.Invoice]
description = "A commercial invoice"
refines = "PDF"
```

## When to Refine vs. When to Create New Concepts

### Refine When:

- ✅ Your concept is semantically a specific type of a native concept
- ✅ The native structure is sufficient for your needs
- ✅ You want to inherit existing validation and behavior
- ✅ You're building domain-specific workflows with clear document/content types

**Example:**
```plx
[concept.Invoice]  # Clearly a type of PDF
refines = "PDF"
```

### Create New Concept When:

- ✅ Your concept needs custom structure with multiple fields
- ✅ Your concept doesn't naturally fit any native concept
- ✅ You need complex validation or computed properties


## Related Documentation

- [Define Your Concepts](define_your_concepts.md) - Introduction to concepts
- [Native Concepts](native-concepts.md) - Complete guide to native concepts
- [Inline Structures](inline-structures.md) - Add structure to concepts
- [Python StructuredContent Classes](python-classes.md) - Advanced customization

