from enum import StrEnum


class CredentialResolution(StrEnum):
    """Whether a load of the inference backend library resolves the credentials its files reference.

    `REQUIRE` is the boot that needs inference: every `${…}` placeholder is substituted, and a
    credential that cannot be resolved is an error naming the variable. `SKIP` is the keyless boot:
    it substitutes nothing and asks the secrets provider nothing, yet keeps every enabled backend with
    its models and constraints, so it knows every model a keyed boot knows. What it cannot do is call
    a provider, and each backend records what it left unresolved so that a call is refused.
    """

    REQUIRE = "require"
    SKIP = "skip"
