---
title: "pipelex.catalog.selector_invalid"
description: "The catalog selector is malformed: what the Pipelex error code pipelex.catalog.selector_invalid means, who must act and what to do."
---

# pipelex.catalog.selector_invalid

**The catalog selector is malformed**

| | |
|---|---|
| Type | `https://docs.pipelex.com/errors/pipelex.catalog.selector_invalid` |
| Family | [`pipelex.catalog`](../../index.md#pipelex-catalog): Saved methods in an organization's catalog. |
| [Domain](https://mthds.ai/latest/spec/protocol/#domain-who-must-act) | `input`: the caller acts, by changing the request or its inputs |
| [Retry](https://mthds.ai/latest/spec/protocol/#retry) | `no`: repeating the operation fails the same way |
| HTTP status | `422` |
| Raised as | a problem document, sent as the body of an HTTP response or kept in a run's record |

## What it means

A method selector names a saved method by its catalog id, `mt_` and its characters, and may add `@3` for one version or `@draft` for the draft. This one breaks that grammar.

## What to do

Read `params.reason`, then correct the selector: a catalog id as the catalog returned it, with a version number that has no leading zero or the word `draft` after the `@`.

## Next steps

A problem carries the [step](https://mthds.ai/latest/spec/protocol/#next-steps) aimed at whoever reads it: the first when its reader is the domain's actor, the caller, and the second for any other reader.

| Reader | Kind | Detail |
|---|---|---|
| The domain's actor | `change_input` | Write the selector as a catalog id, alone or followed by '@' and a version number or 'draft', then send the request again. |
| Any other reader | `change_input` | Pass this to the caller, whose catalog selector cannot be parsed. |

## Detail

The problem's `detail` is written from this template, filled with the occurrence's parameters:

> The catalog selector cannot be parsed (reason: `{reason}`).

## Parameters

Every parameter is present on every occurrence of the code.

| Name | Type | Description |
|---|---|---|
| `reason` | one of `malformed_method_id`, `malformed_version_suffix`, `suffix_on_linkage` | What is wrong: the catalog id itself, the suffix after its '@', or a suffix where the request runs the source it sends and names no version. |

## See also

- [The MTHDS error registry format](https://mthds.ai/latest/spec/error-registry/), which describes the members of this page
- [Error Codes](../../index.md), every Pipelex code
