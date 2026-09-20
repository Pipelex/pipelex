# Example: Expense Data with Receipts

This advanced example generates complete synthetic expense datasets for multiple employees, including realistic receipt images and HTML reports. It features fraud scenario generation for testing expense validation systems.

## Get the code

[![GitHub](https://img.shields.io/badge/View_on_GitHub-5a0dad?logo=github&logoColor=white&style=flat)](https://github.com/Pipelex/pipelex-cookbook/blob/main/examples/c_advanced/gen_expense_data/bundle.mthds)

## What it demonstrates

- Deep concept hierarchy (Employee, ExpenseScenario, CompanyProfile, ReceiptContent, Expense, etc.)
- Nested `PipeSequence` pipelines (main pipeline batches over employees, sub-pipeline batches over categories)
- `PipeImgGen` for generating realistic receipt images
- `PipeCompose` with `construct` for assembling structured objects from parts
- `PipeCompose` with HTML templates for report rendering
- Fraud scenario modeling (weekend expenses, inflated amounts, receipt mismatches, vague purposes)
- Custom Python runner for post-processing (PDF generation, file export)

## The Method: `bundle.mthds`

### Concept hierarchy (simplified)

```
NbOfEmployees (input, refines Number)
  -> Employee[]
     -> CompanyCategory[] (with ExpenseScenario)
        -> CompanyProfile
        -> ReceiptContent (from ReceiptHeader + ReceiptItemsAndTotals + ExpenseMetadata)
        -> Receipt (image via PipeImgGen)
        -> Expense + Receipt = ExpenseWithReceipt
     -> EmployeeExpenseReport (employee + expenses + HTML report)
```

### Main pipeline

```toml
[pipe.generate_expense_dataset]
type = "PipeSequence"
inputs = { nb_employees = "NbOfEmployees" }
output = "EmployeeExpenseReport[]"
steps = [
  { pipe = "generate_employees", result = "employees" },
  { pipe = "generate_employee_report", batch_over = "employees", batch_as = "employee", result = "reports" },
]
```

For each employee, the `generate_employee_report` sub-pipeline assigns expense categories (with fraud scenarios), then for each category generates a company profile, receipt content, receipt image, and expense record.

### Receipt generation

Receipt content is built in multiple steps: header (transaction number, date), items and totals (from the company's product catalog), and business purpose metadata. These are composed into formatted thermal-paper-style text, then rendered as a photo using `PipeImgGen`.

## How to run

**Using the CLI:**

```bash
pipelex run bundle examples/c_advanced/gen_expense_data/bundle.mthds \
  -i examples/c_advanced/gen_expense_data/inputs.json
```

**Using the Python runner** (for PDF export and file organization):

```bash
cd examples/c_advanced/gen_expense_data
python run_generate_expense_dataset.py
```

## Related Documentation

- [PipeSequence Controller](../building-methods/pipes/pipe-controllers/PipeSequence.md) - Chain pipes into sequential workflows
- [PipeImgGen Operator](../building-methods/pipes/pipe-operators/PipeImgGen.md) - Generate images from prompts
- [PipeCompose Operator](../building-methods/pipes/pipe-operators/PipeCompose.md) - Template-based data composition
- [Understanding Multiplicity](../building-methods/pipes/understanding-multiplicity.md) - How batching works
