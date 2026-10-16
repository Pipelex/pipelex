---
title: "pipelex.docgen.content_unprintable"
description: "The document's content cannot be printed: what the Pipelex error code pipelex.docgen.content_unprintable means, who must act and what to do."
---

# pipelex.docgen.content_unprintable

**The document's content cannot be printed**

| | |
|---|---|
| Type | `https://docs.pipelex.com/errors/pipelex.docgen.content_unprintable` |
| Family | [`pipelex.docgen`](../../index.md#pipelex-docgen): The document engines that print a PipeDocGen step's documents. |
| [Domain](https://mthds.ai/latest/spec/protocol/#domain-who-must-act) | `input`: the caller acts, by changing the request or its inputs |
| [Retry](https://mthds.ai/latest/spec/protocol/#retry) | `no`: repeating the operation fails the same way |
| HTTP status | `422` |
| Raised as | a problem document, sent as the body of an HTTP response or kept in a run's record |

## What it means

The run's data holds something the print engine cannot lay out or decode.

## What to do

Read `params.reason`, then shorten, resize or replace the content, and run the method again.

## Next steps

A problem carries the [step](https://mthds.ai/latest/spec/protocol/#next-steps) aimed at whoever reads it: the first when its reader is the domain's actor, the caller, and the second for any other reader.

| Reader | Kind | Detail |
|---|---|---|
| The domain's actor | `change_input` | Change the input that fills '`{element}`', then run the method again. |
| Any other reader | `change_input` | Pass this to the caller, whose inputs hold something the document cannot print. |

## Detail

The problem's `detail` is written from this template, filled with the occurrence's parameters:

> The run's data holds something the print engine cannot lay out (reason: `{reason}`, in '`{element}`').

## Parameters

Every parameter is present on every occurrence of the code.

| Name | Type | Description |
|---|---|---|
| `reason` | one of `too_tall_for_page`, `image_unreadable`, `image_too_large`, `image_empty`, `html_too_large` | What cannot be printed: an element taller than a page, an image that cannot be read, is too large or is empty, or HTML past its size limit. |
| `element` | `identifier` | The element of the document that holds it. |

## See also

- [The MTHDS error registry format](https://mthds.ai/latest/spec/error-registry/), which describes the members of this page
- [Error Codes](../../index.md), every Pipelex code
