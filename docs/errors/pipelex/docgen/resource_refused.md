---
title: "pipelex.docgen.resource_refused"
description: "The document names a file it may not read: what the Pipelex error code pipelex.docgen.resource_refused means, who must act and what to do."
---

# pipelex.docgen.resource_refused

**The document names a file it may not read**

| | |
|---|---|
| Type | `https://docs.pipelex.com/errors/pipelex.docgen.resource_refused` |
| Family | [`pipelex.docgen`](../../index.md#pipelex-docgen): The document engines that print a PipeDocGen step's documents. |
| [Domain](https://mthds.ai/latest/spec/protocol/#domain-who-must-act) | `method`: the method's author acts, by changing the method |
| [Retry](https://mthds.ai/latest/spec/protocol/#retry) | `no`: repeating the operation fails the same way |
| HTTP status | `422` |
| Raised as | a problem document, sent as the body of an HTTP response or kept in a run's record |

## What it means

The print engine's fetcher refused a resource the document names, by policy. A plain `http://` URL breaks a transport rule rather than a security one, so its refusal records no security event.

## What to do

Use an absolute `https://` URL, embed the file as a data URL that decodes, or use a font the engine provides.

## Next steps

A problem carries the [step](https://mthds.ai/latest/spec/protocol/#next-steps) aimed at whoever reads it: the first when its reader is the domain's actor, the method's author, and the second for any other reader.

| Reader | Kind | Detail |
|---|---|---|
| The domain's actor | `change_method` | Name the file by an absolute https URL or embed it, then run the method again. |
| Any other reader | `contact_owner` | Ask the method's owner to fix the file its document names. |

## Detail

The problem's `detail` is written from this template, filled with the occurrence's parameters:

> The document names a file the print engine may not read (reason: `{reason}`).

## Parameters

Every parameter is present on every occurrence of the code.

| Name | Type | Description |
|---|---|---|
| `reason` | one of `relative_url`, `plain_http_url`, `undecodable_data_url`, `unknown_font` | Why the file was refused: a relative URL, a plain http URL, a data URL that does not decode, or a font the engine does not know. |

## See also

- [Document Engine Plugins](../../../under-the-hood/document-engine-plugins.md)
- [The MTHDS error registry format](https://mthds.ai/latest/spec/error-registry/), which describes the members of this page
- [Error Codes](../../index.md), every Pipelex code
