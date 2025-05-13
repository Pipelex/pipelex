# SPDX-FileCopyrightText: © 2025 Evotis S.A.S.
# SPDX-License-Identifier: Elastic-2.0
# "Pipelex" is a trademark of Evotis S.A.S.

"""
Use it like that:
python -m pipelex.tools.secrets.secrets_cli env OPENAI_API_KEY
python -m pipelex.tools.secrets.secrets_cli env OPENAI_API_KEY --version-id latest
python -m pipelex.tools.secrets.secrets_cli gcp OPENAI_API_KEY
python -m pipelex.tools.secrets.secrets_cli gcp OPENAI_API_KEY --version-id latest
"""

from typing import Annotated, Optional

import typer

from pipelex.tools.secrets.env_secrets_provider import EnvSecretsProvider

app = typer.Typer(help="CLI tool to fetch secrets from environment and GCP Secret Manager")


@app.command()
def env(
    secret_id: Annotated[str, typer.Argument(help="Secret ID defined in environment variables")],
    version_id: Annotated[Optional[str], typer.Option("--version-id", "-v", help="Version ID of the secret to use")] = None,
) -> None:
    """
    Fetch a secret from environment variables.
    """
    secrets_provider = EnvSecretsProvider()
    if version_id:
        secret = secrets_provider.get_required_secret_specific_version(secret_id=secret_id, version_id=version_id)
    else:
        secret = secrets_provider.get_required_secret(secret_id=secret_id)
    typer.echo(f"secret '{secret_id}' = '{secret}'")


if __name__ == "__main__":
    app()
