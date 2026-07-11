from typing import NamedTuple

from pydantic import BaseModel, ConfigDict

from pipelex.tools.misc.string_utils import is_pascal_case, is_snake_case


class QualifiedRefError(ValueError):
    """Raised when a qualified reference string is invalid."""


class CrossPackageRef(NamedTuple):
    alias: str
    remainder: str


class QualifiedRef(BaseModel):
    """A domain-qualified reference to a concept or pipe.

    Concept ref: "legal.contracts.NonCompeteClause" -> domain_path="legal.contracts", local_code="NonCompeteClause"
    Pipe ref: "scoring.compute_score" -> domain_path="scoring", local_code="compute_score"
    Bare ref: "compute_score" -> domain_path=None, local_code="compute_score"
    """

    model_config = ConfigDict(frozen=True)

    domain_path: str | None = None
    local_code: str

    @property
    def is_qualified(self) -> bool:
        return self.domain_path is not None

    @property
    def full_ref(self) -> str:
        if self.domain_path:
            return f"{self.domain_path}.{self.local_code}"
        return self.local_code

    @classmethod
    def parse(cls, raw: str) -> "QualifiedRef":
        """Split on last dot. No naming-convention check on local_code.

        Args:
            raw: The raw reference string to parse

        Returns:
            A QualifiedRef with domain_path and local_code

        Raises:
            QualifiedRefError: If the raw string is empty, starts/ends with a dot,
                or contains consecutive dots
        """
        if not raw:
            msg = "Qualified reference cannot be empty"
            raise QualifiedRefError(msg)
        if raw.startswith(".") or raw.endswith("."):
            msg = f"Qualified reference '{raw}' must not start or end with a dot"
            raise QualifiedRefError(msg)
        if ".." in raw:
            msg = f"Qualified reference '{raw}' must not contain consecutive dots"
            raise QualifiedRefError(msg)

        if "." not in raw:
            return cls(domain_path=None, local_code=raw)

        domain_path, local_code = raw.rsplit(".", maxsplit=1)
        return cls(domain_path=domain_path, local_code=local_code)

    @classmethod
    def parse_stripping_cross_package(cls, raw: str) -> "QualifiedRef":
        """Strip any cross-package prefix ('alias->...') then parse.

        Use this when the caller may receive a cross-package reference but only
        needs the domain + local_code part, not the alias.
        """
        if cls.has_cross_package_prefix(raw):
            _, raw = cls.split_cross_package_ref(raw)
        return cls.parse(raw)

    @classmethod
    def parse_concept_ref(cls, raw: str) -> "QualifiedRef":
        """Parse a concept ref. Validates domain_path segments are snake_case, local_code is PascalCase.

        Args:
            raw: The raw concept reference string to parse

        Returns:
            A QualifiedRef with validated domain_path and local_code

        Raises:
            QualifiedRefError: If the ref is invalid
        """
        ref = cls.parse(raw)

        if not is_pascal_case(ref.local_code):
            msg = f"Concept code '{ref.local_code}' in reference '{raw}' must be PascalCase"
            raise QualifiedRefError(msg)

        if ref.domain_path is not None:
            for segment in ref.domain_path.split("."):
                if not is_snake_case(segment):
                    msg = f"Domain segment '{segment}' in reference '{raw}' must be snake_case"
                    raise QualifiedRefError(msg)

        return ref

    @classmethod
    def parse_pipe_ref(cls, raw: str) -> "QualifiedRef":
        """Parse a pipe ref. Validates domain_path segments are snake_case, local_code is snake_case.

        Args:
            raw: The raw pipe reference string to parse

        Returns:
            A QualifiedRef with validated domain_path and local_code

        Raises:
            QualifiedRefError: If the ref is invalid
        """
        ref = cls.parse(raw)

        if not is_snake_case(ref.local_code):
            msg = f"Pipe code '{ref.local_code}' in reference '{raw}' must be snake_case"
            raise QualifiedRefError(msg)

        if ref.domain_path is not None:
            for segment in ref.domain_path.split("."):
                if not is_snake_case(segment):
                    msg = f"Domain segment '{segment}' in reference '{raw}' must be snake_case"
                    raise QualifiedRefError(msg)

        return ref

    @classmethod
    def from_domain_and_code(cls, *, domain_path: str, local_code: str) -> "QualifiedRef":
        """Build from already-known parts.

        Args:
            domain_path: The domain path (e.g. "legal.contracts")
            local_code: The local code (e.g. "NonCompeteClause" or "compute_score")

        Returns:
            A QualifiedRef
        """
        return cls(domain_path=domain_path, local_code=local_code)

    def is_local_to(self, domain: str) -> bool:
        """True if this ref belongs to the given domain (same domain or bare).

        Args:
            domain: The domain to check against

        Returns:
            True if this ref is local to the given domain
        """
        if self.domain_path is None:
            return True
        return self.domain_path == domain

    def is_external_to(self, domain: str) -> bool:
        """True if this ref belongs to a different domain.

        Args:
            domain: The domain to check against

        Returns:
            True if this ref is qualified and points to a different domain
        """
        if self.domain_path is None:
            return False
        return self.domain_path != domain

    @staticmethod
    def is_address_based_alias(alias: str) -> bool:
        """True if alias looks like a package address (contains '/').

        Regular aliases (e.g., "documents") never contain '/'.
        Address-based aliases (e.g., "github.com/Pipelex/methods/documents") always do.

        Args:
            alias: The alias string to check

        Returns:
            True if the alias contains '/'
        """
        return "/" in alias

    @staticmethod
    def has_cross_package_prefix(raw: str) -> bool:
        """Check if a raw reference string contains the cross-package '->' prefix.

        Cross-package references look like: 'alias->domain.pipe_code'

        Args:
            raw: The raw reference string to check

        Returns:
            True if the string contains '->'
        """
        return "->" in raw

    @staticmethod
    def split_cross_package_ref(raw: str) -> CrossPackageRef:
        """Split a cross-package reference into alias and remainder.

        Args:
            raw: The raw reference string like 'alias->domain.pipe_code'

        Returns:
            CrossPackageRef(alias, remainder) where remainder is 'domain.pipe_code'

        Raises:
            QualifiedRefError: If the string does not contain '->'
        """
        if "->" not in raw:
            msg = f"Reference '{raw}' is not a cross-package reference (no '->' found)"
            raise QualifiedRefError(msg)
        parts = raw.split("->", maxsplit=1)
        return CrossPackageRef(alias=parts[0], remainder=parts[1])
