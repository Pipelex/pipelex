# PipeJinja2

The `PipeJinja2` operator is a powerful utility for rendering [Jinja2 templates](https://jinja.palletsprojects.com/). It allows you to dynamically generate text by combining data from your pipeline's working memory with a template. This is ideal for creating formatted reports, HTML content, or constructing complex, multi-part prompts for LLMs.

## How it works

`PipeJinja2` takes all the data currently in the `WorkingMemory` and uses it as the context for rendering a Jinja2 template. The resulting text is then saved back to the working memory as a new `Text` output.

The template itself can be provided in one of two ways:
1.  **By Name**: Referring to a template file that has been loaded into Pipelex's template provider. This is the most common and maintainable method.
2.  **Inline**: Providing the template as a multi-line string directly in the `.plx` file.

### Templating Context

The Jinja2 template has access to all the "stuffs" currently in the working memory. You can access them by the names they were given in previous pipeline steps. For example, if a previous step produced an output named `user_profile`, you can access its attributes in the template like `{{ user_profile.name }}` or `{{ user_profile.email }}`.

## Configuration

`PipeJinja2` is configured in your pipeline's `.plx` file.

### PLX Parameters

| Parameter       | Type            | Description                                                                                               | Required                    |
| --------------- | --------------- | --------------------------------------------------------------------------------------------------------- | --------------------------- |
| `type`          | string          | The type of the pipe: `PipeJinja2`                                                                       | Yes                         |
| `definition`   | string          | A description of the Jinja2 operation.                                                                   | Yes                         |
| `output`        | string          | The concept for the output. Defaults to `native.Text`.                                                    | No                          |
| `jinja2_name`   | string          | The name of a pre-loaded template file.                                                                   | Yes (or `jinja2`)           |
| `jinja2`        | string          | An inline Jinja2 template string.                                                                         | Yes (or `jinja2_name`)      |
| `extra_context` | table (dict)    | A table of key-value pairs to add to the rendering context, making them available as variables in the template. | No                          |

### Example: Generating a report from a template file

This example assumes you have a user profile object and a list of activities in the working memory, and a template file named `weekly_report.md` has been registered.

**`weekly_report.md` template file:**
```jinja
# Weekly Report for {{ user.name }}

Hello {{ user.first_name }},

Here is a summary of your activity this week:

{% for activity in activities %}
- {{ activity.timestamp }}: {{ activity.description }}
{% else %}
- No activity logged this week.
{% endfor %}

Report generated on: {{ report_date }}
```

**Pipeline PLX definition:**
```plx
[pipe.generate_weekly_report]
type = "PipeJinja2"
definition = "Generate a formatted weekly report for a user"
output = "WeeklyReportText"
jinja2_name = "weekly_report.md"
extra_context = { report_date = "2023-10-27" }
```

In this scenario:
- `PipeJinja2` will load the `weekly_report.md` template.
- It will use the `user` and `activities` objects from the working memory.
- It will add `report_date` to the context from the `extra_context` table.
- The rendered markdown text will be saved as the `WeeklyReportText` concept. 