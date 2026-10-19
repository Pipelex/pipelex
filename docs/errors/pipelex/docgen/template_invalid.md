---
title: "pipelex.docgen.template_invalid"
description: "The document template cannot be used: what the Pipelex error code pipelex.docgen.template_invalid means, who must act and what to do."
---

# pipelex.docgen.template_invalid

**The document template cannot be used**

| | |
|---|---|
| Type | `https://docs.pipelex.com/errors/pipelex.docgen.template_invalid` |
| Family | [`pipelex.docgen`](../../index.md#pipelex-docgen): The document engines that print a PipeDocGen step's documents. |
| [Domain](https://mthds.ai/latest/spec/protocol/#domain-who-must-act) | `method`: the method's author acts, by changing the method |
| [Retry](https://mthds.ai/latest/spec/protocol/#retry) | `no`: repeating the operation fails the same way |
| HTTP status | `422` |
| Raised as | a problem document, sent as the body of an HTTP response or kept in a run's record |

## What it means

A PipeDocGen step's template cannot be used to print its document.

## What to do

Read `params.finding`, then fix the template, or the inputs the step maps into it.

## Next steps

A problem carries the [step](https://mthds.ai/latest/spec/protocol/#next-steps) aimed at whoever reads it: the first when its reader is the domain's actor, the method's author, and the second for any other reader.

| Reader | Kind | Detail |
|---|---|---|
| The domain's actor | `change_method` | Fix the template '`{template}`', then run the method again. |
| Any other reader | `contact_owner` | Ask the method's owner to fix the template '`{template}`'. |

## Detail

The problem's `detail` is written from this template, filled with the occurrence's parameters:

> The document template '`{template}`' cannot be used (reason: `{reason}`): `{finding}`

## Parameters

Every parameter is present on every occurrence of the code.

| Name | Type | Description |
|---|---|---|
| `template` | `identifier` | The template. |
| `reason` | one of `unreadable`, `does_not_fit`, `check_failed`, `value_unsupported` | Why it cannot be used: it is not a readable file of its format, it does not fit the step's inputs, it fails the engine's check, or it maps a value no cell can take. |
| `finding` | `caller_text` | What the engine found, about the method's own template. |

## See also

- [Document Engine Plugins](../../../under-the-hood/document-engine-plugins.md)
- [The MTHDS error registry format](https://mthds.ai/latest/spec/error-registry/), which describes the members of this page
- [Error Codes](../../index.md), every Pipelex code
