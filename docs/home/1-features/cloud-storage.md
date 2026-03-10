---
title: Cloud Storage
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

## Configuration

Storage is configured in `pipelex.toml` under the `[storage]` section. Set the storage method (`local`, `in_memory`, `s3`, or `gcp`) and provide provider-specific settings like bucket names, regions, and credential paths.

For AWS configuration, see [AWS Configuration](../7-configuration/config-technical/aws-config.md).
