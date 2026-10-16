---
title: "pipelex.security.result_outside_scope"
description: "A result location lies outside the run: what the Pipelex error code pipelex.security.result_outside_scope means, who must act and what to do."
---

# pipelex.security.result_outside_scope

**A result location lies outside the run**

| | |
|---|---|
| Type | `https://docs.pipelex.com/errors/pipelex.security.result_outside_scope` |
| Family | [`pipelex.security`](../../index.md#pipelex-security): Pipelex's own refusals made for safety, each recorded as a security event. |
| [Domain](https://mthds.ai/latest/spec/protocol/#domain-who-must-act) | `runtime`: nobody could have acted beforehand, so whoever made the call waits, retries or reports the problem |
| [Retry](https://mthds.ai/latest/spec/protocol/#retry) | `no`: repeating the operation fails the same way |
| HTTP status | `500` |
| Raised as | a problem document, sent as the body of an HTTP response or kept in a run's record |

## What it means

A result location that a step reported, or that storage holds, lies outside the run's own storage scope. The runtime refuses it, and records the refusal as a security event.

## What to do

Report the problem to whoever runs the runtime, with the run's `pipeline_run_id`.

## Next steps

A problem carries the [step](https://mthds.ai/latest/spec/protocol/#next-steps) aimed at whoever reads it: the first when its reader is the domain's actor, whoever made the call, and the second for any other reader.

| Reader | Kind | Detail |
|---|---|---|
| The domain's actor | `report` | Report this to whoever runs the runtime. |
| Any other reader | `report` | Report this to whoever runs the runtime. |

## Detail

The problem's `detail` is written from this template, filled with the occurrence's parameters:

> A result location lies outside the run's storage scope, so the runtime refused it.

## Parameters

This code declares no parameters, so its problems carry no `params`.

## See also

- [The MTHDS error registry format](https://mthds.ai/latest/spec/error-registry/), which describes the members of this page
- [Error Codes](../../index.md), every Pipelex code
