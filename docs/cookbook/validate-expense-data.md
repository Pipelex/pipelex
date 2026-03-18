---
title: "Expense Validation Example"
description: "Validate expense reports against company policies using a comprehensive Pipelex pipeline combining LLM checks, Python functions, and vision analysis."
---

# Example: Expense Validation

!!! warning "Work in Progress"
    This example is under active development and may change.

This example validates expense reports against company policies. It extracts data from PDF reports, then runs each expense through multiple validation checks — including receipt matching with vision, spending limits, weekend policy, purpose quality assessment, and amount reasonableness.

## Get the code

[![GitHub](https://img.shields.io/badge/View_on_GitHub-5a0dad?logo=github&logoColor=white&style=flat)](https://github.com/Pipelex/pipelex-cookbook/blob/main/examples/wip/validate_expense_data/validation.mthds)

## What it demonstrates

- `PipeFunc` for Python-based validation logic (spending limits, weekend checks, timeliness)
- `PipeLLM` with vision for receipt matching
- `PipeLLM` for subjective assessments (purpose quality, amount reasonableness)
- `PipeExtract` for PDF parsing
- Complex validation pipeline combining 6 different checks per expense
- Rich result concepts with detailed approval status and statistics

## The Method: `validation.mthds`

### Validation pipeline

```toml
[pipe.validate_expense_report]
type = "PipeSequence"
inputs = { expense_pdf = "ExpenseReportPDF", receipts = "ReceiptImage[]" }
output = "ValidationReport"
steps = [
  { pipe = "extract_pdf_content", result = "pages" },
  { pipe = "parse_expense_report", result = "report" },
  { pipe = "extract_expenses_list", result = "expenses" },
  { pipe = "validate_single_expense", batch_over = "expenses", batch_as = "expense",
    result = "expense_validations" },
  { pipe = "compose_validation_report", result = "validation_report" },
]
```

### Per-expense validation

Each expense goes through 6 checks, then results are composed:

```toml
[pipe.validate_single_expense]
type = "PipeSequence"
inputs = { report = "ExpenseReport", expense = "Expense", receipts = "ReceiptImage[]" }
output = "ExpenseValidationResult"
steps = [
  { pipe = "check_receipt_match", result = "receipt_check" },
  { pipe = "check_spending_limit", result = "limit_check" },
  { pipe = "check_weekend", result = "weekend_check" },
  { pipe = "check_timeliness", result = "timeliness_check" },
  { pipe = "check_purpose_quality", result = "purpose_check" },
  { pipe = "check_reasonable_amount", result = "reasonable_check" },
  { pipe = "compose_expense_result", result = "validation_result" },
]
```

The checks use a mix of:

- **`PipeFunc`**: Deterministic checks (spending limits, weekend detection, timeliness)
- **`PipeLLM`**: Subjective assessments (purpose quality, amount reasonableness)
- **`PipeLLM` with vision**: Receipt-to-expense matching

## How to run

This example requires a custom Python runner:

```bash
cd examples/wip/validate_expense_data
python run_validate_expenses.py
```

## Related Documentation

- [PipeFunc Operator](../building-methods/pipes/pipe-operators/PipeFunc.md) - Call Python functions from pipes
- [PipeLLM Operator](../building-methods/pipes/pipe-operators/PipeLLM.md) - The core operator for LLM interactions
- [PipeExtract Operator](../building-methods/pipes/pipe-operators/PipeExtract.md) - Extract text and images from documents
- [PipeSequence Controller](../building-methods/pipes/pipe-controllers/PipeSequence.md) - Chain pipes into sequential workflows
