# PipeCompose

The `PipeCompose` operator is a powerful utility for rendering [Jinja2 templates](https://jinja.palletsprojects.com/). It allows you to dynamically generate text by combining data from your pipeline's working memory with a template. This is ideal for creating formatted reports, HTML content, or constructing complex, multi-part prompts for LLMs.

## How it works

`PipeCompose` takes all the data currently in the `WorkingMemory` and uses it as the context for rendering a Jinja2 template. The resulting text is then saved back to the working memory as a new `Text` output.

The template itself can be provided in one of two ways:
1.  **By Name**: Referring to a template file that has been loaded into Pipelex's template provider. This is the most common and maintainable method.
2.  **Inline**: Providing the template as a multi-line string directly in the `.plx` file.

### Templating Context

The Jinja2 template has access to all the "stuffs" currently in the working memory. You can access them by the names they were given in previous pipeline steps. For example, if a previous step produced an output named `user_profile`, you can access its attributes in the template like `{{ user_profile.name }}` or `{{ user_profile.email }}`.

## Configuration

`PipeCompose` is configured in your pipeline's `.plx` file.

### PLX Parameters

| Parameter       | Type            | Description                                                                                               | Required                    |
| --------------- | --------------- | --------------------------------------------------------------------------------------------------------- | --------------------------- |
| `type`          | string          | The type of the pipe: `PipeCompose`                                                                       | Yes                         |
| `description`   | string          | A description of the Jinja2 operation.                                                                   | Yes                         |
| `output`        | string          | The concept for the output. Defaults to `native.Text`.                                                    | No                          |
| `template`        | string          | An inline Jinja2 template string.                                                                         | Yes       |
| `extra_context` | table (dict)    | A table of key-value pairs to add to the rendering context, making them available as variables in the template. | No                          |
