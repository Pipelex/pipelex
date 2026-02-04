---
name: synthesize-inputs
description: Generate synthetic test inputs for Pipelex workflows. Use when user asks to "create test data", "generate inputs", "synthesize inputs", "mock inputs", or wants to test a .plx workflow with realistic data. Analyzes workflow input requirements and produces complete JSON input files with realistic content.
---

# Synthesize Inputs

Generate realistic synthetic inputs for testing Pipelex workflows. Uses the agent CLI to extract input schemas, then populates them with appropriate test data.

## Workflow

### Step 1: Get Input Schema

Extract the input template from the workflow:

```bash
pipelex-agent inputs <bundle.plx> [--pipe specific_pipe]
```

**Output format:**
```json
{
  "success": true,
  "pipe_code": "process_document",
  "inputs": {
    "document": {
      "concept": "native.Document",
      "content": {"url": "url_value"}
    },
    "context": {
      "concept": "native.Text",
      "content": {"text": "text_value"}
    }
  }
}
```

### Step 2: Identify Input Types

Parse the JSON output to identify what types of synthetic data are needed:

| Concept | Content Fields | Synthesis Method |
|---------|---------------|------------------|
| `native.Text` | `text` | Generate realistic text matching the workflow context |
| `native.Number` | `number` | Generate appropriate numeric values |
| `native.Image` | `url`, `caption?`, `mime_type?` | Use `synthesize_image` pipeline |
| `native.Document` | `url`, `mime_type?` | Use document generation skills |
| `native.Page` | `text_and_images`, `page_view?` | Composite: text + optional images |
| `native.TextAndImages` | `text?`, `images?` | Composite: text + image list |
| `native.JSON` | `json_obj` | Generate structured JSON matching context |
| Custom structured | Per-field types | Recurse through structure fields |

**List types** (`Type[]` or `Type[N]`): Generate multiple items. Variable lists typically need 2-5 items; fixed lists need exactly N items.

### Step 3: Generate Content

For each input, generate appropriate synthetic content:

**Text inputs**: Create realistic text that matches the workflow's purpose. Consider:
- If the workflow processes invoices, generate invoice-like text
- If it analyzes reports, generate report-style content
- Match expected length (short prompts vs long documents)

**Numeric inputs**: Generate sensible values within expected ranges.

**Structured concepts**: Fill each field according to its type and description.

### Step 4: Generate File Inputs

When inputs require actual files (Image, Document), use the appropriate generation method.

---

## Image Generation

Use the `synthesize_image` Pipelex pipeline to generate test images.

**Command:**
```bash
pipelex run synthesize_image.plx --input request='{"category": "<category>", "description": "<optional description>"}'
```

**Image Categories:**

| Category | Use For | Example Description |
|----------|---------|---------------------|
| `photograph` | Real-world photos, product images, portraits | "A professional headshot of a business person" |
| `screenshot` | UI mockups, app screens, web pages | "A mobile banking app dashboard showing account balance" |
| `chart` | Data visualizations, graphs, plots | "A bar chart showing quarterly sales by region" |
| `diagram` | Technical diagrams, flowcharts, architecture | "A system architecture diagram with microservices" |
| `document_scan` | Scanned papers, receipts, forms | "A scanned invoice from a hardware store" |
| `handwritten` | Handwritten notes, signatures | "Handwritten meeting notes on lined paper" |

**Examples:**
```bash
# Generate a product photo
pipelex run synthesize_image.plx --input request='{"category": "photograph", "description": "A red sneaker on white background"}'

# Generate a chart
pipelex run synthesize_image.plx --input request='{"category": "chart", "description": "Pie chart showing market share percentages"}'

# Generate a scanned document
pipelex run synthesize_image.plx --input request='{"category": "document_scan", "description": "A utility bill with usage details"}'

# Simple generation (category only)
pipelex run synthesize_image.plx --input request='{"category": "screenshot"}'
```

**Output**: The pipeline saves the generated image to `pipelex-wip/test-files/` and returns the file path.

---

## Document Generation

Generate test documents based on the document type needed.

### PDF Documents

**If `example-skills:pdf` skill is available:**
```
Use the /pdf skill to create a PDF document with the following content:
[Describe the document content, structure, and any specific fields]
Save to: pipelex-wip/test-files/<filename>.pdf
```

**If skill is NOT available**, create a simple PDF using Python:
```python
# Requires: pip install reportlab
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

pdf = canvas.Canvas("pipelex-wip/test-files/test_document.pdf", pagesize=letter)
pdf.drawString(100, 750, "Test Document Title")
pdf.drawString(100, 730, "This is synthetic test content.")
# Add more content as needed
pdf.save()
```

Or use a public test PDF URL as fallback:
```json
{
  "url": "https://www.w3.org/WAI/WCAG21/Techniques/pdf/img/table-word.pdf",
  "mime_type": "application/pdf"
}
```

### Word Documents (DOCX)

**If `example-skills:docx` skill is available:**
```
Use the /docx skill to create a Word document with the following content:
[Describe the document content, structure, and formatting]
Save to: pipelex-wip/test-files/<filename>.docx
```

**If skill is NOT available**, create using Python:
```python
# Requires: pip install python-docx
from docx import Document

doc = Document()
doc.add_heading('Test Document', 0)
doc.add_paragraph('This is synthetic test content for workflow testing.')
# Add more content as needed
doc.save('pipelex-wip/test-files/test_document.docx')
```

### Spreadsheets (XLSX)

**If `example-skills:xlsx` skill is available:**
```
Use the /xlsx skill to create a spreadsheet with the following data:
[Describe columns, rows, and sample data]
Save to: pipelex-wip/test-files/<filename>.xlsx
```

**If skill is NOT available**, create using Python:
```python
# Requires: pip install openpyxl
from openpyxl import Workbook

wb = Workbook()
ws = wb.active
ws['A1'] = 'Column1'
ws['B1'] = 'Column2'
ws['A2'] = 'Value1'
ws['B2'] = 'Value2'
wb.save('pipelex-wip/test-files/test_spreadsheet.xlsx')
```

---

## Checking Available Skills

Before attempting to use document generation skills, check if they're available:

```bash
# List available skills (look for pdf, docx, xlsx in the output)
claude --help
```

**Fallback Strategy:**
1. First, try to use the appropriate skill (`/pdf`, `/docx`, `/xlsx`)
2. If skill not available, use Python script generation
3. If Python dependencies missing, use public test file URLs
4. As last resort, ask user to provide test files

---

## Assembling Final Input

Create the complete input JSON file:

```json
{
  "document": {
    "concept": "native.Document",
    "content": {
      "url": "pipelex-wip/test-files/invoice.pdf",
      "mime_type": "application/pdf"
    }
  },
  "product_image": {
    "concept": "native.Image",
    "content": {
      "url": "pipelex-wip/test-files/product_photo.jpg",
      "mime_type": "image/jpeg",
      "caption": "Product photograph for analysis"
    }
  },
  "instructions": {
    "concept": "native.Text",
    "content": {
      "text": "Extract the invoice details and match with the product image."
    }
  }
}
```

**Save location**: Save input files to `pipelex-wip/inputs/` with descriptive names.

---

## Validate & Run

Test the synthetic inputs:

```bash
# Dry run with the generated inputs
pipelex-agent run <bundle.plx> --dry-run --input-file pipelex-wip/inputs/test_input.json

# Full run (uses actual AI/extraction models)
pipelex-agent run <bundle.plx> --input-file pipelex-wip/inputs/test_input.json
```

---

## Native Concept Content Structures

### Text
```json
{"text": "The actual text content"}
```

### Number
```json
{"number": 42}
```

### Image
```json
{
  "url": "/path/to/image.jpg",
  "caption": "Optional description",
  "mime_type": "image/jpeg"
}
```

### Document
```json
{
  "url": "/path/to/document.pdf",
  "mime_type": "application/pdf"
}
```

### TextAndImages
```json
{
  "text": {"text": "Main text content"},
  "images": [
    {"url": "/path/to/img1.png", "caption": "Figure 1"}
  ]
}
```

### Page
```json
{
  "text_and_images": {
    "text": {"text": "Page content..."},
    "images": []
  },
  "page_view": null
}
```

### JSON
```json
{"json_obj": {"key": "value", "nested": {"data": 123}}}
```

---

## Complete Example

**Workflow**: Image analysis pipeline expecting `image: Image` and `analysis_prompt: Text`

**Step 1**: Get schema
```bash
pipelex-agent inputs image_analyzer.plx
```

**Step 2**: Identify needs:
- `image`: Need a test photograph
- `analysis_prompt`: Need instruction text

**Step 3**: Generate image
```bash
pipelex run synthesize_image.plx --input request='{"category": "photograph", "description": "A busy city street with pedestrians and storefronts"}'
```

**Step 4**: Assemble input file
```json
{
  "image": {
    "concept": "native.Image",
    "content": {
      "url": "pipelex-wip/test-files/city_street.jpg",
      "mime_type": "image/jpeg",
      "caption": "Urban street scene for analysis"
    }
  },
  "analysis_prompt": {
    "concept": "native.Text",
    "content": {
      "text": "Analyze this street scene. Count the number of visible people, identify any storefronts, and describe the overall atmosphere."
    }
  }
}
```

**Step 5**: Test
```bash
pipelex-agent run image_analyzer.plx --input-file pipelex-wip/inputs/city_analysis_input.json
```

---

## Reference

See [Pipelex Language Reference](../shared/pipelex-reference.md) for concept definitions and syntax.
