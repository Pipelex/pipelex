---
title: "pipelex.request.dependency_key_mismatch"
description: "A dependency is keyed by another address than its manifest declares: what the Pipelex error code pipelex.request.dependency_key_mismatch means, who must act and what to do."
---

# pipelex.request.dependency_key_mismatch

**A dependency is keyed by another address than its manifest declares**

| | |
|---|---|
| Type | `https://docs.pipelex.com/errors/pipelex.request.dependency_key_mismatch` |
| Family | [`pipelex.request`](../../index.md#pipelex-request): Refusals of a request's shape that name a fact no core code carries. |
| [Domain](https://mthds.ai/latest/spec/protocol/#domain-who-must-act) | `input`: the caller acts, by changing the request or its inputs |
| [Retry](https://mthds.ai/latest/spec/protocol/#retry) | `no`: repeating the operation fails the same way |
| HTTP status | `422` |
| Raised as | a problem document, sent as the body of an HTTP response or kept in a run's record |

## What it means

A request ships each package its method calls by address in `dependencies`, keyed by the package's full address: the address its `METHODS.toml` declares, followed by a slash and the package's name. This dependency is keyed by another address, such as its repository address alone, so the method's calls cannot reach it.

## What to do

Key the dependency by `params.address`, the full address its manifest declares, as the method's calls name it.

## Next steps

A problem carries the [step](https://mthds.ai/latest/spec/protocol/#next-steps) aimed at whoever reads it: the first when its reader is the domain's actor, the caller, and the second for any other reader.

| Reader | Kind | Detail |
|---|---|---|
| The domain's actor | `change_input` | Key the dependency by '`{address}`', the address its manifest declares, then send the request again. |
| Any other reader | `change_input` | Pass this to the caller, who must key the dependency '`{key}`' by '`{address}`'. |

## Detail

The problem's `detail` is written from this template, filled with the occurrence's parameters:

> The dependency keyed '`{key}`' declares the address '`{address}`', which must be its key.

## Parameters

Every parameter is present on every occurrence of the code.

| Name | Type | Description |
|---|---|---|
| `key` | `identifier` | The key the request gives the dependency in `dependencies`. |
| `address` | `identifier` | The full address the dependency's manifest declares, its repository address followed by its package name, which its key must be. |

## See also

- [The MTHDS error registry format](https://mthds.ai/latest/spec/error-registry/), which describes the members of this page
- [Error Codes](../../index.md), every Pipelex code
