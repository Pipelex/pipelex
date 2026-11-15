---
title: "pipelex.docgen.template_input_unfit"
description: "The template a run supplied does not fit the step: what the Pipelex error code pipelex.docgen.template_input_unfit means, who must act and what to do."
---

# pipelex.docgen.template_input_unfit

**The template a run supplied does not fit the step**

| | |
|---|---|
| Type | `https://docs.pipelex.com/errors/pipelex.docgen.template_input_unfit` |
| Family | [`pipelex.docgen`](../../index.md#pipelex-docgen): The document engines that print a PipeDocGen step's documents. |
| [Domain](https://mthds.ai/latest/spec/protocol/#domain-who-must-act) | `input`: the caller acts, by changing the request or its inputs |
| [Retry](https://mthds.ai/latest/spec/protocol/#retry) | `no`: repeating the operation fails the same way |
| HTTP status | `422` |
| Raised as | a problem document, sent as the body of an HTTP response or kept in a run's record |

## What it means

A PipeDocGen step takes its template from a run input, and the engine's check of the file found that it does not fit the step's inputs, such as a Table the step fills that the workbook lacks.

## What to do

Read `params.finding`, then fix the file, or give the input another one, and run the method again.

## Next steps

A problem carries the [step](https://mthds.ai/latest/spec/protocol/#next-steps) aimed at whoever reads it: the first when its reader is the domain's actor, the caller, and the second for any other reader.

| Reader | Kind | Detail |
|---|---|---|
| The domain's actor | `change_input` | Give the input '`{input}`' a file that fits the step's template, then run the method again. |
| Any other reader | `change_input` | Pass this to the caller, whose file for the input '`{input}`' does not fit the step's template. |

## Detail

The problem's `detail` is written from this template, filled with the occurrence's parameters:

> The file of the input '`{input}`' cannot be used as the document's template: `{finding}`

## Parameters

Every parameter is present on every occurrence of the code.

| Name | Type | Description |
|---|---|---|
| `input` | `identifier` | The input whose file is the template. |
| `finding` | `caller_text` | What the engine's check found in the file the caller supplied. |

## See also

- [Document Engine Plugins](../../../under-the-hood/document-engine-plugins.md)
- [The MTHDS error registry format](https://mthds.ai/latest/spec/error-registry/), which describes the members of this page
- [Error Codes](../../index.md), every Pipelex code
