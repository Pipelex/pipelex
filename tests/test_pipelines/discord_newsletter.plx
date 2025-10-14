domain = "discord_newsletter"
description = "Create newsletters from Discord channel content by summarizing messages and organizing them according to newsletter format"

[concept]
DiscordChannelUpdate = "A Discord channel with its messages for newsletter generation"
ChannelSummary = "A summarized Discord channel for newsletter inclusion"
HtmlNewsletter = "The final newsletter content in html format with organized channel summaries"

[pipe.write_discord_newsletter]
type = "PipeSequence"
description = "Create a newsletter from Discord articles by summarizing channels and organizing content"
inputs = { discord_channel_updates = "DiscordChannelUpdate" }
output = "HtmlNewsletter"
steps = [
   { pipe = "summarize_discord_channel_update", batch_over = "discord_channel_updates", batch_as = "discord_channel_update", result = "channel_summaries" },
   { pipe = "write_weekly_summary", result = "weekly_summary" },
   { pipe = "format_html_newsletter", result = "html_newsletter" },
]


[pipe.summarize_discord_channel_update]
type = "PipeCondition"
description = "Select the appropriate summary pipe based on the channel name"
inputs = { discord_channel_update = "DiscordChannelUpdate" }
output = "ChannelSummary"
expression = "discord_channel_update.name"
outcomes = { "Introduce-Yourself" = "summarize_discord_channel_update_for_new_members" }
default_outcome = "summarize_discord_channel_update_general"

[pipe.summarize_discord_channel_update_for_new_members]
type = "PipeLLM"
description = "Summarize the new member announcements"
inputs = { discord_channel_update = "DiscordChannelUpdate" }
output = "ChannelSummary"
system_prompt = "You are a newsletter editor who creates engaging summaries of Discord channel content. You extract key information, preserve important links, and write in a clear, concise style suitable for newsletter readers."
prompt = """
Analyze this Discord channel update and create a newsletter-friendly summary.

Channel Information:
@discord_channel_update

Summarize with one bullet point for each new member
"""

[pipe.summarize_discord_channel_update_general]
type = "PipeLLM"
description = "Summarize a Discord channel's messages into newsletter-friendly content"
inputs = { discord_channel_update = "DiscordChannelUpdate" }
output = "ChannelSummary"
system_prompt = "You are a newsletter editor who creates engaging summaries of Discord channel content. You extract key information, preserve important links, and write in a clear, concise style suitable for newsletter readers."
prompt = """
Analyze this Discord channel update and create a newsletter-friendly summary.

Channel Information:
@discord_channel_update

The summary should be informative and engaging for newsletter readers who want to understand what happened in this channel during the week.
Generate one or more summary items: each one can correspond to a single message or to a bunch of messages that were part of the same conversation.
Each summary item should be in plain text, no bullet points. You can make some parts **bold** to highlight important information.

Make sure to preserve the channel name and position from the input for proper ordering in the newsletter.
"""

[pipe.write_weekly_summary]
type = "PipeLLM"
description = "Combine channel summaries into a short summary of the week's Share channel content (200 characters)"
inputs = { channel_summaries = "ChannelSummary" }
output = "Text"
prompt = """
Write a single overall summary of the week's content based on the following Share channel summaries:

{% for channel in channel_summaries.content.items if channel.category == "Share" %}
{{ channel }}
{% endfor %}

Keep it short: 200 characters.
"""

[pipe.format_html_newsletter]
type = "PipeCompose"
description = "Combine weekly and channel summaries into a complete newsletter following specific formatting requirements"
inputs = { weekly_summary = "Text", channel_summaries = "ChannelSummary" }
output = "HtmlNewsletter"

[pipe.format_html_newsletter.template]
category = "html"
template = """
<!-- Weekly Summary -->
<h2>☀️ Weekly Summary</h2>
<p>
$weekly_summary
</p>

<!-- New Members Section -->
{% set introduce_channels = channel_summaries.content.items | selectattr('category', 'equalto', 'Introduce Yourself') | list %}
{% if introduce_channels %}
   <h2>🙌 New members</h2>
   <ul>
      {% for channel in introduce_channels %}
         {% for item in channel.summary_items_as_html %}
            <li>{{ item }}</li>
         {% endfor %}
      {% endfor %}
   </ul>
{% endif %}

<!-- Share Channel Section -->
{% set regular_channels = channel_summaries.content.items | selectattr('category', 'equalto', 'Share') | list | sort(attribute='position') %}
{% if regular_channels %}
   {% for channel in regular_channels %}
   <h2>{{ channel.channel_name }}</h2>
      {% for item in channel.summary_items_as_html %}
         <p>{{ item }}</p>
      {% endfor %}
   {% endfor %}
{% endif %}

<!-- Geographic Hubs Section -->
{% set geo_hubs = channel_summaries.content.items | selectattr('category', 'equalto', 'Geographic Hubs') | list | sort(attribute='position') %}
{% if geo_hubs %}
   <h2>🌎 Geographic hubs</h2>
   {% for channel in geo_hubs %}
      <h3>{{ channel.channel_name }}</h3>
      {% for item in channel.summary_items_as_html %}
         <p>{{ item }}</p>
      {% endfor %}
   {% endfor %}
{% endif %}
"""

