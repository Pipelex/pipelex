---
title: "Discord Newsletter Example"
description: "Generate HTML newsletters from Discord channel data — summarize messages, organize by category, and format as a weekly digest."
---

# Example: Discord Newsletter

!!! warning "Work in Progress"
    This example is under active development and may change.

This example generates HTML newsletters from Discord channel data. It summarizes messages from each channel, organizes them by category (Share, Introduce Yourself, Geographic Hubs), and formats everything as a weekly newsletter.

## Get the code

[![GitHub](https://img.shields.io/badge/View_on_GitHub-5a0dad?logo=github&logoColor=white&style=flat)](https://github.com/Pipelex/pipelex-cookbook/blob/main/examples/wip/discord_newsletter/bundle.mthds)

## What it demonstrates

- `PipeCondition` for conditional routing based on channel name
- Structured Discord data concepts (messages, attachments, embeds, channels)
- Channel-specific summarization strategies (new members vs. general)
- `PipeCompose` with complex Jinja2 HTML template (filtering, sorting, conditional sections)
- Custom Python runner for loading external JSON data

## The Method: `bundle.mthds`

### Pipeline

```toml
[pipe.write_discord_newsletter]
type = "PipeSequence"
inputs = { discord_channel_updates = "DiscordChannelUpdate[]" }
output = "HtmlNewsletter"
steps = [
  { pipe = "summarize_discord_channel_update",
    batch_over = "discord_channel_updates", batch_as = "discord_channel_update",
    result = "channel_summaries" },
  { pipe = "write_weekly_summary", result = "weekly_summary" },
  { pipe = "format_html_newsletter", result = "html_newsletter" },
]
```

### Conditional routing

The `summarize_discord_channel_update` pipe uses `PipeCondition` to route different channels to different summarization strategies:

```toml
[pipe.summarize_discord_channel_update]
type            = "PipeCondition"
description     = "Select the appropriate summary pipe based on the channel name"
inputs          = { discord_channel_update = "DiscordChannelUpdate" }
output          = "ChannelSummary"
expression      = "discord_channel_update.name"
outcomes        = { "Introduce-Yourself" = "summarize_discord_channel_update_for_new_members" }
default_outcome = "summarize_discord_channel_update_general"
```

## How to run

This example requires a custom Python runner to load Discord channel data from JSON:

```bash
cd examples/wip/discord_newsletter
python run_discord_newsletter.py
```

## Related Documentation

- [PipeCondition Controller](../building-methods/pipes/pipe-controllers/PipeCondition.md) - Conditional pipe routing
- [PipeCompose Operator](../building-methods/pipes/pipe-operators/PipeCompose.md) - Template-based data composition
- [PipeSequence Controller](../building-methods/pipes/pipe-controllers/PipeSequence.md) - Chain pipes into sequential workflows
