---
title: "pipelex.org.required"
description: "An organization is required: what the Pipelex error code pipelex.org.required means, who must act and what to do."
---

# pipelex.org.required

**An organization is required**

| | |
|---|---|
| Type | `https://docs.pipelex.com/errors/pipelex.org.required` |
| Family | [`pipelex.org`](../../index.md#pipelex-org): Organizations, their members, their API keys and their promo codes. |
| [Domain](https://mthds.ai/latest/spec/protocol/#domain-who-must-act) | `account`: the account's owner acts |
| [Retry](https://mthds.ai/latest/spec/protocol/#retry) | `no`: repeating the operation fails the same way |
| HTTP status | `403` |
| Raised as | a problem document, sent as the body of an HTTP response or kept in a run's record |

## What it means

The caller acts for no organization, and the route acts on an organization's resources.

## What to do

Sign in to an organization, or use an API key that belongs to one, then send the request again.

## Next steps

A problem carries the [step](https://mthds.ai/latest/spec/protocol/#next-steps) aimed at whoever reads it: the first when its reader is the domain's actor, the account's owner, and the second for any other reader.

| Reader | Kind | Detail |
|---|---|---|
| The domain's actor | `check_account` | Act for an organization, by joining or creating one, then send the request again. |
| Any other reader | `contact_owner` | Ask the account's owner to add you to an organization. |

## Detail

The problem's `detail` is written from this template, filled with the occurrence's parameters:

> This operation acts on an organization, and the request acts for none.

## Parameters

This code declares no parameters, so its problems carry no `params`.

## See also

- [The MTHDS error registry format](https://mthds.ai/latest/spec/error-registry/), which describes the members of this page
- [Error Codes](../../index.md), every Pipelex code
