---
description: "Define typed concepts in .mthds files to give your AI methods clear data boundaries, validation rules, and structured outputs."
---

# Defining Your Concepts

!!! tip "MTHDS Standard Reference"
    Concepts are part of the MTHDS open standard. For the authoritative language specification, see [Concepts](https://mthds.ai/latest/language/concepts/) on mthds.ai. This page documents Pipelex-specific behavior and usage.

Concepts are the foundation of reliable AI methods. They define what flows through your pipes—not just as data types, but as meaningful pieces of knowledge with clear boundaries and validation rules.

## Writing Concept Definitions

Every concept starts with a natural language definition. This definition serves two audiences: developers who build with your pipeline, and the LLMs that process your knowledge.

### Basic Concept Definition

The simplest way to define a concept is with a descriptive sentence:

```toml
[concept]
Invoice = "A commercial document issued by a seller to a buyer"
Employee = "A person employed by an organization"
ProductReview = "A customer's evaluation of a product or service"
```

!!! important "Concept Naming Convention"
    Concept names **MUST** be in `PascalCase` (also known as UpperCamelCase). Each word starts with a capital letter, with no underscores or hyphens.
    
    **Valid concept names:**
    ```toml
    ✅ Invoice
    ✅ ProductReview
    ✅ CustomerFeedback
    ✅ InvoiceLineItem
    ```
    
    **Invalid concept names:**
    ```toml
    ❌ invoice           # Not PascalCase
    ❌ product_review    # snake_case not allowed
    ❌ Product-Review    # Hyphens not allowed
    ❌ productReview     # camelCase not allowed (must start with capital)
    ```

Those concepts will be Text-based by default. If you want to use structured output, declare the structure directly in the concept definition (recommended) or create a Python class for advanced use cases.

**Key principles for concept definitions:**

1. **Define what it is, not what it's for**
   ```toml
   # ❌ Wrong: includes usage context
   TextToSummarize = "Text that needs to be summarized"
   
   # ✅ Right: defines the essence
   Article = "A written composition on a specific topic"
   ```

2. **Use singular forms**
   ```toml
   # ❌ Wrong: plural form
   Invoices = "Commercial documents from sellers"
   
   # ✅ Right: singular form
   Invoice = "A commercial document issued by a seller to a buyer"
   ```

3. **Avoid unnecessary adjectives**
   ```toml
   # ❌ Wrong: includes subjective qualifier
   LongArticle = "A lengthy written composition"
   
   # ✅ Right: neutral description
   Article = "A written composition on a specific topic"
   ```

### Organizing Related Concepts

Group concepts that naturally belong together in the same domain. A domain acts as a namespace for a set of related concepts and pipes, helping you organize and reuse your pipeline components. You can learn more about them in [Understanding Domains](../domain.md).

```toml
# finance.mthds
domain = "finance"
description = "Financial document processing"

[concept]
Invoice = "A commercial document issued by a seller to a buyer"
Receipt = "Proof of payment for goods or services"
PurchaseOrder = "A buyer's formal request to purchase goods or services"
PaymentTerms = "Conditions under which payment is to be made"
LineItem = "An individual item or service listed in a financial document"
```

## Get Started with Inline Structures

To add structure to your concepts, the **recommended approach** is using **inline structures** directly in your `.mthds` files. Inline structures support all field types including nested concepts:

```toml
[concept.Customer]
description = "A customer for an invoice"

[concept.Customer.structure]
name = { type = "text", description = "Customer's full name", required = true }
email = { type = "text", description = "Customer's email address", required = true }

[concept.Invoice]
description = "A commercial document issued by a seller to a buyer"

[concept.Invoice.structure]
invoice_number = "The unique invoice identifier"
issue_date = { type = "date", description = "The date the invoice was issued" }
customer = { type = "concept", concept_ref = "finance.Customer", description = "The customer" }
total_amount = { type = "number", description = "The total invoice amount" }
```

This automatically generates fully-typed Pydantic models with validation—no Python code needed!

**For complete details on inline structures, nested concepts, and all features, see [Inline Structures](inline-structures.md).**

### Generating Python Classes

If you need type hints and IDE autocomplete, use the `pipelex build structures` command to generate Python classes from your inline definitions:

```bash
pipelex build structures ./my_pipelines/
```

### Alternative: Hand-Written Python Classes

For advanced features like custom validation, computed properties, or reusable business logic, you can create explicit Python classes.

**Learn more in [Python StructuredContent Classes](python-classes.md).**

## Refining Concepts

You can create more specific versions of existing concepts through refinement. For example, an `Invoice` is a specific kind of `Document`:

```toml
[concept.Invoice]
description = "A commercial document issued by a seller to a buyer"
refines = "Document"
```

The refined concept inherits the structure of the base concept while adding semantic specificity.

**For complete details on refinement, see [Refining Concepts](refining-concepts.md).**

## Native Concepts

Pipelex includes 12 built-in native concepts: `Text`, `Image`, `Document`, `Html`, `TextAndImages`, `Number`, `ImgGenPrompt`, `Page`, `Dynamic`, `JSON`, `SearchResult`, and `Anything`.

These concepts are automatically available in all pipelines—no setup required. You can use them directly in your pipes or refine them to create more specific concepts.

**For complete details on all native concepts and their structures, see [Native Concepts](native-concepts.md).**
