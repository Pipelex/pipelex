---
title: "pipelex.catalog.not_found"
description: "The saved method does not exist: what the Pipelex error code pipelex.catalog.not_found means, who must act and what to do."
---

# pipelex.catalog.not_found

**The saved method does not exist**

| | |
|---|---|
| Type | `https://docs.pipelex.com/errors/pipelex.catalog.not_found` |
| Family | [`pipelex.catalog`](../../index.md#pipelex-catalog): Saved methods in an organization's catalog. |
| [Domain](https://mthds.ai/latest/spec/protocol/#domain-who-must-act) | `input`: the caller acts, by changing the request or its inputs |
| [Retry](https://mthds.ai/latest/spec/protocol/#retry) | `no`: repeating the operation fails the same way |
| HTTP status | `404` |
| Raised as | a problem document, sent as the body of an HTTP response or kept in a run's record |

## What it means

No saved method, version or example matches the request in the catalog of the organization the request acts for.

## What to do

List the catalog's methods and their versions, and use an identifier that exists. A catalog id is read in the organization the request acts for, so check that it is the right one.

## Next steps

A problem carries the [step](https://mthds.ai/latest/spec/protocol/#next-steps) aimed at whoever reads it: the first when its reader is the domain's actor, the caller, and the second for any other reader.

| Reader | Kind | Detail |
|---|---|---|
| The domain's actor | `change_input` | List the organization's catalog to find the `{resource}`, then send the request again with one that exists. |
| Any other reader | `change_input` | Pass this to the caller, whose request names a `{resource}` the catalog does not hold. |

## Detail

The problem's `detail` is written from this template, filled with the occurrence's parameters:

> The organization's catalog holds no `{resource}` matching the request for the method '`{method_id}`'.

## Parameters

A parameter is present on every occurrence of the code unless it is marked optional, and one marked operator-only reaches only whoever runs the runtime, never a caller.

| Name | Type | Description |
|---|---|---|
| `resource` | one of `method`, `version`, `example` | What the request names: a saved method, one of its versions, or one of its examples. |
| `method_id` | `identifier` | The catalog id of the method the request names. |
| `version` | `integer` (optional) | The version the request names, when what it names is a version. |

## See also

- [The MTHDS error registry format](https://mthds.ai/latest/spec/error-registry/), which describes the members of this page
- [Error Codes](../../index.md), every Pipelex code
