# Understanding Multiplicity

Multiplicity in Pipelex defines how many items a particular stuff can comprise in a particular context. This applies to any of the pipe input variables and also to the output of the pipe. This idea is fundamental to building flexible AI workflows that can handle both single items and collections.

This guide explains the philosophy behind multiplicity in Pipelex and how to use it effectively in your pipelines.

## The Philosophy: Why Concepts Are Always Singular

In Pipelex, concepts are always defined in the singular form. You define a `Keyword`, not `Keywords`. You define an `Invoice`, not `Invoices`. This isn't just a naming convention—it's a fundamental design principle.

### Concepts Represent Semantic Entities

A concept represents a semantic entity—a meaningful piece of knowledge with clear boundaries. When you define a concept, you're describing what something *is*, not how many of them you might have:

```plx
[concept]
Keyword = "A significant word or term extracted from text"
ProductIdea = "A concept for a new product or service"
Document = "A written or printed record containing information"
```

Each of these definitions describes a single, coherent entity. The essence of what makes something a "Keyword" doesn't change whether you have one keyword or a hundred.

### Lists Are Circumstantial, Not Essential

The number of items you're working with is a circumstantial detail of your workflow, not part of the concept's identity:

- A pipe that extracts keywords from text might find 3 keywords or 30—but each is still a `Keyword`
- A pipe that generates product ideas might produce 5 ideas or 10—but each remains a `ProductIdea`
- A pipe that processes documents might handle 1 document or a batch of 100—but each is still a `Document`

By keeping concepts singular and using multiplicity to express quantity, Pipelex maintains a clean semantic model that's both flexible and intuitive.

## Output Multiplicity

Output multiplicity controls how many items a pipe produces. You can specify this using bracket notation in the `output` field.

### The Three Output Multiplicity Modes

**1. Single output (default)**

When no brackets are used in the output, the pipe produces a single item:

```plx
[concept]
Summary = "A concise overview of content"

[pipe.summarize]
type = "PipeLLM"
description = "Create a summary of the document"
inputs = { document = "Text" }
output = "Summary"
prompt = """
Summarize this document concisely:

@document
"""
```

This is the default behavior and represents the most common case.

**2. Variable output (bracket notation `[]`)**

Use empty brackets in the output to let the LLM decide how many items to generate:

```plx
[concept]
LineItem = "A single line item from an invoice"

[concept.LineItem.structure]
description = "Description of the item or service"
quantity = { type = "number", description = "Quantity purchased" }
unit_price = { type = "number", description = "Price per unit" }
total = { type = "number", description = "Total price for this line" }

[pipe.extract_line_items]
type = "PipeLLM"
description = "Extract all line items from an invoice"
inputs = { invoice_text = "Text" }
output = "LineItem[]"
prompt = """
Extract all line items from this invoice:

@invoice_text

For each line item, extract the description, quantity, unit price, and total amount.
"""
```

The pipe will extract however many line items appear in the invoice. A simple invoice might have 2 line items, while a detailed purchase order might have 50.

**Common use cases for variable output:**

- Extract entities from text (unknown count in advance)
- Generate as many alternatives as needed
- List all items that match criteria
- Identify all occurrences of a pattern

**3. Fixed output (bracket notation `[N]`)**

Use a number in brackets to generate an exact number of items:

```plx
[concept]
Headline = "A catchy title for content"

[pipe.generate_headline_options]
type = "PipeLLM"
description = "Generate headline alternatives"
inputs = { article_text = "Text" }
output = "Headline[5]"
prompt = """
Read this article:

@article_text

Generate 5 different headline options for this article.
Make each one unique and compelling.
"""
```

The pipe will always produce exactly 5 headlines.

**Common use cases for fixed output:**

- Generate N alternative versions for A/B testing
- Create a fixed set of options for user selection
- Produce a specific number of variations for comparison
- Match external requirements (e.g., "always provide 3 recommendations")

## Input Multiplicity

Input multiplicity specifies whether a pipe expects a single item or multiple items as input. This allows you to design pipes that explicitly require lists or explicitly require single items.

### Syntax for Input Multiplicity

Input multiplicity is specified using bracket notation in the `inputs` dictionary:

```plx
# Standard syntax (single item, the default)
inputs = { document = "Text" }

# Variable list (indeterminate number of items)
inputs = { documents = "Text[]" }

# Fixed count (exactly N items)
inputs = { comparison_items = "Text[2]" }
```

### The Three Input Multiplicity Modes

**1. Single item (default)**

When you use the standard syntax, the pipe expects exactly one item. This is the default behavior:

```plx
[concept]
Report = "A detailed analytical document"

[pipe.analyze_report]
type = "PipeLLM"
description = "Analyze a single report"
inputs = { report = "Report" }
output = "Analysis"
prompt = """
Analyze this report in detail:

@report
"""
```

!!! note "Default Single Item Behavior"
    When no brackets are used, the input expects a single item. Only use brackets when you need multiple items (`[]`) or a specific count (`[N]`).

**2. Variable list (bracket notation `[]`)**

Use empty brackets `[]` to specify that the pipe expects a list with an indeterminate number of items:

```plx
[concept]
Document = "A written or printed record"
Summary = "A concise overview of multiple documents"

[pipe.summarize_all_documents]
type = "PipeLLM"
description = "Create a unified summary of multiple documents"
inputs = { documents = "Document[]" }
output = "Summary"
prompt = """
Analyze all of these documents:

@documents

Create a single unified summary that captures the key points across all documents.
"""
```

!!! info "When You Actually Need `[]` Notation"
    The `[]` notation is only required for **advanced use cases**:
    
    1. **Batching over items**: When using `batch_over` in a `PipeSequence` to process each item separately
    2. **Looping in templates**: When you need to iterate over items using Jinja2 syntax (`{% for item in items %}`) in `PipeLLM`, `PipeCompose`, or `PipeCondition` prompts
    
    For most cases where you simply pass multiple items to a pipe that processes them all together, you don't need to declare the input with `[]`. The pipe will receive the list and process it as a whole.

**3. Fixed count (bracket notation `[N]`)**

Use a number in brackets `[N]` to specify that the pipe expects exactly that many items:

```plx
[concept]
Image = "A visual image file"
Comparison = "A detailed comparison analysis"

[pipe.compare_two_images]
type = "PipeLLM"
description = "Compare exactly two images side by side"
inputs = { images = "Image[2]" }
output = "Comparison"
prompt = """
Compare these two images in detail:

@images

Describe their similarities, differences, and relative strengths.
"""
```

## Practical Use Cases

### Use Case 1: Batch Processing with Variable Input

Process an unknown number of invoices, extracting structured data from each:

```plx
[concept]
InvoiceImage = "An image of an invoice document"
InvoiceData = "Structured invoice information"

[pipe.extract_single_invoice]
type = "PipeLLM"
description = "Extract data from one invoice"
inputs = { invoice_image = "InvoiceImage" }
output = "InvoiceData"
prompt = """
Extract all fields from this invoice:

@invoice_image
"""

[pipe.process_invoice_batch]
type = "PipeSequence"
description = "Process multiple invoices"
inputs = { invoice_images = "InvoiceImage[]" }
output = "InvoiceData"
steps = [
    { pipe = "extract_single_invoice", batch_over = "invoice_images", batch_as = "invoice_image", result = "all_invoice_data" }
]
```

### Use Case 2: Generate Fixed Alternatives for Testing

Create exactly 3 subject line variations for A/B testing:

```plx
[concept]
EmailContent = "The body text of an email"
SubjectLine = "An email subject line"

[pipe.generate_subject_lines]
type = "PipeLLM"
description = "Generate 3 subject line options"
inputs = { email_body = "EmailContent" }
output = "SubjectLine"
nb_output = 3
prompt = """
Email content:
@email_body

Generate $_nb_output compelling subject lines for this email.
Each should use a different persuasion technique.
"""
```

### Use Case 3: Comparative Analysis

Compare exactly two products side by side:

```plx
[concept]
ProductDescription = "A description of a product's features"
Comparison = "A comparative analysis of products"

[pipe.compare_products]
type = "PipeLLM"
description = "Compare two products"
inputs = { products = "ProductDescription[2]" }
output = "Comparison"
prompt = """
Compare these two products:

@products

Provide a balanced comparison of features, benefits, and potential drawbacks.
"""
```

### Use Case 4: Entity Extraction with Unknown Count

Extract all company names mentioned in a document:

```plx
[concept]
Article = "A news or information article"
CompanyName = "The name of a company or organization"

[pipe.extract_companies]
type = "PipeLLM"
description = "Extract all company names from an article"
inputs = { article = "Article" }
output = "CompanyName[]"
prompt = """
Read this article:

@article

Extract all company and organization names mentioned in the article.
Only include entities that are explicitly named.
"""
```

## Best Practices

### When to Use Variable Output (`[]`)

Use variable output multiplicity when:

- The number of outputs depends on the content being analyzed
- You're extracting or identifying items (entities, keywords, issues)
- The count isn't known until after processing
- You want the LLM to use its judgment about completeness

### When to Use Fixed Output (`[N]`)

Use fixed output multiplicity when:

- You need a specific number for downstream processes
- You're generating alternatives for comparison or selection
- External requirements dictate a fixed count
- You want consistent batch sizes for processing

### When to Use Variable Input (Empty Brackets `[]`)

Use variable input multiplicity when:

- The pipe should handle batches of unknown size
- You're aggregating or summarizing multiple items
- The workflow involves collecting items before processing
- You want maximum flexibility in how the pipe is called

### When to Use Fixed Input (Brackets with Number `[N]`)

Use fixed input multiplicity when:

- The operation inherently requires a specific count (e.g., comparison of 2 items)
- You want to enforce validation at the pipeline level
- The prompt logic depends on an exact number of inputs
- You're preventing misuse by requiring the right number of items

## How Multiplicity Interacts with ListContent

When a pipe produces multiple outputs, Pipelex automatically wraps them in a `ListContent` container. This container maintains the type information:

```python
from pipelex.pipeline.execute import execute_pipeline

# Execute a pipe with multiple outputs
pipe_output = await execute_pipeline(
    pipe_code="extract_line_items",
    inputs={"invoice_text": "Your invoice text here..."}
)

# Get the list of line items
line_items_list = pipe_output.main_stuff_as_items(item_type=LineItem)
# Result: [LineItem(...), LineItem(...), LineItem(...)]

# Or work with the ListContent directly
line_items_container = pipe_output.main_stuff_as_list(item_type=LineItem)
# Result: ListContent[LineItem] with additional metadata
```

Similarly, when providing multiple inputs, you can use lists:

```python
from pipelex.core.stuffs.text_content import TextContent

pipe_output = await execute_pipeline(
    pipe_code="summarize_all_documents",
    inputs={
        "documents": [
            TextContent(text="Document 1 content..."),
            TextContent(text="Document 2 content..."),
            TextContent(text="Document 3 content..."),
        ]
    }
)
```

## Summary

Multiplicity in Pipelex gives you precise control over how many items flow through your pipelines:

- **Concepts stay singular** to maintain clean semantics
- **Output multiplicity** (bracket notation in `output` field) controls generation
- **Input multiplicity** (bracket notation in `inputs` definition) enforces expectations
- **Variable multiplicity** (`[]`) for unknown counts
- **Fixed multiplicity** (`[N]`) for exact requirements

By understanding and using multiplicity effectively, you can build pipelines that handle both single items and collections with clarity and type safety.

