class URLs:
    logo_white_on_transparent = "https://d2cinlfp2qnig1.cloudfront.net/logo/Pipelex-logo-wot-1119x352.png"
    logo_black_on_transparent = "https://d2cinlfp2qnig1.cloudfront.net/logo/Pipelex-logo-bot-1119x352.png"
    homepage = "https://pipelex.com"
    app = "https://app.pipelex.com/"
    repository = "https://github.com/Pipelex/pipelex"
    documentation = "https://docs.pipelex.com/"
    changelog = "https://docs.pipelex.com/latest/changelog/"
    discord = "https://go.pipelex.com/discord"
    privacy_policy = "https://go.pipelex.com/privacy-policy"
    telemetry_docs = "https://docs.pipelex.com/latest/setup/telemetry/"
    gateway_docs = (
        "https://docs.pipelex.com/latest/setup/configure-ai-providers/#option-1-pipelex-gateway-easiest-and-most-powerful-for-getting-started"
    )
    pipe_func_docs = "https://docs.pipelex.com/latest/building-methods/pipes/pipe-operators/PipeFunc/"
    backend_provider_docs = "https://docs.pipelex.com/latest/setup/configure-ai-providers/"
    native_concepts_docs = "https://docs.pipelex.com/latest/building-methods/concepts/native-concepts/"
    app_cli_auth = "https://app.pipelex.com/auth/cli"

    # Base for the RFC 7807 ``type`` URI of every PipelexError class. A stable
    # identifier by spec — kept as a constant so PipelexError.type_uri() stays
    # pure (no process config, safe inside Temporal workflow code). No trailing
    # slash: type_uri() appends ``/<kebab-class-name>/``.
    error_docs_base = "https://docs.pipelex.com/latest/errors"

    jpg_example_1 = "https://pipelex-pytest-assets.s3.eu-west-3.amazonaws.com/jpg_example_1.jpg"
    jpg_example_2 = "https://pipelex-pytest-assets.s3.eu-west-3.amazonaws.com/jpg_example_2.jpg"
    jpg_example_3 = "https://pipelex-pytest-assets.s3.eu-west-3.amazonaws.com/jpg_example_3.jpg"

    pdf_example_1 = "https://pipelex-pytest-assets.s3.eu-west-3.amazonaws.com/pdf_example_1.pdf"
    pdf_example_2 = "https://pipelex-pytest-assets.s3.eu-west-3.amazonaws.com/pdf_example_2.pdf"
    pdf_example_3 = "https://pipelex-pytest-assets.s3.eu-west-3.amazonaws.com/pdf_example_3.pdf"

    svg_example = "https://pipelex-pytest-assets.s3.eu-west-3.amazonaws.com/svg_example.svg"

    png_example_1 = "https://pipelex-pytest-assets.s3.eu-west-3.amazonaws.com/png_example_1.png"
    png_example_2 = "https://pipelex-pytest-assets.s3.eu-west-3.amazonaws.com/png_example_2.png"
    png_example_3 = "https://pipelex-pytest-assets.s3.eu-west-3.amazonaws.com/png_example_3.png"

    txt_example = "https://pipelex-pytest-assets.s3.eu-west-3.amazonaws.com/txt_example.txt"

    openai_billing = "https://platform.openai.com/account/billing"
    anthropic_billing = "https://platform.claude.com/settings/billing"
    google_billing = "https://console.cloud.google.com/billing"
    mistral_billing = "https://admin.mistral.ai/organization/billing"
    aws_billing = "https://console.aws.amazon.com/billing"
    linkup_billing = "https://app.linkup.so/organization/billing"
    fal_billing = "https://fal.ai/dashboard/usage-billing/billing"
