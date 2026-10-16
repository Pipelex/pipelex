---
title: "pipelex.docgen.template_warning"
description: "The document template may be faulty: what the Pipelex error code pipelex.docgen.template_warning means, who must act and what to do."
---

# pipelex.docgen.template_warning

**The document template may be faulty**

| | |
|---|---|
| Type | `https://docs.pipelex.com/errors/pipelex.docgen.template_warning` |
| Family | [`pipelex.docgen`](../../index.md#pipelex-docgen): The document engines that print a PipeDocGen step's documents. |
| [Domain](https://mthds.ai/latest/spec/protocol/#domain-who-must-act) | `method`: the method's author acts, by changing the method |
| [Retry](https://mthds.ai/latest/spec/protocol/#retry) | `no`: repeating the operation fails the same way |
| HTTP status | none (warning) |
| Raised as | an item of a validate verdict's `warnings`, which never makes a method invalid |

## What it means

An advisory: the check of a PipeDocGen step's template found a likely fault, which does not stop the method from validating.

## What to do

Read `params.finding`, check the template, and fix it if the finding is right.

## Next steps

A warning carries no [step](https://mthds.ai/latest/spec/protocol/#next-steps) of its own, since it is an item of a validate verdict, so its reader takes one of the code's steps: the first when the reader is the domain's actor, the method's author, and the second for any other reader.

| Reader | Kind | Detail |
|---|---|---|
| The domain's actor | `change_method` | Check the template '`{template}`', and fix it if the finding is right. |
| Any other reader | `contact_owner` | Ask the method's owner to check the template '`{template}`'. |

## Detail

The problem's `detail` is written from this template, filled with the occurrence's parameters:

> The document template '`{template}`' may be faulty: `{finding}`

## Parameters

Every parameter is present on every occurrence of the code.

| Name | Type | Description |
|---|---|---|
| `template` | `identifier` | The template. |
| `finding` | `caller_text` | What the check found, about the method's own template. |

## See also

- [Document Engine Plugins](../../../under-the-hood/document-engine-plugins.md)
- [The MTHDS error registry format](https://mthds.ai/latest/spec/error-registry/), which describes the members of this page
- [Error Codes](../../index.md), every Pipelex code
