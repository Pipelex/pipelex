---
title: "pipelex.security.reserved_key"
description: "The request carries a reserved key: what the Pipelex error code pipelex.security.reserved_key means, who must act and what to do."
---

# pipelex.security.reserved_key

**The request carries a reserved key**

| | |
|---|---|
| Type | `https://docs.pipelex.com/errors/pipelex.security.reserved_key` |
| Family | [`pipelex.security`](../../index.md#pipelex-security): Pipelex's own refusals made for safety, each recorded as a security event. |
| [Domain](https://mthds.ai/latest/spec/protocol/#domain-who-must-act) | `input`: the caller acts, by changing the request or its inputs |
| [Retry](https://mthds.ai/latest/spec/protocol/#retry) | `no`: repeating the operation fails the same way |
| HTTP status | `422` |
| Raised as | a problem document, sent as the body of an HTTP response or kept in a run's record |

## What it means

An object in the request holds a key that Pipelex's decoder would read as a class marker, such as `__class__`, `__module__` or a key starting with `__kajson`. The request is refused, and the refusal is recorded as a security event.

## What to do

Rename or remove each key `params.keys` lists. No input of a method needs one.

## Next steps

A problem carries the [step](https://mthds.ai/latest/spec/protocol/#next-steps) aimed at whoever reads it: the first when its reader is the domain's actor, the caller, and the second for any other reader.

| Reader | Kind | Detail |
|---|---|---|
| The domain's actor | `change_input` | Rename or remove the reserved keys in the request, then send it again. |
| Any other reader | `change_input` | Pass this to the caller, whose request carries reserved keys. |

## Detail

The problem's `detail` is written from this template, filled with the occurrence's parameters:

> The request carries object keys that Pipelex's decoder reserves for its own markers.

## Parameters

Every parameter is present on every occurrence of the code.

| Name | Type | Description |
|---|---|---|
| `keys` | list of `identifier` | The reserved keys the request carries. |

## See also

- [The MTHDS error registry format](https://mthds.ai/latest/spec/error-registry/), which describes the members of this page
- [Error Codes](../../index.md), every Pipelex code
