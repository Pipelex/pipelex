from typing import Any, ClassVar


class HostedAccountCheckTestData:
    """An account the hosted end-to-end cases expect, as the environment states it, and the `/v1/me` answers to it."""

    KEY_ENV = "PIPELEX_API_KEY"
    API_KEY = "plx_sk_test_not_a_secret"
    DEV_BASE_URL = "https://api-dev.example.test"
    ORG_ID = "org_11111111-1111-4111-8111-111111111111"
    OTHER_ORG_ID = "org_22222222-2222-4222-8222-222222222222"
    ROLE = "member"
    EMAIL = "qa+builder@example.test"

    ENVIRON: ClassVar[dict[str, str]] = {
        "PIPELEX_API_KEY": API_KEY,
        "PIPELEX_BASE_URL": DEV_BASE_URL,
        "PIPELEX_API_KEY_EXPECTED_ORG_ID": ORG_ID,
        "PIPELEX_API_KEY_EXPECTED_ROLE": ROLE,
        "PIPELEX_API_KEY_EXPECTED_EMAIL": EMAIL,
    }

    MATCHING_ME: ClassVar[dict[str, Any]] = {
        "user_id": "user_33333333-3333-4333-8333-333333333333",
        "email": EMAIL,
        "full_name": "QA Builder",
        "onboarding_completed_at": None,
        "organization": {"org_id": ORG_ID, "name": "QA Runtime", "role_in_org": ROLE},
        "api_key": {
            "id": "apikey_44444444-4444-4444-8444-444444444444",
            "label": "qa.runtime",
            "created_at": "2026-10-27T03:58:46Z",
            "expires_at": None,
        },
    }
