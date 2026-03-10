# Refining Concepts

Concept refinement allows you to create more specific versions of existing concepts while inheriting their structure. This provides semantic clarity and type safety for domain-specific methods.

## What is Concept Refinement?

Refinement is the process of creating a specialized concept from a more general one. When you refine a concept, the new concept:

- **Inherits the structure** of the base concept
- **Adds semantic specificity** to clarify its purpose

Think of it as creating a subtype: an `Invoice` is a specific kind of `Document`, and a `Photo` is a specific kind of `Image`.

## Why Refine Concepts?

### 1. Semantic Clarity

Refined concepts make your pipeline's intent explicit:

```toml
# ❌ Less clear
[pipe.process_invoice]
inputs = { invoice = "PDF" }

# ✅ More clear
[pipe.process_invoice]
inputs = { invoice = "Invoice" }
```

### 2. Self-Documenting Code

```toml
[pipe.extract_contract_terms]
type = "PipeLLM"
description = "Extract key terms from a contract"
inputs = { contract = "Contract" }  # Clear what type of document is expected
output = "ContractTerms"
```

### 3. Domain-Specific Methods

Build pipelines tailored to specific use cases:

```toml
domain = "finance"

[concept.Invoice]
description = "A commercial invoice"
refines = "Document"

[concept.Receipt]
description = "Proof of payment"
refines = "Document"

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

```toml
[pipe.analyze_invoice]
inputs = { invoice = "Invoice" }  # Only accepts Invoice
output = "Analysis"
```

## Current Limitations

!!! warning "No structure on refined concepts (For Now)"
    When you refine a concept, you **cannot** add an inline structure or specify a `structure_class_name`. This limitation will be lifted in future releases.
    
    **Not allowed:**
```toml
[concept.Invoice]
description = "A commercial invoice"
refines = "Document"
structure_class_name = "InvoiceModel"  # ❌ Not allowed

[concept.Invoice.structure]  # ❌ Not allowed
invoice_number = "Invoice ID"
```

**Allowed:**
```toml
[concept.Invoice]
description = "A commercial invoice"
refines = "Document"  # ✅ Inherits DocumentContent structure
```

## Basic Refinement Syntax

Define a refined concept using the `refines` field:

```toml
[concept.ConceptName]
description = "Description of the refined concept"
refines = "BaseConceptName"
```

For concepts in a different domain, use the fully qualified reference:

```toml
[concept.SpecializedConcept]
description = "A more specialized version of an existing concept"
refines = "otherdomain.BaseConceptName"
```

### Refining Document

```toml
[concept.Invoice]
description = "A commercial document issued by a seller to a buyer"
refines = "Document"

[concept.Contract]
description = "A legally binding agreement between parties"
refines = "Document"
```

Both concepts inherit the `DocumentContent` structure (with a `url` field) but represent semantically distinct document types.

### Refining Image

```toml
[concept.ProductPhoto]
description = "A photograph of a product for marketing purposes"
refines = "Image"

[concept.Screenshot]
description = "A screen capture image"
refines = "Image"
```

Each inherits `ImageContent` structure (url, caption, base_64, etc.) with specific semantic meaning.

### Refining Text

```toml
[concept.Article]
description = "A written composition on a specific topic"
refines = "Text"

[concept.Summary]
description = "A condensed version of a longer text"
refines = "Text"
```

### Building Concept Hierarchies

You can build hierarchies by refining concepts that have their own structures. The refined concept inherits the structure from the base concept:

```toml
domain = "crm"

# Base concept with structure
[concept.Customer]
description = "A customer in our system"

[concept.Customer.structure]
name = { type = "text", required = true, description = "Customer name" }
email = { type = "text", required = true, description = "Customer email" }

# Refined concept - inherits Customer's structure
[concept.VIPCustomer]
description = "A VIP customer with special privileges"
refines = "Customer"

# Another refined concept from the same base
[concept.InactiveCustomer]
description = "A customer who has not been active recently"
refines = "Customer"
```

Both `VIPCustomer` and `InactiveCustomer` will have access to the `name` and `email` fields defined in `Customer`. When you create content for these concepts, it will be compatible with the base `Customer` structure.

## Cross-Package Refinement

You can refine concepts that live in a different package. This lets you specialize a shared concept from a dependency without modifying the dependency itself.

### Syntax

Use the `->` cross-package reference operator in the `refines` field:

```toml
[concept.RefinedConcept]
description = "A more specialized version of a cross-package concept"
refines = "alias->domain.BaseConceptCode"
```

| Part | Description |
|------|-------------|
| `alias` | The dependency alias declared in your `METHODS.toml` `[dependencies]` section |
| `->` | Cross-package reference operator |
| `domain` | The dot-separated domain path inside the dependency package |
| `BaseConceptCode` | The `PascalCase` concept code to refine |

### Full Example

Suppose you depend on a scoring library that defines a `WeightedScore` concept:

**Dependency package** (`scoring-lib`):

```toml title="METHODS.toml"
[package]
address = "github.com/acme/scoring-lib"
version = "2.0.0"
description = "Scoring utilities."

[exports.scoring]
pipes = ["compute_weighted_score"]
```

```toml title="scoring.mthds"
domain = "scoring"

[concept.WeightedScore]
description = "A weighted score result"

[pipe.compute_weighted_score]
type = "PipeLLM"
description = "Compute a weighted score"
output = "WeightedScore"
prompt = "Compute a weighted score for: {{ item }}"
```

**Your consumer package**:

```toml title="METHODS.toml"
[package]
address = "github.com/acme/analysis-app"
version = "1.0.0"
description = "Analysis application."

[dependencies]
scoring_lib = { address = "github.com/acme/scoring-lib", version = "^2.0.0" }

[exports.analysis]
pipes = ["compute_detailed_score"]
```

```toml title="analysis.mthds"
domain = "analysis"

[concept.DetailedScore]
description = "An extended score with additional detail"
refines = "scoring_lib->scoring.WeightedScore"

[pipe.compute_detailed_score]
type = "PipeLLM"
description = "Compute a detailed score"
output = "DetailedScore"
prompt = "Compute a detailed score for: {{ item }}"
```

`DetailedScore` inherits the structure of `WeightedScore` from the `scoring_lib` dependency's `scoring` domain.

!!! important
    The base concept must be accessible from the dependency. The dependency must export the pipes in the domain that contains the concept, or the concept's domain must be reachable via an exported pipe's bundle.

For more on how dependencies and cross-package references work, see [Packages](../packages.md#cross-package-references).

## Type Compatibility

Understanding how refined concepts interact with pipe inputs is crucial.

### How Refinement Affects Type Checking

!!! important "Key Rule"
    A pipe that accepts a **base concept** will also accept any concept that **refines** it. Refined concepts are substitutable for their parent — this is standard subtype compatibility.

```toml
[pipe.extract_text]
inputs = { document = "Document" }  # Accepts Document, Invoice, Contract, or any concept that refines Document
```

### Practical Example

```toml
[concept.Invoice]
refines = "Document"

[concept.Contract]
refines = "Document"

# This pipe accepts Document and any concept that refines it (Invoice, Contract, etc.)
[pipe.extract_from_document]
type = "PipeExtract"
inputs = { document = "Document" }
output = "Page[]"

# This pipe accepts Invoice (and any concept that refines Invoice)
[pipe.process_invoice]
type = "PipeLLM"
inputs = { invoice = "Invoice" }
output = "InvoiceData"

# This pipe accepts Contract (and any concept that refines Contract)
[pipe.process_contract]
type = "PipeLLM"
inputs = { contract = "Contract" }
output = "ContractData"
```

In this setup:

- `extract_from_document` accepts `Document`, `Invoice`, `Contract`, or any other concept that refines `Document`
- `process_invoice` accepts `Invoice` or any concept that refines `Invoice`
- `process_contract` accepts `Contract` or any concept that refines `Contract`

## Best Practices

### 1. Choose Meaningful Names

```toml
# ❌ Avoid generic or vague names
[concept.Document1]
refines = "Document"

# ✅ Use specific, descriptive names
[concept.Invoice]
refines = "Document"
```

### 2. Write Clear Descriptions

```toml
# ❌ Too vague
[concept.Invoice]
description = "A document"
refines = "Document"

# ✅ Clear and specific
[concept.Invoice]
description = "A commercial document issued by a seller to a buyer, detailing products or services provided and payment terms"
refines = "Document"
```

### 3. Don't Over-Refine

```toml
# ❌ Too specific, creates unnecessary complexity
[concept.SmallInvoice]
description = "An invoice under $100"
refines = "Document"

[concept.LargeInvoice]
description = "An invoice over $1000"
refines = "Document"

# ✅ Keep it general, handle specifics in processing logic
[concept.Invoice]
description = "A commercial invoice"
refines = "Document"
```

## When to Refine vs. When to Create New Concepts

### Refine When:

- ✅ Your concept is semantically a specific type of an existing concept
- ✅ The base concept's structure is sufficient for your needs
- ✅ You want to inherit existing validation and behavior
- ✅ You're building domain-specific methods with clear document/content types
- ✅ You need to create specialized versions of an existing concept

**Examples:**
```toml
[concept.Invoice]  # Clearly a type of Document
refines = "Document"

[concept.VIPCustomer]  # A specialized type of Customer
refines = "Customer"
```

### Create New Concept When:

- ✅ Your concept needs custom structure with multiple fields
- ✅ Your concept doesn't naturally fit any existing concept
- ✅ You need complex validation or computed properties


## Related Documentation

- [Define Your Concepts](define_your_concepts.md) - Introduction to concepts
- [Native Concepts](native-concepts.md) - Complete guide to native concepts
- [Inline Structures](inline-structures.md) - Add structure to concepts
- [Python StructuredContent Classes](python-classes.md) - Advanced customization
- [Packages](../packages.md) - Package system, dependencies, and cross-package references

