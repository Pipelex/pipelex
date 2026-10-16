---
title: "pipelex.docgen.print_timeout"
description: "Printing the document took too long: what the Pipelex error code pipelex.docgen.print_timeout means, who must act and what to do."
---

# pipelex.docgen.print_timeout

**Printing the document took too long**

| | |
|---|---|
| Type | `https://docs.pipelex.com/errors/pipelex.docgen.print_timeout` |
| Family | [`pipelex.docgen`](../../index.md#pipelex-docgen): The document engines that print a PipeDocGen step's documents. |
| [Domain](https://mthds.ai/latest/spec/protocol/#domain-who-must-act) | `runtime`: nobody could have acted beforehand, so whoever made the call waits, retries or reports the problem |
| [Retry](https://mthds.ai/latest/spec/protocol/#retry) | `yes`: repeating the operation may succeed, after `retry_after` seconds when the problem gives it |
| HTTP status | `504` |
| Raised as | a problem document, sent as the body of an HTTP response or kept in a run's record |

## What it means

The print, or a resource it read, ran past its limit and was stopped.

## What to do

Run the method again. If the print keeps running past its limit, make the document lighter, or report it to whoever runs the runtime.

## Next steps

A problem carries the [step](https://mthds.ai/latest/spec/protocol/#next-steps) aimed at whoever reads it: the first when its reader is the domain's actor, whoever made the call, and the second for any other reader.

| Reader | Kind | Detail |
|---|---|---|
| The domain's actor | `retry` | Run the method again, since the print may finish within its limit. |
| Any other reader | `retry` | Run the method again, since the print may finish within its limit. |

## Detail

The problem's `detail` is written from this template, filled with the occurrence's parameters:

> Printing the document ran past its limit of `{limit}` seconds and was stopped.

## Parameters

Every parameter is present on every occurrence of the code.

| Name | Type | Description |
|---|---|---|
| `limit` | `seconds` | The time the print was allowed. |

## See also

- [The MTHDS error registry format](https://mthds.ai/latest/spec/error-registry/), which describes the members of this page
- [Error Codes](../../index.md), every Pipelex code
