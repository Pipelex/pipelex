---
title: "pipelex.deployment.token_claims_invalid"
description: "The token's claims cannot be used: what the Pipelex error code pipelex.deployment.token_claims_invalid means, who must act and what to do."
---

# pipelex.deployment.token_claims_invalid

**The token's claims cannot be used**

| | |
|---|---|
| Type | `https://docs.pipelex.com/errors/pipelex.deployment.token_claims_invalid` |
| Family | [`pipelex.deployment`](../../index.md#pipelex-deployment): The policies of a runner deployment. |
| [Domain](https://mthds.ai/latest/spec/protocol/#domain-who-must-act) | `operator`: whoever runs the runtime acts |
| [Retry](https://mthds.ai/latest/spec/protocol/#retry) | `no`: repeating the operation fails the same way |
| HTTP status | `500` |
| Raised as | a problem document, sent as the body of an HTTP response or kept in a run's record |

## What it means

A verified token carries a user id the runner cannot use, so the token's issuer is misconfigured.

## What to do

If you run the runtime, correct the claims its token issuer writes. Otherwise, report the problem to whoever runs it.

## Next steps

A problem carries the [step](https://mthds.ai/latest/spec/protocol/#next-steps) aimed at whoever reads it: the first when its reader is the domain's actor, whoever runs the runtime, and the second for any other reader.

| Reader | Kind | Detail |
|---|---|---|
| The domain's actor | `fix_configuration` | Correct the claim '`{claim}`' (`{reason}`) that the token issuer writes, then send the request again. |
| Any other reader | `report` | Report this to whoever runs the runtime. |

## Detail

The problem's `detail` is written from this template, filled with the occurrence's parameters:

> The request's verified token carries claims this runner cannot use.

## Parameters

A parameter is present on every occurrence of the code unless it is marked optional, and one marked operator-only reaches only whoever runs the runtime, never a caller.

| Name | Type | Description |
|---|---|---|
| `claim` | `identifier` (operator-only) | The claim at fault. |
| `reason` | one of `missing`, `unsafe`, `reserved` (operator-only) | What is wrong with the claim: it is missing, unsafe as an identifier, or reserved. |

## See also

- [API Server Configuration](../../../api-server/configuration.md)
- [The MTHDS error registry format](https://mthds.ai/latest/spec/error-registry/), which describes the members of this page
- [Error Codes](../../index.md), every Pipelex code
