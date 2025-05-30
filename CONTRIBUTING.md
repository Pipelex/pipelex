# Contributing to Pipelex

Thank you for your interest in contributing! Contributions are very welcome. We appreciate first time contributors and we are happy help you get started. Join our community on Discord and feel free to reach out with questions in the #code-contributions and #pipeline-contributions channels.

Everyone interacting in Discord, codebases, mailing lists, events, or any other Pipelex activities is expected to follow the [Code of Conduct](CODE_OF_CONDUCT.md). Please review it before getting started.

Most of the issues that are open for contributions are tagged with `good first issue` or `help-welcome`. If you see an issue that isn't tagged that you're interested in, post a comment with your approach, and we'll be happy to assign it to you. If you submit a fix that isn't linked to an issue you're assigned, there's chance it won't be accepted. Don't hesitate to ping the Pipelex team on Discord to discuss your choice of issue before getting to work.

We are open to contributions in all areas of our core Pipelex library:

- **Bug fixes**: Crashes, incorrect output, performance issues
- **Feature**: New API, CLI flag, module, test coverage
- **Refactor**: Rethink architecture
- **Chore**: Dependency updates, config tweaks, file renames
- **Doc**: Main docs, SWE Agent rules, tutorials, examples, READMEs
- **CI/CD**: GitHub Actions, packaging, release tooling

## Contribution process

- Fork the Pipelex repository
- Clone the repository locally
- Install dependencies: `make install` (creates .venv and installs dependencies)
- Copy `.env.example` to `.env` and fill in required API keys (at least OpenAI)
- Run checks to make sure all is good: `make check` & `make runtests`
- Create a branch with the format user_name/category/short_slug where category is one of: `feature`, `fix`, `refactor`, `doc`, `cicd` or `chore`
- Make and commit changes
- Push your local branch to your fork
- Open a PR that [links to an existing Issue](https://docs.github.com/en/issues/tracking-your-work-with-issues/linking-a-pull-request-to-an-issue) which does not include the `needs triage` label
- Write a PR title and description by filling the template
- CI tests will be triggered and maintainers will review the code
- Respond to feedback if required
- Merge the contribution

## Requirements

- Python ≥ 3.11 < 3.12
- uv ≥ 0.7.2

## Development Setup

- Fork & clone the repository
- Run `make install` to set up virtualenv and dependencies
- Copy `.env.example` to `.env` and configure API keys
- Use uv for dependency management:
  - Runtime deps: `uv pip install <package>`
  - Dev deps: `uv pip install --extra dev <package>`
  - Keep dependencies alphabetically ordered in pyproject.toml

## Pull Request Process

- Fork the Pipelex repository
- Clone the repository locally
- Install dependencies: `make install` (creates .venv and installs dependencies)
- Copy `.env.example` to `.env` and fill in required API keys (at least OpenAI)
- Run checks to make sure all is good: `make check` & `make runtests`
- Create a branch for your feature/bug-fix with the format user_name/feature/some_feature or user_name/fix/some_bugfix
- Make and commit changes
- Push your local branch to your fork
- When it's ready, run quality tests:
- Run `make fix-unused-imports` to removed unused imports
- Run `make check` for formatting & linting with Ruff, and type-checking with Pyright and Mypy
- Run `make runtests` for test suite
- Open a PR that [links to an existing Issue](https://docs.github.com/en/issues/tracking-your-work-with-issues/linking-a-pull-request-to-an-issue) including a PR title and description
- Mark as Draft until CI passes
- Maintainers will review the code
- Respond to feedback if required
- Merge the contribution

## Environment Setup

- Copy `.env.example` to `.env`
- Fill in required credentials (OPENAI_API_KEY, AWS_ACCESS_KEY_ID, etc.)
- Never commit `.env`

## License

* **CLA** – The first time you open a PR, the CLA-assistant bot will guide you through signing the Contributor License Agreement. The process signature uses the [CLA assistant lite](https://github.com/marketplace/actions/cla-assistant-lite).
* **Code of Conduct** – Be kind. All interactions fall under [`CODE_OF_CONDUCT.md`](CODE_OF_CONDUCT.md).
