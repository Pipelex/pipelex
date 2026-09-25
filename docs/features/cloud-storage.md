---
title: Cloud Storage
description: "Store pipeline artifacts on AWS S3, Google Cloud Storage, or local disk. Pipelex handles uploads, signed URLs, and access control out of the box."
---

# Cloud Storage

Store generated artifacts on cloud infrastructure.

## Overview

Pipelex can automatically upload generated artifacts — images, extracted pages, and other outputs — to cloud storage providers with configurable access control. For development and testing, local filesystem and in-memory storage are also available.

## Supported Providers

- **Local filesystem** — Store artifacts on the local disk (default for development)
- **In-memory** — Ephemeral storage for testing, no persistence
- **AWS S3** — Amazon Simple Storage Service with configurable region and bucket
- **Google Cloud Storage** — GCS buckets with project-level credentials

## URL Options

- **Public URLs** — Directly accessible URLs for public content
- **Signed URLs** — Time-limited secure URLs for private content, with configurable lifespan

### The host an S3 link names

An S3 link, signed or not, is virtual-hosted on the bucket's own regional host: `https://<bucket>.s3.<region>.amazonaws.com/<key>`. The runtime's own reads and writes go to that host too. A page that shows the runtime's links under a content security policy therefore allows that one origin, which covers your bucket and no one else's, where the region's shared endpoint `https://s3.<region>.amazonaws.com` would cover every bucket in the region.

The exception is a legacy bucket name that cannot be a hostname, one with uppercase letters or an underscore. Its links are path-style on the regional endpoint, `https://s3.<region>.amazonaws.com/<bucket>/<key>`, so a policy must allow the shared endpoint for it. Name a bucket with lowercase letters, digits and hyphens only if its links have to be allowed on their own. A bucket name containing a dot is refused by the storage configuration; it could not be virtual-hosted over HTTPS anyway, because it breaks the `*.s3.<region>.amazonaws.com` wildcard certificate.

A deployment whose egress rules allow S3 by hostname must allow `*.s3.<region>.amazonaws.com`, not only `s3.<region>.amazonaws.com`.

## Configuration

Storage is configured in `pipelex.toml` under `[runtime.storage]`. Set `method` to `local`, `in_memory`, `s3`, or `gcp`, then provide provider-specific settings such as `bucket_name`, `region`, or `project_id` in the matching subsection.

For AWS configuration, see [AWS Configuration](../configuration/config-technical/aws-config.md).
