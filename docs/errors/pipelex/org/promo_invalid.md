---
title: "pipelex.org.promo_invalid"
description: "The promo code cannot be redeemed: what the Pipelex error code pipelex.org.promo_invalid means, who must act and what to do."
---

# pipelex.org.promo_invalid

**The promo code cannot be redeemed**

| | |
|---|---|
| Type | `https://docs.pipelex.com/errors/pipelex.org.promo_invalid` |
| Family | [`pipelex.org`](../../index.md#pipelex-org): Organizations, their members, their API keys and their promo codes. |
| [Domain](https://mthds.ai/latest/spec/protocol/#domain-who-must-act) | `input`: the caller acts, by changing the request or its inputs |
| [Retry](https://mthds.ai/latest/spec/protocol/#retry) | `no`: repeating the operation fails the same way |
| HTTP status | `422` |
| Raised as | a problem document, sent as the body of an HTTP response or kept in a run's record |

## What it means

The promo code is not one this organization can redeem. The reason is withheld on purpose, so that a code cannot be guessed by trying.

## What to do

Check the promo code as it was given to you, and ask whoever gave it for one that is valid.

## Next steps

A problem carries the [step](https://mthds.ai/latest/spec/protocol/#next-steps) aimed at whoever reads it: the first when its reader is the domain's actor, the caller, and the second for any other reader.

| Reader | Kind | Detail |
|---|---|---|
| The domain's actor | `change_input` | Check the promo code, then redeem one that is valid. |
| Any other reader | `change_input` | Pass this to the caller, whose promo code cannot be redeemed. |

## Detail

The problem's `detail` is written from this template, filled with the occurrence's parameters:

> The promo code cannot be redeemed.

## Parameters

This code declares no parameters, so its problems carry no `params`.

## See also

- [The MTHDS error registry format](https://mthds.ai/latest/spec/error-registry/), which describes the members of this page
- [Error Codes](../../index.md), every Pipelex code
