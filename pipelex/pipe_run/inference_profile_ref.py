"""Neutral reference to an externally-stored inference configuration (an "inference profile").

Core ships mechanism only: the runtime stores and transports this ref on the run payload but
never resolves it — no profile store, no resolver, no credentials. A hosting layer that owns a
profile store stamps the ref at submission and consumes it wherever it binds the run to the
profile's inference configuration (worker-side verification, usage attribution). Field names are
tenant-neutral: ``owner_id`` identifies whatever entity owns the profile in that store.
"""

from pydantic import BaseModel, ConfigDict, Field


class InferenceProfileRef(BaseModel):
    """Reference to a named inference configuration held by an external store.

    Travels in the serialized run payload (``PipeRunParams`` and the derived ``CogtRunParams``
    carrier stamped on every cogt assignment), so it survives process boundaries. It must never
    be carried by ambient state alone — ContextVars may only re-expose it in-process after
    deserialization.
    """

    # `frozen=True`: a value object — the selection must not drift mid-run. `extra="forbid"`:
    # a typo'd key on a wire payload must fail loud (mirrors CogtRunParams / LibraryCrate).
    model_config = ConfigDict(frozen=True, extra="forbid")

    owner_id: str = Field(min_length=1)
    profile_id: str = Field(min_length=1)
    # Content marker of the profile version the run was bound to (e.g. a digest over the profile's
    # configuration and a credential-version counter). Opaque to core; recorded for traceability
    # and verified by workers that were booted for a specific profile version.
    fingerprint: str = Field(min_length=1)

    @property
    def ref_str(self) -> str:
        """Compact form for logs and error messages — carries no credential material."""
        return f"{self.owner_id}/{self.profile_id}@{self.fingerprint}"
