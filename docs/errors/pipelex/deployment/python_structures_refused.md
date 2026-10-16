---
title: "pipelex.deployment.python_structures_refused"
description: "Python structure classes are not allowed here: what the Pipelex error code pipelex.deployment.python_structures_refused means, who must act and what to do."
---

# pipelex.deployment.python_structures_refused

**Python structure classes are not allowed here**

| | |
|---|---|
| Type | `https://docs.pipelex.com/errors/pipelex.deployment.python_structures_refused` |
| Family | [`pipelex.deployment`](../../index.md#pipelex-deployment): The policies of a runner deployment. |
| [Domain](https://mthds.ai/latest/spec/protocol/#domain-who-must-act) | `method`: the method's author acts, by changing the method |
| [Retry](https://mthds.ai/latest/spec/protocol/#retry) | `no`: repeating the operation fails the same way |
| HTTP status | `422` |
| Raised as | a problem document, sent as the body of an HTTP response or kept in a run's record |

## What it means

The method declares its structures as Python classes, which no hosted runner imports. Concepts declared in the method itself replace them.

## What to do

Rewrite each structure the files in `params.files` declare as a concept with its fields in the method, then run it again.

## Next steps

A problem carries the [step](https://mthds.ai/latest/spec/protocol/#next-steps) aimed at whoever reads it: the first when its reader is the domain's actor, the method's author, and the second for any other reader.

| Reader | Kind | Detail |
|---|---|---|
| The domain's actor | `change_method` | Declare the structures as concepts in the method in place of Python classes, then run it again. |
| Any other reader | `contact_owner` | Ask the method's owner to declare its structures as concepts in the method. |

## Detail

The problem's `detail` is written from this template, filled with the occurrence's parameters:

> The method declares structures as Python classes, which this runner does not import.

## Parameters

Every parameter is present on every occurrence of the code.

| Name | Type | Description |
|---|---|---|
| `files` | list of `identifier` | The method's files that declare structures as Python classes. |

## See also

- [Python StructuredContent Classes](../../../building-methods/concepts/python-classes.md)
- [The MTHDS error registry format](https://mthds.ai/latest/spec/error-registry/), which describes the members of this page
- [Error Codes](../../index.md), every Pipelex code
