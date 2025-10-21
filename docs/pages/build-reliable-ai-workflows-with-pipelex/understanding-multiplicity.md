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

Output multiplicity controls how many items a pipe produces. This is most commonly used with `PipeLLM` to generate multiple outputs from a single execution.

### The Two Modes of Output Multiplicity

Pipelex supports two ways to specify output multiplicity:

1. **Fixed multiplicity** (`nb_output`): Generate an exact number of items
2. **Variable multiplicity** (`multiple_output`): Let the LLM decide how many items to generate

### Fixed Output Multiplicity

Use `nb_output` when you need a specific, predetermined number of outputs:

```plx
[concept]
Headline = "A catchy title for content"

[pipe.generate_headline_options]
type = "PipeLLM"
description = "Generate headline alternatives"
inputs = { article_text = "Text" }
output = "Headline"
nb_output = 5
prompt = """
Read this article:

@article_text

Generate $_nb_output different headline options for this article.
Make each one unique and compelling.
"""
```

In this example, the pipe will always produce exactly 5 headlines. The variable `$_nb_output` is automatically available in your prompt, making it easy to communicate the requirement to the LLM.

**Common use cases for fixed multiplicity:**

- Generate N alternative versions for A/B testing
- Create a fixed set of options for user selection
- Produce a specific number of variations for comparison
- Match external requirements (e.g., "always provide 3 recommendations")

### Variable Output Multiplicity

Use `multiple_output = true` when the number of outputs should depend on the content:

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
output = "LineItem"
multiple_output = true
prompt = """
Extract all line items from this invoice:

@invoice_text

For each line item, extract the description, quantity, unit price, and total amount.
"""
```

Here, the pipe will extract however many line items appear in the invoice. A simple invoice might have 2 line items, while a detailed purchase order might have 50.

**Common use cases for variable multiplicity:**

- Extract entities from text (unknown count in advance)
- Generate as many alternatives as needed
- List all items that match criteria
- Identify all occurrences of a pattern

### Single Output (Default)

When you don't specify `nb_output` or `multiple_output`, a pipe produces a single output:

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

## Input Multiplicity

Input multiplicity specifies whether a pipe expects a single item or multiple items as input. This allows you to design pipes that explicitly require lists or explicitly require single items.

### Syntax for Input Multiplicity

Input multiplicity is specified using an expanded syntax in the `inputs` dictionary:

```plx
# Standard syntax (single item, the default)
inputs = { document = "Text" }

# Equivalent with explicit multiplicity = false (not needed, but shown for clarity)
inputs = { document = { concept = "Text", multiplicity = false } }

# Variable list (indeterminate number)
inputs = { documents = { concept = "Text", multiplicity = true } }

# Fixed count (exactly N items)
inputs = { comparison_items = { concept = "Text", multiplicity = 2 } }
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

!!! note "No Need for `multiplicity = false`"
    You don't need to specify `multiplicity = false` explicitly, it's the default. Only use the expanded syntax when you need `multiplicity = true` or a fixed integer count.

**2. Variable list (`multiplicity = true`)**

When you set `multiplicity = true`, the pipe expects a list with an indeterminate number of items:

```plx
[concept]
Document = "A written or printed record"
Summary = "A concise overview of multiple documents"

[pipe.summarize_all_documents]
type = "PipeLLM"
description = "Create a unified summary of multiple documents"
inputs = { documents = { concept = "Document", multiplicity = true } }
output = "Summary"
prompt = """
Analyze all of these documents:

@documents

Create a single unified summary that captures the key points across all documents.
"""
```

**3. Fixed count (`multiplicity = N`)**

When you set `multiplicity` to a specific integer, the pipe expects exactly that many items:

```plx
[concept]
Image = "A visual image file"
Comparison = "A detailed comparison analysis"

[pipe.compare_two_images]
type = "PipeLLM"
description = "Compare exactly two images side by side"
inputs = { images = { concept = "Image", multiplicity = 2 } }
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
inputs = { invoice_images = { concept = "InvoiceImage", multiplicity = true } }
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
inputs = { products = { concept = "ProductDescription", multiplicity = 2 } }
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
output = "CompanyName"
multiple_output = true
prompt = """
Read this article:

@article

Extract all company and organization names mentioned in the article.
Only include entities that are explicitly named.
"""
```

## Best Practices

### When to Use Variable Output (`multiple_output = true`)

Use variable output multiplicity when:

- The number of outputs depends on the content being analyzed
- You're extracting or identifying items (entities, keywords, issues)
- The count isn't known until after processing
- You want the LLM to use its judgment about completeness

### When to Use Fixed Output (`nb_output = N`)

Use fixed output multiplicity when:

- You need a specific number for downstream processes
- You're generating alternatives for comparison or selection
- External requirements dictate a fixed count
- You want consistent batch sizes for processing

### When to Use Variable Input (`multiplicity = true`)

Use variable input multiplicity when:

- The pipe should handle batches of unknown size
- You're aggregating or summarizing multiple items
- The workflow involves collecting items before processing
- You want maximum flexibility in how the pipe is called

### When to Use Fixed Input (`multiplicity = N`)

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
    input_memory={"invoice_text": "Your invoice text here..."}
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
    input_memory={
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
- **Output multiplicity** (`nb_output`, `multiple_output`) controls generation
- **Input multiplicity** (in the `inputs` definition) enforces expectations
- **Variable multiplicity** (`true`) for unknown counts
- **Fixed multiplicity** (integer) for exact requirements

By understanding and using multiplicity effectively, you can build pipelines that handle both single items and collections with clarity and type safety.

