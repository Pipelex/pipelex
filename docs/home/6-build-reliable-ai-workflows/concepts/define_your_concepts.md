# Defining Your Concepts

Concepts are the foundation of reliable AI workflows. They define what flows through your pipes—not just as data types, but as meaningful pieces of knowledge with clear boundaries and validation rules.

## Writing Concept Definitions

Every concept starts with a natural language definition. This definition serves two audiences: developers who build with your pipeline, and the LLMs that process your knowledge.

### Basic Concept Definition

The simplest way to define a concept is with a descriptive sentence:

```plx
[concept]
Invoice = "A commercial document issued by a seller to a buyer"
Employee = "A person employed by an organization"
ProductReview = "A customer's evaluation of a product or service"
```

Those concepts will be Text-based by default. If you want to use sutrctured output, you need to create a Python class for the concept, or declare the structure directly in the concept definition. 

**Key principles for concept definitions:**

1. **Define what it is, not what it's for**
   ```plx
   # ❌ Wrong: includes usage context
   TextToSummarize = "Text that needs to be summarized"
   
   # ✅ Right: defines the essence
   Article = "A written composition on a specific topic"
   ```

2. **Use singular forms**
   ```plx
   # ❌ Wrong: plural form
   Invoices = "Commercial documents from sellers"
   
   # ✅ Right: singular form
   Invoice = "A commercial document issued by a seller to a buyer"
   ```

3. **Avoid unnecessary adjectives**
   ```plx
   # ❌ Wrong: includes subjective qualifier
   LongArticle = "A lengthy written composition"
   
   # ✅ Right: neutral description
   Article = "A written composition on a specific topic"
   ```

### Organizing Related Concepts

Group concepts that naturally belong together in the same domain. A domain acts as a namespace for a set of related concepts and pipes, helping you organize and reuse your pipeline components. You can learn more about them in [Kick off a Pipelex Workflow Project](../kick-off-a-pipelex-workflow-project.md#what-are-domains).

```plx
# finance.plx
domain = "finance"
description = "Financial document processing"

[concept]
Invoice = "A commercial document issued by a seller to a buyer"
Receipt = "Proof of payment for goods or services"
PurchaseOrder = "A buyer's formal request to purchase goods or services"
PaymentTerms = "Conditions under which payment is to be made"
LineItem = "An individual item or service listed in a financial document"
```

## How to Structure Your Concepts

Once you've defined your concepts semantically, you may need to add structure if they have specific fields. Pipelex offers two approaches for adding structure:

| Approach | Best For | Advantages | Limitations |
|----------|----------|------------|-------------|
| **Inline Structure** | Most use cases, prototyping | Fast, single-file, no boilerplate | No custom validation or methods |
| **Python Class** | Complex validation, computed properties | Full Pydantic power, IDE support | More files, more code |

### Inline Structures

Define structured concepts directly in your `.plx` files. This is the **recommended approach** for most use cases:

```plx
[concept.Invoice]
description = "A commercial document issued by a seller to a buyer"

[concept.Invoice.structure]
invoice_number = "The unique invoice identifier"
total_amount = { type = "number", description = "Total invoice amount" }
```

Behind the scenes, Pipelex generates a complete Pydantic model with validation. Learn more in [Inline Structures](inline-structures.md).

### Python StructuredContent Classes

Create explicit Python classes when you need custom validation, computed properties, or advanced features:

```python
from pipelex.core.stuffs.structured_content import StructuredContent
from pydantic import Field

class Invoice(StructuredContent):
    invoice_number: str
    total_amount: float = Field(ge=0, description="Total invoice amount")
```

Python classes are automatically discovered and registered. Learn more in [Python StructuredContent Classes](python-classes.md).

### Choosing an Approach

- **Start with inline structures** for rapid prototyping and simple data models
- **Upgrade to Python classes** when you need custom validation, computed properties, or reusable business logic
- Both approaches provide full type safety and validation

For detailed guidance on implementation, field types, validation, and migration between approaches, see:
- [Inline Structures](inline-structures.md) - Complete guide to inline structure syntax
- [Python StructuredContent Classes](python-classes.md) - Advanced features with Python

## Concept Refinement

Sometimes you need to create more specific versions of existing concepts. For example, an `Invoice` is a specific kind of `PDF`, and a `ProductPhoto` is a specific kind of `Image`. Pipelex lets you express these relationships through refinement.

### Quick Example

```plx
[concept.Invoice]
description = "A commercial document issued by a seller to a buyer"
refines = "PDF"

[concept.ProductPhoto]
description = "A photograph of a product for marketing purposes"
refines = "Image"
```

Refined concepts inherit the structure of their base concept while adding semantic specificity.

!!! warning "Current Limitation"
    You can **only refine native concepts** (Text, Image, PDF, TextAndImages, Number, Page, Dynamic) for now. Support for refining custom concepts will be added in future releases.

**For complete details on refinement, including syntax, type compatibility, best practices, and limitations, see [Refining Concepts](refining-concepts.md).**

## Native Concepts

Pipelex includes several built-in native concepts that cover common data types in AI workflows: `Text`, `Image`, `PDF`, `TextAndImages`, `Number`, `Page`, `Dynamic`, `LlmPrompt`, and `Anything`.

These concepts come with predefined structures and are automatically available in all pipelines—no setup required. You can use them directly or refine them to create more specific concepts.

### Quick Example

```plx
[pipe.analyze_document]
type = "PipeLLM"
description = "Analyze a PDF document"
inputs = { document = "PDF" }
output = "Text"
prompt = "Analyze this document and provide a summary"
```

### Refining Native Concepts

Create more specific concepts by refining native ones:

```plx
[concept.Invoice]
description = "A commercial document issued by a seller to a buyer"
refines = "PDF"

[concept.ProductPhoto]
description = "A photograph of a product for marketing purposes"
refines = "Image"
```

Your refined concept inherits the structure of the native concept while adding semantic specificity.

**For complete details on all native concepts, their structures, and advanced usage, see [Native Concepts](native-concepts.md).**

## Summary

With well-defined concepts—both in natural language and with appropriate structure—your pipelines gain clarity, reliability, and maintainability. Understanding concepts is foundational to building effective AI workflows.